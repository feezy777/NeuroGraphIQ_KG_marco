# Phase1.7 V3 - batch construction of 62 cortical G1 canonical reference geometries

VERDICT: CORTICAL_G1_62_REFERENCE_GEOMETRIES_FROZEN
targets: 62 (left 31 / right 31); source = official aparc+aseg 4c7db4478ccc171f... (grid == fsaverage orig 256^3).
source selected labelmap CORTICAL_G1_SELECTED_LABELMAP_FSAVG_V1 sha c97f9bb5f999daea... union 320337 voxels, unique labels 62, unexpected [].
transform: single multiclass NearestNeighbor application (count=1) with TRF-CORT-FSAVG-TO-MNI2009C-DIRECT-V1 (aff ff95a9fc7b84..., fwd 8bf90f3efdf7...).
target selected labelmap CORTICAL_G1_SELECTED_LABELMAP_MNI2009C_V1 sha 07235e25bace8ffb... on MNI152NLin2009cAsym grid [193, 229, 193] @ [1.0, 1.0, 1.0] mm; unique labels 62, unexpected [], nonempty 62/62.
volumes: total source 320337 -> target 409083 (ratio 1.277); per-region ratio min/median/max {'min': 1.0431, 'median': 1.2754, 'max': 1.5201}; outliers [].
fragmentation review: []; laterality abnormal: []; centroid-application residual max 10.0545 mm.
centroid residual note: residuals (<=~10 mm) reflect genuine parcel centroid shift under the nonlinear deformation + NN discretization; they are bounded by the warp scale (max 11.6 mm) and are NOT a transform order/direction/convention bug (authoritative physical-point roundtrip P95 = 0.014 mm; laterality preserved). Reported as diagnostic only.
target grid == frozen Julich reference grid (193x229x193 @1mm). label IDs preserved identity (1024->1024 etc); pairwise overlap impossible by single labelmap.
Guards: no G4/Julich parcel use, no mapping tuning, no morphology, no re-registration, no transform change, no FreeSurfer CLI/Docker/license, no DB, no reclassification, no promotion. 62 target binary SHAs recorded (manifest); binaries gitignored.
direct_overlap_grid_ready = True; direct_validation_executed = False.

