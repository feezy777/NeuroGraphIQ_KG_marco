# Phase1.7 V3 - Thalamus BN rollup basis <-> THALAMUS_PROPER compatibility

final_verdict = BN_ROLLUP_BASIS_PARTIALLY_COMPATIBLE  (direct spatial validation NOT yet done)
incompatible = 0
preconstruction_gate = PASSED
preconstruction_rollup_compatibility = PASS_WITH_POSTCONSTRUCTION_VALIDATION_REQUIRED
blocker #2 (V2: BN_ROLLUP_BASIS_NOT_RECONCILED) -> NO_LONGER_PRECONSTRUCTION_BLOCKER (migrated out of pre-construction gate; V2 historical snapshot untouched)
construction_blocker_status = RECLASSIFIED_OUT_OF_CONSTRUCTION_GATE
postconstruction_requirement = DIRECT_BN_G3_TO_G1_SPATIAL_VALIDATION_REQUIRED
promotion_gate = BLOCKED_UNTIL_DIRECT_VALIDATION
active_construction_blockers = ['DEC-THAL-04 (L-Sg / Limitans-Suprageniculate boundary)']
geometry_construction = BLOCKED_BY_LSG_ONLY
promotion = BLOCKED
relation_verdict_distribution = {'KEEP_FROZEN_MAPPING_PENDING_DIRECT_SPATIAL_VALIDATION': 10, 'KEEP_FROZEN_MAPPING_PENDING_BOUNDARY_AND_DIRECT_VALIDATION': 6}
  - 6 L-Sg-dependent:   KEEP_FROZEN_MAPPING_PENDING_BOUNDARY_AND_DIRECT_VALIDATION
  - 10 non-L-Sg:        KEEP_FROZEN_MAPPING_PENDING_DIRECT_SPATIAL_VALIDATION
universe = 16 relations (8L+8R) from real frozen manifest
stats = {'LIKELY_COMPATIBLE_NEEDS_SPATIAL_CONFIRMATION': 16}  (all LIKELY_COMPATIBLE_NEEDS_SPATIAL_CONFIRMATION; NOT upgraded to COMPATIBLE)
bilateral_asymmetry = NONE (all L/R symmetric)
evidence_mode = SEMANTIC_ANATOMICAL_COMPATIBILITY (+gross BNA-246 spatial)
NOT direct G1 geometry validation (no independent THALAMUS_PROPER geometry yet)
pre-construction gate PASSED does NOT mean the 16 frozen mappings are finally validated; promotion stays blocked until post-construction direct validation.
no frozen mapping modified; no geometry/transform/overlap/DB; no retro-edit of V1/V2; no reclassification; no commit

