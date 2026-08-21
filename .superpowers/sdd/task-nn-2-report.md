# Task NN-2 Report: 创建任务时判定靶标,非神经直接标记

## Status: DONE

## TDD Evidence

### Step 1 — RED (test added, before implementation)

Added `TestBatchStateMachine.test_non_neural_target_marked_without_search` and module-level helper `_read_item_outcome` to `backend/tests/test_paper_evidence_batch.py`.

### Step 2 — RED run

Command:
```
cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_paper_evidence_batch.py -q
```

Output (tail):
```
E           AttributeError: <module 'app.services.paper_evidence_service' ...> does not have the attribute '_classify_item_target'
=========================== short test summary info ===========================
FAILED tests/test_paper_evidence_batch.py::TestBatchStateMachine::test_non_neural_target_marked_without_search
1 failed, 5 passed in 4.57s
```

Expected failure confirmed: exactly the brief-predicted AttributeError; other 5 tests unaffected.

### Step 3 — GREEN (implementation, verbatim from brief)

`backend/app/services/paper_evidence_service.py`:
1. Top import: `from app.services.evidence_target_classifier import classify_target`
2. New `_classify_item_target(session, target_type, target_id)` before `create_batch_task` — queries `mirror_region_connections.target_region_name_cn/en` for connection/projection, returns `unknown` for other types or missing mirror rows, else delegates to `classify_target`.
3. `create_batch_task` per-object loop replaced per brief: after `_batch_scope_label`, classify target → `preprocess_outcome = "non_neural_target"` if `non_neural` else `None`; item INSERT now includes `preprocess_outcome` column (param `:po`, status param `:status` = 'pending'); audit `after_data` gains `non_neural_target: True` and reason text when marked.

### Step 4 — Regression run

Command:
```
cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_paper_evidence_batch.py tests/test_paper_evidence_batch_phase4.py -q
```

Output:
```
................                                                         [100%]
16 passed in 14.63s
```

All 16 tests pass (6 in batch file incl. new test + 10 phase4). Existing tests unaffected — they do not mock `_classify_item_target`, real implementation hits `mirror_region_connections` with random UUIDs that have no mirror rows → `unknown` → `preprocess_outcome=None`, preserving prior behavior.

## Commit

- SHA: `3724925`
- Subject: `feat(evidence): mark non-neural target items as structurally non-existent at creation`
- Files in commit (only the two brief-named files):
  - `backend/app/services/paper_evidence_service.py` (+44/-5)
  - `backend/tests/test_paper_evidence_batch.py` (+35)
- Branch: `codex/ontology-evidence` (unchanged)

## Concerns

- None blocking. Notes:
  - Brief mentions placing the helper "near `_seed_items`"; `_seed_items` does not exist in `test_paper_evidence_batch.py` (grep across `backend/tests` found no matches), so `_read_item_outcome` was placed with the other module-level read helpers next to `_read_task_items`.
  - `preprocess_outcome` column confirmed present via `migrations/20260807_paper_evidence_v8.sql` (VARCHAR(32); `"non_neural_target"` fits).
  - Wording of the audit reason line is verbatim from brief.
