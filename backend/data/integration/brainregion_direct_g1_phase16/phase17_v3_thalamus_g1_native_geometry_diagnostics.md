# Phase1.7 V3 - THALAMUS_PROPER G1 native-space reference geometry

source = ThalamusProbs.MNIsymSpace.nii.gz  (ICBM152 2009c symmetric, 138x106x94 @0.5mm, 53 ch)
source_sha256 = 640377ae93cf0782365a698573970c2a429a775c6f64dcf9ac02536156b51f22
names_sha256 = 74b70bfa4fa75aa05a0bee9fcb548fa97bea20bfceef43b63a97c52a3923bfec
scope_contract = THALAMUS_G1_SCOPE_CONTRACT_V3  sha 22e24a31bab9659769f7e550ee32f8e3b37887d0ae1a4c4c4cf64974c3c05f68
left  included=25 excluded=1  (Reticular R excluded)
right included=25 excluded=1  (Reticular R excluded)
aggregation = SUM of included probability channels (MUTUALLY_EXCLUSIVE_CATEGORICAL)
no MAX / union / threshold / binarization / clipping / normalization
left  weighted_volume_mm3 = 9080.703  support=134809
right weighted_volume_mm3 = 9080.703  support=134809
left  centroid_mm = [-11.24019372013143, -18.908388772486518, 6.038820542398757]
right centroid_mm = [11.740193720131431, -18.908388772486525, 6.038820542398761]
reticular exclusion (all26 == G1 + R): left max|res|=0.000e+00 right max|res|=0.000e+00
atlas conservation bg+52nuclei: min=1.0000 mean=1.0000 p99=1.0000 max=1.0000
output grid == source grid (138x106x94); output affine == source affine (no registration/resampling)
independent_from_g3_g1_mapping = TRUE; circularity_risk = NONE
direct_g4_overlap_ready = FALSE; transform_required = SYMMETRIC_TO_ASYMMETRIC_TEMPLATE_TRANSFORM_REQUIRED
left output_sha256  = 2c9d3d2d7823a02749c77a7084339d503fcb251b5db53b7791e2f008b43f2ba8
right output_sha256 = e9e93d593ddc073431d3e8d2da3e1d16e89e05ec213f9e24d6659caa9c926ae2
derived NIfTI are local only (NOT committed, per derived_g1 policy)
no DB write; no commit; no Sym->Asym transform; classification/DB untouched

