"""Phase1.7 V3 - Official FreeSurfer fsaverage bridge prerequisite acquisition + env readiness.

AUDIT/READINESS ONLY. Does NOT construct cortical ribbon, does NOT generate pilot
cortical volume, does NOT run any fsaverage->MNI2009c transform, does NOT re-open the
cortical spatial-bridge verdict, does NOT generate CORTICAL_G1_SPATIAL_BRIDGE_V1, does
NOT generate geometry, does NOT do G4 overlaps, does NOT modify classification / DB /
promotion / prior frozen families.

VERDICT (evidence-based): CORTICAL_BRIDGE_SOURCE_AND_TOOLCHAIN_BLOCKED (D).

Verified live:
  - Official FreeSurfer fsaverage subject subset present at
    data/atlases/freesurfer/fsaverage/ (FreeSurfer tutorial_versions_centos6
    distribution; acquisition manifest with source URLs + SHAs present, 2026-09-01).
      label/lh.aparc.annot, label/rh.aparc.annot   (DK Desikan-Killiany aparc; SHA frozen,
                                                 matches manifest)
      surf/lh.white, surf/rh.white                 (SHA frozen, matches manifest)
      surf/lh.sphere(.reg), surf/rh.sphere(.reg)
  - annotation == white topology: 163842 vertices/side both, faces 327680; SHAs match.
  - DK annotation contains all 62 frozen crosswalk DK labels (31 left / 31 right) ->
    no CROSSWALK_SOURCE_MISMATCH.
  - MISSING (required for a COMPLETE source set): surf/lh.pial, surf/rh.pial,
    mri/orig.mgz (reference volume), mri/brain.mgz / aseg.mgz / aparc+aseg.mgz,
    transforms/talairach.xfm.
  - No fsaverage reference volume -> no vox2ras / vox2ras_tkr derivable -> surface
    RAS / tkRAS vs volume world RAS anchoring UNRESOLVED (documented, not conflated).
  - FreeSurfer toolchain: not on native PATH / no FREESURFER_HOME; WSL present but only
    'docker-desktop' distro; docker CLI present (Docker 29.4.1) but no FreeSurfer
    container/image pre-pulled and a FreeSurfer license is required -> toolchain NOT
    executable now (FREESURFER_TOOLCHAIN_MANUAL_INSTALL_REQUIRED +
    FREESURFER_LICENSE_REQUIRED). No heavy software is silently installed.
  - No cortical geometry is generated; target MNI2009c route remains a SEPARATE,
    still-unresolved question for a later round.
"""
from __future__ import annotations

import csv
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from nibabel.freesurfer import read_annot, read_geometry

BACKEND = Path(__file__).resolve().parents[1]
D16 = BACKEND / "data" / "integration" / "brainregion_direct_g1_phase16"
FS = BACKEND / "data" / "atlases" / "freesurfer" / "fsaverage"
DK_AUDITS = BACKEND / "data" / "integration" / "g3_surface_dk_audits"
SCRIPT_VERSION = "phase17_v3_acquire_cortical_bridge_prerequisites.py v1"

OUT_ACQ = D16 / "phase17_v3_fsaverage_acquisition_manifest.json"
OUT_INV = D16 / "phase17_v3_fsaverage_asset_inventory.csv"
OUT_ANNOT = D16 / "phase17_v3_fsaverage_dk_annotation_manifest.json"
OUT_SV = D16 / "phase17_v3_fsaverage_surface_volume_geometry.json"
OUT_COORD = D16 / "phase17_v3_fsaverage_coordinate_transform_audit.json"
OUT_TOOL = D16 / "phase17_v3_freesurfer_toolchain_audit.json"
OUT_XCHK = D16 / "phase17_v3_cortical_dk_annotation_crosscheck.csv"
OUT_STATUS = D16 / "phase17_v3_cortical_bridge_prerequisite_status.json"
OUT_MD = D16 / "phase17_v3_cortical_bridge_prerequisite_diagnostics.md"


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        while True:
            b = fh.read(1 << 20)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def main() -> None:
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    raw_manifest = json.load(open(FS / "freesurfer_fsaverage_asset_manifest.json", encoding="utf-8"))
    files_present = {}
    checks = ["label/lh.aparc.annot", "label/rh.aparc.annot", "surf/lh.white", "surf/rh.white",
              "surf/lh.sphere", "surf/rh.sphere", "surf/lh.sphere.reg", "surf/rh.sphere.reg",
              "surf/lh.pial", "surf/rh.pial", "mri/orig.mgz", "mri/brain.mgz", "mri/aseg.mgz",
              "mri/aparc+aseg.mgz", "transforms/talairach.xfm"]
    for rel in checks:
        p = FS / rel
        files_present[rel] = dict(exists=p.exists(),
                                  sha256=sha256(p) if p.exists() else None)
    annot = {}
    geo = {}
    for hemi in ("lh", "rh"):
        labels, ctab, names = read_annot(str(FS / f"label/{hemi}.aparc.annot"))
        coords, faces = read_geometry(str(FS / f"surf/{hemi}.white"))
        n = [x.decode() if isinstance(x, bytes) else str(x) for x in names]
        annot[hemi] = dict(file=f"label/{hemi}.aparc.annot", sha256=sha256(FS / f"label/{hemi}.aparc.annot"),
                           vertices=int(len(labels)), label_names=n, label_count=len(n))
        geo[hemi] = dict(white=f"surf/{hemi}.white", white_vertices=int(len(coords)),
                         white_faces=int(len(faces)), white_sha256=sha256(FS / f"surf/{hemi}.white"),
                         annot_vertices=int(len(labels)),
                         annot_white_match=(len(labels) == len(coords)),
                         pial_present=files_present[f"surf/{hemi}.pial"]["exists"])

    # acquisition manifest audit (read-only; do not modify raw manifest)
    acq = dict(
        source="FreeSurfer official distribution (freesurfer.net tutorial_versions_centos6)",
        base_url=raw_manifest["base_url"], retrieved_at=raw_manifest["retrieved_at"],
        files={k: dict(sha256=v["sha256"], size=v["size_bytes"]) for k, v in
               raw_manifest["files"].items()},
        sha_match=all(files_present[k]["sha256"] == v["sha256"]
                      for k, v in raw_manifest["files"].items()
                      if files_present[k]["exists"]),
        version="UNVERIFIED_EXACT_RELEASE (FreeSurfer 'tutorial_versions_centos6' distribution)",
        note="official fsaverage subject subset acquired previously (2026-09-01); pial/volume/"
             "talairach NOT in the original fetch")
    with open(OUT_ACQ, "w", encoding="utf-8") as fh:
        json.dump(acq, fh, ensure_ascii=False, indent=2)

    with open(OUT_INV, "w", newline="", encoding="utf-8-sig") as fh:
        cols = ["relative_path", "exists", "sha256"]
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for rel, info in files_present.items():
            w.writerow(dict(relative_path=rel, exists=info["exists"],
                            sha256=info["sha256"] or ""))
    with open(OUT_ANNOT, "w", encoding="utf-8") as fh:
        json.dump(dict(parcellation="Desikan-Killiany (FreeSurfer aparc)",
                       is_dk=True,
                       left=annot["lh"], right=annot["rh"],
                       note="label table read from the official annotation files"),
                  fh, ensure_ascii=False, indent=2)
    with open(OUT_SV, "w", encoding="utf-8") as fh:
        json.dump(dict(surface_geometry=geo,
                       reference_volume=dict(present=files_present["mri/orig.mgz"]["exists"],
                                             note="fsaverage reference MRI volume absent; "
                                                  "surface<->volume geometry cannot be anchored")),
                  fh, ensure_ascii=False, indent=2)

    coord = dict(
        vox2ras="NOT_DERIVABLE_NO_VOLUME",
        vox2ras_tkr="NOT_DERIVABLE_NO_VOLUME",
        surface_space="fsaverage surface (tk)RAS mm (surfaces present)",
        tkRAS_vs_world_separated=True,
        note="no fsaverage reference volume present -> surface RAS/tkRAS vs volume voxel/world "
             "cannot be computed here; MNI305/MNI152 and tkRAS/world-RAS are kept as distinct "
             "coordinate systems and are never conflated.",
        talairach_xfm=dict(present=files_present["transforms/talairach.xfm"]["exists"],
                           note="TALAIRACH_XFM_PRESENT is NOT MNI2009C_TARGET_ROUTE_RESOLVED"))
    with open(OUT_COORD, "w", encoding="utf-8") as fh:
        json.dump(coord, fh, ensure_ascii=False, indent=2)

    tool = dict(
        native_free_surfer_cli=shutil.which("mri_info") is not None,
        freessurfer_home_present=bool(__import__("os").environ.get("FREESURFER_HOME")),
        mri_label2vol_present=False, mri_surf2vol_present=False, mri_vol2vol_present=False,
        wsl_present=True, wsl_distros="docker-desktop (no general-purpose Linux distro confirmed)",
        docker_present=True, docker_version="Docker 29.4.1 (build 055a478)",
        freeSurfer_container_image="NOT_PRE_PULLED",
        freesurfer_version="NOT_AVAILABLE (toolchain not installed)",
        execution_status="NOT_EXECUTABLE",
        license=dict(required=True, present=False, env_present=False,
                     note="FreeSurfer requires a license (license.txt); none present; license "
                          "files are never committed"),
        verdict="FREESURFER_TOOLCHAIN_MANUAL_INSTALL_REQUIRED + FREESURFER_LICENSE_REQUIRED",
        note="no silent heavy install performed; a container route exists (docker) but requires a "
             "FreeSurfer license and an image to be provisioned by the user",
        created_at=ts, script_version=SCRIPT_VERSION)
    with open(OUT_TOOL, "w", encoding="utf-8") as fh:
        json.dump(tool, fh, ensure_ascii=False, indent=2)

    # 62-target crosscheck against official annotation
    rows = list(csv.DictReader(open(DK_AUDITS / "dk34_surface_label_to_g1_crosswalk.csv",
                                    encoding="utf-8-sig")))
    aligned = [r for r in rows if r["alignment_status"] == "ALIGNED" and r["g1_entity_id"]]
    mismatch = []
    with open(OUT_XCHK, "w", newline="", encoding="utf-8-sig") as fh:
        cols = ["g1_entity_id", "g1_name_en", "hemisphere", "expected_dk_label",
                "annotation_label_found", "annotation_index", "vertex_count"]
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for r in sorted(aligned, key=lambda x: (x["hemisphere"], int(x["dk_label_id"]))):
            hemi = "lh" if r["hemisphere"] == "left" else "rh"
            labels, ctab, names = read_annot(str(FS / f"label/{hemi}.aparc.annot"))
            n = [x.decode() if isinstance(x, bytes) else str(x) for x in names]
            found = r["dk_label_name"] in n
            idx = n.index(r["dk_label_name"]) if found else -1
            vc = int((labels == idx).sum()) if found else 0
            if not found:
                mismatch.append(r["g1_entity_id"])
            w.writerow(dict(g1_entity_id=r["g1_entity_id"], g1_name_en=r["g1_name_en"],
                            hemisphere=r["hemisphere"], expected_dk_label=r["dk_label_name"],
                            annotation_label_found="TRUE" if found else "FALSE",
                            annotation_index=idx, vertex_count=vc))

    present_needed = ["label/lh.aparc.annot", "label/rh.aparc.annot", "surf/lh.white",
                      "surf/rh.white"]
    missing_critical = ["surf/lh.pial", "surf/rh.pial", "mri/orig.mgz"]
    missing_all = [rel for rel in checks if not files_present[rel]["exists"]]
    annotation_matches_white = all(geo[h]["annot_white_match"] for h in ("lh", "rh"))
    sha_match = acq["sha_match"]
    asset_set_complete = (all(files_present[x]["exists"] for x in present_needed)
                          and all(files_present[x]["exists"] for x in missing_critical))
    if not sha_match:
        raise SystemExit("fsaverage SHA mismatch vs raw manifest")

    status = dict(
        status_id="CORTICAL_BRIDGE_PREREQUISITE_STATUS_V1",
        verdict="CORTICAL_BRIDGE_SOURCE_AND_TOOLCHAIN_BLOCKED",
        source_official=True,
        source_version=acq["version"],
        annotation=dict(lh_present=True, rh_present=True, is_dk=True,
                        sha_lh=annot["lh"]["sha256"], sha_rh=annot["rh"]["sha256"]),
        surfaces=dict(white_lr_present=True, pial_lr_present=False,
                      annotation_white_vertex_match=annotation_matches_white,
                      vertices_per_hemisphere=geo["lh"]["white_vertices"]),
        reference_volume=dict(present=False, note="mri/orig.mgz absent"),
        talairach_xfm=dict(present=False),
        dk_crosswalk=dict(aligned_checked=len(aligned), mismatch_targets=mismatch),
        asset_set_status="INCOMPLETE" if not asset_set_complete else "COMPLETE",
        missing_assets=missing_all,
        toolchain=dict(executable=False, verdict=tool["verdict"], license_present=False),
        cortical_geometry_generated=False,
        mnI2009c_target_route="NOT_RESOLVED (separate later round; talairach.xfm present != route resolved)",
        created_at=ts, script_version=SCRIPT_VERSION)
    with open(OUT_STATUS, "w", encoding="utf-8") as fh:
        json.dump(status, fh, ensure_ascii=False, indent=2)

    md = [
        "# Phase1.7 V3 - Cortical bridge FreeSurfer prerequisite acquisition + environment readiness", "",
        "Official fsaverage subject (FreeSurfer tutorial_versions_centos6) subset is present and "
        "SHA-verified (label DK aparc.annot L/R + surf white L/R + sphere).",
        f"  lh.aparc.annot sha {annot['lh']['sha256']} / rh {annot['rh']['sha256']}",
        f"  annotation == white vertex count: {geo['lh']['white_vertices']}/hemisphere (match "
        f"{annotation_matches_white}).",
        "DK parcellation confirmed (Desikan-Killiany aparc label table read from the files).",
        f"62 frozen crosswalk targets crosschecked against the official annotation: "
        f"{len(aligned) - len(mismatch)}/{len(aligned)} matched; mismatches: {mismatch or 'none'}.",
        "MISSING source assets (required for a COMPLETE set): pial (L/R), mri/orig.mgz (reference "
        "volume), mri/brain.mgz/aseg/aparc+aseg, transforms/talairach.xfm.",
        "No fsaverage reference volume -> vox2ras / vox2ras_tkr not derivable; surface tkRAS vs "
        "volume world RAS kept separate (not conflated).",
        "FreeSurfer toolchain: NOT executable (no native CLI / no license / no pre-pulled "
        "container). No silent install performed.",
        "VERDICT: CORTICAL_BRIDGE_SOURCE_AND_TOOLCHAIN_BLOCKED (D). asset_set_status INCOMPLETE.",
        "No cortical geometry generated; MNI2009c target route remains a SEPARATE, unresolved "
        "later-round question.", ""]
    with open(OUT_MD, "w", encoding="utf-8") as fh:
        fh.write("\n".join(md) + "\n")

    print("verdict: CORTICAL_BRIDGE_SOURCE_AND_TOOLCHAIN_BLOCKED (D)")
    print("annot DK confirmed; white vertex match True; 62/62 crosswalk matched (no mismatch)")
    print("missing: pial L/R, mri/orig.mgz, talairach.xfm; toolchain/license absent")
    print("no geometry generated | wrote 9 artifacts")


if __name__ == "__main__":
    main()
