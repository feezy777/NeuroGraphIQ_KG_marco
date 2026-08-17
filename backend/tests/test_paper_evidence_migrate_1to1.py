# -*- coding: utf-8 -*-
"""存量拆分迁移:拆分/幂等/审计标记/快照回填。"""

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


async def _insert_legacy_multi_task(n=3) -> tuple[str, list[str]]:
    oids = [str(uuid.uuid4()) for _ in range(n)]
    async with AsyncSessionLocal() as s:
        tid = (
            await s.execute(
                text(
                    "INSERT INTO paper_evidence_tasks "
                    "(target_type, scope, mode, max_papers_per_object, status, total_items) "
                    "VALUES ('connection', 'low_confidence', 'function', 3, 'pending', :n) RETURNING id::text"
                ),
                {"n": n},
            )
        ).scalar_one()
        for oid in oids:
            await s.execute(
                text(
                    "INSERT INTO paper_evidence_task_items (task_id, target_type, target_id, label, status) "
                    "VALUES (:tid, 'connection', :oid, :lbl, 'pending')"
                ),
                {"tid": tid, "oid": oid, "lbl": str(uuid.uuid4())},
            )
        await s.commit()
        return tid, oids


async def _migrate():
    async with AsyncSessionLocal() as s:
        return await pes.migrate_tasks_to_1to1(s)


async def _cleanup(ids: list[str]):
    async with AsyncSessionLocal() as s:
        for tid in ids:
            await s.execute(text("DELETE FROM paper_evidence_tasks WHERE id::text=:tid"), {"tid": tid})
        await s.commit()


def test_split_multi_object_task_and_idempotent():
    tid, oids = _run(_insert_legacy_multi_task(3))
    new_ids: list[str] = []
    try:
        stats = _run(_migrate())
        assert stats["tasks_split"] >= 1
        assert stats["objects_migrated"] >= 3

        async def check():
            nonlocal new_ids
            async with AsyncSessionLocal() as s:
                old = (
                    await s.execute(
                        text("SELECT status, summary FROM paper_evidence_tasks WHERE id::text=:tid"),
                        {"tid": tid},
                    )
                ).first()
                assert old[0] == "cancelled"
                assert isinstance(old[1], dict) and old[1].get("migrated_to")
                new_ids = old[1]["migrated_to"]
                assert len(new_ids) == 3
                for nid in new_ids:
                    row = (
                        await s.execute(
                            text(
                                "SELECT target_id IS NOT NULL, total_items, scope, mode "
                                "FROM paper_evidence_tasks WHERE id::text=:nid"
                            ),
                            {"nid": nid},
                        )
                    ).first()
                    assert row[0] is True
                    assert row[1] == 1
                    assert row[2] == "low_confidence"
                    assert row[3] == "function"
                    items = (
                        await s.execute(
                            text("SELECT COUNT(*) FROM paper_evidence_task_items WHERE task_id::text=:nid"),
                            {"nid": nid},
                        )
                    ).scalar_one()
                    assert items == 1
                    snap = (
                        await s.execute(
                            text(
                                "SELECT label, current_confidence FROM paper_evidence_task_items "
                                "WHERE task_id::text=:nid"
                            ),
                            {"nid": nid},
                        )
                    ).first()
                    assert snap[0] is None
                    assert snap[1] is None
        _run(check())
        # 幂等:旧任务已 cancelled,不在扫描范围,不再产生新拆分
        stats2 = _run(_migrate())
        assert stats2["tasks_split"] == 0
        assert stats2["labels_backfilled"] == 0
        async def verify_idempotent():
            async with AsyncSessionLocal() as s:
                rows = (
                    await s.execute(
                        text("SELECT id::text FROM paper_evidence_tasks WHERE summary->>'migrated_to' IS NOT NULL"),
                    )
                ).scalars().all()
                assert tid in set(rows)
        _run(verify_idempotent())
    finally:
        _run(_cleanup([tid, *new_ids]))


def test_single_object_task_gets_target_id_backfilled():
    oid = str(uuid.uuid4())
    tid: str | None = None
    try:
        async def seed():
            nonlocal tid
            async with AsyncSessionLocal() as s:
                tid = (
                    await s.execute(
                        text(
                            "INSERT INTO paper_evidence_tasks "
                            "(target_type, scope, mode, max_papers_per_object, status, total_items) "
                            "VALUES ('connection', 'low_confidence', 'function', 3, 'pending', 1) RETURNING id::text"
                        ),
                    )
                ).scalar_one()
                await s.execute(
                    text(
                        "INSERT INTO paper_evidence_task_items (task_id, target_type, target_id, label, status) "
                        "VALUES (:tid, 'connection', :oid, :lbl, 'pending')"
                    ),
                    {"tid": tid, "oid": oid, "lbl": str(uuid.uuid4())},
                )
                await s.commit()
        _run(seed())
        _run(_migrate())

        async def check():
            async with AsyncSessionLocal() as s:
                row = (
                    await s.execute(
                        text("SELECT target_id::text, status FROM paper_evidence_tasks WHERE id::text=:tid"),
                        {"tid": tid},
                    )
                ).first()
                assert row[0] == oid
                assert row[1] == "pending"  # 不拆分、不取消
                lbl_row = (
                    await s.execute(
                        text("SELECT label FROM paper_evidence_task_items WHERE task_id::text=:tid"),
                        {"tid": tid},
                    )
                ).first()
                assert lbl_row[0] is None
        _run(check())
    finally:
        _run(_cleanup([tid]))


def test_split_path_reassigns_real_label_item_with_null_conf():
    """回归:真实标签 + NULL 置信度(无镜像行)的 item 也必须重挂接到新任务,不得滞留旧任务。"""
    oids = [str(uuid.uuid4()), str(uuid.uuid4())]
    tid: str | None = None
    new_ids: list[str] = []
    try:
        async def seed():
            nonlocal tid
            async with AsyncSessionLocal() as s:
                tid = (
                    await s.execute(
                        text(
                            "INSERT INTO paper_evidence_tasks "
                            "(target_type, scope, mode, max_papers_per_object, status, total_items) "
                            "VALUES ('connection', 'low_confidence', 'function', 3, 'pending', 2) RETURNING id::text"
                        ),
                    )
                ).scalar_one()
                await s.execute(
                    text(
                        "INSERT INTO paper_evidence_task_items (task_id, target_type, target_id, label, status) "
                        "VALUES (:tid, 'connection', :oid, :lbl, 'pending')"
                    ),
                    {"tid": tid, "oid": oids[0], "lbl": "BLA → IL"},
                )
                await s.execute(
                    text(
                        "INSERT INTO paper_evidence_task_items (task_id, target_type, target_id, label, status) "
                        "VALUES (:tid, 'connection', :oid, :lbl, 'pending')"
                    ),
                    {"tid": tid, "oid": oids[1], "lbl": str(uuid.uuid4())},
                )
                await s.commit()
        _run(seed())
        _run(_migrate())

        async def check():
            nonlocal new_ids
            async with AsyncSessionLocal() as s:
                old = (
                    await s.execute(
                        text("SELECT status, summary FROM paper_evidence_tasks WHERE id::text=:tid"),
                        {"tid": tid},
                    )
                ).first()
                assert old[0] == "cancelled"
                assert isinstance(old[1], dict) and old[1].get("migrated_to")
                new_ids = old[1]["migrated_to"]
                assert len(new_ids) == 2
                seen: dict[str | None, object] = {}
                for nid in new_ids:
                    row = (
                        await s.execute(
                            text(
                                "SELECT COUNT(*), MIN(label), MIN(current_confidence) "
                                "FROM paper_evidence_task_items WHERE task_id::text=:nid"
                            ),
                            {"nid": nid},
                        )
                    ).first()
                    assert row[0] == 1
                    seen[row[1]] = row[2]
                # item A: 真实标签保留不被清空,conf 仍 NULL(无镜像行)
                assert "BLA → IL" in seen
                assert seen["BLA → IL"] is None
                # item B: UUID 坏标签被清空为 NULL
                assert None in seen
        _run(check())
    finally:
        _run(_cleanup([tid, *new_ids]))
