"""Phase C: batch pre-processing state machine, review queue, stats, audit."""

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


def _ids(n: int = 3):
    return [str(uuid.uuid4()) for _ in range(n)]


def _paper(pmid="10001"):
    return {
        "pmid": pmid,
        "doi": "10.1/x",
        "title": "Batch paper",
        "journal": "J Neuro",
        "year": "2026",
        "authors": "A B",
        "abstract": "The hippocampus supports memory consolidation.",
        "is_open_access": False,
        "source": "europepmc",
    }


def _extraction():
    return {
        "overall_direction": "supports",
        "paper_relevance": 0.9,
        "assessment": "relevant",
        "source_type": "abstract",
        "passages": [
            {
                "source_scope": "abstract",
                "section_title": None,
                "paragraph_index": 0,
                "passage": "The hippocampus supports memory consolidation.",
                "direction": "supports",
                "reason": "explicit",
                "confidence": 0.82,
                "source_locator": "abstract:0",
                "source_verified": True,
                "passage_hash": pes.passage_hash("The hippocampus supports memory consolidation."),
            }
        ],
        "parse_status": "ok",
        "retry_count": 0,
        "raw_response": '{"overall_direction":"supports"}',
    }


async def _cleanup(task_ids, evidence_ids=(), record_ids=(), audit_ids=()):
    async with AsyncSessionLocal() as s:
        for tid in task_ids:
            await s.execute(text("DELETE FROM paper_evidence_tasks WHERE id::text=:tid"), {"tid": tid})
        for eid in evidence_ids:
            await s.execute(text("DELETE FROM mirror_evidence_records WHERE id=:eid"), {"eid": eid})
        for rid in record_ids:
            await s.execute(text("DELETE FROM evidence_validation_records WHERE id=:rid"), {"rid": rid})
        for aid in audit_ids:
            await s.execute(text("DELETE FROM ontology_change_logs WHERE id=:aid"), {"aid": aid})
        await s.commit()


class TestBatchStateMachine:
    def _make_task(self, target_ids=None, start_paused=False):
        target_ids = target_ids or _ids(3)
        with (
            patch.object(pes, "_resolve_scope_ids", new=AsyncMock(return_value=target_ids)),
            patch.object(pes, "_resolve_scope_ids_low_confidence", new=AsyncMock(return_value=target_ids)),
            patch.object(
                pes,
                "_batch_scope_label",
                new=AsyncMock(side_effect=lambda s, tt, oid: (f"target-{oid}", 0.4)),
            ),
        ):
            return _run(_make_task_inner(target_ids=target_ids, start_paused=start_paused))

    def test_create_task_creates_one_task_per_object_with_labels(self):
        ids = _ids(2)
        result = self._make_task(ids)
        task_ids = result["task_ids"]
        try:
            assert len(task_ids) == 2
            assert result["target_count"] == 2
            assert result["task_id"] == task_ids[0]
            for tid in task_ids:
                row = _run(_read_task_row(tid))
                assert row[0] == "pending"
                assert row[1] == 1  # total_items = 1
                items = _run(_read_task_items(tid))
                assert len(items) == 1
                assert items[0][1] == "pending"
                assert items[0][0].startswith("target-")
        finally:
            _run(_cleanup(task_ids))

    def test_batch_loop_preprocesses_to_awaiting_review_without_formal_attach(self):
        ids = _ids(2)
        result = self._make_task(ids)
        task_ids = result["task_ids"]
        try:
            with (
                patch.object(pes, "pack_target_info", new=AsyncMock(return_value={
                    "function_term": "memory consolidation",
                    "query": '"memory consolidation"',
                    "info": {},
                })),
                patch.object(pes, "build_retrieval_context", new=AsyncMock(return_value={
                    "claim_text": "memory consolidation",
                    "structured_claim": {},
                    "object_type": "connection",
                    "granularity": "macro",
                    "source_region": "Hippocampus",
                    "target_region": "Prefrontal cortex",
                    "source_region_synonyms": [],
                    "target_region_synonyms": [],
                    "function_terms": ["memory consolidation"],
                    "function_synonyms": [],
                    "relation_keywords": ["projection"],
                })),
                patch.object(pes, "search_papers", new=AsyncMock(return_value=[_paper()])),
                patch.object(pes, "fetch_fulltext", new=AsyncMock(return_value="")),
                patch.object(pes, "verify_paper", new=AsyncMock(return_value=_paper())),
                patch.object(pes.pfs, "fetch_oa_fulltext_xml", new=AsyncMock(return_value="")),
                patch.object(pes, "build_search_query", new=AsyncMock(return_value='"memory consolidation"')),
                patch.object(pes, "extract_passage_from_paper", new=AsyncMock(return_value=_extraction())),
                patch.object(pes, "semantic_filter_papers", new=AsyncMock(side_effect=lambda papers, ctx: (papers, []))),
            ):
                for tid in task_ids:
                    _run(_run_loop(tid))
            for tid in task_ids:
                task = _run(_read_task_row(tid))
                assert task[0] == "completed"
                assert task[1] == 1
                assert task[2] == 1
                items = _run(_read_task_items(tid))
                assert all(i[1] == "awaiting_review" for i in items)
                assert all(i[2] and i[3] and i[4] for i in items)
            ev_count = _run(_count_evidence(ids))
            assert ev_count == 0
        finally:
            _run(_cleanup(task_ids))
            _run(_cleanup_batch_paper())

    def test_pause_resume_cancel(self):
        result = self._make_task(_ids(1))
        task_id = result["task_id"]
        try:
            _run(_pause(task_id))
            assert _run(_read_status(task_id)) == "paused"
            _run(_resume(task_id))
            assert _run(_read_status(task_id)) == "pending"
            _run(_cancel(task_id))
            assert _run(_read_status(task_id)) == "cancelled"
            assert _run(_count_skipped(task_id)) == 1
        finally:
            _run(_cleanup([task_id]))

    def test_failed_item_retry_and_unique_active_target(self):
        ids = _ids(1)
        result = self._make_task(ids)
        task_id = result["task_id"]
        try:
            _run(_fail_item(task_id))
            retried = _run(_retry(task_id))
            assert retried["retried"] == 1
            assert _run(_read_status(task_id)) == "pending"
            # same target cannot be enqueued again while active
            with pytest.raises(ValueError, match="already have an active evidence task"):
                self._make_task(ids)
        finally:
            _run(_cleanup([task_id]))

    def test_non_neural_target_marked_without_search(self):
        oid = str(uuid.uuid4())
        # 靶标名含「脑室」→ 创建即标记结构性不存在
        with (
            patch.object(pes, "_resolve_scope_ids", new=AsyncMock(return_value=[oid])),
            patch.object(pes, "_resolve_scope_ids_low_confidence", new=AsyncMock(return_value=[oid])),
            patch.object(
                pes,
                "_batch_scope_label",
                new=AsyncMock(side_effect=lambda s, tt, o: (f"X → 侧脑室", 0.1)),
            ),
            patch.object(pes, "_classify_item_target", new=AsyncMock(return_value="non_neural")),
        ):
            result = _run(_make_task_inner(target_ids=[oid], start_paused=True))
        task_id = result["task_id"]
        try:
            items = _run(_read_task_items(task_id))
            assert len(items) == 1
            assert items[0][0].startswith("X → 侧脑室")
            # 标记结构性不存在
            outcome = _run(_read_item_outcome(task_id))
            assert outcome == "non_neural_target"
        finally:
            _run(_cleanup([task_id]))


class TestReviewQueueStatsAudit:
    def test_review_queue_resolve_and_stats_shape(self):
        target_id = uuid.uuid4()
        record_ids = []
        evidence_ids = []
        audit_ids = []
        try:
            ev = _run(_insert_evidence(target_id))
            evidence_ids.append(ev)
            _run(_insert_validation(ev, target_id))
            rid = _run(_find_validation_id(ev))
            record_ids.append(rid)
            queue = _run(_list_queue())
            assert queue["total"] >= 1
            assert any(r["rule_code"] == "EV_PAPER_EVIDENCE_ATTACHED" for r in queue["items"])
            _run(_resolve_record(rid))
            stats = _run(_stats())
            assert "objects_with_evidence" in stats
            assert "directions" in stats
            assert "avg_confidence_delta" in stats
            _run(_write_audit(target_id))
            audit_rows = _run(_find_audit(target_id))
            assert audit_rows
            audit_ids.extend(audit_rows)
        finally:
            _run(_cleanup([], evidence_ids, record_ids, audit_ids))


# ── async helpers (kept at module level for clarity) ────────────────────────

async def _make_task_inner(*, target_ids, start_paused):
    async with AsyncSessionLocal() as session:
        return await pes.create_batch_task(
            session,
            target_type="connection",
            mode="function",
            max_papers_per_object=3,
            created_by="test",
            limit=20,
            start_paused=start_paused,
            target_ids=target_ids,
            scope="selected",
        )


async def _read_task_row(task_id):
    async with AsyncSessionLocal() as s:
        return (
            await s.execute(
                text(
                    "SELECT status, total_items, awaiting_review_items, processed_items "
                    "FROM paper_evidence_tasks WHERE id::text=:tid"
                ),
                {"tid": task_id},
            )
        ).first()


async def _read_task_items(task_id):
    async with AsyncSessionLocal() as s:
        return (
            await s.execute(
                text(
                    "SELECT label, status, candidate_papers IS NOT NULL, "
                    "EXISTS(SELECT 1 FROM paper_evidence_task_item_passages pp WHERE pp.task_item_id = t.id), "
                    "claim_text_snapshot IS NOT NULL "
                    "FROM paper_evidence_task_items t WHERE task_id::text=:tid"
                ),
                {"tid": task_id},
            )
        ).all()


async def _read_item_outcome(task_id):
    async with AsyncSessionLocal() as s:
        return (
            await s.execute(
                text("SELECT preprocess_outcome FROM paper_evidence_task_items WHERE task_id::text=:tid"),
                {"tid": task_id},
            )
        ).scalar_one()


async def _run_loop(task_id):
    async with AsyncSessionLocal() as s:
        await pes._run_batch_loop(s, task_id)


async def _count_evidence(ids):
    async with AsyncSessionLocal() as s:
        return (
            await s.execute(
                text(
                    "SELECT COUNT(*) FROM mirror_evidence_records "
                    "WHERE evidence_target_id::text = ANY(:ids) AND evidence_type='paper_verification'"
                ),
                {"ids": ids},
            )
        ).scalar_one()


async def _pause(task_id):
    async with AsyncSessionLocal() as s:
        await pes.pause_batch_task(s, task_id)


async def _resume(task_id):
    async with AsyncSessionLocal() as s:
        await pes.resume_batch_task(s, task_id)


async def _cancel(task_id):
    async with AsyncSessionLocal() as s:
        await pes.cancel_batch_task(s, task_id)


async def _read_status(task_id):
    async with AsyncSessionLocal() as s:
        return (
            await s.execute(text("SELECT status FROM paper_evidence_tasks WHERE id::text=:tid"), {"tid": task_id})
        ).scalar_one()


async def _count_skipped(task_id):
    async with AsyncSessionLocal() as s:
        return (
            await s.execute(
                text(
                    "SELECT COUNT(*) FROM paper_evidence_task_items "
                    "WHERE task_id::text=:tid AND status='skipped'"
                ),
                {"tid": task_id},
            )
        ).scalar_one()


async def _fail_item(task_id):
    async with AsyncSessionLocal() as s:
        await s.execute(
            text(
                "UPDATE paper_evidence_task_items SET status='failed', last_error='boom' "
                "WHERE task_id::text=:tid"
            ),
            {"tid": task_id},
        )
        await s.commit()


async def _retry(task_id):
    async with AsyncSessionLocal() as s:
        return await pes.retry_failed_batch_items(s, task_id)


async def _insert_evidence(target_id):
    async with AsyncSessionLocal() as s:
        await s.execute(
            text(
                "INSERT INTO mirror_evidence_records "
                "(evidence_target_type, evidence_target_id, evidence_type, verification_status, evidence_direction, evidence_text) "
                "VALUES ('connection', :oid, 'paper_verification', 'human_verified', 'supports', '')"
            ),
            {"oid": target_id},
        )
        await s.commit()
        return (
            await s.execute(
                text(
                    "SELECT id FROM mirror_evidence_records "
                    "WHERE evidence_target_id=:oid AND evidence_type='paper_verification'"
                ),
                {"oid": target_id},
            )
        ).scalar_one()


async def _insert_validation(ev, target_id):
    async with AsyncSessionLocal() as s:
        await pes._write_validation_record(
            s,
            evidence_id=ev,
            rule_code="EV_PAPER_EVIDENCE_ATTACHED",
            target_type="connection",
            target_id=target_id,
            direction="supports",
            paper_snapshot={"pmid": "1", "title": "t"},
        )
        await s.commit()


async def _find_validation_id(ev):
    async with AsyncSessionLocal() as s:
        return (
            await s.execute(text("SELECT id FROM evidence_validation_records WHERE evidence_id=:eid"), {"eid": ev})
        ).scalar_one()


async def _list_queue():
    async with AsyncSessionLocal() as s:
        return await pes.list_evidence_review_queue(s, status="pending")


async def _resolve_record(rid):
    async with AsyncSessionLocal() as s:
        await pes.resolve_evidence_review_record(s, rid, note="ok")


async def _stats():
    async with AsyncSessionLocal() as s:
        return await pes.paper_evidence_stats(s, target_types=["connection"])


async def _write_audit(target_id):
    async with AsyncSessionLocal() as s:
        await pes.write_evidence_audit_event(
            s,
            action_type="EVIDENCE_DIRECTION_EDIT",
            entity_type="evidence",
            entity_id=target_id,
            after_data={"direction": "partial"},
            reason="manual",
        )


async def _find_audit(target_id):
    async with AsyncSessionLocal() as s:
        return (
            await s.execute(
                text(
                    "SELECT id FROM ontology_change_logs "
                    "WHERE action_type='EVIDENCE_DIRECTION_EDIT' AND entity_id=:oid"
                ),
                {"oid": target_id},
            )
        ).scalars().all()


async def _cleanup_batch_paper():
    async with AsyncSessionLocal() as s:
        await s.execute(
            text("DELETE FROM paper_passages WHERE paper_id IN (SELECT id FROM paper_sources WHERE pmid='10001')")
        )
        await s.execute(text("DELETE FROM paper_sources WHERE pmid='10001'"))
        await s.commit()
