# BrainRegion Integration — Phase 2H Gate Report
## G4→G3 Spatial Evidence Interpretation & Decision Calibration Prep

**Date:** 2026-09-03
**Branch:** develop (no commit / no push). **DB writes:** none. **Relation thresholds:** none.
**contained/dominant/partial emitted:** none. **Mapping candidates:** none.

---

## Result

**READY_FOR_G4_G3_SCIENTIFIC_DECISION_POLICY** — 414 row-level evidence profiles, hard-label auxiliary coverage, evidence strata, shared-component review and a decision-free scientific review packet prepared. Final relation thresholds intentionally NOT defined here (owner/ChatGPT in the next phase).

## 1. Evidence roles (frozen)

- PRIMARY = Julich probability × Brainnetome probability (all Phase 2G metrics). Because Brainnetome PMs overlap, `g4_mass_weighted_g3` is NOT "% of G4 in G3" and is not a partition.
- AUXILIARY = hard-label containment: G4 probability mass inside Brainnetome `BN_Atlas_246_1mm` deterministic parcels (transformed to the Julich grid, NearestNeighbor).

## 2. Deterministic BNA label transform (auxiliary asset)

`BN_Atlas_246_1mm` (MNI152NLin6Asym 1mm) → Julich MNI152NLin2009cAsym native grid using the SAME official TemplateFlow H5, **NearestNeighbor / GenericLabel** (never linear).
- Output: `backend/data/atlases/brainnetome/bna246/transformed_label_to_julich2009c/BN_Atlas_246_1mm_NLin6to2009c_labels.nii.gz` (+ provenance).
- QA: grid match TRUE (193³, RAS, affine == Julich ref exactly), integer-only, labels ⊆ 0–246, **no parcel vanished** (labels_present 247/247). Raw label atlas untouched.

## 3. Hard-label coverage results (auxiliary)

For each G4 component: `hard_label_g4_coverage(i,j) = Σ[P4_i · I(BNA_label=j)] / ΣP4_i`. Per-voxel unique labels → per-row `Σ_j coverage ≤ 1`; remainder = `bna_uncovered_fraction`.

One-to-one (390) empirical distributions:
- **hard_top1_coverage**: median 0.46, P10 0.23, P75 0.58, P90 0.73, P95 0.82, max 0.95 (min ~2e-5)
- **hard_total_bna_coverage**: median ≈ 0.90 (implied by uncovered median 0.10)
- **bna_uncovered_fraction**: median 0.10, P90 0.52, P95 0.80, max 1.0
- **hard_top1_top2_margin** & **effective_target_count**: median 3.08 targets (max 24)

## 4. PP (primary) top1 distribution (one-to-one)

pp_top1_g4_weighted: median ≈ 0.58 (full distribution in summary). Spearman(hard_top1 vs pp_top1_g4w) = **0.916** (joint-2D, descriptive).

## 5. Top1 agreement (probability vs hard-label)

- TRUE = 358 · FALSE (disagreement) = **44** · NA (undefined) = 12 (10 zero-association + 2 shared/edge)
- Disagreement table: `g4_g3_probability_hardlabel_disagreements.csv` (44 rows, both evidence sets kept; NOT auto-resolved).

## 6. Zero-association semantic correction (interpretation layer)

10 Julich rows have max joint mass == 0 (all cerebellum/midbrain: dentate d/v, fastigial, interposed, nucleus ruber, L+R). Phase 2G's 5 "opposite top1" artifacts + 5 unflagged L-counterparts are here marked **NO_SPATIAL_ASSOCIATION** with **NULL top1** (no fabricated argmax). Phase 2G artifacts unchanged.

## 7. Coverage-gap candidates & evidence strata

- **coverage_gap_candidate_count = 9** (hard_total < 0.10, non-zero); plus 10 zero rows → cerebellum/midbrain/BNA-coverage-gap family isolated for review.
- Descriptive strata (NOT ontology relations): SINGLE_TARGET_CONCENTRATED 47 · MULTI_TARGET_CONCENTRATED 97 · DIFFUSE_ASSOCIATION 190 · PROBABILITY_HARDLABEL_DISAGREEMENT 44 · LOW_BNA_COVERAGE 7 · ZERO_BNA_ASSOCIATION 10 · SHARED_SPATIAL_REPRESENTATION 19.

## 8. Shared spatial representation (24 components)

- 24 shared components → **64 distinct canonical leaves** (NOT the hypothesized 50). Accounting: canonical union = one-to-one canonical subset **376** + shared canonical **64** = **440** ✓; **14** one-to-one single leaves are outside the 440-canonical registry (non-canonical leaves), which explains the 50-vs-64 discrepancy.
- No component-level score duplicated across canonical descendants (101,844 matrix rows remain one-per-spatial-component).
- Hierarchy-split investigation (official metadata only): **NO_INDEPENDENT_LEAF_SPATIAL_EVIDENCE** — each shared component has a single official probability map; no finer/hemisphere-child leaf map exists in the 414-map set.
- `g4_g3_shared_spatial_component_review.csv` (24 rows, status SHARED_COMPONENT_LEVEL_ONLY).

## 9. Representative examples + 2D pattern + threshold sensitivity (descriptive)

- `g4_g3_evidence_pattern_examples.csv` — deterministic sets A (top5 highest hard top1), B (5 smallest margins), C (10 highest uncovered), D (10 strongest disagreement), E (10 highest effective targets), F (shared examples).
- Joint 2D: HIGH-concentration cluster 43, dual-target band 111, low-coverage 19, ambiguous middle 217 (descriptive; not named contained/dominant/partial).
- `g4_g3_threshold_sensitivity_table.csv` (hard_top1 coverage ≥ cut): 0.5→156(414)/148(390) · 0.6→89/85 · 0.7→49/47 · 0.8→24/24 · 0.9→6/6 — **DESCRIPTIVE_ONLY_NOT_SCIENTIFICALLY_APPROVED**, no scientific rule chosen.

## 10. Scientific review packet (decisions blank)

`g4_g3_scientific_review_packet.csv` — **390** one-to-one rows, self-contained (identity, pp + hard top1–3, margins/ratios, coverage, uncovered, agreement, effective targets, pattern, QA flags) with **`scientific_decision` and `decision_reason` left blank** for the owner/ChatGPT decision phase.

## 11. Artifacts

```
g4_g3_overlap_interpretation_profiles.csv        (414 rows)
g4_g3_overlap_interpretation_summary.json
g4_g3_probability_hardlabel_disagreements.csv    (44)
g4_g3_shared_spatial_component_review.csv        (24)
g4_g3_scientific_review_packet.csv               (390, decisions blank)
g4_g3_evidence_pattern_examples.csv
g4_g3_threshold_sensitivity_table.csv            (DESCRIPTIVE_ONLY)
transformed_label_to_julich2009c/  (label asset + provenance)
```

## 12. State protection

- Phase 2G matrix hash unchanged (`SUM.phase2g_matrix_hash == Phase2G summary matrix_hash`, asserted).
- 414 Julich PM / 246 transformed BNA PM / raw BNA assets SHA unchanged (only auxiliary label + derived artifacts added).
- G3→G1 rows=246 active=246 approved=246 rollup=172; G4→G3 production rows=0 (asserted).

## 13. Tests

`backend/tests/test_g4_g3_overlap_interpretation.py` — **20 passed**. Related 2G+2H combined: **41 passed**.

## 14. Out of scope (NOT executed)

Final relation thresholds, contained/dominant/partial decisions, mapping candidates, DB writes, decision fills, commit/push. Next: Phase 2I owner/ChatGPT scientific decision policy.
