# Evidence Center Review/Promotion Pipeline -- Data Flow Survey

Generated: 2026-08-11 | Branch: `codex/ontology-evidence` | Read-only analysis

---

## 1. ReviewStatusStore -- Full API

**File:** `frontend/src/pages/evidence-center/components/ReviewStatusStore.ts:1-68`

### Key Prefix

```
evidence-center.review-approved.<targetId>
```

### Type Definitions

```typescript
// ReviewStatusStore.ts:6
type ReviewStatus = 'review_approved' | 'rejected'

// ReviewStatusStore.ts:8-15
interface ReviewStatusMeta {
  direction: Direction          // 'supports' | 'partial' | 'contradicts' | 'mixed' | 'not_found'
  evidenceLevel: EvidenceLevel  // 'direct' | 'indirect' | 'interpretive' | 'background'
  confidence: string            // e.g. "0.8"
  note: string
  at: string                    // ISO timestamp
}

// ReviewStatusStore.ts:17-23
interface ReviewStatusRecord {
  targetId: string
  status: ReviewStatus
  meta: ReviewStatusMeta
  targetType?: string           // set by review module, consumed by promotion module
}
```

### Functions

| Function | Line | Signature | Behavior |
|---|---|---|---|
| `saveReviewStatus` | 25 | `(targetId, status, meta, targetType?) -> void` | `sessionStorage.setItem(key, JSON.stringify({targetId, status, meta, targetType}))` |
| `loadReviewStatus` | 34 | `(targetId) -> ReviewStatusRecord\|null` | `sessionStorage.getItem(key)` + JSON parse + validation |
| `clearReviewStatus` | 46 | `(targetId) -> void` | `sessionStorage.removeItem(key)` |
| `listReviewApproved` | 51 | `() -> ReviewStatusRecord[]` | Scans ALL sessionStorage keys with prefix; returns all valid records (including rejected; caller filters by `status==='review_approved'`) |

### Storage Location

`sessionStorage` (per-tab, lost on tab close but survives page refresh within tab).

---

## 2. Review Module -- Write Paths

**File:** `frontend/src/pages/evidence-center/modules/EvidenceReviewModule.tsx`

### Draft Key Format

```
evidence-center.review-draft.<targetId>
```

### Draft Interface (line 25-37)

```typescript
interface ReviewDraft {
  passages: WorkbenchPassage[]
  modelDirection: Direction | null
  modelAssessment: string | null
  paperTitle: string
  pmid: string
  doi?: string | null
  translations?: Record<string, string>
  reviewerDirection?: Direction
  reviewerEvidenceLevel?: EvidenceLevel
  reviewerConfidence?: string
  note?: string
}
```

### Draft Auto-Persist (line 196-215)

- `buildDraft()` (182-194): builds snapshot from ALL current state
- `persistDraft()` (197-200): writes `buildDraft()` to `sessionStorage` under `evidence-center.review-draft.<targetId>`
- 500ms debounced auto-save (202-206)
- Cleanup effect (213-215): synchronously flushes final draft on unmount/switch

### Draft Recovery on Target Switch (line 66-109)

Reads `evidence-center.review-draft.<targetId>` from sessionStorage and restores:
- `passages` -> `setPassages`, `setSelectedHashes` (by `source_verified`)
- `modelDirection`, `modelAssessment`
- `paperTitle`, `pmid`, `doi`
- `translations`
- `reviewerDirection`, `reviewerEvidenceLevel`, `reviewerConfidence`, `note`

Also restores review status: `loadReviewStatus(targetId)`

### handleBack (line 255-258)

```
persistDraft() -> openTarget(targetType, targetId, 'candidates')
```
Navigates back to EvidenceCandidatesModule; draft is saved to sessionStorage before navigation.

### handleSaveDraft (line 262-278)

```
1. persistDraft to sessionStorage
2. If taskItem?.taskItemId exists:
   -> saveTaskItemDraft(taskItem.taskItemId, draft, revision=0)
   -> PUT /api/ontology/evidence/batch/items/{itemId}/draft
      (writes to paper_evidence_task_items.review_draft JSONB)
3. If no taskItemId: shows "草稿已保存在本地（未关联任务项）"
```

### commitReviewStatus (line 281-290)

```
1. persistDraft()  -- saves current draft state to sessionStorage
2. Builds ReviewStatusMeta from current state:
   { direction, evidenceLevel, confidence, note, at: ISO timestamp }
3. saveReviewStatus(targetId, 'review_approved'|'rejected', meta, state.targetType)
   -> writes to sessionStorage under evidence-center.review-approved.<targetId>
4. Updates local reviewStatus state
5. setProgress({ reviewed: true })  -- advances StepPills
```

### handleApprove (line 292-295)

Calls `commitReviewStatus('review_approved', ...)` + sets message.

### handleReject (line 297-300)

Calls `commitReviewStatus('rejected', ...)` + sets message.

### Data Written by Review Module

| Destination | What | Key |
|---|---|---|
| sessionStorage | Full review draft (passages + decisions) | `evidence-center.review-draft.<targetId>` |
| sessionStorage | Review status record (`review_approved`/`rejected`) | `evidence-center.review-approved.<targetId>` |
| Backend DB | Draft (if taskItemId exists) | `paper_evidence_task_items.review_draft` JSONB |

**No backend evidence is written during review.** The review module is purely read-only regarding the database; it only writes to sessionStorage and optionally saves a draft to the task item.

---

## 3. Promotion Module -- Read/Write Paths

**File:** `frontend/src/pages/evidence-center/modules/EvidencePromotionModule.tsx`

### Pending List Construction (line 73-76)

```
listReviewApproved().filter(r => r.status === 'review_approved')
```
- Reads ALL sessionStorage keys with prefix `evidence-center.review-approved.`
- Filters to only `status === 'review_approved'`
- Each record has: `{ targetId, status: 'review_approved', meta: {direction, evidenceLevel, confidence, note, at}, targetType? }`

### Draft Recovery (line 107-123)

For the selected pending record:
- Reads `evidence-center.review-draft.<selectedPendingId>` from sessionStorage
- Validates: must have `reviewerDirection` AND at least one `source_verified` passage
- Sets `draft` state (used for preview and promotion)

### handlePromote (line 213-268)

```
1. Calls attachPaperEvidence({
     target_type: selectedTargetType,
     target_id: selectedPendingId,
     pmid: draft.pmid,
     direction: draft.reviewerDirection,
     evidence_level: draft.reviewerEvidenceLevel,
     model_direction: draft.modelDirection,
     model_assessment: draft.modelAssessment,
     reviewer_note: draft.note,
     reviewer_confidence: parseFloat(draft.reviewerConfidence),
     passages: selectedPassages (source_verified only),
   })
   -> POST /api/ontology/evidence/attach
   -> Backend: attach_evidence() (paper_evidence_service.py:704-990)
      Writes to: mirror_evidence_records, mirror_evidence_passages,
                 confidence_adjustment_logs, ontology_change_logs,
                 evidence_validation_records

2. Clears sessionStorage:
   sessionStorage.removeItem('evidence-center.review-draft.<selectedPendingId>')
   clearReviewStatus(selectedPendingId)   -- removes review-approved status

3. Advances StepPills: setProgress({ promoted: true })

4. Updates queue: marks item as 'completed'

5. If taskId exists, marks backend task item:
   completePaperEvidenceTaskItem(taskId, itemId, evidenceId)
   -> POST /api/ontology/evidence/batch/{taskId}/items/{itemId}/reviewed

6. Refreshes: loadList() + refreshPending()
```

### handleReturnToReview (line 271-287)

```
1. clearReviewStatus(rec.targetId)
2. sessionStorage.removeItem('evidence-center.review-draft.<rec.targetId>')
3. Clears draft/preview states
4. refreshPending()  -> re-scans sessionStorage
5. openTarget(rec.targetType, rec.targetId, 'review')  -> navigates back to review
```

### handleRollback (line 290-305)

```
1. rollbackPaperEvidence(ev.evidence_id, reason)
   -> POST /api/ontology/evidence/{evidence_id}/rollback
   -> Backend: rollback_evidence()
      - Marks MirrorEvidenceRecord.verification_status = 'invalidated'
      - Rolls back ConfidenceAdjustmentLog (status = 'rolled_back')
      - Recomputes target confidence from remaining applied logs
      - Writes audit + validation record
2. Refreshes list
```

---

## 4. Draft Storage Details

### sessionStorage Draft Format

**Key:** `evidence-center.review-draft.<targetId>`

**Value:** JSON serialized `ReviewDraft` object:

```json
{
  "passages": [
    {
      "source_scope": "abstract",
      "paragraph_index": 0,
      "passage": "...",
      "direction": "supports",
      "reason": "...",
      "confidence": 0.9,
      "source_locator": "...",
      "source_verified": true,
      "supported_components": ["source_region", "target_region"],
      "hash": "sha256...",
      "paper_passage_id": "...",
      "paragraph_id": "..."
    }
  ],
  "modelDirection": "supports",
  "modelAssessment": "...",
  "paperTitle": "...",
  "pmid": "12345",
  "doi": "10.xxx/yyy",
  "translations": { "<hash>": "中文翻译" },
  "reviewerDirection": "supports",
  "reviewerEvidenceLevel": "direct",
  "reviewerConfidence": "0.85",
  "note": "可信证据"
}
```

### Draft Persist Timing

1. **Auto-save:** 500ms debounce after ANY state change (`passages`, `direction`, `confidence`, etc.)
2. **Before navigation:** `handleBack()` calls `persistDraft()` synchronously
3. **Before unmount:** cleanup effect calls `persistDraft()` synchronously
4. **In handleSaveDraft:** writes to both sessionStorage AND backend (if taskItemId exists)
5. **In commitReviewStatus:** calls `persistDraft()` before writing review status

### Promotion Module Draft Read

- `handlePromote` reads these fields from the draft: `passages` (filtered to `source_verified`), `reviewerDirection`, `reviewerEvidenceLevel`, `reviewerConfidence`, `modelDirection`, `modelAssessment`, `note`, `pmid`

---

## 5. Batch Task Item Draft (Backend)

### Database Schema

**Table:** `paper_evidence_task_items` (created in `20260807_paper_evidence.sql:32-48`)

Relevant columns added by subsequent migrations:
| Column | Type | Migration | Added By |
|---|---|---|---|
| `review_draft` | JSONB | `20260807_paper_evidence_v8.sql:34` | Review module save |
| `draft_revision` | INT (default 0) | `20260807_paper_evidence_v9.sql:17` | Optimistic concurrency |
| `claim_text_snapshot` | TEXT | `20260807_paper_evidence_v8.sql:24` | Preprocessing |
| `claim_components_snapshot` | JSONB | `20260807_paper_evidence_v8.sql:25` | Preprocessing |
| `candidate_papers` | JSONB | `20260807_paper_evidence_v8.sql:27` | Preprocessing |

### PUT Endpoint (ontology.py:1080-1090)

```
PUT /api/ontology/evidence/batch/items/{item_id}/draft
Body: { draft: <any JSON object>, revision: <int> }
Auth: reviewer role
```

### Schema (schemas/ontology.py:264-266)

```python
class TaskItemDraftRequest(BaseModel):
    draft: dict
    revision: int = 0
```

### Service Function (paper_evidence_service.py:4109-4135)

```python
async def save_task_item_draft(
    session: AsyncSession,
    item_id: str,
    draft: dict,
    operator_id: str | None = None,
    revision: int = 0,
) -> dict:
```

**SQL (raw):**
```sql
UPDATE paper_evidence_task_items
SET review_draft = CAST(:d AS jsonb),
    draft_revision = :rev,
    updated_at = now()
WHERE id::text = :iid
  AND (draft_revision IS NULL OR draft_revision <= :rev)
RETURNING id::text
```

### GET Endpoint (ontology.py:1069-1077)

```
GET /api/ontology/evidence/batch/items/{item_id}/draft
Returns: { item_id, status, preprocess_outcome, review_draft, candidate_papers }
```

### Frontend Handler (EvidenceReviewModule.tsx:262-278)

```
handleSaveDraft():
  sessionStorage.setItem(key, JSON.stringify(draft))
  if taskItem?.taskItemId:
    saveTaskItemDraft(taskItem.taskItemId, draft, revision=0)
```

---

## 6. Existing Evidence/Target Models

### MirrorEvidenceRecord (`models/mirror_kg.py:263-321`)

**Table:** `mirror_evidence_records`

| Column | Type | Default | Notes |
|---|---|---|---|
| `id` | UUID (PK) | gen_random_uuid() | |
| `evidence_target_type` | VARCHAR(64) | NOT NULL | e.g. 'connection', 'function', 'circuit' |
| `evidence_target_id` | UUID | NOT NULL | FK to target object |
| `resource_id` | UUID | nullable | FK atlas_resources |
| `batch_id` | UUID | nullable | FK import_batches |
| `llm_run_id` | UUID | nullable | FK llm_extraction_runs |
| `llm_item_id` | UUID | nullable | FK llm_extraction_items |
| `granularity_level` | VARCHAR(64) | nullable | Added 20260714 |
| `evidence_type` | VARCHAR(64) | 'llm_explanation' | 'paper_verification' for paper evidence |
| `evidence_text` | TEXT | NOT NULL | Rebuilt from valid records |
| `source_document_id` | UUID | nullable | |
| `source_reference_text` | TEXT | nullable | |
| `citation_json` | JSONB | '{}'::jsonb | |
| `confidence` | NUMERIC | nullable | |
| `uncertainty_reason` | TEXT | nullable | |
| `evidence_direction` | VARCHAR(16) | nullable | 'supports'/'partial'/'contradicts'/'mixed' |
| `evidence_level` | VARCHAR(16) | nullable | 'direct'/'indirect'/'interpretive'/'background' |
| `model_direction` | VARCHAR(16) | nullable | AI model's direction |
| `model_assessment` | TEXT | nullable | AI model's assessment |
| `reviewer_note` | TEXT | nullable | Human reviewer's note |
| `claim_version` | VARCHAR(32) | nullable | |
| `claim_text_snapshot` | TEXT | nullable | |
| `claim_components_snapshot` | JSONB | nullable | |
| `coverage_summary_snapshot` | JSONB | nullable | |
| `coverage_formula_version` | VARCHAR(64) | nullable | 'paper_evidence_coverage_v1' |
| `verification_status` | VARCHAR(16) | 'pending' | 'human_verified'/'ai_extracted'/'invalidated' |
| `paper_id` | UUID | nullable | FK paper_sources |
| `paper_source` | VARCHAR(32) | nullable | 'europepmc' |
| `paper_pmid` | VARCHAR(64) | nullable | |
| `paper_doi` | VARCHAR(256) | nullable | |
| `paper_title` | TEXT | nullable | |
| `paper_journal` | VARCHAR(256) | nullable | |
| `paper_year` | INT | nullable | |
| `suggested_confidence` | NUMERIC | nullable | |
| `reviewer_confidence` | NUMERIC | nullable | |
| `confidence_adjustment_status` | VARCHAR(16) | 'none' | 'applied'/'pending'/'none'/'no_change_weak_evidence' |
| `verification_by` | VARCHAR(64) | nullable | |
| `verification_at` | TIMESTAMPTZ | nullable | |
| `invalidated_by` | VARCHAR(64) | nullable | |
| `invalidated_at` | TIMESTAMPTZ | nullable | |
| `invalidation_reason` | TEXT | nullable | |
| `created_at` | TIMESTAMPTZ | now() | |

### MirrorEvidencePassage (`models/mirror_kg.py:324-359`)

**Table:** `mirror_evidence_passages`

| Column | Type | Default | Notes |
|---|---|---|---|
| `id` | UUID (PK) | gen_random_uuid() | |
| `evidence_id` | UUID (FK) | NOT NULL | FK mirror_evidence_records ON DELETE CASCADE |
| `paper_passage_id` | UUID | nullable | FK paper_passages ON DELETE SET NULL |
| `source_scope` | VARCHAR(16) | NOT NULL | 'abstract'/'fulltext' |
| `section_title` | TEXT | nullable | |
| `paragraph_index` | INT | nullable | |
| `passage_text` | TEXT | NOT NULL | |
| `passage_text_snapshot` | TEXT | nullable | |
| `translation_zh` | TEXT | nullable | |
| `direction` | VARCHAR(16) | NOT NULL | |
| `evidence_level` | VARCHAR(16) | nullable | |
| `reason` | TEXT | nullable | |
| `confidence` | NUMERIC | nullable | |
| `semantic_confidence` | NUMERIC | nullable | |
| `is_selected` | BOOLEAN | false | |
| `source_locator` | VARCHAR(256) | nullable | |
| `passage_hash` | VARCHAR(64) | NOT NULL | SHA256 of normalized passage |
| `source_verified` | BOOLEAN | false | |
| `source_verification_method` | VARCHAR(32) | nullable | 'exact'/'normalized_whitespace'/'normalized_unicode'/'similarity' |
| `supported_components` | JSONB | '[]'::jsonb | |
| `created_at` | TIMESTAMPTZ | now() | |
| `updated_at` | TIMESTAMPTZ | now() | onupdate |

**Unique constraint:** `(evidence_id, passage_hash)`

### ConfidenceAdjustmentLog (`models/mirror_kg.py:362-386`)

**Table:** `confidence_adjustment_logs`

| Column | Type | Default | Notes |
|---|---|---|---|
| `id` | UUID (PK) | gen_random_uuid() | |
| `target_type` | VARCHAR(32) | NOT NULL | |
| `target_id` | UUID | NOT NULL | |
| `evidence_id` | UUID | nullable | FK mirror_evidence_records ON DELETE SET NULL |
| `before_confidence` | NUMERIC | nullable | |
| `suggested_confidence` | NUMERIC | nullable | |
| `reviewer_confidence` | NUMERIC | nullable | |
| `calculated_confidence` | NUMERIC | nullable | |
| `after_confidence` | NUMERIC | nullable | |
| `direction` | VARCHAR(16) | nullable | |
| `formula_version` | VARCHAR(64) | NOT NULL | 'paper_evidence_v1' |
| `status` | VARCHAR(16) | 'applied' | 'applied'/'rolled_back' |
| `applied_by` | VARCHAR(64) | nullable | |
| `applied_at` | TIMESTAMPTZ | nullable | |
| `rolled_back_by` | VARCHAR(64) | nullable | |
| `rolled_back_at` | TIMESTAMPTZ | nullable | |
| `rollback_reason` | TEXT | nullable | |
| `created_at` | TIMESTAMPTZ | now() | |

### PaperEvidenceTask / PaperEvidenceTaskItem

**NOT ORM models** -- these are raw SQL tables only. Defined in migrations:

**paper_evidence_tasks** (`20260807_paper_evidence.sql:17-30`, extended by v3/v8/v9):

| Column | Type | Default |
|---|---|---|
| `id` | UUID (PK) | gen_random_uuid() |
| `target_type` | VARCHAR(32) | NOT NULL |
| `scope` | VARCHAR(32) | NOT NULL |
| `mode` | VARCHAR(16) | 'function' |
| `max_papers_per_object` | INT | 3 |
| `status` | VARCHAR(16) | 'pending' |
| `name` | TEXT | nullable |
| `review_status` | VARCHAR(16) | 'not_started' |
| `granularity_level` | VARCHAR(32) | nullable |
| `only_oa` | BOOLEAN | false |
| `confidence_lt` | NUMERIC | nullable |
| `stop_after_strong_support` | BOOLEAN | false |
| `total_items` | INT | 0 |
| `processed_items` | INT | 0 |
| `awaiting_review_items` | INT | 0 |
| `failed_items` | INT | 0 |
| `scope_type` | VARCHAR(16) | nullable |
| `filter_snapshot` | JSONB | nullable |
| `estimated_target_count` | INT | nullable |
| `materialized_target_count` | INT | 0 |
| `materialization_status` | VARCHAR(16) | 'pending' |
| `materialization_cursor` | UUID | nullable |
| `materialization_error` | TEXT | nullable |
| `paused_at` | TIMESTAMPTZ | nullable |
| `resumed_at` | TIMESTAMPTZ | nullable |
| `cancelled_at` | TIMESTAMPTZ | nullable |
| `summary` | JSONB | '{}'::jsonb |
| `config` | JSONB | '{}'::jsonb |
| `created_by` | VARCHAR(64) | nullable |
| `created_at` | TIMESTAMPTZ | now() |
| `started_at` | TIMESTAMPTZ | nullable |
| `finished_at` | TIMESTAMPTZ | nullable |
| `error_message` | TEXT | nullable |

**paper_evidence_task_items** (`20260807_paper_evidence.sql:32-48`, extended by v3/v8/v9):

| Column | Type | Default |
|---|---|---|
| `id` | UUID (PK) | gen_random_uuid() |
| `task_id` | UUID (FK) | NOT NULL |
| `target_type` | VARCHAR(32) | NOT NULL |
| `target_id` | UUID | NOT NULL |
| `status` | VARCHAR(16) | 'pending' |
| `pmid` | VARCHAR(64) | nullable |
| `title` | TEXT | nullable |
| `abstract` | TEXT | nullable |
| `passage` | TEXT | nullable |
| `direction` | VARCHAR(16) | nullable |
| `confidence` | NUMERIC | nullable |
| `evidence_id` | UUID | nullable |
| `error_message` | TEXT | nullable |
| `label` | TEXT | nullable |
| `current_confidence` | NUMERIC | nullable |
| `paper_json` | JSONB | nullable |
| `passages_json` | JSONB | nullable |
| `raw_response` | TEXT | nullable |
| `source_text_hash` | VARCHAR(64) | nullable |
| `parse_status` | VARCHAR(32) | nullable |
| `retry_count` | INT | 0 |
| `attempt_count` | INT | 0 |
| `last_error_code` | VARCHAR(48) | nullable |
| `last_error_message` | TEXT | nullable |
| `last_error_at` | TIMESTAMPTZ | nullable |
| `next_retry_at` | TIMESTAMPTZ | nullable |
| `started_at` | TIMESTAMPTZ | nullable |
| `finished_preprocessing_at` | TIMESTAMPTZ | nullable |
| `preprocess_outcome` | VARCHAR(32) | nullable |
| `claim_version` | VARCHAR(32) | nullable |
| `claim_text_snapshot` | TEXT | nullable |
| `claim_components_snapshot` | JSONB | nullable |
| `search_query` | TEXT | nullable |
| `candidate_papers` | JSONB | nullable |
| `model_direction` | VARCHAR(16) | nullable |
| `model_assessment` | TEXT | nullable |
| `coverage_summary` | JSONB | nullable |
| `reviewed_by` | VARCHAR(64) | nullable |
| `reviewed_at` | TIMESTAMPTZ | nullable |
| `preprocessing_version` | VARCHAR(32) | nullable |
| `retrieval_version` | VARCHAR(64) | nullable |
| `llm_model` | VARCHAR(128) | nullable |
| `prompt_version` | VARCHAR(64) | nullable |
| `review_draft` | JSONB | nullable | <-- Review module saves here |
| `draft_revision` | INT | 0 | <-- Optimistic concurrency |
| `last_error` | TEXT | nullable |
| `created_at` | TIMESTAMPTZ | now() |
| `updated_at` | TIMESTAMPTZ | now() |

**paper_evidence_task_item_passages** (`20260807_paper_evidence_v8.sql:40-58`):

| Column | Type | Default |
|---|---|---|
| `id` | UUID (PK) | gen_random_uuid() |
| `task_item_id` | UUID (FK) | NOT NULL (ON DELETE CASCADE) |
| `paper_id` | UUID | nullable |
| `paper_passage_id` | UUID | nullable |
| `paragraph_id` | VARCHAR(128) | nullable |
| `passage_text_snapshot` | TEXT | NOT NULL |
| `translation_zh` | TEXT | nullable |
| `direction` | VARCHAR(16) | nullable |
| `evidence_level` | VARCHAR(16) | nullable |
| `supported_components` | JSONB | '[]'::jsonb |
| `reason` | TEXT | nullable |
| `semantic_confidence` | NUMERIC | nullable |
| `source_verified` | BOOLEAN | false |
| `source_verification_method` | VARCHAR(32) | nullable |
| `rank` | INT | nullable |
| `is_recommended` | BOOLEAN | false |
| `created_at` | TIMESTAMPTZ | now() |

---

## 7. attach_evidence -- Full Flow

**File:** `paper_evidence_service.py:704-990`

### Signature

```python
async def attach_evidence(
    session: AsyncSession,
    *,
    target_type: str,
    target_id: uuid.UUID,
    pmid: str,
    direction: str,
    reviewer_confidence: float,
    passages: list[dict],
    mode: str = "function",
    operator_id: str | None = None,
    verification_status: str = "human_verified",
    evidence_level: str | None = None,
    model_direction: str | None = None,
    model_assessment: str | None = None,
    reviewer_note: str | None = None,
) -> dict:
```

### Internal Steps

| Step | Lines | Action |
|---|---|---|
| **1) Verify paper** | 722-726 | `verify_paper(pmid)` -> Europe PMC API call; raises ValueError if paper not found |
| **2) Ensure paper source** | 726 | `ensure_paper_source(session, paper)` -> upserts `paper_sources` table (raw SQL with ON CONFLICT) |
| **3) Verify target** | 727-732 | Looks up target via `TARGET_MODELS[target_type]`; raises if not found |
| **4) Build claim** | 734-737 | `build_target_dto(session, target_type, target_id)` -> backend-authoritative claim components |
| **5) Verify passages** | 739-773 | - `_load_source(session, pmid)` -> loads cached paper_passages or fetches from Europe PMC |
| | | - `_verify_passages(passages, source, source_scope)` -> tiered verification (exact -> normalized_whitespace -> normalized_unicode -> similarity) |
| | | - Raises if no passage verified |
| | | - Raises if similarity passages present without reviewer_note |
| | | - Links verified passages to `paper_passages` by text_hash |
| | | - Populates `supported_components` from claim components |
| **6) Compute coverage** | 775-783 | `compute_coverage_summary(claim_components, verified)` + `aggregate_overall_direction()` -> backend authority, never trusts client |
| | | - Raises if reviewer direction != coverage overall and no reviewer_note |
| **7) Dedup check** | 784-787 | `_count_duplicate_hashes()` -> counts existing passages with same hash for same target; raises if duplicates |
| **8) Confidence adjustment** | 789-796 | `compute_adjustment(direction, current_confidence, reviewer_confidence)` -> returns AdjustmentResult |
| **9) Write evidence record** | 798-843 | Creates `MirrorEvidenceRecord` ORM object with ALL fields populated; calls `session.add()` + `session.flush()` |
| **10) Write passages** | 845-867 | For each verified passage, creates `MirrorEvidencePassage` ORM object linked to evidence_id |
| **11) Confidence adjustment log + apply** | 869-890 | If adjustment applies: writes `ConfidenceAdjustmentLog`, updates `row.confidence = final_confidence` |
| **12) Rebuild evidence_text** | 892 | `rebuild_evidence_text(session, target_type, target_id)` -> concatenates all valid evidence records' text |
| **13) Audit + validation records** | 894-971 | Only if `verification_status == 'human_verified'`: |
| | | - `_write_audit()` -> inserts into `ontology_change_logs` (ORM) |
| | | - `_write_validation_record()` -> inserts into `evidence_validation_records` (raw SQL) |
| | | - Second validation record for contradictions/mixed without confidence adjustment |

### SQL Insert Style

**Mix of ORM and raw SQL:**

- `MirrorEvidenceRecord` -> ORM (`session.add(record)`)
- `MirrorEvidencePassage` -> ORM (`session.add()`)
- `ConfidenceAdjustmentLog` -> ORM (`session.add()`)
- `OntologyChangeLog` -> ORM (`session.add()` via `_write_audit`)
- `evidence_validation_records` -> **raw SQL** via `session.execute(text("INSERT INTO ..."))`
- `paper_sources` -> **raw SQL** via `text("INSERT INTO ... ON CONFLICT ... RETURNING id")`
- `paper_passages` -> **mix** (ORM for inserts, raw text for queries)

---

## 8. Migration Files -- Evidence-Related

### Complete List of Evidence Migrations

| File | Purpose |
|---|---|
| `20260714_add_granularity_to_evidence.sql` | Adds `granularity_level` to `mirror_evidence_records` |
| `20260806_ontology_governance.sql` | Creates `ontology_change_logs`, `ontology_alignment_candidates` |
| `20260807_paper_evidence.sql` | Adds paper fields to `mirror_evidence_records`; creates `paper_evidence_tasks` + `paper_evidence_task_items` |
| `20260807_paper_evidence_v2.sql` | (not checked; likely evidence_level, reviewer_confidence) |
| `20260807_paper_evidence_v3.sql` | Task lifecycle columns; creates `evidence_validation_records` |
| `20260807_paper_evidence_v4.sql` | (not checked) |
| `20260807_paper_evidence_v5.sql` | `source_verification_method` on `mirror_evidence_passages`; real FKs |
| `20260807_paper_evidence_v6.sql` | `supported_components` JSONB on `mirror_evidence_passages` |
| `20260807_paper_evidence_v7.sql` | Claim/coverage snapshot + model_direction/assessment on evidence records |
| `20260807_paper_evidence_v8.sql` | Batch review lifecycle; `review_draft` JSONB; `paper_evidence_task_item_passages` |
| `20260807_paper_evidence_v9.sql` | Scale/version closure; `draft_revision`; `uq_task_item_target` |
| `20260807_paper_evidence_target_types.sql` | (not checked) |

### Table Naming Convention

- Evidence tables: `mirror_evidence_records`, `mirror_evidence_passages`, `confidence_adjustment_logs`
- Paper tables: `paper_sources`, `paper_passages`
- Batch tables: `paper_evidence_tasks`, `paper_evidence_task_items`, `paper_evidence_task_item_passages`
- Audit: `ontology_change_logs`
- Validation: `evidence_validation_records`

---

## 9. Existing Review/Audit Tables

### evidence_validation_records

**Exists:** YES -- created in `20260807_paper_evidence_v3.sql:33-54`

**Schema:**
```sql
CREATE TABLE IF NOT EXISTS evidence_validation_records (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    evidence_id UUID REFERENCES mirror_evidence_records(id) ON DELETE CASCADE,
    task_id UUID,
    rule_code VARCHAR(64) NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'pending',
    target_type VARCHAR(32) NOT NULL,
    target_id UUID NOT NULL,
    direction VARCHAR(16),
    paper_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
    detail JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_by VARCHAR(64),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at TIMESTAMPTZ,
    resolved_by VARCHAR(64),
    resolution_note TEXT
);
```

**Indexes:** `idx_evidence_validation_records_status (status, rule_code)`, `idx_evidence_validation_records_target (target_type, target_id)`

**Code references:**
- `paper_evidence_service.py:102-133` -- `_write_validation_record()` inserts via raw SQL
- Called in: `attach_evidence()` (lines 920-971), `rollback_evidence()` (lines 1235-1251)
- Tests: `test_paper_evidence_batch.py`, `test_paper_evidence_snapshot.py`, `test_paper_evidence_e2e.py`

**Rule codes used:** `EV_PAPER_EVIDENCE_ATTACHED`, `EV_PAPER_EVIDENCE_MIXED`, `EV_PAPER_EVIDENCE_CONTRADICTORY`, `EV_CONFIDENCE_ADJUSTMENT_PENDING`, `EV_PAPER_EVIDENCE_INVALIDATED`

### ontology_change_logs

**Exists:** YES -- created in `20260806_ontology_governance.sql:30-41`

**Schema (ORM model in `models/ontology.py:156-169`):**
```sql
CREATE TABLE IF NOT EXISTS ontology_change_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    action_type VARCHAR(64) NOT NULL,    -- e.g. 'EVIDENCE_ATTACH', 'EVIDENCE_ROLLBACK'
    entity_type VARCHAR(64) NOT NULL,    -- e.g. 'evidence'
    entity_id UUID NOT NULL,
    before_data JSONB NOT NULL DEFAULT '{}'::jsonb,
    after_data JSONB NOT NULL DEFAULT '{}'::jsonb,
    operator_id VARCHAR(64),
    reason TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

**Index:** `idx_ontology_change_logs_entity (entity_type, entity_id)`

**Code references:**
- `paper_evidence_service.py:78-99` -- `_write_audit()` inserts via ORM (`session.add(OntologyChangeLog(...))`)
- Used in: `attach_evidence()` (line 896-919), `rollback_evidence()` (line 1222-1234)

---

## 10. Confidence Adjust Formula

**File:** `backend/app/services/confidence_rules.py:1-77`

### Constants

```python
FORMULA_VERSION = "paper_evidence_v1"
SUPPORT_CAP = 0.85
PARTIAL_CAP = 0.75
```

### AdjustmentResult Dataclass

```python
@dataclass
class AdjustmentResult:
    final_confidence: float | None
    adjustment_status: str   # 'applied' | 'pending' | 'none' | 'no_change_weak_evidence'
    formula_version: str     # 'paper_evidence_v1'
    apply: bool              # whether to update target confidence
    reason: str
```

### compute_adjustment Logic

```python
def compute_adjustment(*, direction: str, current_confidence: float | None, reviewer_confidence: float) -> AdjustmentResult:
    current = current_confidence if current_confidence is not None else 0.0
    reviewer = max(0.0, min(1.0, float(reviewer_confidence)))

    if direction == "supports":
        if reviewer >= current:
            final = min(SUPPORT_CAP, reviewer)       # cap at 0.85
            return AdjustmentResult(final_confidence=final, adjustment_status="applied", apply=True)
        # reviewer below current -> weak evidence, no change
        return AdjustmentResult(final_confidence=current, adjustment_status="no_change_weak_evidence", apply=False)

    if direction == "partial":
        if reviewer >= current:
            final = min(PARTIAL_CAP, reviewer)       # cap at 0.75
            return AdjustmentResult(final_confidence=final, adjustment_status="applied", apply=True)
        return AdjustmentResult(final_confidence=current, adjustment_status="no_change_weak_evidence", apply=False)

    if direction in ("contradicts", "mixed"):
        # Never auto-apply; pending human review
        return AdjustmentResult(final_confidence=current, adjustment_status="pending", apply=False)

    raise ValueError("not_found evidence cannot be stored as paper evidence")
```

### Summary Table

| Direction | Reviewer >= Current | Action | Result Cap |
|---|---|---|---|
| `supports` | Yes | Apply | min(0.85, reviewer) |
| `supports` | No | No change | current (unchanged) |
| `partial` | Yes | Apply | min(0.75, reviewer) |
| `partial` | No | No change | current (unchanged) |
| `contradicts` | any | Pending | current (unchanged, needs human) |
| `mixed` | any | Pending | current (unchanged, needs human) |
| `not_found` | any | ERROR | N/A |

---

## 11. Frontend Endpoint Signatures

**All from `frontend/src/api/endpoints.ts`:**

### attachPaperEvidence (line 5352)

```typescript
export const attachPaperEvidence = (body: {
  target_type: string
  target_id: string
  pmid: string
  direction: 'supports' | 'partial' | 'contradicts' | 'mixed' | 'not_found'
  evidence_level: 'direct' | 'indirect' | 'interpretive' | 'background'
  model_direction?: 'supports' | 'partial' | 'contradicts' | 'mixed' | 'not_found' | null
  model_assessment?: string | null
  reviewer_note?: string | null
  reviewer_confidence: number
  passages: EvidencePassageInput[]
}) => postJson<PaperAttachResponse>('/api/ontology/evidence/attach', body)
```

### attachPaperEvidencePreview (line 5479)

```typescript
export const attachPaperEvidencePreview = (body: {
  target_type: string
  target_id: string
  pmid: string
  direction: string
  reviewer_confidence: number
  passages: EvidencePassageInput[]
}, signal?: AbortSignal) => postJson<AttachPreviewResponse>('/api/ontology/evidence/attach-preview', body, undefined, signal)
```

### rollbackPaperEvidence (line 5488)

```typescript
export const rollbackPaperEvidence = (evidenceId: string, reason: string) =>
  postJson<{ evidence_id: string; status: string; changed: boolean; confidence: number | null }>(
    `/api/ontology/evidence/${evidenceId}/rollback`, { reason })
```

### completePaperEvidenceTaskItem (line 5614)

```typescript
export const completePaperEvidenceTaskItem = (taskId: string, itemId: string, evidenceId?: string | null) =>
  postJson<{ task_id: string; item_id: string; status: string; evidence_id: string | null }>(
    `/api/ontology/evidence/batch/${taskId}/items/${itemId}/reviewed`,
    undefined,
    { evidence_id: evidenceId ?? undefined })
```

### saveTaskItemDraft (line 5631)

```typescript
export const saveTaskItemDraft = (itemId: string, draft: Record<string, unknown>, revision = 0) =>
  putJson<{ item_id: string; saved: boolean; server_revision: number }>(
    `/api/ontology/evidence/batch/items/${itemId}/draft`,
    { draft, revision })
```

### Other Evidence Endpoints Summary

| Function | Method | URL |
|---|---|---|
| `searchPaperEvidence` | POST | `/api/ontology/evidence/search` |
| `extractPaperPassage` | POST | `/api/ontology/evidence/extract` |
| `extractSelectedPaperEvidence` | POST | `/api/ontology/evidence/extract-selected` |
| `getEvidenceTarget` | GET | `/api/ontology/evidence/target/{targetType}/{targetId}` |
| `listPaperEvidence` | GET | `/api/ontology/evidence/list` |
| `getEvidenceQueue` | GET | `/api/ontology/evidence/queue` |
| `translateEvidenceText` | POST | `/api/ontology/evidence/translate` |
| `createPaperEvidenceBatch` | POST | `/api/ontology/evidence/batch` |
| `listPaperEvidenceTasks` | GET | `/api/ontology/evidence/batch` |
| `getPaperEvidenceTask` | GET | `/api/ontology/evidence/batch/{taskId}` |
| `listPaperEvidenceTaskItems` | GET | `/api/ontology/evidence/batch/{taskId}/items` |
| `pausePaperEvidenceTask` | POST | `/api/ontology/evidence/batch/{taskId}/pause` |
| `resumePaperEvidenceTask` | POST | `/api/ontology/evidence/batch/{taskId}/resume` |
| `cancelPaperEvidenceTask` | POST | `/api/ontology/evidence/batch/{taskId}/cancel` |
| `retryPaperEvidenceTask` | POST | `/api/ontology/evidence/batch/{taskId}/retry-failed` |
| `getTaskItemDraft` | GET | `/api/ontology/evidence/batch/items/{itemId}/draft` |
| `saveTaskItemDraft` | PUT | `/api/ontology/evidence/batch/items/{itemId}/draft` |
| `previewEvidenceBatchScope` | GET | `/api/ontology/evidence/batch/preview` |

### EvidencePassageInput (line 5452)

```typescript
interface EvidencePassageInput {
  source_scope: 'abstract' | 'fulltext'
  section_title?: string | null
  paragraph_index?: number | null
  passage: string
  direction: 'supports' | 'partial' | 'contradicts' | 'not_found'
  reason?: string
  confidence?: number
  source_locator?: string | null
  source_verified?: boolean
}
```

---

## 12. SQL Insert Style in attach_evidence

### ORM Inserts (session.add + flush)

```python
# 1) MirrorEvidenceRecord -> ORM
record = MirrorEvidenceRecord(
    evidence_target_type=target_type,
    evidence_target_id=target_id,
    evidence_type="paper_verification",
    evidence_text="",   # rebuilt later
    # ... 30+ fields populated
)
session.add(record)
await session.flush()

# 2) MirrorEvidencePassage -> ORM (in loop)
session.add(
    MirrorEvidencePassage(
        evidence_id=record.id,
        # ... fields from verified passage dict
    )
)

# 3) ConfidenceAdjustmentLog -> ORM
session.add(
    ConfidenceAdjustmentLog(
        target_type=target_type,
        target_id=target_id,
        evidence_id=record.id,
        before_confidence=before,
        # ...
    )
)

# 4) OntologyChangeLog -> ORM (via _write_audit)
session.add(
    OntologyChangeLog(
        action_type="EVIDENCE_ATTACH",
        entity_type="evidence",
        entity_id=record.id,
        # ...
    )
)
```

### Raw SQL Inserts (text + execute)

```python
# evidence_validation_records -> raw SQL
await session.execute(
    text(
        "INSERT INTO evidence_validation_records "
        "(evidence_id, task_id, rule_code, status, target_type, target_id, direction, "
        "paper_snapshot, detail, created_by) "
        "VALUES (:eid, :tid, :rule, 'pending', :tt, :oid, :dir, CAST(:ps AS jsonb), CAST(:det AS jsonb), :cb)"
    ),
    {"eid": evidence_id, ...}
)

# paper_sources -> raw SQL with ON CONFLICT + RETURNING
await session.execute(
    text(
        "INSERT INTO paper_sources (...) VALUES (...) "
        "ON CONFLICT (pmid) WHERE pmid IS NOT NULL AND pmid <> '' "
        "DO UPDATE SET ... RETURNING id"
    ),
    {...}
)
```

### Style Summary

- **ORM** for: MirrorEvidenceRecord, MirrorEvidencePassage, ConfidenceAdjustmentLog, OntologyChangeLog (models with SQLAlchemy Mapped columns)
- **Raw SQL** for: evidence_validation_records, paper_sources (upsert logic), paper_evidence_tasks/task_items (not ORM-mapped tables)
- **Query style:** Raw SQL (`text(...)`) for complex queries; SQLAlchemy `select()` for simple queries on ORM-mapped tables

For any new review table: follow the same pattern -- use raw SQL for tables without ORM models, ORM for tables with Mapped columns.

---

## State Machine Diagram (Summary)

```
[佐证任务 Queue Entry]
    |
    v
[证据候选 EvidenceCandidatesModule]  -- select passages, verify, add to review
    |
    |  writes: sessionStorage draft (evidence-center.review-draft.<targetId>)
    |  writes: sessionStorage reviewBasket
    v
[人工审核 EvidenceReviewModule]  -- review decisions
    |
    |  persistDraft() -> sessionStorage (auto 500ms + on exit)
    |  handleSaveDraft() -> sessionStorage + backend review_draft JSONB
    |  handleApprove() -> sessionStorage review_approved status
    |  handleReject() -> sessionStorage rejected status
    |
    |  DATA WRITTEN:
    |    sessionStorage: evidence-center.review-draft.<targetId>  (full state)
    |    sessionStorage: evidence-center.review-approved.<targetId>  (status + meta)
    |    Backend DB: paper_evidence_task_items.review_draft  (if taskItemId exists)
    |
    v
[证据晋升 EvidencePromotionModule]  -- attach to Mirror KG
    |
    |  listReviewApproved() -> reads sessionStorage review-approved records
    |  Draft recovery -> reads sessionStorage review-draft
    |  handlePromote() -> POST /api/ontology/evidence/attach
    |
    |  Backend attach_evidence():
    |    1. verify_paper(pmid) -> Europe PMC API
    |    2. ensure_paper_source() -> INSERT/UPDATE paper_sources
    |    3. Verify target -> TARGET_MODELS lookup
    |    4. Build claim -> build_target_dto()
    |    5. Verify passages -> tiered verification against source
    |    6. Compute coverage -> backend-authoritative
    |    7. Dedup check -> passage_hash duplicate count
    |    8. Confidence adjustment -> compute_adjustment()
    |    9. INSERT mirror_evidence_records (ORM)
    |   10. INSERT mirror_evidence_passages (ORM, one per verified passage)
    |   11. UPDATE target.confidence + INSERT confidence_adjustment_logs (ORM)
    |   12. UPDATE target.evidence_text = rebuild_evidence_text()
    |   13. INSERT ontology_change_logs (ORM, audit)
    |   14. INSERT evidence_validation_records (raw SQL)
    |
    |  DATA WRITTEN (backend):
    |    mirror_evidence_records: 1 row
    |    mirror_evidence_passages: N rows (verified passages)
    |    confidence_adjustment_logs: 1 row (if adjustment applied)
    |    ontology_change_logs: 1 row (EVIDENCE_ATTACH)
    |    evidence_validation_records: 1-2 rows (EV_PAPER_EVIDENCE_* rules)
    |    target table (connection/function/circuit): confidence + evidence_text updated
    |
    |  DATA CLEARED (frontend):
    |    sessionStorage: evidence-center.review-draft.<targetId> (deleted)
    |    sessionStorage: evidence-center.review-approved.<targetId> (deleted)
    |
    v
[已晋升 / 已失效 lists]  -- EvidencePromotionModule displays listPaperEvidence results
    |
    |  handleRollback() -> POST /api/ontology/evidence/{id}/rollback
    |    Backend: sets verification_status='invalidated', rolls back confidence log,
    |    recomputes target confidence from remaining applied logs,
    |    writes audit + validation (EV_PAPER_EVIDENCE_INVALIDATED)
```
