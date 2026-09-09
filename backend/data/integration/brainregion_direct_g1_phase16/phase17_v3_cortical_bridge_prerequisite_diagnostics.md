# Phase1.7 V3 - Cortical bridge FreeSurfer prerequisite acquisition + environment readiness

Official fsaverage subject (FreeSurfer tutorial_versions_centos6) subset is present and SHA-verified (label DK aparc.annot L/R + surf white L/R + sphere).
  lh.aparc.annot sha 39b1acde9a32b4227631eb51cbcd8dff84e2138c57bf9f96d74026f2c17f1480 / rh 6a326aed325d313e6e0d10f67630efcd8d3b8343c50d3e108e005f626614badb
  annotation == white vertex count: 163842/hemisphere (match True).
DK parcellation confirmed (Desikan-Killiany aparc label table read from the files).
62 frozen crosswalk targets crosschecked against the official annotation: 62/62 matched; mismatches: none.
MISSING source assets (required for a COMPLETE set): pial (L/R), mri/orig.mgz (reference volume), mri/brain.mgz/aseg/aparc+aseg, transforms/talairach.xfm.
No fsaverage reference volume -> vox2ras / vox2ras_tkr not derivable; surface tkRAS vs volume world RAS kept separate (not conflated).
FreeSurfer toolchain: NOT executable (no native CLI / no license / no pre-pulled container). No silent install performed.
VERDICT: CORTICAL_BRIDGE_SOURCE_AND_TOOLCHAIN_BLOCKED (D). asset_set_status INCOMPLETE.
No cortical geometry generated; MNI2009c target route remains a SEPARATE, unresolved later-round question.

