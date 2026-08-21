# Task 1 Report: 后端回退端点 reopen

Status: DONE_WITH_CONCERNS
Commit: `dada7cb` feat(evidence): 任务项回退端点 reopen(completed→awaiting_review,清 reviewed 字段)

## What was implemented

Followed the brief's steps 1–6 exactly, with the code given in the brief.

1. **Tests (Step 1)** — appended 3 tests to `backend/tests/test_paper_evidence_batch_phase4.py`:
   - `test_reopen_completed_item_returns_to_awaiting_review`
   - `test_reopen_non_completed_item_raises`
   - `test_reopen_missing_item_raises`
2. **Service (Step 3)** — inserted `pes.reopen_batch_item(session, task_id, item_id)` after `complete_batch_item_reviewed` in `backend/app/services/paper_evidence_service.py` (anchor found at line 3899, before `write_evidence_audit_event`). Raises `ValueError("task item not found")` / `ValueError("item is not completed")`; resets status → `awaiting_review`, clears `reviewed_by/reviewed_at/evidence_id`, then `_update_task_totals` + `_update_task_review_status`.
3. **Router (Step 4)** — inserted `POST /evidence/batch/{task_id}/items/{item_id}/reopen` after the `reviewed` endpoint in `backend/app/routers/ontology.py` (anchor found at line 1132, before the draft GET endpoint). `require_role("reviewer")`, ValueError → 400 `INVALID_REQUEST`.

## TDD evidence

**RED (Step 2)** — `pytest tests/test_paper_evidence_batch_phase4.py -k reopen -v`:
```
FAILED tests/test_paper_evidence_batch_phase4.py::test_reopen_completed_item_returns_to_awaiting_review
FAILED tests/test_paper_evidence_batch_phase4.py::test_reopen_non_completed_item_raises
FAILED tests/test_paper_evidence_batch_phase4.py::test_reopen_missing_item_raises
E AttributeError: module 'app.services.paper_evidence_service' has no attribute 'reopen_batch_item'
======================= 3 failed, 7 deselected in 1.81s =======================
```
Matches the brief's expected failure exactly.

**GREEN (Step 5)** — same command:
```
tests/test_paper_evidence_batch_phase4.py::test_reopen_completed_item_returns_to_awaiting_review PASSED [ 33%]
tests/test_paper_evidence_batch_phase4.py::test_reopen_non_completed_item_raises PASSED [ 66%]
tests/test_paper_evidence_batch_phase4.py::test_reopen_missing_item_raises PASSED [100%]
======================= 3 passed, 7 deselected in 1.66s =======================
```

## Regression checks

- Full `test_paper_evidence_batch_phase4.py`: **10 passed**.
- `test_paper_evidence_api.py` + `test_paper_evidence_reviews.py` (exercises the ontology router via TestClient, confirming the new route registers cleanly): **25 passed**.
- `py_compile` on all 3 modified files: OK.

## Files changed (exact brief paths only)

- `backend/app/services/paper_evidence_service.py`
- `backend/app/routers/ontology.py`
- `backend/tests/test_paper_evidence_batch_phase4.py`

Committed with `git add` on exactly these 3 paths (no `-A`, no `git add .`), message per brief, no Co-Authored-By trailer.

## Self-review findings

- Service mirrors `complete_batch_item_reviewed`'s structure (commit → rowcount check → totals → review_status); rowcount-after-commit is the same pattern the existing function uses, and SQLAlchemy caches rowcount on the result, so this is safe.
- The existence pre-check uses the same `SELECT 1` / `:tid`/`:iid` parameterized style as the rest of the file — no SQL injection.
- Route auth is identical to the neighboring `reviewed` endpoint (`require_role("reviewer")`).

## Concerns

1. **Commit swept in pre-existing uncommitted changes.** The 3 files were already dirty before this task started (confirmed in the conversation-start git status). The commit therefore includes ~986 lines of pre-existing changes beyond my ~140-line addition (diff stat: ontology.py +104/-?, service +1031/-202, tests +81). This is exactly what the brief's Step 6 instructs (`git add <3 paths>`), and the plan (BASE 2a0259b) presumably accounts for it, but the commit is not a pure "reopen only" changeset.
2. **Semantic note (per brief design):** reopen clears `evidence_id` on the item but does not delete the already-written `paper_evidence` row — documented in the function docstring as intentional 留痕 (audit trail). Re-review/promotion will create a new evidence record per the existing flow.
3. The reviewer-role endpoint and ValueError→400 mapping are not covered by an API-level test in this task (only service-level tests were specified). Router registration was smoke-tested via the existing evidence API test suite.
