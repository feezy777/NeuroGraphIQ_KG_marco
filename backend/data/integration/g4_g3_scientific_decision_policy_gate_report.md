# BrainRegion Integration — Phase 2I-A Gate Report
## G4→G3 Scientific Decision Policy Application V1 (preliminary, owner review pending)

**Date:** 2026-09-03
**Branch:** develop (no commit / no push). **DB writes:** none. **Candidate staging / approval / promotion:** none.

---

## Result

**READY_FOR_G4_G3_OWNER_SCIENTIFIC_REVIEW** — 440 canonical G4 leaves each carry exactly one source-level preliminary decision; 14 noncanonical components audited separately; review_status = PENDING_OWNER_REVIEW everywhere.

## 1. Decision mother-set (Phase 2H corrected)

| set | components | canonical G4 |
|---|---|---|
| A DIRECT_CANONICAL_SPATIAL_EVIDENCE | 376 | 376 |
| B NONCANONICAL_SPATIAL_COMPONENT | 14 | 0 (audited separately, no production source) |
| C SHARED_SPATIAL_EVIDENCE | 24 | 64 (each leaf SHARED_SPATIAL_EVIDENCE_ONLY) |
| total canonical | — | 376 + 64 = **440** |

Noncanonical 14 = one-to-one spatial components whose single Julich leaf is absent from the 440-canonical registry (audit: `g4_g3_noncanonical_spatial_components.csv`, production_mapping_allowed=FALSE).

## 2. V1 decision ledger (440) — fixed policy order

1 shared exclusion → 2 noncanonical exclusion → 3 NO_G3_MAPPING (zero / coverage gap) → 4 disagreement conflict → 5 contained → 6 dominant → 7 partial → 8 fallback conflict.

| decision | count |
|---|---|
| APPROVE_CONTAINED_IN | **22** |
| APPROVE_DOMINANT_OVERLAP | **109** |
| PARTIAL_OVERLAP | **101** |
| NO_G3_MAPPING | **18** (10 ZERO_BNA_SPATIAL_ASSOCIATION + 8 BNA_COVERAGE_GAP) |
| CONFLICT_REVIEW | **126** |
| SHARED_SPATIAL_EVIDENCE_ONLY | **64** |
| total | 440 |

## 3. Conflict reason distribution (126)

PROBABILITY_HARDLABEL_TOP1_DISAGREEMENT 35 · HIGH_FRAGMENTATION 71 · LOW_DOMINANCE 6 · DIFFUSE_ASSOCIATION 8 · LOW_BNA_COVERAGE 1 · PARTIAL_TARGET_EVIDENCE_INCONSISTENT 5. Sorted in `g4_g3_conflict_review_queue.csv` (disagreement/boundary first, diffuse last).

## 4. Preliminary relation rows (only contained/dominant/partial)

`g4_g3_preliminary_relation_decisions.csv` — **367 rows** = contained 22 (1:1) + dominant 109 (1:1) + partial 236 (1:N, ≥2 targets per source; >2 kept when present). NO_MAPPING / CONFLICT / SHARED produce **zero** relation rows (asserted). No production mapping_id, no staging.

- future_rollup_eligible = TRUE only for contained (22 sources); DOMINANT and PARTIAL are NOT parent/rollup.

## 5. Representative examples

- **CONTAINED (5):** AcbM/Ventral Striatum Medial Accumbens (hard_top1 0.924 → BG accumbens L), AcbL Lateral Accumbens L (0.906), AcbL R (0.840), VTM Amygdala left (0.828), Area PFcm IPL right (0.890) — all hard/pp top1 agree, rollup TRUE.
- **DOMINANT (5):** FuCd Fundus of Caudate (0.675), AcbM R (0.661), VTM Amygdala right (0.647), Area 7P SPL right (0.572), Op1 POperc left (0.579) — single dominant target, not containment.
- **PARTIAL (5):** FuCd (0.558), Area 5L SPL right (0.465), 7PC SPL right (0.435), 7PC left (0.445), 5M SPL left (0.377) — ≥2 co-targets (multi-row).
- **CONFLICT (10):** VP Ventral Pallidum L/R (LOW_DOMINANCE / HIGH_FRAGMENTATION), FuP Fundus of Putamen L/R (PARTIAL_TARGET_EVIDENCE_INCONSISTENT / PP-HARDLABEL DISAGREEMENT), Ch4 Basal Forebrain R (disagreement), BST L/R (HIGH_FRAGMENTATION), etc.
- **NO_G3_MAPPING:** SNC/SNR Substantia Nigra, NRp Nucleus Ruber, cerebellum nuclei (hard_total≈0, pp≈0).
- **SHARED:** CM.AAA / CM.Ce / CM.Me Amygdala right share one component-level evidence (identical metrics), decision SHARED_SPATIAL_EVIDENCE_ONLY.

## 6. Sensitivity (DESCRIPTIVE_ONLY, does not change V1)

- contained hard_top1 cut: 0.75→25 · **0.80→22 (V1)** · 0.85→15
- dominant top1 cut: 0.45→134 · **0.50→109 (V1)** · 0.55→81

## 7. Policy thresholds (operational note recorded)

contained: hard_top1≥0.80, uncovered≤0.15, hard_top2≤0.10, eff_targets≤2.0, pp_ratio≥1.50; dominant: hard_total≥0.70, hard_top1≥0.50, margin≥0.20, pp_ratio≥1.25; partial: hard_total≥0.60, ≥2 targets each hard≥0.15 & pp>0, top2-cum≥0.60, all partial targets in pp Top3; NO_G3_MAPPING: (joint=0 & hard_total=0) or (hard_total<0.10 & pp_g4w<0.05). These are **project-conservative operational thresholds, NOT a universal neuroscience rule** (stated in summary policy artifact).

## 8. Artifacts

```
g4_g3_scientific_decision_policy_v1.csv           440-row ledger (review_status PENDING_OWNER_REVIEW)
g4_g3_preliminary_relation_decisions.csv          367 rows (contained/dominant/partial only)
g4_g3_conflict_review_queue.csv                   126 rows (prioritized)
g4_g3_shared_canonical_decision_exclusions.csv    64 rows (SHARED_SPATIAL_EVIDENCE_ONLY, mapping_allowed=FALSE)
g4_g3_noncanonical_spatial_components.csv         14 rows
g4_g3_scientific_decision_policy_summary.json
g4_g3_hard_label_coverage_matrix.npz              (supporting coverage matrix)
```

## 9. State protection (asserted)

- G3→G1 rows=246 active=246 approved=246 rollup=172; G4→G3 production rows=0.
- No DB write, no staging, no approval/promotion; decision artifact review_status = PENDING_OWNER_REVIEW (NOT human-reviewed / NOT approved).

## 10. Tests

`backend/tests/test_g4_g3_scientific_decision_policy.py` — **19 passed**. Related 2H+2I suites: **39 passed**.

## 11. Out of scope (NOT executed)

Staging, candidate load, approval/promotion, DB writes, ontology changes, threshold revisions, commit/push. Next: Phase 2I-B owner scientific review of the ledger / conflict queue / preliminary relations.
