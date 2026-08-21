"""Formal evidence review snapshot: claim/coverage/model vs reviewer/audit."""

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
    "Anterograde tracing revealed dense BLA terminals in the infralimbic cortex. "
    "Activation of BLA terminals facilitated extinction learning."
)
MIXED_SOURCE = SOURCE + "\n\nActivation of BLA terminals did not alter extinction learning."
PAPER = {
    "pmid": "99080001",
    "doi": "10.1/snapshot",
    "title": "Snapshot Paper",
    "journal": "J Snap",
    "year": "2026",
    "authors": "A B",
    "abstract": SOURCE,
    "source": "europepmc",
}


async def _insert_connection(name_cn="旧名称"):
    cid = uuid.uuid4()
    async with AsyncSessionLocal() as s:
        await s.execute(
            text(
                "INSERT INTO mirror_region_connections "
                "(id, source_region_name_en, target_region_name_en, connection_type, confidence, "
                "granularity_level, source_atlas) "
                "VALUES (:id, 'BLA', 'infralimbic cortex', 'projection', 0.2, 'macro', 'AAL3')"
            ),
            {"id": cid},
        )
        await s.commit()
    return cid


async def _attach(cid, *, direction="supports", note=None, level="direct", model_direction="supports", model_assessment="model says support", source=SOURCE):
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
                    "passage_text": source,
                    "text_hash": pes.passage_hash(source),
                    "locator": "abstract:paragraph:0",
                }
            ],
        )
        await s.commit()
        with (
            patch.object(pes, "verify_paper", new=AsyncMock(return_value=PAPER)),
            patch.object(pes, "_load_source", new=AsyncMock(return_value=(source, "abstract"))),
        ):
            result = await pes.attach_evidence(
                s,
                target_type="connection",
                target_id=cid,
                pmid="99080001",
                direction=direction,
                evidence_level=level,
                model_direction=model_direction,
                model_assessment=model_assessment,
                reviewer_note=note,
                reviewer_confidence=0.78,
                passages=[{
                    "source_scope": "abstract",
                    "passage": source,
                    "direction": "supports",
                    "reason": "r",
                    "confidence": 0.85,
                    "source_verified": True,
                    "supported_components": ["source_region", "target_region", "relation"],
                }],
                operator_id="reviewer-1",
            )
            await s.commit()
            return result, paper.id


async def _cleanup(cid, paper_id):
    async with AsyncSessionLocal() as s:
        await s.execute(
            text("DELETE FROM mirror_evidence_records WHERE evidence_target_id=:oid AND evidence_type='paper_verification'"),
            {"oid": cid},
        )
        await s.execute(text("DELETE FROM evidence_validation_records WHERE target_id=:oid"), {"oid": cid})
        await s.execute(text("DELETE FROM confidence_adjustment_logs WHERE target_id=:oid"), {"oid": cid})
        await s.execute(text("DELETE FROM ontology_change_logs WHERE entity_id=:oid"), {"oid": cid})
        await s.execute(text("DELETE FROM paper_sources WHERE id=:pid"), {"pid": paper_id})
        await s.execute(text("DELETE FROM mirror_region_connections WHERE id=:cid"), {"cid": cid})
        await s.commit()


def test_claim_and_coverage_snapshot_attached():
    cid = _run(_insert_connection())
    try:
        result, paper_id = _run(_attach(cid))
        eid = uuid.UUID(result["evidence_id"])

        async def check():
            async with AsyncSessionLocal() as s:
                row = (
                    await s.execute(
                        text(
                            "SELECT claim_version, claim_text_snapshot, claim_components_snapshot, "
                            "coverage_summary_snapshot, coverage_formula_version, evidence_level, "
                            "model_direction, model_assessment, reviewer_note "
                            "FROM mirror_evidence_records WHERE id=:eid"
                        ),
                        {"eid": eid},
                    )
                ).first()
                assert row[0] == "claim_v1"
                assert "BLA" in (row[1] or "")
                comps = row[2]
                assert {c["component_type"] for c in comps} >= {"source_region", "target_region", "relation"}
                cov = row[3]
                assert cov["full_claim_supported"] is True
                assert cov["overall_direction"] == "supports"
                assert cov["coverage_ratio"] == 1.0
                assert set(cov["supported_components"]) >= {"source_region", "target_region", "relation"}
                assert row[4] == "paper_evidence_coverage_v1"
                assert row[5] == "direct"
                assert row[6] == "supports"
                assert row[7] == "model says support"
                # passage-level evidence_level independent from record-level
                p_level = (
                    await s.execute(
                        text(
                            "SELECT evidence_level, supported_components FROM mirror_evidence_passages "
                            "WHERE evidence_id=:eid AND is_selected"
                        ),
                        {"eid": eid},
                    )
                ).first()
                assert p_level[0] == "indirect"  # passage default (not the record-level direct)
                assert len(p_level[1]) == 3
        _run(check())
    finally:
        # paper_id may not exist if attach failed; cleanup defensively
        async def cleanup():
            try:
                async with AsyncSessionLocal() as s:
                    await s.execute(text("DELETE FROM paper_sources WHERE pmid='99080001'"))
                    await s.commit()
            except Exception:
                pass
        _run(cleanup())
        _run(_cleanup(cid, uuid.uuid4()))


def test_override_without_note_auto_generates_note():
    """S8:生产行为已改为方向与覆盖不一致且无备注时自动生成备注(不再拒绝)。"""
    cid = _run(_insert_connection())
    try:
        # coverage=support but reviewer=contradicts without note -> 自动生成备注并记录
        result, paper_id = _run(_attach(cid, direction="contradicts", note=None))
        eid = uuid.UUID(result["evidence_id"])

        async def check_auto():
            async with AsyncSessionLocal() as s:
                row = (
                    await s.execute(
                        text(
                            "SELECT reviewer_note, evidence_direction FROM mirror_evidence_records WHERE id=:eid"
                        ),
                        {"eid": eid},
                    )
                ).first()
                assert row[1] == "contradicts"
                assert row[0] and "人工判定为 contradicts" in row[0]

        _run(check_auto())
        # with note -> accepted and recorded(换一段原文避免去重)
        result2, paper_id2 = _run(_attach(
            cid,
            direction="contradicts",
            note="human disagrees with coverage",
            source=SOURCE + "\n\nA follow-up control experiment confirmed the same pattern.",
        ))
        result, paper_id = result2, paper_id2
        eid = uuid.UUID(result["evidence_id"])

        async def check():
            async with AsyncSessionLocal() as s:
                row = (
                    await s.execute(
                        text(
                            "SELECT coverage_summary_snapshot, evidence_direction, reviewer_note "
                            "FROM mirror_evidence_records WHERE id=:eid"
                        ),
                        {"eid": eid},
                    )
                ).first()
                assert row[0]["overall_direction"] == "supports"
                assert row[1] == "contradicts"
                assert row[2] == "human disagrees with coverage"
                audit = (
                    await s.execute(
                        text(
                            "SELECT after_data, reason FROM ontology_change_logs "
                            "WHERE action_type='EVIDENCE_ATTACH' AND entity_id=:eid"
                        ),
                        {"eid": eid},
                    )
                ).first()
                assert audit is not None
                assert audit[0].get("override") is True
                assert "override reason" in (audit[1] or "")
        _run(check())
    finally:
        async def cleanup():
            try:
                async with AsyncSessionLocal() as s:
                    await s.execute(text("DELETE FROM paper_sources WHERE pmid='99080001'"))
                    await s.commit()
            except Exception:
                pass
        _run(cleanup())
        _run(_cleanup(cid, uuid.uuid4()))


def test_snapshot_survives_target_change_and_rollback():
    cid = _run(_insert_connection())
    try:
        result, paper_id = _run(_attach(cid))
        eid = uuid.UUID(result["evidence_id"])

        async def mutate_and_rollback():
            async with AsyncSessionLocal() as s:
                # mutate target name: latest DTO would differ, snapshot must not change
                await s.execute(
                    text("UPDATE mirror_region_connections SET source_region_name_en='Renamed BLA' WHERE id=:cid"),
                    {"cid": cid},
                )
                await s.commit()
                before = (
                    await s.execute(
                        text("SELECT claim_text_snapshot, claim_components_snapshot, coverage_summary_snapshot FROM mirror_evidence_records WHERE id=:eid"),
                        {"eid": eid},
                    )
                ).first()
                rb = await pes.rollback_evidence(s, eid, reason="snapshot test", operator_id="reviewer-1")
                await s.commit()
                after = (
                    await s.execute(
                        text(
                            "SELECT claim_text_snapshot, claim_components_snapshot, coverage_summary_snapshot, "
                            "model_direction, evidence_direction, reviewer_note, verification_status "
                            "FROM mirror_evidence_records WHERE id=:eid"
                        ),
                        {"eid": eid},
                    )
                ).first()
                assert before[0] == after[0]
                assert before[1] == after[1]
                assert before[2] == after[2]
                assert after[3] == "supports"
                assert after[4] == "supports"
                assert after[6] == "invalidated"
                assert rb["status"] == "invalidated"
        _run(mutate_and_rollback())
    finally:
        async def cleanup():
            try:
                async with AsyncSessionLocal() as s:
                    await s.execute(text("DELETE FROM paper_sources WHERE pmid='99080001'"))
                    await s.commit()
            except Exception:
                pass
        _run(cleanup())
        _run(_cleanup(cid, uuid.uuid4()))


def test_model_support_reviewer_partial_is_preserved():
    cid = _run(_insert_connection())
    try:
        result, paper_id = _run(_attach(cid, direction="partial", note="weaker than model"))
        eid = uuid.UUID(result["evidence_id"])

        async def check():
            async with AsyncSessionLocal() as s:
                row = (
                    await s.execute(
                        text("SELECT model_direction, evidence_direction FROM mirror_evidence_records WHERE id=:eid"),
                        {"eid": eid},
                    )
                ).first()
                assert row[0] == "supports"  # model judgment preserved
                assert row[1] == "partial"   # reviewer final preserved
        _run(check())
    finally:
        async def cleanup():
            try:
                async with AsyncSessionLocal() as s:
                    await s.execute(text("DELETE FROM paper_sources WHERE pmid='99080001'"))
                    await s.commit()
            except Exception:
                pass
        _run(cleanup())
        _run(_cleanup(cid, uuid.uuid4()))


def test_mixed_coverage_to_reviewer_support_requires_note():
    async def attach_mixed(cid, note=None, source=MIXED_SOURCE, contradicts_text="Activation of BLA terminals did not alter extinction learning."):
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
                        "passage_text": source,
                        "text_hash": pes.passage_hash(source),
                        "locator": "abstract:paragraph:0",
                    }
                ],
            )
            await s.commit()
            with (
                patch.object(pes, "verify_paper", new=AsyncMock(return_value=PAPER)),
                patch.object(pes, "_load_source", new=AsyncMock(return_value=(source, "abstract"))),
            ):
                result = await pes.attach_evidence(
                    s,
                    target_type="connection",
                    target_id=cid,
                    pmid="99080001",
                    direction="supports",
                    evidence_level="direct",
                    model_direction="mixed",
                    model_assessment="model saw conflict",
                    reviewer_note=note,
                    reviewer_confidence=0.7,
                    passages=[
                        {
                            "source_scope": "abstract",
                            "passage": source,
                            "direction": "supports",
                            "reason": "support",
                            "confidence": 0.85,
                            "source_verified": True,
                            "supported_components": ["source_region", "target_region", "relation", "direction"],
                        },
                        {
                            "source_scope": "abstract",
                            "passage": contradicts_text,
                            "direction": "contradicts",
                            "reason": "deny",
                            "confidence": 0.6,
                            "source_verified": True,
                            "supported_components": ["source_region", "target_region", "relation", "direction"],
                        },
                    ],
                    operator_id="reviewer-1",
                )
                await s.commit()
                return result

    cid = _run(_insert_connection())
    try:
        async def setup_paper():
            async with AsyncSessionLocal() as s:
                paper = await pes.ensure_paper_source(s, {**PAPER, "abstract": SOURCE, "fulltext": ""})
                await s.commit()
                await s.execute(
                    text(
                        "UPDATE paper_passages SET passage_text=:txt, text_hash=:h "
                        "WHERE paper_id=:pid AND paragraph_id='abstract_p001'"
                    ),
                    {
                        "pid": paper.id,
                        "txt": MIXED_SOURCE,
                        "h": pes.passage_hash(MIXED_SOURCE),
                    },
                )
                await s.commit()
                return paper.id

        paper_id = _run(setup_paper())
        # S8:生产行为已改为自动生成备注(不再拒绝)
        auto_result = _run(attach_mixed(cid, note=None))
        assert auto_result.get("evidence_id")
        result = _run(attach_mixed(cid, note="reviewer overrides model conflict", source=MIXED_SOURCE + "\n\nAn additional independent replication confirmed this.", contradicts_text="An additional independent replication confirmed this."))
        eid = uuid.UUID(result["evidence_id"])

        async def check():
            async with AsyncSessionLocal() as s:
                row = (
                    await s.execute(
                        text("SELECT coverage_summary_snapshot, evidence_direction FROM mirror_evidence_records WHERE id=:eid"),
                        {"eid": eid},
                    )
                ).first()
                assert row[0]["has_conflict"] is True
                assert row[0]["overall_direction"] == "mixed"
                assert row[1] == "supports"
        _run(check())
    finally:
        async def cleanup():
            try:
                async with AsyncSessionLocal() as s:
                    await s.execute(text("DELETE FROM paper_sources WHERE pmid='99080001'"))
                    await s.commit()
            except Exception:
                pass
        _run(cleanup())
        _run(_cleanup(cid, uuid.uuid4()))
