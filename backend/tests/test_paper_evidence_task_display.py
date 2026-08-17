# -*- coding: utf-8 -*-
"""任务列表/详情 display 字段:中英名+置信度、兜底链、无 N+1。"""

from __future__ import annotations

import asyncio
import json
import uuid

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


async def _insert_task(tt, oid, *, label, conf, summary_counts=True):
    async with AsyncSessionLocal() as s:
        tid = (
            await s.execute(
                text(
                    "INSERT INTO paper_evidence_tasks "
                    "(target_type, target_id, scope, mode, max_papers_per_object, status, total_items, summary) "
                    "VALUES (:tt, :oid, 'selected', 'function', 3, 'pending', 1, :sm) RETURNING id::text"
                ),
                {
                    "tt": tt,
                    "oid": uuid.UUID(oid),
                    "sm": json.dumps({"counts": {"pending": 1}}) if summary_counts else None,
                },
            )
        ).scalar_one()
        await s.execute(
            text(
                "INSERT INTO paper_evidence_task_items "
                "(task_id, target_type, target_id, label, current_confidence, status) "
                "VALUES (:tid, :tt, :oid, :lbl, :conf, 'pending')"
            ),
            {"tid": tid, "tt": tt, "oid": uuid.UUID(oid), "lbl": label, "conf": conf},
        )
        await s.commit()
        return tid


async def _insert_connection(oid, *, src_cn="杏仁核", src_en="Amygdala", tgt_cn="海马", tgt_en="Hippocampus", confidence=0.35):
    async with AsyncSessionLocal() as s:
        await s.execute(
            text(
                "INSERT INTO mirror_region_connections "
                "(id, source_region_name_cn, source_region_name_en, target_region_name_cn, target_region_name_en, "
                "connection_type, confidence, granularity_level, source_atlas) "
                "VALUES (:id, :sc, :se, :tc, :te, 'projection', :conf, 'macro', 'AAL3')"
            ),
            {"id": uuid.UUID(oid), "sc": src_cn, "se": src_en, "tc": tgt_cn, "te": tgt_en, "conf": confidence},
        )
        await s.commit()


async def _cleanup(task_ids, conn_ids):
    async with AsyncSessionLocal() as s:
        for tid in task_ids:
            await s.execute(text("DELETE FROM paper_evidence_tasks WHERE id::text=:tid"), {"tid": tid})
        for cid in conn_ids:
            await s.execute(text("DELETE FROM mirror_region_connections WHERE id::text=:cid"), {"cid": cid})
        await s.commit()


def test_list_tasks_returns_cn_en_and_confidence():
    oid = str(uuid.uuid4())
    task_ids: list[str] = []
    try:
        _run(_insert_connection(oid, confidence=0.35))
        task_ids.append(_run(_insert_task("connection", oid, label=str(uuid.uuid4()), conf=None)))

        async def case():
            async with AsyncSessionLocal() as s:
                resp = await pes.list_paper_evidence_tasks(s, limit=10)
                task = next(t for t in resp["items"] if t["id"] == task_ids[0])
                assert task["target_id"] == oid
                assert task["display_name_cn"] == "杏仁核 → 海马"
                assert task["display_name_en"] == "Amygdala → Hippocampus"
                assert task["display_confidence"] == 0.35
                assert task["display_name_source"] == "mirror_live"
                assert task["display_confidence_source"] == "mirror_live"
        _run(case())
    finally:
        _run(_cleanup(task_ids, [oid]))


def test_get_task_returns_display_fields():
    oid = str(uuid.uuid4())
    task_ids: list[str] = []
    try:
        _run(_insert_connection(oid, confidence=0.35))
        task_ids.append(_run(_insert_task("connection", oid, label=str(uuid.uuid4()), conf=None)))

        async def case():
            async with AsyncSessionLocal() as s:
                resp = await pes.get_batch_task(s, task_ids[0])
                task = resp["task"]
                assert task["display_name_cn"] == "杏仁核 → 海马"
                assert task["display_confidence"] == 0.35
        _run(case())
    finally:
        _run(_cleanup(task_ids, [oid]))


def test_missing_mirror_row_falls_back_to_snapshot_then_short_id():
    ghost = str(uuid.uuid4())
    task_ids: list[str] = []
    try:
        # 快照 label 非 UUID → task_snapshot
        task_ids.append(_run(_insert_task("connection", ghost, label="BLA → IL", conf=0.7)))
        # 快照 label 为 UUID → 类型中文 #短ID
        ghost2 = str(uuid.uuid4())
        task_ids.append(_run(_insert_task("connection", ghost2, label=str(uuid.uuid4()), conf=None)))

        async def case():
            async with AsyncSessionLocal() as s:
                resp = await pes.list_paper_evidence_tasks(s, limit=10)
                t1 = next(t for t in resp["items"] if t["id"] == task_ids[0])
                assert t1["display_name_cn"] == "BLA → IL"
                assert t1["display_name_source"] == "task_snapshot"
                assert t1["display_confidence"] == 0.7
                assert t1["display_confidence_source"] == "task_snapshot"
                t2 = next(t for t in resp["items"] if t["id"] == task_ids[1])
                assert t2["display_name_cn"] == f"连接 #{ghost2[:8]}"
                assert t2["display_name_source"] == "fallback"
                assert t2["display_confidence"] is None
                assert t2["display_confidence_source"] == "missing"
        _run(case())
    finally:
        _run(_cleanup(task_ids, []))


def test_list_tasks_no_n1():
    conn_ids = []
    task_ids: list[str] = []
    try:
        async def seed():
            async with AsyncSessionLocal() as s:
                # 填满 limit=10 窗口,避免库中既有旧任务(缺 summary.counts)触发兜底聚合多一次 SELECT
                for _ in range(10):
                    cid = str(uuid.uuid4())
                    conn_ids.append(cid)
                    await s.execute(
                        text(
                            "INSERT INTO mirror_region_connections "
                            "(id, source_region_name_en, target_region_name_en, connection_type, confidence, "
                            "granularity_level, source_atlas) "
                            "VALUES (:id, 'A', 'B', 'projection', 0.1, 'macro', 'AAL3')"
                        ),
                        {"id": uuid.UUID(cid)},
                    )
                    tid = (
                        await s.execute(
                            text(
                                "INSERT INTO paper_evidence_tasks "
                                "(target_type, target_id, scope, mode, max_papers_per_object, status, total_items, summary) "
                                "VALUES ('connection', :oid, 'selected', 'function', 3, 'pending', 1, :sm) RETURNING id::text"
                            ),
                            {"oid": uuid.UUID(cid), "sm": '{"counts":{"pending":1}}'},
                        )
                    ).scalar_one()
                    task_ids.append(tid)
                    await s.execute(
                        text(
                            "INSERT INTO paper_evidence_task_items "
                            "(task_id, target_type, target_id, label, status) "
                            "VALUES (:tid, 'connection', :oid, 'x', 'pending')"
                        ),
                        {"tid": tid, "oid": uuid.UUID(cid)},
                    )
                await s.commit()
        _run(seed())

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

        async def case():
            async with AsyncSessionLocal() as s:
                proxy = CountingSession(s)
                await pes.list_paper_evidence_tasks(proxy, limit=10)
                # 任务列表 + COUNT + 镜像表批量 JOIN(仅 1 种 target_type)= 3 次 SELECT
                assert proxy.selects == 3, f"expected 3 SELECT, got {proxy.selects}"
        _run(case())
    finally:
        _run(_cleanup(task_ids, conn_ids))
