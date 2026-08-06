"""Ontology REST API tests (patched services, no DB writes)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.ontology import OntologyTerm, OntologyVocabulary
from app.services import ontology_governance_service as gov
from app.services import ontology_service as svc


def _vocab(**overrides) -> OntologyVocabulary:
    now = datetime.now(timezone.utc)
    defaults = dict(
        id=uuid.uuid4(),
        code="associated_with",
        vocab_type="relation_type",
        label_cn=None,
        label_en="associated_with",
        description=None,
        status="active",
        seq=20,
        created_at=now,
        updated_at=now,
    )
    defaults.update(overrides)
    return OntologyVocabulary(**defaults)


def _term(**overrides) -> OntologyTerm:
    now = datetime.now(timezone.utc)
    defaults = dict(
        id=uuid.uuid4(),
        term_code="ng:func:memory",
        canonical_term_en="memory",
        canonical_term_cn=None,
        term_type="function",
        category=None,
        domain=None,
        role=None,
        effect_type=None,
        description=None,
        status="proposed",
        created_by="llm",
        created_at=now,
        updated_at=now,
    )
    defaults.update(overrides)
    return OntologyTerm(**defaults)


@pytest.fixture
def client():
    return TestClient(app, raise_server_exceptions=False)


def test_openapi_registers_ontology_routes(client):
    spec = client.get("/api/openapi.json").json()
    paths = spec.get("paths", {})
    assert "/api/ontology/vocabularies" in paths
    assert "/api/ontology/terms" in paths
    assert "/api/ontology/coverage" in paths
    assert "/api/ontology/report/term-panorama" in paths
    assert "/api/ontology/governance/dashboard" in paths
    assert "/api/ontology/governance/ungrounded-records" in paths
    assert "/api/ontology/terms/{term_id}/detail" in paths
    assert "/api/ontology/alignment/candidates" in paths
    assert "/api/ontology/audit/runs" in paths


def test_get_vocabularies_returns_items(monkeypatch, client):
    row = _vocab()

    async def _list(*args, **kwargs):
        return [row]

    monkeypatch.setattr(svc, "list_vocabularies", _list)
    resp = client.get("/api/ontology/vocabularies?vocab_type=relation_type")

    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["code"] == "associated_with"


def test_create_term_returns_201(monkeypatch, client):
    row = _term(status="proposed")

    async def _propose(*args, **kwargs):
        return row

    monkeypatch.setattr(svc, "propose_term", _propose)
    resp = client.post("/api/ontology/terms", json={"canonical_term_en": "memory", "created_by": "llm"})

    assert resp.status_code == 201
    body = resp.json()
    assert body["term_code"] == "ng:func:memory"
    assert body["status"] == "proposed"


def test_get_terms_paginated(monkeypatch, client):
    row = _term(status="active")

    async def _list(*args, **kwargs):
        return [row], 1

    monkeypatch.setattr(svc, "list_terms", _list)
    resp = client.get("/api/ontology/terms?status=active&limit=50")

    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["status"] == "active"


def test_activate_term(monkeypatch, client):
    row = _term(status="active")

    async def _activate(*args, **kwargs):
        return row

    monkeypatch.setattr(svc, "activate_term", _activate)
    resp = client.post(f"/api/ontology/terms/{row.id}/activate")

    assert resp.status_code == 200
    assert resp.json()["status"] == "active"


def test_get_coverage_shape(monkeypatch, client):
    async def _coverage(*args, **kwargs):
        return {
            "items": [
                {"key": "circuit_function", "label": "circuit_function", "total": 10, "grounded": 6, "ungrounded": 4, "by_method": {"deterministic": 6}}
            ],
            "total_terms": 5,
            "active_terms": 3,
            "proposed_terms": 2,
        }

    monkeypatch.setattr(svc, "coverage", _coverage)
    resp = client.get("/api/ontology/coverage")

    assert resp.status_code == 200
    body = resp.json()
    assert body["items"][0]["grounded"] == 6
    assert body["proposed_terms"] == 2


def test_run_deterministic_grounding(monkeypatch, client):
    async def _run(*args, **kwargs):
        return {"target_type": "circuit_function", "processed": 2, "grounded": 1, "ungrounded": 1}

    monkeypatch.setattr(svc, "run_deterministic_grounding_batch", _run)
    resp = client.post(
        "/api/ontology/groundings/run",
        json={"target_type": "circuit_function", "limit": 10},
    )

    assert resp.status_code == 200
    assert resp.json()["grounded"] == 1


def test_get_term_panorama(monkeypatch, client):
    async def _panorama(*args, **kwargs):
        return {
            "target_type": "projection_function",
            "total_distinct": 1,
            "items": [{"term_key": "memory", "term_label": "memory", "count": 42, "sample_ids": []}],
        }

    monkeypatch.setattr(svc, "term_panorama", _panorama)
    resp = client.get("/api/ontology/report/term-panorama?target_type=projection_function")

    assert resp.status_code == 200
    assert resp.json()["items"][0]["count"] == 42


def test_governance_dashboard(monkeypatch, client):
    async def _dashboard(*args, **kwargs):
        return {
            "function_anchor_rate": 0.96,
            "function_total": 114110,
            "function_grounded": 109789,
            "proposed_terms": 4988,
            "ungrounded_records": 4321,
            "region_unaligned": 96,
            "enum_anomalies": 0,
            "last_audit_at": None,
        }

    monkeypatch.setattr(gov, "dashboard", _dashboard)
    resp = client.get("/api/ontology/governance/dashboard?granularity_level=macro")

    assert resp.status_code == 200
    body = resp.json()
    assert body["function_anchor_rate"] == 0.96
    assert body["proposed_terms"] == 4988


def test_governance_ungrounded_records(monkeypatch, client):
    async def _ungrounded(*args, **kwargs):
        return {
            "items": [
                {
                    "target_type": "projection_function",
                    "target_id": "00000000-0000-0000-0000-000000000001",
                    "function_term": "weird phrase",
                    "granularity_level": "molecular_attr",
                    "reason": "no matching active ontology term",
                    "recommendations": [],
                }
            ],
            "total": 1,
        }

    monkeypatch.setattr(gov, "ungrounded_records", _ungrounded)
    resp = client.get("/api/ontology/governance/ungrounded-records?limit=10")

    assert resp.status_code == 200
    assert resp.json()["total"] == 1
