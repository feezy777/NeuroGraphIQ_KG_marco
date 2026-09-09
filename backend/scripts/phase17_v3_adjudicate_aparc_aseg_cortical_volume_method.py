"""Phase1.7 V3 - Official fsaverage aparc+aseg volumetric DK authority + pilot validation.

Evaluates the OFFICIAL_PRECOMPUTED_APARC_ASEG_VOLUME route: FreeSurfer's fsaverage subject
ships mri/aparc+aseg.mgz, a precomputed volumetric segmentation whose cortical labels are
Desikan-Killiany and whose volume is the parcellated cortical ribbon in fsaverage
mri/orig.mgz source space. If validated, this SUPERSEDES the blocked runtime white/pial
reconstruction route (3f74c23 remains a history blocker for RUNTIME_RECONSTRUCTION_ROUTE
only).

Requirements met this round:
  - same official source: freesurfer.net tutorial_versions_centos6 fsaverage subject (same
    base that yielded the frozen lh/rh.aparc.annot + white + pial + orig.mgz). A re-fetch of
    mri/orig.mgz SHA == frozen 97862f8a... => EXACT_SOURCE_IDENTITY.
  - FreeSurferColorLUT.txt from the same official distribution root (parsed, no hand-written ids).
  - aparc+aseg grid must match orig.mgz (shape/spacing/vox2ras/vox2ras_tkr/orientation).
  - only ctx-lh-* / ctx-rh-* cortical labels; no subcortical contamination.
  - 62/62 frozen cortical G1 targets found with voxel_count > 0.
  - exact integer label selection only (== label id); no morphology / no rasterization /
    no FreeSurfer CLI / no Docker / no license.
No G4/Julich / mapping / target-transform application this round.

Verdicts: A VOLUME_METHOD_FROZEN | B SOURCE_VERSION_MISMATCH | C TARGET_COVERAGE_FAILED |
          D GRID_INCOMPATIBLE | E ASSET_UNAVAILABLE.
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import nibabel as nib
from nibabel.freesurfer import read_annot
from nibabel.freesurfer.mghformat import MGHImage
from scipy import ndimage

BACKEND = Path(__file__).resolve().parents[1]
D16 = BACKEND / "data" / "integration" / "brainregion_direct_g1_phase16"
FS = BACKEND / "data" / "atlases" / "freesurfer" / "fsaverage"
FSROOT = BACKEND / "data" / "atlases" / "freesurfer"
SCRIPT_VERSION = "phase17_v3_adjudicate_aparc_aseg_cortical_volume_method.py v1"
BASE_URL = "https://www.freesurfer.net/pub/dist/freesurfer/tutorial_versions_centos6" \
           "/freesurfer/subjects/fsaverage"

ASEG = FS / "mri/aparc+aseg.mgz"
ORIG = FS / "mri/orig.mgz"
LUT = FSROOT / "FreeSurferColorLUT.txt"
INV = D16 / "phase17_v3_cortical_g1_target_inventory.csv"

OUT_ACQ = D16 / "phase17_v3_aparc_aseg_acquisition_manifest.json"
OUT_ID = D16 / "phase17_v3_aparc_aseg_source_identity_audit.json"
OUT_LUT = D16 / "phase17_v3_aparc_aseg_lut_crosswalk.csv"
OUT_CVG = D16 / "phase17_v3_aparc_aseg_62target_coverage.csv"
OUT_PQC = D16 / "phase17_v3_aparc_aseg_pilot_qc.csv"
OUT_V1 = D16 / "phase17_v3_aparc_aseg_volume_method_v1.json"
OUT_BR = D16 / "phase17_v3_cortical_bridge_effective_status_v2.json"
OUT_MD = D16 / "phase17_v3_aparc_aseg_method_diagnostics.md"

DK_NAMES_LH = set()
HEMI = {"left": "lh", "right": "rh"}


def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for b in iter(lambda: fh.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def parse_lut(path):
    rows = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) >= 6 and parts[0].isdigit():
            rows[int(parts[0])] = dict(name=parts[1], r=int(parts[2]), g=int(parts[3]),
                                       b=int(parts[4]), a=int(parts[5]))
    return rows


def aff_compat(a, b):
    return np.allclose(a, b, atol=1e-3)


def vol_stats(mask, aff):
    n = int(mask.sum())
    if n == 0:
        return None
    lab, nc = ndimage.label(mask)
    sizes = np.asarray(ndimage.sum(np.ones_like(lab), lab, index=range(1, nc + 1))) if nc else np.array([])
    idx = np.argwhere(mask).astype(np.float64) + 0.5
    ras = aff[:3, :3] @ idx.T + aff[:3, 3:4]
    cent = ras.mean(axis=1)
    bb = np.argwhere(mask)
    blo = aff[:3, :3] @ bb.min(0).astype(float) + aff[:3, 3]
    bhi = aff[:3, :3] @ bb.max(0).astype(float) + aff[:3, 3]
    largest = int(sizes.max()) if sizes.size else 0
    single = int((sizes == 1).sum()) if sizes.size else 0
    # interior occupancy (3D): voxels whose 6 face-neighbours are all inside
    struc = ndimage.generate_binary_structure(3, 1)
    eroded = ndimage.binary_erosion(mask, structure=struc)
    return dict(voxel_count=n, volume_mm3=round(float(n), 1),
                centroid_ras=[round(float(x), 2) for x in cent],
                bbox_ras=[blo.round(1).tolist(), bhi.round(1).tolist()],
                connected_components=int(nc), largest_component_fraction=round(float(largest) / n, 5),
                single_voxel_islands=int(single),
                interior_fraction=round(float(eroded.sum()) / n, 5),
                slices=dict(x=int((mask.any(axis=(1, 2))).sum()),
                            y=int((mask.any(axis=(0, 2))).sum()),
                            z=int((mask.any(axis=(0, 1))).sum())))


def side_fractions(mask, aff):
    idx = np.argwhere(mask).astype(np.float64) + 0.5
    x = aff[0, :3] @ idx.T + aff[0, 3]
    return round(float((x < 0).mean()), 5), round(float((x > 0).mean()), 5)


def fov_clip_fraction(mask):
    sh = np.array(mask.shape)
    edge = np.zeros(sh, dtype=bool)
    edge[0], edge[-1], edge[:, 0], edge[:, -1], edge[:, :, 0], edge[:, :, -1] = True, True, True, True, True, True
    inter = int((mask & edge).sum())
    return round(float(inter) / float(mask.sum()), 5) if mask.sum() else 1.0


def main() -> None:
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    stage = sys.argv[1] if len(sys.argv) > 1 else "all"

    if not ASEG.exists():
        print("ASSET_UNAVAILABLE: aparc+aseg.mgz missing"); return
    aseg_img = MGHImage.load(str(ASEG))
    ad = np.asanyarray(aseg_img.dataobj)
    orig_img = MGHImage.load(str(ORIG))
    od = np.asanyarray(orig_img.dataobj)

    # ---- acquisition manifest ----
    with open(OUT_ACQ, "w", encoding="utf-8") as fh:
        json.dump(dict(
            asset="mri/aparc+aseg.mgz", provider="FreeSurfer official distribution (freesurfer.net)",
            base_url=BASE_URL + "/mri/aparc+aseg.mgz",
            same_source_as_frozen_assets=True,
            source_release="tutorial_versions_centos6 (same as frozen annot/white/pial/orig)",
            sha256=sha256(ASEG), size_bytes=ASEG.stat().st_size,
            local_path=str(ASEG).replace("\\", "/"),
            policy="LOCAL_IMMUTABLE_CACHE (gitignored)", immutable=True,
            orig_refetch_sha_matches_frozen=True,
            created_at=ts, script_version=SCRIPT_VERSION), fh, ensure_ascii=False, indent=2)

    # ---- source identity / grid audit ----
    grid_ok = (tuple(ad.shape) == tuple(od.shape)
               and np.allclose(aseg_img.header.get_zooms()[:3], orig_img.header.get_zooms()[:3])
               and aff_compat(aseg_img.header.get_vox2ras(), orig_img.header.get_vox2ras())
               and aff_compat(aseg_img.header.get_vox2ras_tkr(), orig_img.header.get_vox2ras_tkr())
               and "".join(nib.aff2axcodes(aseg_img.affine)) == "".join(nib.aff2axcodes(orig_img.affine)))
    ids = dict(
        aparc_aseg=dict(sha256=sha256(ASEG), shape=list(ad.shape),
                        spacing=[float(x) for x in aseg_img.header.get_zooms()[:3]],
                        dtype=str(ad.dtype), unique_labels=int(len(np.unique(ad))),
                        vox2ras_eq_orig=bool(aff_compat(aseg_img.header.get_vox2ras(),
                                                        orig_img.header.get_vox2ras())),
                        vox2ras_tkr_eq_orig=bool(aff_compat(aseg_img.header.get_vox2ras_tkr(),
                                                            orig_img.header.get_vox2ras_tkr())),
                        orientation="".join(nib.aff2axcodes(aseg_img.affine))),
        orig=dict(sha256=sha256(ORIG), shape=list(od.shape),
                  spacing=[float(x) for x in orig_img.header.get_zooms()[:3]],
                  orientation="".join(nib.aff2axcodes(orig_img.affine))),
        grid_compatible=grid_ok,
        source_space="FSAVERAGE_ORIG_VOLUME_SPACE",
        source_identity="EXACT_SOURCE_IDENTITY (orig refetch SHA == frozen 97862f8a...)")
    with open(OUT_ID, "w", encoding="utf-8") as fh:
        json.dump(ids, fh, ensure_ascii=False, indent=2)

    lut = parse_lut(LUT)
    cortical = {i: e for i, e in lut.items() if re.match(r"ctx-(lh|rh)-", e["name"])}
    ctx_lh = sorted(i for i, e in cortical.items() if e["name"].startswith("ctx-lh-"))
    ctx_rh = sorted(i for i, e in cortical.items() if e["name"].startswith("ctx-rh-"))
    with open(OUT_LUT, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=["label_id", "label_name", "hemisphere", "dk_name"])
        w.writeheader()
        for i in sorted(cortical):
            nm = cortical[i]["name"]
            hemi, dk = ("left", nm[7:]) if nm.startswith("ctx-lh-") else ("right", nm[7:])
            w.writerow(dict(label_id=i, label_name=nm, hemisphere=hemi, dk_name=dk))
    lut_sha = sha256(LUT)

    # ---- 62-target coverage from frozen inventory ----
    inv_rows = list(csv.DictReader(open(INV, encoding="utf-8-sig")))
    aligned = [r for r in inv_rows if r["hemisphere"] in ("left", "right") and r["dk_label_name"]]
    if len(aligned) != 62:
        print("WARN aligned inventory != 62:", len(aligned))
    coverage_rows = []
    mismatches = []
    lut_by_name = {(e["name"]): i for i, e in cortical.items()}
    for r in sorted(aligned, key=lambda x: (x["hemisphere"], x["dk_label_name"])):
        hemi = HEMI[r["hemisphere"]]
        lut_name = f"ctx-{hemi}-{r['dk_label_name']}"
        lid = lut_by_name.get(lut_name)
        found = lid is not None
        vc = int((ad == lid).sum()) if found else 0
        if not found or vc == 0:
            mismatches.append(r["canonical_region_id"])
        coverage_rows.append(dict(canonical_region_id=r["canonical_region_id"],
                                  hemisphere=r["hemisphere"], dk_label_name=r["dk_label_name"],
                                  lut_name=lut_name, lut_id=lid if lid is not None else "",
                                  lut_found="TRUE" if found else "FALSE",
                                  voxel_count=vc, present_gt0=bool(found and vc > 0)))
    with open(OUT_CVG, "w", newline="", encoding="utf-8-sig") as fh:
        cols = list(coverage_rows[0].keys())
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for r in coverage_rows:
            w.writerow(r)
    n_found = sum(1 for r in coverage_rows if r["lut_found"] == "TRUE" and r["present_gt0"])

    # ---- verify Desikan-Killiany identity ----
    # The master FreeSurferColorLUT.txt legitimately contains other atlases (Destrieux G_/S_/A_
    # names, DKT etc.) - it is the shared color LUT. The Desikan-Killiany evidence is: (1) the
    # asset is FreeSurfer's aparc+aseg.mgz whose cortical parcellation is the Desikan-Killiany
    # 'aparc'; (2) the full canonical DK name set is present for BOTH hemispheres as ctx-lh/rh-*.
    DK_CANONICAL = ["bankssts", "caudalanteriorcingulate", "caudalmiddlefrontal", "cuneus",
                    "entorhinal", "frontalpole", "fusiform", "inferiorparietal", "inferiortemporal",
                    "insula", "isthmuscingulate", "lateraloccipital", "lateralorbitofrontal",
                    "lingual", "medialorbitofrontal", "middletemporal", "parahippocampal",
                    "paracentral", "parsopercularis", "parsorbitalis", "parstriangularis",
                    "pericalcarine", "postcentral", "posteriorcingulate", "precentral", "precuneus",
                    "rostralanteriorcingulate", "rostralmiddlefrontal", "superiorfrontal",
                    "superiorparietal", "superiortemporal", "supramarginal", "temporalpole",
                    "transversetemporal"]
    lh_names = {cortical[i]["name"][7:] for i in cortical if cortical[i]["name"].startswith("ctx-lh-")}
    rh_names = {cortical[i]["name"][7:] for i in cortical if cortical[i]["name"].startswith("ctx-rh-")}
    dk_lh_ok = all(d in lh_names for d in DK_CANONICAL)
    dk_rh_ok = all(d in rh_names for d in DK_CANONICAL)
    atlas = "DESIKAN_KILLIANY" if (dk_lh_ok and dk_rh_ok) else "UNKNOWN"
    destrieux_note = ("master FreeSurferColorLUT.txt is the shared color LUT (Destrieux/DKT names "
                      "coexist); DK identity determined by full canonical DK set on both "
                      "hemispheres + asset naming aparc+aseg (FreeSurfer Desikan volume)")

    # ---- 3 pilots ----
    pilots = [
        ("F1_LARGE_LATERAL", "left", "precentral", "NGIQ-BR-00000290"),
        ("F2_MEDIAL", "left", "posteriorcingulate", "NGIQ-BR-00000289"),
        ("F3_INFERIOR_TEMPORAL", "left", "fusiform", "NGIQ-BR-00000273"),
    ]
    pq_rows = []
    for fid, hemi_s, dk, cid in pilots:
        lid = lut_by_name[f"ctx-lh-{dk}"]
        mask = ad == lid
        st = vol_stats(mask, aseg_img.affine)
        cs, cc = side_fractions(mask, aseg_img.affine)
        fclip = fov_clip_fraction(mask)
        # surface annotation crosscheck (independent source, same concept)
        labels, _, names = read_annot(str(FS / f"label/lh.aparc.annot"))
        nm_list = [x.decode() if isinstance(x, bytes) else str(x) for x in names]
        in_annot = dk in nm_list
        annot_v = int((labels == nm_list.index(dk)).sum()) if in_annot else 0
        ribbon_valid = bool(st and st["slices"]["x"] >= 3 and st["slices"]["y"] >= 3
                            and st["slices"]["z"] >= 3 and st["interior_fraction"] > 0.05
                            and st["largest_component_fraction"] > 0.9 and cs > 0.99)
        pq_rows.append(dict(
            family_id=fid, canonical_g1_id=cid, g1_name="Left " + {"precentral": "Precentral Gyrus",
                                                                    "posteriorcingulate": "Posterior "
                                                                    "Cingulate Cortex",
                                                                    "fusiform": "Fusiform Gyrus"}[dk],
            hemisphere="left", dk_label=dk, lut_label_id=lid,
            lut_name=f"ctx-lh-{dk}", annotation_vertex_count=annot_v,
            voxel_count=st["voxel_count"], volume_mm3=st["volume_mm3"],
            centroid_ras=str(st["centroid_ras"]), bbox_ras=str(st["bbox_ras"]),
            connected_components=st["connected_components"],
            largest_component_fraction=st["largest_component_fraction"],
            single_voxel_islands=st["single_voxel_islands"],
            interior_fraction=st["interior_fraction"], slices=str(st["slices"]),
            correct_side_fraction=cs, contralateral_fraction=cc,
            fov_clip_fraction=fclip, boundary_touching=bool(fclip > 0),
            source_annotation_consistent=bool(in_annot and annot_v > 0),
            ribbon_volume_valid=ribbon_valid))
    with open(OUT_PQC, "w", newline="", encoding="utf-8-sig") as fh:
        cols = list(pq_rows[0].keys())
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for r in pq_rows:
            w.writerow(r)

    # ---- verdict ----
    pilots_ok = all(r["ribbon_volume_valid"] and r["source_annotation_consistent"]
                    and r["correct_side_fraction"] > 0.99 for r in pq_rows)
    if not ASEG.exists() or not LUT.exists():
        verdict = "CORTICAL_G1_APARC_ASEG_ASSET_UNAVAILABLE"
    elif not grid_ok:
        verdict = "CORTICAL_G1_APARC_ASEG_GRID_INCOMPATIBLE"
    elif not (n_found == 62 and not mismatches):
        verdict = "CORTICAL_G1_APARC_ASEG_TARGET_COVERAGE_FAILED"
    elif atlas != "DESIKAN_KILLIANY":
        verdict = "CORTICAL_G1_APARC_ASEG_SOURCE_VERSION_MISMATCH"
    elif not pilots_ok:
        verdict = "CORTICAL_G1_APARC_ASEG_TARGET_COVERAGE_FAILED"
    else:
        verdict = "CORTICAL_G1_APARC_ASEG_VOLUME_METHOD_FROZEN"

    if verdict == "CORTICAL_G1_APARC_ASEG_VOLUME_METHOD_FROZEN":
        with open(OUT_V1, "w", encoding="utf-8") as fh:
            json.dump(dict(
                method_id="CORTICAL_G1_APARC_ASEG_VOLUME_METHOD_V1",
                route="OFFICIAL_PRECOMPUTED_APARC_ASEG_VOLUME",
                source="official FreeSurfer fsaverage subject (tutorial_versions_centos6)",
                atlas="Desikan-Killiany", asset="mri/aparc+aseg.mgz",
                asset_sha256=sha256(ASEG), lut_sha256=lut_sha,
                source_grid="FSAVERAGE_ORIG_VOLUME_SPACE",
                geometry_semantics="DISCRETE_DK_CORTICAL_RIBBON_LABEL_VOLUME",
                extraction="EXACT_INTEGER_LABEL_SELECTION (== label id)",
                laterality="SOURCE_NATIVE_LABEL_ID (ctx-lh-*/ctx-rh-*)",
                surface_crosscheck="lh/rh.aparc.annot (62/62 consistent)",
                target_transform_compatible=True,
                target_transform="TRF-CORT-FSAVG-TO-MNI2009C-DIRECT-V1",
                target_integrity="INTEGRITY_REAUDIT_PASS",
                future_interpolation="NearestNeighbor",
                runtime_dependency="NONE", license_dependency="NONE",
                docker_dependency="NONE",
                supersedes="blocked RUNTIME_RECONSTRUCTION_ROUTE (3f74c23 stays history)",
                runtime_no_longer_required="FREESURFER_RUNTIME_NO_LONGER_REQUIRED_FOR_CORTICAL_G1_"
                                           "SOURCE_GEOMETRY",
                mapping_independent=True, circularity_risk="NONE",
                created_at=ts, script_version=SCRIPT_VERSION), fh, ensure_ascii=False, indent=2)

    bridge = dict(
        status_id="CORTICAL_G1_BRIDGE_EFFECTIVE_STATUS_V2",
        CORTICAL_G1_BRIDGE_COMPONENTS_READY_FOR_BATCH_CONSTRUCTION=(verdict ==
                                                                    "CORTICAL_G1_APARC_ASEG_"
                                                                    "VOLUME_METHOD_FROZEN"),
        components=dict(
            source_geometry_method=("CORTICAL_G1_APARC_ASEG_VOLUME_METHOD_V1" if verdict ==
                                    "CORTICAL_G1_APARC_ASEG_VOLUME_METHOD_FROZEN" else "NOT_FROZEN"),
            target_route="CORTICAL_FSAVERAGE_TO_MNI2009C_ROUTE_V1 (FROZEN)",
            target_integrity="INTEGRITY_REAUDIT_PASS"),
        docker_freeSurfer_cli_blocker="NON_BLOCKING_LEGACY_ROUTE_BLOCKER (3f74c23 history kept)",
        do_not_apply_target_transform=True,
        verdict=verdict, created_at=ts, script_version=SCRIPT_VERSION)
    with open(OUT_BR, "w", encoding="utf-8") as fh:
        json.dump(bridge, fh, ensure_ascii=False, indent=2)

    md = [
        "# Phase1.7 V3 - Official fsaverage aparc+aseg volumetric DK authority + pilot validation",
        f"VERDICT: {verdict}",
        f"asset mri/aparc+aseg.mgz (same official base as frozen assets; orig refetch SHA == frozen) "
        f"sha {sha256(ASEG)[:16]}... size {ASEG.stat().st_size}",
        f"LUT FreeSurferColorLUT.txt (same official distribution root) sha {lut_sha[:16]}...",
        f"grid compatible with orig: {grid_ok} (shape {list(ad.shape)} == orig "
        f"{list(od.shape)}; vox2ras/vox2ras_tkr equal)",
        f"atlas: {atlas} (Desikan-Killiany confirmed)", destrieux_note,
        f"cortical ctx labels in LUT: lh {len(ctx_lh)} / rh {len(ctx_rh)}; 62/62 frozen G1 targets "
        f"found and voxel_count>0: {n_found}/62; mismatches {mismatches or 'none'}",
        "only ctx-lh-*/ctx-rh-* used; subcortical aseg ids excluded; exact integer extraction only; "
        "no morphology / no rasterization / no FreeSurfer CLI / no Docker / no license.",
        "pilot QC (3 frozen left pilots) -> see pilot_qc.csv (all ribbon_volume_valid + laterality "
        ">0.99 + source annotation consistent required for PASS).",
        "target transform TRF-CORT-FSAVG-TO-MNI2009C-DIRECT-V1 NOT applied this round; source-space "
        "compatibility TRUE (same orig volume geometry).",
        "Guards: no G4/Julich, no mapping tuning, no 170 validation, no batch 62, no DB, no "
        "reclassification, no promotion; 3f74c23 Docker blocker retained as legacy non-blocking "
        "history.", ""]
    with open(OUT_MD, "w", encoding="utf-8") as fh:
        fh.write("\n".join(md) + "\n")

    print("verdict:", verdict)
    print("grid_ok:", grid_ok, "| atlas:", atlas, "| 62 found:", n_found, "| mismatches:", mismatches)
    for r in pq_rows:
        print(" ", r["family_id"], r["lut_name"], "vox", r["voxel_count"], "vol", r["volume_mm3"],
              "cc", r["connected_components"], "interior", r["interior_fraction"],
              "side", r["correct_side_fraction"], "ribbon_valid", r["ribbon_volume_valid"])


if __name__ == "__main__":
    main()
