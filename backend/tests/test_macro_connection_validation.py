"""Macro Connection Validation V1 — 纯函数测试(无 DB)。"""

import uuid

from app.services.macro_connection_validation_service import (
    FAIL,
    PASS,
    REVIEW_REQUIRED,
    build_validation_context,
    summarize_results,
    validate_connection,
)


def _canonical(**overrides) -> dict:
    c = dict(
        id=str(uuid.uuid4()), source_region_id="r1", target_region_id="r2",
        connection_type="structural", directionality_policy="directed",
        species="human", granularity_level="clinical",
        evidence_count=2, provenance_json={"llm_run_id": "x"},
        confidence_statistics={"count": 2, "min": 0.1, "max": 0.3, "avg": 0.2},
    )
    c.update(overrides)
    return c


# 默认 lineage 使用的固定 mirror ids(_ctx 默认将其视为有效,保持 PASS 用例语义)
DEFAULT_MIRROR_IDS = ["m1", "m2"]


def _ctx(**overrides) -> dict:
    base = dict(
        valid_region_ids={"r1", "r2"},
        lineage_by_canonical={},
        duplicate_keys=set(),
        valid_mirror_ids=set(DEFAULT_MIRROR_IDS),
    )
    base.update(overrides)
    return build_validation_context(
        base["valid_region_ids"], base["lineage_by_canonical"],
        base["duplicate_keys"], base["valid_mirror_ids"],
    )


def _with_lineage(cid: str, cluster_size: int = 2, mirror_ids=None) -> list[dict]:
    return [{"cluster_size": cluster_size,
             "mirror_connection_ids": mirror_ids or DEFAULT_MIRROR_IDS[:cluster_size]}]


class TestPass:
    def test_all_rules_pass(self):
        c = _canonical()
        ctx = _ctx(lineage_by_canonical={c["id"]: _with_lineage(c["id"])})
        status, failed = validate_connection(c, ctx)
        assert status == PASS
        assert failed == []

    def test_duplicate_key_passes_without_duplicate(self):
        c = _canonical()
        ctx = _ctx(lineage_by_canonical={c["id"]: _with_lineage(c["id"])})
        status, failed = validate_connection(c, ctx)
        assert status == PASS


class TestStructuralRules:
    def test_missing_source_region_fail(self):
        c = _canonical(source_region_id="ghost")
        ctx = _ctx(lineage_by_canonical={c["id"]: _with_lineage(c["id"])})
        status, failed = validate_connection(c, ctx)
        assert status == FAIL
        codes = [f["rule_code"] for f in failed]
        assert "src_region_exists" in codes

    def test_missing_target_region_fail(self):
        c = _canonical(target_region_id="ghost")
        ctx = _ctx(lineage_by_canonical={c["id"]: _with_lineage(c["id"])})
        status, failed = validate_connection(c, ctx)
        assert status == FAIL
        assert "tgt_region_exists" in [f["rule_code"] for f in failed]

    def test_self_loop_fail(self):
        c = _canonical(source_region_id="r1", target_region_id="r1")
        ctx = _ctx(lineage_by_canonical={c["id"]: _with_lineage(c["id"])})
        status, failed = validate_connection(c, ctx)
        assert status == FAIL
        assert "src_ne_tgt" in [f["rule_code"] for f in failed]

    def test_invalid_type_fail(self):
        c = _canonical(connection_type="nonsense")
        ctx = _ctx(lineage_by_canonical={c["id"]: _with_lineage(c["id"])})
        status, failed = validate_connection(c, ctx)
        assert status == FAIL
        assert "connection_type_valid" in [f["rule_code"] for f in failed]

    def test_invalid_direction_fail(self):
        c = _canonical(directionality_policy="unknown")
        ctx = _ctx(lineage_by_canonical={c["id"]: _with_lineage(c["id"])})
        status, failed = validate_connection(c, ctx)
        assert status == FAIL
        assert "direction_valid" in [f["rule_code"] for f in failed]

    def test_non_human_species_fail(self):
        c = _canonical(species="mouse")
        ctx = _ctx(lineage_by_canonical={c["id"]: _with_lineage(c["id"])})
        status, failed = validate_connection(c, ctx)
        assert status == FAIL
        assert "species_human" in [f["rule_code"] for f in failed]

    def test_invalid_granularity_fail(self):
        c = _canonical(granularity_level="fine")
        ctx = _ctx(lineage_by_canonical={c["id"]: _with_lineage(c["id"])})
        status, failed = validate_connection(c, ctx)
        assert status == FAIL
        assert "granularity_macro" in [f["rule_code"] for f in failed]

    def test_macro_granularity_ok(self):
        c = _canonical(granularity_level="macro")
        ctx = _ctx(lineage_by_canonical={c["id"]: _with_lineage(c["id"])})
        status, failed = validate_connection(c, ctx)
        assert status == PASS


class TestEvidenceRules:
    def test_no_lineage_review(self):
        c = _canonical()
        status, failed = validate_connection(c, _ctx())
        assert status == REVIEW_REQUIRED
        codes = [f["rule_code"] for f in failed]
        assert "lineage_exists" in codes

    def test_evidence_count_mismatch_review(self):
        c = _canonical(evidence_count=5)  # lineage sum = 2
        ctx = _ctx(lineage_by_canonical={c["id"]: _with_lineage(c["id"])})
        status, failed = validate_connection(c, ctx)
        assert status == REVIEW_REQUIRED
        assert "evidence_count_correct" in [f["rule_code"] for f in failed]

    def test_empty_provenance_review(self):
        c = _canonical(provenance_json={})
        ctx = _ctx(lineage_by_canonical={c["id"]: _with_lineage(c["id"])})
        status, failed = validate_connection(c, ctx)
        assert status == REVIEW_REQUIRED
        assert "provenance_json_nonempty" in [f["rule_code"] for f in failed]

    def test_missing_confidence_review(self):
        c = _canonical(confidence_statistics={"count": 0})
        ctx = _ctx(lineage_by_canonical={c["id"]: _with_lineage(c["id"])})
        status, failed = validate_connection(c, ctx)
        assert status == REVIEW_REQUIRED
        assert "confidence_exists" in [f["rule_code"] for f in failed]

    def test_no_evidence_no_lineage_review(self):
        c = _canonical(evidence_count=0, confidence_statistics={}, provenance_json={})
        status, failed = validate_connection(c, _ctx())
        assert status == REVIEW_REQUIRED
        codes = [f["rule_code"] for f in failed]
        assert "lineage_exists" in codes and "confidence_exists" in codes


class TestQualityRules:
    def test_duplicate_key_fail(self):
        c = _canonical()
        dup = {(c["source_region_id"], c["target_region_id"], c["connection_type"])}
        ctx = _ctx(duplicate_keys=dup,
                   lineage_by_canonical={c["id"]: _with_lineage(c["id"])})
        status, failed = validate_connection(c, ctx)
        assert status == FAIL
        assert "no_duplicate_key" in [f["rule_code"] for f in failed]

    def test_unresolved_mirror_review(self):
        c = _canonical()
        ctx = _ctx(lineage_by_canonical={c["id"]: _with_lineage(
            c["id"], mirror_ids=["ghost-mirror"])},
            valid_mirror_ids={"real-mirror"})
        status, failed = validate_connection(c, ctx)
        assert status == REVIEW_REQUIRED
        assert "traceable_to_mirror" in [f["rule_code"] for f in failed]

    def test_traceable_passes(self):
        mid = str(uuid.uuid4())
        c = _canonical()
        ctx = _ctx(valid_mirror_ids={mid},
                   lineage_by_canonical={c["id"]: _with_lineage(c["id"], mirror_ids=[mid])})
        status, failed = validate_connection(c, ctx)
        assert status == PASS


class TestSummarize:
    def test_counts_and_rule_breakdown(self):
        results = [
            {"validation_status": PASS, "failed_rules": []},
            {"validation_status": FAIL, "failed_rules": [{"rule_code": "src_ne_tgt"}]},
            {"validation_status": REVIEW_REQUIRED,
             "failed_rules": [{"rule_code": "lineage_exists"},
                              {"rule_code": "provenance_json_nonempty"}]},
        ]
        s = summarize_results(results)
        assert s["total"] == 3
        assert s["pass"] == 1 and s["fail"] == 1 and s["review_required"] == 1
        assert s["pass_pct"] == round(1 / 3 * 100, 2)
        assert s["failed_rule_counts"]["lineage_exists"] == 1
        assert s["failed_rule_counts"]["src_ne_tgt"] == 1

    def test_empty(self):
        s = summarize_results([])
        assert s["total"] == 0 and s["pass"] == 0 and s["pass_pct"] == 0.0
