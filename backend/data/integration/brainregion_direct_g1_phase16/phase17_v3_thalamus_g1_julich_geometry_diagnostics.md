# Phase1.7 V3 - Thalamus Julich-reference-grid G1 geometry (SPATIAL BRIDGE, v2)

## Adjudicated scientific position
- ICBM152 2009c symmetric and MNI152NLin2009cAsym are DIFFERENT template variants
  with SHARED stereotaxic world-coordinate frame.
- No authoritative nonlinear Sym->Asym anatomical warp is used; none is
  manufactured.
- Previous project-derived SyN attempt TRF-ICBM2009CSYM-TO-MNI2009CASYM-V1 is
  RETRACTED (ANTSPy SyN zero-displacement provenance anomaly on this runtime).

spatial_bridge_id = SPB-MNI2009C-SYM-ASYM-SHARED-FRAME-V1
spatial_bridge_class = SHARED_COORDINATE_REFERENCE_GRID_RESAMPLING  (NOT a TRF)
registration_applied = FALSE; nonlinear_registration_applied = FALSE; deformation_field_applied = FALSE
resampling_applied = TRUE; resampling_basis = SHARED_MNI152_2009C_WORLD_COORDINATE_FRAME
interpolation = LINEAR
template_variant_statement = DIFFERENT_TEMPLATE_VARIANTS_WITH_SHARED_STEREOTAXIC_COORDINATE_FRAME
residual_spatial_limitation = TEMPLATE_VARIANT_ANATOMICAL_MISMATCH_NOT_EXPLICITLY_WARP_CORRECTED
global shared-frame brain-mask Dice = 0.9872  (NOT proof of local thalamic anatomy identity)
direct-overlap evidence type = DIRECT_SPATIAL_OVERLAP_IN_SHARED_MNI2009C_COORDINATE_FRAME
left  = GEO-G1-THAL-L-MNI2009CASYM-V1  wvol_mm3=9080.456  centroid=[-11.241, -18.908, 6.039]  support=16822  rel_vol_change=-0.0
right = GEO-G1-THAL-R-MNI2009CASYM-V1  wvol_mm3=9080.571  centroid=[11.742, -18.908, 6.038]  support=16873  rel_vol_change=-0.0
output grid = 193x229x193 @1mm; affine == Julich reference (verified); zooms=1mm
left  output_sha256 = bd431608fcea3c5f0f7387b1b0e1010582fa2e39dae95a300b3bba976a10cc87
right output_sha256 = 73e4242b581f2420c316593f6cd85183ea7f99c29e2b817b0257cdf267c5bd3b
old SyN-derived geometry SHAs (37a82b65.../1c9b8b8d...) = SUPERSEDED / INVALIDATED_BY_TRANSFORM_PROVENANCE_REPAIR
direct_overlap_grid_ready = TRUE; template_variant_uncertainty = PRESENT
BN direct validation = PENDING_NEXT_FUNCTION; Promotion = BLOCKED
no DB write; no commit; no reclassification; no BN/G4 overlap; no nonlinear registration claimed

