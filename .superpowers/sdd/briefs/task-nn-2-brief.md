### Task 2: 创建任务时判定靶标,非神经直接标记

**Files:**
- Modify: `backend/app/services/paper_evidence_service.py`(`create_batch_task` per-object 循环,约 5670-5730 行)

**Interfaces:**
- Consumes: Task 1 的 `classify_target`
- Produces: 非神经靶标 item 写入 `preprocess_outcome='non_neural_target'`(Task 3 处理时跳过;Task 4 反向检索不触发)

- [ ] **Step 1: 写失败测试**

在 `backend/tests/test_paper_evidence_batch.py` 的 `TestBatchStateMachine` 追加:

```python
    def test_non_neural_target_marked_without_search(self):
        oid = str(uuid.uuid4())
        # 靶标名含「脑室」→ 创建即标记结构性不存在
        with (
            patch.object(pes, "_resolve_scope_ids", new=AsyncMock(return_value=[oid])),
            patch.object(pes, "_resolve_scope_ids_low_confidence", new=AsyncMock(return_value=[oid])),
            patch.object(
                pes,
                "_batch_scope_label",
                new=AsyncMock(side_effect=lambda s, tt, o: (f"X → 侧脑室", 0.1)),
            ),
            patch.object(pes, "_classify_item_target", new=AsyncMock(return_value="non_neural")),
        ):
            result = _run(_make_task_inner(target_ids=[oid], start_paused=True))
        task_id = result["task_id"]
        try:
            items = _run(_read_task_items(task_id))
            assert len(items) == 1
            assert items[0][0].startswith("X → 侧脑室")
            # 标记结构性不存在
            outcome = _run(_read_item_outcome(task_id))
            assert outcome == "non_neural_target"
        finally:
            _run(_cleanup([task_id]))
```

并新增 helper(模块级,`_seed_items` 附近):

```python
async def _read_item_outcome(task_id):
    async with AsyncSessionLocal() as s:
        return (
            await s.execute(
                text("SELECT preprocess_outcome FROM paper_evidence_task_items WHERE task_id::text=:tid"),
                {"tid": task_id},
            )
        ).scalar_one()
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_paper_evidence_batch.py -q`
Expected: FAIL(AttributeError:`module 'paper_evidence_service' has no attribute '_classify_item_target'`)

- [ ] **Step 3: 实现**

`paper_evidence_service.py` 顶部 import:

```python
from app.services.evidence_target_classifier import classify_target
```

`create_batch_task` 的 per-object 循环(当前 `for oid in fresh_ids:` 内,`_batch_scope_label` 之后)插入靶标判定:

```python
    for oid in fresh_ids:
        label, conf = await _batch_scope_label(session, target_type, uuid.UUID(oid))
        # 非神经靶标(脑室/脑脊液/脑膜等):直接标记结构性不存在,不进入论文检索
        target_kind = await _classify_item_target(session, target_type, uuid.UUID(oid))
        preprocess_outcome = "non_neural_target" if target_kind == "non_neural" else None
        task_id = (
            await session.execute(
                text(
                    "INSERT INTO paper_evidence_tasks "
                    "(target_type, target_id, scope, scope_type, mode, max_papers_per_object, status, created_by, "
                    "total_items, config, name, granularity_level, only_oa, confidence_lt, "
                    "stop_after_strong_support, review_status, filter_snapshot, estimated_target_count, "
                    "materialization_status, materialized_target_count) "
                    "VALUES (:tt, :oid, :scope, :scope_type, :mode, :maxp, :status, :cb, 1, CAST(:cfg AS jsonb), "
                    ":name, :gl, :only_oa, :clt, :stop, 'not_started', CAST(:fs AS jsonb), 1, 'completed', 1) "
                    "RETURNING id::text"
                ),
                {
                    "tt": target_type,
                    "oid": uuid.UUID(oid),
                    "scope": scope,
                    "scope_type": scope_type,
                    "mode": mode,
                    "maxp": max_papers_per_object,
                    "status": status,
                    "cb": created_by,
                    "cfg": cfg_json,
                    "name": name,
                    "gl": granularity_level,
                    "only_oa": only_oa,
                    "clt": confidence_lt,
                    "stop": stop_after_strong_support,
                    "fs": json.dumps(snapshot, ensure_ascii=False),
                },
            )
        ).scalar_one()
        await session.execute(
            text(
                "INSERT INTO paper_evidence_task_items "
                "(task_id, target_type, target_id, label, current_confidence, status, preprocess_outcome) "
                "VALUES (:tid, :tt, :oid, :label, :conf, :status, :po)"
            ),
            {
                "tid": task_id, "tt": target_type, "oid": uuid.UUID(oid), "label": label, "conf": conf,
                "status": "pending", "po": preprocess_outcome,
            },
        )
        await _write_audit(
            session,
            action_type="EVIDENCE_TASK_CREATE",
            entity_type="evidence_task",
            entity_id=uuid.UUID(task_id),
            after_data={
                "target_type": target_type, "target_id": oid, "scope": scope, "mode": mode,
                **({"non_neural_target": True} if preprocess_outcome == "non_neural_target" else {}),
            },
            operator_id=created_by,
            reason=(
                "single-object evidence task created; target is non-neural structure, marked structurally non-existent"
                if preprocess_outcome == "non_neural_target"
                else "single-object evidence task created"
            ),
        )
        task_ids.append(task_id)
```

`create_batch_task` 之前新增 `_classify_item_target`(查镜像行靶标名 → classify):

```python
async def _classify_item_target(
    session: AsyncSession, target_type: str, target_id: uuid.UUID
) -> str:
    """查镜像行靶标名并分类:connection/projection 取 target_region 名,其余类型返回 unknown。"""
    if target_type not in ("connection", "projection"):
        return "unknown"
    row = (
        await session.execute(
            text(
                "SELECT target_region_name_cn, target_region_name_en "
                "FROM mirror_region_connections WHERE id = :oid"
            ),
            {"oid": target_id},
        )
    ).first()
    if row is None:
        return "unknown"
    return classify_target(row[0], row[1])
```

- [ ] **Step 4: 运行确认通过**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_paper_evidence_batch.py tests/test_paper_evidence_batch_phase4.py -q`
Expected: 全部通过(原有用例不受影响:`_classify_item_target` 对 mock 的 `_batch_scope_label` 路径返回 unknown)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/paper_evidence_service.py backend/tests/test_paper_evidence_batch.py
git commit -m "feat(evidence): mark non-neural target items as structurally non-existent at creation"
```

---

