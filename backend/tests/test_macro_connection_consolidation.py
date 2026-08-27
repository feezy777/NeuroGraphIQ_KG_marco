"""Macro Connection canonical consolidation v1 — 聚类纯函数测试(无 DB)。"""

import uuid

import pytest

from app.services.macro_connection_consolidation import (
    MERGE_REASON_DUPLICATE,
    MERGE_REASON_HEMISPHERE,
    MERGE_REASON_SELF_LOOP,
    MERGE_REASON_SINGLE,
    MERGE_REASON_UNRESOLVED,
    build_clusters,
    cluster_key,
    norm_modality,
    side_of,
)


def _row(**overrides):
    base = {
        "id": str(uuid.uuid4()),
        "source_region_name_en": "left hippocampus",
        "target_region_name_en": "left prefrontal cortex",
        "connection_type": "structural_connection",
        "directionality": "directed",
        "modality": "diffusion_tensor",
        "confidence": 0.5,
        "evidence_text": "evidence text",
        "llm_run_id": str(uuid.uuid4()),
        "g_status": "grounded",
        "unresolved_reason": None,
        "src_canonical_id": "11111111-1111-1111-1111-111111111111",
        "tgt_canonical_id": "22222222-2222-2222-2222-222222222222",
        "src_canonical_name": "Hippocampus",
        "tgt_canonical_name": "Prefrontal cortex",
    }
    base.update(overrides)
    return base


class TestSideOf:
    def test_left_right_bilateral(self):
        assert side_of("left caudate") == "left"
        assert side_of("Right amygdala") == "right"
        assert side_of("CSF") == "bilateral"
        assert side_of("cerebellar vermal lobules I-V") == "bilateral"
        assert side_of(None) == "bilateral"


class TestClusterKey:
    def test_key_uses_normalized_modality(self):
        k1 = cluster_key(1, 2, "structural_connection", "directed", "diffusion_tensor")
        k2 = cluster_key(1, 2, "structural_connection", "directed", "structural_connection")
        assert k1 == k2  # diffusion_tensor 与 structural_connection 归一到 structural

    def test_key_differs_on_type_direction(self):
        assert cluster_key(1, 2, "structural_connection", "directed", "functional_connection") != \
            cluster_key(1, 2, "structural_connection", "directed", "structural_connection")
        assert cluster_key(1, 2, "structural_connection", "directed", "structural_connection") != \
            cluster_key(1, 2, "structural_connection", "bidirectional", "structural_connection")


class TestBuildClusters:
    def test_duplicate_evidence_merges(self):
        """同一 canonical key + 同一 hemisphere pattern 的 3 条合并为 1 个 cluster。"""
        rows = [_row() for _ in range(3)]
        res = build_clusters(rows)
        assert len(res.clusters) == 1
        c = res.clusters[0]
        assert c.evidence_count == 3
        assert c.merge_reason == MERGE_REASON_DUPLICATE
        assert len(c.hemisphere_groups) == 1
        assert c.hemisphere_groups[0]["pattern"] == "left-left"
        assert len(c.hemisphere_groups[0]["mirror_connection_ids"]) == 3
        assert len({ev.mirror_id for ev in c.evidence}) == 3  # id 全保留

    def test_hemisphere_specific_kept_separate(self):
        """left-left 与 right-right 同 key 但 pattern 不同 → 不合并,标记 hemisphere_specific。"""
        rows = [
            _row(),
            _row(source_region_name_en="right hippocampus", target_region_name_en="right prefrontal cortex"),
        ]
        res = build_clusters(rows)
        assert len(res.clusters) == 1
        c = res.clusters[0]
        assert c.evidence_count == 2  # 证据都保留
        assert c.merge_reason == MERGE_REASON_HEMISPHERE
        patterns = {g["pattern"] for g in c.hemisphere_groups}
        assert patterns == {"left-left", "right-right"}

    def test_single_evidence(self):
        res = build_clusters([_row()])
        assert len(res.clusters) == 1
        assert res.clusters[0].merge_reason == MERGE_REASON_SINGLE

    def test_self_loop_excluded(self):
        rows = [
            _row(),
            _row(source_region_name_en="left caudate", target_region_name_en="right caudate",
                 src_canonical_id="3", tgt_canonical_id="3",
                 src_canonical_name="Caudate", tgt_canonical_name="Caudate"),
        ]
        res = build_clusters(rows)
        assert len(res.clusters) == 1
        assert len(res.self_loop_rows) == 1

    def test_unresolved_excluded(self):
        rows = [_row(), _row(g_status="unresolved", unresolved_reason="no_name_match")]
        res = build_clusters(rows)
        assert len(res.clusters) == 1
        assert len(res.unresolved_rows) == 1
        assert res.unresolved_rows[0]["reason"] == "no_name_match"

    def test_conservation(self):
        """证据守恒:clusters + self_loop + unresolved == 输入行数。"""
        rows = [
            _row(), _row(),  # 同 cluster
            _row(source_region_name_en="right hippocampus",
                 target_region_name_en="right prefrontal cortex"),
            _row(g_status="unresolved"),
            _row(source_region_name_en="left caudate", target_region_name_en="right caudate",
                 src_canonical_id="3", tgt_canonical_id="3",
                 src_canonical_name="Caudate", tgt_canonical_name="Caudate"),
        ]
        res = build_clusters(rows)
        total = sum(c.evidence_count for c in res.clusters) + len(res.self_loop_rows) + len(res.unresolved_rows)
        assert total == len(rows)

    def test_connection_type_preserved(self):
        rows = [
            _row(connection_type="functional_connectivity"),
            _row(connection_type="structural_connection"),
        ]
        res = build_clusters(rows)
        types = {c.connection_type for c in res.clusters}
        assert types == {"functional_connectivity", "structural_connection"}

    def test_confidence_distribution(self):
        rows = [_row(confidence=0.3), _row(confidence=0.5)]
        res = build_clusters(rows)
        cd = res.clusters[0].confidence_distribution
        assert cd["count"] == 2
        assert cd["min"] == 0.3 and cd["max"] == 0.5
        assert abs(cd["avg"] - 0.4) < 1e-6
        assert cd["buckets"].get("0.3") == 1 and cd["buckets"].get("0.5") == 1

    def test_provenance_keeps_llm_runs_and_texts(self):
        rows = [_row(llm_run_id="r1", evidence_text="text-a"), _row(llm_run_id="r1", evidence_text="text-b")]
        res = build_clusters(rows)
        pv = res.clusters[0].provenance
        assert pv["llm_run_ids"] == ["r1"]
        assert "text-a" in pv["evidence_texts"] and "text-b" in pv["evidence_texts"]

    def test_stats_counts(self):
        rows = [_row(), _row(), _row(g_status="unresolved")]
        res = build_clusters(rows)
        s = res.stats
        assert s["clusters"] == 1
        assert s["evidence_rows_in_clusters"] == 2
        assert s["unresolved_rows"] == 1
        assert s["total_input_rows"] == 3


class TestNormModality:
    def test_normalization(self):
        assert norm_modality("structural_connection") == "structural"
        assert norm_modality("diffusion_tensor") == "structural"
        assert norm_modality("functional_connection") == "functional"
        assert norm_modality(None) == "other"
