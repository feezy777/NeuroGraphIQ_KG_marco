# -*- coding: utf-8 -*-
"""S5: 任务统一 work_status/item_counts/capabilities 与 items 状态筛选(service 级)。"""
from __future__ import annotations

import asyncio
import json
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.database import AsyncSessionLocal
from app.main import app
from app.services import paper_evidence_service as pes


def _run(coro):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _make_task(session, *, raw_status="pending", counts: dict[str, int] | None = None, summary: bool = True) -> str:
    tid = str(uuid.uuid4())
    summary_json = (
        json.dumps({"counts": counts}, ensure_ascii=False)
        if summary and counts is not None
        else json.dumps({}, ensure_ascii=False)  # summary NOT NULL:空对象触发批量兜底路径
    )
    await session.execute(
        text(
            "INSERT INTO paper_evidence_tasks "
            "(id, target_type, scope, mode, max_papers_per_object, status, review_status, summary) "
            "VALUES (:tid, 'connection', 'selected', 'existence', 3, :st, 'not_started', "
            "CAST(:sum AS jsonb))"
        ),
        {"tid": tid, "st": raw_status, "sum": summary_json},
    )
    await session.commit()
    return tid


async def _add_items(session, task_id: str, statuses: list[str]) -> None:
    for st in statuses:
        await session.execute(
            text(
                "INSERT INTO paper_evidence_task_items (task_id, target_type, target_id, label, current_confidence, status) "
                "VALUES (:tid, 'connection', :oid, :lbl, NULL, :st)"
            ),
            {"tid": task_id, "oid": str(uuid.uuid4()), "lbl": str(uuid.uuid4())[:8], "st": st},
        )
    await session.commit()


async def _cleanup(session, task_id: str) -> None:
    await session.execute(text("DELETE FROM paper_evidence_task_items WHERE task_id::text=:tid"), {"tid": task_id})
    await session.execute(text("DELETE FROM paper_evidence_tasks WHERE id::text=:tid"), {"tid": task_id})
    await session.commit()


def _task_by_id(session, task_id: str) -> dict:
    async def case():
        async with AsyncSessionLocal() as s:
            return next(t for t in (await pes.list_paper_evidence_tasks(s, limit=200))["items"] if t["id"] == task_id)
    return _run(case())


def test_raw_completed_with_awaiting_is_awaiting_review():
    task_id = None
    try:
        async def case():
            nonlocal task_id
            async with AsyncSessionLocal() as s:
                task_id = await _make_task(s, raw_status="completed", counts=None, summary=False)
                await _add_items(s, task_id, ["awaiting_review", "awaiting_review"])
        _run(case())
        t = _task_by_id(None, task_id)
        assert t["work_status"] == "awaiting_review"
        assert t["item_counts"]["awaiting_review"] == 2
        assert t["capabilities"]["can_continue_review"] is True
    finally:
        _run(_cleanup_case(task_id))


async def _cleanup_case(task_id):
    async with AsyncSessionLocal() as s:
        await _cleanup(s, task_id)


def test_empty_when_no_items():
    task_id = None
    try:
        async def case():
            nonlocal task_id
            async with AsyncSessionLocal() as s:
                task_id = await _make_task(s, raw_status="pending", counts=None, summary=False)
        _run(case())
        t = _task_by_id(None, task_id)
        assert t["work_status"] == "empty"
        assert t["item_counts"]["total"] == 0
    finally:
        _run(_cleanup_case(task_id))


def test_paused_work_status_and_resume_capability():
    task_id = None
    try:
        async def case():
            nonlocal task_id
            async with AsyncSessionLocal() as s:
                task_id = await _make_task(s, raw_status="paused", counts={"pending": 3}, summary=True)
        _run(case())
        t = _task_by_id(None, task_id)
        assert t["work_status"] == "paused"
        assert t["capabilities"]["can_resume"] is True
        assert t["capabilities"]["can_pause"] is False
    finally:
        _run(_cleanup_case(task_id))


def test_running_processing_and_pause_capability():
    task_id = None
    try:
        async def case():
            nonlocal task_id
            async with AsyncSessionLocal() as s:
                task_id = await _make_task(s, raw_status="running", counts={"searching": 2, "pending": 1}, summary=True)
        _run(case())
        t = _task_by_id(None, task_id)
        assert t["work_status"] == "processing"
        assert t["item_counts"]["processing"] == 2
        assert t["item_counts"]["pending"] == 1
        assert t["capabilities"]["can_pause"] is True
        assert t["capabilities"]["can_resume"] is False
    finally:
        _run(_cleanup_case(task_id))


def test_failed_and_partially_failed():
    ids = []
    try:
        async def case():
            async with AsyncSessionLocal() as s:
                ids.append(await _make_task(s, raw_status="failed", counts={"failed": 4}, summary=True))
                ids.append(await _make_task(s, raw_status="failed", counts={"failed": 2, "completed": 3}, summary=True))
        _run(case())
        t1 = _task_by_id(None, ids[0])
        t2 = _task_by_id(None, ids[1])
        assert t1["work_status"] == "failed"
        assert t1["capabilities"]["can_retry_failed"] is True
        assert t2["work_status"] == "partially_failed"
        assert t2["capabilities"]["can_retry_failed"] is True
        assert t2["capabilities"]["can_view_results"] is True
    finally:
        for tid in ids:
            _run(_cleanup_case(tid))


def test_completed_is_not_approved():
    task_id = None
    try:
        async def case():
            nonlocal task_id
            async with AsyncSessionLocal() as s:
                task_id = await _make_task(s, raw_status="completed", counts={"completed": 5, "skipped": 1}, summary=True)
        _run(case())
        t = _task_by_id(None, task_id)
        assert t["work_status"] == "completed"
        # 与 review 无关:review_status 始终 not_started,但 work_status 由对象终态推导
        assert t["review_status"] == "not_started"
        assert t["capabilities"]["can_view_results"] is True
        assert t["capabilities"]["can_continue_review"] is False
    finally:
        _run(_cleanup_case(task_id))


def test_cancelled_work_status():
    task_id = None
    try:
        async def case():
            nonlocal task_id
            async with AsyncSessionLocal() as s:
                task_id = await _make_task(s, raw_status="cancelled", counts={"cancelled": 6}, summary=True)
        _run(case())
        t = _task_by_id(None, task_id)
        assert t["work_status"] == "cancelled"
        assert t["capabilities"]["can_pause"] is False
        assert t["capabilities"]["can_resume"] is False
        assert t["capabilities"]["can_retry_failed"] is False
    finally:
        _run(_cleanup_case(task_id))


def test_status_filter_and_total():
    task_id = None
    try:
        async def case():
            nonlocal task_id
            async with AsyncSessionLocal() as s:
                task_id = await _make_task(s, raw_status="pending", counts=None, summary=False)
                await _add_items(s, task_id, ["awaiting_review"] * 3 + ["pending"] * 2 + ["completed"])
                resp = await pes.list_batch_items(s, task_id, status="awaiting_review", sort="confidence")
                assert resp["total"] == 3
                assert all(it["status"] == "awaiting_review" for it in resp["items"])
                resp2 = await pes.list_batch_items(s, task_id, status="completed")
                assert resp2["total"] == 1
                # 不带筛选保持原行为
                resp3 = await pes.list_batch_items(s, task_id)
                assert resp3["total"] == 6
        _run(case())
    finally:
        _run(_cleanup_case(task_id))


def test_task_list_no_n1_for_missing_summary():
    """缺 summary 的任务列表:一次批量聚合,SELECT 次数固定。"""
    task_ids = []
    try:
        async def case():
            async with AsyncSessionLocal() as s:
                # 种子任务填满 limit 窗口(不带 target_id/summary):确保窗口内只有 NULL-target 任务,
                # by_type 为空 → 不触发 enrich 的镜像 JOIN,SELECT 次数对环境不敏感
                for _ in range(100):
                    task_ids.append(await _make_task(s, raw_status="pending", counts=None, summary=False))
                proxy = CountingSession(s)
                resp = await pes.list_paper_evidence_tasks(proxy, limit=100)
                assert len(resp["items"]) >= 100
                # 1 列表 SELECT + 1 COUNT + 1 批量聚合 + 1 唯一 item 查询 = 4
                assert proxy.selects == 4, f"expected 4 SELECT, got {proxy.selects}"
        _run(case())
    finally:
        for tid in task_ids:
            _run(_cleanup_case(tid))


class CountingSession:
    def __init__(self, inner):
        self.inner = inner
        self.selects = 0

    async def execute(self, stmt, params=None):
        if str(stmt).lstrip().upper().startswith("SELECT"):
            self.selects += 1
        return await self.inner.execute(stmt, params)

    def __getattr__(self, name):
        return getattr(self.inner, name)


def test_invalid_status_filter_returns_422():
    """非法 status 由路由白名单校验返回 4xx,不进入 SQL。"""
    with TestClient(app, raise_server_exceptions=False) as client:
        r = client.get("/api/ontology/evidence/batch/00000000-0000-0000-0000-000000000000/items?status=evil")
        assert r.status_code == 422
