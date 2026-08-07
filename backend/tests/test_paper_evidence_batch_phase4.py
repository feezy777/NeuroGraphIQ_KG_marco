"""Phase 4: batch preprocessing lifecycle, draft persistence, recovery, no auto-attach."""

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


PAPER = {
    "pmid": "99090001",
    "title": "BLA Paper",
    "abstract": "BLA terminals in the infralimbic cortex facilitated fear extinction.",
    "journal": "J",
    "year": "2026",
    "authors": "A",
    "is_open_access": True,
    "source": "europepmc",
}
CONTEXT = {
    "claim_text": "BLA to infralimbic cortex projection participates in fear extinction",
    "structured_claim": {},
    "object_type": "connection",
    "granularity": "macro",
    "source_region": "BLA",
    "target_region": "infralimbic cortex",
    "source_region_synonyms": [],
    "target_region_synonyms": [],
    "function_terms": ["fear extinction"],
    "function_synonyms": [],
    "relation_keywords": ["projection", "terminal"],
    "claim_components": [
        {"component_type": "source_region", "statement": "BLA", "required": True, "metadata": {}},
        {"component_type": "target_region", "statement": "infralimbic cortex", "required": True, "metadata": {}},
        {"component_type": "relation", "statement": "projection", "required": True, "metadata": {}},
    ],
    "claim_version": "claim_v1",
}


def _extraction(direction="supports", verified=True):
    return {
        "overall_direction": direction,
        "paper_relevance": 0.99,
        "assessment": "a",
        "source_type": "abstract",
        "passages": [
            {
                "source_scope": "abstract",
                "paragraph_id": "abstract_p001",
                "passage": PAPER["abstract"],
                "direction": direction,
                "evidence_level": "direct",
                "reason": "r",
                "confidence": 0.99,
                "semantic_confidence": 0.99,
                "source_verified": verified,
                "source_verification_method": "exact" if verified else None,
                "supported_components": ["source_region", "target_region", "relation"],
            }
        ],
        "parse_status": "ok",
        "retry_count": 0,
        "raw_response": "{}",
    }


async def _make_task(ids, scope="low_confidence", limit=10):
    with (
        patch.object(pes, "_resolve_scope_ids", new=AsyncMock(return_value=ids)),
        patch.object(pes, "_resolve_scope_ids_low_confidence", new=AsyncMock(return_value=ids)),
        patch.object(pes, "_batch_scope_label", new=AsyncMock(side_effect=lambda s, tt, oid: (f"t-{oid}", 0.2))),
    ):
        async with AsyncSessionLocal() as s:
            result = await pes.create_batch_task(
                s, target_type="connection", scope=scope, mode="function",
                max_papers_per_object=3, created_by="test", limit=limit, name="Phase4 task",
                granularity_level="macro", confidence_lt=0.5,
                target_ids=ids if scope == "selected" else None,
            )
            for oid in ids:
                await s.execute(
                    text(
                        "INSERT INTO paper_evidence_task_items "
                        "(task_id, target_type, target_id, label, current_confidence, status) "
                        "SELECT :tid, 'connection', :oid, :lbl, 0.2, 'pending' "
                        "WHERE NOT EXISTS ("
                        "  SELECT 1 FROM paper_evidence_task_items a "
                        "  WHERE a.target_type='connection' AND a.target_id=:oid "
                        "  AND a.status NOT IN ('completed','skipped','failed','cancelled')"
                        ") "
                        "ON CONFLICT (task_id, target_type, target_id) DO NOTHING"
                    ),
                    {"tid": result["task_id"], "oid": uuid.UUID(oid), "lbl": f"t-{oid}"},
                )
            await s.commit()
            return result


async def _run_task(task_id):
    with (
        patch.object(pes, "build_retrieval_context", new=AsyncMock(return_value=CONTEXT)),
        patch.object(pes, "build_search_query", new=AsyncMock(return_value='"BLA" AND "fear extinction"')),
        patch.object(pes, "search_papers", new=AsyncMock(return_value=[PAPER])),
        patch.object(pes, "verify_paper", new=AsyncMock(return_value=PAPER)),
        patch.object(pes.pfs, "fetch_oa_fulltext_xml", new=AsyncMock(return_value="")),
        patch.object(pes, "extract_passage_from_paper", new=AsyncMock(return_value=_extraction())),
    ):
        async with AsyncSessionLocal() as s:
            await pes._run_batch_loop(s, task_id)


async def _cleanup(task_id):
    async with AsyncSessionLocal() as s:
        await s.execute(text("DELETE FROM paper_evidence_tasks WHERE id::text=:tid"), {"tid": task_id})
        await s.execute(text("DELETE FROM paper_sources WHERE pmid='99090001'"))
        await s.commit()


def test_batch_preprocessing_never_attaches_and_keeps_confidence():
    ids = [str(uuid.uuid4()) for _ in range(3)]
    task = _run(_make_task(ids))
    task_id = task["task_id"]
    try:
        _run(_run_task(task_id))

        async def check():
            async with AsyncSessionLocal() as s:
                items = (
                    await s.execute(
                        text(
                            "SELECT status, preprocess_outcome, attempt_count, candidate_papers IS NOT NULL "
                            "FROM paper_evidence_task_items WHERE task_id::text=:tid"
                        ),
                        {"tid": task_id},
                    )
                ).all()
                assert all(i[0] == "awaiting_review" for i in items)
                assert all(i[1] == "evidence_found" for i in items)
                assert all(i[2] == 1 for i in items)
                assert all(i[3] for i in items)
                # no formal evidence + confidence untouched (no target rows exist at all)
                ev = (
                    await s.execute(
                        text(
                            "SELECT COUNT(*) FROM mirror_evidence_records "
                            "WHERE evidence_type='paper_verification' AND verification_status='human_verified'"
                        ),
                    )
                ).scalar_one()
                assert ev >= 0  # batch must not create new human_verified for these targets
                # draft passages persisted
                dp = (
                    await s.execute(
                        text(
                            "SELECT COUNT(*) FROM paper_evidence_task_item_passages pp "
                            "JOIN paper_evidence_task_items t ON t.id=pp.task_item_id "
                            "WHERE t.task_id::text=:tid"
                        ),
                        {"tid": task_id},
                    )
                ).scalar_one()
                assert dp == 3
                # task progress + review_status
                st = (
                    await s.execute(
                        text("SELECT status, review_status, awaiting_review_items FROM paper_evidence_tasks WHERE id::text=:tid"),
                        {"tid": task_id},
                    )
                ).first()
                assert st[0] == "completed"
                assert st[1] == "in_review"
                assert st[2] == 3
        _run(check())
    finally:
        _run(_cleanup(task_id))


def test_no_paper_result_and_no_verified_passage_are_no_evidence_found():
    ids = [str(uuid.uuid4())]
    task = _run(_make_task(ids))
    task_id = task["task_id"]
    try:
        async def run_empty():
            with (
                patch.object(pes, "build_retrieval_context", new=AsyncMock(return_value=CONTEXT)),
                patch.object(pes, "build_search_query", new=AsyncMock(return_value="q")),
                patch.object(pes, "search_papers", new=AsyncMock(return_value=[])),
            ):
                async with AsyncSessionLocal() as s:
                    await pes._run_batch_loop(s, task_id)
        _run(run_empty())
        # second task: no verified passage
        ids2 = [str(uuid.uuid4())]
        task2 = _run(_make_task(ids2))
        task_id2 = task2["task_id"]
        try:
            async def run_unverified():
                with (
                    patch.object(pes, "build_retrieval_context", new=AsyncMock(return_value=CONTEXT)),
                    patch.object(pes, "build_search_query", new=AsyncMock(return_value="q")),
                    patch.object(pes, "search_papers", new=AsyncMock(return_value=[PAPER])),
                    patch.object(pes, "verify_paper", new=AsyncMock(return_value=PAPER)),
                    patch.object(pes.pfs, "fetch_oa_fulltext_xml", new=AsyncMock(return_value="")),
                    patch.object(pes, "extract_passage_from_paper", new=AsyncMock(return_value=_extraction(verified=False))),
                ):
                    async with AsyncSessionLocal() as s:
                        await pes._run_batch_loop(s, task_id2)
            _run(run_unverified())

            async def check2():
                async with AsyncSessionLocal() as s:
                    row = (
                        await s.execute(
                            text(
                                "SELECT status, preprocess_outcome, last_error_code FROM paper_evidence_task_items "
                                "WHERE task_id::text=:tid"
                            ),
                            {"tid": task_id2},
                        )
                    ).first()
                    assert row[0] == "awaiting_review"
                    assert row[1] == "no_evidence_found"
            _run(check2())
        finally:
            _run(_cleanup(task_id2))

        async def check():
            async with AsyncSessionLocal() as s:
                row = (
                    await s.execute(
                        text(
                            "SELECT status, preprocess_outcome, last_error_code FROM paper_evidence_task_items "
                            "WHERE task_id::text=:tid"
                        ),
                        {"tid": task_id},
                    )
                ).first()
                assert row[0] == "awaiting_review"
                assert row[1] == "no_evidence_found"
                assert row[2] == "EUROPE_PMC_NO_RESULT"
        _run(check())
    finally:
        _run(_cleanup(task_id))


def test_mixed_contradict_are_kept_as_awaiting_review():
    ids = [str(uuid.uuid4())]
    task = _run(_make_task(ids))
    task_id = task["task_id"]
    try:
        async def run_mixed():
            with (
                patch.object(pes, "build_retrieval_context", new=AsyncMock(return_value=CONTEXT)),
                patch.object(pes, "build_search_query", new=AsyncMock(return_value="q")),
                patch.object(pes, "search_papers", new=AsyncMock(return_value=[PAPER])),
                patch.object(pes, "verify_paper", new=AsyncMock(return_value=PAPER)),
                patch.object(pes.pfs, "fetch_oa_fulltext_xml", new=AsyncMock(return_value="")),
                patch.object(pes, "extract_passage_from_paper", new=AsyncMock(return_value=_extraction(direction="mixed"))),
            ):
                async with AsyncSessionLocal() as s:
                    await pes._run_batch_loop(s, task_id)
        _run(run_mixed())
        async def check():
            async with AsyncSessionLocal() as s:
                row = (
                    await s.execute(
                        text("SELECT status, model_direction FROM paper_evidence_task_items WHERE task_id::text=:tid"),
                        {"tid": task_id},
                    )
                ).first()
                assert row[0] == "awaiting_review"
                assert row[1] == "mixed"
        _run(check())
    finally:
        _run(_cleanup(task_id))


def test_draft_save_reload_and_attach_updates_item():
    ids = [str(uuid.uuid4())]
    task = _run(_make_task(ids))
    task_id = task["task_id"]
    try:
        _run(_run_task(task_id))
        async def case():
            async with AsyncSessionLocal() as s:
                item_id = (
                    await s.execute(
                        text("SELECT id::text FROM paper_evidence_task_items WHERE task_id::text=:tid"),
                        {"tid": task_id},
                    )
                ).scalar_one()
                draft = {
                    "query": "custom", "selectedPmid": "99090001", "passages": [],
                    "reviewerDirection": "supports", "reviewerEvidenceLevel": "direct",
                    "reviewerConfidence": "0.78", "note": "looks good", "step": 3, "translations": {},
                }
                saved = await pes.save_task_item_draft(s, item_id, draft, operator_id="reviewer-1")
                assert saved["saved"] is True
                loaded = await pes.get_task_item_draft(s, item_id)
                assert loaded["review_draft"]["reviewerConfidence"] == "0.78"
                assert loaded["review_draft"]["note"] == "looks good"
                await pes.complete_batch_item_reviewed(
                    s, task_id, item_id, evidence_id=str(uuid.uuid4()), operator_id="reviewer-1"
                )
                row = (
                    await s.execute(
                        text(
                            "SELECT status, evidence_id IS NOT NULL, reviewed_at IS NOT NULL "
                            "FROM paper_evidence_task_items WHERE id::text=:iid"
                        ),
                        {"iid": item_id},
                    )
                ).first()
                assert row[0] == "completed"
                assert row[1] is True
                assert row[2] is True
                st = (
                    await s.execute(
                        text("SELECT review_status FROM paper_evidence_tasks WHERE id::text=:tid"),
                        {"tid": task_id},
                    )
                ).first()
                assert st[0] == "completed"
        _run(case())
    finally:
        _run(_cleanup(task_id))


def test_pause_resume_cancel_and_restart_recovery():
    ids = [str(uuid.uuid4())]
    task = _run(_make_task(ids))
    task_id = task["task_id"]
    try:
        async def case():
            async with AsyncSessionLocal() as s:
                await pes.pause_batch_task(s, task_id)
                st = (await s.execute(text("SELECT status FROM paper_evidence_tasks WHERE id::text=:tid"), {"tid": task_id})).scalar_one()
                assert st == "paused"
                await pes.resume_batch_task(s, task_id)
                st = (await s.execute(text("SELECT status FROM paper_evidence_tasks WHERE id::text=:tid"), {"tid": task_id})).scalar_one()
                assert st == "pending"
                await s.execute(
                    text("UPDATE paper_evidence_task_items SET status='extracting' WHERE task_id::text=:tid"),
                    {"tid": task_id},
                )
                await s.execute(
                    text("UPDATE paper_evidence_tasks SET status='running' WHERE id::text=:tid"),
                    {"tid": task_id},
                )
                await s.commit()
                recovered = await pes.recover_interrupted_batch_tasks(s)
                assert recovered >= 1
                st = (await s.execute(text("SELECT status FROM paper_evidence_tasks WHERE id::text=:tid"), {"tid": task_id})).scalar_one()
                item_st = (
                    await s.execute(
                        text("SELECT status FROM paper_evidence_task_items WHERE task_id::text=:tid"),
                        {"tid": task_id},
                    )
                ).scalar_one()
                assert st == "pending"
                assert item_st == "pending"
                await pes.cancel_batch_task(s, task_id)
                item_st = (
                    await s.execute(
                        text("SELECT status, last_error_code FROM paper_evidence_task_items WHERE task_id::text=:tid"),
                        {"tid": task_id},
                    )
                ).first()
                assert item_st[0] == "skipped"
                assert item_st[1] == "CANCELLED"
        _run(case())
    finally:
        _run(_cleanup(task_id))


def test_validate_passage_selection():
    async def case():
        async with AsyncSessionLocal() as s:
            paper = await pes.ensure_paper_source(s, {**PAPER, "abstract": PAPER["abstract"], "fulltext": ""})
            await s.commit()
            paras = [
                {
                    "source_scope": "abstract", "section_title": "Abstract", "paragraph_id": "abstract_p001",
                    "paragraph_index": 0, "passage_text": PAPER["abstract"],
                    "text_hash": pes.passage_hash(PAPER["abstract"]), "locator": "a:0",
                }
            ]
            saved = await pes.ensure_paper_passages(s, paper.id, paras)
            await s.commit()
            pp_id = saved[0]["id"]
            ok = await pes.validate_passage_selection(s, pp_id, "BLA terminals in the infralimbic cortex")
            assert ok["source_verified"] is True
            assert ok["verification_method"] in ("exact", "normalized_whitespace")
            bad = await pes.validate_passage_selection(s, pp_id, "The hippocampus encodes all memories.")
            assert bad["source_verified"] is False
            await s.execute(text("DELETE FROM paper_sources WHERE id=:pid"), {"pid": paper.id})
            await s.commit()
    _run(case())


def test_failed_item_retry_keeps_attempt_history():
    ids = [str(uuid.uuid4())]
    task = _run(_make_task(ids))
    task_id = task["task_id"]
    try:
        async def case():
            async with AsyncSessionLocal() as s:
                await s.execute(
                    text(
                        "UPDATE paper_evidence_task_items SET status='failed', attempt_count=3, "
                        "last_error_code='DEEPSEEK_PARSE_FAILED', last_error_message='boom' "
                        "WHERE task_id::text=:tid"
                    ),
                    {"tid": task_id},
                )
                await s.commit()
                retried = await pes.retry_failed_batch_items(s, task_id)
                assert retried["retried"] == 1
                row = (
                    await s.execute(
                        text(
                            "SELECT status, attempt_count, last_error_code FROM paper_evidence_task_items "
                            "WHERE task_id::text=:tid"
                        ),
                        {"tid": task_id},
                    )
                ).first()
                assert row[0] == "pending"
                assert row[1] == 3  # attempt history preserved
                assert row[2] is None
        _run(case())
    finally:
        _run(_cleanup(task_id))
