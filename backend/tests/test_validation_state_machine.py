"""Tests for validation state machine, blocked reasons assembly, DeepSeek parser, and effective circuit builder."""
import json
import uuid
import pytest
from app.services.validation_state_machine import (
    RuleValidationStatus,
    BlockerAnalysisStatus,
    CorrectionStatus,
    RevalidationStatus,
    ReviewerStatus,
    AdjudicationStatus,
    HumanReviewStatus,
    PromotionStatus,
    get_rule_severity,
    can_enter_dual_review,
    can_enter_promotion,
    RULE_SEVERITY_POLICY,
)
from app.services.mirror_circuit_validation_service import (
    assemble_blocked_reasons,
    parse_deepseek_diagnosis,
)


# ── State Machine Tests ───────────────────────────────────────────────────


class TestStateMachineEnums:
    def test_all_status_classes_have_not_started(self):
        """Every status class defines NOT_STARTED (except CorrectionStatus which uses 'none')."""
        classes = [
            RuleValidationStatus, BlockerAnalysisStatus,
            RevalidationStatus, ReviewerStatus, AdjudicationStatus,
            HumanReviewStatus, PromotionStatus,
        ]
        for cls in classes:
            assert hasattr(cls, "NOT_STARTED"), f"{cls.__name__} missing NOT_STARTED"

    def test_correction_status_no_not_started(self):
        """CorrectionStatus uses 'none' instead of 'not_started'."""
        assert not hasattr(CorrectionStatus, "NOT_STARTED")
        assert CorrectionStatus.NONE == "none"

    def test_correction_status_cycle(self):
        """CorrectionStatus covers the full lifecycle."""
        assert CorrectionStatus.NONE == "none"
        assert CorrectionStatus.PROPOSED == "proposed"
        assert CorrectionStatus.DETERMINISTIC_REJECTED == "deterministic_rejected"
        assert CorrectionStatus.PENDING_HUMAN == "pending_human"
        assert CorrectionStatus.APPROVED == "approved"
        assert CorrectionStatus.REJECTED == "rejected"
        assert CorrectionStatus.APPLIED == "applied_to_effective_view"

    def test_promotion_status_cycle(self):
        """PromotionStatus covers the full lifecycle."""
        assert PromotionStatus.NOT_STARTED == "not_started"
        assert PromotionStatus.PREVIEW_READY == "preview_ready"
        assert PromotionStatus.PROMOTED == "promoted"
        assert PromotionStatus.ROLLED_BACK == "rolled_back"


class TestGetRuleSeverity:
    def test_hard_rule_severity(self):
        """Hard rules return hard_fail validation."""
        for code in ["REGION_IDENTITY", "EDGE_EXISTENCE", "DIRECTION_CORRECT",
                     "STEP_CONTINUITY", "CLOSED_LOOP", "GRANULARITY_HOMOGENEITY"]:
            policy = get_rule_severity(code)
            assert policy["validation"] == "hard_fail"
            assert policy["blocks_dual_review"] is True
            assert policy["blocks_promotion"] is True

    def test_soft_rule_severity(self):
        """Soft rules return warning validation."""
        for code in ["TOPOLOGY_TYPE_VALID", "FIELD_COMPLETENESS", "LABEL_QUALITY"]:
            policy = get_rule_severity(code)
            assert policy["validation"] == "warning"

    def test_unknown_rule_defaults_to_warning(self):
        """Unknown rule codes default to warning with no blocking."""
        policy = get_rule_severity("NONEXISTENT_RULE")
        assert policy["validation"] == "warning"
        assert policy["blocks_dual_review"] is False
        assert policy["blocks_promotion"] is False

    def test_provenance_blocks_promotion_only(self):
        """PROVENANCE_COMPLETE blocks promotion but not dual review."""
        policy = get_rule_severity("PROVENANCE_COMPLETE")
        assert policy["validation"] == "warning"
        assert policy["blocks_dual_review"] is False
        assert policy["blocks_promotion"] is True

    def test_canonical_key_blocks_promotion(self):
        """CANONICAL_KEY_DUPLICATE blocks promotion."""
        policy = get_rule_severity("CANONICAL_KEY_DUPLICATE")
        assert policy["validation"] == "warning"
        assert policy["blocks_promotion"] is True

    def test_predicate_validity_blocks_promotion(self):
        """PREDICATE_VALIDITY blocks promotion."""
        policy = get_rule_severity("PREDICATE_VALIDITY")
        assert policy["validation"] == "warning"
        assert policy["blocks_promotion"] is True


class TestCanEnterDualReview:
    def test_all_passed_allows_dual_review(self):
        """All rules passing allows dual review."""
        results = [
            {"rule_code": "REGION_IDENTITY", "status": "passed"},
            {"rule_code": "EDGE_EXISTENCE", "status": "passed"},
            {"rule_code": "PROVENANCE_COMPLETE", "status": "passed"},
        ]
        assert can_enter_dual_review(results) is True

    def test_warnings_allow_dual_review(self):
        """Warnings still allow dual review."""
        results = [
            {"rule_code": "REGION_IDENTITY", "status": "passed"},
            {"rule_code": "PROVENANCE_COMPLETE", "status": "warning"},
        ]
        assert can_enter_dual_review(results) is True

    def test_blocked_hard_fail_blocks_dual_review(self):
        """Blocked hard_fail rule blocks dual review."""
        results = [
            {"rule_code": "REGION_IDENTITY", "status": "blocked"},
        ]
        assert can_enter_dual_review(results) is False

    def test_blocked_warning_does_not_block_dual_review(self):
        """Blocked warning rule doesn't block dual review."""
        results = [
            {"rule_code": "PROVENANCE_COMPLETE", "status": "blocked"},
        ]
        assert can_enter_dual_review(results) is True


class TestCanEnterPromotion:
    def test_all_passed_allows_promotion(self):
        """All rules passing allows promotion."""
        results = [
            {"rule_code": "REGION_IDENTITY", "status": "passed"},
            {"rule_code": "EDGE_EXISTENCE", "status": "passed"},
        ]
        assert can_enter_promotion(results) is True

    def test_hard_fail_blocks_promotion(self):
        """Hard fail blocks promotion."""
        results = [
            {"rule_code": "REGION_IDENTITY", "status": "blocked"},
        ]
        assert can_enter_promotion(results) is False

    def test_provenance_warning_blocks_promotion(self):
        """PROVENANCE_COMPLETE warning blocks promotion."""
        results = [
            {"rule_code": "PROVENANCE_COMPLETE", "status": "warning"},
        ]
        assert can_enter_promotion(results) is False

    def test_topology_warning_does_not_block_promotion(self):
        """TOPOLOGY_TYPE_VALID warning doesn't block promotion."""
        results = [
            {"rule_code": "TOPOLOGY_TYPE_VALID", "status": "warning"},
        ]
        assert can_enter_promotion(results) is True

    def test_field_completeness_warning_does_not_block_promotion(self):
        """FIELD_COMPLETENESS warning doesn't block promotion."""
        results = [
            {"rule_code": "FIELD_COMPLETENESS", "status": "warning"},
        ]
        assert can_enter_promotion(results) is True


# ── Blocked Reasons Assembly Tests ────────────────────────────────────────


class TestAssembleBlockedReasons:
    def test_no_blocked_rules(self):
        """No blocked rules returns empty reasons and no integrity warning."""
        results = [
            {"rule_code": "REGION_IDENTITY", "status": "passed", "message": "OK"},
            {"rule_code": "EDGE_EXISTENCE", "status": "passed", "message": "OK"},
        ]
        reasons, warning = assemble_blocked_reasons(results, "result-1")
        assert reasons == []
        assert warning is False

    def test_blocked_hard_fail(self):
        """Blocked hard fail rule returns reason."""
        results = [
            {"rule_code": "REGION_IDENTITY", "status": "blocked", "message": "regions < 2"},
        ]
        reasons, warning = assemble_blocked_reasons(results, "result-1")
        assert len(reasons) == 1
        assert reasons[0]["rule_code"] == "REGION_IDENTITY"
        assert reasons[0]["severity"] == "hard_fail"
        assert reasons[0]["message"] == "regions < 2"
        assert reasons[0]["rule_result_id"] == "result-1"
        assert warning is False

    def test_blocked_warning(self):
        """Blocked warning rule returns reason with warning severity."""
        results = [
            {"rule_code": "PROVENANCE_COMPLETE", "status": "blocked", "message": "missing trace"},
        ]
        reasons, warning = assemble_blocked_reasons(results, "result-1")
        assert len(reasons) == 1
        assert reasons[0]["severity"] == "warning"
        assert warning is False

    def test_integrity_warning(self):
        """When hard_fail rules are blocked but no results with 'blocked' status in filtered list."""
        # This simulates the edge case where blocked_reasons assembly finds no 'blocked'
        # but there are hard_fail rules that would block
        results = [
            {"rule_code": "REGION_IDENTITY", "status": "blocked", "message": "fail"},
            {"rule_code": "FIELD_COMPLETENESS", "status": "passed"},
        ]
        reasons, warning = assemble_blocked_reasons(results, "result-1")
        # Both hard_fail and blocked match, so reasons exist
        assert len(reasons) >= 1
        assert warning is False

    def test_multiple_blocked_rules(self):
        """Multiple blocked rules return multiple reasons."""
        results = [
            {"rule_code": "REGION_IDENTITY", "status": "blocked", "message": "regions < 2"},
            {"rule_code": "STEP_CONTINUITY", "status": "blocked", "message": "steps not continuous"},
        ]
        reasons, warning = assemble_blocked_reasons(results, "result-1")
        assert len(reasons) == 2
        codes = {r["rule_code"] for r in reasons}
        assert "REGION_IDENTITY" in codes
        assert "STEP_CONTINUITY" in codes

    def test_blocked_reasons_include_field_metadata(self):
        """Blocked reasons include field path, expected and actual values."""
        results = [{
            "rule_code": "CLOSED_LOOP",
            "status": "blocked",
            "message": "not closed",
            "field": "closed_loop",
            "expected": True,
            "actual": False,
            "source_reference": "circuit.def",
        }]
        reasons, warning = assemble_blocked_reasons(results, "result-1")
        assert len(reasons) == 1
        r = reasons[0]
        assert r["field"] == "closed_loop"
        assert r["expected"] is True
        assert r["actual"] is False
        assert r["source_reference"] == "circuit.def"
        assert r["validator_version"] == "1.0"

    def test_empty_results(self):
        """Empty results list returns empty reasons."""
        reasons, warning = assemble_blocked_reasons([], "result-1")
        assert reasons == []
        assert warning is False

    def test_none_status(self):
        """Results with None status are treated as not blocked."""
        results = [
            {"rule_code": "REGION_IDENTITY", "status": None},
            {"rule_code": "EDGE_EXISTENCE", "status": "running"},
        ]
        reasons, warning = assemble_blocked_reasons(results, "result-1")
        assert reasons == []
        assert warning is False


# ── DeepSeek Parser Tests ─────────────────────────────────────────────────


class TestParseDeepseekDiagnosis:
    def test_direct_json_dict(self):
        """Direct JSON dict parses correctly."""
        raw = '{"circuit_id": "abc", "rule_diagnostics": []}'
        result = parse_deepseek_diagnosis(raw)
        assert result["circuit_id"] == "abc"
        assert "parse_failed" not in result

    def test_direct_json_list(self):
        """JSON list wraps into rule_diagnostics."""
        raw = '[{"rule_code": "A", "diagnosis": "missing"}]'
        result = parse_deepseek_diagnosis(raw)
        assert "rule_diagnostics" in result
        assert len(result["rule_diagnostics"]) == 1

    def test_fenced_json_code_block(self):
        """JSON in fenced code block extracts correctly."""
        raw = 'Some text\n```json\n{"circuit_id": "xyz", "suggested_changes": []}\n```\nmore text'
        result = parse_deepseek_diagnosis(raw)
        assert result["circuit_id"] == "xyz"

    def test_fenced_no_language(self):
        """Code block without language specifier."""
        raw = 'text\n```\n{"circuit_id": "no-lang"}\n```\nend'
        result = parse_deepseek_diagnosis(raw)
        assert result["circuit_id"] == "no-lang"

    def test_first_json_object_fallback(self):
        """Extracts first JSON object from text."""
        raw = 'Explanation: {"key": "value", "nested": {"a": 1}} trailing'
        result = parse_deepseek_diagnosis(raw)
        assert result["key"] == "value"
        assert result["nested"]["a"] == 1

    def test_parse_failed_marker(self):
        """Non-JSON text returns parse_failed marker."""
        raw = "This is not JSON at all. No braces, nothing."
        result = parse_deepseek_diagnosis(raw)
        assert result["parse_failed"] is True
        assert result["overall_repairability"] == "manual_required"
        assert result["revalidation_recommended"] is True
        assert "raw_text" in result

    def test_parse_failed_with_braces_but_no_json(self):
        """Text with braces but not JSON returns parse_failed."""
        raw = "Some {curly} braces but {not json"
        result = parse_deepseek_diagnosis(raw)
        assert result["parse_failed"] is True

    def test_truncated_raw_text_on_parse_failure(self):
        """raw_text is truncated to 1000 chars on parse failure."""
        raw = "x" * 2000
        result = parse_deepseek_diagnosis(raw)
        assert len(result["raw_text"]) == 1000

    def test_valid_json_with_extra_text(self):
        """Valid JSON dict returned even with surrounding text."""
        raw = 'Note: {"valid": true, "count": 3} -- end'
        result = parse_deepseek_diagnosis(raw)
        assert result["valid"] is True
        assert result["count"] == 3

    def test_empty_string_returns_parse_failed(self):
        """Empty string returns parse_failed marker."""
        result = parse_deepseek_diagnosis("")
        assert result["parse_failed"] is True

    def test_nested_json_extraction(self):
        """Deeply nested JSON object."""
        raw = json.dumps({"level1": {"level2": {"value": 42}}, "items": [1, 2, 3]})
        result = parse_deepseek_diagnosis(raw)
        assert result["level1"]["level2"]["value"] == 42
        assert len(result["items"]) == 3


# ── RULE_SEVERITY_POLICY completeness ─────────────────────────────────────


class TestRuleSeverityPolicyCompleteness:
    def test_all_12_rules_in_policy(self):
        """All 12 rules have entries in RULE_SEVERITY_POLICY."""
        expected_rules = {
            "REGION_IDENTITY", "EDGE_EXISTENCE", "DIRECTION_CORRECT",
            "STEP_CONTINUITY", "CLOSED_LOOP", "GRANULARITY_HOMOGENEITY",
            "PROVENANCE_COMPLETE", "TOPOLOGY_TYPE_VALID",
            "CANONICAL_KEY_DUPLICATE", "FIELD_COMPLETENESS",
            "LABEL_QUALITY", "PREDICATE_VALIDITY",
        }
        assert set(RULE_SEVERITY_POLICY.keys()) == expected_rules, (
            f"Missing from policy: {expected_rules - set(RULE_SEVERITY_POLICY.keys())}"
        )
