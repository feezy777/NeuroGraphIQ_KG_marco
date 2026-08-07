"""Phase 4 closure: scale materialization, concurrency, versions, draft revision."""

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


async def _insert_connections(n=6, confidence=0.0001):
    cids = []
    async with AsyncSessionLocal() as s:
        for i in range(n):
            cid = uuid.uuid4()
            await s.execute(
                text(
                    "INSERT INTO mirror_region_connections "
                    "(id, source_region_name_en, target_region_name_en, connection_type, confidence, "
                    "granularity_level, source_atlas) "
                    "VALUES (:id, 'R', 'T', 'projection', :conf, 'macro', 'AAL3')"
                ),
                {"id": cid, "conf": confidence},
            )
            cids.append(str(cid))
        await s.commit()
    return cids


async def _cleanup_connections(cids):
    async with AsyncSessionLocal() as s:
        await s.execute(
            text("DELETE FROM mirror_region_connections WHERE id::text = ANY(:ids)"),
            {"ids": cids},
        )
        await s.commit()


def test_filter_snapshot_and_preview_and_max_limit():
    async def case():
        async with AsyncSessionLocal() as s:
            preview = await pes.preview_batch_scope(
                s, target_type="connection", filter_snapshot={"confidence_lt": 0.5}
            )
            assert preview["estimated_target_count"] >= 0
            assert "max_task_items" in preview
            cfg = pes.get_settings()
            old = cfg.paper_evidence_max_task_items
            cfg.paper_evidence_max_task_items = 3
            try:
                with pytest.raises(ValueError, match="单任务最大"):
                    await pes.create_batch_task(
                        s, target_type="connection", scope="low_confidence", mode="function",
                        max_papers_per_object=3, confidence_lt=0.5, limit=200,
                        filter_snapshot={"confidence_lt": 0.5},
                    )
            finally:
                cfg.paper_evidence_max_task_items = old
    _run(case())


def test_large_scope_materialization_checkpoint_and_idempotency():
    cids = _run(_insert_connections(6))
    try:
        async def case():
            cfg = pes.get_settings()
            old = cfg.paper_evidence_max_task_items
            cfg.paper_evidence_max_task_items = 100000
            async with AsyncSessionLocal() as s:
                task = await pes.create_batch_task(
                    s, target_type="connection", scope="low_confidence", mode="function",
                    max_papers_per_object=3, confidence_lt=0.5, limit=200,
                    filter_snapshot={"confidence_lt": 0.001},
                )
                task_id = task["task_id"]
            try:
                await pes.materialize_task_items_background(task_id)
                # idempotent re-materialize after simulated restart (checkpoint continues, no dupes)
                async with AsyncSessionLocal() as s:
                    await s.execute(
                        text("UPDATE paper_evidence_tasks SET materialization_status='running' WHERE id::text=:tid"),
                        {"tid": task_id},
                    )
                    await s.commit()
                await pes.materialize_task_items_background(task_id)
                async with AsyncSessionLocal() as s:
                    row = (
                        await s.execute(
                            text(
                                "SELECT materialization_status, materialized_target_count, total_items "
                                "FROM paper_evidence_tasks WHERE id::text=:tid"
                            ),
                            {"tid": task_id},
                        )
                    ).first()
                    assert row[0] == "completed"
                    assert row[1] >= 6
                    count = (
                        await s.execute(
                            text("SELECT COUNT(*) FROM paper_evidence_task_items WHERE task_id::text=:tid"),
                            {"tid": task_id},
                        )
                    ).scalar_one()
                    assert count == row[1]  # every materialized target has exactly one item
                    snap = (
                        await s.execute(
                            text("SELECT scope_type, filter_snapshot FROM paper_evidence_tasks WHERE id::text=:tid"),
                            {"tid": task_id},
                        )
                    ).first()
                    assert snap[0] == "filter"
                    assert snap[1].get("confidence_lt") == 0.001
                    await s.execute(text("DELETE FROM paper_evidence_tasks WHERE id::text=:tid"), {"tid": task_id})
                    await s.commit()
            finally:
                cfg.paper_evidence_max_task_items = old
        _run(case())
    finally:
        _run(_cleanup_connections(cids))


def test_materialization_cancel_stops_and_keeps_generated():
    cids = _run(_insert_connections(4))
    try:
        async def case():
            cfg = pes.get_settings()
            old = cfg.paper_evidence_max_task_items
            cfg.paper_evidence_max_task_items = 100000
            async with AsyncSessionLocal() as s:
                task = await pes.create_batch_task(
                    s, target_type="connection", scope="low_confidence", mode="function",
                    max_papers_per_object=3, confidence_lt=0.5, limit=200,
                    filter_snapshot={"confidence_lt": 0.001},
                )
                task_id = task["task_id"]
            try:
                await pes.cancel_batch_task(s, task_id)
                await pes.materialize_task_items_background(task_id)
                async with AsyncSessionLocal() as s:
                    st = (
                        await s.execute(
                            text("SELECT materialization_status FROM paper_evidence_tasks WHERE id::text=:tid"),
                            {"tid": task_id},
                        )
                    ).first()
                    assert st[0] == "cancelled"
                    await s.execute(text("DELETE FROM paper_evidence_tasks WHERE id::text=:tid"), {"tid": task_id})
                    await s.commit()
            finally:
                cfg.paper_evidence_max_task_items = old
        _run(case())
    finally:
        _run(_cleanup_connections(cids))


def test_versions_written_on_items():
    ids = [str(uuid.uuid4())]
    extraction = {
        "overall_direction": "supports", "paper_relevance": 0.9, "assessment": "a",
        "source_type": "abstract", "llm_model": "deepseek-v4-flash-test",
        "passages": [{
            "source_scope": "abstract", "paragraph_id": "abstract_p001",
            "passage": "BLA terminals in the infralimbic cortex facilitated fear extinction.",
            "direction": "supports", "evidence_level": "direct", "reason": "r",
            "confidence": 0.9, "semantic_confidence": 0.9, "source_verified": True,
            "source_verification_method": "exact", "supported_components": ["source_region", "target_region", "relation"],
        }], "parse_status": "ok", "retry_count": 0, "raw_response": "{}",
    }
    context = {
        "claim_text": "c", "structured_claim": {}, "object_type": "connection", "granularity": "macro",
        "source_region": "BLA", "target_region": "infralimbic cortex", "source_region_synonyms": [],
        "target_region_synonyms": [], "function_terms": ["fear extinction"], "function_synonyms": [],
        "relation_keywords": ["terminal"], "claim_components": [
            {"component_type": "source_region", "statement": "BLA", "required": True, "metadata": {}},
            {"component_type": "target_region", "statement": "IL", "required": True, "metadata": {}},
            {"component_type": "relation", "statement": "projection", "required": True, "metadata": {}},
        ], "claim_version": "claim_v1",
    }
    async def case():
        async with AsyncSessionLocal() as s:
            task = await pes.create_batch_task(
                s, target_type="connection", scope="selected", mode="function",
                max_papers_per_object=3, target_ids=ids,
            )
            task_id = task["task_id"]
            for oid in ids:
                await s.execute(
                    text(
                        "INSERT INTO paper_evidence_task_items (task_id, target_type, target_id, label, status) "
                        "SELECT :tid, 'connection', :oid, :lbl, 'pending' "
                        "WHERE NOT EXISTS (SELECT 1 FROM paper_evidence_task_items a "
                        "WHERE a.target_type='connection' AND a.target_id=:oid AND a.status NOT IN "
                        "('completed','skipped','failed','cancelled')) "
                        "ON CONFLICT (task_id,target_type,target_id) DO NOTHING"
                    ),
                    {"tid": task_id, "oid": uuid.UUID(oid), "lbl": "t"},
                )
            await s.commit()
        with (
            patch.object(pes, "build_retrieval_context", new=AsyncMock(return_value=context)),
            patch.object(pes, "build_search_query", new=AsyncMock(return_value="q")),
            patch.object(pes, "search_papers", new=AsyncMock(return_value=[{
                "pmid": "99090005", "title": "p", "abstract": extraction["passages"][0]["passage"],
                "is_open_access": True,
            }])),
            patch.object(pes, "verify_paper", new=AsyncMock(return_value={
                "pmid": "99090005", "title": "p", "abstract": extraction["passages"][0]["passage"],
                "journal": "J", "year": "2026", "authors": "A", "is_open_access": True, "source": "europepmc",
            })),
            patch.object(pes.pfs, "fetch_oa_fulltext_xml", new=AsyncMock(return_value="")),
            patch.object(pes, "extract_passage_from_paper", new=AsyncMock(return_value=extraction)),
        ):
            async with AsyncSessionLocal() as s:
                await pes._run_batch_loop(s, task_id)
        async with AsyncSessionLocal() as s:
            row = (
                await s.execute(
                    text(
                        "SELECT preprocessing_version, retrieval_version, prompt_version, llm_model, "
                        "preprocess_outcome FROM paper_evidence_task_items WHERE task_id::text=:tid"
                    ),
                    {"tid": task_id},
                )
            ).first()
            assert row[0] == "paper_evidence_preprocess_v1"
            assert row[1] == "paper_passage_retrieval_v1"
            assert row[2] == "paper_evidence_extract_v2"
            assert row[3] == "deepseek-v4-flash-test"
            assert row[4] == "evidence_found"
            await s.execute(text("DELETE FROM paper_evidence_tasks WHERE id::text=:tid"), {"tid": task_id})
            await s.commit()
    _run(case())


def test_draft_revision_optimistic_concurrency():
    ids = [str(uuid.uuid4())]
    async def case():
        async with AsyncSessionLocal() as s:
            task = await pes.create_batch_task(
                s, target_type="connection", scope="selected", mode="function",
                max_papers_per_object=3, target_ids=ids,
            )
            task_id = task["task_id"]
            await s.execute(
                text(
                    "INSERT INTO paper_evidence_task_items (task_id, target_type, target_id, label, status) "
                    "SELECT :tid, 'connection', :oid, 't', 'awaiting_review' "
                    "ON CONFLICT (task_id,target_type,target_id) DO NOTHING"
                ),
                {"tid": task_id, "oid": uuid.UUID(ids[0])},
            )
            await s.commit()
            item_id = (
                await s.execute(
                    text("SELECT id::text FROM paper_evidence_task_items WHERE task_id::text=:tid"),
                    {"tid": task_id},
                )
            ).scalar_one()
            # newer revision first
            r2 = await pes.save_task_item_draft(s, item_id, {"note": "newer"}, revision=2)
            assert r2["server_revision"] == 2
            # stale revision rejected
            with pytest.raises(ValueError, match="stale draft revision"):
                await pes.save_task_item_draft(s, item_id, {"note": "older"}, revision=1)
            loaded = await pes.get_task_item_draft(s, item_id)
            assert loaded["review_draft"]["note"] == "newer"
            await s.execute(text("DELETE FROM paper_evidence_tasks WHERE id::text=:tid"), {"tid": task_id})
            await s.commit()
    _run(case())


def test_dual_worker_skip_locked_no_overlap():
    n = 20
    ids = [str(uuid.uuid4()) for _ in range(n)]

    async def case():
        async with AsyncSessionLocal() as s:
            task = await pes.create_batch_task(
                s, target_type="connection", scope="selected", mode="function",
                max_papers_per_object=3, target_ids=ids,
            )
            task_id = task["task_id"]
            for oid in ids:
                await s.execute(
                    text(
                        "INSERT INTO paper_evidence_task_items (task_id, target_type, target_id, label, status) "
                        "SELECT :tid, 'connection', :oid, 't', 'pending' "
                        "ON CONFLICT (task_id,target_type,target_id) DO NOTHING"
                    ),
                    {"tid": task_id, "oid": uuid.UUID(oid)},
                )
            await s.commit()

        async def worker_claim(limit=10):
            claimed: list[str] = []
            for _ in range(limit):
                async with AsyncSessionLocal() as ws:
                    rows = (
                        await ws.execute(
                            text(
                                "SELECT id::text FROM paper_evidence_task_items "
                                "WHERE task_id::text=:tid AND status='pending' "
                                "ORDER BY created_at LIMIT 1 FOR UPDATE SKIP LOCKED"
                            ),
                            {"tid": task_id},
                        )
                    ).all()
                    if not rows:
                        break
                    await ws.execute(
                        text("UPDATE paper_evidence_task_items SET status='searching' WHERE id::text=:iid"),
                        {"iid": rows[0][0]},
                    )
                    await ws.commit()
                    claimed.append(rows[0][0])
            return claimed

        w1, w2 = await asyncio.gather(worker_claim(10), worker_claim(10))
        assert set(w1).isdisjoint(set(w2))
        assert len(set(w1 + w2)) == n
        async with AsyncSessionLocal() as s:
            await s.execute(text("DELETE FROM paper_evidence_tasks WHERE id::text=:tid"), {"tid": task_id})
            await s.commit()
    _run(case())
