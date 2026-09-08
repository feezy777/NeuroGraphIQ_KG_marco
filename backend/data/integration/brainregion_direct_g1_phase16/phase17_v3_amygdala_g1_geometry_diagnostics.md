# Phase1.7 V3 - Amygdala G1 authoritative reference geometry construction

Canonical: Left Amygdala NGIQ-BR-00000253 / Right Amygdala NGIQ-BR-00000261 (G1_MACRO, whole Amygdala).
Scope verdict: AMYGDALA_G1_SCOPE_FROZEN (included 9 amygdala channels; excluded 19 hippocampal + 1 HATA-transition + 1 background).
IF/MF entity-type review is NOT resolved by this construction (no scope widening).

Source: FreeSurfer/Iglesias HippoAmygProbs.MNIsymSpace left/right (left sha a79d5f88acfa..., right sha 4d20bb95435a...).
Probability semantics: MUTUALLY_EXCLUSIVE_CATEGORICAL (sum over 30 channels == 1.0 at every voxel); Amygdala aggregation operator = SUM over the included channels.

Native geometry (ICBM152 2009c SYM, 0.25 mm):
  Left  GEO-G1-AMYG-L-FS2009CSYM-V1: weighted volume 2318.24 mm3, support 311378 vox, centroid (-23.52, -3.75, -20.06), sha 6aceaf66bc6f4baf5df430d9c65a7717d925564873dec00695940908f0c716c7
  Right GEO-G1-AMYG-R-FS2009CSYM-V1: weighted volume 2318.24 mm3, support 311378 vox, centroid (23.52, -3.75, -20.06), sha e3f7f2acbd6da0db94daf4ef16db8949aee029d146857edab1571e1502489b97
Reference-grid geometry (MNI152NLin2009cAsym / Julich, 193x229x193 @1mm):
  Left  GEO-G1-AMYG-L-MNI2009CASYM-V1: weighted volume 2318.676 mm3, centroid (-23.52, -3.76, -20.06), sha 51229502646da36dabedeebc178d7e35f2a4f550f05dfbe9fc1ecf8aba784f28
  Right GEO-G1-AMYG-R-MNI2009CASYM-V1: weighted volume 2318.676 mm3, centroid (23.52, -3.76, -20.06), sha 5dbf039922444e02c2e12b8bc0393b5330e5226520d6122efcacb59082a812fc
Spatial bridge: SPB-MNI2009C-SYM-ASYM-SHARED-FRAME-V1 (SHARED_COORDINATE_REFERENCE_GRID_RESAMPLING); registration_applied=FALSE, nonlinear_registration_applied=FALSE, resampling_applied=TRUE, interpolation=LINEAR. No threshold/binarization/clipping/renormalization; no artificial symmetrization.

Evidence limitation preserved: TEMPLATE_VARIANT_ANATOMICAL_MISMATCH_NOT_EXPLICITLY_WARP_CORRECTED.
template_variant_uncertainty = PRESENT; direct_overlap_grid_ready = TRUE; direct_validation_executed = FALSE.

Binary NIfTI are local (gitignored); only SHA256 + manifests are tracked.
No DB write; classification untouched (86/132/93); Promotion not executed; no commit in-script.

