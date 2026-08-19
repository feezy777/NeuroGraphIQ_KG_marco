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


def test_attach_requires_note_for_similarity_passages():
    session = FakeSession(get_map={(pes.TARGET_MODELS["connection"], uuid.UUID(int=1)): _Row(confidence=0.4)})
    source = "The hippocampus is critical for memory consolidation."
    with patch.object(pes, "verify_paper", new=AsyncMock(return_value=_paper())), \
         patch.object(pes, "_load_source", new=AsyncMock(return_value=(source, "abstract"))), \
         patch.object(pes, "_count_duplicate_hashes", new=AsyncMock(return_value=0)):
        import asyncio
        with pytest.raises(ValueError, match="reviewer note"):
            asyncio.run(
                pes.attach_evidence(
                    session,
                    target_type="connection",
                    target_id=uuid.UUID(int=1),
                    pmid="12345678",
                    direction="supports",
                    reviewer_confidence=0.8,
                    passages=[{"source_scope": "abstract", "passage": "The hippocampus is critical for memory consilidation.", "direction": "supports", "reason": "r", "confidence": 0.9}],
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


def test_extract_selected_multi_paper(monkeypatch, client):
    monkeypatch.setattr(
        "app.routers.ontology.pes.build_retrieval_context",
        AsyncMock(return_value={"claim_text": "c", "claim_components": [], "function_term": "f"}),
    )
    extract_candidates = AsyncMock(return_value=(
        [
            {"paper_id": "p1", "title": "A", "model_direction": "supports", "passages": []},
            {"paper_id": "p2", "title": "B", "error_code": "PAPER_FETCH_FAILED", "passages": []},
        ],
        "deepseek-v4-flash-test",
    ))
    monkeypatch.setattr(
        "app.routers.ontology.pes.extract_candidates_for_target",
        extract_candidates,
    )
    resp = client.post("/api/ontology/evidence/extract-selected", json={
        "target_type": "connection",
        "target_id": str(uuid.uuid4()),
        "papers": [
            {"pmid": "11111", "title": "A", "abstract": "A directly studies the selected connection."},
            {"pmid": "22222", "title": "B"},
        ],
    })
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["results"]) == 2
    assert body["results"][1]["error_code"] == "PAPER_FETCH_FAILED"
    assert body["llm_model"] == "deepseek-v4-flash-test"
    assert extract_candidates.await_args.kwargs["papers"][0]["abstract"] == (
        "A directly studies the selected connection."
    )


def test_weak_evidence_status_fits_column():
    """Regression: 'no_change_weak_evidence' (23 chars) must fit confidence_adjustment_status."""
    from app.services.confidence_rules import compute_adjustment

    r = compute_adjustment(direction="supports", current_confidence=0.9, reviewer_confidence=0.4)
    assert r.adjustment_status == "no_change_weak_evidence"
    assert len(r.adjustment_status) <= 32


def test_merge_manual_candidates_persists_to_active_item():
    """手动提取结果合并写回活跃 item:现有候选保留,手动按 paper_id 覆盖/追加。"""
    import json
    import uuid as _uuid

    from sqlalchemy import text as _text

    from app.database import AsyncSessionLocal
    from app.services import paper_evidence_service as _pes

    async def case():
        oid = _uuid.uuid4()
        async with AsyncSessionLocal() as s:
            tid = (
                await s.execute(
                    _text(
                        "INSERT INTO paper_evidence_tasks "
                        "(target_type, target_id, scope, mode, max_papers_per_object, status, total_items) "
                        "VALUES ('connection', :oid, 'selected', 'function', 3, 'pending', 1) RETURNING id::text"
                    ),
                    {"oid": oid},
                )
            ).scalar_one()
            iid = (
                await s.execute(
                    _text(
                        "INSERT INTO paper_evidence_task_items (task_id, target_type, target_id, label, status, candidate_papers) "
                        "VALUES (:tid, 'connection', :oid, 'x', 'awaiting_review', CAST(:cp AS jsonb)) RETURNING id::text"
                    ),
                    {"tid": tid, "oid": oid, "cp": json.dumps([
                        {"paper_id": "p-pre", "pmid": "1", "title": "Pre", "passages": []},
                    ])},
                )
            ).scalar_one()
            await s.commit()
            try:
                await _pes.merge_manual_candidates(
                    s,
                    target_type="connection",
                    target_id=oid,
                    manual_candidates=[
                        {"paper_id": "p-pre", "pmid": "1", "title": "Pre-Updated", "passages": [{"passage": "new"}]},
                        {"paper_id": "p-man", "pmid": "2", "title": "Manual", "passages": [{"passage": "m"}]},
                    ],
                )
                await s.commit()
                row = (
                    await s.execute(
                        _text("SELECT candidate_papers FROM paper_evidence_task_items WHERE id::text=:iid"),
                        {"iid": iid},
                    )
                ).first()
                papers = {c["paper_id"]: c for c in row[0]}
                # 手动覆盖预处理同名论文 + 追加新论文
                assert papers["p-pre"]["title"] == "Pre-Updated"
                assert len(papers["p-pre"]["passages"]) == 1
                assert papers["p-man"]["title"] == "Manual"
            finally:
                await s.execute(_text("DELETE FROM paper_evidence_tasks WHERE id::text=:tid"), {"tid": tid})
                await s.commit()

    _run_case(case())


def _run_case(coro):
    import asyncio as _asyncio
    _asyncio.set_event_loop_policy(_asyncio.WindowsSelectorEventLoopPolicy())
    loop = _asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()
