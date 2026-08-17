# -*- coding: utf-8 -*-
"""S3: 任务对象列表实时展示字段/排序/分页 与 物化快照修复(service 级测试)。

覆盖:
- live_display_name/live_confidence/display_*/source 与 total
- 历史快照不被修改;0.0 保留;null=未评分
- 中文优先/英文兜底/中文#短ID 兜底
- sort=confidence 排序(0 最前,null 最后,稳定)
- offset 稳定分页不重不漏
- 批量解析无逐对象查询
- _materialize_page 写入真实快照
"""
from __future__ import annotations

import asyncio
import uuid

import pytest
from sqlalchemy import text

from app.database import AsyncSessionLocal
from app.models.mirror_kg import MirrorRegionConnection
from app.services import paper_evidence_service as pes


def _run(coro):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _make_connection(
    session,
    *,
    confidence=None,
    src_cn="体感区，第4层",
    src_en="Somatosensory areas, layer 4",
    tgt_cn="鼻区，第1层",
    tgt_en="Primary somatosensory area, nose, layer 1",
    conn_id=None,
) -> str:
    conn = MirrorRegionConnection(
        id=conn_id or uuid.uuid4(),
        granularity_level="macro",
        granularity_family="macro_clinical",
        source_atlas="test_atlas",
        connection_type="projection",
        source_region_name_cn=src_cn,
        source_region_name_en=src_en,
        target_region_name_cn=tgt_cn,
        target_region_name_en=tgt_en,
        confidence=confidence,
        mirror_status="llm_suggested",
        review_status="pending",
        promotion_status="not_promoted",
    )
    session.add(conn)
    await session.flush()
    return str(conn.id)


async def _make_task(session, ids: list[str]) -> str:
    tid = (
        await session.execute(
            text(
                "INSERT INTO paper_evidence_tasks "
                "(target_type, scope, mode, max_papers_per_object, status, total_items) "
                "VALUES ('connection', 'selected', 'existence', 3, 'paused', :n) RETURNING id::text"
            ),
            {"n": len(ids)},
        )
    ).scalar_one()
    return tid


async def _insert_item(session, task_id, *, target_id, label, conf, status="awaiting_review") -> None:
    await session.execute(
        text(
            "INSERT INTO paper_evidence_task_items "
            "(task_id, target_type, target_id, label, current_confidence, status) "
            "VALUES (:tid, 'connection', :oid, :lbl, :conf, :st)"
        ),
        {"tid": task_id, "oid": target_id, "lbl": label, "conf": conf, "st": status},
    )
    await session.commit()


async def _cleanup(session, task_id: str, conn_ids: list[str]) -> None:
    await session.execute(text("DELETE FROM paper_evidence_task_items WHERE task_id::text=:tid"), {"tid": task_id})
    await session.execute(text("DELETE FROM paper_evidence_tasks WHERE id::text=:tid"), {"tid": task_id})
    for cid in conn_ids:
        await session.execute(text("DELETE FROM mirror_region_connections WHERE id::text=:cid"), {"cid": cid})
    await session.commit()


class CountingSession:
    """统计 SELECT 次数的只读代理(验证批量解析无 N+1)。"""

    def __init__(self, inner):
        self.inner = inner
        self.selects = 0

    async def execute(self, stmt, params=None):
        if str(stmt).lstrip().upper().startswith("SELECT"):
            self.selects += 1
        return await self.inner.execute(stmt, params)

    def __getattr__(self, name):
        return getattr(self.inner, name)


# ── 列表接口:实时展示字段 ──


def test_live_fields_audit_object():
    """审计对象:UUID 快照 + null 快照置信度,镜像行有中文名与 0.0 → display 用实时值,快照不动。"""
    conn_ids: list[str] = []
    task_id: str | None = None
    try:
        async def case():
            nonlocal task_id
            async with AsyncSessionLocal() as s:
                cid = await _make_connection(s, confidence=0.0)
                conn_ids.append(cid)
                task_id = await _make_task(s, [cid])
                uuid_label = str(uuid.uuid4())
                await _insert_item(s, task_id, target_id=cid, label=uuid_label, conf=None)
                resp = await pes.list_batch_items(s, task_id)
                assert resp["total"] == 1
                item = resp["items"][0]
                # 历史快照不动
                assert item["label"] == uuid_label
                assert item["current_confidence"] is None
                # 实时字段
                assert item["live_display_name"] == "体感区，第4层 → 鼻区，第1层"
                assert item["live_confidence"] == 0.0
                # 展示合成
                assert item["display_name"] == "体感区，第4层 → 鼻区，第1层"
                assert item["display_confidence"] == 0.0
                assert item["display_name_source"] == "mirror_live"
                assert item["display_confidence_source"] == "mirror_live"
        _run(case())
    finally:
        _run(_cleanup_case(task_id, conn_ids))


async def _cleanup_case(task_id, conn_ids):
    async with AsyncSessionLocal() as s:
        await _cleanup(s, task_id, conn_ids)


def test_live_null_falls_back_to_snapshot():
    conn_ids: list[str] = []
    task_id: str | None = None
    try:
        async def case():
            nonlocal task_id
            async with AsyncSessionLocal() as s:
                cid = await _make_connection(s, confidence=None)
                conn_ids.append(cid)
                task_id = await _make_task(s, [cid])
                await _insert_item(s, task_id, target_id=cid, label="BLA → IL", conf=0.7)
                item = (await pes.list_batch_items(s, task_id))["items"][0]
                # 名称:实时名优先(镜像行有中文名) → mirror_live
                assert item["display_name"] == "体感区，第4层 → 鼻区，第1层"
                # 置信度:实时 null → 快照 0.7
                assert item["display_confidence"] == 0.7
                assert item["display_confidence_source"] == "task_snapshot"
        _run(case())
    finally:
        _run(_cleanup_case(task_id, conn_ids))


def test_missing_row_uuid_label_falls_back_to_type_short_id():
    conn_ids: list[str] = []
    task_id: str | None = None
    try:
        async def case():
            nonlocal task_id
            async with AsyncSessionLocal() as s:
                ghost = str(uuid.uuid4())
                task_id = await _make_task(s, [ghost])
                uuid_label = str(uuid.uuid4())
                await _insert_item(s, task_id, target_id=ghost, label=uuid_label, conf=None)
                item = (await pes.list_batch_items(s, task_id))["items"][0]
                assert item["live_display_name"] is None
                assert item["live_confidence"] is None
                assert item["display_name"] == f"连接 #{ghost[:8]}"
                assert item["display_name_source"] == "fallback"
                assert item["display_confidence"] is None
                assert item["display_confidence_source"] == "missing"
        _run(case())
    finally:
        _run(_cleanup_case(task_id, conn_ids))


def test_cn_first_en_fallback():
    conn_ids: list[str] = []
    task_id: str | None = None
    try:
        async def case():
            nonlocal task_id
            async with AsyncSessionLocal() as s:
                cid = await _make_connection(s, confidence=0.2, src_cn=None, tgt_cn=None)
                conn_ids.append(cid)
                task_id = await _make_task(s, [cid])
                await _insert_item(s, task_id, target_id=cid, label=str(uuid.uuid4()), conf=None)
                item = (await pes.list_batch_items(s, task_id))["items"][0]
                assert item["display_name"] == "Somatosensory areas, layer 4 → Primary somatosensory area, nose, layer 1"
        _run(case())
    finally:
        _run(_cleanup_case(task_id, conn_ids))


def test_sort_confidence_zero_low_high_null():
    """排序:0 最前 → 低值 → 高值 → null 最后;同分按 created_at/id 稳定。"""
    conn_ids: list[str] = []
    task_id: str | None = None
    try:
        async def case():
            nonlocal task_id
            async with AsyncSessionLocal() as s:
                c0 = await _make_connection(s, confidence=0.0)
                c3 = await _make_connection(s, confidence=0.3)
                ghost = str(uuid.uuid4())
                conn_ids.extend([c0, c3])
                task_id = await _make_task(s, [c0, c3, ghost])
                await _insert_item(s, task_id, target_id=c0, label="z0", conf=None)
                await _insert_item(s, task_id, target_id=c3, label="z3", conf=None)
                await _insert_item(s, task_id, target_id=ghost, label=str(uuid.uuid4()), conf=None)
                items = (await pes.list_batch_items(s, task_id, sort="confidence"))["items"]
                confs = [it["display_confidence"] for it in items]
                assert confs == [0.0, 0.3, None]
        _run(case())
    finally:
        _run(_cleanup_case(task_id, conn_ids))


def test_total_and_stable_offset_pagination():
    conn_ids: list[str] = []
    task_id: str | None = None
    try:
        async def case():
            nonlocal task_id
            async with AsyncSessionLocal() as s:
                for _ in range(5):
                    conn_ids.append(await _make_connection(s, confidence=0.1))
                task_id = await _make_task(s, conn_ids)
                for i, cid in enumerate(conn_ids):
                    await _insert_item(s, task_id, target_id=cid, label=f"obj-{i}", conf=0.1)
                r1 = await pes.list_batch_items(s, task_id, limit=2, offset=0)
                r2 = await pes.list_batch_items(s, task_id, limit=2, offset=2)
                r3 = await pes.list_batch_items(s, task_id, limit=2, offset=4)
                assert r1["total"] == 5 and len(r1["items"]) == 2
                ids = [it["id"] for it in r1["items"] + r2["items"] + r3["items"]]
                assert len(ids) == 5 and len(set(ids)) == 5, "分页不得重复或遗漏"
        _run(case())
    finally:
        _run(_cleanup_case(task_id, conn_ids))


def test_list_batch_items_no_n1():
    """列表读取的 SELECT 次数固定(任务类型 + items + count),不随对象数增长。"""
    conn_ids: list[str] = []
    task_id: str | None = None
    try:
        async def case():
            nonlocal task_id
            async with AsyncSessionLocal() as s:
                for _ in range(5):
                    conn_ids.append(await _make_connection(s, confidence=0.2))
                task_id = await _make_task(s, conn_ids)
                for i, cid in enumerate(conn_ids):
                    await _insert_item(s, task_id, target_id=cid, label=f"obj-{i}", conf=0.2)
                proxy = CountingSession(s)
                await pes.list_batch_items(proxy, task_id)
                assert proxy.selects == 3, f"expected 3 SELECT, got {proxy.selects}"
        _run(case())
    finally:
        _run(_cleanup_case(task_id, conn_ids))


# ── 物化流程快照 ──


def test_materialize_writes_real_snapshot_with_zero():
    conn_ids: list[str] = []
    task_id: str | None = None
    try:
        async def case():
            nonlocal task_id
            async with AsyncSessionLocal() as s:
                cid = await _make_connection(s, confidence=0.0)
                conn_ids.append(cid)
                task_id = await _make_task(s, [cid])
                inserted, _ = await pes._materialize_page(
                    s, task_id=task_id, target_type="connection",
                    filter_snapshot=None, cursor=None, batch_size=100, selected_ids=[cid],
                )
                assert inserted == 1
                row = (await s.execute(
                    text("SELECT label, current_confidence FROM paper_evidence_task_items WHERE task_id::text=:tid"),
                    {"tid": task_id},
                )).first()
                assert row[0] == "体感区，第4层 → 鼻区，第1层"
                assert float(row[1]) == 0.0
        _run(case())
    finally:
        _run(_cleanup_case(task_id, conn_ids))


def test_materialize_null_confidence_stays_null():
    conn_ids: list[str] = []
    task_id: str | None = None
    try:
        async def case():
            nonlocal task_id
            async with AsyncSessionLocal() as s:
                cid = await _make_connection(s, confidence=None)
                conn_ids.append(cid)
                task_id = await _make_task(s, [cid])
                inserted, _ = await pes._materialize_page(
                    s, task_id=task_id, target_type="connection",
                    filter_snapshot=None, cursor=None, batch_size=100, selected_ids=[cid],
                )
                assert inserted == 1
                row = (await s.execute(
                    text("SELECT label, current_confidence FROM paper_evidence_task_items WHERE task_id::text=:tid"),
                    {"tid": task_id},
                )).first()
                assert row[0] == "体感区，第4层 → 鼻区，第1层"
                assert row[1] is None
        _run(case())
    finally:
        _run(_cleanup_case(task_id, conn_ids))


def test_materialize_missing_row_falls_back_to_target_id():
    task_id: str | None = None
    try:
        async def case():
            nonlocal task_id
            async with AsyncSessionLocal() as s:
                ghost = str(uuid.uuid4())
                task_id = await _make_task(s, [ghost])
                inserted, _ = await pes._materialize_page(
                    s, task_id=task_id, target_type="connection",
                    filter_snapshot=None, cursor=None, batch_size=100, selected_ids=[ghost],
                )
                assert inserted == 1
                row = (await s.execute(
                    text("SELECT label, current_confidence FROM paper_evidence_task_items WHERE task_id::text=:tid"),
                    {"tid": task_id},
                )).first()
                assert row[0] == ghost
                assert row[1] is None
        _run(case())
    finally:
        _run(_cleanup_case(task_id, []))
