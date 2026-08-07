"""DB integrity closure: real FKs reject invalid ids; valid chain keeps working."""

from __future__ import annotations

import asyncio
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.database import AsyncSessionLocal
from app.services import paper_evidence_service as pes


def _run(coro):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


SOURCE = (
    "The hippocampus is critical for memory consolidation.\n\n"
    "We found hippocampal engagement during spatial navigation tasks."
)
PAPER = {
    "pmid": "99090001",
    "doi": "10.1/integrity",
    "title": "Integrity Paper",
    "journal": "J Integrity",
    "year": "2026",
    "authors": "A B",
    "abstract": SOURCE,
    "source": "europepmc",
}


async def _insert_evidence_row(s, paper_id=None):
    eid = uuid.uuid4()
    await s.execute(
        text(
            "INSERT INTO mirror_evidence_records "
            "(id, evidence_target_type, evidence_target_id, evidence_type, evidence_text, "
            "verification_status, paper_id) "
            "VALUES (:id, 'connection', :oid, 'paper_verification', '', 'pending', :pid)"
        ),
        {"id": eid, "oid": uuid.uuid4(), "pid": paper_id},
    )
    return eid


async def _cleanup(cids=(), eids=(), pids=()):
    async with AsyncSessionLocal() as s:
        for pid in pids:
            await s.execute(text("DELETE FROM paper_sources WHERE id=:pid"), {"pid": pid})
        for eid in eids:
            await s.execute(text("DELETE FROM mirror_evidence_records WHERE id=:eid"), {"eid": eid})
        for cid in cids:
            await s.execute(text("DELETE FROM mirror_region_connections WHERE id=:cid"), {"cid": cid})
        await s.commit()


def test_invalid_paper_id_rejected_by_fk():
    async def case():
        async with AsyncSessionLocal() as s:
            with pytest.raises(IntegrityError):
                await _insert_evidence_row(s, paper_id=uuid.uuid4())
                await s.commit()
            await s.rollback()
    _run(case())


def test_invalid_paper_passage_id_rejected_by_fk():
    async def case():
        async with AsyncSessionLocal() as s:
            eid = await _insert_evidence_row(s)
            await s.commit()
            try:
                with pytest.raises(IntegrityError):
                    await s.execute(
                        text(
                            "INSERT INTO mirror_evidence_passages "
                            "(evidence_id, paper_passage_id, source_scope, passage_text, passage_hash, "
                            "direction, source_verified) "
                            "VALUES (:eid, :ppid, 'abstract', 'x', 'h', 'supports', TRUE)"
                        ),
                        {"eid": eid, "ppid": uuid.uuid4()},
                    )
                    await s.commit()
                await s.rollback()
            finally:
                await s.execute(text("DELETE FROM mirror_evidence_records WHERE id=:eid"), {"eid": eid})
                await s.commit()
    _run(case())


def test_invalid_evidence_id_rejected_by_fk_on_adjustment_log():
    async def case():
        async with AsyncSessionLocal() as s:
            with pytest.raises(IntegrityError):
                await s.execute(
                    text(
                        "INSERT INTO confidence_adjustment_logs "
                        "(target_type, target_id, evidence_id, formula_version, status) "
                        "VALUES ('connection', :oid, :eid, 'paper_evidence_v1', 'applied')"
                    ),
                    {"oid": uuid.uuid4(), "eid": uuid.uuid4()},
                )
                await s.commit()
            await s.rollback()
    _run(case())


def test_valid_attach_rollback_under_fk():
    async def case():
        async with AsyncSessionLocal() as s:
            cid = uuid.uuid4()
            await s.execute(
                text(
                    "INSERT INTO mirror_region_connections "
                    "(id, source_region_name_en, target_region_name_en, connection_type, confidence, "
                    "granularity_level, source_atlas) "
                    "VALUES (:id, 'Hippocampus', 'Prefrontal cortex', 'direct', 0.2, 'macro', 'AAL3')"
                ),
                {"id": cid},
            )
            await s.commit()
            paper = await pes.ensure_paper_source(s, {**PAPER, "abstract": SOURCE, "fulltext": ""})
            await s.commit()
            await pes.ensure_paper_passages(
                s,
                paper.id,
                [
                    {
                        "source_scope": "abstract",
                        "section_title": "Abstract",
                        "paragraph_id": "abstract_p001",
                        "paragraph_index": 0,
                        "passage_text": SOURCE,
                        "text_hash": pes.passage_hash(SOURCE),
                        "locator": "abstract:paragraph:0",
                    }
                ],
            )
            await s.commit()
            with (
                patch.object(pes, "verify_paper", new=AsyncMock(return_value=PAPER)),
                patch.object(pes, "_load_source", new=AsyncMock(return_value=(SOURCE, "abstract"))),
            ):
                result = await pes.attach_evidence(
                    s,
                    target_type="connection",
                    target_id=cid,
                    pmid="99090001",
                    direction="supports",
                    reviewer_confidence=0.78,
                    passages=[{
                        "source_scope": "abstract",
                        "passage": SOURCE,
                        "direction": "supports",
                        "reason": "r",
                        "confidence": 0.8,
                        "source_verified": True,
                    }],
                    operator_id="integrity-test",
                )
                await s.commit()
            eid = uuid.UUID(result["evidence_id"])
            # FK references are valid and method persisted
            row = (
                await s.execute(
                    text(
                        "SELECT e.paper_id, ep.paper_passage_id, ep.source_verified, "
                        "ep.source_verification_method "
                        "FROM mirror_evidence_records e "
                        "JOIN mirror_evidence_passages ep ON ep.evidence_id=e.id "
                        "WHERE e.id=:eid"
                    ),
                    {"eid": eid},
                )
            ).first()
            assert row[0] == paper.id
            assert row[1] is not None
            assert row[2] is True
            assert row[3] == "exact"
            # rollback keeps evidence row (no physical delete) and sets invalidation audit
            rb = await pes.rollback_evidence(s, eid, reason="integrity test", operator_id="integrity-test")
            await s.commit()
            assert rb["status"] == "invalidated"
            st = (
                await s.execute(
                    text(
                        "SELECT verification_status, invalidated_by, invalidation_reason "
                        "FROM mirror_evidence_records WHERE id=:eid"
                    ),
                    {"eid": eid},
                )
            ).first()
            assert st[0] == "invalidated"
            assert st[1] == "integrity-test"
            assert st[2] == "integrity test"
            await s.execute(text("DELETE FROM mirror_evidence_records WHERE id=:eid"), {"eid": eid})
            await s.execute(text("DELETE FROM paper_sources WHERE id=:pid"), {"pid": paper.id})
            await s.execute(text("DELETE FROM mirror_region_connections WHERE id=:cid"), {"cid": cid})
            await s.commit()

    _run(case())
