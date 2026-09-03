# BrainRegion Integration — Phase 2G Gate Report
## G4 (Julich) × G3 (Brainnetome) Probability-Weighted Spatial Association Matrix (measurement only)

**Date:** 2026-09-03
**Branch:** develop (no commit / no push). **DB writes:** none. **Mapping/decision:** none. **Input NIfTI modified:** none.

---

## Result

**READY_FOR_G4_G3_OVERLAP_INTERPRETATION** — full 414 × 246 = **101,844** pair evidence computed, finite, ranges valid, deterministic (matrix hash stable across reruns).

## 1. Inputs re-locked (FAIL CLOSED path — all passed)

| Side | count | grid | scale | integrity |
|---|---|---|---|---|
| Julich G4 spatial components | 414 | 193×229×193 · 1 mm · RAS · shared affine (exactly equal across all 414) | 0–1 | 414/414 SHA = frozen alignment + provenance (no change) |
| Brainnetome G3 transformed PM | 246 | same grid / affine (exact equality with Julich) | 0–1 | 246/246 SHA = Phase 2F manifest (no change); raw BNA_PM_4D SHA unchanged |
| Shared voxel alignment | — | flat-index identical because affines are **exactly equal** | — | — |

## 2. Spatial components ≠ canonical rows (never inflated)

- 414 Julich **spatial components** (rows of this matrix) — the measurement unit.
- **390** components map to exactly 1 canonical G4 (ONE_TO_ONE_CANONICAL).
- **24** components are SHARED_SPATIAL_REPRESENTATION (2–4 canonical descendants; e.g. AREA_25_SACC, AREA_P24AB_PACC).
- Distinct canonical G4 leaves covered = **440** (the full canonical G4 registry entity count).
- The long matrix contains exactly `414 × 246` rows — **one score per spatial component × G3**, NEVER duplicated per canonical descendant → no fabricated independent canonical scores. Governance of shared components deferred to Phase 2H.

## 3. Metrics (frozen contract — all saved, none used for classification)

Let P4 = Julich component prob (0–1), P3 = Brainnetome prob (0–1), Σ over the shared 1 mm voxel grid:

| metric | formula | semantics |
|---|---|---|
| g4_probability_mass | Σ P4 | G4 row mass |
| g3_probability_mass | Σ P3 | G3 column mass |
| joint_weighted_mass (= _mm3) | Σ P4·P3 | probability-weighted spatial association (NOT a Bayesian joint prob) |
| g4_mass_weighted_g3_probability | joint / ΣP4 | mean G3 prob under G4 mass distribution |
| g3_mass_weighted_g4_probability | joint / ΣP3 | mean G4 prob under G3 mass distribution |
| probability_cosine | joint / √(ΣP4² · ΣP3²) | field similarity |
| soft_dice | 2·joint / (ΣP4² + ΣP3²) | field similarity |

`classification_thresholds = NOT_DEFINED`, `mapping_decisions_created = FALSE`. No P-thresholds, no binary masking, no contained/dominant/partial.

## 4. Computation (efficient, no resolution loss)

- Nonzero density: Julich 6.22 M / BNA 6.61 M voxels (<0.5 % of 193³).
- Core: single scipy sparse product `M = S4[414×V] @ S3[V×246]`; all directional/cosine/soft-dice metrics vectorized from M + per-row/col masses/norms. **No per-voxel Python loops, no downsampling, no thresholding, no discarding small voxels.**
- Full compute ≈ 60 s; outputs written atomically; deterministic row (sorted asset-file) and column (component_index) order.

## 5. Results summary

- joint_weighted_mass: median 0, max 6265.6; **10,324 (10.14 %) of pairs have non-zero spatial association** (most parcel×parcel pairs legitimately zero).
- g4_mass_weighted_g3 distribution: [0, 0.844]; g3_mass_weighted_g4: [0, 0.872]; cosine: [0, 0.822]; soft_dice: [0, 0.788].
- Hemisphere QA: real **flip count = 0**. 5 `top1-opposite` flags, all right **cerebellar/midbrain** Julich components (dentate/fastigial/interposed/nucleus ruber) with **no Brainnetome coverage** (row_max_joint_mass = 0) → degenerate near-zero argmax tie, NOT a flip; listed as QA_ANOMALY, not auto-deleted, cause `DEGENERATE_ZERO_G3_OVERLAP` recorded.
- Independent formula recomputation from M + masses/norms: **max abs error 0.0**.

## 6. Artifacts (backend/data/integration/)

| file | content |
|---|---|
| `g4_g3_probability_overlap_matrix.csv` | long-form, 101,844 rows (all mandated columns + lineage + hemisphere_relation + metric_version) |
| `g4_g3_probability_overlap_matrix.npz` | compact M / g4w / g3w / cosine / soft_dice / mass4 / mass3 / norm2_4 / norm2_3 + index vectors |
| `g4_g3_probability_overlap_rows.csv` | 414-row manifest (julich id/name/hemi, lineage, identity status) |
| `g4_g3_probability_overlap_columns.csv` | 246-column manifest (component/parcel/canonical_g3/hemi) |
| `g4_g3_probability_overlap_top10_by_g4.csv` | 414×2 schemes×10 Top-10 G3 per Julich component (browse only, not candidates) |
| `g4_g3_probability_overlap_top10_by_g3.csv` | 246×10 Top-10 Julich per G3 |
| `g4_g3_probability_overlap_summary.json` | phase `G4_G3_PROBABILITY_OVERLAP_V1`, all distributions, hemisphere QA, formulas, matrix_hash |
| `g4_g3_probability_overlap_qa.json` | representative QA detail + formula recompute check |
| `qa/g4_g3_probability_overlap/rep_*.png` (6) + `matrix_overview_heatmap.png` | deterministic reps (2L/2R cortex, near-midline, subcortical) + full-matrix heatmap |

Representative deterministic set (selected by true probability-weighted CoM, not by appearance): LATERAL_LEFT TE3_STG (x=−62.9), PFop_IPL (x=−60.9); LATERAL_RIGHT TE3_STG (x=+63.2), PF_IPL (x=+62.8); NEAR_MIDLINE Area33_ACC right (x=+5.2); SUBCORTICAL DG hippocampus left (x=−27.5).

## 7. Rerun determinism

Second compute execution produced the **identical matrix_hash `a64d0c598300d1f0e6d56c67c1e2564775287447d5c17f77741bcf96ec2df874`** and byte-identical NPZ M (verified in test). No thresholds/mapping/db during rerun.

## 8. State protection

- G3→G1 aggregation: rows=246 / active=246 / approved=246 / rollup=172 — unchanged.
- G4→G3 production rows = 0.
- Scientific spatial assets (414 Julich, 246 transformed BNA, raw BNA_PM_4D) SHA unchanged; added only derived metrics/QA/tests.

## 9. Tests

`backend/tests/test_g4_g3_probability_overlap.py` — **21 passed** (gate items 1–20 incl. rerun matrix-hash). Full G4→G3 spatial regression (8 files): **132 passed**.

## 10. Out of scope (NOT executed)

contained/dominant/partial decisions, relation thresholds, mapping candidates, DB writes, shared-component governance (→ Phase 2H), commit/push.
