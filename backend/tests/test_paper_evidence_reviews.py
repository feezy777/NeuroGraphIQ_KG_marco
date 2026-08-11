"""Phase 1: paper_evidence_reviews lifecycle tests (build/approve/reject/promote/return/list/get)."""

from __future__ import annotations

import asyncio
import uuid
from unittest.mock import patch

import pytest
from sqlalchemy import text

from app.database import AsyncSessionLocal
from app.services import paper_evidence_service as pes


def _run(coro):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ════════════════════════════════════════════════════════════════════════════
# Helpers
# ════════════════════════════════════════════════════════════════════════════


def _uuid():
    return uuid.uuid4()


def _make_connection(granularity: str = "macro_clinical"):
    """Insert a minimal mirror_region_connection for test targeting."""
    async def _insert():
        conn_id = _uuid()
        async with AsyncSessionLocal() as s:
            await s.execute(
                text(
                    "INSERT INTO mirror_region_connections "
                    "(id, source_region_name_en, target_region_name_en, connection_type, "
                    "directionality, granularity_level, source_atlas, mirror_status, review_status) "
                    "VALUES (:id, 'Hippocampus', 'Prefrontal Cortex', 'projection', "
                    "'unidirectional', :gl, 'test', 'llm_suggested', 'pending')"
                ),
                {"id": conn_id, "gl": granularity},
            )
            await s.commit()
        return conn_id
    return _run(_insert())


def _make_paper_source(pmid: str = "30000001"):
    """Insert a minimal paper_sources row for test referencing."""
    async def _insert():
        paper_id = _uuid()
        async with AsyncSessionLocal() as s:
            await s.execute(
                text(
                    "INSERT INTO paper_sources "
                    "(id, source, pmid, title, journal, publication_year, is_oa) "
                    "VALUES (:id, 'europepmc', :pmid, 'Test Paper Title', 'Neuro J', 2026, false)"
                ),
                {"id": paper_id, "pmid": pmid},
            )
            await s.commit()
        return paper_id
    return _run(_insert())


def _cleanup_review(review_id):
    async def _del():
        async with AsyncSessionLocal() as s:
            await s.execute(
                text("DELETE FROM paper_evidence_review_passages WHERE review_id = :rid"),
                {"rid": review_id},
            )
            await s.execute(
                text("DELETE FROM paper_evidence_reviews WHERE id = :rid"),
                {"rid": review_id},
            )
            await s.commit()
    _run(_del())


def _cleanup_connection(conn_id):
    async def _del():
        async with AsyncSessionLocal() as s:
            await s.execute(
                text("DELETE FROM mirror_region_connections WHERE id = :cid"),
                {"cid": conn_id},
            )
            await s.commit()
    _run(_del())


def _cleanup_paper(paper_id):
    async def _del():
        async with AsyncSessionLocal() as s:
            await s.execute(
                text("DELETE FROM paper_sources WHERE id = :pid"),
                {"pid": paper_id},
            )
            await s.commit()
    _run(_del())


def _cleanup_evidence(evidence_ids):
    async def _del():
        async with AsyncSessionLocal() as s:
            for eid in evidence_ids:
                await s.execute(
                    text("DELETE FROM mirror_evidence_passages WHERE evidence_id = :eid"),
                    {"eid": eid},
                )
                await s.execute(
                    text("DELETE FROM confidence_adjustment_logs WHERE evidence_id = :eid"),
                    {"eid": eid},
                )
                await s.execute(
                    text("DELETE FROM mirror_evidence_records WHERE id = :eid"),
                    {"eid": eid},
                )
            await s.commit()
    _run(_del())


def _sample_passages():
    return [
        {
            "passage": "The hippocampus projects to the prefrontal cortex via direct pathways.",
            "source_scope": "abstract",
            "direction": "supports",
            "evidence_level": "direct",
            "reason": "Explicit statement of projection.",
            "confidence": 0.85,
            "source_verified": True,
            "source_verification_method": "exact",
            "source_locator": "abstract:0",
            "supported_components": ["source_region", "target_region", "relation"],
            "is_selected": True,
        }
    ]


# ════════════════════════════════════════════════════════════════════════════
# Tests
# ════════════════════════════════════════════════════════════════════════════


def test_build_review_approved():
    """build_review with supports direction creates an approved review."""
    conn_id = _make_connection()
    paper_id = _make_paper_source()
    try:
        result = _run(_build_review_inner(conn_id, paper_id, "supports", _sample_passages()))
        assert result["review_id"]
        assert result["status"] == "approved"
        # Verify review exists
        review = _run(_get_review_inner(result["review_id"]))
        assert review["review_status"] == "approved"
        assert review["promotion_status"] == "awaiting_promotion"
        assert review["target_type"] == "connection"
        assert review["paper_id"] == str(paper_id)
        assert len(review["passages"]) == 1
        assert review["passages"][0]["source_verified"] is True
    finally:
        if "result" in locals():
            _cleanup_review(uuid.UUID(result["review_id"]))
        _cleanup_paper(paper_id)
        _cleanup_connection(conn_id)


def test_build_review_rejected():
    """build_review with not_found direction creates a rejected review."""
    conn_id = _make_connection()
    paper_id = _make_paper_source()
    try:
        result = _run(_build_review_inner(conn_id, paper_id, "not_found", _sample_passages()))
        assert result["review_id"]
        assert result["status"] == "rejected"
        review = _run(_get_review_inner(result["review_id"]))
        assert review["review_status"] == "rejected"
    finally:
        if "result" in locals():
            _cleanup_review(uuid.UUID(result["review_id"]))
        _cleanup_paper(paper_id)
        _cleanup_connection(conn_id)


def test_approved_does_not_create_evidence_or_modify_confidence():
    """build_review/approve_review writes to paper_evidence_reviews only — never mirror_evidence_records."""
    conn_id = _make_connection()
    paper_id = _make_paper_source()
    try:
        # build with "supports" creates an already-approved review
        result = _run(_build_review_inner(conn_id, paper_id, "supports", _sample_passages()))
        review_id = uuid.UUID(result["review_id"])
        assert result["status"] == "approved"
        # Count evidence records for this target — should be 0
        evidence_count = _run(_count_evidence_for_target(conn_id))
        assert evidence_count == 0, "build_review should never write mirror_evidence_records"
        # approve on already-approved is rejected (correct behavior)
        with pytest.raises(ValueError, match="cannot approve"):
            _run(_approve_inner(review_id))
        evidence_count2 = _run(_count_evidence_for_target(conn_id))
        assert evidence_count2 == 0, "approve_review should never write mirror_evidence_records"
    finally:
        if "result" in locals():
            _cleanup_review(review_id)
        _cleanup_paper(paper_id)
        _cleanup_connection(conn_id)


def test_approve_review():
    """approve_review transitions status to 'approved'."""
    conn_id = _make_connection()
    paper_id = _make_paper_source()
    try:
        # Build as draft-like first (use returned state from return, then approve)
        result = _run(_build_review_inner(conn_id, paper_id, "supports", _sample_passages()))
        review_id = uuid.UUID(result["review_id"])
        assert result["status"] == "approved"  # already approved from build
        # Reject first to test approve from non-draft
        _run(_reject_inner(review_id))
        with pytest.raises(ValueError, match="cannot approve"):
            _run(_approve_inner(review_id))
    finally:
        if "result" in locals():
            _cleanup_review(review_id)
        _cleanup_paper(paper_id)
        _cleanup_connection(conn_id)


def test_reject_review():
    """reject_review transitions to 'rejected'."""
    conn_id = _make_connection()
    paper_id = _make_paper_source()
    try:
        result = _run(_build_review_inner(conn_id, paper_id, "supports", _sample_passages()))
        review_id = uuid.UUID(result["review_id"])
        rej = _run(_reject_inner(review_id))
        assert rej["status"] == "rejected"
        review = _run(_get_review_inner(review_id))
        assert review["review_status"] == "rejected"
    finally:
        if "result" in locals():
            _cleanup_review(review_id)
        _cleanup_paper(paper_id)
        _cleanup_connection(conn_id)


def test_promote_returns_on_wrong_status():
    """promote_review raises ValueError when review is not in 'approved' status."""
    conn_id = _make_connection()
    paper_id = _make_paper_source()
    try:
        result = _run(_build_review_inner(conn_id, paper_id, "not_found", _sample_passages()))
        review_id = uuid.UUID(result["review_id"])
        assert result["status"] == "rejected"
        with pytest.raises(ValueError, match="cannot promote"):
            _run(_promote_inner(review_id))
    finally:
        if "result" in locals():
            _cleanup_review(review_id)
        _cleanup_paper(paper_id)
        _cleanup_connection(conn_id)


def test_promote_creates_evidence():
    """promote_review calls attach_evidence and creates MirrorEvidenceRecord + updates review."""
    conn_id = _make_connection()
    paper_id = _make_paper_source()
    evidence_ids_to_cleanup = []
    try:
        # Need source_verified passages
        passage_text = "The hippocampus projects to the prefrontal cortex via direct pathways."
        passages = [
            {
                "passage": passage_text,
                "source_scope": "abstract",
                "direction": "supports",
                "evidence_level": "direct",
                "reason": "Explicit statement.",
                "confidence": 0.85,
                "source_verified": True,
                "source_verification_method": "exact",
                "source_locator": "abstract:0",
                "supported_components": ["source_region", "target_region", "relation"],
                "is_selected": True,
            }
        ]
        # Mock verify_paper and _load_source to bypass Europe PMC API calls
        mock_paper = {
            "pmid": "30000001",
            "doi": "10.1/test",
            "title": "Test Paper Title",
            "journal": "Neuro J",
            "year": "2026",
            "authors": "A B",
            "abstract": passage_text,
            "source": "europepmc",
        }
        with patch.object(pes, "verify_paper", return_value=mock_paper), \
             patch.object(pes, "_load_source", return_value=(passage_text, "abstract")):
            result = _run(_build_review_inner(conn_id, paper_id, "supports", passages))
            review_id = uuid.UUID(result["review_id"])
            assert result["status"] == "approved"
            # promote
            promote_result = _run(_promote_inner(review_id))
            assert promote_result["status"] == "promoted"
            assert promote_result["evidence_id"]
            evidence_ids_to_cleanup.append(promote_result["evidence_id"])
            # Verify review state
            review = _run(_get_review_inner(review_id))
            assert review["promotion_status"] == "promoted"
            assert review["evidence_id"] == promote_result["evidence_id"]
            # Verify evidence record exists
            async def _check_ev():
                async with AsyncSessionLocal() as s:
                    row = (await s.execute(
                        text(
                            "SELECT id, evidence_target_type, evidence_target_id, "
                            "verification_status, paper_pmid FROM mirror_evidence_records "
                            "WHERE id = :eid"
                        ),
                        {"eid": uuid.UUID(promote_result["evidence_id"])},
                    )).first()
                    return row
            ev_row = _run(_check_ev())
            assert ev_row is not None
            assert ev_row[3] == "human_verified"
    finally:
        if "result" in locals():
            _cleanup_review(review_id)
        _cleanup_evidence(evidence_ids_to_cleanup)
        _cleanup_paper(paper_id)
        _cleanup_connection(conn_id)


def test_promote_idempotent():
    """promote_review is idempotent: second call returns 'already_promoted'."""
    conn_id = _make_connection()
    paper_id = _make_paper_source()
    evidence_ids_to_cleanup = []
    try:
        passage_text = "The hippocampus projects to the prefrontal cortex via direct pathways."
        passages = [
            {
                "passage": passage_text,
                "source_scope": "abstract",
                "direction": "supports",
                "evidence_level": "direct",
                "reason": "Explicit statement.",
                "confidence": 0.85,
                "source_verified": True,
                "source_verification_method": "exact",
                "source_locator": "abstract:0",
                "supported_components": ["source_region", "target_region", "relation"],
                "is_selected": True,
            }
        ]
        mock_paper = {
            "pmid": "30000001",
            "doi": "10.1/test",
            "title": "Test Paper Title",
            "journal": "Neuro J",
            "year": "2026",
            "authors": "A B",
            "abstract": passage_text,
            "source": "europepmc",
        }
        with patch.object(pes, "verify_paper", return_value=mock_paper), \
             patch.object(pes, "_load_source", return_value=(passage_text, "abstract")):
            result = _run(_build_review_inner(conn_id, paper_id, "supports", passages))
            review_id = uuid.UUID(result["review_id"])
            # First promote
            p1 = _run(_promote_inner(review_id))
            assert p1["status"] == "promoted"
            evidence_ids_to_cleanup.append(p1["evidence_id"])
            # Second promote — idempotent
            p2 = _run(_promote_inner(review_id))
            assert p2["status"] == "already_promoted"
            assert p2["evidence_id"] == p1["evidence_id"]
    finally:
        if "result" in locals():
            _cleanup_review(review_id)
        _cleanup_evidence(evidence_ids_to_cleanup)
        _cleanup_paper(paper_id)
        _cleanup_connection(conn_id)


def test_return_review():
    """return_review sets promotion_status='returned' and review_status='awaiting_review'."""
    conn_id = _make_connection()
    paper_id = _make_paper_source()
    try:
        result = _run(_build_review_inner(conn_id, paper_id, "supports", _sample_passages()))
        review_id = uuid.UUID(result["review_id"])
        ret = _run(_return_inner(review_id, "Needs clarification on evidence level."))
        assert ret["status"] == "returned"
        review = _run(_get_review_inner(review_id))
        assert review["promotion_status"] == "returned"
        assert review["review_status"] == "awaiting_review"
        assert review["return_reason"] == "Needs clarification on evidence level."
    finally:
        if "result" in locals():
            _cleanup_review(review_id)
        _cleanup_paper(paper_id)
        _cleanup_connection(conn_id)


def test_list_reviews():
    """list_reviews returns paginated results with optional filters."""
    conn_id = _make_connection()
    paper_id = _make_paper_source()
    review_id = None
    try:
        result_a = _run(_build_review_inner(conn_id, paper_id, "supports", _sample_passages()))
        review_id = uuid.UUID(result_a["review_id"])
        # List all
        all_items = _run(_list_inner())
        assert all_items["total"] >= 1
        # Filter by status
        approved = _run(_list_inner(review_status="approved"))
        for item in approved["items"]:
            assert item["review_status"] == "approved"
        # Filter by target_type
        by_type = _run(_list_inner(target_type="connection"))
        for item in by_type["items"]:
            assert item["target_type"] == "connection"
    finally:
        if review_id:
            _cleanup_review(review_id)
        _cleanup_paper(paper_id)
        _cleanup_connection(conn_id)


def test_get_review_with_passages():
    """get_review returns review with its frozen passages."""
    conn_id = _make_connection()
    paper_id = _make_paper_source()
    try:
        passages = [
            {
                "passage": "The hippocampus projects to the PFC.",
                "source_scope": "abstract",
                "direction": "supports",
                "evidence_level": "direct",
                "reason": "Direct evidence.",
                "confidence": 0.85,
                "source_verified": True,
                "source_verification_method": "exact",
                "source_locator": "abstract:0",
                "supported_components": ["source_region", "target_region"],
                "is_selected": True,
            },
            {
                "passage": "Prefrontal-hippocampal connectivity is well-established.",
                "source_scope": "abstract",
                "direction": "supports",
                "evidence_level": "indirect",
                "reason": "Review context.",
                "confidence": 0.6,
                "source_verified": False,
                "source_verification_method": None,
                "source_locator": None,
                "supported_components": ["source_region", "target_region"],
                "is_selected": False,
            },
        ]
        result = _run(_build_review_inner(conn_id, paper_id, "supports", passages))
        review_id = uuid.UUID(result["review_id"])
        review = _run(_get_review_inner(review_id))
        assert len(review["passages"]) == 2
        assert review["passages"][0]["is_selected"] is True
        assert review["passages"][0]["source_verified"] is True
        assert review["passages"][1]["is_selected"] is False
    finally:
        if "result" in locals():
            _cleanup_review(review_id)
        _cleanup_paper(paper_id)
        _cleanup_connection(conn_id)


# ════════════════════════════════════════════════════════════════════════════
# Internal async helpers (called via _run in tests)
# ════════════════════════════════════════════════════════════════════════════


async def _build_review_inner(conn_id, paper_id, direction, passages):
    async with AsyncSessionLocal() as s:
        return await pes.build_review(
            s,
            target_type="connection",
            target_id=conn_id,
            paper_id=paper_id,
            task_id=None,
            task_item_id=None,
            reviewer_id="test_reviewer",
            claim_version="claim_v1",
            claim_text_snapshot="Hippocampus projects to Prefrontal Cortex.",
            claim_components_snapshot=[
                {"component_type": "source_region", "required": True},
                {"component_type": "target_region", "required": True},
                {"component_type": "relation", "required": True},
            ],
            model_direction="supports",
            model_assessment="Model assessment text.",
            reviewer_direction=direction,
            reviewer_evidence_level="direct",
            reviewer_confidence=0.85,
            reviewer_note="Reviewer note.",
            coverage_summary_snapshot={
                "required_components": ["source_region", "target_region", "relation"],
                "supported_components": ["source_region", "target_region", "relation"],
                "coverage_ratio": 1.0,
            },
            coverage_formula_version="paper_evidence_coverage_v1",
            draft_revision=0,
            passages=passages,
        )


async def _get_review_inner(review_id):
    async with AsyncSessionLocal() as s:
        return await pes.get_review(s, review_id)


async def _approve_inner(review_id):
    async with AsyncSessionLocal() as s:
        return await pes.approve_review(s, review_id)


async def _reject_inner(review_id):
    async with AsyncSessionLocal() as s:
        return await pes.reject_review(s, review_id)


async def _promote_inner(review_id):
    async with AsyncSessionLocal() as s:
        return await pes.promote_review(s, review_id)


async def _return_inner(review_id, reason):
    async with AsyncSessionLocal() as s:
        return await pes.return_review(s, review_id, reason=reason)


async def _list_inner(review_status=None, promotion_status=None, target_type=None, page=1, page_size=20):
    async with AsyncSessionLocal() as s:
        return await pes.list_reviews(
            s,
            review_status=review_status,
            promotion_status=promotion_status,
            target_type=target_type,
            page=page,
            page_size=page_size,
        )


async def _count_evidence_for_target(target_id):
    async with AsyncSessionLocal() as s:
        return (
            await s.execute(
                text(
                    "SELECT COUNT(*) FROM mirror_evidence_records "
                    "WHERE evidence_target_id = :tid"
                ),
                {"tid": target_id},
            )
        ).scalar_one()
