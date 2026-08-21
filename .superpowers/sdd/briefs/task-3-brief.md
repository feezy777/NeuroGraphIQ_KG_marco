### Task 3: `create_batch_task` 一对一重写 + 更新状态机测试

**Files:**
- Modify: `backend/app/services/paper_evidence_service.py`(替换 5605 行的 `create_batch_task`;删除 2511 与 2762 行的两个旧同名定义)
- Test: `backend/tests/test_paper_evidence_batch.py`

**Interfaces:**
- Consumes: `_resolve_scope_ids`、`_resolve_scope_ids_low_confidence`、`_build_filter_clause`、`_batch_scope_label`、`_write_audit`、`get_settings`(均已在模块内)
- Produces: `create_batch_task(...) -> {"task_id": <首个>, "task_ids": [<全部>], "target_count": int, "skipped_active_targets": int}`(Task 4/7 使用)

- [ ] **Step 1: 定位三处同名定义并删除前两处**

Run: `grep -n "async def create_batch_task" backend/app/services/paper_evidence_service.py`
Expected: 三处(约 2511 / 2762 / 5605)。

删除前两处:
- 2511 行版本:从 `async def create_batch_task(` 起到 `return {"task_id": task_id, "target_count": len(ids)}`(其后的 `async def run_batch_step` 保留)。
- 2762 行版本:从 `async def create_batch_task(` 起到 `return {"task_id": task_id, "target_count": len(fresh_ids), "skipped_active_targets": len(busy)}`(其后的 `async def _update_task_totals` 保留)。

保留第三处(5605 行版本)待 Step 3 重写。

- [ ] **Step 2: 写失败测试(先改测试,验证新协议)**

`backend/tests/test_paper_evidence_batch.py` 的 `TestBatchStateMachine._make_task` 改为(删除 `_seed_items` 调用,items 由创建路径写入):

```python
    def _make_task(self, target_ids=None, start_paused=False):
        target_ids = target_ids or _ids(3)
        with (
            patch.object(pes, "_resolve_scope_ids", new=AsyncMock(return_value=target_ids)),
            patch.object(pes, "_resolve_scope_ids_low_confidence", new=AsyncMock(return_value=target_ids)),
            patch.object(
                pes,
                "_batch_scope_label",
                new=AsyncMock(side_effect=lambda s, tt, oid: (f"target-{oid}", 0.4)),
            ),
        ):
            return _run(_make_task_inner(target_ids=target_ids, start_paused=start_paused))
```

`test_create_task_creates_items_with_labels` 整体替换为:

```python
    def test_create_task_creates_one_task_per_object_with_labels(self):
        ids = _ids(2)
        result = self._make_task(ids)
        task_ids = result["task_ids"]
        try:
            assert len(task_ids) == 2
            assert result["target_count"] == 2
            assert result["task_id"] == task_ids[0]
            for tid in task_ids:
                row = _run(_read_task_row(tid))
                assert row[0] == "pending"
                assert row[1] == 1  # total_items = 1
                items = _run(_read_task_items(tid))
                assert len(items) == 1
                assert items[0][1] == "pending"
                assert items[0][0].startswith("target-")
        finally:
            _run(_cleanup(task_ids))
```

`test_batch_loop_preprocesses_to_awaiting_review_without_formal_attach` 整体替换为:

```python
    def test_batch_loop_preprocesses_to_awaiting_review_without_formal_attach(self):
        ids = _ids(2)
        result = self._make_task(ids)
        task_ids = result["task_ids"]
        try:
            with (
                patch.object(pes, "pack_target_info", new=AsyncMock(return_value={
                    "function_term": "memory consolidation",
                    "query": '"memory consolidation"',
                    "info": {},
                })),
                patch.object(pes, "build_retrieval_context", new=AsyncMock(return_value={
                    "claim_text": "memory consolidation",
                    "structured_claim": {},
                    "object_type": "connection",
                    "granularity": "macro",
                    "source_region": "Hippocampus",
                    "target_region": "Prefrontal cortex",
                    "source_region_synonyms": [],
                    "target_region_synonyms": [],
                    "function_terms": ["memory consolidation"],
                    "function_synonyms": [],
                    "relation_keywords": ["projection"],
                })),
                patch.object(pes, "search_papers", new=AsyncMock(return_value=[_paper()])),
                patch.object(pes, "fetch_fulltext", new=AsyncMock(return_value="")),
                patch.object(pes, "verify_paper", new=AsyncMock(return_value=_paper())),
                patch.object(pes.pfs, "fetch_oa_fulltext_xml", new=AsyncMock(return_value="")),
                patch.object(pes, "build_search_query", new=AsyncMock(return_value='"memory consolidation"')),
                patch.object(pes, "extract_passage_from_paper", new=AsyncMock(return_value=_extraction())),
                patch.object(pes, "semantic_filter_papers", new=AsyncMock(side_effect=lambda papers, ctx: (papers, []))),
            ):
                for tid in task_ids:
                    _run(_run_loop(tid))
            for tid in task_ids:
                task = _run(_read_task_row(tid))
                assert task[0] == "completed"
                assert task[1] == 1
                assert task[2] == 1
                items = _run(_read_task_items(tid))
                assert all(i[1] == "awaiting_review" for i in items)
                assert all(i[2] and i[3] and i[4] for i in items)
            ev_count = _run(_count_evidence(ids))
            assert ev_count == 0
        finally:
            _run(_cleanup(task_ids))
            _run(_cleanup_batch_paper())
```

`test_pause_resume_cancel` 改为单对象任务:

```python
    def test_pause_resume_cancel(self):
        result = self._make_task(_ids(1))
        task_id = result["task_id"]
        try:
            _run(_pause(task_id))
            assert _run(_read_status(task_id)) == "paused"
            _run(_resume(task_id))
            assert _run(_read_status(task_id)) == "pending"
            _run(_cancel(task_id))
            assert _run(_read_status(task_id)) == "cancelled"
            assert _run(_count_skipped(task_id)) == 1
        finally:
            _run(_cleanup([task_id]))
```

删除模块级 `_seed_items` 函数(约 239 行,已无调用方)。

- [ ] **Step 3: 运行确认失败**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_paper_evidence_batch.py -q`
Expected: FAIL(`result["task_ids"]` 不存在 / KeyError)

- [ ] **Step 4: 重写 create_batch_task(5605 行版本)**

将 5605 行的 `create_batch_task` 整体替换为:

```python
async def create_batch_task(
    session: AsyncSession,
    *,
    target_type: str,
    scope: str,
    mode: str,
    max_papers_per_object: int,
    created_by: str | None = None,
    limit: int = 200,
    start_paused: bool = False,
    name: str | None = None,
    granularity_level: str | None = None,
    only_oa: bool = False,
    confidence_lt: float | None = None,
    stop_after_strong_support: bool = False,
    target_ids: list[str] | None = None,
    filter_snapshot: dict | None = None,
) -> dict:
    """一对一佐证任务创建:每个对象生成一个独立任务(1 任务 = 1 item)。

    - 圈选(selected / low_confidence / filter)与单任务最大守卫语义不变;
    - busy 去重统一在创建时完成:跳过已有活动任务的对象并计数返回;
    - item 创建时直接写入实时 label/current_confidence 快照,不依赖物化流程。
    """
    if target_type not in TARGET_MODELS:
        raise ValueError(f"unsupported target_type: {target_type}")
    cfg = get_settings()
    scope_type = "selected" if scope == "selected" else "filter"
    snapshot = (
        {
            "target_type": target_type,
            "granularity_level": granularity_level,
            "target_ids": target_ids or [],
        }
        if scope == "selected"
        else filter_snapshot
        or {
            "target_type": target_type,
            "granularity_level": granularity_level,
            "confidence_lt": confidence_lt if scope == "low_confidence" else None,
        }
    )
    if target_ids:
        ids = target_ids
    elif scope == "low_confidence":
        ids = await _resolve_scope_ids_low_confidence(session, target_type, confidence_lt, limit)
    else:
        where, params = _build_filter_clause(target_type, snapshot)
        rows = (
            await session.execute(
                text(
                    f"SELECT id::text FROM {TARGET_MODELS[target_type].__tablename__} "
                    f"WHERE {where} ORDER BY created_at DESC LIMIT :lim"
                ),
                {**params, "lim": limit},
            )
        ).all()
        ids = [str(r[0]) for r in rows]
    if not ids:
        raise ValueError("no targets matched scope")
    if len(ids) > cfg.paper_evidence_max_task_items:
        raise ValueError(
            f"当前筛选结果共 {len(ids)} 条，单任务最大 {cfg.paper_evidence_max_task_items} 条，"
            "请进一步筛选或拆分任务。"
        )
    busy = set(
        (
            await session.execute(
                text(
                    "SELECT target_id::text FROM paper_evidence_task_items "
                    "WHERE target_type = :tt AND target_id::text = ANY(:ids) "
                    "AND status IN ('pending','searching','paper_found','extracting','awaiting_review')"
                ),
                {"tt": target_type, "ids": ids},
            )
        ).scalars().all()
    )
    fresh_ids = [oid for oid in ids if oid not in busy]
    if not fresh_ids:
        raise ValueError("all matched targets already have an active evidence task")
    cfg_json = json.dumps(
        {"deepseek_concurrency": DEEPSEEK_CONCURRENCY, "europepmc_concurrency": EUROPE_PMC_CONCURRENCY},
        ensure_ascii=False,
    )
    status = "paused" if start_paused else "pending"
    task_ids: list[str] = []
    for oid in fresh_ids:
        label, conf = await _batch_scope_label(session, target_type, uuid.UUID(oid))
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
                "(task_id, target_type, target_id, label, current_confidence, status) "
                "VALUES (:tid, :tt, :oid, :label, :conf, 'pending')"
            ),
            {"tid": task_id, "tt": target_type, "oid": uuid.UUID(oid), "label": label, "conf": conf},
        )
        await _write_audit(
            session,
            action_type="EVIDENCE_TASK_CREATE",
            entity_type="evidence_task",
            entity_id=uuid.UUID(task_id),
            after_data={"target_type": target_type, "target_id": oid, "scope": scope, "mode": mode},
            operator_id=created_by,
            reason="single-object evidence task created",
        )
        task_ids.append(task_id)
    await session.commit()
    return {
        "task_id": task_ids[0],
        "task_ids": task_ids,
        "target_count": len(task_ids),
        "skipped_active_targets": len(busy),
    }
```

- [ ] **Step 5: 运行确认通过**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_paper_evidence_batch.py -q`
Expected: 5 passed(`TestBatchStateMachine` 4 个 + `TestReviewQueueStatsAudit` 1 个)

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/paper_evidence_service.py backend/tests/test_paper_evidence_batch.py
git commit -m "feat(evidence): 1:1 object tasks — create_batch_task emits one task per object"
```

---

