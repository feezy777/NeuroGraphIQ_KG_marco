# Phase1.7 V3 - Cortical G1 surface-to-volume spatial bridge authority + method audit

Cortical universe (computed live from frozen G3->G1 manifest x DK34 surface->G1 crosswalk):
  cortical G3->G1 relations = 170 (left 85 / right 85)
  aligned DK-label->G1 rows = 62 (left 31 / right 31) -> distinct G1 targets = 62
  target inventory + DK crosswalk written to the CSVs.

VERDICT: CORTICAL_SURFACE_TO_VOLUME_BRIDGE_BLOCKED
  Reason: no fsaverage Desikan-Killiany aparc.annot, no fsaverage reference volume (source template identity unresolved), no talairach/MNI305->2009cAsym transform, and no FreeSurfer surface->volume toolchain available in this environment.
  The historical BN<->DK fsaverage route is surface-to-surface only and is NOT reused as a volume bridge.
  No pilot geometry was produced (assets/toolchain missing); pilot deferred.
  No CORTICAL_G1_SPATIAL_BRIDGE_V1 is generated (bridge is not frozen).

Coordinate hard rules recorded: no direct surface XYZ -> MNI2009cAsym; MNI305/MNI152 are never conflated; tkRAS/world-RAS kept separate.
Guards: no bulk geometry, no relation validation, no reclassification, no DB, no promotion; Basal Forebrain blocker and prior frozen families (Thalamus/Amygdala/Hippocampus/BNST) unchanged.

