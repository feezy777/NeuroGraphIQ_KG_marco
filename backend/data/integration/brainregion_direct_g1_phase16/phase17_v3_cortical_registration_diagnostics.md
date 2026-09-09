# Phase1.7 V3 - fsaverage -> MNI152NLin2009cAsym project-derived whole-template registration execution + QC freeze

VERDICT: CORTICAL_TARGET_PROJECT_DERIVED_TRANSFORM_FROZEN
run: RUN-CORT-FSAVG-TO-MNI2009C-DIRECT-V1 | transform: TRF-CORT-FSAVG-TO-MNI2009C-DIRECT-V1 (direct R_D; no MNI305/NLin6/talairach intermediate)
moving = fsaverage mri/orig.mgz (sha 97862f8adfa48ff0...) | fixed = MNI152NLin2009cAsym res01 desc-brain (sha 97cee2cf7f51388d...)
runtime ANTs SyN (ANTsPy 0.6.3); runtime sanity PASS (no zero-warp anomaly); seed 17; regular sampling.
pass flags: {"runtime_registered": true, "deformation_valid": true, "finite": true, "nonzero_disp": true, "zero_frac_ok": true, "max_disp_ok": true, "coverage_min_ok": true, "coverage_not_degraded_vs_affine": true, "no_truncation_ok": true, "laterality_ok": true}
coverage(fixed-brain by warped content) baseline/affine/nonlinear = 0.9766 / 0.9975 / 0.9951
COM disp affine/nonlinear = 10.52 / 7.75 mm; fov_no_truncation = True
deformation max 11.584011975037585 mm, median 0.01748558984068652 mm, zero-vec frac 0.256755, finite True
Jacobian median 1.0, negative frac 0.001341, min -2.5100693912563163
inverse status AVAILABLE; roundtrip coverage 0.6129778056091939
laterality preserved: True
mapping independence: whole-template anatomical intensities only; metric restricted to the fixed whole-brain mask; no DK/G4/Julich/Brainnetome labels, no mapping results -> circularity NONE. No FreeSurfer/license, no ribbon, no label transform, no cortical geometry, no G4 overlap, no DB, no reclassification, no promotion.
route_v1 generated: phase17_v3_cortical_target_route_v1.json (only on FROZEN).

