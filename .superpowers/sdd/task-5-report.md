# Task 5 Report: 任务列表/详情接口补 display 字段(中英名+置信度,无 N+1)

## Status: DONE_WITH_CONCERNS (tests green; 3 documented deviations from brief)

## What was implemented

- New `_enrich_task_display(session, tasks)` in `backend/app/services/paper_evidence_service.py` (inserted after `_build_capabilities`): batch JOIN per target_type against mirror tables via `TARGET_MODELS`/`_LIVE_NAME_COLUMNS`, reusing Task 2's `mirror_live_display_name_parts` / `mirror_live_confidence`. Fallback chain: mirror_live → snapshot label (non-UUID) → `类型中文 #短ID`; confidence: live → snapshot → None. Emits `target_id`, `display_name_cn/en`, `display_confidence`, `display_name_source`, `display_confidence_source` per task.
- `list_paper_evidence_tasks`: SELECT appended `, target_id::text` (r[23]), dict key `"target_id": r[23]`, return `{"items": await _enrich_task_display(session, items), "total": total}`.
- `get_batch_task` (Phase C version, line ~4007): SELECT appended `, target_id::text` (task[29]), dict rebuilt into `task_dict` + `"target_id": task[29]`, then `task_dict = (await _enrich_task_display(session, [task_dict]))[0]` before return.
- New test file `backend/tests/test_paper_evidence_task_display.py` (4 tests).

## TDD evidence

- RED: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_paper_evidence_task_display.py -q` → 4 failed:
  - tests 1–3 failed with `KeyError: 'target_id'` / `KeyError: 'display_name_cn'` (expected per brief).
  - test 4 failed at its own seed INSERT with `StatementError: A value is required for bind parameter '1'` — SQLAlchemy `text()` parsed `:1}` inside the inline JSON literal `'{"counts":{"pending":1}}'::jsonb` as a bind parameter (brief test code, as-is, cannot run under SQLAlchemy). After fixing (see deviations) it re-RED'd on `assert proxy.selects == 3` with got 2 (no enrich yet), as expected.
- GREEN: same command → `4 passed in 0.73s`.
- Regression: `pytest tests/test_paper_evidence_batch.py tests/test_paper_evidence_live_fields.py tests/test_paper_evidence_work_status.py -q` → `25 passed`.
- Safety net: `pytest tests/ -q -k paper_evidence` → `214 passed`. Full suite: `6 failed, 1449 passed, 9 skipped`; the same 6 failures reproduce with the service change stashed (verified via `git stash push` on the service file), i.e. all pre-existing and unrelated (test_circuit_pack_field_coverage, test_llm_circuit_projection_extraction, test_llm_composite_workflow, test_llm_projection_circuit_extraction x2, test_symptom_query).

## Files changed

- `backend/app/services/paper_evidence_service.py` (modified)
- `backend/tests/test_paper_evidence_task_display.py` (new)

Commit: `d84d890 feat(evidence): task list/detail display fields (cn/en name + confidence, no N+1)` (only the two brief-named files staged).

## Deviations from brief (all required to make the brief's own tests pass; brief-internal contradictions)

1. **`target_id::text` cast in both SELECTs** (brief wrote bare `, target_id`). The column is `UUID` (migration `20260817_evidence_tasks_target_id.sql`) and psycopg3 returns `uuid.UUID` objects, so the brief's own assertion `task["target_id"] == oid` (str) and `oid[:8]` slicing would fail without the cast. Index positions unchanged (r[23] / task[29]).
2. **Snapshot query condition changed.** Brief's `_enrich_task_display` fetches item snapshots only for tasks with NULL target_id. But the brief's `test_missing_mirror_row_falls_back_to_snapshot_then_short_id` seeds tasks WITH target_id and expects snapshot-label fallback, and the regression `test_task_list_no_n1_for_missing_summary` (test_paper_evidence_work_status.py, expects exactly 3 SELECTs with NULL-target_id tasks present) forbids the extra query for old tasks. Implemented: snapshot query runs only for tasks that have a target_id but no live mirror row (post-join), which satisfies the fallback test and keeps both SELECT-count tests at exactly 3. Consequence: legacy NULL-target_id tasks get `display_name_source="missing"` (no items lookup) — brief docstring's old-task path is dropped; recommend the parent decide (e.g. rely on the backfill migration making target_id non-NULL, or revisit).
3. **Test file fixes (test 4)**: (a) inline JSON literal moved to bind param `:sm` to fix the `:1}` bind-param parse error; (b) seed count 5 → 10 so the `limit=10` window contains only seeded tasks — the e2e DB (`neurographiq_kg_v3_mvp1_e2e`) holds 118 leftover legacy tasks, 59 lacking `summary.counts`; with 5 seeds the 5 newest legacy tasks (all `{}` summary) enter the window and trigger the pre-existing fallback-agg SELECT, making the count 4 instead of 3 regardless of implementation.

## Concerns

- Deviation 2 means legacy NULL-target_id tasks (118 in the e2e DB) surface `display_name_* = missing/None` from these endpoints until target_id is backfilled. Frontend (Task 6) should keep its own label fallback for those.
- Full suite has 6 pre-existing failures unrelated to this task (verified against pre-change baseline).
