# Data Enhancement Engine — Design Spec

**Date:** 2026-08-03
**Status:** Draft
**Context:** DeepSeek 只诊断阻塞原因但不实际修正数据 — 验证中心需要成为数据质量提升引擎。

---

## 1. Problem Statement

### 1.1 Current State (Broken)

```
规则校验 → 发现阻塞 → DeepSeek 诊断 → 建议修正 → 人类审批 → ?
                                                    ↑
                                          修正质量差（UUID字段填中文）
                                          只改字段值，不补缺失内容
                                          不生成证据、不交叉验证
```

### 1.2 Target State

```
规则校验 → 发现缺口 → DeepSeek 分层增强 → 自动修复(可回填的) + LLM建议(待审)
                              ↓
                        数据质量分提升
                        可追溯、可回退
```

### 1.3 Key Data Gaps (Macro, Sep 2026)

| Field | Fill Rate | Priority |
|-------|-----------|----------|
| step evidence_text | 2.1% | P0 |
| circuit evidence_text | 22.2% | P0 |
| source_atlas | 34.2% | P0 |
| provenance chain | 22.2% | P1 |
| step description | 68.7% | P1 |

---

## 2. Architecture

### 2.1 Three-Phase Pipeline

```
Phase 1: Rule Validation  (existing)
  12 rules → per-circuit gap report + quality score

Phase 2: Tiered Enhancement (NEW)
  Tier 1 — Auto-apply (deterministic, no LLM)
  Tier 2 — LLM-suggest (DeepSeek, pending human review)

Phase 3: Human Review  (existing HumanReviewPanel, extended)
  Tier 2 suggestions → approve / reject / edit
```

### 2.2 Tier 1 — Auto-Apply

Triggered by rule validation results. Deterministic backfill from existing data. **No LLM calls, no human review needed.**

| Fix | Source Table | Method |
|-----|-------------|--------|
| `source_atlas` | `CandidateBrainRegion.source_atlas` | From circuit's linked regions |
| `resource_id` | `MirrorCircuitStep → CandidateBrainRegion → resource_id` | Trace through step → region → resource |
| `batch_id` | Same provenance chain | Reconstruct from resource |
| `circuit_type` normalization | Known enum map | `known_circuit_types` (12 values) |
| `step_type` / `role` normalization | Known enum map | `valid_roles`, `valid_types` sets |
| `closed_loop` detection | Steps topology | first_step.region == last_step.region |
| `region_candidate_id` backfill | CircuitSelector (existing) | Steps with names → candidate match |
| MirrorCircuitRegion creation | From step region_candidate_id | Phase 1 of existing region-match |

**Security:** Only writes to `mirror_region_circuits` and `mirror_circuit_steps` (mirror tables). Never touches `final_*`.

### 2.3 Tier 2 — LLM-Suggest

DeepSeek generates content for fields that cannot be deterministically backfilled. All output marked `suggestion_source="deepseek"`, `approval_status="proposed"`.

| Suggestion | Prompt Strategy | Fallback |
|-----------|----------------|----------|
| `evidence_text` | Given: circuit topology + step names + source atlas. Generate: 2-4 sentence evidence summary citing the source. | Empty → manual needed |
| `description` | Given: circuit name + type + steps + function. Generate: 1-2 sentence description. | Empty |
| `function_association` cross-check | Given: circuit function + step regions + atlas. Flag: inconsistencies. | "unverified" |
| Topology sanity | Given: step roles + circuit type + closed_loop. Flag: role mismatches (e.g., origin as last step) | "unverified" |
| Step name → region name match | Given: step_name + candidate list. Score: 0-1 match confidence. Flag: <0.5 | Mark "llm_suggested" |

**Storage:** Each suggestion writes to a new `MirrorEnhancementSuggestion` table (same pattern as `MirrorCircuitCorrection` but broader scope — not just corrections, also new content).

### 2.4 Data Quality Score

Computed per circuit after rule validation. Ranges 0–100.

| Dimension | Weight | Max Points | Criteria |
|-----------|--------|------------|----------|
| Field Completeness | 30 | All required fields non-null | circuit_name, circuit_type, source_atlas, evidence_text, description 各 6 分 |
| Provenance | 20 | resource_id + batch_id + llm_run_id all present | 链完整=20, 部分=10, 无=0 |
| Topology Health | 20 | Steps ≥ 2, start/end defined, valid types | 步骤数(5) + 首尾角色(10) + 类型(5) |
| Evidence Quality | 20 | Evidence length ≥ 50 chars, step-level evidence | 回路证据(10) + 步骤证据(10) |
| Region Association | 10 | MirrorCircuitRegion count ≥ 2 | ≥2=10, 1=5, 0=0 |

**Display:** Badge on circuit rows, sortable, visible in detail drawer.

---

## 3. API Design

### 3.1 New Endpoints

#### `POST /api/validation/circuit/selection/enhance`

Trigger enhancement for circuits from a completed validation run.

```json
// Request
{
  "run_id": "uuid",            // required — the completed validation run
  "circuit_ids": ["uuid",...], // optional — subset; omit = all in run
  "tier2_enabled": true,       // default true — run LLM suggestions
  "dry_run": false
}

// Response
{
  "run_id": "uuid",
  "tier1_fixes": {
    "source_atlas_backfill": 115,
    "provenance_backfill": 80,
    "enum_normalization": 20,
    "topology_fix": 5,
    "region_creation": 30,
    "total": 250
  },
  "tier2_suggestions": {
    "evidence_text": 150,
    "description": 200,
    "function_crosscheck": 30,
    "topology_flags": 5,
    "total": 385
  },
  "quality_score_change": {
    "before_avg": 45.2,
    "after_avg": 72.8
  },
  "circuit_scores": [
    {"circuit_id": "uuid", "before": 38, "after": 71},
    ...
  ]
}
```

#### `GET /api/validation/circuit/candidates/{circuit_id}/enhancements`

List all Tier 2 suggestions for a circuit (pending human review).

```json
// Response
{
  "items": [{
    "id": "uuid",
    "circuit_id": "uuid",
    "field_path": "evidence_text",
    "suggested_value": "...",
    "confidence": 0.85,
    "suggestion_type": "evidence_generation",
    "approval_status": "proposed",
    "created_at": "..."
  }],
  "total": 5
}
```

#### `POST /api/validation/circuit/enhancements/{id}/approve`

Approve a Tier 2 suggestion. Applies the suggested value to the source table (same pattern as `_apply_correction_to_source`).

#### `POST /api/validation/circuit/enhancements/{id}/reject`

Reject a Tier 2 suggestion.

### 3.2 Extended Existing Endpoints

#### `GET /api/validation/circuit/candidates`

Add optional query params:
- `min_quality_score` — filter circuits below quality threshold
- `sort_by` — add `quality_score` as sort option

Response adds `quality_score` field to each item.

---

## 4. Database

### 4.1 New Table: `mirror_enhancement_suggestions`

```sql
CREATE TABLE mirror_enhancement_suggestions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  circuit_id UUID NOT NULL,
  validation_run_id UUID,        -- which run triggered this
  field_path TEXT NOT NULL,      -- "circuit.evidence_text" / "steps.3.description"
  suggested_value JSONB,         -- the suggested content
  original_value JSONB,          -- value before suggestion (for before/after)
  suggestion_type TEXT NOT NULL, -- evidence_generation / description_fill / function_crosscheck / topology_flag
  suggestion_source TEXT DEFAULT 'deepseek',
  confidence REAL,               -- 0.0–1.0
  approval_status TEXT DEFAULT 'proposed', -- proposed / approved / rejected
  approved_by TEXT,
  approved_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT now()
);
```

### 4.2 New Column: `mirror_region_circuits.quality_score`

```sql
ALTER TABLE mirror_region_circuits
  ADD COLUMN quality_score REAL DEFAULT NULL;
```

Updated by enhancement pipeline and rule validation.

---

## 5. Frontend Changes

### 5.1 RuleValidationTab — Progress Modal Footer

After rule validation completes, the modal footer shows three actions:

```
[送入双模型审核(N)] [数据增强(N个缺失字段)] [DeepSeek 诊断(N条阻塞)]
```

### 5.2 Enhancement Progress Modal (NEW)

Triggered by "数据增强" button. Shows:

- **Tier 1 progress** — real-time counters for each auto-fix type
- **Tier 2 summary** — count of LLM suggestions by category
- **Quality score delta** — before → after average
- **[查看 LLM 建议]** button — navigates to details
- **[关闭]** button

### 5.3 HumanReviewPanel Extension

Tier 2 suggestions appear in the existing human review tab with:

- `suggestion_type` badge to distinguish from other review items
- Before/after diff view
- Confidence score from DeepSeek
- Approve / Reject / Edit actions

### 5.4 Quality Score Badge

Displayed on:
- Candidate circuit table rows (sortable column)
- Circuit detail drawer (prominent card)
- Validation progress result table

---

## 6. New File Manifest

### Backend

| File | Purpose |
|------|---------|
| `app/models/mirror_enhancement_suggestion.py` | ORM model for new table |
| `app/schemas/enhancement.py` | Pydantic request/response schemas |
| `app/services/enhancement_service.py` | Tier 1 deterministic fixes + Tier 2 LLM orchestration |
| `app/routers/enhancement.py` | New router (`/api/validation/circuit/enhancements/...`) |
| `migrations/NNN_enhancement_suggestions.sql` | DDL migration |

### Frontend

| File | Purpose |
|------|---------|
| `components/EnhancementModal.tsx` | Progress modal for enhancement run |
| `components/EnhancementSuggestionList.tsx` | Tier 2 suggestion review list |
| `components/QualityScoreBadge.tsx` | Reusable quality score badge |

### Modified Files

| File | Change |
|------|--------|
| `validation_circuit.py` | Add `/selection/enhance` endpoint; add `quality_score` to candidate list |
| `validation_circuit.py` | Add `/candidates/{id}/enhancements` endpoint |
| `mirror_circuit_validation_service.py` | `run_rule_validation` computes quality_score |
| `RuleValidationTab.tsx` | Add "数据增强" button in progress modal footer |
| `HumanReviewPanel.tsx` | Show Tier 2 enhancement suggestions |
| `CandidateCircuitTable.tsx` | Quality score column |
| `CircuitDetailDrawer.tsx` | Quality score card |

---

## 7. Scope Boundaries

### In Scope
- Tier 1 auto-fixes for `source_atlas`, provenance chain, enum normalization, region creation
- Tier 2 LLM suggestions for evidence_text, description, cross-checks
- Quality score computation and display
- Enhancement triggered from completed validation runs
- Human review of Tier 2 suggestions

### Out of Scope (Future)
- Continuous background enhancement (cron)
- Multi-model cross-validation for evidence (Kimi + DeepSeek)
- Evidence citation extraction from PDF sources
- Auto-promotion of circuits reaching quality threshold

---

## 8. Acceptance Criteria

1. Enhancement triggered from rule validation progress modal for macro circuits
2. Tier 1 auto-fixes applied without errors — no invalid UUID writes (lesson from correction bug)
3. Tier 2 suggestions created with confidence > 0.5
4. Quality score computed and visible on circuit list and detail
5. Tier 2 suggestions appear in human review queue
6. Approving a Tier 2 suggestion applies the value to the source table
7. No regression — existing rule validation, dual review, promotion unchanged

---

## 9. Risks

| Risk | Mitigation |
|------|-----------|
| DeepSeek generates hallucinated evidence | All Tier 2 output marked `llm_suggested` + human review gate |
| DeepSeek suggests invalid field values | UUID/type validation in `_apply_correction_to_source` (already fixed) |
| Large circuits (>50 steps) exceed prompt token limit | Truncate to first 20 steps, note truncation in response |
| Concurrent enhancement runs on same circuits | Idempotency key, skip already-fixed fields |
