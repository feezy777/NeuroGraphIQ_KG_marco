# Task 7 Report: 存量拆分迁移 (migrate_tasks_to_1to1 + 脚本 + 测试 + 真实执行)

## Status: DONE (two review-fix rounds applied; final round fixes a Critical found in re-review)

## What was implemented

1. **`backend/app/services/paper_evidence_service.py`** — `migrate_tasks_to_1to1(session)` inserted after `recover_interrupted_batch_tasks`. Final logic:
   - **Split path (multi-object)**: per item, task_id reassignment to the new 1:1 task is **unconditional and decoupled** from backfill (Fix A — prevents items from being stranded on the cancelled old task when the change-guard is false); backfill UPDATE separately guarded by `(label IS NULL OR label = '' OR label ~* :uuid_re OR current_confidence IS NULL) AND (label IS DISTINCT FROM :lbl OR current_confidence IS DISTINCT FROM :conf)`, stats by `rowcount`.
   - **Single-object path**: same guarded backfill (with `label = ''` per Fix B), NULL label written when mirror row is missing (bad UUID labels cleared, real labels kept); `target_id`/`total_items` backfill guarded by `(target_id IS NULL OR target_id <> :oid OR total_items IS DISTINCT FROM 1)`, stats by `rowcount`.
   - Deviation from the original brief: `COALESCE(CAST(:config AS jsonb), '{}'::jsonb)` + `json.dumps(config) if isinstance(config, dict) else config` (psycopg3 cannot adapt a Python dict decoded from the JSONB `config` column).
2. **`backend/scripts/migrate_evidence_tasks_1to1.py`** (new) — one-shot idempotent migration runner.
3. **`backend/tests/test_paper_evidence_migrate_1to1.py`** (new) — 3 tests:
   - `test_split_multi_object_task_and_idempotent` (hardened: NULL label/conf on split items, `stats2["tasks_split"] == 0`, `stats2["labels_backfilled"] == 0`)
   - `test_single_object_task_gets_target_id_backfilled` (hardened: item label IS NULL)
   - `test_split_path_reassigns_real_label_item_with_null_conf` (Fix C regression: real label 'BLA → IL' + NULL conf item must be reassigned to its new task with label kept and conf NULL; UUID-label item cleared to NULL; old task cancelled with `migrated_to` = 2 new task IDs)

## TDD evidence (final round)

- Fix C added → GREEN: `3 passed in 1.05s` (regression test exercises the stranded-item scenario the previous amendment would have failed).

## Dev-DB migration runs (after Fix A/B/C)

- **Run 1**: `{'tasks_scanned': 231, 'tasks_split': 0, 'objects_migrated': 0, 'labels_backfilled': 0, 'target_ids_backfilled': 0}`
- **Run 2 (idempotency)**: identical all-zero stats — as expected by the coordinator.
- Post-run DB integrity: total_tasks=233, cancelled=2, total_items=198, items stranded on cancelled tasks=0.
- Note: all fixable rows were already backfilled by the earlier (old-code) runs; the remaining NULL-conf/NULL-label items have no mirror rows and the 35 NULL-target_id tasks have zero items, so zero actual changes is correct behavior.

## Files changed (committed)

- `backend/app/services/paper_evidence_service.py` (+132)
- `backend/scripts/migrate_evidence_tasks_1to1.py` (new)
- `backend/tests/test_paper_evidence_migrate_1to1.py` (new, +251)

Commit (amended in place, same message): **b7d33a9** `feat(evidence): idempotent 1:1 split migration for legacy batch tasks`
(previous SHAs faf06b2, 376cdaa were amended away.)

## Concerns

None remaining. The critical reassignment bug (Fix A) is covered by the new regression test; dev DB shows 0 items stranded on cancelled tasks.
