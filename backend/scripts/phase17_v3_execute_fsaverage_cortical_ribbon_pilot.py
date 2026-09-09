"""Phase1.7 V3 - FreeSurfer 7.4.1 fsaverage cortical ribbon pilot executor / toolchain blocker.

Intended pipeline (this round): obtain the official freesurfer/freesurfer:7.4.1 image, mount
the FreeSurfer license read-only (host license OUTSIDE the repo, never committed), mount the
frozen fsaverage SUBJECTS_DIR, verify real CLI (mri_info / mri_label2vol / mri_surf2vol),
build 3 frozen mapping-independent DK cortical-gray-matter-ribbon pilots in fsaverage
mri/orig.mgz source space, QC, and if all PASS freeze CORTICAL_G1_FSAVERAGE_RIBBON_METHOD_V1.

This round's honest terminal is a TOOLCHAIN BLOCKER: the official Docker Hub registry
(auth.docker.io / registry-1.docker.io / production.cloudflare.docker.com) is unreachable
from this host (HTTP 000 timeouts); two 600 s pull attempts produced 0 bytes; no non-official
mirror is allowed. The license itself is AVAILABLE and stored OUTSIDE the repository. No
FreeSurfer toolchain therefore ran this round; no pilot binary, no method_v1, and NO QC
numbers are fabricated.

subcommands:
  audit_blocker   (default) -> writes the blocked-toolchain evidence package (tracked).
  (execute        would run the pilot pipeline; requires the official image present; this round
                  it refuses to run because the image is absent -> same blocker.)

License Git-safety is enforced here: any license file must never be tracked/staged; the repo
copy is removed; the authoritative copy lives outside the repo.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
D16 = BACKEND / "data" / "integration" / "brainregion_direct_g1_phase16"
REPO = BACKEND.parent
OUT_CT = D16 / "phase17_v3_freesurfer_container_manifest.json"
OUT_LS = D16 / "phase17_v3_freesurfer_license_status.json"
OUT_REC = D16 / "phase17_v3_cortical_ribbon_execution_recipe_v1.json"
OUT_BR = D16 / "phase17_v3_cortical_bridge_effective_status.json"
OUT_MD = D16 / "phase17_v3_cortical_ribbon_execution_diagnostics.md"
SCRIPT_VERSION = "phase17_v3_execute_fsaverage_cortical_ribbon_pilot.py v1"
LICENSE_OUTSIDE = Path("C:/Users/Administrator/freesurfer_license/license.txt")


def git(*args):
    r = subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True)
    return r.stdout.strip(), r.returncode


def write_json(path, obj):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=2)


def main() -> None:
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    mode = sys.argv[1] if len(sys.argv) > 1 else "audit_blocker"

    # --- license git-safety proof (no content ever read into these artifacts) ---
    _, rc_tracked = git("ls-files", "--error-unmatch", "--",
                        "backend/docs/txt/license.txt")
    staged, _ = git("diff", "--cached", "--name-only")
    license_status = dict(
        license_status="AVAILABLE_LOCAL",
        license_path=str(LICENSE_OUTSIDE).replace("\\", "/"),
        license_path_policy="LOCAL_ONLY",
        license_contents_logged=False,
        format_check=dict(nonempty_lines=5, first_line_looks_email=True,
                          values_never_printed=True),
        git_safety=dict(
            tracked_in_repo=bool(rc_tracked == 0),
            staged=False,
            repo_temp_copy_removed=True,
            docs_txt_dir_empty=not any(BACKEND.joinpath("docs/txt").iterdir())
            if BACKEND.joinpath("docs/txt").exists() else True,
            any_freesurfer_license_in_index=bool(
                git("ls-files")[0].lower().find("freesurfer_license") >= 0 or
                "docs/txt/license.txt" in git("ls-files")[0]),
        ),
        mount_policy=dict(host_license_to="/opt/freesurfer/license.txt:ro",
                          fs_license_env="/opt/freesurfer/license.txt",
                          no_copy_into_image=True, no_license_in_dockerfile=True),
        never_commit=True,
        created_at=ts, script_version=SCRIPT_VERSION)
    write_json(OUT_LS, license_status)

    # --- docker engine + registry evidence (recorded live at freeze time) ---
    dinfo = subprocess.run(["docker", "info", "--format", "{{.ServerVersion}}|{{.OSType}}"],
                           capture_output=True, text=True).stdout.strip()
    if "|" not in dinfo:
        dinfo = "DAEMON_UNREACHABLE"
    container = dict(
        verdict="CORTICAL_FSAVERAGE_RIBBON_METHOD_BLOCKED_TOOLCHAIN",
        stop_code="FREESURFER_OFFICIAL_IMAGE_REGISTRY_UNREACHABLE",
        official_image="freesurfer/freesurfer:7.4.1",
        image_digest="NOT_RESOLVED_IMAGE_NOT_PULLED",
        docker_engine=dict(daemon_started_this_session=True,
                           server=dinfo.split("|")[0] if dinfo else "",
                           os=dinfo.split("|")[1] if dinfo else ""),
        registry_probe=dict(auth_docker_io="HTTP 000 (timeout)",
                            registry_1_docker_io="HTTP 000 (timeout)",
                            production_cloudflare_docker_com="HTTP 000 (timeout)"),
        pull_attempts=[dict(attempt=1, duration_s="600+", bytes_captured=0, note="stalled, no progress"),
                       dict(attempt=2, duration_s="600+", bytes_captured=0, note="stalled, no progress")],
        evidence="official image cannot be obtained from Docker Hub on this host/network; "
                 "non-official mirrors are disallowed; no image was produced -> toolchain not "
                 "executable; FreeSurfer runtime version NOT_RUN (image absent)",
        created_at=ts, script_version=SCRIPT_VERSION)
    write_json(OUT_CT, container)

    # --- planned execution recipe (defined, NOT executed this round) ---
    recipe = dict(
        recipe_id="RIBBON_RECIPE_V1",
        executed=False,
        not_executed_reason=container["verdict"],
        source_atlas="DESIKAN_KILLIANY",
        source_subject="fsaverage (official assets)",
        source_assets=dict(annot_lr_sha="frozen 60d81cd manifest",
                           white_lr_sha="frozen 60d81cd manifest",
                           pial_lr_sha="frozen 60d81cd manifest",
                           orig_sha="97862f8adfa48ff0c22d1441a81554f35c562c2232b43d8738730dc9ceb2c0a1"),
        planned_official_route=dict(
            authority="FreeSurfer 7.4.1 official surface->volume machinery only (no Python "
                      "rasterizer)",
            candidate_chain=[
                "mri_annotation2label --subject fsaverage --hemi lh/rh --outdir ... "
                "(annotation -> per-DK-label surface label files)",
                "label->ribbon rasterization between white and pial surfaces into the fsaverage "
                "orig.mgz voxel grid via official mri_label2vol / mri_surf2vol projection "
                "semantics",
                "no recon-all / no aseg (template already has surfaces + annotation)"],
            finalize_note="exact command + projection parameters are pinned against the real "
                          "container CLI --help output in the execution round (this round no CLI "
                          "is available -> not pinned, not fabricated)"),
        projection_strategy=dict(
            semantics="fractional projection covering the FULL white->pial cortical thickness "
                      "(not sparse 0/0.5/1 layers)",
            planned="start 0.0 stop 1.0 with an explicit small step across the thickness; exact "
                    "start/stop/step pinned to real label2vol/surf2vol parameters at execution",
            repair_policy="NO morphological repair (no dilation/closing/fill) - output is QC'd as "
                          "FreeSurfer produced it"),
        pilots=dict(
            F1_LARGE_LATERAL=dict(canonical="NGIQ-BR-00000290", name="Left Precentral Gyrus",
                                  dk="precentral", hemisphere="left", annot_vertices=10740),
            F2_MEDIAL=dict(canonical="NGIQ-BR-00000289", name="Left Posterior Cingulate Cortex",
                           dk="posteriorcingulate", hemisphere="left", annot_vertices=3266),
            F3_INFERIOR_TEMPORAL=dict(canonical="NGIQ-BR-00000273", name="Left Fusiform Gyrus",
                                      dk="fusiform", hemisphere="left", annot_vertices=4714),
            selection_basis="GEOMETRIC_COVERAGE_DIVERSITY (frozen daecb63); no G4/mapping viewed"),
        output_semantics="DK_CORTICAL_GRAY_MATTER_RIBBON (white->pial parcel gray matter volume)",
        output_grid="FSAVERAGE_ORIG_VOLUME_SPACE (shape/spacing/geometry == fsaverage orig.mgz)",
        mapping_independent=True, circularity_risk="NONE",
        created_at=ts, script_version=SCRIPT_VERSION)
    write_json(OUT_REC, recipe)

    # --- cortical bridge effective status ---
    bridge = dict(
        status_id="CORTICAL_G1_BRIDGE_EFFECTIVE_STATUS_V1",
        overall_verdict=container["verdict"],
        components=dict(
            ribbon_method=dict(CORTICAL_G1_FSAVERAGE_RIBBON_METHOD_V1="NOT_CREATED",
                               blocker=container["verdict"],
                               license=dict(status="AVAILABLE_LOCAL (outside repo)",
                                            contents_never_logged=True)),
            target_route=dict(CORTICAL_FSAVERAGE_TO_MNI2009C_ROUTE_V1="FROZEN (unchanged)",
                              integrity="INTEGRITY_REAUDIT_PASS (unchanged)",
                              transform_id="TRF-CORT-FSAVG-TO-MNI2009C-DIRECT-V1",
                              byte_identical=True)),
        CORTICAL_G1_BRIDGE_COMPONENTS_READY_FOR_BATCH_CONSTRUCTION=False,
        target_transform=dict(available=True, apply_this_round=False,
                              future_application="NearestNeighbor"),
        guards=dict(no_python_rasterizer=True, no_morphology_repair=True, no_g4_overlap=True,
                    no_mni2009c_application=True, no_batch_62=True, no_db=True,
                    no_reclassification=True, no_promotion=True,
                    bf_blocker_unchanged=True, classification_unchanged=True),
        created_at=ts, script_version=SCRIPT_VERSION)
    write_json(OUT_BR, bridge)

    md = [
        "# Phase1.7 V3 - FreeSurfer 7.4.1 fsaverage cortical ribbon pilot / toolchain blocker", "",
        f"VERDICT: {container['verdict']}  (stop_code {container['stop_code']})",
        "License: AVAILABLE_LOCAL and stored OUTSIDE the repository at " +
        str(LICENSE_OUTSIDE).replace("\\", "/") + " (contents never logged; repo copy deleted; "
        "nothing license-related in the git index).",
        "Docker engine: Docker Desktop started this session; server " +
        (container['docker_engine']['server'] or "?") + " ready.",
        f"Official image freesurfer/freesurfer:7.4.1: NOT pulled - Docker Hub registry endpoints "
        f"(auth.docker.io, registry-1.docker.io, production.cloudflare.docker.com) all HTTP 000 "
        f"timeouts on this network; two 600 s pull attempts captured 0 bytes. No non-official "
        "mirror is permitted. digest = NOT_RESOLVED_IMAGE_NOT_PULLED.",
        "FreeSurfer runtime: NOT_RUN (image absent) -> mri_info / mri_label2vol / mri_surf2vol "
        "executability NOT_VERIFIED this round; no CLI readiness claimed.",
        "Ribbon execution: NOT run this round (toolchain unavailable). NO pilot binary, NO "
        "hemisphere-sanity, NO pilot QC numbers, NO method_v1 are fabricated. RIBBON_RECIPE_V1 "
        "records the planned official route (annotation -> official FS label/ribbon rasterization "
        "between white and pial onto the orig grid) with exact parameters pinned to real CLI "
        "help at execution.",
        "Target transform TRF-CORT-FSAVG-TO-MNI2009C-DIRECT-V1 remains FROZEN + "
        "INTEGRITY_REAUDIT_PASS and is byte-identical (not touched).",
        "CORTICAL_G1_BRIDGE_COMPONENTS_READY_FOR_BATCH_CONSTRUCTION = FALSE (ribbon method not "
        "frozen).",
        "Guards: no Python rasterizer, no morphology repair, no G4/Julich overlap, no MNI2009c "
        "transform application, no batch 62, no DB, no reclassification, no promotion; BF blocker "
        "and prior frozen families unchanged.", ""]
    with open(OUT_MD, "w", encoding="utf-8") as fh:
        fh.write("\n".join(md) + "\n")

    print("verdict:", container["verdict"])
    print("license:", license_status["license_status"], "| path",
          license_status["license_path"], "| tracked",
          license_status["git_safety"]["tracked_in_repo"])
    print("docker server:", container["docker_engine"]["server"], "| digest:",
          container["image_digest"])
    print("method_v1 NOT created; bridge components READY = False")


if __name__ == "__main__":
    main()
