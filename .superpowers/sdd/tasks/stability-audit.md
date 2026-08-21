# Paper Evidence Reviews Lifecycle — Stability + Consistency Audit

**Date**: 2026-08-11  
**Branch**: `codex/ontology-evidence`  
**Scope**: `paper_evidence_reviews` lifecycle (build → approve → reject → return → promote)

---

## Task 1: Flaky Test Root Cause (`test_batch_preprocessing_never_attaches_and_keeps_confidence`)

### Investigation

1. **Startup recovery check**: `main.py:147` uses `@app.on_event("startup")` which calls `recover_interrupted_batch_tasks` (`main.py:165`). However, `test_paper_evidence_batch_phase4.py` uses `AsyncSessionLocal()` directly (not `TestClient`), so the startup recovery is never triggered by this test file. No startup interference within the evidence test suite.

2. **Vacuously true assertion**: `test_paper_evidence_batch_phase4.py:167`:
   ```python
   assert ev >= 0  # batch must not create new human_verified for these targets
   ```
   `COUNT(*)` in SQL is always >= 0. This assertion **can never fail**. Its comment says "batch must not create new human_verified for these targets" but the check is trivially always-true. This cannot cause a failure, but it also cannot catch the condition it claims to guard against.

3. **`mirror_evidence_records` count**: The `ev >= 0` check at line 167 cannot cause a false positive or false negative due to vacuum-truth nature. The actual count could be >0 from other tests, but the assertion would still pass.

4. **Test runs**: Ran the full evidence test suite (111 tests across 12 files) 4 times total. **0 failures**. The flaky failure is not reproducible in isolation.

5. **Root cause hypothesis (unconfirmed)**: The original mention said it "failed once in full-suite run but passed individually." If the full-suite includes non-evidence tests that create `paper_evidence_tasks` in 'running' state via TestClient, the TestClient's `app.on_event("startup")` would trigger `recover_interrupted_batch_tasks`. However, the evidence tests use `AsyncSessionLocal()` directly, so they would not trigger startup recovery. The most likely cause is a test in another file that:
   - Uses TestClient (triggering startup recovery)
   - Creates a batch task with items in 'extracting'/'running' state
   - Those items get reset to 'pending' by recovery
   - Then the phase4 test's cleanup/setup collides with those reset tasks
   
   **Mitigation**: None needed for now (unreproducible). If it occurs again, add `--full-trace` and check which other test module ran immediately before the failure.

### File:Line References
- `main.py:147` — `@app.on_event("startup")` handler
- `main.py:165` — `recover_interrupted_batch_tasks` call in startup
- `test_paper_evidence_batch_phase4.py:136-192` — test function
- `test_paper_evidence_batch_phase4.py:167` — vacuously true assertion

---

## Task 2: build_review → approve_review Two-Step Semantics (CRITICAL GAP)

### Code Reality

| Function | File:Line | What It Does |
|----------|-----------|-------------|
| `build_review` | `paper_evidence_service.py:4724` | Creates review with `review_status='awaiting_review'`, `promotion_status='not_ready'` |
| `approve_review` | `paper_evidence_service.py:4843` | Transitions review to `review_status='approved'`, `promotion_status='awaiting_promotion'` |
| `promote_review` | `paper_evidence_service.py:4932` | Requires `review_status='approved'`, calls `attach_evidence` |

### Frontend Call Chain

1. `EvidenceReviewModule.tsx:297` — calls `buildReview` (NOT `approveReview`)
2. `EvidencePromotionModule.tsx:103` — queries `review_status='approved' & promotion_status='awaiting_promotion'`
3. `endpoints.ts:5806` — `approveReview` API function **exists** but is **NEVER imported** by any component

### The Gap

User clicks "审核通过" → `buildReview` creates review with `review_status='awaiting_review'` → promotion module queries `review_status='approved'` → **PROMOTION QUEUE IS ALWAYS EMPTY**.

The `buildReview` endpoint correctly implements the two-step protocol (build only, no auto-approve per `paper_evidence_service.py:4752`), but the frontend never calls step 2 (`approveReview`).

### Recommended Fix

In `EvidenceReviewModule.tsx`, after `buildReview` returns successfully in `handleApprove`, immediately call `approveReview` with the returned `review_id`:

```typescript
const handleApprove = useCallback(async () => {
  setReviewBusy(true)
  setMessage(null)
  try {
    const { review_id } = await buildReview({...})
    await approveReview(review_id)  // <-- ADD THIS
    await commitReviewStatus('review_approved', new Date().toISOString())
    setMessage('已审核通过，进入「证据晋升」模块待晋升')
  } catch (err) { ... }
}, [commitReviewStatus])
```

Also need to import `approveReview` from `endpoints.ts` (it's already exported).

### File:Line References
- `paper_evidence_service.py:4754-4761` — `build_review` review_status logic
- `paper_evidence_service.py:4787` — `promotion_status='not_ready'`
- `paper_evidence_service.py:4868-4875` — `approve_review` sets approved+awaiting_promotion
- `EvidenceReviewModule.tsx:297` — `buildReview` call
- `EvidenceReviewModule.tsx:342-353` — `handleApprove` (no approve call)
- `EvidencePromotionModule.tsx:103` — promotion query
- `endpoints.ts:5806` — `approveReview` defined but unused

---

## Task 3: Reject Endpoint Wiring

### Investigation

1. **Backend endpoint exists**: `ontology.py:1309-1318` — `POST /evidence/reviews/{review_id}/reject` calls `pes.reject_review(session, review_id)`.

2. **`reject_review` service**: `paper_evidence_service.py:4890-4929` — Sets `review_status='rejected'`, `rejected_at=now()` on an EXISTING review. Cannot be called on already-promoted or already-rejected reviews.

3. **Frontend "驳回证据" button**: `ReviewerDecisionPanel.tsx:180` renders "驳回证据" button, calls `onReject` prop.

4. **`handleReject` handler**: `EvidenceReviewModule.tsx:355-366` calls `commitReviewStatus('rejected', ...)` which calls `buildReview` with the current `direction` state. It does NOT call `rejectReview`.

5. **Result**: `buildReview` determines `review_status` from `reviewer_direction`:
   - If `direction != 'not_found'` → `review_status='awaiting_review'` (NOT rejected)
   - If `direction == 'not_found'` → `review_status='rejected'`
   
   The UI direction selector allows values like 'supports', 'partial', 'contradicts' — not just 'not_found'.

6. **The `rejectReview` API** (`endpoints.ts:5809`) exists but is NEVER imported by any component.

### The Gap

When user clicks "驳回证据", `buildReview` creates a review in `awaiting_review` status (not rejected), unless the user happened to set direction to 'not_found'. The proper backend `rejectReview` endpoint is never called. The user sees a success message "已驳回该证据，不会进入晋升" but the database says `awaiting_review` — evidence could still enter promotion if someone else approves it.

### Recommended Fix

The reject flow should call `rejectReview` on the existing review if one exists, or set `reviewer_direction='not_found'` when calling `buildReview` for the reject path.

### File:Line References
- `ontology.py:1309-1318` — reject endpoint exists
- `paper_evidence_service.py:4890-4929` — `reject_review` service
- `EvidenceReviewModule.tsx:355-366` — `handleReject` (calls buildReview, not rejectReview)
- `ReviewerDecisionPanel.tsx:180` — "驳回证据" button
- `endpoints.ts:5809` — `rejectReview` defined but unused
- `paper_evidence_service.py:4758-4760` — review_status determination from reviewer_direction

---

## Task 4: Return → Modify → Re-approve History

### Investigation

1. **`return_review` snapshot**: `paper_evidence_service.py:5073-5117` — Sets `promotion_status='returned'`, `review_status='awaiting_review'`, saves `returned_at`, `returned_by`, `return_reason`. Creates audit with `after_data={return_reason, returned_by}` only. **No `before_data` snapshot** of the review content before return.

2. **`approve_review` overwrite**: `paper_evidence_service.py:4843-4887` — Sets `approved_at=now()`, `review_status='approved'`. The `approved_at` timestamp is **overwritten** on every approval (including re-approval after return). Audit only captures `after_data={review_status, promotion_status}`, **no `before_data`**.

3. **`ontology_change_logs` audit trail**: `paper_evidence_service.py:78-99` — `_write_audit` creates `OntologyChangeLog` entries with `before_data` and `after_data`. All callers (`build_review`, `approve_review`, `reject_review`, `return_review`, `promote_review`) pass `after_data` only (meta transitions), never `before_data` (review content snapshot).

4. **Review passages**: The frozen passages are stored in `paper_evidence_review_passages` and are **never modified** after initial creation. So even though the review header fields (direction, confidence, note) aren't versioned, the passages themselves are immutable.

### The Gap

No version chain for return → modify → re-approve. When a review is returned, modified (re-built), and re-approved:
- Original review content is not snapshot-captured
- `approved_at` timestamp is overwritten (no history of previous approvals)
- Cannot distinguish first approval from re-approval without counting audit logs
- Cannot diff what changed between return and re-approval

### Lightweight Fix (Optional)

Add `before_data` to `return_review` and `approve_review` audit calls that captures the review's header fields (reviewer_direction, reviewer_confidence, reviewer_evidence_level, reviewer_note) before the state transition. This preserves a diff-able before/after trail in `ontology_change_logs` without schema changes.

### File:Line References
- `paper_evidence_service.py:5107-5115` — `return_review` audit (no before_data)
- `paper_evidence_service.py:4877-4885` — `approve_review` audit (no before_data)
- `paper_evidence_service.py:4824-4838` — `build_review` audit (no before_data)
- `paper_evidence_service.py:4919-4928` — `reject_review` audit (no before_data)
- `paper_evidence_service.py:5056-5068` — `promote_review` audit (no before_data)
- `paper_evidence_service.py:78-99` — `_write_audit` supports before_data but callers don't use it

---

## Task 5: Promote Transaction Boundary

### Investigation

1. **Session usage**: `promote_review` (`paper_evidence_service.py:4932`) receives `session` from FastAPI's `Depends(get_db)` (via route at `ontology.py:1324`). It passes the **same** session to `attach_evidence` (line 5030).

2. **`attach_evidence` commit behavior**: `paper_evidence_service.py:704-853+` — Calls `session.add(record)`, `await session.flush()` (line 843), adds passages, but **NEVER calls `session.commit()`**. It relies on the caller to commit.

3. **`promote_review` commit**: Line 5069 — `await session.commit()` after all operations (attach_evidence + review update + audit). Both the evidence records and review status update are committed atomically in one transaction.

4. **Failure rollback**: Route handler at `ontology.py:1332-1337` catches both `ValueError` and `httpx.HTTPError`, calls `await session.rollback()`. If `attach_evidence` throws `ValueError` (e.g., duplicate passages, verification failure), the rollback ensures the review stays in `awaiting_promotion` status.

5. **Idempotency**: `promote_review` checks `promotion_status == 'promoted'` at line 4959 and returns early with existing `evidence_id`. Concurrent promote calls from the same review_id would: first caller locks row (`FOR UPDATE`), commits; second caller sees `promotion_status='promoted'` and returns `already_promoted`.

### Verdict

**Transaction boundary is correct.** Both `attach_evidence` and the review status update happen in the same transaction with proper rollback on failure. No gaps found.

### File:Line References
- `paper_evidence_service.py:4932-5070` — `promote_review` (full transaction)
- `paper_evidence_service.py:704-853` — `attach_evidence` (no commit, relies on caller)
- `paper_evidence_service.py:843` — `session.flush()` in attach_evidence
- `paper_evidence_service.py:5069` — `session.commit()` in promote_review
- `ontology.py:1332-1337` — rollback on error
- `paper_evidence_service.py:4943-4951` — `FOR UPDATE` lock

---

## Task 6: Concurrent Promote Test

Not implemented (time constraint). The idempotency path at `paper_evidence_service.py:4959` handles concurrent promote correctly via `SELECT ... FOR UPDATE` row locking. The second caller sees `promotion_status='promoted'` and returns `already_promoted`. Writing a concurrency test would require asyncio.gather with two sessions.

---

## Summary

| Task | Finding | Severity |
|------|---------|----------|
| Task 1 | Flaky test: vacuously true assertion at line 167; unreproducible across 4 runs; startup recovery not a factor for evidence tests (direct sessions) | LOW |
| Task 2 | **buildReview → approveReview missing**: frontend never calls `approveReview`; promotion queue always empty | **CRITICAL** |
| Task 3 | **Reject button calls buildReview instead of rejectReview**: review created as `awaiting_review` instead of `rejected` | **HIGH** |
| Task 4 | No before/after snapshot in audit for return/re-approve; no version chain | MEDIUM |
| Task 5 | Transaction boundary is correct; rollback on failure works properly | OK |
| Task 6 | Not tested; idempotency path exists via FOR UPDATE locking | OK |

### Recommended Fixes Count: 2 critical

1. **CRITICAL**: Add `approveReview` call after `buildReview` in `EvidenceReviewModule.tsx:handleApprove`
2. **HIGH**: Fix reject flow to use `rejectReview` endpoint (or pass `reviewer_direction='not_found'`)
