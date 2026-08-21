# Task nn-3 Report: 后台处理跳过已标记 item(非神经靶标治理的检索跳过)

**Status:** DONE_WITH_CONCERNS
**Commit:** `0a18414` feat(evidence): skip paper search for structurally-impossible items (branch `codex/ontology-evidence`)

## Implementation

`backend/app/services/paper_evidence_service.py` — `_process_batch_item_v2` 开头(约 5147 行),在 `stage = "search"` + `try:` 之后、原 `context = await build_retrieval_context(` 行之前,逐字插入 brief 代码块:

- 查询 `paper_evidence_task_items.preprocess_outcome`;若为 `'non_neural_target'`,调 `_set_item_stage(... "awaiting_review", preprocess_outcome="non_neural_target", finished_preprocessing_at="SQL:now()")` 并 `return`(不检索、不调 LLM)。
- `_set_item_stage` 内部 commit(5005-5018 行),故提前 return 的终态持久化。
- 原 `context = await build_retrieval_context(` 行保留,缩进不变。

`backend/tests/test_paper_evidence_batch.py` — `TestBatchStateMachine` 新增 `test_non_neural_item_skips_search`。

## TDD Evidence

### RED(先加测试,无实现)

```
$ ./.venv/Scripts/python.exe -m pytest tests/test_paper_evidence_batch.py -q -k non_neural_item_skips_search
>           assert items[0][1] == "awaiting_review"
E           AssertionError: assert 'pending' == 'awaiting_review'
E             - awaiting_review
E             + pending
FAILED tests/test_paper_evidence_batch.py::TestBatchStateMachine::test_non_neural_item_skips_search
1 failed, 6 deselected in 0.23s
```

(注:brief 预期 RED 形态为 `search_papers.await_count > 0`;实际 RED 路径中 `build_search_query` 对测试随机 UUID 抛异常(last_error_code='UNKNOWN'),item 被回置 `pending` 重试,`search_papers` 未被调用(await_count=0,已用调试脚本确认)。RED 仍成立——测试在无实现时失败。)

### GREEN(实现后)

```
$ ./.venv/Scripts/python.exe -m pytest tests/test_paper_evidence_batch.py -q
.......                                                                  [100%]
7 passed in 2.50s
```

commit 后复跑:`7 passed in 4.09s`。两文件工作树状态 clean。

## Concerns(对 brief 测试代码的两处最小修正)

brief 的测试代码原样跑不通,做了两处最小修正(均不影响测试意图),已与 brief 实现块逐字一致:

1. **`start_paused=True` → `start_paused=False`**:任务以 `paused` 状态创建时,`_run_batch_loop` 在 while 循环开头 `if state in ("cancelled", "paused"): return` 直接退出,item 永远停在 `pending`——即使实现正确,测试也无法通过(已用调试脚本实证:创建后 task status='paused',循环不处理任何 item)。同文件既有跑循环的测试(`test_batch_loop_preprocesses_to_awaiting_review_without_formal_attach`)均用 `start_paused=False`。
2. **`pes.search_papers.await_count` 断言移入 patch 上下文内**:brief 在 `with patch(...)` 块结束后读取 `pes.search_papers.await_count`,patch 已撤销,`pes.search_papers` 恢复为真实函数 → `AttributeError: 'function' object has no attribute 'await_count'`。现将 item 读取与两条断言移入 with 块内(断言语句本身逐字保留)。

## Files

- Modified: `backend/app/services/paper_evidence_service.py`
- Modified: `backend/tests/test_paper_evidence_batch.py`

(未触碰工作树其他无关改动;commit 仅含上述两文件,40 insertions,0 deletions。)
