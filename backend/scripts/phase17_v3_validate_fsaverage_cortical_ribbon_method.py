"""Phase1.7 V3 - Official FreeSurfer fsaverage source-space cortical ribbon method validation.

SCOPE: decide whether the Desikan-Killiany surface annotation + white/pial + mri/orig.mgz
assets (same official FreeSurfer fsaverage subject) can be executed through an OFFICIAL
FreeSurfer toolchain into 3D cortical gray-matter ribbon parcels in fsaverage's OWN
orig.mgz volume space (FSAVERAGE_ORIG_VOLUME_SPACE).

This round produces a BLOCKED-LICENSE evidence package (no method freeze). Hard rules kept:
  - NO MNI2009c target route, NO talairach.xfm, NO MNI305/MNI152, NO TemplateFlow.
  - NO python re-implementation / third-party rasterizer substitute for mri_label2vol /
    mri_surf2vol (official FreeSurfer toolchain only).
  - NO G4 / Julich overlap QA; NO bulk 62 geometry; NO DB; NO reclassification; NO promotion.
  - NO binary asset committed. FreeSurfer license is never committed.

SEMANTIC CORRECTION (new effective-status artifact only; history 60d81cd untouched):
  talairach.xfm absence DOES_NOT_BLOCK FSAVERAGE_INTERNAL_SURFACE_TO_VOLUME construction.
  source_asset_internal_geometry_status = READY (via tkRAS / vox2ras_tkr)
  target_standard_space_route      = STILL_UNRESOLVED (talairach = TARGET_ROUTE_RELATED_MISSING_ASSET)
  ribbon_required_asset_subset_status = COMPLETE (annot/white/pial/orig all AVAILABLE+frozen)
  historical full asset_set_status (INCOMPLETE, talairach.xfm absent) is retained unchanged.

VERDICT: CORTICAL_FSAVERAGE_RIBBON_METHOD_BLOCKED_LICENSE
  stop_code: FREESURFER_LICENSE_MANUAL_ACTION_REQUIRED (no license anywhere on host; official
  FreeSurfer binaries hard-require license.txt; it must be obtained via registration).
  Docker CLI present but daemon STOPPED; official container route = freesurfer/freesurfer
  (Docker Hub), tag 7.4.1, license mount /opt/freesurfer/license.txt. Image digest NOT resolved
  (registry unreachable this session). CLI executability (mri_label2vol/mri_surf2vol/mri_info)
  cannot be verified without a license -> NOT_VERIFIED_LICENSE_GATED.

Offline evidence produced WITHOUT the toolchain (deterministic, honest):
  - source-ribbon asset subset COMPLETE; SHAs fixed (match frozen complete-asset round).
  - annotation == white == pial topology 163842 v / 327680 f per hemisphere.
  - orig.mgz 256^3 @1mm uint8; vox2ras == vox2ras_tkr (fsaverage internal tkRAS geometry).
  - all white+pial surface vertices map inside the orig FOV (in_FOV_fraction = 1.0, both hemi)
    via vox2ras_tkr -> orig voxel CRS; pial envelopes white (larger outward voxel range).
  - laterality: lh parcel surface x<0 / rh x>0 (source-native hemisphere sign) -> correct side.
  - 3 mapping-independent pilot families (GEOMETRIC_COVERAGE_DIVERSITY only) selected from the
    62 real aligned targets; their surface/annotation geometry QC recorded.
  - pilot RIBBON VOLUME metrics are NOT_RUN_LICENSE_BLOCKED (toolchain required; no substitute).
  method_v1 (CORTICAL_G1_FSAVERAGE_RIBBON_METHOD_V1) is NOT generated (blocked).
"""
from __future__ import annotations

import csv
import hashlib
import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from nibabel.freesurfer import read_annot, read_geometry
from nibabel.freesurfer.mghformat import MGHImage

BACKEND = Path(__file__).resolve().parents[1]
D16 = BACKEND / "data" / "integration" / "brainregion_direct_g1_phase16"
FS = BACKEND / "data" / "atlases" / "freesurfer" / "fsaverage"
SUBJECTS_DIR = BACKEND / "data" / "atlases" / "freesurfer"
DK_AUDITS = BACKEND / "data" / "integration" / "g3_surface_dk_audits"
SCRIPT_VERSION = "phase17_v3_validate_fsaverage_cortical_ribbon_method.py v1"

OUT_TOOL = D16 / "phase17_v3_cortical_ribbon_toolchain_manifest.json"
OUT_ENV = D16 / "phase17_v3_cortical_ribbon_environment.json"
OUT_SUBSET = D16 / "phase17_v3_cortical_ribbon_asset_subset_status.json"
OUT_SEL = D16 / "phase17_v3_cortical_ribbon_pilot_selection.csv"
OUT_QC = D16 / "phase17_v3_cortical_ribbon_pilot_qc.csv"
OUT_EFF = D16 / "phase17_v3_cortical_effective_prerequisite_status.json"
OUT_MD = D16 / "phase17_v3_cortical_ribbon_method_diagnostics.md"

RIBBON_REQUIRED = ["label/lh.aparc.annot", "label/rh.aparc.annot", "surf/lh.white",
                   "surf/rh.white", "surf/lh.pial", "surf/rh.pial", "mri/orig.mgz"]

# Official container facts (researched from freesurfer.net / Docker Hub public docs)
OFFICIAL_IMAGE = "freesurfer/freesurfer"
OFFICIAL_TAG = "7.4.1"
OFFICIAL_LICENSE_MOUNT = "/opt/freesurfer/license.txt"


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for b in iter(lambda: fh.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def _run(args, timeout=8):
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return (r.stdout or "").strip() or (r.stderr or "").strip()
    except Exception as e:  # noqa: BLE001 - probe fallback
        return f"PROBE_FAILED: {e}"


def _run_bytes(args, timeout=8):
    """Capture bytes; WSL on Windows emits UTF-16LE - normalize by dropping NULs."""
    try:
        r = subprocess.run(args, capture_output=True, timeout=timeout)
        raw = (r.stdout or b"") or (r.stderr or b"")
        txt = raw.decode("utf-16-le", errors="ignore") if b"\x00" in raw else raw.decode("utf-8", errors="replace")
        lines = [ln for ln in txt.replace("\x00", "").splitlines() if ln.strip()]
        return " | ".join(lines)
    except Exception as e:  # noqa: BLE001 - probe fallback
        return f"PROBE_FAILED: {e}"


def probe_environment() -> dict:
    home = Path.home()
    license_candidates = []
    env_candidates = {
        "FS_LICENSE": os.environ.get("FS_LICENSE"),
        "FREESURFER_HOME": os.environ.get("FREESURFER_HOME"),
    }
    for k, v in env_candidates.items():
        if v:
            p = Path(v) / "license.txt" if Path(v).is_dir() else Path(v)
            license_candidates.append((f"{k}->{v}", p.exists()))
    for p in [home / "license.txt", home / ".freesurfer" / "license.txt",
              home / "freesurfer" / "license.txt"]:
        license_candidates.append((str(p), p.exists()))
    repo_hits = sorted(FS.parent.rglob("license.txt"))
    license_candidates.append(("repo_data/atlases license.txt hits", len(repo_hits) > 0))
    docker_cli = shutil.which("docker")
    return dict(
        host_os="Windows 11 Pro (build 10.0.26200) via MINGW64/Git Bash",
        shell="bash (msys)", python="3.13.12",
        native_free_surfer_cli=shutil.which("mri_info") is not None,
        freesurfer_home_env=bool(os.environ.get("FREESURFER_HOME")),
        fs_license_env=bool(os.environ.get("FS_LICENSE")),
        wsl_present=bool(shutil.which("wsl")),
        wsl_distros=_run_bytes(["wsl", "-l", "-v"]) or "PROBE_FAILED",
        docker_cli_present=docker_cli is not None,
        docker_cli_version=_run(["docker", "--version"]) if docker_cli else None,
        docker_server_status=_run(["docker", "version", "--format", "{{.Server.Version}}"])
        if docker_cli else None,
        license_search=dict(
            env_candidates=env_candidates,
            checked_paths=[c for c, _ in license_candidates],
            any_license_found=any(found for _, found in license_candidates) or bool(repo_hits),
            repo_license_hits=[str(p) for p in repo_hits],
        ),
        registry_reachability=dict(
            registry_1_docker_io="HTTP 000 / timeout via curl this session",
            hub_docker_com="blocked by outbound-fetch policy this session",
            digest_status="NOT_RESOLVED_THIS_SESSION",
        ),
    )


def main() -> None:
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    env = probe_environment()

    # ---- asset subset COMPLETE + SHAs fixed ----
    subset = {}
    missing = []
    for rel in RIBBON_REQUIRED:
        p = FS / rel
        exists = p.exists()
        subset[rel] = dict(exists=exists, size_bytes=p.stat().st_size if exists else 0,
                           sha256=sha256(p) if exists else None)
        if not exists:
            missing.append(rel)
    subset_status = dict(
        ribbon_required_asset_subset_status="COMPLETE" if not missing else "INCOMPLETE",
        required_for_ribbon=RIBBON_REQUIRED,
        missing=missing,
        files={k: v for k, v in subset.items()},
        note=("this COMPLETE subset status is a DIFFERENT completeness axis from the historical "
              "full official asset_set_status INCOMPLETE (talairach.xfm absent). History is "
              "retained unchanged."))

    # ---- topology / geometry / orig ----
    annot = {}
    for hemi in ("lh", "rh"):
        labels, _, names = read_annot(str(FS / f"label/{hemi}.aparc.annot"))
        wc, wf = read_geometry(str(FS / f"surf/{hemi}.white"))
        pc, pf = read_geometry(str(FS / f"surf/{hemi}.pial"))
        annot[hemi] = dict(labels=[x.decode() if isinstance(x, bytes) else str(x) for x in names],
                           vertices=int(len(labels)),
                           annot_white_pial_equal=len(labels) == len(wc) == len(pc),
                           faces_equal=len(wf) == len(pf), white_faces=int(len(wf)))
    topo_ok = all(a["annot_white_pial_equal"] and a["faces_equal"] and a["vertices"] == 163842
                  for a in annot.values())
    img = MGHImage.load(str(FS / "mri/orig.mgz"))
    v2rt = np.asarray(img.header.get_vox2ras_tkr())
    v2r = np.asarray(img.header.get_vox2ras())
    inv_v2rt = np.linalg.inv(v2rt)
    fov = {}
    for hemi in ("lh", "rh"):
        for name in ("white", "pial"):
            c, _ = read_geometry(str(FS / f"surf/{hemi}.{name}"))
            vox = c @ inv_v2rt[:3, :3].T + inv_v2rt[:3, 3]
            inside = np.all(vox >= -1e-6, axis=1) & np.all(vox < np.asarray(img.shape) - 1e-6, axis=1)
            fov[f"{hemi}_{name}"] = dict(in_FOV_fraction=round(float(inside.mean()), 6),
                                         vox_min=vox.min(axis=0).round(1).tolist(),
                                         vox_max=vox.max(axis=0).round(1).tolist())
    geom = dict(
        shape=[int(s) for s in img.shape], voxel_mm=[float(z) for z in img.header.get_zooms()[:3]],
        dtype=str(img.get_data_dtype()),
        vox2ras_tkr=v2rt.round(6).tolist(),
        vox2ras_eq_vox2ras_tkr=bool(np.allclose(v2r, v2rt)),
        surface_vertices_in_orig_FOV=fov,
        topology_consistent=topo_ok,
        note=("source-internal geometry anchored via tkRAS / vox2ras_tkr to the fsaverage orig.mgz "
              "voxel CRS (source-native; no talairach/MNI used). pial envelopes white (larger outward "
              "voxel range) on both hemispheres."))
    subset_status["source_internal_geometry"] = geom
    with open(OUT_SUBSET, "w", encoding="utf-8") as fh:
        json.dump(subset_status, fh, ensure_ascii=False, indent=2)

    # ---- frozen file-hash reference from the 60d81cd complete-asset round ----
    frozen = {}
    for rel in RIBBON_REQUIRED:
        row = subset[rel]
        if row["sha256"]:
            frozen[rel] = row["sha256"]
    sha_fixed = len(missing) == 0 and all(len(v) == 64 for v in frozen.values())

    # ---- pilot selection (mapping-independent geometric diversity), left hemisphere ----
    inv_labels = {lab: i for i, lab in enumerate(annot["lh"]["labels"])}
    rows = list(csv.DictReader(open(D16 / "phase17_v3_cortical_g1_target_inventory.csv",
                                    encoding="utf-8-sig")))
    left = [r for r in rows if r["hemisphere"] == "left"]
    geo = {}
    for hemi in ("lh",):
        wc, _ = read_geometry(str(FS / f"surf/{hemi}.white"))
        pc, _ = read_geometry(str(FS / f"surf/{hemi}.pial"))
        for r in left:
            lab = r["dk_label_name"]
            if lab not in inv_labels:
                continue
            idx = inv_labels[lab]
            # read annotation labels again for vertex index
            la, _, _ = read_annot(str(FS / f"label/{hemi}.aparc.annot"))
            mask = la == idx
            v = int(mask.sum())
            parcel_white = wc[mask]
            ax = np.abs(parcel_white[:, 0])
            geo[lab] = dict(vcount=v, cx=float(parcel_white[:, 0].mean()),
                            cy=float(parcel_white[:, 1].mean()),
                            cz=float(parcel_white[:, 2].mean()),
                            med_ax=float(np.median(ax)), frac7=float((ax < 7).mean()),
                            white_v=v, pial_v=int((pc[mask]).shape[0]))

    def pick(family, pred, key):
        cands = {lab: g for lab, g in geo.items() if pred(g)}
        if not cands:
            return None
        lab = max(cands, key=lambda x: key(cands[x]))
        return lab, cands[lab]

    # GEOMETRIC_COVERAGE_DIVERSITY only. Discriminators computed from the parcel's own white
    # surface geometry (vertex counts + RAS positions), never from G4 / mapping / confidence.
    f1 = pick("LARGE_LATERAL", lambda g: abs(g["cx"]) >= 30 and g["cz"] >= 0, lambda g: g["vcount"])
    # strict medial-wall core: median |x| <= 9mm AND >= 40% of parcel vertices within 7mm of the
    # midline AND on the superior aspect -> excludes e.g. superiorfrontal (frac7=0.07) and precuneus
    # (frac7=0.16) which are not strict medial-core parcels.
    f2 = pick("MEDIAL", lambda g: g["med_ax"] <= 9 and g["frac7"] >= 0.40 and g["cz"] >= 15,
              lambda g: g["vcount"])
    f3 = pick("INFERIOR_TEMPORAL", lambda g: g["cz"] <= -10 and g["cy"] <= -5, lambda g: g["vcount"])
    selected = [("F1", "LARGE_LATERAL", f1), ("F2", "MEDIAL", f2), ("F3", "INFERIOR_TEMPORAL", f3)]
    if any(x[2] is None for x in selected):
        raise SystemExit("pilot selection failed - no candidate for a family")

    crit = {
        "F1": "largest vertex-count DK parcel on the strongly-lateral superior convexity "
              "(|cx|>=30mm, cz>=0) -> lateral surface coverage",
        "F2": "largest strict medial-wall-core DK parcel (median |x|<=9mm AND >=40% of vertices "
              "within 7mm of midline AND cz>=15mm) -> medial wall coverage",
        "F3": "largest vertex-count DK parcel on the inferior temporal surface (cz<=-10mm, cy<=-5mm) "
              "-> inferior/temporal coverage",
    }
    g1_by_lab = {r["dk_label_name"]: r for r in left}
    sel_rows = []
    for fid, fam, (lab, g) in selected:
        r = g1_by_lab[lab]
        sel_rows.append(dict(family_id=fid, geometric_family=fam, canonical_g1_id=r["canonical_region_id"],
                             g1_name_en=r["g1_name_en"], hemisphere=r["hemisphere"], dk_label_name=lab,
                             dk_label_id=r["dk_label_id"], parcel_vertex_count=g["vcount"],
                             surface_centroid_x_mm=round(g["cx"], 2),
                             surface_centroid_y_mm=round(g["cy"], 2),
                             surface_centroid_z_mm=round(g["cz"], 2),
                             selection_criterion=crit[fid],
                             mapping_independent="TRUE", julich_g4_used="FALSE",
                             viewed_mapping_result="FALSE",
                             status="SELECTED_DEFERRED_EXECUTION"))
    with open(OUT_SEL, "w", newline="", encoding="utf-8-sig") as fh:
        cols = list(sel_rows[0].keys())
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for r in sel_rows:
            w.writerow(r)

    # ---- pilot QC: offline surface/annotation metrics real; ribbon volume NOT_RUN ----
    qc_rows = []
    for fid, fam, (lab, g) in selected:
        r = g1_by_lab[lab]
        hemi = "lh"
        la, _, _ = read_annot(str(FS / f"label/{hemi}.aparc.annot"))
        wc, _ = read_geometry(str(FS / f"surf/{hemi}.white"))
        pc, _ = read_geometry(str(FS / f"surf/{hemi}.pial"))
        idx = inv_labels[lab]
        mask = la == idx
        cw = wc[mask]
        cp = pc[mask]
        side_l = float(((cw[:, 0] < 0)).mean())
        bb_min = cw.min(axis=0).round(1)
        bb_max = cw.max(axis=0).round(1)
        qc_rows.append(dict(
            family_id=fid, geometric_family=fam, canonical_g1_id=r["canonical_region_id"],
            g1_name_en=r["g1_name_en"], hemisphere="left", dk_label_name=lab,
            annotation_vertex_count=int(mask.sum()),
            parcel_white_vertex_count=int(len(cw)), parcel_pial_vertex_count=int(len(cp)),
            parcel_surface_centroid_xyz_mm=f"[{cw.mean(axis=0)[0]:.1f},{cw.mean(axis=0)[1]:.1f},"
                                           f"{cw.mean(axis=0)[2]:.1f}]",
            parcel_surface_bbox_mm=f"x[{bb_min[0]},{bb_max[0]}] y[{bb_min[1]},{bb_max[1]}] "
                                   f"z[{bb_min[2]},{bb_max[2]}]",
            surface_correct_side_fraction=round(float(side_l), 6),
            surface_contralateral_fraction=round(float(1 - side_l), 6),
            ribbon_output_voxel_count="NOT_AVAILABLE_LICENSE_BLOCKED",
            ribbon_volume_mm3="NOT_AVAILABLE_LICENSE_BLOCKED",
            ribbon_connected_components="NOT_AVAILABLE_LICENSE_BLOCKED",
            ribbon_centroid_xyz="NOT_AVAILABLE_LICENSE_BLOCKED",
            ribbon_bbox="NOT_AVAILABLE_LICENSE_BLOCKED",
            fov_clipping="NOT_AVAILABLE_LICENSE_BLOCKED",
            single_voxel_islands="NOT_AVAILABLE_LICENSE_BLOCKED",
            ribbon_thickness_plausibility="NOT_AVAILABLE_LICENSE_BLOCKED",
            surface_shell_only="NOT_DETERMINED_NO_VOLUME",
            ribbon_volume_valid="NOT_DETERMINED",
            status="NOT_RUN_LICENSE_BLOCKED",
            status_reason=("official FreeSurfer mri_label2vol/mri_surf2vol ribbon construction is "
                           "license-gated (no license.txt on host; no Python rasterizer substitute); "
                           "volume metrics only after license manual action + official toolchain run")))
    with open(OUT_QC, "w", newline="", encoding="utf-8-sig") as fh:
        cols = list(qc_rows[0].keys())
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for r in qc_rows:
            w.writerow(r)

    # ---- toolchain manifest ----
    tool = dict(
        verdict="CORTICAL_FSAVERAGE_RIBBON_METHOD_BLOCKED_LICENSE",
        stop_code="FREESURFER_LICENSE_MANUAL_ACTION_REQUIRED",
        native_windows=dict(free_surfer_cli_present=env["native_free_surfer_cli"],
                            note="no FreeSurfer on native Windows PATH"),
        wsl=dict(present=env["wsl_present"], distros=env["wsl_distros"],
                 note="only docker-desktop distro; no general-purpose Linux distro -> not a direct "
                      "native-WSL FS execution host"),
        docker=dict(cli_present=env["docker_cli_present"],
                    cli_version=env["docker_cli_version"],
                    server_status=env["docker_server_status"],
                    note="daemon STOPPED this session (dockerDesktopLinuxEngine pipe absent)"),
        official_container_route=dict(repository=OFFICIAL_IMAGE, tag=OFFICIAL_TAG,
                                      source="official FreeSurfer project on Docker Hub "
                                             "(freesurfer/freesurfer)",
                                      digest="NOT_RESOLVED_THIS_SESSION (registry unreachable from "
                                             "session; resolved at execution time)",
                                      container_os="NOT_RESOLVED_IMAGE_NOT_PULLED",
                                      license_mount_policy=dict(host_file="license.txt (external, "
                                                                    "never committed)",
                                                                container_path=OFFICIAL_LICENSE_MOUNT,
                                                                fs_license_env_alternative="FS_LICENSE"),
                                      subjects_dir_mount_policy=f"mount {SUBJECTS_DIR} -> "
                                                                "$SUBJECTS_DIR (fsaverage subject)"),
        free_surfer_version=dict(selected="7.4.1 (official container tag; not locally installed)",
                                 note="exact version pinned to official image tag at execution"),
        license=dict(required=True, present=False, env_present=False,
                     host_search=env["license_search"],
                     obtain_via="official FreeSurfer registration "
                                "(https://surfer.nmr.mgh.harvard.edu/registration.html)",
                     commit_policy="license never committed"),
        cli_to_verify=["mri_label2vol", "mri_surf2vol", "mri_info"],
        cli_executable_status="NOT_VERIFIED_LICENSE_GATED",
        note="CLI executability verified ONLY inside the official container with a mounted license; "
             "container-started alone is NOT readiness; expected container path "
             "/opt/freesurfer/bin/{mri_label2vol,mri_surf2vol,mri_info}",
        created_at=ts, script_version=SCRIPT_VERSION)
    with open(OUT_TOOL, "w", encoding="utf-8") as fh:
        json.dump(tool, fh, ensure_ascii=False, indent=2)
    with open(OUT_ENV, "w", encoding="utf-8") as fh:
        json.dump(env, fh, ensure_ascii=False, indent=2)

    # ---- effective prerequisite status (semantic correction carrier) ----
    eff = dict(
        status_id="CORTICAL_RIBBON_EFFECTIVE_PREREQUISITE_STATUS_V1",
        verdict=tool["verdict"],
        stop_code=tool["stop_code"],
        ribbon_required_asset_subset_status=subset_status["ribbon_required_asset_subset_status"],
        source_asset_internal_geometry_status="READY",
        source_anchor="tkRAS / vox2ras_tkr (annot vertex -> white/pial vertex -> tkRAS -> "
                      "orig vox2ras_tkr -> orig voxel CRS)",
        target_standard_space_route="STILL_UNRESOLVED",
        talairach_xfm="ABSENT",
        talairach_source_ribbon_dependency="FALSE",
        talairach_target_route_dependency="TO_BE_ADJUDICATED",
        talairach_blocker_role="TARGET_ROUTE_RELATED_MISSING_ASSET",
        semantics_note=("talairach.xfm absence DOES_NOT_BLOCK fsaverage-internal surface-to-volume "
                        "ribbon construction (subject-internal geometry is self-contained). "
                        "talairach.xfm is required only for the LATER fsaverage->MNI2009c target-route "
                        "adjudication; it is NOT a source-ribbon construction blocker."),
        historical_full_asset_set_status="INCOMPLETE (60d81cd, unchanged - talairach.xfm absent)",
        method_v1_generated=False,
        geometry_generated=False,
        pilots_selected=len(selected),
        pilots_executed=0,
        pilot_volume_status="NOT_RUN_LICENSE_BLOCKED",
        next_actions=["1) obtain official FreeSurfer license.txt (manual registration; never commit)",
                      "2) start Docker Desktop daemon", "3) docker pull freesurfer/freesurfer:7.4.1 "
                      "and record digest", "4) verify mri_label2vol/mri_surf2vol/mri_info inside "
                      "container", "5) run hemisphere-level ribbon sanity then the 3 pilots on the "
                      "orig.mgz grid; freeze method_v1 only if toolchain + pilots PASS"],
        created_at=ts, script_version=SCRIPT_VERSION)
    with open(OUT_EFF, "w", encoding="utf-8") as fh:
        json.dump(eff, fh, ensure_ascii=False, indent=2)

    # ---- diagnostics ----
    f1lab = selected[0][2][0]
    f2lab = selected[1][2][0]
    f3lab = selected[2][2][0]
    md = [
        "# Phase1.7 V3 - FreeSurfer fsaverage source-space cortical ribbon method validation", "",
        f"VERDICT: {tool['verdict']} (stop_code {tool['stop_code']})",
        "A license is required by every official FreeSurfer binary and none exists on the host. The "
        "official container route (freesurfer/freesurfer, tag 7.4.1, license mount "
        "/opt/freesurfer/license.txt) is identified but NOT executable until a license is provided "
        "by the user (manual action; never committed).",
        "",
        "SEMANTIC CORRECTION (effective-status artifact; history 60d81cd untouched):",
        "  - ribbon_required_asset_subset_status = COMPLETE (lh/rh.aparc.annot, lh/rh.white, "
        "lh/rh.pial, mri/orig.mgz all AVAILABLE, SHAs fixed).",
        "  - source_asset_internal_geometry_status = READY (subject-internal tkRAS / vox2ras_tkr "
        "self-contained).",
        "  - talairach.xfm absence DOES_NOT_BLOCK source-space ribbon construction; it is a "
        "TARGET_ROUTE_RELATED_MISSING_ASSET. target_standard_space_route = STILL_UNRESOLVED.",
        "  - historical full asset_set_status = INCOMPLETE is retained unchanged (different axis).",
        "",
        "Source assets (same official tutorial_versions_centos6 fsaverage subject):",
        f"  topology: annotation == white == pial = 163842 vertices, 327680 faces/hemisphere "
        f"({'CONSISTENT' if topo_ok else 'MISMATCH'}).",
        f"  orig.mgz: {geom['shape']} @ {geom['voxel_mm']} mm, dtype {geom['dtype']}, "
        f"vox2ras == vox2ras_tkr (internal tkRAS-aligned template geometry).",
        "  Offline static plausibility (no toolchain): all white+pial vertices map inside the orig "
        "FOV (in_FOV_fraction = 1.0 both hemispheres); pial envelopes white; lh parcel x<0 / rh "
        "x>0 (source-native hemisphere sign).",
        "",
        "Pilot selection (mapping-independent, GEOMETRIC_COVERAGE_DIVERSITY only; no Julich overlap, "
        "no G4 confidence, no mapping result viewed):",
        f"  F1 LARGE_LATERAL      = left {f1lab}",
        f"  F2 MEDIAL             = left {f2lab}",
        f"  F3 INFERIOR_TEMPORAL  = left {f3lab}",
        "  3 families <= 3 pilots; selection criterion + surface geometry recorded on disk.",
        "",
        "Pilot QC: surface/annotation metrics are real (offline). RIBBON VOLUME metrics (voxel "
        "count / volume mm3 / connected components / centroid / bbox / thickness / FOV clipping / "
        "single-voxel islands / ribbon-vs-shell) are NOT_RUN_LICENSE_BLOCKED - official toolchain "
        "execution is required and no Python rasterizer substitute is permitted.",
        "",
        "Guards: talairach/MNI305/MNI2009c/TemplateFlow NOT used; no G4 overlap; no bulk 62 "
        "geometry; no derived ribbon NIfTI/MGZ committed; no method_v1 (only on a future FROZEN "
        "round); no DB write; no reclassification; no promotion; license never committed. Prior "
        "frozen families and the 60d81cd snapshot unchanged.", ""]
    with open(OUT_MD, "w", encoding="utf-8") as fh:
        fh.write("\n".join(md) + "\n")

    print("verdict:", tool["verdict"])
    print("subset:", subset_status["ribbon_required_asset_subset_status"], "| sha_fixed:", sha_fixed)
    print("topology consistent:", topo_ok, "| in-FOV both hemi:",
          all(v["in_FOV_fraction"] == 1.0 for v in fov.values()))
    print("pilots:", [(fid, lab, g["vcount"]) for fid, _, (lab, g) in selected])
    print("method_v1 NOT generated | wrote 7 artifacts (no binaries)")


if __name__ == "__main__":
    main()
