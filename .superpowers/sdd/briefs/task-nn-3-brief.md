### Task 3: 后台处理跳过已标记 item(等效不跑检索)

**Files:**
- Modify: `backend/app/services/paper_evidence_service.py`(`_process_batch_item_v2` 开头,约 5093 行)

**Interfaces:**
- Consumes: Task 2 写入的 `preprocess_outcome='non_neural_target'`
- Produces: 已标记 item 处理时直接置 `awaiting_review` 完成(状态推进、无检索/LLM 调用)

- [ ] **Step 1: 写失败测试**

在 `backend/tests/test_paper_evidence_batch.py` 追加(验证已标记 item 不触发检索调用):

```python
    def test_non_neural_item_skips_search(self):
        oid = str(uuid.uuid4())
        with (
            patch.object(pes, "_resolve_scope_ids", new=AsyncMock(return_value=[oid])),
            patch.object(pes, "_resolve_scope_ids_low_confidence", new=AsyncMock(return_value=[oid])),
            patch.object(pes, "_batch_scope_label", new=AsyncMock(side_effect=lambda s, tt, o: (f"X → 侧脑室", 0.1))),
            patch.object(pes, "_classify_item_target", new=AsyncMock(return_value="non_neural")),
        ):
            result = _run(_make_task_inner(target_ids=[oid], start_paused=True))
        task_id = result["task_id"]
        try:
            with (
                patch.object(pes, "build_retrieval_context", new=AsyncMock(return_value={})),
                patch.object(pes, "search_papers", new=AsyncMock(return_value=[])),
                patch.object(pes, "pack_target_info", new=AsyncMock(return_value={})),
            ):
                _run(_run_loop(task_id))
            # 已标记 item:不触发检索,直接 awaiting_review
            items = _run(_read_task_items(task_id))
            assert items[0][1] == "awaiting_review"
            assert pes.search_papers.await_count == 0  # type: ignore[attr-defined]
        finally:
            _run(_cleanup([task_id]))
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_paper_evidence_batch.py -q -k non_neural_item_skips_search`
Expected: FAIL(search_papers 被调用,await_count > 0)

- [ ] **Step 3: 实现**

`_process_batch_item_v2` 的 `stage = "search"` 之后、`build_retrieval_context` 之前插入:

```python
        stage = "search"
        try:
            # 非神经靶标:已标记结构性不存在,直接完成(不检索、不调 LLM)
            marked_row = (
                await session.execute(
                    text(
                        "SELECT preprocess_outcome FROM paper_evidence_task_items WHERE id::text = :iid"
                    ),
                    {"iid": item_id},
                )
            ).first()
            if marked_row is not None and marked_row[0] == "non_neural_target":
                await _set_item_stage(
                    session, item_id, "awaiting_review",
                    preprocess_outcome="non_neural_target",
                    finished_preprocessing_at="SQL:now()",
                )
                return
            context = await build_retrieval_context(
```

(原 `context = await build_retrieval_context(` 行保留,缩进不变。)

- [ ] **Step 4: 运行确认通过**

Run: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_paper_evidence_batch.py -q`
Expected: 全部通过

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/paper_evidence_service.py backend/tests/test_paper_evidence_batch.py
git commit -m "feat(evidence): skip paper search for structurally-impossible items"
```

---

