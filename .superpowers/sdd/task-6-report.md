# Task 6 Report: 统一任务端点 label 改用对象名

## Status: DONE

## What Changed

- File: `backend/app/routers/unified_tasks.py` (function `_paper_evidence`)
- Replaced `label=f"论文佐证 · {item['target_type']}"` with a fallback chain:
  `item.get("display_name_cn") or item.get("display_name_en") or f"论文佐证 · {item['target_type']}"`
- Task 5 prerequisite verified: `paper_evidence_service.py` (lines 3823, 3910-3911) augments task dicts
  with `display_name_cn`/`display_name_en`, so the new label picks up object display names.

## Commands Run

1. `cd backend && ./.venv/Scripts/python.exe -m pytest tests/ -q -k "unified"`
   - Result: 0 tests collected (1464 deselected, 12 warnings in 1.30s). No test file matches this
     keyword; per brief, 0 collected is acceptable.
2. `cd backend && ./.venv/Scripts/python.exe -m pytest tests/ -q -k "unified or tasks_runs"`
   - Result: same — 0 collected, no failures (1464 deselected).
3. Smoke import: `cd backend && ./.venv/Scripts/python.exe -c "import app.routers.unified_tasks; print('import ok')"`
   - Result: `import ok`
4. Commit: `git add backend/app/routers/unified_tasks.py && git commit -m "feat(evidence): unified task label uses object display name"`

## Commit

- SHA: `8966dad` — feat(evidence): unified task label uses object display name
- Contents: only `backend/app/routers/unified_tasks.py` (5 insertions, 1 deletion)

## Concerns

- None. The change is behavior-preserving for items lacking display names (fallback keeps the old
  label format).
- Pre-existing unrelated working-tree modifications were left untouched.
