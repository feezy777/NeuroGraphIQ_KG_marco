# -*- coding: utf-8 -*-
"""S6: review ↔ task item 稳定关联与审核终态同步(service 级)。

注意:本文件测试按既有项目约定直接使用开发库,但所有写入均为测试自建行,
清理只删除本测试创建的 task/item/review(绝不 DELETE 全表)。
"""
from __future__ import annotations

import asyncio
import uuid

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


async def _make_task(session, raw_status="pending") -> str:
    tid = str(uuid.uuid4())
    await session.execute(
        text(
            "INSERT INTO paper_evidence_tasks "
            "(id, target_type, scope, mode, max_papers_per_object, status, review_status, summary) "
            "VALUES (:tid, 'connection', 'selected', 'existence', 3, :st, 'not_started', '{}'::jsonb)"
        ),
        {"tid": tid, "st": raw_status},
    )
    await session.commit()
    return tid


async def _add_item(session, task_id: str, target_id: str, status="awaiting_review") -> str:
    iid = str(uuid.uuid4())
    await session.execute(
        text(
            "INSERT INTO paper_evidence_task_items "
            "(id, task_id, target_type, target_id, label, current_confidence, status) "
            "VALUES (:iid, :tid, 'connection', :oid, :lbl, NULL, :st)"
        ),
        {"iid": iid, "tid": task_id, "oid": target_id, "lbl": target_id[:8], "st": status},
    )
    await session.commit()
    return iid


async def _cleanup(session, task_ids: list[str], review_ids: list[str]) -> None:
    for rid in review_ids:
        await session.execute(
            text("DELETE FROM paper_evidence_review_passages WHERE review_id = :rid"), {"rid": rid}
        )
        await session.execute(text("DELETE FROM paper_evidence_reviews WHERE id = :rid"), {"rid": rid})
    for tid in task_ids:
        await session.execute(
            text("DELETE FROM paper_evidence_task_items WHERE task_id::text=:tid"), {"tid": tid}
        )
        await session.execute(text("DELETE FROM paper_evidence_tasks WHERE id::text=:tid"), {"tid": tid})
    await session.commit()


def _build(session, *, task_id=None, task_item_id=None, target_id=None, reviewer_direction="supports") -> dict:
    return pes.build_review(
        session,
        target_type="connection",
        target_id=uuid.UUID(target_id or str(uuid.uuid4())),
        paper_id=None,
        task_id=uuid.UUID(task_id) if task_id else None,
        task_item_id=uuid.UUID(task_item_id) if task_item_id else None,
        reviewer_id=None,
        claim_version="v1",
        claim_text_snapshot="test claim",
        claim_components_snapshot=[],
        model_direction=None,
        model_assessment=None,
        reviewer_direction=reviewer_direction,
        reviewer_evidence_level="direct",
        reviewer_confidence=0.7,
        reviewer_note=None,
        coverage_summary_snapshot={},
        coverage_formula_version="v1",
        draft_revision=0,
        passages=[],
    )


async def _review_row(session, review_id: str) -> tuple:
    row = (
        await session.execute(
            text(
                "SELECT task_id::text, task_item_id::text, review_status, promotion_status "
                "FROM paper_evidence_reviews WHERE id=:rid"
            ),
            {"rid": review_id},
        )
    ).first()
    return tuple(row) if row else None


async def _item_row(session, item_id: str) -> tuple:
    row = (
        await session.execute(
            text(
                "SELECT status, reviewed_at IS NOT NULL, reviewed_by, label, current_confidence "
                "FROM paper_evidence_task_items WHERE id=:iid"
            ),
            {"iid": item_id},
        )
    ).first()
    return tuple(row) if row else None


async def _task_view(session, task_id: str) -> dict:
    tasks = await pes.list_paper_evidence_tasks(session, limit=200)
    return next(t for t in tasks["items"] if t["id"] == task_id)


# ════════════════════════════════════════════════════════════════════════════
# 关联校验(五)
# ════════════════════════════════════════════════════════════════════════════


def test_linked_review_created_with_both_ids():
    async def case():
        async with AsyncSessionLocal() as s:
            tid = await _make_task(s)
            review_id = None
            try:
                target = str(uuid.uuid4())
                iid = await _add_item(s, tid, target)
                r = await _build(s, task_id=tid, task_item_id=iid, target_id=target)
                review_id = r["review_id"]
                row = await _review_row(s, review_id)
                assert row[0] == tid and row[1] == iid
            finally:
                await _cleanup(s, [tid], [review_id] if review_id else [])
    _run(case())


def test_item_not_belong_to_task_rejected():
    async def case():
        async with AsyncSessionLocal() as s:
            tid1 = await _make_task(s)
            tid2 = await _make_task(s)
            try:
                target = str(uuid.uuid4())
                iid = await _add_item(s, tid2, target)
                with pytest.raises(pes.ReviewLinkError, match="does not match task_item_id"):
                    await _build(s, task_id=tid1, task_item_id=iid, target_id=target)
                # 未为这两个任务留下任何 review
                n = (
                    await s.execute(
                        text("SELECT COUNT(*) FROM paper_evidence_reviews WHERE task_id IN (:a, :b)"),
                        {"a": tid1, "b": tid2},
                    )
                ).scalar_one()
                assert n == 0
            finally:
                await _cleanup(s, [tid1, tid2], [])
    _run(case())


def test_target_mismatch_rejected():
    async def case():
        async with AsyncSessionLocal() as s:
            tid = await _make_task(s)
            try:
                target = str(uuid.uuid4())
                iid = await _add_item(s, tid, target)
                with pytest.raises(pes.ReviewLinkError, match="does not match task item"):
                    await _build(s, task_id=tid, task_item_id=iid, target_id=str(uuid.uuid4()))
            finally:
                await _cleanup(s, [tid], [])
    _run(case())


def test_cancelled_task_rejected():
    async def case():
        async with AsyncSessionLocal() as s:
            tid = await _make_task(s, raw_status="cancelled")
            try:
                target = str(uuid.uuid4())
                iid = await _add_item(s, tid, target)
                with pytest.raises(pes.ReviewConflictError, match="task is cancelled"):
                    await _build(s, task_id=tid, task_item_id=iid, target_id=target)
            finally:
                await _cleanup(s, [tid], [])
    _run(case())


def test_terminal_item_status_rejected():
    async def case():
        async with AsyncSessionLocal() as s:
            tid = await _make_task(s)
            try:
                target = str(uuid.uuid4())
                iid = await _add_item(s, tid, target, status="completed")
                with pytest.raises(pes.ReviewLinkError, match="does not allow review"):
                    await _build(s, task_id=tid, task_item_id=iid, target_id=target)
            finally:
                await _cleanup(s, [tid], [])
    _run(case())


def test_legacy_task_only_unique_match_backfills_item():
    async def case():
        async with AsyncSessionLocal() as s:
            tid = await _make_task(s)
            review_id = None
            try:
                target = str(uuid.uuid4())
                iid = await _add_item(s, tid, target)
                r = await _build(s, task_id=tid, task_item_id=None, target_id=target)
                review_id = r["review_id"]
                row = await _review_row(s, review_id)
                assert row[1] == iid
            finally:
                await _cleanup(s, [tid], [review_id] if review_id else [])
    _run(case())


def test_legacy_task_only_zero_match_rejected():
    async def case():
        async with AsyncSessionLocal() as s:
            tid = await _make_task(s)
            try:
                with pytest.raises(pes.ReviewNotFoundError, match="no matching task item"):
                    await _build(s, task_id=tid, task_item_id=None, target_id=str(uuid.uuid4()))
            finally:
                await _cleanup(s, [tid], [])
    _run(case())


def test_legacy_task_only_ambiguous_rejected():
    """同 task+target 多 item 在真实库被唯一索引 uq_task_item_target 阻止;
    防御分支(返回冲突)以 mock 查询结果单测,保证 spec 语义。"""
    from unittest.mock import AsyncMock, MagicMock

    async def case():
        session = AsyncMock()
        task_res = MagicMock()
        task_res.first.return_value = ("pending",)
        match_res = MagicMock()
        match_res.all.return_value = [(uuid.uuid4(), "awaiting_review"), (uuid.uuid4(), "awaiting_review")]
        session.execute = AsyncMock(side_effect=[task_res, match_res])
        with pytest.raises(pes.ReviewConflictError, match="ambiguous task item"):
            await pes._resolve_review_task_item(
                session, task_id=uuid.uuid4(), task_item_id=None,
                target_type="connection", target_id=uuid.uuid4(),
            )
    _run(case())


def test_standalone_review_no_task_context():
    async def case():
        async with AsyncSessionLocal() as s:
            r = await _build(s, task_id=None, task_item_id=None, target_id=str(uuid.uuid4()))
            row = await _review_row(s, r["review_id"])
            assert row[0] is None and row[1] is None
            await _cleanup(s, [], [r["review_id"]])
    _run(case())


# ════════════════════════════════════════════════════════════════════════════
# 防重(六)
# ════════════════════════════════════════════════════════════════════════════


def test_duplicate_active_review_rejected():
    async def case():
        async with AsyncSessionLocal() as s:
            tid = await _make_task(s)
            review_ids = []
            try:
                target = str(uuid.uuid4())
                iid = await _add_item(s, tid, target)
                r = await _build(s, task_id=tid, task_item_id=iid, target_id=target)
                review_ids.append(r["review_id"])
                with pytest.raises(pes.ReviewConflictError, match="active review already exists"):
                    await _build(s, task_id=tid, task_item_id=iid, target_id=target)
            finally:
                await _cleanup(s, [tid], review_ids)
    _run(case())


def test_terminal_review_does_not_block_new_build_after_item_reopen():
    """终态(approved)review 不参与防重;item 经旧 reopen 回退后允许再 build 新 review(下一步回退重评前的最小路径)。"""
    async def case():
        async with AsyncSessionLocal() as s:
            tid = await _make_task(s)
            review_ids = []
            try:
                target = str(uuid.uuid4())
                iid = await _add_item(s, tid, target)
                r = await _build(s, task_id=tid, task_item_id=iid, target_id=target)
                review_ids.append(r["review_id"])
                await pes.approve_review(s, uuid.UUID(r["review_id"]), operator_id="reviewer-1")
                # 旧 reopen 语义(十一.5 不改后端):completed → awaiting_review
                await pes.reopen_batch_item(s, tid, iid)
                r2 = await _build(s, task_id=tid, task_item_id=iid, target_id=target)
                review_ids.append(r2["review_id"])
                assert r2["review_id"] != r["review_id"]
            finally:
                await _cleanup(s, [tid], review_ids)
    _run(case())


# ════════════════════════════════════════════════════════════════════════════
# 审核终态同步(七)
# ════════════════════════════════════════════════════════════════════════════


def test_approve_completes_linked_item_transactionally():
    async def case():
        async with AsyncSessionLocal() as s:
            tid = await _make_task(s)
            review_id = None
            try:
                target = str(uuid.uuid4())
                iid = await _add_item(s, tid, target)
                r = await _build(s, task_id=tid, task_item_id=iid, target_id=target)
                review_id = r["review_id"]
                await pes.approve_review(s, uuid.UUID(review_id), operator_id="reviewer-1")
                row = await _item_row(s, iid)
                assert row[0] == "completed" and row[1] is True and row[2] == "reviewer-1"
                # 名称/置信度快照未动(七.4)
                assert row[3] == target[:8] and row[4] is None
                # review.id 未塞进语义不同的 evidence_id(七.3)
                eid = (
                    await s.execute(
                        text("SELECT evidence_id FROM paper_evidence_task_items WHERE id=:iid"), {"iid": iid}
                    )
                ).scalar_one()
                assert eid is None
                # 任务统计与 work_status 重算(七.5/6)
                t = await _task_view(s, tid)
                assert t["item_counts"]["completed"] == 1
                assert t["work_status"] == "completed"
            finally:
                await _cleanup(s, [tid], [review_id] if review_id else [])
    _run(case())


def test_reject_completes_linked_item():
    async def case():
        async with AsyncSessionLocal() as s:
            tid = await _make_task(s)
            review_id = None
            try:
                target = str(uuid.uuid4())
                iid = await _add_item(s, tid, target)
                r = await _build(s, task_id=tid, task_item_id=iid, target_id=target)
                review_id = r["review_id"]
                await pes.reject_review(s, uuid.UUID(review_id), operator_id="reviewer-1")
                row = await _item_row(s, iid)
                assert row[0] == "completed"
                assert row[1] is True and row[2] == "reviewer-1"
            finally:
                await _cleanup(s, [tid], [review_id] if review_id else [])
    _run(case())


def test_standalone_approve_and_reject_do_not_touch_items():
    async def case():
        async with AsyncSessionLocal() as s:
            tid = await _make_task(s)
            review_ids = []
            try:
                target = str(uuid.uuid4())
                iid = await _add_item(s, tid, target)
                r1 = await _build(s, task_id=None, task_item_id=None, target_id=str(uuid.uuid4()))
                review_ids.append(r1["review_id"])
                await pes.approve_review(s, uuid.UUID(r1["review_id"]))
                r2 = await _build(s, task_id=None, task_item_id=None, target_id=str(uuid.uuid4()))
                review_ids.append(r2["review_id"])
                await pes.reject_review(s, uuid.UUID(r2["review_id"]))
                row = await _item_row(s, iid)
                assert row[0] == "awaiting_review" and row[1] is False and row[2] is None
            finally:
                await _cleanup(s, [tid], review_ids)
    _run(case())


def test_duplicate_approve_conflicts():
    async def case():
        async with AsyncSessionLocal() as s:
            tid = await _make_task(s)
            review_id = None
            try:
                target = str(uuid.uuid4())
                iid = await _add_item(s, tid, target)
                r = await _build(s, task_id=tid, task_item_id=iid, target_id=target)
                review_id = r["review_id"]
                await pes.approve_review(s, uuid.UUID(review_id))
                with pytest.raises(pes.ReviewConflictError, match="cannot approve review in status"):
                    await pes.approve_review(s, uuid.UUID(review_id))
            finally:
                await _cleanup(s, [tid], [review_id] if review_id else [])
    _run(case())


def test_duplicate_reject_conflicts():
    async def case():
        async with AsyncSessionLocal() as s:
            tid = await _make_task(s)
            review_id = None
            try:
                target = str(uuid.uuid4())
                iid = await _add_item(s, tid, target)
                r = await _build(s, task_id=tid, task_item_id=iid, target_id=target)
                review_id = r["review_id"]
                await pes.reject_review(s, uuid.UUID(review_id))
                with pytest.raises(pes.ReviewConflictError, match="already rejected"):
                    await pes.reject_review(s, uuid.UUID(review_id))
            finally:
                await _cleanup(s, [tid], [review_id] if review_id else [])
    _run(case())


def test_approve_failure_leaves_no_partial_state():
    """十二.14:事务中途失败(统计重算抛错)→ review 与 item 均保持原状态,无半完成数据。"""
    async def case():
        async with AsyncSessionLocal() as s:
            tid = await _make_task(s)
            review_id = None
            orig = pes._update_task_totals

            async def boom(_session, _task_id):
                raise RuntimeError("stats boom")

            try:
                target = str(uuid.uuid4())
                iid = await _add_item(s, tid, target)
                r = await _build(s, task_id=tid, task_item_id=iid, target_id=target)
                review_id = r["review_id"]
                pes._update_task_totals = boom
                with pytest.raises(RuntimeError, match="stats boom"):
                    await pes.approve_review(s, uuid.UUID(review_id), operator_id="reviewer-1")
                await s.rollback()  # 模拟请求结束回滚未提交事务
                # review 未变 approved,item 未变 completed
                assert (await _review_row(s, review_id))[2] == "awaiting_review"
                assert (await _item_row(s, iid))[0] == "awaiting_review"
                # 无半完成审计
                n = (
                    await s.execute(
                        text(
                            "SELECT COUNT(*) FROM ontology_change_logs "
                            "WHERE action_type='EVIDENCE_REVIEW_APPROVED' AND entity_id=:rid"
                        ),
                        {"rid": review_id},
                    )
                ).scalar_one()
                assert n == 0
            finally:
                pes._update_task_totals = orig
                await _cleanup(s, [tid], [review_id] if review_id else [])
    _run(case())


# ════════════════════════════════════════════════════════════════════════════
# 只读解析端点服务函数(三.8 / 四)
# ════════════════════════════════════════════════════════════════════════════


def test_resolve_unique_match_returns_item():
    async def case():
        async with AsyncSessionLocal() as s:
            tid = await _make_task(s)
            try:
                target = str(uuid.uuid4())
                iid = await _add_item(s, tid, target)
                r = await pes.resolve_task_item_for_target(
                    s, task_id=uuid.UUID(tid), target_type="connection", target_id=uuid.UUID(target)
                )
                assert r["task_item_id"] == iid and r["task_id"] == tid and r["matched"] == "task_target"
            finally:
                await _cleanup(s, [tid], [])
    _run(case())


def test_resolve_zero_match_not_found():
    async def case():
        async with AsyncSessionLocal() as s:
            tid = await _make_task(s)
            try:
                with pytest.raises(pes.ReviewNotFoundError):
                    await pes.resolve_task_item_for_target(
                        s, task_id=uuid.UUID(tid), target_type="connection", target_id=uuid.uuid4()
                    )
            finally:
                await _cleanup(s, [tid], [])
    _run(case())


def test_resolve_ambiguous_conflict():
    """真实库唯一索引使同任务同 target 多 item 不可达;以 mock 查询结果单测冲突分支。"""
    from unittest.mock import AsyncMock, MagicMock

    async def case():
        session = AsyncMock()
        res = MagicMock()
        res.all.return_value = [
            (uuid.uuid4(), "connection", uuid.uuid4(), "awaiting_review"),
            (uuid.uuid4(), "connection", uuid.uuid4(), "awaiting_review"),
        ]
        session.execute = AsyncMock(return_value=res)
        with pytest.raises(pes.ReviewConflictError, match="ambiguous"):
            await pes.resolve_task_item_for_target(
                session, task_id=uuid.uuid4(), target_type="connection", target_id=uuid.uuid4()
            )
    _run(case())


def test_resolve_with_task_item_id_verifies_identity():
    async def case():
        async with AsyncSessionLocal() as s:
            tid = await _make_task(s)
            try:
                target = str(uuid.uuid4())
                iid = await _add_item(s, tid, target)
                r = await pes.resolve_task_item_for_target(
                    s, task_id=uuid.UUID(tid), target_type="connection",
                    target_id=uuid.UUID(target), task_item_id=uuid.UUID(iid),
                )
                assert r["task_item_id"] == iid and r["matched"] == "task_item_id"
                # 不一致 target → 拒绝
                with pytest.raises(pes.ReviewLinkError):
                    await pes.resolve_task_item_for_target(
                        s, task_id=uuid.UUID(tid), target_type="connection",
                        target_id=uuid.uuid4(), task_item_id=uuid.UUID(iid),
                    )
            finally:
                await _cleanup(s, [tid], [])
    _run(case())


def test_invalid_item_rejects_without_insert():
    async def case():
        async with AsyncSessionLocal() as s:
            target = str(uuid.uuid4())
            with pytest.raises(pes.ReviewNotFoundError, match="task item not found"):
                await _build(s, task_id=None, task_item_id=str(uuid.uuid4()), target_id=target)
            # 未为该 target 留下任何 review
            n = (
                await s.execute(
                    text("SELECT COUNT(*) FROM paper_evidence_reviews WHERE target_id=:tgt"),
                    {"tgt": target},
                )
            ).scalar_one()
            assert n == 0
    _run(case())
