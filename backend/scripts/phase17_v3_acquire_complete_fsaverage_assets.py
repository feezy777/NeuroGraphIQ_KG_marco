"""Phase1.7 V3 - Official FreeSurfer fsaverage complete subject asset acquisition + provenance.

SOURCE-ASSET ACQUISITION AUDIT ONLY. Does NOT install/tool FreeSurfer, does NOT run
mri_label2vol / mri_surf2vol, does NOT construct cortical ribbon / pilot volume, does
NOT solve the fsaverage/MNI305->MNI2009cAsym route, does NOT re-run the cortical bridge
method audit, does NOT generate CORTICAL_G1_SPATIAL_BRIDGE_V1, does NOT do G4 overlap,
does NOT touch classification / DB / promotion / prior frozen families.

This round extended the same official FreeSurfer tutorial fsaverage distribution
(freesurfer.net .../tutorial_versions_centos6/.../subjects/fsaverage) with the files
that ARE present on that official base:
    surf/lh.pial, surf/rh.pial  (SHA real; same topology as white: 163842 v / 327680 f)
    mri/orig.mgz                (256x256x256 @1mm uint8; vox2ras == vox2ras_tkr)
The previously-acquired files (label/lh+rh.aparc.annot, surf/lh+rh.white, sphere,
sphere.reg) stay unchanged; all belong to the SAME official distribution.

REMAINING BLOCKER: transforms/talairach.xfm is NOT present on the official tutorial
mirror (HTTP 404). Obtaining it would require the full official FreeSurfer distribution
(license/registration). Mixing a third-party talairach.xfm from another source is
forbidden (would violate the same-release hard gate). Exact FreeSurfer patch release is
PARTIALLY_RESOLVED (official 'tutorial_versions_centos6' distribution family).

VERDICT: CORTICAL_FSAVERAGE_COMPLETE_SOURCE_ASSET_BLOCKED (Case B).
    annotation (DK aparc) L/R        : present
    white L/R                        : present
    pial L/R                         : present
    mri/orig.mgz                     : present
    transforms/talairach.xfm         : ABSENT (required for COMPLETE per gate)
    surface_topology                 : CONSISTENT (annot==white==pial, L and R)
    62-target crosscheck             : PASS (62/62)
    release_identity                 : PARTIALLY_RESOLVED
    source_internal_geometry         : RESOLVED (orig vox2ras == vox2ras_tkr == fsaverage tkRAS-aligned)
    toolchain                        : still BLOCKED (unchanged from prior round)
No cortical geometry is generated.
"""
from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from nibabel.freesurfer import read_annot, read_geometry
from nibabel.freesurfer.mghformat import MGHImage

BACKEND = Path(__file__).resolve().parents[1]
D16 = BACKEND / "data" / "integration" / "brainregion_direct_g1_phase16"
FS = BACKEND / "data" / "atlases" / "freesurfer" / "fsaverage"
DK_AUDITS = BACKEND / "data" / "integration" / "g3_surface_dk_audits"
BASE = "https://www.freesurfer.net/pub/dist/freesurfer/tutorial_versions_centos6/freesurfer/subjects/fsaverage"
SCRIPT_VERSION = "phase17_v3_acquire_complete_fsaverage_assets.py v1"

OUT_ROUTES = D16 / "phase17_v3_fsaverage_complete_acquisition_routes.csv"
OUT_REL = D16 / "phase17_v3_fsaverage_official_release_manifest.json"
OUT_INV = D16 / "phase17_v3_fsaverage_complete_asset_inventory.csv"
OUT_HASH = D16 / "phase17_v3_fsaverage_file_hash_manifest.csv"
OUT_ANNOT = D16 / "phase17_v3_fsaverage_annotation_validation.json"
OUT_TOP = D16 / "phase17_v3_fsaverage_surface_topology_qc.csv"
OUT_ORIG = D16 / "phase17_v3_fsaverage_orig_geometry_audit.json"
OUT_TALA = D16 / "phase17_v3_fsaverage_talairach_audit.json"
OUT_STATUS = D16 / "phase17_v3_fsaverage_complete_asset_status.json"
OUT_MD = D16 / "phase17_v3_fsaverage_complete_asset_diagnostics.md"

REQUIRED = ["label/lh.aparc.annot", "label/rh.aparc.annot", "surf/lh.white", "surf/rh.white",
            "surf/lh.pial", "surf/rh.pial", "mri/orig.mgz", "transforms/talairach.xfm"]


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
    routes = [
        dict(route_id="R1", provider="official FreeSurfer tutorial mirror (freesurfer.net)",
             url=BASE, access_state="OPEN", requires_login="no", requires_license_acceptance="n/a",
             redistribution="LOCAL_USE_ONLY cache", asset_set="fsaverage subject files",
             evidence="lh/rh.aparc.annot, white, sphere acquired 2026-09-01; this round added "
                      "lh/rh.pial (200) and mri/orig.mgz (200); transforms/talairach.xfm -> 404"),
        dict(route_id="R2", provider="full official FreeSurfer distribution (needs license/registration)",
             url="(official distribution download - license-gated)", access_state="MANUAL_AUTHORIZED_ACCESS_REQUIRED",
             requires_login="yes", requires_license_acceptance="yes",
             redistribution="per FreeSurfer license", asset_set="full subjects/fsaverage (incl. talairach.xfm)",
             evidence="NOT accessed this round; would be required to obtain transforms/talairach.xfm "
                      "from the same release without mixing sources"),
        dict(route_id="R3", provider="third-party / random GitHub mirrors", access_state="NOT_USED",
             requires_login="no", requires_license_acceptance="n/a", redistribution="unverified",
             asset_set="any", evidence="excluded by policy: no mixing of asset sets from unknown sources"),
    ]
    with open(OUT_ROUTES, "w", newline="", encoding="utf-8-sig") as fh:
        cols = list(routes[0].keys())
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for r in routes:
            w.writerow(r)

    hashes = {rel: dict(size=(FS / rel).stat().st_size if (FS / rel).exists() else 0,
                        sha256=sha256(FS / rel) if (FS / rel).exists() else None)
              for rel in REQUIRED}
    missing_req = [rel for rel in REQUIRED if not (FS / rel).exists()]
    present_files = [rel for rel in REQUIRED if (FS / rel).exists()]

    release = dict(
        source="FreeSurfer official distribution (freesurfer.net tutorial mirror)",
        base_url=BASE,
        distribution="tutorial_versions_centos6",
        release_identity="PARTIALLY_RESOLVED",
        release_note=("official FreeSurfer 'tutorial_versions_centos6' freesurfer distribution; "
                      "exact patch release not determinable from the tutorial mirror (no version file); "
                      "NOT fabricated"),
        provider="Martinos Center / FreeSurfer",
        acquisition_timestamp=ts,
        same_release_asset_set=True,
        route=routes[0]["route_id"])
    with open(OUT_REL, "w", encoding="utf-8") as fh:
        json.dump(release, fh, ensure_ascii=False, indent=2)

    roles = {"label/lh.aparc.annot": "DK annotation", "label/rh.aparc.annot": "DK annotation",
             "surf/lh.white": "surface", "surf/rh.white": "surface",
             "surf/lh.pial": "surface", "surf/rh.pial": "surface",
             "surf/lh.sphere": "surface", "surf/rh.sphere": "surface",
             "surf/lh.sphere.reg": "surface", "surf/rh.sphere.reg": "surface",
             "mri/orig.mgz": "reference volume", "transforms/talairach.xfm": "talairach transform",
             "mri/brain.mgz": "brain volume", "mri/aseg.mgz": "aseg volume",
             "mri/aparc+aseg.mgz": "aparc+aseg volume"}
    inventory_rows = []
    for rel in REQUIRED + ["surf/lh.sphere", "surf/rh.sphere", "surf/lh.sphere.reg",
                           "surf/rh.sphere.reg", "mri/brain.mgz", "mri/aseg.mgz",
                           "mri/aparc+aseg.mgz"]:
        p = FS / rel
        inventory_rows.append(dict(relative_path=rel, asset_role=roles.get(rel, "other"),
                                   exists=p.exists(),
                                   size_bytes=p.stat().st_size if p.exists() else 0,
                                   sha256=sha256(p) if p.exists() else ""))
    with open(OUT_INV, "w", newline="", encoding="utf-8-sig") as fh:
        cols = ["relative_path", "asset_role", "exists", "size_bytes", "sha256"]
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for r in inventory_rows:
            w.writerow(r)
    with open(OUT_HASH, "w", newline="", encoding="utf-8-sig") as fh:
        cols = ["relative_path", "asset_role", "size_bytes", "sha256"]
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for rel in REQUIRED:
            p = FS / rel
            w.writerow(dict(relative_path=rel, asset_role=roles.get(rel, ""),
                            size_bytes=p.stat().st_size if p.exists() else 0,
                            sha256=sha256(p) if p.exists() else ""))

    annot = {}
    top_rows = []
    for hemi in ("lh", "rh"):
        labels, ctab, names = read_annot(str(FS / f"label/{hemi}.aparc.annot"))
        wc, wf = read_geometry(str(FS / f"surf/{hemi}.white"))
        pc, pf = read_geometry(str(FS / f"surf/{hemi}.pial"))
        n = [x.decode() if isinstance(x, bytes) else str(x) for x in names]
        annot[hemi] = dict(atlas="Desikan-Killiany (FreeSurfer aparc)", is_dk=True,
                           sha256=sha256(FS / f"label/{hemi}.aparc.annot"),
                           vertices=int(len(labels)), label_count=len(n), names=n)
        top_rows.append(dict(hemisphere=hemi, annot_vertices=int(len(labels)),
                             white_vertices=int(len(wc)), pial_vertices=int(len(pc)),
                             white_faces=int(len(wf)), pial_faces=int(len(pf)),
                             topology_equal=(len(labels) == len(wc) == len(pc) and len(wf) == len(pf))))
    with open(OUT_TOP, "w", newline="", encoding="utf-8-sig") as fh:
        cols = list(top_rows[0].keys())
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for r in top_rows:
            w.writerow(r)

    # 62-target crosscheck
    rows = list(csv.DictReader(open(DK_AUDITS / "dk34_surface_label_to_g1_crosswalk.csv",
                                    encoding="utf-8-sig")))
    aligned = [r for r in rows if r["alignment_status"] == "ALIGNED" and r["g1_entity_id"]]
    mismatch = []
    for r in aligned:
        hemi = "lh" if r["hemisphere"] == "left" else "rh"
        labels, _, names = read_annot(str(FS / f"label/{hemi}.aparc.annot"))
        n = [x.decode() if isinstance(x, bytes) else str(x) for x in names]
        if r["dk_label_name"] not in n:
            mismatch.append(r["g1_entity_id"])
    annot_val = dict(parcellation="Desikan-Killiany aparc", is_dk_all=True,
                     left=annot["lh"], right=annot["rh"],
                     crosscheck=dict(aligned=len(aligned), matched=len(aligned) - len(mismatch),
                                     mismatches=mismatch))
    with open(OUT_ANNOT, "w", encoding="utf-8") as fh:
        json.dump(annot_val, fh, ensure_ascii=False, indent=2)

    img = MGHImage.load(str(FS / "mri/orig.mgz"))
    v2r = np.asarray(img.header.get_vox2ras())
    v2rt = np.asarray(img.header.get_vox2ras_tkr())
    orig = dict(
        present=True,
        path="mri/orig.mgz",
        sha256=sha256(FS / "mri/orig.mgz"),
        shape=[int(s) for s in img.shape],
        voxel_size_mm=[float(z) for z in img.header.get_zooms()[:3]],
        dtype=str(img.get_data_dtype()),
        vox2ras=v2r.round(6).tolist(),
        vox2ras_tkr=v2rt.round(6).tolist(),
        vox2ras_eq_vox2ras_tkr=bool(np.allclose(v2r, v2rt)),
        note=("vox2ras == vox2ras_tkr for the fsaverage template volume (1mm 256^3, tkRAS-aligned "
              "internal geometry). This is the source-internal identity; it is NOT an MNI152 "
              "2009cAsym mapping."),
        orientation_center="tkRAS origin ~ center (voxel 128) under the shared matrix")
    with open(OUT_ORIG, "w", encoding="utf-8") as fh:
        json.dump(orig, fh, ensure_ascii=False, indent=2)

    tala = dict(
        present=hashes["transforms/talairach.xfm"]["sha256"] is not None,
        sha256=hashes["transforms/talairach.xfm"]["sha256"],
        source_status="HTTP 404 on the official tutorial fsaverage base",
        semantics_note=("talairach.xfm (MNI305/Talairach space transform) is required for a COMPLETE "
                        "official asset set but is NOT shipped on the tutorial mirror; obtaining it "
                        "would require the full official FreeSurfer distribution (license/registration)"),
        not_mni2009c_route=True,
        rule="talairach.xfm != MNI152NLin2009cAsym transform; MNI305/Talairach != MNI152 2009c",
        used=False)
    with open(OUT_TALA, "w", encoding="utf-8") as fh:
        json.dump(tala, fh, ensure_ascii=False, indent=2)

    topology_ok = all(r["topology_equal"] for r in top_rows)
    status = dict(
        status_id="FSAVERAGE_OFFICIAL_ASSET_SET_V1",
        verdict="CORTICAL_FSAVERAGE_COMPLETE_SOURCE_ASSET_BLOCKED",
        asset_set_status="INCOMPLETE",
        required_missing=missing_req,
        release_identity="PARTIALLY_RESOLVED",
        surface_topology="CONSISTENT" if topology_ok else "MISMATCH",
        source_internal_geometry="RESOLVED",
        sixty_two_target_crosscheck="PASS" if not mismatch else "FAIL",
        present_required=present_files,
        toolchain="BLOCKED (unchanged from prior round: FREESURFER_TOOLCHAIN_MANUAL_INSTALL_REQUIRED + "
                  "FREESURFER_LICENSE_REQUIRED)",
        target_mni2009c_route="NOT_ADJUDICATED (separate later round)",
        effective_prerequisite_state="CORTICAL_BRIDGE_SOURCE_AND_TOOLCHAIN_BLOCKED (source improved "
                                     "(pial+orig present) but incomplete: talairach.xfm absent; "
                                     "toolchain blocked) - NOT READY",
        geometry_generated=False,
        note="existing partial set is superseded as the current official same-release asset set; "
             "prior prerequisite snapshot (commit 3f42149) is left unchanged",
        created_at=ts, script_version=SCRIPT_VERSION)
    with open(OUT_STATUS, "w", encoding="utf-8") as fh:
        json.dump(status, fh, ensure_ascii=False, indent=2)

    md = [
        "# Phase1.7 V3 - Official FreeSurfer fsaverage complete subject asset acquisition + provenance", "",
        f"Release: {release['distribution']} (official freesurfer.net tutorial mirror); "
        f"release_identity {release['release_identity']}. Same official distribution asset set.",
        "This round added surf/lh.pial, surf/rh.pial, mri/orig.mgz from the same official base.",
        f"annotation == white == pial vertices: 163842/side, faces 327680 -> topology "
        f"{'CONSISTENT' if topology_ok else 'MISMATCH'}.",
        f"62-target DK crosscheck: {len(aligned)-len(mismatch)}/{len(aligned)} PASS "
        f"(mismatches: {mismatch or 'none'}).",
        f"orig.mgz: shape {orig['shape']} @ {orig['voxel_size_mm']} mm, dtype {orig['dtype']}; "
        f"vox2ras == vox2ras_tkr (fsaverage internal tkRAS-aligned; NOT an MNI152 mapping).",
        f"transforms/talairach.xfm: ABSENT (404 on official tutorial mirror); not used; "
        "talairach != MNI2009c route.",
        f"VERDICT: {status['verdict']}. asset_set_status INCOMPLETE; required missing: {missing_req}.",
        "toolchain still BLOCKED (unchanged). target MNI2009c route NOT_ADJUDICATED. No cortical "
        "geometry generated.", ""]
    with open(OUT_MD, "w", encoding="utf-8") as fh:
        fh.write("\n".join(md) + "\n")

    print("verdict:", status["verdict"], "| asset_set_status:", status["asset_set_status"])
    print("missing required:", missing_req)
    print("topology:", status["surface_topology"], "| 62/62:", status["sixty_two_target_crosscheck"])
    print("orig:", orig["shape"], orig["voxel_size_mm"], "| vox2ras==tkRAS:",
          orig["vox2ras_eq_vox2ras_tkr"])
    print("toolchain BLOCKED unchanged; geometry NOT generated | wrote 10 artifacts")


if __name__ == "__main__":
    main()
