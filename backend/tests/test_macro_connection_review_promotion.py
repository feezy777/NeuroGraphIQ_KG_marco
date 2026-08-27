"""Macro Connection Human Review + Promotion — 纯函数测试(无 DB)。

覆盖任务要求:
* REVIEW_REQUIRED 不能直接 promotion(未审 / rejected / needs_more_evidence)
* PASS 可以 promotion
* 未验证(validation status 缺失)即使 review approved 也禁止进入 Final
* Final 行保留 lineage 可追溯(canonical_connection_id)+ evidence / provenance 保持
* promotion 幂等语义(final 行唯一锚,重复 promotion → skipped_duplicate 判定)
"""

import uuid

from app.services.macro_connection_review_promotion_service import (
    build_review_queue,
    check_promotion_eligibility,
    final_connection_from_canonical,
    latest_review_decision,
    summarize_final,
    summarize_promotion,
)


def _review(action: str, created_at: str = "2026-08-24T10:00:00+00:00") -> dict:
    return {"id": str(uuid.uuid4()), "canonical_connection_id": str(uuid.uuid4()),
            "action": action, "reviewer": "tester", "created_at": created_at}


def _canonical(**overrides) -> dict:
    c = dict(
        id=str(uuid.uuid4()), connection_code="ng:cn:test",
        source_region_id="r1", target_region_id="r2",
        connection_type="structural", directionality_policy="directed",
        species="human", granularity_level="clinical", confidence=0.5,
        evidence_summary={"evidence_count": 2, "sources": [{"source_id": "s1"}]},
        provenance_json={"llm_run_id": "run-1"},
        assertion_type="reported_fact", source_type="llm_extraction",
        generation_method="cn1_connection_grounding_v1",
        evidence_reference=[{"type": "mirror_connection_id", "id": "m1"}],
    )
    c.update(overrides)
    return c


class TestEligibilityGuard:
    """Promotion 资格守卫:REVIEW 不能直接 promotion。"""

    def test_review_required_no_review_ineligible(self):
        eligible, reason = check_promotion_eligibility("REVIEW_REQUIRED", None)
        assert not eligible
        assert reason == "review_pending"

    def test_review_required_rejected_ineligible(self):
        eligible, reason = check_promotion_eligibility(
            "REVIEW_REQUIRED", _review("rejected"))
        assert not eligible
        assert reason == "review_rejected"

    def test_review_required_needs_more_evidence_ineligible(self):
        eligible, reason = check_promotion_eligibility(
            "REVIEW_REQUIRED", _review("needs_more_evidence"))
        assert not eligible
        assert reason == "needs_more_evidence"

    def test_review_required_approved_eligible(self):
        eligible, reason = check_promotion_eligibility(
            "REVIEW_REQUIRED", _review("approved"))
        assert eligible
        assert reason == "review_approved"

    def test_pass_eligible(self):
        eligible, reason = check_promotion_eligibility("PASS", None)
        assert eligible
        assert reason == "validation_pass"

    def test_fail_ineligible(self):
        eligible, reason = check_promotion_eligibility("FAIL", _review("approved"))
        assert not eligible
        assert reason == "validation_fail"

    def test_unvalidated_ineligible_even_with_approved_review(self):
        """未验证 connection 禁止进入 Final(任务要求)。"""
        eligible, reason = check_promotion_eligibility(None, _review("approved"))
        assert not eligible
        assert reason == "validation_missing"


class TestLatestReview:
    def test_latest_wins(self):
        reviews = [_review("needs_more_evidence", "2026-08-24T09:00:00+00:00"),
                   _review("approved", "2026-08-24T11:00:00+00:00")]
        for r in reviews:
            r["canonical_connection_id"] = "cc-1"
        latest = latest_review_decision(reviews, "cc-1")
        assert latest["action"] == "approved"

    def test_no_review_returns_none(self):
        assert latest_review_decision([], "cc-1") is None


class TestFinalRow:
    def test_evidence_and_provenance_preserved(self):
        c = _canonical()
        f = final_connection_from_canonical(c, "val-run-1", "rev-1")
        assert f["canonical_connection_id"] == c["id"]
        assert f["evidence_summary"] == c["evidence_summary"]      # evidence 保持
        assert f["provenance_json"] == c["provenance_json"]        # provenance 保持
        assert f["evidence_reference"] == c["evidence_reference"]  # evidence_reference 保持
        assert f["validation_run_id"] == "val-run-1"               # 溯源
        assert f["review_record_id"] == "rev-1"
        assert f["final_status"] == "active"
        assert f["generation_method"] == "cn1_connection_grounding_v1"

    def test_final_row_is_deterministic(self):
        """同一 canonical 两次构造 → 完全一致(幂等基础)。"""
        c = _canonical()
        a = final_connection_from_canonical(c, "val-run-1", None)
        b = final_connection_from_canonical(c, "val-run-1", None)
        assert a == b


class TestSummarizePromotion:
    def test_counts(self):
        records = [
            {"status": "promoted", "promotion_reason": "validation_pass"},
            {"status": "promoted", "promotion_reason": "validation_pass"},
            {"status": "skipped_duplicate", "promotion_reason": "already_in_final"},
            {"status": "skipped_ineligible", "promotion_reason": "review_pending"},
        ]
        s = summarize_promotion(records)
        assert s["total"] == 4
        assert s["promoted"] == 2
        assert s["skipped_duplicate"] == 1
        assert s["skipped_ineligible"] == 1
        assert s["by_reason"]["validation_pass"] == 2


class TestReviewQueue:
    def test_build_queue_with_region_names(self):
        cid = str(uuid.uuid4())
        items = [{
            "canonical_connection_id": cid, "connection_code": "ng:cn:x",
            "source_region_id": "r1", "target_region_id": "r2",
            "connection_type": "projection", "directionality_policy": "directed",
            "evidence_count": 1, "evidence_summary": {}, "provenance_json": {},
            "confidence_statistics": {"count": 1},
            "validation_status": "REVIEW_REQUIRED", "validation_run_id": "vr",
            "failed_rules": [{"rule_code": "provenance_json_nonempty",
                              "category": "evidence", "message": "empty"}],
        }]
        queue = build_review_queue(items, {
            "r1": {"canonical_name_en": "Hippocampus", "canonical_name_cn": "海马"},
            "r2": {"canonical_name_en": "Brain Stem", "canonical_name_cn": "脑干"},
        })
        assert len(queue) == 1
        q = queue[0]
        assert q["source_region"]["name_en"] == "Hippocampus"
        assert q["target_region"]["name_en"] == "Brain Stem"
        assert q["evidence_count"] == 1
        assert q["failed_rules"][0]["rule_code"] == "provenance_json_nonempty"
        assert q["validation_run_id"] == "vr"

    def test_queue_sorts_failed_first(self):
        items = [
            {"canonical_connection_id": str(uuid.uuid4()), "connection_code": "a",
             "source_region_id": "r1", "target_region_id": "r2",
             "connection_type": "t", "directionality_policy": "d",
             "evidence_count": 5, "evidence_summary": {}, "provenance_json": {},
             "confidence_statistics": {}, "validation_status": "REVIEW_REQUIRED",
             "validation_run_id": "vr", "failed_rules": []},
            {"canonical_connection_id": str(uuid.uuid4()), "connection_code": "b",
             "source_region_id": "r1", "target_region_id": "r2",
             "connection_type": "t", "directionality_policy": "d",
             "evidence_count": 2, "evidence_summary": {}, "provenance_json": {},
             "confidence_statistics": {}, "validation_status": "REVIEW_REQUIRED",
             "validation_run_id": "vr", "failed_rules": [{"rule_code": "x"}]},
        ]
        queue = build_review_queue(items, {})
        assert queue[0]["connection_code"] == "b"  # 有 failed rules 的在前


class TestSummarizeFinal:
    def test_evidence_coverage(self):
        finals = [
            {"final_status": "active", "granularity_level": "clinical",
             "connection_type": "structural",
             "evidence_summary": {"evidence_count": 2},
             "evidence_reference": []},
            {"final_status": "active", "granularity_level": "clinical",
             "connection_type": "projection",
             "evidence_summary": {}, "evidence_reference": [{"id": "m1"}]},
        ]
        s = summarize_final(finals, total_connections=2500)
        assert s["active"] == 2
        assert s["with_evidence"] == 2
        assert s["evidence_coverage"] == 100.0
        assert s["coverage_pct"] == round(2 / 2500 * 100, 2)
