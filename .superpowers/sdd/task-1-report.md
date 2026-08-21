# Task 1 Report: 迁移 SQL — paper_evidence_tasks 增加 target_id

## Status: DONE

## What I Did

1. Created `backend/migrations/20260817_evidence_tasks_target_id.sql` with the exact SQL from the brief:
   - `ALTER TABLE paper_evidence_tasks ADD COLUMN IF NOT EXISTS target_id UUID;`
   - `CREATE INDEX IF NOT EXISTS idx_paper_evidence_tasks_target ON paper_evidence_tasks (target_type, target_id);`
2. Applied the migration to the dev DB (`neurographiq_kg_v3_mvp1_e2e` at 127.0.0.1:5432) via `app.database.AsyncSessionLocal`.
3. Verified the column and index; re-ran the migration to confirm idempotency.
4. Committed only the new migration file.

## Commands Run and Actual Output

### Step 2: Apply migration

```bash
cd backend && ./.venv/Scripts/python.exe -c "..."   # verbatim from brief
```

Output:

```
migration applied
```

### Step 3: Verify column

```bash
cd backend && ./.venv/Scripts/python.exe -c "..."   # verbatim from brief
```

Output:

```
target_id column: target_id
```

### Extra verification (idempotency + type + index)

```
col: ('uuid', 'YES')
index: idx_paper_evidence_tasks_target
migration re-applied (idempotent)
```

- `target_id` is `uuid`, nullable (`is_nullable=YES`) — matches brief's "UUID NULL".
- Index `idx_paper_evidence_tasks_target` exists on `(target_type, target_id)`.
- Re-running the migration is safe (`IF NOT EXISTS`).

## Files Changed

- Created: `backend/migrations/20260817_evidence_tasks_target_id.sql` (4 lines)

## Commit

- `df7dda0` — `feat(evidence): add paper_evidence_tasks.target_id for 1:1 object tasks`
- Commit contains exactly 1 file, 4 insertions. No pre-existing modified files were touched or staged.

## TDD Evidence

N/A — this task is a pure SQL migration with no testable code; RED/GREEN cycle does not apply. Verification was performed directly against the dev database (column type, nullability, index presence, idempotent re-run).

## Concerns

None. Note: the existing table uses a composite `(target_type, target_id)` index, consistent with the pre-existing `target_type VARCHAR(32) NOT NULL` column from `20260807_paper_evidence.sql`. Backfill of `target_id` for legacy rows is intentionally left to later split-migration tasks per the brief.
