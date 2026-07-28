"""Integration tests using real DB schema with isolated transactions."""
import pytest
from app.services.mirror_circuit_validation_service import (
    get_rule_registry,
    _adjudicate,
    HARD_RULES,
    SOFT_RULES,
)


class TestRuleRegistry:
    def test_exactly_12_rules(self):
        """Verify the rule registry returns exactly 12 rules."""
        rules = get_rule_registry()
        assert len(rules) == 12, f"Expected 12 rules, got {len(rules)}"
        codes = {r["rule_code"] for r in rules}
        assert "PREDICATE_VALIDITY" in codes, (
            f"PREDICATE_VALIDITY missing from registry; codes={codes}"
        )
        assert all(r["enabled"] for r in rules), "All rules must be enabled"
        assert all(r["validator_version"] == "1.0" for r in rules), (
            "All rules must have validator_version='1.0'"
        )

    def test_rule_count_consistency(self):
        """HARD_RULES + SOFT_RULES must sum to 12."""
        assert len(HARD_RULES) + len(SOFT_RULES) == 12, (
            f"HARD({len(HARD_RULES)}) + SOFT({len(SOFT_RULES)}) != 12"
        )

    def test_rule_code_uniqueness(self):
        """No duplicate rule codes."""
        all_rules = HARD_RULES + SOFT_RULES
        codes = [code for code, _desc in all_rules]
        assert len(codes) == len(set(codes)), f"Duplicate rule codes: {codes}"

    def test_blocker_severity_for_hard_rules(self):
        """Hard rules must have blocker default_severity."""
        rules = get_rule_registry()
        hard_codes = {code for code, _desc in HARD_RULES}
        for r in rules:
            if r["rule_code"] in hard_codes:
                assert r["default_severity"] == "blocker", (
                    f"Rule {r['rule_code']} should be blocker severity"
                )

    def test_warning_severity_for_soft_rules(self):
        """Soft rules must have warning default_severity."""
        rules = get_rule_registry()
        soft_codes = {code for code, _desc in SOFT_RULES}
        for r in rules:
            if r["rule_code"] in soft_codes:
                assert r["default_severity"] == "warning", (
                    f"Rule {r['rule_code']} should be warning severity"
                )


class TestAdjudicationExtended:
    """Extended adjudication tests covering all statuses."""

    def test_all_statuses(self):
        """Every adjudication status is reachable."""
        cases = [
            ({"decision": "support", "confidence": 0.8},
             {"decision": "support", "confidence": 0.75},
             "consensus_supported"),
            ({"decision": "support", "confidence": 0.9},
             {"decision": "support", "confidence": 0.5},
             "confidence_divergence"),
            ({"decision": "reject", "confidence": 0.8},
             {"decision": "reject", "confidence": 0.7},
             "consensus_rejected"),
            ({"decision": "support", "confidence": 0.8},
             {"decision": "reject", "confidence": 0.7},
             "model_conflict"),
            ({"decision": "support", "confidence": 0.3},
             {"decision": "support", "confidence": 0.35},
             "low_evidence"),
            ({"decision": "uncertain", "confidence": 0.5},
             {"decision": "support", "confidence": 0.6},
             "insufficient_information"),
        ]
        for a, b, expected in cases:
            result = _adjudicate(a, b)
            assert result["status"] == expected, (
                f"Expected {expected} for a={a}, b={b}, got {result['status']}"
            )

    def test_confidence_diff_calculation(self):
        """Confidence difference is absolute difference."""
        r = _adjudicate(
            {"decision": "support", "confidence": 0.9},
            {"decision": "support", "confidence": 0.6},
        )
        assert r["confidence_diff"] == pytest.approx(0.3)

    def test_priority_urgent_for_model_conflict(self):
        """Model conflict yields urgent priority."""
        r = _adjudicate(
            {"decision": "support", "confidence": 0.8},
            {"decision": "reject", "confidence": 0.7},
        )
        assert r["priority"] == "urgent"

    def test_priority_high_for_low_evidence(self):
        """Low evidence yields high priority."""
        r = _adjudicate(
            {"decision": "support", "confidence": 0.3},
            {"decision": "support", "confidence": 0.35},
        )
        assert r["priority"] == "high"

    def test_priority_normal_for_consensus(self):
        """Consensus yields normal priority."""
        r = _adjudicate(
            {"decision": "support", "confidence": 0.8},
            {"decision": "support", "confidence": 0.75},
        )
        assert r["priority"] == "normal"

    def test_boundary_confidence_threshold(self):
        """Exactly 0.4 confidence borders low evidence."""
        # At 0.4 it's NOT low evidence (if both >= 0.4)
        r = _adjudicate(
            {"decision": "support", "confidence": 0.4},
            {"decision": "support", "confidence": 0.5},
        )
        # Both at or above 0.4, both support, diff < 0.3 -> consensus_supported
        assert r["status"] == "consensus_supported"

        # Just below 0.4 -> low evidence
        r2 = _adjudicate(
            {"decision": "support", "confidence": 0.399},
            {"decision": "support", "confidence": 0.5},
        )
        assert r2["status"] == "low_evidence"
