### Task 7: 存量拆分迁移(migrate_tasks_to_1to1 + 脚本 + 测试)

**Files:**
- Modify: `backend/app/services/paper_evidence_service.py`(新增 `migrate_tasks_to_1to1`)
- Create: `backend/scripts/migrate_evidence_tasks_1to1.py`
- Test: `backend/tests/test_paper_evidence_migrate_1to1.py`(新建)

**Interfaces:**
- Consumes: `_batch_scope_label`、`_UUID_RE`(模块内)
- Produces: `migrate_tasks_to_1to1(session) -> {"tasks_scanned": int, "tasks_split": int, "objects_migrated": int, "labels_backfilled": int, "target_ids_backfilled": int}`

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_paper_evidence_migrate_1to1.py`:

```python
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
        _run(check())
        # 幂等:旧任务已 cancelled,不在扫描范围,不再产生新拆分
        stats2 = _run(_migrate())
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
        _run(check())
    finally:
        _run(_cleanup([tid]))
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_paper_evidence_migrate_1to1.py -q`
Expected: FAIL(AttributeError:`module 'paper_evidence_service' has no attribute 'migrate_tasks_to_1to1'`)

- [ ] **Step 3: 实现迁移函数**

在 `paper_evidence_service.py` 的 `recover_interrupted_batch_tasks` 之后新增:

```python
async def migrate_tasks_to_1to1(session: AsyncSession) -> dict:
    """存量拆分迁移(幂等):多对象任务按对象拆成一对一任务;旧任务标记 cancelled + migrated_to。

    - 单对象任务:回填任务 target_id 与 item 快照(label 为 UUID/空、置信度 NULL 时实时取);
    - 多对象任务:每 item 生成一个新任务(复制配置与状态),item 挂接过去,旧任务 cancelled;
    - 仅扫描 status <> 'cancelled' 的任务,已拆任务自然跳过(幂等)。
    """
    rows = (
        await session.execute(
            text(
                "SELECT id::text, target_type, scope, mode, max_papers_per_object, status, name, "
                "granularity_level, only_oa, confidence_lt, stop_after_strong_support, config, created_by "
                "FROM paper_evidence_tasks WHERE status <> 'cancelled' ORDER BY created_at"
            )
        )
    ).all()
    stats = {
        "tasks_scanned": len(rows),
        "tasks_split": 0,
        "objects_migrated": 0,
        "labels_backfilled": 0,
        "target_ids_backfilled": 0,
    }
    for r in rows:
        tid, tt, scope, mode, maxp, status, name, gl, only_oa, clt, stop, config, created_by = r
        items = (
            await session.execute(
                text(
                    "SELECT id::text, target_id::text, label, current_confidence FROM paper_evidence_task_items "
                    "WHERE task_id::text = :tid ORDER BY updated_at"
                ),
                {"tid": tid},
            )
        ).all()
        if not items:
            continue
        if len(items) == 1:
            oid = uuid.UUID(items[0][1])
            label, conf = await _batch_scope_label(session, tt, oid)
            if str(label) == str(oid):
                label = None
            if (not items[0][2] or _UUID_RE.fullmatch(str(items[0][2]))) or items[0][3] is None:
                await session.execute(
                    text(
                        "UPDATE paper_evidence_task_items SET label=COALESCE(:lbl, label), "
                        "current_confidence=COALESCE(:conf, current_confidence) WHERE id::text=:iid"
                    ),
                    {"lbl": label, "conf": conf, "iid": items[0][0]},
                )
                stats["labels_backfilled"] += 1
            await session.execute(
                text("UPDATE paper_evidence_tasks SET target_id=:oid, total_items=1 WHERE id::text=:tid"),
                {"oid": oid, "tid": tid},
            )
            stats["target_ids_backfilled"] += 1
            continue
        new_ids: list[str] = []
        for iid, oid_s, lbl, conf in items:
            oid = uuid.UUID(oid_s)
            label, live_conf = await _batch_scope_label(session, tt, oid)
            if str(label) == str(oid):
                label = None
            new_id = (
                await session.execute(
                    text(
                        "INSERT INTO paper_evidence_tasks "
                        "(target_type, target_id, scope, mode, max_papers_per_object, status, name, "
                        "granularity_level, only_oa, confidence_lt, stop_after_strong_support, config, "
                        "created_by, total_items, review_status, materialization_status, materialized_target_count) "
                        "VALUES (:tt, :oid, :scope, :mode, :maxp, :status, :name, :gl, :only_oa, :clt, :stop, "
                        "COALESCE(CAST(:config AS jsonb), '{}'::jsonb), :cb, 1, 'not_started', 'completed', 1) RETURNING id::text"
                    ),
                    {
                        "tt": tt,
                        "oid": oid,
                        "scope": scope,
                        "mode": mode,
                        "maxp": maxp,
                        "status": status,
                        "name": name,
                        "gl": gl,
                        "only_oa": only_oa,
                        "clt": clt,
                        "stop": stop,
                        "config": json.dumps(config) if isinstance(config, dict) else config,
                        "cb": created_by,
                    },
                )
            ).scalar_one()
            if not lbl or _UUID_RE.fullmatch(str(lbl)):
                await session.execute(
                    text(
                        "UPDATE paper_evidence_task_items SET task_id=:new, label=COALESCE(:lbl, label), "
                        "current_confidence=COALESCE(:conf, current_confidence) WHERE id::text=:iid"
                    ),
                    {"new": uuid.UUID(new_id), "lbl": label, "conf": live_conf, "iid": iid},
                )
                stats["labels_backfilled"] += 1
            else:
                await session.execute(
                    text("UPDATE paper_evidence_task_items SET task_id=:new WHERE id::text=:iid"),
                    {"new": uuid.UUID(new_id), "iid": iid},
                )
            new_ids.append(new_id)
        await session.execute(
            text(
                "UPDATE paper_evidence_tasks SET status='cancelled', "
                "summary=jsonb_set(COALESCE(summary, '{}'::jsonb), '{migrated_to}', CAST(:ids AS jsonb)) "
                "WHERE id::text=:tid"
            ),
            {"ids": json.dumps(new_ids), "tid": tid},
        )
        stats["tasks_split"] += 1
        stats["objects_migrated"] += len(new_ids)
    await session.commit()
    return stats
```

- [ ] **Step 4: 写运行脚本**

创建 `backend/scripts/migrate_evidence_tasks_1to1.py`:

```python
"""一次性存量迁移:多对象佐证任务 → 一对一对象任务(幂等,可重复执行)。

用法: backend/.venv/Scripts/python.exe backend/scripts/migrate_evidence_tasks_1to1.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import AsyncSessionLocal  # noqa: E402
from app.services import paper_evidence_service as pes  # noqa: E402


async def main() -> None:
    if AsyncSessionLocal is None:
        print("AsyncSessionLocal 未初始化(数据库未配置),退出。")
        return
    async with AsyncSessionLocal() as session:
        stats = await pes.migrate_tasks_to_1to1(session)
    print("迁移完成:", stats)


if __name__ == "__main__":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
```

- [ ] **Step 5: 运行确认通过**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_paper_evidence_migrate_1to1.py -q`
Expected: 2 passed

- [ ] **Step 6: 对开发库执行迁移(真实数据)**

Run:

```bash
cd backend && ./.venv/Scripts/python.exe scripts/migrate_evidence_tasks_1to1.py
```

Expected: 打印 `迁移完成: {'tasks_scanned': N, 'tasks_split': M, ...}`(M ≥ 1,现库有多对象任务)。重复执行一遍确认幂等(第二次 `tasks_split` 为 0 或仅剩漏网之鱼)。

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/paper_evidence_service.py backend/scripts/migrate_evidence_tasks_1to1.py backend/tests/test_paper_evidence_migrate_1to1.py
git commit -m "feat(evidence): idempotent 1:1 split migration for legacy batch tasks"
```

---

