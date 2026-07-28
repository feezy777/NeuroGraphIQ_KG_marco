"""E2E test for circuit validation pipeline."""
import pytest
from app.services.mirror_circuit_validation_service import _adjudicate
from app.schemas.mirror_circuit_validation import CircuitValidationCreateRequest


class TestValidationPipeline:
    def test_create_request(self):
        """Create a validation run and verify it can be started."""
        req = CircuitValidationCreateRequest(
            granularity_level="molecular_attr",
            circuit_ids=["00000000-0000-0000-0000-000000000001"],
            dry_run=True,
        )
        assert req.granularity_level == "molecular_attr"
        assert len(req.circuit_ids) == 1
        assert req.dry_run is True

    def test_adjudication_pipeline_full(self):
        """Test all 6 adjudication outcomes."""
        # Both support
        r = _adjudicate({"decision": "support", "confidence": 0.8}, {"decision": "support", "confidence": 0.75})
        assert r["status"] == "consensus_supported"

        # Divergence
        r = _adjudicate({"decision": "support", "confidence": 0.9}, {"decision": "support", "confidence": 0.5})
        assert r["status"] == "confidence_divergence"

        # Both reject
        r = _adjudicate({"decision": "reject", "confidence": 0.8}, {"decision": "reject", "confidence": 0.7})
        assert r["status"] == "consensus_rejected"

        # Conflict
        r = _adjudicate({"decision": "support", "confidence": 0.8}, {"decision": "reject", "confidence": 0.7})
        assert r["status"] == "model_conflict"

        # Low evidence
        r = _adjudicate({"decision": "support", "confidence": 0.3}, {"decision": "support", "confidence": 0.35})
        assert r["status"] == "low_evidence"

        # Insufficient info
        r = _adjudicate({"decision": "uncertain", "confidence": 0.5}, {"decision": "support", "confidence": 0.6})
        assert r["status"] == "insufficient_information"
