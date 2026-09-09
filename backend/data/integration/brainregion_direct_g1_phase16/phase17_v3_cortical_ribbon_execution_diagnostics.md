# Phase1.7 V3 - FreeSurfer 7.4.1 fsaverage cortical ribbon pilot / toolchain blocker

VERDICT: CORTICAL_FSAVERAGE_RIBBON_METHOD_BLOCKED_TOOLCHAIN  (stop_code FREESURFER_OFFICIAL_IMAGE_REGISTRY_UNREACHABLE)
License: AVAILABLE_LOCAL and stored OUTSIDE the repository at C:/Users/Administrator/freesurfer_license/license.txt (contents never logged; repo copy deleted; nothing license-related in the git index).
Docker engine: Docker Desktop started this session; server 29.4.1 ready.
Official image freesurfer/freesurfer:7.4.1: NOT pulled - Docker Hub registry endpoints (auth.docker.io, registry-1.docker.io, production.cloudflare.docker.com) all HTTP 000 timeouts on this network; two 600 s pull attempts captured 0 bytes. No non-official mirror is permitted. digest = NOT_RESOLVED_IMAGE_NOT_PULLED.
FreeSurfer runtime: NOT_RUN (image absent) -> mri_info / mri_label2vol / mri_surf2vol executability NOT_VERIFIED this round; no CLI readiness claimed.
Ribbon execution: NOT run this round (toolchain unavailable). NO pilot binary, NO hemisphere-sanity, NO pilot QC numbers, NO method_v1 are fabricated. RIBBON_RECIPE_V1 records the planned official route (annotation -> official FS label/ribbon rasterization between white and pial onto the orig grid) with exact parameters pinned to real CLI help at execution.
Target transform TRF-CORT-FSAVG-TO-MNI2009C-DIRECT-V1 remains FROZEN + INTEGRITY_REAUDIT_PASS and is byte-identical (not touched).
CORTICAL_G1_BRIDGE_COMPONENTS_READY_FOR_BATCH_CONSTRUCTION = FALSE (ribbon method not frozen).
Guards: no Python rasterizer, no morphology repair, no G4/Julich overlap, no MNI2009c transform application, no batch 62, no DB, no reclassification, no promotion; BF blocker and prior frozen families unchanged.

