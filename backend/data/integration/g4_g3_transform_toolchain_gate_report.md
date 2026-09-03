# BrainRegion Integration — Phase 2E Gate Report
## G4 (Julich-Brain v3.1) → G3 (Brainnetome BNA246): Standard Nonlinear Transform Toolchain + Single-Component Smoke Test

**Date:** 2026-09-03
**Branch:** develop (no commit / no push — gate did not authorize)
**DB writes:** none. **Migration:** none. **G3→G1 frozen state:** preserved (246/246/246/172, verified).

---

## 1. Scope executed (exactly one feature)

> 建立能够稳定应用官方 nonlinear transform 的正式执行工具链，并只选择 1 个 Brainnetome probability component 做完整 source→target smoke test。

1. Built the **formal executable toolchain** script `backend/scripts/transform_brainnetome_to_julich2009c.py` (SimpleITK 2.5.6) that applies the official TemplateFlow transform `MNI152NLin2009cAsym_from-MNI152NLin6Asym` (204 MB ITK composite h5).
2. **Locked the transform direction empirically** (as-stored, no inverse) via a template-agreement probe.
3. Ran **one** Brainnetome probability component (BNA_PM_4D comp 1 = `SFG_L_7_1`, left area 8m) through a complete source→target smoke → **PASS** (all 6 checks).
4. Batch transform (246 components), Julich resampling, overlap, and any G4→G3 spatial mapping were **explicitly NOT executed** (out of scope, as the gate requires stopping here).

## 2. Inputs

| Item | Path | SHA256 |
|---|---|---|
| Source PM 4D (0-100 percent, NLin6/HCP40 1.25mm) | `backend/data/atlases/brainnetome/bna246/volume_raw/BNA_PM_4D.nii.gz` | `b1318517…e97f020` |
| Official TemplateFlow transform | `backend/data/atlases/templateflow_ref/MNI152NLin2009cAsym_from-MNI152NLin6Asym_mode-image_xfm.h5` | `2e3869a0…3a4dfe` |
| Target reference (Julich native grid, an actual v3.1 PM) | `backend/data/atlases/julich/v3.1/spatial_raw/probability_maps/*.nii.gz` (193×229×193, 1 mm, RAS) | per-file recorded |
| 2009c template (for brain check) | `backend/data/atlases/templateflow_ref/tpl-MNI152NLin2009cAsym_res01_desc-brain_T1w.nii.gz` | — |

## 3. Toolchain decision + direction lock

- `antsApplyTransforms` NOT on PATH; antspy NOT installed; nitransforms public API cannot apply this 204 MB composite.
- **SimpleITK 2.5.6 reads and applies the ITK composite natively** — canonical toolchain.
- SimpleITK's `GetInverse()` **throws** on the DisplacementFieldTransform composite → inversion is neither needed nor possible.
- **Direction locked by template agreement:** resampling the real MNI152NLin6Asym template onto the real 2009c grid with the **as-stored** composite gives brain **Dice 0.9726** / intensity **corr 0.8597** vs the true 2009c template → the h5 is authored as the pull-back transform; `sitk.Resample(moving=<NLin6 img>, reference=<2009c grid>, transform=<h5 as-stored>, Linear, bg=0)` is correct.
  - Artifact: `g4_g3_transform_direction_lock.json`.

## 4. Smoke run (component 1, deterministic)

- Auto-select (deterministic, median safe band) → **component 1** = `SFG_L_7_1` / `A8m_L`, canonical `NGIQ-BR-00000001`, **left**.
- Physical lattice report: BN_Atlas_246_1mm and BNA_PM_4D/HCP40 1.25 mm grids share origin `(90, −126, −72)` → the 1.25 mm probability grid is a sub-lattice of the same MNI152NLin6Asym physical space.
- Interpolation: **Linear**, background 0. Raw percent preserved; normalized (÷100) 0–1 derivative also written.

| Check | Result |
|---|---|
| TARGET_GRID_MATCH (193×229×193, 1 mm, RAS affine = Julich native) | ✅ |
| NaN / Inf absent | ✅ (0 / 0) |
| raw percent range 0–100 | ✅ (max 98.96) |
| normalized range 0–1 | ✅ (max 0.9896) |
| no hemisphere flip | ✅ (left parcel CoM x = −7.81 mm, stayed left) |
| centroid within 2009c brain | ✅ |

Geometric proof of correctness: transformed volume world-bbox `x ∈ [−31, +1]`, `y ∈ [−20, 73]`, `z ∈ [−2, 81]`, CoM `(−7.8, 16.3, 53.3)` — exactly the left superior-frontal (area 8m) location expected. A wrong direction or a physically mispositioned source would not land there.

### Smoke outputs
- `backend/data/atlases/brainnetome/bna246/transformed_to_julich2009c_smoke/BNA_PM4D_comp001_NLin6to2009c_raw_percent.nii.gz`
- `…/BNA_PM4D_comp001_NLin6to2009c_probability.nii.gz` (normalized derivative)
- QA: `backend/data/integration/qa/g4_g3_transform_smoke/smoke_comp001_{provenance.json,slices.png}`
- Source BNA_PM_4D bit-identical (SHA verified unchanged).

## 5. Validation

- New targeted suite `backend/tests/test_g4_g3_transform_toolchain.py` — **20 passed**.
- Full G4→G3 spatial regression (all 6 files incl. this one): **91 passed**.
- Scope discipline verified by test: only `comp001` output pair exists (no 246-component batch).

## 6. State / constraints preserved

- G3→G1 production: 246 total / 246 active / 246 approved / 172 rollup — **unchanged** (test-asserted).
- No G4→G3 aggregation rows added (246 rows only).
- No DB writes, no migration applied, no commit/push.

## 7. Readiness + next phase (explicitly NOT executed here)

**READY_FOR_G4_G3_BATCH_TRANSFORM**

Next phase must (when authorized):
1. Batch-transform all 246 BNA_PM_4D components with this same toolchain (deterministic, per-component provenance + SHA).
2. Resample the 414 Julich PMs onto a shared grid (target authority is the Julich native 2009c grid).
3. Reconcile the Brainnetome **0–100 percent** scale by ÷100 before any overlap (never normalize the stored raw asset).
4. Compute overlap and — only through the full review/promotion pipeline — produce G4→G3 spatial mappings. No direct writes to `final_*` or aggregation tables.
