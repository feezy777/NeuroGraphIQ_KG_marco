# BrainRegion Integration — Phase 2F Gate Report
## Brainnetome 246 Probability Components — Batch Transform to Julich MNI152NLin2009cAsym

**Date:** 2026-09-03
**Branch:** develop (no commit / no push — gate did not authorize)
**DB writes:** none. **Migration:** none. **Julich 414 PM resampled:** no (left native). **Overlap / mapping:** none.

---

## 1. Result

**processed = 246 · skipped = 0 · failed = 0** → **READY_FOR_G4_G3_PROBABILITY_OVERLAP**

| Metric | Count |
|---|---|
| valid transformed outputs | 246 / 246 |
| TARGET_GRID_MATCH (193³ · 1 mm · RAS · Julich native affine) | 246 / 246 |
| finite (NaN=0, Inf=0) | 246 / 246 |
| range (normalized 0–1) | 246 / 246 |
| nonempty | 246 / 246 |
| hemisphere flips (mass-majority, midline-aware) | **0** |
| cross-check (independent read-back vs transform provenance) | 246 / 246 |
| boundary-touch anomaly candidates | 0 |
| outer-5 mm shell mass-heavy parcels (clipping proxy) | 0 |
| L/R pair QA (123 bilateral pairs, each L+R) | 123 pairs, 0 malformed |
| Julich 414 target grid (read-only re-verify) | 414 / 414 |

## 2. Batch parameters (frozen from Phase 2E — unchanged)

- executor `SimpleITK 2.5.6`, transform h5 **as-stored (no GetInverse)** (direction locked in Phase 2E: template-agreement Dice 0.9726)
- interpolation **Linear**, background **0**
- target reference = **a real Julich v3.1 native PM grid** (not the 1mm BN grid, not a registration)
- source = `BNA_PM_4D.nii.gz` (MNI152NLin6Asym/HCP40 1.25 mm, 145×173×145×246, 0–100 percent) — **bit-identical after batch (SHA verified)**
- Julich raw maps **not resampled/rewritten/normalized**; 414/414 confirmed on identical 2009c grid

## 3. Normalization / storage policy

- SimpleITK interpolates in original **percent** space.
- Raw percent is a **processing intermediate** (not persisted per component).
- **Formal stored asset = normalized probability = transformed_percent / 100 (range 0–1)** — the shared-scale input for the future Julich × Brainnetome overlap.
- No 4D copy was produced (avoiding a ~3.6 GB float32 4D NIfTI). Output = **246 independent compressed per-component NIfTI** (resumable, individually verifiable, single-file corruption contained).
- File name carries component index + official BNA code, e.g. `BNA_PM_comp081_MTG_L_4_1_prob_2009c.nii.gz`.

## 4. Outputs

```
backend/data/atlases/brainnetome/bna246/transformed_to_julich2009c/
├── probability_maps/  246 × BNA_PM_comp###_<official_code>_prob_2009c.nii.gz
├── provenance/        246 × comp###_provenance.json   (per-component source/target stats + SHA + checks)
└── manifest/          batch_run_record.json
```
Smoke dir `transformed_to_julich2009c_smoke/` **kept separate and untouched**.

Integration artifacts:
- `backend/data/integration/g3_brainnetome_to_julich_batch_transform_manifest.csv` — 246 rows (all required columns)
- `backend/data/integration/g4_g3_batch_transform_validation.json` — summary (phase G4_G3_BATCH_TRANSFORM_V1)
- `backend/data/integration/qa/g4_g3_batch_transform/rep_comp*.png` — 6 representative source/transformed slice QA

## 5. QA statistics (whole batch)

- **probability_sum_ratio** (target sum / source sum): median **0.0207**, P5 0.0195, P95 0.0221, min 0.0180, max 0.0244 — no outliers. This ratio is EXPECTED ≈ voxel-upsampling factor (1.25³→1³ ≈ 1.95×) × percent→probability (÷100) ≈ 0.0195 baseline; tight P5–P95 band confirms uniform, non-anomalous behaviour.
- **support_volume_ratio**: median 3.05, P5 2.76, P95 3.46, min 2.57, max 3.68 — tighter grid + trilinear tails; no outlier.
- Representative deterministic set (2L/2R/near-midline/subcortical): MTG_L_4_1 & STG_L_6_4 (left), MTG_R_4_1 & STG_R_6_4 (right), CG_R_7_5 (near-midline, |x|=4.4), Tha_L_8_4 (subcortical) — all CoM stable across transform, correct side preserved.

## 6. Disk footprint

- Source `BNA_PM_4D.nii.gz` = 8,547,072 B (unchanged)
- 246 normalized maps total = **35.96 MB** (median 145,634 B, max 284,750 B, min 51,854 B)
- Per-component provenance total ≈ 0.5 MB
- No raw-percent copies, no 4D copy, no temp/cache copies (temp intermediates deleted; `_*` files = 0)

## 7. Rerun safety (verified)

Second execution of the same batch:
**processed = 0 · skipped = 246 · failed = 0**; output SHAs and per-component provenance timestamps unchanged (no rewrite).

## 8. Frozen-state protection (verified before + after)

- G3→G1 aggregation: rows=246, active=246, approved=246, rollup=172 — unchanged
- G4→G3 production rows = 0 (no mapping added)

## 9. Tests

`backend/tests/test_g4_g3_batch_transform.py` — **20 passed** (covers gate section-22 items 1–20 incl. rerun-idempotency).
Full G4→G3 spatial regression (7 files): **111 passed**.

## 10. Out of scope (NOT executed)

Julich×Brainnetome overlap, contained/dominant/partial decisions, thresholds, mapping candidates, DB writes, commit/push, re-registration, Julich resampling. Next authorized phase would consume the two same-grid 0–1 probability sets (Julich 414 native + Brainnetome 246 transformed) for overlap.
