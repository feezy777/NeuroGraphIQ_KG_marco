"""Phase1.7 V3 - THALAMUS_PROPER G1 Native-Space Reference Geometry Construction.

Builds Left/Right Thalamus G1 probability geometry in the SOURCE-NATIVE space of
FreeSurfer / Iglesias ThalamusProbs.MNIsymSpace.nii.gz (ICBM152 2009c symmetric,
138x106x94 @0.5mm, 53 channels) by SUM of included channels.

Source-channel scope is derived programmatically from the frozen V3 scope
contract (THALAMUS_G1_SCOPE_CONTRACT_V3) + the real names.txt channel metadata.
The only excluded nucleus channel per side is Reticular R (DEC-THAL-03);
background/Unknown channel 0 is excluded. LGN/MGN/L-Sg/Pulvinar/Anterior/
Mediodorsal/Ventral/Intralaminar/Midline/LP/LD/VAmc are INCLUDE.

Formula (probability semantics MUTUALLY_EXCLUSIVE_CATEGORICAL, operator SUM):
    P_Left_Thalamus(x)  = sum_i P_i(x)  for i in LEFT_INCLUDED_CHANNELS
    P_Right_Thalamus(x) = sum_i P_i(x)  for i in RIGHT_INCLUDED_CHANNELS

Forbidden: MAX / probabilistic union / threshold / binarization / clipped sum /
renormalization. If a sum > 1 + tol -> PROBABILITY_CONSERVATION_FAILURE, abort.

QC invariants enforced here:
  - all26 (all source nuclei per side) == G1 (25) + Reticular R voxelwise
  - background + all 52 nuclei == 1 (atlas-wide conservation preserved)
  - laterality uses SOURCE-NATIVE channel identity (NOT world-X split); world-X
    only in QC
  - output grid/affine == source grid/affine (no registration/resampling)

Independent of the G3->G1 frozen mapping: independent_from_g3_g1_mapping=TRUE,
circularity_risk=NONE. NOT Julich-ready: direct_g4_overlap_ready=FALSE,
transform_required=SYMMETRIC_TO_ASYMMETRIC_TEMPLATE_TRANSFORM_REQUIRED.

The two derived NIfTI are local only (derived_g1 policy: not committed).
No DB write; no commit; no Sym->Asym transform.
"""
from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import nibabel as nib
import numpy as np

BACKEND = Path(__file__).resolve().parents[1]
D16 = BACKEND / "data" / "integration" / "brainregion_direct_g1_phase16"
DERIVED = BACKEND / "data" / "atlases" / "derived_g1"
RAW = BACKEND / "data" / "atlases" / "external_raw" / "freesurfer_icbm2009c" / "thalamus" / "ThalamusProbs.MNIsymSpace.nii.gz"
NAMES = BACKEND / "data" / "atlases" / "external_raw" / "freesurfer_icbm2009c" / "thalamus" / "ThalamusProbs.MNIsymSpace.names.txt"
V3 = D16 / "phase17_v3_thalamus_g1_scope_contract_v3.json"
CLASS = D16 / "phase17_v3_classification.csv"

OUT_MANIFEST = D16 / "phase17_v3_thalamus_g1_native_geometry_manifest.json"
OUT_QC = D16 / "phase17_v3_thalamus_g1_native_geometry_qc.csv"
OUT_MD = D16 / "phase17_v3_thalamus_g1_native_geometry_diagnostics.md"
OUT_LEFT_NIFTI = DERIVED / "left_thalamus_proper_prob_icbm2009csym.nii.gz"
OUT_RIGHT_NIFTI = DERIVED / "right_thalamus_proper_prob_icbm2009csym.nii.gz"

RAW_SHA_EXPECTED = "640377ae93cf0782365a698573970c2a429a775c6f64dcf9ac02536156b51f22"
V3_SHA_EXPECTED = "22e24a31bab9659769f7e550ee32f8e3b37887d0ae1a4c4c4cf64974c3c05f68"
NAMES_SHA_EXPECTED = "74b70bfa4fa75aa05a0bee9fcb548fa97bea20bfceef43b63a97c52a3923bfec"
SCRIPT_VERSION = "phase17_v3_construct_thalamus_g1_native_geometry.py v1"
TOL = 1e-3

# canonical IDs
LID, RID = "NGIQ-BR-00000247", "NGIQ-BR-00000256"
GEOM_L = "GEO-G1-THAL-L-FS2009CSYM-V1"
GEOM_R = "GEO-G1-THAL-R-FS2009CSYM-V1"


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        while True:
            b = fh.read(1 << 20)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def load_names(p: Path):
    """Return list[(axis_index, numeric_label, official_name, hemisphere, nucleus)].
    axis_index = row order in names.txt (matches the volume 4th dimension)."""
    out = []
    for i, line in enumerate(open(p, encoding="utf-8")):
        line = line.strip()
        if not line:
            continue
        num, name = line.split(",", 1)
        num = int(num)
        hemi = None
        nucleus = name
        for hh in ("Left-", "Right-"):
            if name.startswith(hh):
                hemi = hh.rstrip("-").lower()
                nucleus = name[len(hh):]
                break
        out.append(dict(axis=i, numeric_label=num, official_name=name,
                        hemisphere=hemi, nucleus=nucleus))
    return out


# FreeSurfer / Iglesias 26-nucleus inventory -> (V3 decision, decision_id).
# Decision id is traceable to the frozen V3 scope contract vocabulary:
#   DEC-THAL-01 (LGN INCLUDE), DEC-THAL-02 (MGN INCLUDE),
#   DEC-THAL-03 (reticular EXCLUDE), DEC-THAL-04-LSG (L-Sg channel INCLUDE),
#   THAL-SCOPE-* (V1 dorsal-thalami mass group INCLUDE decisions inherited by V3)
# Only "R" is EXCLUDE (ventral/perithalamus shell); every other nucleus is a
# dorsal thalami mass nucleus frozen INCLUDE by the V3 contract.
NUCLEUS_SCOPE = {
    # INCLUDE - dorsal thalami mass (V3 contract / canonical identity)
    "AV": ("INCLUDE", "THAL-SCOPE-05"),
    "CeM": ("INCLUDE", "THAL-SCOPE-08"),
    "CL": ("INCLUDE", "THAL-SCOPE-08"),
    "CM": ("INCLUDE", "THAL-SCOPE-08"),
    "LD": ("INCLUDE", "THAL-SCOPE-11"),
    "LGN": ("INCLUDE", "DEC-THAL-01"),
    "LP": ("INCLUDE", "THAL-SCOPE-11"),
    "L-Sg": ("INCLUDE", "DEC-THAL-04-LSG"),
    "MDl": ("INCLUDE", "THAL-SCOPE-06"),
    "MDm": ("INCLUDE", "THAL-SCOPE-06"),
    "MGN": ("INCLUDE", "DEC-THAL-02"),
    "MV(Re)": ("INCLUDE", "THAL-SCOPE-09"),
    "Pc": ("INCLUDE", "THAL-SCOPE-08"),
    "Pf": ("INCLUDE", "THAL-SCOPE-08"),
    "Pt": ("INCLUDE", "THAL-SCOPE-09"),
    "PuA": ("INCLUDE", "THAL-SCOPE-04"),
    "PuI": ("INCLUDE", "THAL-SCOPE-04"),
    "PuL": ("INCLUDE", "THAL-SCOPE-04"),
    "PuM": ("INCLUDE", "THAL-SCOPE-04"),
    "VA": ("INCLUDE", "THAL-SCOPE-07"),
    "VAmc": ("INCLUDE", "THAL-SCOPE-14"),
    "VLa": ("INCLUDE", "THAL-SCOPE-07"),
    "VLp": ("INCLUDE", "THAL-SCOPE-07"),
    "VM": ("INCLUDE", "THAL-SCOPE-07"),
    "VPL": ("INCLUDE", "THAL-SCOPE-07"),
    # EXCLUDE - ventral/perithalamus shell (DEC-THAL-03)
    "R": ("EXCLUDE", "DEC-THAL-03"),
}


def derive_scope(names, v3):
    """Derive left/right included/excluded channel sets from metadata + V3."""
    # Validate V3 frozen status / decision vocabulary that this script consumes
    v3d = v3["contract_v3"]
    assert v3d["inherited_decisions"]["reticular_decision"] == "EXCLUDE (DEC-THAL-03)"
    assert v3d["inherited_decisions"]["LGN_decision"] == "INCLUDE (DEC-THAL-01)"
    assert v3d["inherited_decisions"]["MGN_decision"] == "INCLUDE (DEC-THAL-02)"
    assert v3d["new_decisions"]["lsg_freeSurfer_channel_decision"] == "INCLUDE (DEC-THAL-04-LSG)"
    assert v3d["review_structures"] == []

    included = {"left": [], "right": []}
    excluded = {"left": [], "right": []}
    for ch in names:
        if ch["hemisphere"] is None:      # channel 0 = Unknown / background
            continue
        dec, dec_id = NUCLEUS_SCOPE[ch["nucleus"]]
        entry = dict(channel_index=ch["axis"], official_name=ch["official_name"],
                     numeric_label=ch["numeric_label"], nucleus=ch["nucleus"],
                     scope_decision_id=dec_id, decision=dec)
        if dec == "INCLUDE":
            included[ch["hemisphere"]].append(entry)
        else:
            excluded[ch["hemisphere"]].append(entry)

    # programmatic assertions (derived, not hard-coded)
    for side in ("left", "right"):
        n_inc = len(included[side])
        n_exc = len(excluded[side])
        assert n_exc == 1, f"{side}: expected exactly 1 excluded nucleus, got {n_exc}"
        assert excluded[side][0]["nucleus"] == "R", f"{side}: excluded must be Reticular R"
        # 26 source nuclei per side, 25 included (all except R)
        assert n_inc == 25, f"{side}: expected 25 included, got {n_inc}"
        names_inc = {x["nucleus"] for x in included[side]}
        for req in ("LGN", "MGN", "L-Sg"):
            assert req in names_inc, f"{side}: {req} must be INCLUDE"
        assert "R" not in names_inc
    return included, excluded


def conservation_sum(d, axis_ids):
    """float sum of channels listed in axis_ids (full 4th dim axis indices)."""
    if not axis_ids:
        return np.zeros(d.shape[:3], dtype=np.float64)
    return np.sum(np.asarray(d[..., axis_ids], dtype=np.float64), axis=-1)


def main() -> None:
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for p in (RAW, NAMES, V3):
        if not p.exists():
            raise SystemExit(f"FAIL: missing input {p}")
    DERIVED.mkdir(parents=True, exist_ok=True)

    raw_sha = sha256(RAW)
    names_sha = sha256(NAMES)
    v3_sha = sha256(V3)
    assert raw_sha == RAW_SHA_EXPECTED, f"raw SHA mismatch {raw_sha}"
    assert names_sha == NAMES_SHA_EXPECTED, f"names SHA mismatch {names_sha}"
    assert v3_sha == V3_SHA_EXPECTED, f"V3 SHA mismatch {v3_sha}"

    img = nib.load(RAW)
    data = np.asanyarray(img.dataobj)          # float32  (138,106,94,53)
    assert data.shape == (138, 106, 94, 53), data.shape
    assert data.ndim == 4 and data.shape[3] == 53
    assert np.allclose(np.diag(img.affine)[:3], 0.5)
    n_channels = data.shape[3]

    names = load_names(NAMES)
    assert len(names) == n_channels == 53
    # every axis must have an entry; axis index must match row order
    for k, ch in enumerate(names):
        assert ch["axis"] == k

    v3 = json.load(open(V3, encoding="utf-8"))
    included, excluded = derive_scope(names, v3)

    # --- aggregation: SUM over included channels (native laterality) ---
    # axis ids per side
    def axis_ids(entries):
        return sorted(e["channel_index"] for e in entries)

    # whole-atlas conservation before geometry
    bg = np.asarray(data[..., 0], dtype=np.float64)
    all52 = np.sum(np.asarray(data[..., 1:53], dtype=np.float64), axis=-1)  # 52 nuclei
    bg_all = bg + all52

    # per side: all26 (all nuclei incl R), G1 (included 25), R (reticular)
    left_all26 = conservation_sum(data, sorted(e["channel_index"] for e in
                                               included["left"] + excluded["left"]))
    right_all26 = conservation_sum(data, sorted(e["channel_index"] for e in
                                                included["right"] + excluded["right"]))
    left_g1 = conservation_sum(data, axis_ids(included["left"]))
    right_g1 = conservation_sum(data, axis_ids(included["right"]))
    left_r = conservation_sum(data, [e["channel_index"] for e in excluded["left"]])
    right_r = conservation_sum(data, [e["channel_index"] for e in excluded["right"]])

    # --- probability conservation failure gate ---
    for side, g1 in (("left", left_g1), ("right", right_g1)):
        mx = float(g1.max())
        if mx > 1 + TOL:
            raise SystemExit(f"PROBABILITY_CONSERVATION_FAILURE: {side} max={mx:.6f} > 1+{TOL}")

    # --- Reticular exclusion verification (all26 == G1 + R) ---
    resL = left_all26 - (left_g1 + left_r)
    resR = right_all26 - (right_g1 + right_r)
    for tag, res in (("left", resL), ("right", resR)):
        maxa = float(np.abs(res).max())
        meana = float(np.abs(res).mean())
        nz = int(np.count_nonzero(np.abs(res) > 1e-5))
        assert maxa < 1e-3, f"Reticular exclusion conservation FAILED {tag} max|res|={maxa}"
        print(f"[{tag}] all26==G1+R max_abs_residual={maxa:.3e} mean_abs={meana:.3e} nonzero={nz}")

    # --- atlas-wide conservation (bg + all52 ~ 1) ---
    bg_stats = dict(
        min=float(bg_all.min()), mean=float(bg_all.mean()),
        median=float(np.median(bg_all)), p95=float(np.percentile(bg_all, 95)),
        p99=float(np.percentile(bg_all, 99)), max=float(bg_all.max()),
        frac_gt_1plus=float(np.mean(bg_all > 1 + 1e-3)),
        frac_lt_0=float(np.mean(bg_all < -1e-3)))

    # --- geometry QC per side ---
    voxel_vol = float(np.prod(img.header.get_zooms()[:3]))  # 0.125 mm3

    def geom_qc(prob, hemi, n_inc, n_exc):
        gid = GEOM_L if hemi == "left" else GEOM_R
        # world coordinates from affine
        aff = img.affine
        I, J, K = np.meshgrid(np.arange(prob.shape[0]), np.arange(prob.shape[1]),
                              np.arange(prob.shape[2]), indexing="ij")
        xw = aff[0, 0] * I + aff[0, 3]
        yw = aff[1, 1] * J + aff[1, 3]
        zw = aff[2, 2] * K + aff[2, 3]
        p = prob.astype(np.float64)
        mass = float(p.sum())
        nz_support = int(np.count_nonzero(p > 0))
        wvol = mass * voxel_vol
        cx = float((p * xw).sum() / mass) if mass > 0 else float("nan")
        cy = float((p * yw).sum() / mass) if mass > 0 else float("nan")
        cz = float((p * zw).sum() / mass) if mass > 0 else float("nan")
        nz = np.argwhere(p > 0)
        bb_v = ([int(nz[:, 0].min()), int(nz[:, 1].min()), int(nz[:, 2].min())],
                [int(nz[:, 0].max()), int(nz[:, 1].max()), int(nz[:, 2].max())])
        xs = xw[p > 0]; ys = yw[p > 0]; zs = zw[p > 0]
        bb_w = ([float(xs.min()), float(ys.min()), float(zs.min())],
                [float(xs.max()), float(ys.max()), float(zs.max())])
        contra = {"left": float(np.mean(p[np.asarray(xw) > 0] > 0)) if nz_support else 0.0,
                  "right": float(np.mean(p[np.asarray(xw) < 0] > 0)) if nz_support else 0.0}
        return dict(geometry_id=gid, hemisphere=hemi,
                    included_channel_count=n_inc, excluded_channel_count=n_exc,
                    probability_min=float(prob.min()), probability_max=float(prob.max()),
                    sum_probability_mass=mass, voxel_volume_mm3=voxel_vol,
                    weighted_volume_mm3=wvol, nonzero_support_voxels=nz_support,
                    weighted_centroid_mm=[cx, cy, cz], bounding_box_voxel=bb_v,
                    bounding_box_world_mm=bb_w, laterality_source="SOURCE_NATIVE_CHANNEL_IDENTITY",
                    laterality_expected=("x<0" if hemi == "left" else "x>0"),
                    contralateral_support_anomaly=contra,
                    max_probability=float(prob.max()))

    qL = geom_qc(left_g1, "left", len(included["left"]), len(excluded["left"]))
    qR = geom_qc(right_g1, "right", len(included["right"]), len(excluded["right"]))

    # Reticular excluded mass per side
    rmassL = float(left_r.sum())
    rmassR = float(right_r.sum())
    # all26 mass
    m26L = float(left_all26.sum())
    m26R = float(right_all26.sum())

    # bilateral QC
    ratio = qL["weighted_volume_mm3"] / qR["weighted_volume_mm3"] if qR["weighted_volume_mm3"] else float("nan")
    bilateral = dict(weighted_volume_ratio_L_over_R=ratio,
                     support_ratio_L_over_R=qL["nonzero_support_voxels"] / qR["nonzero_support_voxels"],
                     centroid_symmetry=dict(
                         L=[qL["weighted_centroid_mm"][0], qL["weighted_centroid_mm"][1], qL["weighted_centroid_mm"][2]],
                         R=[qR["weighted_centroid_mm"][0], qR["weighted_centroid_mm"][1], qR["weighted_centroid_mm"][2]]))

    # ---- write derived NIfTI (float32, same grid/affine as source) ----
    def write_nifti(prob, out, src_img):
        src_hdr = src_img.header
        hdr = nib.Nifti1Header()
        hdr.set_data_shape(prob.shape)
        hdr.set_zooms(list(src_hdr.get_zooms()[:3]))
        hdr.set_xyzt_units("mm", "sec")
        hdr.set_qform(src_img.get_qform(), code=int(src_hdr["qform_code"]))
        hdr.set_sform(src_img.get_sform(), code=int(src_hdr["sform_code"]))
        out_img = nib.Nifti1Image(prob.astype(np.float32), src_img.affine.copy(), header=hdr)
        nib.save(out_img, out)
        return sha256(out)

    left_out_sha = write_nifti(left_g1, OUT_LEFT_NIFTI, img)
    right_out_sha = write_nifti(right_g1, OUT_RIGHT_NIFTI, img)

    # ---- manifest ----
    manifest = dict(
        geometry_class="AUTHORITATIVE_DERIVED_G1_GEOMETRY",
        derivation="PROBABILITY_CHANNEL_SUM_FROM_FROZEN_SCOPE",
        space_status="SOURCE_NATIVE_ICBM2009C_SYMMETRIC",
        entries=[
            dict(geometry_id=GEOM_L, canonical_region_id=LID, hemisphere="left",
                 source_asset_id="FreeSurfer/Iglesias ThalamusProbs.MNIsymSpace",
                 source_path=str(RAW.relative_to(BACKEND)).replace("\\", "/"),
                 source_sha256=raw_sha,
                 channel_metadata_path=str(NAMES.relative_to(BACKEND)).replace("\\", "/"),
                 channel_metadata_sha256=names_sha,
                 scope_contract_id="THALAMUS_G1_SCOPE_CONTRACT_V3",
                 scope_contract_sha256=v3_sha,
                 probability_semantics="MUTUALLY_EXCLUSIVE_CATEGORICAL",
                 aggregation_operator="SUM",
                 included_channels=included["left"],
                 excluded_channels=excluded["left"],
                 background_channel=dict(channel_index=0, official_name="Unknown",
                                         scope="EXCLUDE"),
                 derivation="PROBABILITY_CHANNEL_SUM_FROM_FROZEN_SCOPE",
                 threshold_applied=False, binarization_applied=False,
                 clipping_applied=False, normalization_applied=False,
                 registration_applied=False, resampling_applied=False,
                 transform_id=None,
                 source_space="ICBM152_2009c_symmetric",
                 output_space="ICBM152_2009c_symmetric",
                 output_path=str(OUT_LEFT_NIFTI.relative_to(BACKEND)).replace("\\", "/"),
                 output_sha256=left_out_sha,
                 independent_from_g3_g1_mapping=True, circularity_risk="NONE",
                 script=str(Path(__file__).name), script_version=SCRIPT_VERSION,
                 run_timestamp=ts),
            dict(geometry_id=GEOM_R, canonical_region_id=RID, hemisphere="right",
                 source_asset_id="FreeSurfer/Iglesias ThalamusProbs.MNIsymSpace",
                 source_path=str(RAW.relative_to(BACKEND)).replace("\\", "/"),
                 source_sha256=raw_sha,
                 channel_metadata_path=str(NAMES.relative_to(BACKEND)).replace("\\", "/"),
                 channel_metadata_sha256=names_sha,
                 scope_contract_id="THALAMUS_G1_SCOPE_CONTRACT_V3",
                 scope_contract_sha256=v3_sha,
                 probability_semantics="MUTUALLY_EXCLUSIVE_CATEGORICAL",
                 aggregation_operator="SUM",
                 included_channels=included["right"],
                 excluded_channels=excluded["right"],
                 background_channel=dict(channel_index=0, official_name="Unknown",
                                         scope="EXCLUDE"),
                 derivation="PROBABILITY_CHANNEL_SUM_FROM_FROZEN_SCOPE",
                 threshold_applied=False, binarization_applied=False,
                 clipping_applied=False, normalization_applied=False,
                 registration_applied=False, resampling_applied=False,
                 transform_id=None,
                 source_space="ICBM152_2009c_symmetric",
                 output_space="ICBM152_2009c_symmetric",
                 output_path=str(OUT_RIGHT_NIFTI.relative_to(BACKEND)).replace("\\", "/"),
                 output_sha256=right_out_sha,
                 independent_from_g3_g1_mapping=True, circularity_risk="NONE",
                 script=str(Path(__file__).name), script_version=SCRIPT_VERSION,
                 run_timestamp=ts),
        ],
        source=dict(shape=[138, 106, 94, 53], spacing_mm=0.5,
                    channel_count=53,
                    affine=img.affine.tolist(),
                    qform_code=int(img.header["qform_code"]),
                    sform_code=int(img.header["sform_code"]),
                    space="ICBM152_2009c_symmetric"),
        v3_scope=dict(contract_id="THALAMUS_G1_SCOPE_CONTRACT_V3", sha256=v3_sha,
                      decision_summary=dict(LGN="INCLUDE DEC-THAL-01", MGN="INCLUDE DEC-THAL-02",
                                            reticular="EXCLUDE DEC-THAL-03",
                                            limitans="INCLUDE DEC-THAL-04-LI",
                                            suprageniculate="INCLUDE DEC-THAL-04-SG",
                                            l_sg_channel="INCLUDE DEC-THAL-04-LSG")),
        reticular_exclusion_qc=dict(
            left=dict(all26_mass=m26L, g1_mass=float(left_g1.sum()), r_mass=rmassL,
                      max_abs_residual=float(np.abs(resL).max()),
                      mean_abs_residual=float(np.abs(resL).mean()),
                      nonzero_residual_voxels=int(np.count_nonzero(np.abs(resL) > 1e-5))),
            right=dict(all26_mass=m26R, g1_mass=float(right_g1.sum()), r_mass=rmassR,
                       max_abs_residual=float(np.abs(resR).max()),
                       mean_abs_residual=float(np.abs(resR).mean()),
                       nonzero_residual_voxels=int(np.count_nonzero(np.abs(resR) > 1e-5)))),
        atlas_conservation=dict(background_plus_52_nuclei=bg_stats),
        qc_left=qL, qc_right=qR, bilateral_qc=bilateral,
        julich_readiness=dict(direct_g4_overlap_ready=False,
                              transform_required="SYMMETRIC_TO_ASYMMETRIC_TEMPLATE_TRANSFORM_REQUIRED",
                              note="native geometry is NOT Julich-ready; Sym->Asym transform is a LATER round"),
    )
    with open(OUT_MANIFEST, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=2)

    # ---- QC csv ----
    qc_rows = []
    for tag, q, rmass, allm in (("left", qL, rmassL, m26L), ("right", qR, rmassR, m26R)):
        qc_rows.append(dict(
            side=tag, geometry_id=q["geometry_id"],
            included_channel_count=q["included_channel_count"],
            excluded_channel_count=q["excluded_channel_count"],
            probability_min=q["probability_min"], probability_max=q["probability_max"],
            sum_probability_mass=q["sum_probability_mass"],
            voxel_volume_mm3=q["voxel_volume_mm3"], weighted_volume_mm3=q["weighted_volume_mm3"],
            nonzero_support_voxels=q["nonzero_support_voxels"],
            centroid_x_mm=q["weighted_centroid_mm"][0],
            centroid_y_mm=q["weighted_centroid_mm"][1],
            centroid_z_mm=q["weighted_centroid_mm"][2],
            laterality_source=q["laterality_source"], laterality_expected=q["laterality_expected"],
            reticular_excluded_mass=rmass, all26_mass=allm,
            all26_minus_g1_plus_r_max_abs_residual=(float(np.abs(resL).max()) if tag == "left"
                                                    else float(np.abs(resR).max())),
            output_sha256=(left_out_sha if tag == "left" else right_out_sha)))
    with open(OUT_QC, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(qc_rows[0].keys()))
        w.writeheader()
        for r in qc_rows:
            w.writerow(r)

    # ---- diagnostics md ----
    md = [
        "# Phase1.7 V3 - THALAMUS_PROPER G1 native-space reference geometry",
        "",
        f"source = {RAW.name}  (ICBM152 2009c symmetric, 138x106x94 @0.5mm, 53 ch)",
        f"source_sha256 = {raw_sha}",
        f"names_sha256 = {names_sha}",
        f"scope_contract = THALAMUS_G1_SCOPE_CONTRACT_V3  sha {v3_sha}",
        f"left  included={qL['included_channel_count']} excluded={qL['excluded_channel_count']}  (Reticular R excluded)",
        f"right included={qR['included_channel_count']} excluded={qR['excluded_channel_count']}  (Reticular R excluded)",
        f"aggregation = SUM of included probability channels (MUTUALLY_EXCLUSIVE_CATEGORICAL)",
        "no MAX / union / threshold / binarization / clipping / normalization",
        f"left  weighted_volume_mm3 = {qL['weighted_volume_mm3']:.3f}  support={qL['nonzero_support_voxels']}",
        f"right weighted_volume_mm3 = {qR['weighted_volume_mm3']:.3f}  support={qR['nonzero_support_voxels']}",
        f"left  centroid_mm = {qL['weighted_centroid_mm']}",
        f"right centroid_mm = {qR['weighted_centroid_mm']}",
        f"reticular exclusion (all26 == G1 + R): left max|res|={float(np.abs(resL).max()):.3e} "
        f"right max|res|={float(np.abs(resR).max()):.3e}",
        f"atlas conservation bg+52nuclei: min={bg_stats['min']:.4f} mean={bg_stats['mean']:.4f} "
        f"p99={bg_stats['p99']:.4f} max={bg_stats['max']:.4f}",
        f"output grid == source grid (138x106x94); output affine == source affine (no registration/resampling)",
        f"independent_from_g3_g1_mapping = TRUE; circularity_risk = NONE",
        f"direct_g4_overlap_ready = FALSE; transform_required = "
        "SYMMETRIC_TO_ASYMMETRIC_TEMPLATE_TRANSFORM_REQUIRED",
        f"left output_sha256  = {left_out_sha}",
        f"right output_sha256 = {right_out_sha}",
        "derived NIfTI are local only (NOT committed, per derived_g1 policy)",
        "no DB write; no commit; no Sym->Asym transform; classification/DB untouched", "",
    ]
    with open(OUT_MD, "w", encoding="utf-8") as fh:
        fh.write("\n".join(md) + "\n")

    print("left  included", qL["included_channel_count"], "excluded", qL["excluded_channel_count"])
    print("right included", qR["included_channel_count"], "excluded", qR["excluded_channel_count"])
    print("left  wvol_mm3", round(qL["weighted_volume_mm3"], 3), "centroid", qL["weighted_centroid_mm"])
    print("right wvol_mm3", round(qR["weighted_volume_mm3"], 3), "centroid", qR["weighted_centroid_mm"])
    print("left  out sha", left_out_sha)
    print("right out sha", right_out_sha)
    print("bg+52 conservation", {k: round(bg_stats[k], 4) for k in ("min", "mean", "p99", "max")})


if __name__ == "__main__":
    main()
