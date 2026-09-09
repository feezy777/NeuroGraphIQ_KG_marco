# Phase1.7 V3 - Official fsaverage aparc+aseg volumetric DK authority + pilot validation
VERDICT: CORTICAL_G1_APARC_ASEG_VOLUME_METHOD_FROZEN
asset mri/aparc+aseg.mgz (same official base as frozen assets; orig refetch SHA == frozen) sha 4c7db4478ccc171f... size 341811
LUT FreeSurferColorLUT.txt (same official distribution root) sha b040ad6c0c4e26dd...
grid compatible with orig: True (shape [256, 256, 256] == orig [256, 256, 256]; vox2ras/vox2ras_tkr equal)
atlas: DESIKAN_KILLIANY (Desikan-Killiany confirmed)
master FreeSurferColorLUT.txt is the shared color LUT (Destrieux/DKT names coexist); DK identity determined by full canonical DK set on both hemispheres + asset naming aparc+aseg (FreeSurfer Desikan volume)
cortical ctx labels in LUT: lh 134 / rh 134; 62/62 frozen G1 targets found and voxel_count>0: 62/62; mismatches none
only ctx-lh-*/ctx-rh-* used; subcortical aseg ids excluded; exact integer extraction only; no morphology / no rasterization / no FreeSurfer CLI / no Docker / no license.
pilot QC (3 frozen left pilots) -> see pilot_qc.csv (all ribbon_volume_valid + laterality >0.99 + source annotation consistent required for PASS).
target transform TRF-CORT-FSAVG-TO-MNI2009C-DIRECT-V1 NOT applied this round; source-space compatibility TRUE (same orig volume geometry).
Guards: no G4/Julich, no mapping tuning, no 170 validation, no batch 62, no DB, no reclassification, no promotion; 3f74c23 Docker blocker retained as legacy non-blocking history.

