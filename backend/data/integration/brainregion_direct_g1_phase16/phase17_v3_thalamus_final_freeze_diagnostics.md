# Phase1.7 V3 - Thalamus postconstruction gate closure + final freeze

Freeze ID: THALAMUS_PHASE17_FINAL_FREEZE_V1
Gate ID: THALAMUS_BN_POSTCONSTRUCTION_GATE_V1
Supersession: DEC-THAL-DIRECT-02-S1

Effective 16-relation state (from historical direct decisions + L8_2 supersession):
  KEEP_FROZEN_MAPPING_DIRECTLY_SUPPORTED        = 7
  KEEP_FROZEN_MAPPING_WITH_SPATIAL_UNCERTAINTY  = 9
  FROZEN_MAPPING_REQUIRES_REVIEW                 = 0
  FROZEN_MAPPING_DIRECT_CONFLICT                 = 0
  (insufficient)                                 = 0

Confirmed mapping conflicts = 0; mapping review items = 0; non-blocking spatial uncertainties = 9.
Gate status = CLOSED_NO_MAPPING_CONFLICT; direct validation = PASSED_WITH_RECORDED_SPATIAL_UNCERTAINTY.

NOTES:
  - PASSED does NOT equal PERFECT_GEOMETRIC_CONTAINMENT. Continuous containment varied substantially across parcels (weighted containment 0.12-0.82); recorded spatial uncertainty is retained.
  - DEC-THAL-DIRECT-02 / Tha_L_8_2: historical snapshot still shows REQUIRES_REVIEW; effective verdict via DEC-THAL-DIRECT-02-S1 is KEEP_FROZEN_MAPPING_WITH_SPATIAL_UNCERTAINTY (root cause = G1 probability-envelope boundary limitation + shared-template-variant mismatch; TRUE_MAPPING_INCOMPATIBILITY not supported).
  - Tha_R_8_4 midline leak remains NON_BLOCKING_SPATIAL_UNCERTAINTY.
  - template_variant_uncertainty PRESENT; residual limitation TEMPLATE_VARIANT_ANATOMICAL_MISMATCH_NOT_EXPLICITLY_WARP_CORRECTED preserved; evidence mode DIRECT_SPATIAL_OVERLAP_IN_SHARED_MNI2009C_COORDINATE_FRAME.
  - Current G1 SHAs: L bd431608fcea3c5f0f7387b1b0e1010582fa2e39dae95a300b3bba976a10cc87, R 73e4242b581f2420c316593f6cd85183ea7f99c29e2b817b0257cdf267c5bd3b; superseded SyN geometry 37a82b65d86d... / 1c9b8b8de910 is NOT current.
  - This is a FILE-LEVEL scientific freeze. No DB promotion (brain_regions 770 / active mappings 707 unchanged), no global reclassification (86/132/93 unchanged). Promotion not executed (readiness = READY_FOR_LATER_GLOBAL_PROMOTION_REVIEW).

Provenance chain recorded with artifact SHAs (13 links); see phase17_v3_thalamus_final_freeze_v1.json.

