# Phase1.7 V3 External Raw G1 asset acquisition audit

Julich reference: tpl-MNI152NLin2009cAsym res01 (193x229x193, 1mm, origin -96/-132/-78)
assets=9
acquisition per asset: {"FS_SUBFIELD_HIPPO": "RAW_ASSET_VERIFIED", "FS_AMYG_NUCLEI": "RAW_ASSET_VERIFIED", "FS_THAL_ICBM": "RAW_ASSET_VERIFIED", "CIT168_NAcc": "RAW_ASSET_VERIFIED", "BF_ZABORSZKY_CH1234": "PENDING_EXTERNAL", "BST_BLACKFORD_WHOLE": "RAW_ASSET_VERIFIED", "BST_SIBBACH_DV": "PENDING_EXTERNAL", "BST_CYTO_10BRAIN": "PENDING_EXTERNAL", "FS_ASEG_SUBJECT": "SUBJECT_SPECIFIC_ONLY"}
RAW_ASSET_VERIFIED=5 RAW_ASSET_ACQUIRED=0 pending/metadata=4 FAILED=0
original_archives(sha256): {"freesurfer_icbm2009c/hippocampus/_original/HippoAmyg.zip": {"sha256": "3bedb212780716a9ff5547eb28f5f3018270982f085c892303eb547cb4a85811", "file_size": 25088328}, "freesurfer_icbm2009c/thalamus/_original/Thalamus.zip": {"sha256": "d00485eb94ffebe642e11aaf19130b5d95f6773c93631b38e8e9c44e341006fb", "file_size": 5487795}, "_ref/mni_icbm152_nlin_sym_09c_nifti.zip": {"sha256": "ed981b4611ddd797a22f539035979723ecb1badebd06dcd85df149b5ef00890d", "file_size": 57583823}}
EXACT grid match vs Julich: CIT168 2009cAsym det+prob (193x229x193,1mm,origin -96/-132/-78).
FreeSurfer subfield atlases are on ICBM152 2009c SYMMETRIC template (0.25/0.5mm):
  SYMMETRIC_VS_ASYMMETRIC_TEMPLATE relative to Julich 2009cAsym - resampling+transform required.
Blackford whole-BNST is on the FSL MNI152 6th-gen 1mm grid (182x218x182):
  NOT 2009c - nonlinear template transform to NLin2009cAsym required.
BF/BST separation preserved (BST never merged into Zaborszky Ch atlas).
aseg stays SUBJECT_SPECIFIC_ONLY (never group gold standard).
immutable_mismatches=NONE

## raw file registry (sha256 of every present file)
- bnst/blackford/Blackford_BNST_3T.nii.gz sha256=d7bfa26c7426994ce22e572dbe469484b8c43236a58ebe297238a2cb1cacbc67 size=253342 shape=[182, 218, 182] zooms=[1.0, 1.0, 1.0] range=[0.0, 1.0] nonzero=354
- cit168/CIT168toMNI152-2009c_det.nii.gz sha256=0072d6ea3c05d1e798743e7d1f732fbc9c50ee6969bc5e68c6bdba3472d26242 size=51026 shape=[193, 229, 193] zooms=[1.0, 1.0, 1.0] range=[0.0, 16.0] nonzero=40677
- cit168/CIT168toMNI152-2009c_prob.nii.gz sha256=7a91c36701f36d9d908479b862e65a879d15f54badcec6878e61d857ab570f66 size=857744 shape=[193, 229, 193, 16] zooms=[1.0, 1.0, 1.0, 1.0] range=[0.0, 1.0] nonzero=82002
- cit168/CIT168toMNI152-NLin6Asym_det.nii.gz sha256=8b43e911c6849c9a57c9153499a324d2e3894531bb31446b6905b4c357693ae0 size=44739 shape=[182, 218, 182] zooms=[1.0, 1.0, 1.0] range=[0.0, 16.0] nonzero=37766
- freesurfer_icbm2009c/hippocampus/HippoAmygProbs.MNIsymSpace.left.nii.gz sha256=a79d5f88acfa21684a6f8c1e78da21e74ccbf152e68fb845fde048f451c4474e size=13506619 shape=[164, 224, 196, 30] zooms=[0.25, 0.25, 0.25, 0.0] range=[-0.0, 1.0] nonzero=9541085
- freesurfer_icbm2009c/hippocampus/HippoAmygProbs.MNIsymSpace.right.nii.gz sha256=4d20bb95435afc9a139279ae2a159d8dfbf3f1b1de0d07d901ff6cf08570e5a3 size=13506796 shape=[164, 224, 196, 30] zooms=[0.25, 0.25, 0.25, 0.0] range=[-0.0, 1.0] nonzero=9541085
- freesurfer_icbm2009c/thalamus/ThalamusProbs.MNIsymSpace.nii.gz sha256=640377ae93cf0782365a698573970c2a429a775c6f64dcf9ac02536156b51f22 size=5890664 shape=[138, 106, 94, 53] zooms=[0.5, 0.5, 0.5, 0.0] range=[-0.0, 1.0] nonzero=2527804

