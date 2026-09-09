# Phase1.7 V3 - Official FreeSurfer fsaverage complete subject asset acquisition + provenance

Release: tutorial_versions_centos6 (official freesurfer.net tutorial mirror); release_identity PARTIALLY_RESOLVED. Same official distribution asset set.
This round added surf/lh.pial, surf/rh.pial, mri/orig.mgz from the same official base.
annotation == white == pial vertices: 163842/side, faces 327680 -> topology CONSISTENT.
62-target DK crosscheck: 62/62 PASS (mismatches: none).
orig.mgz: shape [256, 256, 256] @ [1.0, 1.0, 1.0] mm, dtype uint8; vox2ras == vox2ras_tkr (fsaverage internal tkRAS-aligned; NOT an MNI152 mapping).
transforms/talairach.xfm: ABSENT (404 on official tutorial mirror); not used; talairach != MNI2009c route.
VERDICT: CORTICAL_FSAVERAGE_COMPLETE_SOURCE_ASSET_BLOCKED. asset_set_status INCOMPLETE; required missing: ['transforms/talairach.xfm'].
toolchain still BLOCKED (unchanged). target MNI2009c route NOT_ADJUDICATED. No cortical geometry generated.

