"""End-to-end paper-evidence flow against a real database (external APIs mocked).

Covers the 16-step acceptance flow: low-confidence target → verified attach →
confidence update → evidence_text rebuild → evidence list → validation record →
rollback → confidence restore → evidence_text rebuild → idempotent rollback.
"""

from __future__ import annotations

import asyncio
import uuid
from unittest.mock import AsyncMock, patch

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


SOURCE = (
    "Background: The hippocampus is critical for memory consolidation. "
    "Results: Our tractography data shows a connection from the hippocampus to the prefrontal cortex. "
    "Conclusion: This pathway supports memory-related functions."
)
PAPER = {
    "pmid": "99000001",
    "doi": "10.1/e2e",
    "title": "E2E Paper",
    "journal": "E2E J",
    "year": "2026",
    "authors": "A B",
    "abstract": SOURCE,
    "source": "europepmc",
}
PASSAGE = SOURCE


async def _insert_connection():
    cid = uuid.uuid4()
    async with AsyncSessionLocal() as s:
        await s.execute(
            text(
                "INSERT INTO mirror_region_connections "
                "(id, source_region_name_en, target_region_name_en, connection_type, confidence, granularity_level, source_atlas) "
                "VALUES (:id, 'Hippocampus', 'Prefrontal cortex', 'direct', 0.2, 'macro', 'AAL3')"
            ),
            {"id": cid},
        )
        await s.commit()
    return cid


async def _cleanup(cid):
    async with AsyncSessionLocal() as s:
        await s.execute(
            text(
                "DELETE FROM mirror_evidence_records WHERE evidence_target_id=:oid AND evidence_type='paper_verification'"
            ),
            {"oid": cid},
        )
        await s.execute(
            text(
                "DELETE FROM evidence_validation_records WHERE target_id=:oid"
            ),
            {"oid": cid},
        )
        await s.execute(
            text("DELETE FROM confidence_adjustment_logs WHERE target_id=:oid"),
            {"oid": cid},
        )
        await s.execute(text("DELETE FROM ontology_change_logs WHERE entity_id=:oid"), {"oid": cid})
        await s.execute(text("DELETE FROM mirror_region_connections WHERE id=:id"), {"id": cid})
        await s.execute(text("DELETE FROM paper_sources WHERE pmid='99000001'"))
        await s.commit()


def test_full_paper_evidence_flow():
    cid = _run(_insert_connection())
    try:
        # 1) attach with a verified passage (backend re-verifies against source)
        with (
            patch.object(pes, "verify_paper", new=AsyncMock(return_value=PAPER)),
            patch.object(pes, "_load_source", new=AsyncMock(return_value=(SOURCE, "abstract"))),
        ):
            result = _run(_attach(cid))
        evidence_id = result["evidence_id"]
        assert result["final_confidence"] == pytest.approx(0.8)
        # 2) object confidence + evidence_text updated
        _run(_check_attached(cid, evidence_id))
        # 3) rollback restores confidence and rebuilds evidence_text
        with patch.object(pes, "verify_paper", new=AsyncMock(return_value=PAPER)):
            rb = _run(_rollback(evidence_id))
        assert rb["status"] == "invalidated"
        _run(_check_rollback(cid, evidence_id))
        # 4) idempotent rollback
        rb2 = _run(_rollback(evidence_id))
        assert rb2["changed"] is False
    finally:
        _run(_cleanup(cid))


async def _attach(cid):
    async with AsyncSessionLocal() as s:
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
        result = await pes.attach_evidence(
            s,
                    target_type="connection",
                    target_id=cid,
                    pmid="99000001",
                    direction="supports",
                    reviewer_confidence=0.8,
                    passages=[{
                        "source_scope": "abstract",
                        "section_title": None,
                        "paragraph_index": 0,
                        "passage": PASSAGE,
                        "direction": "supports",
                        "reason": "explicit",
                        "confidence": 0.85,
                        "source_locator": "abstract:0",
                        "source_verified": True,
                    }],
                    operator_id="e2e",
                )
        await s.commit()
        return result


async def _check_attached(cid, evidence_id):
    async with AsyncSessionLocal() as s:
        row = (
            await s.execute(
                text("SELECT confidence, evidence_text FROM mirror_region_connections WHERE id=:id"),
                {"id": cid},
            )
        ).first()
        assert float(row[0]) == pytest.approx(0.8)
        assert evidence_id in (row[1] or "")
        ev = (
            await s.execute(
                text(
                    "SELECT verification_status, confidence_adjustment_status, paper_id, "
                    "reviewer_confidence, evidence_level FROM mirror_evidence_records WHERE id=:eid"
                ),
                {"eid": evidence_id},
            )
        ).first()
        assert ev[0] == "human_verified"
        assert ev[2] is not None
        assert float(ev[3]) == pytest.approx(0.8)
        assert ev[4] == "indirect"
        pcount = (
            await s.execute(
                text("SELECT COUNT(*) FROM mirror_evidence_passages WHERE evidence_id=:eid AND is_selected"),
                {"eid": evidence_id},
            )
        ).scalar_one()
        assert pcount == 1
        passage_row = (
            await s.execute(
                text(
                    "SELECT paper_passage_id, semantic_confidence FROM mirror_evidence_passages "
                    "WHERE evidence_id=:eid AND is_selected"
                ),
                {"eid": evidence_id},
            )
        ).first()
        assert passage_row[0] is not None
        assert float(passage_row[1]) == pytest.approx(0.85)
        vcount = (
            await s.execute(
                text("SELECT COUNT(*) FROM evidence_validation_records WHERE evidence_id=:eid"),
                {"eid": evidence_id},
            )
        ).scalar_one()
        assert vcount >= 1
        acount = (
            await s.execute(
                text("SELECT COUNT(*) FROM confidence_adjustment_logs WHERE evidence_id=:eid AND status='applied'"),
                {"eid": evidence_id},
            )
        ).scalar_one()
        assert acount == 1
        listed = await pes.list_paper_evidence(s, target_type="connection", target_id=cid)
        assert listed["items"][0]["evidence_id"] == evidence_id
        assert listed["items"][0]["passages"][0]["source_verified"] is True


async def _rollback(evidence_id):
    async with AsyncSessionLocal() as s:
        result = await pes.rollback_evidence(
            s,
            uuid.UUID(evidence_id),
            reason="e2e rollback",
            operator_id="e2e",
        )
        await s.commit()
        return result


async def _check_rollback(cid, evidence_id):
    async with AsyncSessionLocal() as s:
        row = (
            await s.execute(
                text("SELECT confidence, evidence_text FROM mirror_region_connections WHERE id=:id"),
                {"id": cid},
            )
        ).first()
        assert float(row[0]) == pytest.approx(0.2)
        assert row[1] == "" or evidence_id not in (row[1] or "")
        st = (
            await s.execute(
                text("SELECT verification_status FROM mirror_evidence_records WHERE id=:eid"),
                {"eid": evidence_id},
            )
        ).scalar_one()
        assert st == "invalidated"
