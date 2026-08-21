# Task 4 Report: 路由调度适配 + phase4/scale/live_fields 测试更新

## Status: DONE

## What Was Implemented (per brief, verbatim)

- **Step 1** — `backend/app/services/paper_evidence_service.py`: added `execute_paper_evidence_batch_background_many(task_ids)` after `execute_paper_evidence_batch_background` (loops per-task; single-task function already swallows exceptions so one failure doesn't block the rest).
- **Step 2** — `backend/app/routers/ontology.py` (`paper_evidence_batch_create`): removed the `materialize_task_items_background` / single `execute_paper_evidence_batch_background` scheduling; now schedules `execute_paper_evidence_batch_background_many(result["task_ids"])` when `task_ids` present and not `start_paused`. Materialization is a no-op now (create writes items synchronously; execute is idempotent).
- **Step 3** — `backend/tests/test_paper_evidence_batch_phase4.py`: `_make_task` now returns `create_batch_task` result directly (post-create item INSERT loop removed); `test_batch_preprocessing_never_attaches_and_keeps_confidence` switched to single-object assertions (len==1, dp==1, awaiting_review_items==1).
- **Step 4** — `backend/tests/test_paper_evidence_batch_scale.py`:
  - `test_large_scope_materialization_checkpoint_and_idempotency` → replaced with `test_1to1_create_writes_snapshot_and_materialize_is_noop` (checks each task: total_items==1, materialized_target_count==1, target_id set, 1 item; cleanup deletes all `task_ids`).
  - `test_materialization_cancel_stops_and_keeps_generated` → replaced with `test_cancel_single_object_task`.
  - `test_versions_written_on_items` / `test_draft_revision_optimistic_concurrency`: post-create INSERT loops removed (item written by create path); cleanup loops delete all `task["task_ids"]`.
  - `test_dual_worker_skip_locked_no_overlap` → full replacement building one 20-item task via direct SQL (no longer depends on create).
- **Step 5** — `backend/tests/test_paper_evidence_live_fields.py`: `_make_task` replaced with direct SQL task creation (one task shell, `total_items=len(ids)`, status 'paused'); removed the now-unused `from unittest.mock import patch` (verified via grep that no other `patch` usage remains).
- **Step 6/7** — tests run, commit created.

## Commands Run (actual output)

Three-file run (brief's command):

```
$ cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_paper_evidence_batch_phase4.py tests/test_paper_evidence_batch_scale.py tests/test_paper_evidence_live_fields.py -q
..........................  [100%]
26 passed in 13.11s
```

Note: brief expected "phase4 10 + scale 6 + live_fields 11 = 27", but live_fields contains 10 test functions (verified via `--collect-only`), so the real total is 26 and all pass. The "11" in the brief appears to be a miscount, not a missing test.

Regression sweep beyond the brief (router change affects API-level tests):

```
$ ./.venv/Scripts/python.exe -m pytest tests/test_paper_evidence*.py -q
210 passed, 4 warnings in 20.86s
```

## Files Changed / Committed

Commit: `997dbf0` — `feat(evidence): route batch create through per-task execution; adapt phase4/scale/live tests` (5 files changed, 613 insertions(+), 133 deletions(-))

- backend/app/routers/ontology.py
- backend/app/services/paper_evidence_service.py
- backend/tests/test_paper_evidence_batch_phase4.py
- backend/tests/test_paper_evidence_batch_scale.py
- backend/tests/test_paper_evidence_live_fields.py (was untracked; now added)

## Concerns / Notes

1. **Brief test-count mismatch**: expected 27 passed, actual 26 — live_fields has 10 test functions, not 11. All 26 pass; nothing missing.
2. **Pre-existing uncommitted work rode along in the commit**: `backend/app/routers/ontology.py` already had ~198 lines of uncommitted changes from earlier tasks (multi-source search in `paper_evidence_search`, `/evidence/extraction-runs` endpoints, `/evidence/translate-batch`, S6 `/evidence/batch/{task_id}/items/resolve`, `EvidenceReviewError`/review-history/rescore imports). The brief explicitly named this file in its exact `git add` command, so it was committed whole per instructions. The Task-4-specific change within it is only the 4-line scheduling swap (verified in the diff). If those other hunks belonged to a different task's commit, that task's commit will now be empty of those hunks.
3. No failures beyond brief scope were encountered; no fixes beyond the brief were needed.
