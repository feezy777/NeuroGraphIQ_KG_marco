# Phase1.7 V3 - Tha_L_8_2 / mPMtha-L direct spatial discrepancy: root-cause audit

Primary case: Tha_L_8_2 (mPMtha L, DEC-THAL-DIRECT-02). Paired control: Tha_R_8_2 (mPMtha R).
Frozen G3 relation: NGIQ-BR-00000233 / Tha_L_8_2 -> NGIQ-BR-00000247 (APPROVE_CONTAINED_IN).

TERMINOLOGY CLARIFICATION (this audit supersedes; historical outputs untouched):
  - The prior direct-validation record labelled DEC-THAL-DIRECT-02 evidence as
    DIRECT_SPATIAL_CONFLICT / FROZEN_MAPPING_REQUIRES_REVIEW.
  - That described a MATERIAL DIRECT SPATIAL DISCREPANCY (metric gap), NOT a confirmed mapping conflict.
  - direct_conflict_count = 0; requires_review_count before supersession = 1.
  - Superseding mapping verdict for DEC-THAL-DIRECT-02 = KEEP_FROZEN_MAPPING_WITH_SPATIAL_UNCERTAINTY.

Root cause (primary)  : G1_PROBABILITY_ENVELOPE_BOUNDARY_LIMITATION
Root cause (secondary): ['SHARED_TEMPLATE_VARIANT_BOUNDARY_MISMATCH']
TRUE_MAPPING_INCOMPATIBILITY_SUPPORTED = False (no independent evidence).

Stage evidence:
  A raw-BNA: L/R mPMtha volume ratio 0.7787; raw mirror-centroid distance 4.60 mm (max of the 4 zone pairs; control max 3.07) -> intrinsic BNA laterality asymmetry already present in the source atlas.
  B route   : identical SimpleITK NLin6->2009c route for all 16 (PASS); L8_2 target cc=1; route does not create the discrepancy (conserved; mirror distance 5.68 mm).
  C G1-overlap: L containment 0.123 vs R 0.519 -> the gap is the G1-envelope intersection.
  FS categorization (L8_2): in-G1 support 0.532; in-FS-thalami incl reticular 0.680; reticular>0.5 0.012; outside FS thalami 0.320.
  Discrepant region (L8_2 & P_G1<0.1): 5191 voxels, 82.7% of parcel mass, centroid (-18.7,-14.0,4.0) mm -> LATERAL+ANTERIOR of the G1 envelope.
  Reticular strong overlap inside discrepant region: 0.0031 (no substantial Reticular involvement; ZI/subthalamus not present as a repo reference).

Independent anatomical support (AAL3):
  L8_2 in-G1 mass: 0.790159 Thalamus_L; L8_2 discrepant mass: 0.266808 Thalamus_L, 0.666173 label-0.
  -> the portion of L8_2 that overlaps G1 is solidly within the anatomical thalami; the discrepant fringe is partly still AAL-Thalamus (FS envelope conservative) and partly BNA probability-spread beyond the coarse anatomical thalami.

Gate wording (post-supersession): direct_conflict_count=0; requires_review_count=0 (L8_2 -> spatial uncertainty); postconstruction gate = CLOSABLE_NO_MAPPING_CONFLICT.
Final freeze: ENABLED_RECOMMEND_FORM_IN_FREEZE_GATE (not auto-written by this read-only audit).

Guards: no transform retuning; no threshold tuning; no scope modification; no G1 modification; no DB write; classification untouched (86/132/93); Promotion = BLOCKED; no commit.

