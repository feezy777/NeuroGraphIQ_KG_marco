"""Tests for circuit validation service adjudication logic."""
import pytest
from app.services.mirror_circuit_validation_service import _adjudicate


class TestAdjudication:
    def test_consensus_supported(self):
        """Both support with close confidence → consensus."""
        r = _adjudicate(
            {"decision": "support", "confidence": 0.8},
            {"decision": "support", "confidence": 0.75},
        )
        assert r["status"] == "consensus_supported"
        assert r["confidence_diff"] == pytest.approx(0.05)
        assert r["priority"] == "normal"

    def test_confidence_divergence(self):
        """Both support but confidence gap large → divergence."""
        r = _adjudicate(
            {"decision": "support", "confidence": 0.9},
            {"decision": "support", "confidence": 0.5},
        )
        assert r["status"] == "confidence_divergence"
        assert r["priority"] == "high"

    def test_consensus_rejected(self):
        """Both reject → consensus rejected."""
        r = _adjudicate(
            {"decision": "reject", "confidence": 0.8},
            {"decision": "reject", "confidence": 0.7},
        )
        assert r["status"] == "consensus_rejected"

    def test_model_conflict(self):
        """One support, one reject → model conflict, urgent priority."""
        r = _adjudicate(
            {"decision": "support", "confidence": 0.8},
            {"decision": "reject", "confidence": 0.7},
        )
        assert r["status"] == "model_conflict"
        assert r["priority"] == "urgent"

    def test_low_evidence(self):
        """Both confidence below 0.4 → low evidence."""
        r = _adjudicate(
            {"decision": "support", "confidence": 0.3},
            {"decision": "support", "confidence": 0.35},
        )
        assert r["status"] == "low_evidence"

    def test_insufficient_information(self):
        """Uncertain + support → insufficient information."""
        r = _adjudicate(
            {"decision": "uncertain", "confidence": 0.5},
            {"decision": "support", "confidence": 0.6},
        )
        assert r["status"] == "insufficient_information"
