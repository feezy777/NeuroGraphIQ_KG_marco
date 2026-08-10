"""Paper evidence backend integration semantics (Phase 1 completion)."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.mirror_kg import PaperSource
from app.models.mirror_kg import MirrorEvidencePassage, MirrorEvidenceRecord
from app.services import paper_evidence_service as pes


class FakeSession:
    def __init__(self, get_map=None):
        self.get_map = get_map or {}
        self.added = []
        self.committed = 0

    async def get(self, model, pk):
        if model is PaperSource:
            return SimpleNamespace(id=pk)
        return self.get_map.get((model, pk))

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        pass

    async def execute(self, stmt, params=None):
        if "INSERT INTO paper_sources" in str(stmt):
            return _FakeScalarOne(uuid.uuid4())
        return _FakeResult()

    async def commit(self):
        self.committed += 1


class _FakeScalars:
    def first(self):
        return None

    def all(self):
        return []


class _FakeResult:
    def scalars(self):
        return _FakeScalars()

    def scalar_one(self):
        return 0


class _FakeScalarOne:
    def __init__(self, value):
        self.value = value

    def scalar_one(self):
        return self.value


class _Row:
    def __init__(self, confidence=None, evidence_text=""):
        self.confidence = confidence
        self.evidence_text = evidence_text


def _paper():
    return {
        "pmid": "12345678",
        "doi": "10.1/test",
        "title": "Test paper",
        "journal": "Neuro J",
        "year": "2026",
        "authors": "A B",
        "abstract": "The hippocampus is critical for memory consolidation.",
        "source": "europepmc",
    }


@pytest.fixture
def client():
    return TestClient(app, raise_server_exceptions=False)


def _attach_body(pmid="12345678"):
    return {
        "target_type": "connection",
        "target_id": str(uuid.uuid4()),
        "pmid": pmid,
        "direction": "supports",
        "reviewer_confidence": 0.8,
        "passages": [
            {
                "source_scope": "abstract",
                "passage": "The hippocampus is critical for memory consolidation.",
                "direction": "supports",
                "reason": "r",
                "confidence": 0.9,
            }
        ],
    }


def test_viewer_forbidden_on_attach(monkeypatch, client):
    monkeypatch.setattr(
        "app.routers.ontology.get_settings",
        lambda: SimpleNamespace(ontology_role="viewer"),
    )
    resp = client.post("/api/ontology/evidence/attach", json=_attach_body())
    assert resp.status_code == 403


def test_viewer_forbidden_on_rollback(monkeypatch, client):
    monkeypatch.setattr(
        "app.routers.ontology.get_settings",
        lambda: SimpleNamespace(ontology_role="viewer"),
    )
    resp = client.post(
        f"/api/ontology/evidence/{uuid.uuid4()}/rollback", json={"reason": "x"}
    )
    assert resp.status_code == 403


def test_attach_rejects_unverified_passages():
    session = FakeSession(get_map={(pes.TARGET_MODELS["connection"], uuid.UUID(int=1)): _Row(confidence=0.4)})
    with patch.object(pes, "verify_paper", new=AsyncMock(return_value=_paper())), \
         patch.object(pes, "_load_source", new=AsyncMock(return_value=("source text", "abstract"))):
        with pytest.raises(ValueError):
            import asyncio
            asyncio.run(
                pes.attach_evidence(
                    session,
                    target_type="connection",
                    target_id=uuid.UUID(int=1),
                    pmid="12345678",
                    direction="supports",
                    reviewer_confidence=0.8,
                    passages=[{"source_scope": "abstract", "passage": "fabricated text not in source", "direction": "supports", "reason": "r", "confidence": 0.9}],
                )
            )
    assert not any(isinstance(o, (MirrorEvidenceRecord, MirrorEvidencePassage)) for o in session.added)


def test_attach_rejects_duplicate_passage():
    session = FakeSession(get_map={(pes.TARGET_MODELS["connection"], uuid.UUID(int=1)): _Row(confidence=0.4)})
    with patch.object(pes, "verify_paper", new=AsyncMock(return_value=_paper())), \
         patch.object(pes, "_load_source", new=AsyncMock(return_value=("The hippocampus is critical for memory consolidation.", "abstract"))), \
         patch.object(pes, "_count_duplicate_hashes", new=AsyncMock(return_value=1)):
        import asyncio
        with pytest.raises(ValueError, match="duplicate"):
            asyncio.run(
                pes.attach_evidence(
                    session,
                    target_type="connection",
                    target_id=uuid.UUID(int=1),
                    pmid="12345678",
                    direction="supports",
                    reviewer_confidence=0.8,
                    passages=[{"source_scope": "abstract", "passage": "The hippocampus is critical for memory consolidation.", "direction": "supports", "reason": "r", "confidence": 0.9}],
                )
            )


def test_attach_rejects_not_found_direction():
    session = FakeSession(get_map={(pes.TARGET_MODELS["connection"], uuid.UUID(int=1)): _Row(confidence=0.4)})
    with patch.object(pes, "verify_paper", new=AsyncMock(return_value=_paper())), \
         patch.object(pes, "_load_source", new=AsyncMock(return_value=("The hippocampus is critical for memory consolidation.", "abstract"))), \
         patch.object(pes, "_count_duplicate_hashes", new=AsyncMock(return_value=0)):
        import asyncio
        with pytest.raises(ValueError, match="not_found"):
            asyncio.run(
                pes.attach_evidence(
                    session,
                    target_type="connection",
                    target_id=uuid.UUID(int=1),
                    pmid="12345678",
                    direction="not_found",
                    reviewer_confidence=0.8,
                    passages=[{"source_scope": "abstract", "passage": "The hippocampus is critical for memory consolidation.", "direction": "not_found", "reason": "r", "confidence": 0.9}],
                )
            )


def test_rollback_idempotent():
    rid = uuid.uuid4()
    record = MirrorEvidenceRecord(
        id=rid,
        evidence_target_type="connection",
        evidence_target_id=uuid.uuid4(),
        evidence_type="paper_verification",
        evidence_text="x",
        verification_status="invalidated",
    )
    session = FakeSession(get_map={(MirrorEvidenceRecord, rid): record})

    import asyncio
    result = asyncio.run(pes.rollback_evidence(session, rid, reason="again"))

    assert result["changed"] is False
    assert result["status"] == "already_invalidated"


def test_extract_doi_only_paper(monkeypatch, client):
    """DOI-only papers (no PMID) must not fail with 'paper identifier required'."""
    paper_source = SimpleNamespace(
        id=uuid.uuid4(), pmid=None, pmcid=None, doi="10.1000/doi-only",
        title="DOI Only Paper", journal="J", publication_year=2026,
        metadata_json={}, source="europepmc",
    )
    monkeypatch.setattr(
        "app.routers.ontology.pes.build_retrieval_context",
        AsyncMock(return_value={"claim_text": "c", "claim_components": [], "function_term": "f"}),
    )
    monkeypatch.setattr(
        "app.routers.ontology.pes.pfs.ensure_paper_cached",
        AsyncMock(return_value=(paper_source, None)),
    )
    monkeypatch.setattr("app.routers.ontology.pes.pfs.fetch_oa_fulltext_xml", AsyncMock(return_value=""))
    monkeypatch.setattr("app.routers.ontology.pes.ensure_paper_passages", AsyncMock(return_value=[]))
    monkeypatch.setattr("app.routers.ontology.pes.load_paper_passages", AsyncMock(return_value=[]))
    monkeypatch.setattr("app.routers.ontology.pes.score_paragraphs", lambda *a, **k: [])
    monkeypatch.setattr("app.routers.ontology.pes.build_windows", lambda *a, **k: [])
    monkeypatch.setattr(
        "app.routers.ontology.pes.extract_passage_from_paper",
        AsyncMock(return_value={
            "overall_direction": "not_found",
            "paper_relevance": 0.0,
            "assessment": "no evidence",
            "source_type": "none",
            "passages": [],
            "retrieval_summary": {},
            "parse_status": "ok",
            "retry_count": 0,
            "raw_response": "",
        }),
    )
    resp = client.post("/api/ontology/evidence/extract", json={
        "target_type": "connection",
        "target_id": str(uuid.uuid4()),
        "pmid": "",
        "doi": "10.1000/doi-only",
        "title": "DOI Only Paper",
        "abstract": "",
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["overall_direction"] == "not_found"
    assert body["paper"]["doi"] == "10.1000/doi-only"
