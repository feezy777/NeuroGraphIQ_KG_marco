"""Macro Connection canonicalization Pipeline 第 3 层 — 纯函数测试(无 DB)。"""

import uuid

import pytest

from app.services.macro_connection_canonicalization import (
    ClusterRow,
    build_connection_code,
    build_evidence_aggregation,
    canonical_key,
    norm_dir,
    norm_type,
    pick_directionality,
    plan_canonicalization,
)


def _cluster(**overrides) -> ClusterRow:
    base = dict(
        id=1, cluster_key="k", source_region_id="s", target_region_id="t",
        source_region_name="Hippocampus", target_region_name="Prefrontal cortex",
        connection_type="structural_connection", directionality="directed",
        modality_norm="structural", modality_original=["diffusion_tensor"],
        species="human", hemisphere_groups=[{"pattern": "left-left", "evidence_count": 2}],
        mirror_connection_ids=[str(uuid.uuid4()) for _ in range(2)],
        evidence_count=2, merge_reason="duplicate_evidence",
        confidence_distribution={"count": 2, "min": 0.3, "max": 0.5, "avg": 0.4,
                                 "buckets": {"0.3": 1, "0.5": 1}},
        provenance={"llm_run_ids": ["r1"], "evidence_texts": ["text-a", "text-b"],
                    "directionality_original": ["directed"]},
    )
    base.update(overrides)
    return ClusterRow(**base)


class TestNorm:
    def test_type_norm(self):
        assert norm_type("structural_connection") == "structural"
        assert norm_type("functional_connectivity") == "functional"
        assert norm_type("uncertain_connection") == "uncertain"
        assert norm_type("association") == "association"
        assert norm_type("projection") == "projection"

    def test_dir_norm(self):
        assert norm_dir("unknown") == "unspecified"
        assert norm_dir("directed") == "directed"
        assert norm_dir("bidirectional") == "bidirectional"

    def test_canonical_key(self):
        # 同 region 对 + type 同 key;方向不进入 key(表约束语义)
        assert canonical_key("a", "b", "structural_connection") == \
            canonical_key("a", "b", "structural_connection")
        assert canonical_key("a", "b", "structural_connection") != \
            canonical_key("a", "b", "functional_connectivity")
        assert canonical_key("a", "b", "structural_connection") != \
            canonical_key("a", "c", "structural_connection")


class TestPlan:
    def test_reuse_existing_match(self):
        cl = _cluster()
        existing = [{"id": "c1", "source_region_id": "s", "target_region_id": "t",
                     "connection_type": "structural", "directionality_policy": "directed",
                     "species": "human", "connection_code": "ng:cn:x", "evidence_summary": {}}]
        plans = plan_canonicalization([cl], existing)
        assert plans[0].existing is True
        assert plans[0].canonical_id == "c1"

    def test_new_when_no_match(self):
        cl = _cluster()
        plans = plan_canonicalization([cl], [])
        assert plans[0].existing is False
        assert plans[0].canonical_id is None

    def test_direction_is_property_not_key(self):
        """方向不同仍匹配同一 canonical(与 uq_canonical_connection 约束一致)。"""
        cl = _cluster(directionality="unknown")
        existing = [{"id": "c1", "source_region_id": "s", "target_region_id": "t",
                     "connection_type": "structural", "directionality_policy": "directed",
                     "species": "human", "connection_code": "x", "evidence_summary": {}}]
        plans = plan_canonicalization([cl], existing)
        assert plans[0].existing is True
        assert plans[0].canonical_id == "c1"

    def test_multi_cluster_same_key_reuse_same_canonical(self):
        cls = [_cluster(id=1), _cluster(id=2)]
        existing = [{"id": "c1", "source_region_id": "s", "target_region_id": "t",
                     "connection_type": "structural", "directionality_policy": "directed",
                     "species": "human", "connection_code": "x", "evidence_summary": {}}]
        plans = plan_canonicalization(cls, existing)
        assert all(p.existing and p.canonical_id == "c1" for p in plans)


class TestPickDirectionality:
    def test_unknown_maps_to_unspecified(self):
        """raw 'unknown' 必须归一化为 'unspecified'(CHECK 约束词表)。"""
        assert pick_directionality(["unknown"]) == "unspecified"

    def test_single_directed(self):
        assert pick_directionality(["directed"]) == "directed"

    def test_mixed_directions_unspecified(self):
        assert pick_directionality(["directed", "bidirectional"]) == "unspecified"

    def test_unknown_and_directed_unspecified(self):
        assert pick_directionality(["unknown", "directed"]) == "unspecified"

    def test_empty_unspecified(self):
        assert pick_directionality([]) == "unspecified"


class TestConnectionCode:
    def test_basic_format(self):
        code = build_connection_code("structural_connection", "Hippocampus",
                                     "Prefrontal cortex", "directed", set())
        assert code == "ng:cn:structural_hippocampus_to_prefrontal_cortex"

    def test_conflict_suffix(self):
        used = {"ng:cn:structural_hippocampus_to_prefrontal_cortex"}
        code = build_connection_code("structural_connection", "Hippocampus",
                                     "Prefrontal cortex", "unknown", used)
        assert code == "ng:cn:structural_hippocampus_to_prefrontal_cortex_unspecified"


def _resolved(cls, existing):
    """plans → {cluster_id: canonical_id} 映射(模拟脚本解析后状态)。"""
    plans = plan_canonicalization(cls, existing)
    return {p.cluster.id: p.canonical_id for p in plans}


class TestEvidenceAggregation:
    def test_aggregates_counts_and_sources(self):
        cls = [_cluster(id=1), _cluster(id=2, evidence_count=3,
                                        mirror_connection_ids=[str(uuid.uuid4()) for _ in range(3)])]
        existing = [{"id": "c1", "source_region_id": "s", "target_region_id": "t",
                     "connection_type": "structural", "directionality_policy": "directed",
                     "species": "human", "connection_code": "x", "evidence_summary": {}}]
        agg = build_evidence_aggregation(_resolved(cls, existing), cls)
        a = agg["c1"]
        assert a["evidence_count"] == 5  # 2 + 3 守恒
        assert a["evidence_summary"]["cluster_count"] == 2
        assert len(a["evidence_summary"]["mirror_connection_ids"]) == 5
        assert a["evidence_sources"]["llm_run_ids"] == ["r1"]

    def test_confidence_stats_weighted(self):
        cls = [
            _cluster(id=1, confidence_distribution={"count": 2, "min": 0.3, "max": 0.5, "avg": 0.4,
                                                    "buckets": {"0.3": 1, "0.5": 1}}),
            _cluster(id=2, confidence_distribution={"count": 3, "min": 0.1, "max": 0.2, "avg": 0.15,
                                                    "buckets": {"0.1": 2, "0.2": 1}}),
        ]
        existing = [{"id": "c1", "source_region_id": "s", "target_region_id": "t",
                     "connection_type": "structural", "directionality_policy": "directed",
                     "species": "human", "connection_code": "x", "evidence_summary": {}}]
        agg = build_evidence_aggregation(_resolved(cls, existing), cls)
        cs = agg["c1"]["confidence_statistics"]
        assert cs["count"] == 5
        assert cs["min"] == 0.1 and cs["max"] == 0.5
        assert abs(cs["avg"] - (0.4 * 2 + 0.15 * 3) / 5) < 1e-6
        assert cs["buckets"] == {"0.1": 2, "0.2": 1, "0.3": 1, "0.5": 1}

    def test_no_confidence(self):
        cl = _cluster(confidence_distribution={})
        existing = [{"id": "c1", "source_region_id": "s", "target_region_id": "t",
                     "connection_type": "structural", "directionality_policy": "directed",
                     "species": "human", "connection_code": "x", "evidence_summary": {}}]
        agg = build_evidence_aggregation(_resolved([cl], existing), [cl])
        assert agg["c1"]["confidence_statistics"] == {"count": 0}

    def test_hemisphere_patterns_preserved(self):
        cl = _cluster(hemisphere_groups=[
            {"pattern": "left-left", "evidence_count": 1},
            {"pattern": "right-right", "evidence_count": 1},
        ])
        existing = [{"id": "c1", "source_region_id": "s", "target_region_id": "t",
                     "connection_type": "structural", "directionality_policy": "directed",
                     "species": "human", "connection_code": "x", "evidence_summary": {}}]
        agg = build_evidence_aggregation(_resolved([cl], existing), [cl])
        h = agg["c1"]["evidence_summary"]["hemisphere_patterns"]
        assert h == {"left-left": 1, "right-right": 1}
