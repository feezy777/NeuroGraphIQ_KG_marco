### Task 4: 路由调度适配 + phase4/scale/live_fields 测试更新

**Files:**
- Modify: `backend/app/routers/ontology.py`(POST /evidence/batch,约 979-1010 行)
- Modify: `backend/app/services/paper_evidence_service.py`(新增 `execute_paper_evidence_batch_background_many`)
- Test: `backend/tests/test_paper_evidence_batch_phase4.py`、`backend/tests/test_paper_evidence_batch_scale.py`、`backend/tests/test_paper_evidence_live_fields.py`

**Interfaces:**
- Consumes: Task 3 的 `create_batch_task` 新返回(`task_ids`)
- Produces: `execute_paper_evidence_batch_background_many(task_ids: list[str]) -> None`

- [ ] **Step 1: 新增批量执行入口**

在 `execute_paper_evidence_batch_background`(约 3699 行)之后新增:

```python
async def execute_paper_evidence_batch_background_many(task_ids: list[str]) -> None:
    """逐个执行对象任务(单任务内部已有异常兜底,循环保证一个失败不阻断其余)。"""
    for tid in task_ids:
        await execute_paper_evidence_batch_background(tid)
```

- [ ] **Step 2: 修改路由**

`backend/app/routers/ontology.py` 的 `paper_evidence_batch_create` 中,将:

```python
        background_tasks.add_task(pes.materialize_task_items_background, result["task_id"])
        if not body.start_paused:
            background_tasks.add_task(pes.execute_paper_evidence_batch_background, result["task_id"])
        return {**result, "auto_started": not body.start_paused}
```

替换为:

```python
        if result["task_ids"] and not body.start_paused:
            background_tasks.add_task(pes.execute_paper_evidence_batch_background_many, result["task_ids"])
        return {**result, "auto_started": not body.start_paused}
```

(create 已同步写入 item,不再调度物化;execute 内部对已存在 item 幂等。)

- [ ] **Step 3: 更新 phase4 测试**

`backend/tests/test_paper_evidence_batch_phase4.py` 的 `_make_task` 改为(删除 create 后的补插 item 循环):

```python
async def _make_task(ids, scope="low_confidence", limit=10):
    with (
        patch.object(pes, "_resolve_scope_ids", new=AsyncMock(return_value=ids)),
        patch.object(pes, "_resolve_scope_ids_low_confidence", new=AsyncMock(return_value=ids)),
        patch.object(pes, "_batch_scope_label", new=AsyncMock(side_effect=lambda s, tt, oid: (f"t-{oid}", 0.2))),
    ):
        async with AsyncSessionLocal() as s:
            return await pes.create_batch_task(
                s, target_type="connection", scope=scope, mode="function",
                max_papers_per_object=3, created_by="test", limit=limit, name="Phase4 task",
                granularity_level="macro", confidence_lt=0.5,
                target_ids=ids if scope == "selected" else None,
            )
```

`test_batch_preprocessing_never_attaches_and_keeps_confidence` 改为单对象口径:

```python
def test_batch_preprocessing_never_attaches_and_keeps_confidence():
    ids = [str(uuid.uuid4())]
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
                assert len(items) == 1
                assert items[0][0] == "awaiting_review"
                assert items[0][1] == "evidence_found"
                assert items[0][2] == 1
                assert items[0][3]
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
                assert dp == 1
                st = (
                    await s.execute(
                        text("SELECT status, review_status, awaiting_review_items FROM paper_evidence_tasks WHERE id::text=:tid"),
                        {"tid": task_id},
                    )
                ).first()
                assert st[0] == "completed"
                assert st[1] == "in_review"
                assert st[2] == 1
        _run(check())
    finally:
        _run(_cleanup(task_id))
```

其余 phase4 用例均为单对象(`ids = [str(uuid.uuid4())]`),逻辑不变;仅 `_make_task` 变化使其通过。

- [ ] **Step 4: 更新 scale 测试**

`test_filter_snapshot_and_preview_and_max_limit` 的 create 断言消息不变(新实现保留「单任务最大」文案),无需改。

`test_large_scope_materialization_checkpoint_and_idempotency` 整体替换为(物化被创建时快照取代):

```python
def test_1to1_create_writes_snapshot_and_materialize_is_noop():
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
                task_ids = task["task_ids"]
                assert len(task_ids) >= 6
                first = task_ids[0]
                await pes.materialize_task_items_background(first)
                for tid in task_ids:
                    row = (
                        await s.execute(
                            text(
                                "SELECT total_items, materialized_target_count, target_id IS NOT NULL "
                                "FROM paper_evidence_tasks WHERE id::text=:tid"
                            ),
                            {"tid": tid},
                        )
                    ).first()
                    assert row[0] == 1
                    assert row[1] == 1
                    assert row[2] is True
                    count = (
                        await s.execute(
                            text("SELECT COUNT(*) FROM paper_evidence_task_items WHERE task_id::text=:tid"),
                            {"tid": tid},
                        )
                    ).scalar_one()
                    assert count == 1
                    await s.execute(text("DELETE FROM paper_evidence_tasks WHERE id::text=:tid"), {"tid": tid})
                await s.commit()
            cfg.paper_evidence_max_task_items = old
        _run(case())
    finally:
        _run(_cleanup_connections(cids))
```

`test_materialization_cancel_stops_and_keeps_generated` 整体替换为:

```python
def test_cancel_single_object_task():
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
                task_ids = task["task_ids"]
                assert len(task_ids) >= 4
                first = task_ids[0]
                await pes.cancel_batch_task(s, first)
                st = (
                    await s.execute(
                        text("SELECT status FROM paper_evidence_tasks WHERE id::text=:tid"),
                        {"tid": first},
                    )
                ).first()
                assert st[0] == "cancelled"
                for tid in task_ids:
                    await s.execute(text("DELETE FROM paper_evidence_tasks WHERE id::text=:tid"), {"tid": tid})
                await s.commit()
            cfg.paper_evidence_max_task_items = old
        _run(case())
    finally:
        _run(_cleanup_connections(cids))
```

`test_versions_written_on_items`、`test_draft_revision_optimistic_concurrency` 保持 create 路径(单对象,item 由创建路径自动写入),删除其 create 后的补插 INSERT 循环;两者的清理段改为删除全部 task_ids:

```python
                for tid in task["task_ids"]:
                    await s.execute(text("DELETE FROM paper_evidence_tasks WHERE id::text=:tid"), {"tid": tid})
```

`test_dual_worker_skip_locked_no_overlap` 不再依赖 create(一对一后单任务只有 1 个 item,无法测 skip-locked),整体替换为直接 SQL 建一个含 20 items 的任务:

```python
def test_dual_worker_skip_locked_no_overlap():
    n = 20
    ids = [str(uuid.uuid4()) for _ in range(n)]

    async def case():
        async with AsyncSessionLocal() as s:
            task_id = (
                await s.execute(
                    text(
                        "INSERT INTO paper_evidence_tasks "
                        "(target_type, scope, mode, max_papers_per_object, status, total_items) "
                        "VALUES ('connection', 'selected', 'function', 3, 'pending', :n) RETURNING id::text"
                    ),
                    {"n": n},
                )
            ).scalar_one()
            for oid in ids:
                await s.execute(
                    text(
                        "INSERT INTO paper_evidence_task_items (task_id, target_type, target_id, label, status) "
                        "VALUES (:tid, 'connection', :oid, 't', 'pending')"
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
```

- [ ] **Step 5: 更新 live_fields 测试取数解耦**

`backend/tests/test_paper_evidence_live_fields.py` 的 `_make_task` 整体替换为直接 SQL 建任务(该文件测试列表/物化逻辑,不再依赖 create):

```python
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
```

删除该文件中未再使用的 `from unittest.mock import patch`(若 `count_scope_targets` patch 随之消失)。

- [ ] **Step 6: 运行确认通过**

Run:

```bash
cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_paper_evidence_batch_phase4.py tests/test_paper_evidence_batch_scale.py tests/test_paper_evidence_live_fields.py -q
```

Expected: 全部通过(phase4 10 个、scale 6 个、live_fields 11 个)。

- [ ] **Step 7: Commit**

```bash
git add backend/app/routers/ontology.py backend/app/services/paper_evidence_service.py backend/tests/test_paper_evidence_batch_phase4.py backend/tests/test_paper_evidence_batch_scale.py backend/tests/test_paper_evidence_live_fields.py
git commit -m "feat(evidence): route batch create through per-task execution; adapt phase4/scale/live tests"
```

---

