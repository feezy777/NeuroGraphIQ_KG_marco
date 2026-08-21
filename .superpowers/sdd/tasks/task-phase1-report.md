# Phase 1: paper_evidence_reviews 后端生命周期 — Implementation Report

**Date:** 2026-08-11 | **Branch:** `codex/ontology-evidence`

---

## Summary

Implemented the full `paper_evidence_reviews` backend lifecycle (Phase 1): migration, service, router, frontend endpoints, and tests. All 11 new tests pass; all 42 existing evidence tests pass; TypeScript + Vite build pass with 0 errors.

## Deliverables

### 1. Migration SQL
**File:** `backend/migrations/034_paper_evidence_reviews.sql`

Two tables created:
- `paper_evidence_reviews` — formal review records with reviewer direction/confidence/note, review_status, promotion_status, claim snapshots, timestamps, evidence_id FK
- `paper_evidence_review_passages` — frozen passage snapshots at review time (FK CASCADE on review delete)

Indexes: target lookup, status filter, task filter, review_id on passages.

### 2. Service
**File:** `backend/app/services/paper_evidence_service.py` (appended 567 lines)

Functions appended under `# Review/Promotion Lifecycle` section:

| Function | Purpose |
|---|---|
| `build_review()` | Creates review + frozen passages from reviewer decision. Sets `review_status='approved'` for valid directions, `='rejected'` for `not_found`. Audits. Never writes evidence. |
| `approve_review()` | Locks row (`FOR UPDATE`), sets `approved_at`, `promotion_status='awaiting_promotion'`. Only from draft/awaiting_review/returned. |
| `reject_review()` | Sets `review_status='rejected'`, `rejected_at`. |
| `promote_review()` | **Idempotent**. Reads frozen snapshot, looks up paper→pmid from `paper_sources`, converts review passages to attach format, calls `attach_evidence()` with full backend verification (paper verify, passage verify, coverage compute, dedup check, confidence adjustment, ORM evidence records + passages + audit + validation). Updates review.evidence_id + promotion_status. Transactional. |
| `return_review()` | Sets `promotion_status='returned'`, `review_status='awaiting_review'`, `return_reason`. |
| `list_reviews()` | Paginated list with optional filters (review_status, promotion_status, target_type). |
| `get_review()` | Full review + all frozen passages ordered by rank. |

Helper functions: `_map_review_passage()`, `_write_evidence_audit_event()`, `_review_row_to_dict()`, `_passage_row_to_dict()`.

### 3. Router
**File:** `backend/app/routers/ontology.py` (+132 lines)

7 new endpoints:

| Method | Path | Auth | Function |
|---|---|---|---|
| POST | `/api/ontology/evidence/reviews` | reviewer | Build a review |
| GET | `/api/ontology/evidence/reviews` | — | List reviews (paginated, filterable) |
| GET | `/api/ontology/evidence/reviews/{review_id}` | — | Get review with passages |
| POST | `/api/ontology/evidence/reviews/{review_id}/approve` | reviewer | Approve review |
| POST | `/api/ontology/evidence/reviews/{review_id}/reject` | reviewer | Reject review |
| POST | `/api/ontology/evidence/reviews/{review_id}/promote` | reviewer | Promote to Mirror KG evidence |
| POST | `/api/ontology/evidence/reviews/{review_id}/return` | reviewer | Return for rework |

### 4. Schemas
**File:** `backend/app/schemas/ontology.py` (+103 lines)

Added Pydantic models: `EvidenceReviewBuildRequest`, `EvidenceReviewResponse`, `EvidenceReviewOut`, `EvidenceReviewPassageOut`, `EvidenceReviewListResponse`, `EvidenceReviewReturnRequest`.

### 5. Frontend Endpoints
**File:** `frontend/src/api/endpoints.ts` (+112 lines)

TypeScript interfaces: `EvidenceReviewPassage`, `EvidenceReviewItem`, `EvidenceReviewBuildBody`.

API wrappers: `buildReview()`, `listEvidenceReviews()`, `getEvidenceReview()`, `approveReview()`, `rejectReview()`, `promoteReview()`, `returnReview()`.

### 6. Tests
**File:** `backend/tests/test_paper_evidence_reviews.py` (NEW, ~540 lines)

11 tests, all passing:

| Test | Verifies |
|---|---|
| `test_build_review_approved` | supports direction → approved, passages persisted |
| `test_build_review_rejected` | not_found direction → rejected |
| `test_approved_does_not_create_evidence_or_modify_confidence` | build/approve never touches mirror_evidence_records |
| `test_approve_review` | approve from valid states, rejects invalid states |
| `test_reject_review` | reject transitions to rejected |
| `test_promote_returns_on_wrong_status` | ValueError when not approved |
| `test_promote_creates_evidence` | Full promote flow: attaches evidence, creates MirrorEvidenceRecord |
| `test_promote_idempotent` | Second promote returns 'already_promoted' |
| `test_return_review` | Return sets returned/awaiting_review |
| `test_list_reviews` | Paginated list, status/type filters |
| `test_get_review_with_passages` | Full review + 2 passages (selected + unselected) |

### Regression
- `tests/test_paper_evidence.py` — 42 passed
- `tests/test_paper_evidence_api.py` — passed
- `tests/test_paper_retrieval_phase2.py` — passed
- `frontend/` — `npx tsc --noEmit` clean, `npm run build` succeeded (0 errors, pre-existing warnings only)

## Key Design Decisions

1. **promote_review calls attach_evidence directly** — The review stores `paper_id`, and `promote_review` looks up the pmid via `paper_sources`. This ensures the full backend verification chain (verify_paper → ensure_paper_source → verify_passages → compute_coverage → dedup_check → confidence_adjustment → write_evidence) runs on promotion, not silently trusting frozen review snapshots.

2. **Idempotent promote** — If `promotion_status='promoted'`, returns existing `evidence_id` without re-attaching. Uses `FOR UPDATE` row lock.

3. **No evidence writes during review** — `build_review` and `approve_review` write only to `paper_evidence_reviews` + `paper_evidence_review_passages`. Mirror KG evidence is only created during `promote_review`.

4. **Raw SQL for review tables** — Follows the existing pattern: raw `text()` SQL for `paper_evidence_*` tables (not ORM-mapped), ORM for `mirror_evidence_records` and `mirror_evidence_passages`.

## Known Limitations / Future Work

- `paper_evidence_review_passages` currently lacks a `passage_text_snapshot` hash index; may add if dedup is needed at review level
- No batch promotion endpoint yet (single-review only)
- Frontend UI integration (ReviewModule → buildReview, PromotionModule → promoteReview) is Phase 2

## Post-Review Fixes (2026-08-11)

**Commit:** `02bbe88` | **Branch:** `codex/ontology-evidence`

### Changes

| Finding | Fix |
|---|---|
| **C1** | `reject_review`/`return_review` 增加状态守卫: 已 promoted 或已 rejected/returned → raise ValueError |
| **C2** | 新增 `cancel_review()` service (awaiting_promotion → cancelled), migration 注释 supported values |
| **I1** | `approve_review` 移除不可达 'draft' 守卫, 注释说明 draft 预留未来多步审核流程 |
| **I2** | 删除 `_write_evidence_audit_event` 死代码, ontology 路由改为调用 `_write_audit` |
| **I3** | `build_review` 统一设 `review_status='awaiting_review'` + `promotion_status='not_ready'`, 需 `approve_review` 显式推进 |

### Test Summary

57 passed (15 review + 42 evidence), 0 failed. New: `test_reject_already_promoted_raises`, `test_return_already_promoted_raises`, `test_cancel_review`, `test_cancel_review_wrong_status_raises`.
