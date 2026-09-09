# Phase1.7 V3 - FreeSurfer fsaverage source-space cortical ribbon method validation

VERDICT: CORTICAL_FSAVERAGE_RIBBON_METHOD_BLOCKED_LICENSE (stop_code FREESURFER_LICENSE_MANUAL_ACTION_REQUIRED)
A license is required by every official FreeSurfer binary and none exists on the host. The official container route (freesurfer/freesurfer, tag 7.4.1, license mount /opt/freesurfer/license.txt) is identified but NOT executable until a license is provided by the user (manual action; never committed).

SEMANTIC CORRECTION (effective-status artifact; history 60d81cd untouched):
  - ribbon_required_asset_subset_status = COMPLETE (lh/rh.aparc.annot, lh/rh.white, lh/rh.pial, mri/orig.mgz all AVAILABLE, SHAs fixed).
  - source_asset_internal_geometry_status = READY (subject-internal tkRAS / vox2ras_tkr self-contained).
  - talairach.xfm absence DOES_NOT_BLOCK source-space ribbon construction; it is a TARGET_ROUTE_RELATED_MISSING_ASSET. target_standard_space_route = STILL_UNRESOLVED.
  - historical full asset_set_status = INCOMPLETE is retained unchanged (different axis).

Source assets (same official tutorial_versions_centos6 fsaverage subject):
  topology: annotation == white == pial = 163842 vertices, 327680 faces/hemisphere (CONSISTENT).
  orig.mgz: [256, 256, 256] @ [1.0, 1.0, 1.0] mm, dtype uint8, vox2ras == vox2ras_tkr (internal tkRAS-aligned template geometry).
  Offline static plausibility (no toolchain): all white+pial vertices map inside the orig FOV (in_FOV_fraction = 1.0 both hemispheres); pial envelopes white; lh parcel x<0 / rh x>0 (source-native hemisphere sign).

Pilot selection (mapping-independent, GEOMETRIC_COVERAGE_DIVERSITY only; no Julich overlap, no G4 confidence, no mapping result viewed):
  F1 LARGE_LATERAL      = left precentral
  F2 MEDIAL             = left posteriorcingulate
  F3 INFERIOR_TEMPORAL  = left fusiform
  3 families <= 3 pilots; selection criterion + surface geometry recorded on disk.

Pilot QC: surface/annotation metrics are real (offline). RIBBON VOLUME metrics (voxel count / volume mm3 / connected components / centroid / bbox / thickness / FOV clipping / single-voxel islands / ribbon-vs-shell) are NOT_RUN_LICENSE_BLOCKED - official toolchain execution is required and no Python rasterizer substitute is permitted.

Guards: talairach/MNI305/MNI2009c/TemplateFlow NOT used; no G4 overlap; no bulk 62 geometry; no derived ribbon NIfTI/MGZ committed; no method_v1 (only on a future FROZEN round); no DB write; no reclassification; no promotion; license never committed. Prior frozen families and the 60d81cd snapshot unchanged.

