# Phase1.7 V3 - fsaverage/MNI305 -> MNI152NLin2009cAsym target spatial route authority

VERDICT: CORTICAL_TARGET_ROUTE_PROJECT_DERIVED_ALLOWED_PENDING_EXECUTION (D)
No official precomputed direct (A) or multi-hop (B) MNI305/fsaverage -> 2009cAsym transform exists (TemplateFlow authoritative enumeration this round: tpl-2009c has only from-NLin6Asym/from-OASISTRT20; tpl-MNI305 and tpl-NLin6 have no MNI305/fsaverage-source transforms; FreeSurfer distribution is license-gated/unverifiable).
Shared-frame resample (C) REJECTED: Talairach/MNI305 != MNI152NLin2009cAsym; grids differ.
Scientifically allowed candidate (D): whole-brain anatomical registration of fsaverage mri/orig.mgz (moving) -> MNI152NLin2009cAsym brain template (fixed), estimated without any DK/Julich/G4 label content, then applied to future binary ribbon volumes with NearestNeighbor. Deferred to an independent registration-execution round (not run now).

fsaverage MNI305 semantic audit (documentation-level statements are NOT proof of grid/world identity):
  local orig.mgz: shape [256, 256, 256] @ [1.0, 1.0, 1.0] mm dtype uint8 orientation LIA, sha 97862f8adfa48ff0...
  TemplateFlow tpl-MNI305: shape [172, 220, 156] @ [1.0, 1.0, 1.0] mm dtype int16 orientation RAS, sha ad5bbda698844359..., local cache.
  fsaverage is documented (FreeSurfer wiki) as already registered to Talairach/MNI305; 'Talairach MNI' == MNI305; true Talairach differs (Brett). talairach.xfm = per-subject orig->MNI305 affine; NOT required to assert fsaverage template identity.
  identity test (orig resampled onto tpl-MNI305 grid): NCC 0.5928, MI 0.596 bits, brain COM displacement 5.53 mm.
  => relation_classification: ONLY_DOCUMENTED_AS_MNI305_DERIVED (not exact grid identity).

Guardrails: no Docker/license/ribbon run, no transform applied, no MNI2009c geometry, no G4 overlap, no mapping-based tuning, no project-derived registration executed, no bulk 62, no DB, no reclassification, no promotion. route_v1 NOT generated (pending execution). Source-ribbon license blocker and prior frozen states unchanged.

