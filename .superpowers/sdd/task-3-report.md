# Task 3 Report: `create_batch_task` 一对一重写 + 状态机测试更新

**Status:** DONE

## What Was Implemented

Rewrote `create_batch_task` in `backend/app/services/paper_evidence_service.py` to emit one task per object (1 task = 1 item) and updated the state-machine tests in `backend/tests/test_paper_evidence_batch.py` to the new protocol.

### Service changes (`paper_evidence_service.py`)

- Deleted the two shadowed same-name definitions (formerly ~line 2544, `limit=500` batch version; formerly ~line 2795, multi-item task version). Kept `run_batch_step` and `_update_task_totals` intact after each deletion.
- Replaced the third definition (formerly ~line 5638, now ~line 5513) with the brief's verbatim 1:1 implementation:
  - Resolves ids from `target_ids` / `_resolve_scope_ids_low_confidence` / `_build_filter_clause` (raw SQL over `TARGET_MODELS[target_type].__tablename__`) per scope.
  - Applies max-task guard via `cfg.paper_evidence_max_task_items`.
  - busy dedup at creation time (statuses `pending/searching/paper_found/extracting/awaiting_review`); raises `ValueError("all matched targets already have an active evidence task")` when all busy; returns `skipped_active_targets = len(busy)`.
  - Per fresh object: inserts one `paper_evidence_tasks` row (`total_items=1`, `materialization_status='completed'`, `materialized_target_count=1`, real `target_id`, filter snapshot, config) + one `paper_evidence_task_items` row with live `label`/`current_confidence` from `_batch_scope_label` + `_write_audit` per task.
  - Returns `{"task_id": <first>, "task_ids": [<all>], "target_count": int, "skipped_active_targets": int}`.

### Test changes (`test_paper_evidence_batch.py`)

- `_make_task` helper: removed `_seed_items` call (items now written by the creation path).
- Replaced `test_create_task_creates_items_with_labels` with `test_create_task_creates_one_task_per_object_with_labels` (asserts 2 tasks, `total_items=1`, single item per task with `target-*` label).
- Replaced `test_batch_loop_preprocesses_to_awaiting_review_without_formal_attach` to run the loop per task_id and assert each 1-item task reaches `completed` / `awaiting_review` with snapshots, and no formal evidence written.
- `test_pause_resume_cancel` now uses a single-object task and expects `_count_skipped == 1`.
- Deleted module-level `_seed_items` (no remaining callers).
- `test_failed_item_retry_and_unique_active_target` unchanged and still passes (error message substring `"already have an active evidence task"` preserved).

## TDD Evidence

### RED (after test edits, before implementation)

Command:
```
cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_paper_evidence_batch.py -q
```

Result: `4 failed, 1 passed in 0.35s`

Signature failure, as expected:
```
FAILED test_paper_evidence_batch.py::TestBatchStateMachine::test_create_task_creates_one_task_per_object_with_labels
E   KeyError: 'task_ids'
```
Other failures were consistent with the old third definition (no items written, no `task_ids` key):
- `test_batch_loop_preprocesses_to_awaiting_review_without_formal_attach` — same `KeyError: 'task_ids'`
- `test_pause_resume_cancel` — `assert 0 == 1` (`_count_skipped`; old def writes no items)
- `test_failed_item_retry_and_unique_active_target` — `assert 0 == 1` (`retried`; no items exist)

### GREEN (after Step 4 rewrite)

Command:
```
cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_paper_evidence_batch.py -q
```

Result: `5 passed in 3.11s` (4 × `TestBatchStateMachine` + 1 × `TestReviewQueueStatsAudit`), matching the brief's expectation.

## Files Changed / Committed

- `backend/app/services/paper_evidence_service.py`
- `backend/tests/test_paper_evidence_batch.py`

Commit: `44eedfb` — `feat(evidence): 1:1 object tasks — create_batch_task emits one task per object`
Only these two files were staged (commit stat: 2 files changed, 134 insertions(+), 264 deletions(-)).

## Concerns

- The service-file diff vs HEAD contains exactly the three intended hunks (two deletions + one replacement at ~line 5513); verified via `git diff | grep "^@@"`.
- The test diff includes a pre-existing uncommitted WIP line (`patch.object(pes, "semantic_filter_papers", ...)`) from Task 2's working-tree state; it is also present verbatim in the brief's replacement test code, so the committed file matches the brief exactly.
- Interface note for downstream tasks (Task 4/7): result now includes `task_ids`; other test files / routers calling `create_batch_task` may need adaptation (out of scope here — whole suite not run per instructions).
