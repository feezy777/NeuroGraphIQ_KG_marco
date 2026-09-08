# Phase1.7 V3 - Brainnetome G3 Thalamus -> THALAMUS_PROPER G1 direct spatial validation

EVIDENCE TYPE: DIRECT_SPATIAL_OVERLAP_IN_SHARED_MNI2009C_COORDINATE_FRAME
SHARED_TEMPLATE_VARIANT_UNCERTAINTY: PRESENT
residual limitation: TEMPLATE_VARIANT_ANATOMICAL_MISMATCH_NOT_EXPLICITLY_WARP_CORRECTED
NOT DIRECT_OVERLAP_AFTER_AUTHORITATIVE_SYM_TO_ASYM_REGISTRATION (no authoritative nonlinear Sym->Asym registration is claimed).

G1 left  sha = bd431608fcea3c5f0f7387b1b0e1010582fa2e39dae95a300b3bba976a10cc87  (GEO-G1-THAL-L-MNI2009CASYM-V1)
G1 right sha = 73e4242b581f2420c316593f6cd85183ea7f99c29e2b817b0257cdf267c5bd3b  (GEO-G1-THAL-R-MNI2009CASYM-V1)
superseded G1 SHAs rejected: 37a82b65d86d... / 1c9b8b8de910...
spatial_bridge_id = SPB-MNI2009C-SYM-ASYM-SHARED-FRAME-V1
registration_applied = FALSE; nonlinear_registration_applied = FALSE; resampling_applied = TRUE

Universe = 16 (left 8 / right 8), read from the frozen manifest and bound to DEC-THAL-ROLLUP-01..16.
Evidence grades: directly_supported=7, with_boundary_uncertainty=8, direct_spatial_conflict=1, insufficient=0.
Mapping verdicts: 7 keep-directly-supported / 8 keep-with-uncertainty / 1 requires-review.

Per-relation (weighted_containment C | outside-envelope O | midline W | grade):
  DEC-THAL-DIRECT-01 Tha_L_8_1 (mPFtha, l) C=0.747 O=0.074 W=0.0000 vol=1991 @0.5=0.753 -> DIRECTLY_SUPPORTED
  DEC-THAL-DIRECT-02 Tha_L_8_2 (mPMtha, l) C=0.123 O=0.468 W=0.0000 vol=1411 @0.5=0.114 -> DIRECT_SPATIAL_CONFLICT
  DEC-THAL-DIRECT-03 Tha_L_8_3 (Stha, l) C=0.468 O=0.159 W=0.0000 vol=1502 @0.5=0.462 -> DIRECTLY_SUPPORTED_WITH_BOUNDARY_UNCERTAINTY
  DEC-THAL-DIRECT-04 Tha_L_8_4 (rTtha, l) C=0.538 O=0.093 W=0.0000 vol=2066 @0.5=0.538 -> DIRECTLY_SUPPORTED_WITH_BOUNDARY_UNCERTAINTY
  DEC-THAL-DIRECT-05 Tha_L_8_5 (PPtha, l) C=0.684 O=0.079 W=0.0000 vol=2072 @0.5=0.694 -> DIRECTLY_SUPPORTED
  DEC-THAL-DIRECT-06 Tha_L_8_6 (Otha, l) C=0.717 O=0.055 W=0.0000 vol=2174 @0.5=0.722 -> DIRECTLY_SUPPORTED
  DEC-THAL-DIRECT-07 Tha_L_8_7 (cTtha, l) C=0.596 O=0.110 W=0.0000 vol=1839 @0.5=0.594 -> DIRECTLY_SUPPORTED_WITH_BOUNDARY_UNCERTAINTY
  DEC-THAL-DIRECT-08 Tha_L_8_8 (lPFtha, l) C=0.525 O=0.115 W=0.0000 vol=2113 @0.5=0.522 -> DIRECTLY_SUPPORTED_WITH_BOUNDARY_UNCERTAINTY
  DEC-THAL-DIRECT-09 Tha_R_8_1 (mPFtha, r) C=0.810 O=0.033 W=0.0003 vol=1803 @0.5=0.817 -> DIRECTLY_SUPPORTED
  DEC-THAL-DIRECT-10 Tha_R_8_2 (mPMtha, r) C=0.519 O=0.071 W=0.0002 vol=1805 @0.5=0.512 -> DIRECTLY_SUPPORTED_WITH_BOUNDARY_UNCERTAINTY
  DEC-THAL-DIRECT-11 Tha_R_8_3 (Stha, r) C=0.575 O=0.048 W=0.0003 vol=1314 @0.5=0.568 -> DIRECTLY_SUPPORTED_WITH_BOUNDARY_UNCERTAINTY
  DEC-THAL-DIRECT-12 Tha_R_8_4 (rTtha, r) C=0.304 O=0.175 W=0.0948 vol=1666 @0.5=0.293 -> DIRECTLY_SUPPORTED_WITH_BOUNDARY_UNCERTAINTY
  DEC-THAL-DIRECT-13 Tha_R_8_5 (PPtha, r) C=0.815 O=0.016 W=0.0000 vol=2003 @0.5=0.827 -> DIRECTLY_SUPPORTED
  DEC-THAL-DIRECT-14 Tha_R_8_6 (Otha, r) C=0.728 O=0.036 W=0.0007 vol=1644 @0.5=0.734 -> DIRECTLY_SUPPORTED
  DEC-THAL-DIRECT-15 Tha_R_8_7 (cTtha, r) C=0.469 O=0.138 W=0.0024 vol=1669 @0.5=0.463 -> DIRECTLY_SUPPORTED_WITH_BOUNDARY_UNCERTAINTY
  DEC-THAL-DIRECT-16 Tha_R_8_8 (lPFtha, r) C=0.783 O=0.024 W=0.0023 vol=1767 @0.5=0.791 -> DIRECTLY_SUPPORTED

INTERPRETATION: All 16 corresponding Brainnetome thalamic parcels show non-zero/substantial spatial overlap with the whole-thalamus THALAMUS_PROPER G1 geometry. weighted_containment spans 0.12-0.82 (7/16 >= 0.60 directly supported). The overlap is NOT uniformly high: parcels whose probability mass sits on the G1 boundary/margin (low G1 probability rim) show lower containment and are graded with boundary uncertainty. DEC-THAL-DIRECT-02 (Tha_L_8_2, mPMtha L) is the single material discrepancy: its mass is largely lateral to the current G1 envelope (outside-envelope fraction 0.47, containment 0.12) and strongly asymmetric with its right counterpart (R containment 0.52) -> DIRECT_SPATIAL_CONFLICT / mapping requires review. DEC-THAL-DIRECT-12 (Tha_R_8_4, rTtha R) shows a midline-band leak (<=2mm across, asset-level correct-side fraction 0.780) and is graded with boundary uncertainty plus a midline-leak review note.

LIMITATION explicitly preserved: TEMPLATE_VARIANT_ANATOMICAL_MISMATCH_NOT_EXPLICITLY_WARP_CORRECTED. This is DIRECT_SPATIAL_OVERLAP_IN_SHARED_MNI2009C_COORDINATE_FRAME evidence only - a SHARED_MNI2009C coordinate frame resample, not proof of exact local anatomical correspondence.

Reticular exclusion QC: PASSED (max per-parcel overlap with the excluded reticular territory ~3.2%); Reticular is NOT re-added to G1.
Bilateral QA: 8 zone pairs evaluated; asymmetry-review pairs: Tha_8_2, Tha_8_4, Tha_8_8.
6 L-Sg-dependent relations (PPtha/Otha/cTtha L/R): DEC-THAL-04 frozen INCLUDE -> dependency removed; all six now carry direct evidence verdicts.

REFERENCE LEVELS (this round descriptive mapping, not frozen gate thresholds, not the old 90/5 proxy): see summary.json `reference_levels`.

Grading and classification are independent of the current desired VERIFIED status; classification-independent = TRUE. phase17_v3_classification.csv untouched (86/132/93 unchanged).
No DB write. Promotion = BLOCKED. No lifecycle/classification change. No commit.

BN_G3_TO_G1_DIRECT_SPATIAL_VALIDATION = PARTIALLY_PASSED
postconstruction gate = OPEN_NOT_CLOSED (material DIRECT_SPATIAL_CONFLICT present)
THALAMUS_PHASE17_FINAL_FREEZE_V1 formed = False (deferred: DIRECT_SPATIAL_CONFLICT present (DEC-THAL-DIRECT-02 / Tha_L_8_2); postconstruction gate open)

