### Task 5: 任务列表/详情接口补 display 字段(中英名+置信度)

**Files:**
- Modify: `backend/app/services/paper_evidence_service.py`(`list_paper_evidence_tasks`、`get_batch_task`、新增 `_enrich_task_display`)
- Test: `backend/tests/test_paper_evidence_task_display.py`(新建)

**Interfaces:**
- Consumes: Task 2 的 `mirror_live_display_name_parts`;`TARGET_MODELS`、`_LIVE_NAME_COLUMNS`、`mirror_live_confidence`、`_UUID_RE`、`TARGET_TYPE_LABELS_CN`(均已在模块内)
- Produces: 任务列表/详情每个任务新增 `target_id`、`display_name_cn`、`display_name_en`、`display_confidence`、`display_name_source`('mirror_live'|'task_snapshot'|'fallback'|'missing')、`display_confidence_source`('mirror_live'|'task_snapshot'|'missing')。Task 6/前端使用。

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_paper_evidence_task_display.py`:

```python
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
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_paper_evidence_task_display.py -q`
Expected: FAIL(KeyError: 'target_id' / 'display_name_cn')

- [ ] **Step 3: 实现 `_enrich_task_display`**

> 修订(实施中按 TDD 与测试裁决,已获控制者确认):① 快照查询只覆盖「有 target_id 但镜像行缺失」的任务(NULL-target_id 旧任务不查,保持 SELECT 次数确定,其 display 暂为 missing,由 Task 7 迁移回填 target_id 后自然恢复);② 两处 SELECT 的 `target_id` 用 `::text` 转换(psycopg3 下裸 UUID 列返回 uuid.UUID,与 JSON 协议字符串不一致)。

在 `_build_capabilities` 之后新增:

```python
async def _enrich_task_display(session: AsyncSession, tasks: list[dict]) -> list[dict]:
    """为任务字典补充 display_name_cn/display_name_en/display_confidence 与来源标记(批量,无 N+1)。

    - 按 target_type 分组批量 JOIN 镜像表取实时中英名与置信度;
    - 镜像行缺失时,从任务 items 取唯一对象的快照 label/current_confidence 兜底;
    - 再兜底:非 UUID 快照 label → 「类型中文 #短ID」;置信度实时 → 快照 → None。
    """
    if not tasks:
        return tasks
    by_type: dict[str, list[str]] = {}
    for t in tasks:
        oid = t.get("target_id")
        if oid and t["target_type"] in TARGET_MODELS:
            by_type.setdefault(t["target_type"], []).append(oid)
    live: dict[tuple[str, str], dict] = {}
    for tt, oids in by_type.items():
        table = TARGET_MODELS[tt]
        name_cols = _LIVE_NAME_COLUMNS.get(tt, "")
        sel = ", ".join(f"m.{c}" for c in name_cols.split(", ")) if name_cols else ""
        sel = (sel + ", " if sel else "") + "m.confidence AS live_confidence"
        if tt == "circuit_function":
            sel += ", m.confidence_score"
        rows = (
            await session.execute(
                text(
                    f"SELECT m.id, {sel} FROM {table.__tablename__} m WHERE m.id = ANY(:ids)"
                ),
                {"ids": [uuid.UUID(o) for o in oids]},
            )
        ).all()
        for r in rows:
            live[(tt, str(r._mapping["id"]))] = r._mapping
    # 仅对镜像行缺失的任务取 items 快照(有实时行的任务不再多一次查询;target_id 为空的旧任务不查)
    snap: dict[str, dict] = {}
    need_item = [
        t["id"]
        for t in tasks
        if t.get("target_id")
        and (t["target_type"], str(t.get("target_id"))) not in live
    ]
    if need_item:
        rows = (
            await session.execute(
                text(
                    "SELECT DISTINCT ON (task_id) task_id::text, target_id::text, label, current_confidence "
                    "FROM paper_evidence_task_items WHERE task_id::text = ANY(:ids) "
                    "ORDER BY task_id, updated_at DESC"
                ),
                {"ids": need_item},
            )
        ).all()
        for r in rows:
            snap[r[0]] = {
                "target_id": r[1],
                "label": r[2],
                "confidence": float(r[3]) if r[3] is not None else None,
            }
    out: list[dict] = []
    for t in tasks:
        tt = t["target_type"]
        oid = t.get("target_id") or snap.get(t["id"], {}).get("target_id")
        m = live.get((tt, oid)) if oid else None
        cn = en = None
        conf = None
        name_src = "missing"
        if m is not None:
            cn, en = mirror_live_display_name_parts(tt, m.get)
            conf = mirror_live_confidence(tt, m.get)
            if cn is not None or en is not None:
                name_src = "mirror_live"
        if cn is None and en is None:
            lbl = snap.get(t["id"], {}).get("label")
            if lbl and not _UUID_RE.fullmatch(str(lbl)):
                cn, name_src = str(lbl), "task_snapshot"
            elif oid:
                cn = f"{TARGET_TYPE_LABELS_CN.get(tt, tt)} #{oid[:8]}"
                name_src = "fallback"
        if conf is None:
            sn = snap.get(t["id"], {}).get("confidence")
            if sn is not None:
                conf, conf_src = sn, "task_snapshot"
            else:
                conf_src = "mirror_live" if m is not None else "missing"
        else:
            conf_src = "mirror_live"
        out.append(
            {
                **t,
                "display_name_cn": cn,
                "display_name_en": en,
                "display_confidence": conf,
                "display_name_source": name_src,
                "display_confidence_source": conf_src,
            }
        )
    return out
```

- [ ] **Step 4: 接入两个接口**

`list_paper_evidence_tasks`(约 3923 行):
1. SELECT 列表末尾追加 `, target_id`(在 `confidence_lt` 之后)→ `r[23]`。
2. 字典构造中追加 `"target_id": r[23],`。
3. 在 `return {"items": items, "total": total}` 前改为 `return {"items": await _enrich_task_display(session, items), "total": total}`。

`get_batch_task`(约 4007 行):
1. SELECT 末尾(`materialization_error` 之后)追加 `, target_id` → `task[29]`。
2. 任务字典中追加 `"target_id": task[29],`。
3. `return` 前,将 `"task"` 值改为 `(await _enrich_task_display(session, [task_dict]))[0]`(先组字典、后 enrich、再返回)。

- [ ] **Step 5: 运行确认通过**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_paper_evidence_task_display.py -q`
Expected: 4 passed

- [ ] **Step 6: 回归**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_paper_evidence_batch.py tests/test_paper_evidence_live_fields.py tests/test_paper_evidence_work_status.py -q`
Expected: 全部通过

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/paper_evidence_service.py backend/tests/test_paper_evidence_task_display.py
git commit -m "feat(evidence): task list/detail display fields (cn/en name + confidence, no N+1)"
```

---

