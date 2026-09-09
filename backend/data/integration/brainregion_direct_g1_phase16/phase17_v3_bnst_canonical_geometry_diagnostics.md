# Phase1.7 V3 - BNST canonical geometry construction (whole-BNST, probability)

Primary authority: Julich-Brain v3.1 whole-BST L/R (DOI 10.25493/KNSN-XB4); reference-space MNI152NLin2009cAsym; source-native Left/Right.

Source files (already on the frozen canonical target grid -> NO resampling, no derived copy):
  Left  : BST_BASAL_FOREBRAIN_BED_NUCLEUS_LEFT.nii.gz  sha b72a2396a977ebfbb3668a5fb5981ec43c676e7c497d688a788e0539f8537102
  Right : BST_BASAL_FOREBRAIN_BED_NUCLEUS_RIGHT.nii.gz  sha 8bacb4eab6c77d7bd3e3b1e02ab77f7654fe8e98c232cb2b238b53a4b3ef9d55

Left  QC: support 991 vox / 991.0 mm3; prob mass 141.6895; max P 0.892927; centroid (-6.36, 1.23, -2.82); CC 1.
Right QC: support 791 vox / 791.0 mm3; prob mass 138.3197; max P 0.911041; centroid (5.9, 2.33, -2.36); CC 1.

Representation: continuous probabilistic/statistical values preserved (NOT thresholded, NOT binarized). BINARY_GEOMETRY_POLICY = UNRESOLVED; BINARY_CANONICAL_MASK = NOT_CONSTRUCTED (no frozen probability->binary rule exists for this source class).
CANONICAL_PROBABILITY_GEOMETRY = CONSTRUCTED / REGISTERED (content-addressed to the acquired Julich v3.1 source; no NIfTI copy produced).
Left/Right independent & correctly lateralized (source-native labels; left centroid x<0, right x>0); normalized overlap mass fraction and cross-side leakage are negligible.

Guards: no BNST->Basal Forebrain relation; no Phase1.7 classification change (86/132/93); no DB write; no NGIQ-BR allocation (PROP-BNST-L/R-V1 only); admission ADMIT_AS_CANONICAL_BRAINREGION unchanged; G1 roll-up G1_ROLLUP_UNRESOLVED unchanged; Thalamus/Amygdala/Hippocampus frozen outputs untouched; Theiss/Blackford corroborating only; Brandstetter 2026 not substituted.

