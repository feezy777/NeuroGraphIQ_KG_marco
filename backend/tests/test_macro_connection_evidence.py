"""Macro Connection Evidence Enrichment — 纯函数测试(无 DB)。"""

import uuid

from app.services.macro_connection_evidence_service import (
    build_sources,
    build_standard_evidence_summary,
    build_supporting_records,
    compute_evidence_quality,
    connection_to_summary,
    detail_from_row,
    match_region,
)


def _mirror(**overrides) -> dict:
    m = dict(
        id=str(uuid.uuid4()), llm_run_id="run1", confidence=0.5,
        evidence_text="evidence text " * 30,  # 超过截断长度
        directionality="directed", modality="diffusion_tensor",
        source_atlas="Macro96", cluster_id=100,
    )
    m.update(overrides)
    return m


class TestBuildSources:
    def test_groups_by_run_and_atlas(self):
        rows = [_mirror(), _mirror(confidence=0.3), _mirror(llm_run_id="run2")]
        sources = build_sources(rows)
        assert len(sources) == 2
        by_id = {s["source_id"]: s for s in sources}
        assert by_id["run1"]["record_count"] == 2
        assert by_id["run1"]["source_type"] == "llm_extraction"
        assert by_id["run1"]["source_atlas"] == "Macro96"
        assert by_id["run2"]["record_count"] == 1

    def test_confidence_stats_per_source(self):
        sources = build_sources([_mirror(confidence=0.4), _mirror(confidence=0.6)])
        s = sources[0]
        assert s["confidence_min"] == 0.4
        assert s["confidence_max"] == 0.6
        assert s["confidence_mean"] == 0.5

    def test_no_confidence(self):
        sources = build_sources([_mirror(confidence=None)])
        assert sources[0]["confidence_min"] is None

    def test_sorted_by_record_count_desc(self):
        rows = [_mirror(), _mirror(), _mirror(), _mirror(llm_run_id="run2")]
        sources = build_sources(rows)
        assert sources[0]["record_count"] >= sources[1]["record_count"]


class TestBuildSupportingRecords:
    def test_keeps_traceability_keys(self):
        recs = build_supporting_records([_mirror()], cluster_id=100)
        r = recs[0]
        assert r["mirror_connection_id"]
        assert r["cluster_id"] == 100
        assert r["directionality"] == "directed"
        assert r["llm_run_id"] == "run1"

    def test_evidence_text_truncated(self):
        recs = build_supporting_records([_mirror()])
        assert len(recs[0]["evidence_text"]) == 200

    def test_uses_row_cluster_id_when_given(self):
        recs = build_supporting_records([_mirror(cluster_id=5)], cluster_id=100)
        assert recs[0]["cluster_id"] == 5


class TestBuildStandardEvidenceSummary:
    def test_structure_complete(self):
        rows = [_mirror(), _mirror(llm_run_id="run2", cluster_id=101)]
        summary = build_standard_evidence_summary("c1", [100, 101], rows,
                                                 {"merge_reasons": {"single_evidence": 2}})
        assert summary["canonical_connection_id"] == "c1"
        assert summary["evidence_count"] == 2
        assert summary["cluster_count"] == 2
        assert summary["cluster_ids"] == [100, 101]
        assert summary["confidence_min"] == 0.5 and summary["confidence_max"] == 0.5
        assert summary["confidence_mean"] == 0.5
        assert len(summary["sources"]) == 2
        assert len(summary["supporting_records"]) == 2
        assert summary["merge_reasons"] == {"single_evidence": 2}
        assert summary["llm_run_ids"] == ["run1", "run2"]
        assert len(summary["evidence_texts"]) == 2

    def test_no_evidence(self):
        summary = build_standard_evidence_summary("c1", [], [])
        assert summary["evidence_count"] == 0
        assert summary["confidence_min"] is None
        assert summary["sources"] == []
        assert summary["supporting_records"] == []


class TestComputeEvidenceQuality:
    def test_no_evidence_low(self):
        label, factors = compute_evidence_quality(0, [])
        assert label == "low"
        assert factors["no_evidence"] is True
        assert factors["score"] == 0.0

    def test_single_evidence_low(self):
        label, factors = compute_evidence_quality(1, [_mirror()])
        assert label == "low"
        assert factors["s_evidence"] == 0.1

    def test_multi_evidence_multi_run_high(self):
        rows = [_mirror(confidence=0.4), _mirror(confidence=0.5),
                _mirror(llm_run_id="run2", confidence=0.5),
                _mirror(llm_run_id="run3", confidence=0.4),
                _mirror(llm_run_id="run3", confidence=0.4),
                _mirror(llm_run_id="run3", confidence=0.4)]
        label, factors = compute_evidence_quality(6, rows)
        assert label == "high"
        assert factors["distinct_llm_run_ids"] == 3

    def test_low_consistency_downgrades(self):
        rows = [_mirror(confidence=0.1), _mirror(confidence=0.9),
                _mirror(confidence=0.1), _mirror(confidence=0.9)]
        label, factors = compute_evidence_quality(4, rows)
        assert factors["s_consistency"] == 0.3

    def test_no_confidence_neutral(self):
        rows = [_mirror(confidence=None), _mirror(confidence=None)]
        label, factors = compute_evidence_quality(2, rows)
        assert label == "low"  # 无 confidence + 2 evidence + 1 run 不足以 medium

    def test_medium_band(self):
        rows = [_mirror(confidence=0.3), _mirror(confidence=0.4), _mirror(confidence=0.4)]
        label, factors = compute_evidence_quality(3, rows)
        assert label == "medium"


class TestMatchRegion:
    def test_substring_case_insensitive(self):
        assert match_region("hippocampus", "Left Hippocampus")
        assert match_region("Hippocampus", "hippocampus")
        assert not match_region("amygdala", "Hippocampus")

    def test_empty_filter_matches_all(self):
        assert match_region("", "anything")
        assert match_region("  ", None)


class TestRowMappers:
    class _Row:
        def __init__(self, **kw):
            self.__dict__.update(kw)

    def test_detail_from_row(self):
        r = self._Row(
            id=uuid.UUID("12345678-1234-5678-1234-567812345678"),
            connection_code="ng:cn:x", connection_type="structural",
            directionality_policy="directed", evidence_count=2,
            confidence_statistics={"min": 0.1, "max": 0.3, "avg": 0.2},
            evidence_summary={"supporting_records": [{"x": 1}], "confidence_min": 0.1,
                              "confidence_max": 0.3, "confidence_mean": 0.2},
            evidence_quality_score="medium", evidence_quality_factors={"score": 0.5},
            source_region_name="A", target_region_name="B",
        )
        d = detail_from_row(r)
        assert d["source_region"] == "A" and d["target_region"] == "B"
        assert d["connection_type"] == "structural"
        assert len(d["supporting_records"]) == 1
        assert d["confidence"] == {"min": 0.1, "max": 0.3, "mean": 0.2}
        assert d["evidence_quality_score"] == "medium"

    def test_connection_to_summary(self):
        r = self._Row(
            id=uuid.UUID("12345678-1234-5678-1234-567812345678"),
            connection_code="ng:cn:x", connection_type="structural",
            directionality_policy="directed", evidence_count=2,
            confidence_statistics={"min": 0.1, "max": 0.3, "avg": 0.2},
            source_region_name="A", target_region_name="B",
            evidence_quality_score="low",
        )
        s = connection_to_summary(r)
        assert s["evidence_count"] == 2
        assert s["confidence"]["mean"] == 0.2
        assert s["evidence_quality_score"] == "low"
