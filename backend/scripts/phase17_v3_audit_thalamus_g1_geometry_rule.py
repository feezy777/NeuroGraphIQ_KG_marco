"""Phase1.7 V3 - FreeSurfer Thalamus probability semantics + whole-thalamus
G1 aggregation rule AUDIT (READ-ONLY; no geometry construction).

Determines what each channel of ThalamusProbs.MNIsymSpace.nii.gz means and
whether a whole-thalamus G1 aggregation rule may be frozen. NO left/right
thalamus geometry is produced. No Sym->Asym transform / resample / registration /
overlap / DB write / commit.

Probability semantics determination is DATA + official-source driven:
  - official: Iglesias et al. 2018 NeuroImage (arXiv:1806.08634): 26 nuclei,
    Bayesian inference on whole-thalamus + surroundings.
  - shipped names.txt (same zip) is the authoritative per-channel metadata.
  - real header data: sum over ALL 53 channels == 1.0 at every voxel =>
    mutually-exclusive categorical / normalized posterior (softmax-like) model,
    NOT independent overlapping maps, NOT frequency-only maps.

Top-level high-level verdict (layered statuses live in the summary):
  GEOMETRY_RULE_BLOCKED_BY_ONTOLOGY_SCOPE
Layers:
  probability_aggregation_semantics = RESOLVED  (operator = SUM)
  channel metadata = RESOLVED  (53 = 1 background + 52 nuclei)
  laterality = RESOLVED (26L + 26R)
  spatial = SOURCE/TARGET IDENTIFIED (no transform)
  ontology scope = UNRESOLVED / ONTOLOGY_SCOPE_INCOMPLETE
  geometry construction = BLOCKED
"""
from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import nibabel as nib
import numpy as np

BACKEND = Path(__file__).resolve().parents[1]
D16 = BACKEND / "data" / "integration" / "brainregion_direct_g1_phase16"
RAW = BACKEND / "data" / "atlases" / "external_raw" / "freesurfer_icbm2009c" / "thalamus"
SRC = RAW / "ThalamusProbs.MNIsymSpace.nii.gz"
NAMES = RAW / "ThalamusProbs.MNIsymSpace.names.txt"

OUT_SEM = D16 / "phase17_v3_thalamus_probability_semantics_audit.csv"
OUT_CH = D16 / "phase17_v3_thalamus_channel_scope_audit.csv"
OUT_AGG = D16 / "phase17_v3_thalamus_aggregation_comparison.csv"
OUT_JSON = D16 / "phase17_v3_thalamus_geometry_rule_summary.json"
OUT_MD = D16 / "phase17_v3_thalamus_geometry_rule_diagnostics.md"
FROZEN_ACQ = D16 / "phase17_v3_external_g1_asset_manifest.csv"

CANON = {
    "Left": dict(g1_region_id="NGIQ-BR-00000247", canonical_name="Left Thalamus"),
    "Right": dict(g1_region_id="NGIQ-BR-00000256", canonical_name="Right Thalamus"),
}
SCRIPT_VERSION = "phase17_v3_audit_thalamus_g1_geometry_rule.py v1"


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        while True:
            b = fh.read(1 << 20)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def load_names() -> list[str]:
    """names.txt rows: 'id,label'. Channel index = row index (0..n-1)."""
    out = []
    with open(NAMES, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            parts = line.split(",")
            out.append(parts[1] if len(parts) > 1 else parts[0])
    return out


def qstats(v: np.ndarray) -> dict:
    v = v.astype(np.float64).ravel()
    return dict(min=float(v.min()), mean=float(v.mean()),
                median=float(np.median(v)), p90=float(np.percentile(v, 90)),
                p95=float(np.percentile(v, 95)), p99=float(np.percentile(v, 99)),
                max=float(v.max()))


def main() -> None:
    # ---- 0. freeze + header ----
    im = nib.load(SRC)
    names = load_names()
    nch = im.shape[3]
    if len(names) != nch:
        raise SystemExit(f"FAIL: names.txt rows {len(names)} != channels {nch}")
    arr = im.get_fdata(dtype=np.float64)             # (X,Y,Z,C) float64
    src_sha = sha256(SRC)
    names_sha = sha256(NAMES)
    hd = im.header
    header = dict(shape=list(im.shape), zooms=[float(x) for x in hd.get_zooms()],
                  affine=[float(x) for x in im.affine.ravel()],
                  orientation="".join(nib.aff2axcodes(im.affine)),
                  qform_code=int(hd["qform_code"]), sform_code=int(hd["sform_code"]),
                  raw_dtype="float32", computed_dtype=str(arr.dtype))
    # freeze check vs acquisition manifest
    frozen = {}
    with open(FROZEN_ACQ, encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh):
            frozen[r["asset_id"]] = r
    frow = frozen.get("FS_THAL_ICBM", {})
    freeze_ok = (frow.get("checksum") == src_sha)
    if not freeze_ok:
        raise SystemExit("FAIL: raw sha256 != frozen acquisition manifest checksum")

    # ---- 1. per-channel provenance + laterality (geometry cross-check) ----
    aff = im.affine
    shp = arr.shape[:3]
    I, J, K = np.meshgrid(np.arange(shp[0]), np.arange(shp[1]), np.arange(shp[2]),
                          indexing="ij")
    xyz = nib.affines.apply_affine(aff, np.stack([I, J, K], axis=-1))
    Xw = xyz[..., 0]
    # channel identity from official names
    ch_rows = []
    L_idx, R_idx, BG_idx = [], [], []
    for c in range(nch):
        lbl = names[c]
        v = arr[..., c]
        m = v > 0
        cx = float((Xw[m] * v[m]).sum() / v[m].sum()) if m.sum() else float("nan")
        side = "Left" if lbl.startswith("Left") else ("Right" if lbl.startswith("Right") else "Background/Unknown")
        if side == "Left":
            L_idx.append(c)
        elif side == "Right":
            R_idx.append(c)
        else:
            BG_idx.append(c)
        ch_rows.append(dict(channel_index=c, source_label=lbl, official_name=lbl,
                            hemisphere=side, centroid_x=round(cx, 3) if not np.isnan(cx) else "",
                            include_candidate=""))
    # laterality QC: Left channels x<0, Right x>0
    lat_bad = [r for r in ch_rows
               if r["hemisphere"] == "Left" and r["centroid_x"] and r["centroid_x"] > 0]
    lat_bad += [r for r in ch_rows
                if r["hemisphere"] == "Right" and r["centroid_x"] and r["centroid_x"] < 0]
    laterality_ok = not lat_bad and len(L_idx) == len(R_idx) and len(BG_idx) == 1
    nL, nR, nBG = len(L_idx), len(R_idx), len(BG_idx)

    # ---- 2. probability semantics ----
    Sall = arr.sum(axis=3)                 # sum over all 53
    SL = arr[..., L_idx].sum(axis=3)
    SR = arr[..., R_idx].sum(axis=3)
    Snuc = SL + SR
    Sbg = arr[..., BG_idx[0]]              # channel 0 = Unknown
    res = 1.0 - Snuc
    tol = 1e-6
    sem = {
        "sum_all_channels": qstats(Sall),
        "sum_nucleus_channels_LR": qstats(Snuc),
        "sum_left_channels": qstats(SL),
        "sum_right_channels": qstats(SR),
        "background_channel": qstats(Sbg),
        "S_all_min_within_1e-5": float(np.max(np.abs(Sall - 1.0))) < 1e-5,
        "frac_S_all_eq1": float(np.mean(np.abs(Sall - 1.0) < tol)),
        "frac_S_nuc_gt1": float(np.mean(Snuc > 1.0 + tol)),
        "frac_S_nuc_eq1": float(np.mean(np.abs(Snuc - 1.0) < tol)),
        "frac_0_lt_Snuc_lt_1": float(np.mean((Snuc > tol) & (Snuc < 1.0 - tol))),
        "frac_Snuc_eq0": float(np.mean(Snuc == 0.0)),
        "bg_eq_1_minus_nuc_frac": float(np.mean(np.abs(Sbg - res) < 1e-3)),
        "bg_lt_half_frac_LRsum_eq1": float(np.mean(np.abs((SL + SR) - 1.0)[Sbg < 0.5] < 1e-2))
        if int((Sbg < 0.5).sum()) else None,
        "n_lowbg_voxels": int((Sbg < 0.5).sum()),
        "interpretation": "MUTUALLY_EXCLUSIVE_CATEGORICAL_NORMALIZED_POSTERIOR",
        "evidence": "sum over all 53 channels == 1.0 at every voxel; background ch0 == "
                    "1 - sum(nuclei); consistent with Iglesias 2018 Bayesian label model",
    }

    # ---- 3. background / missing-probability diagnosis ----
    # residual where S<1 (nucleus channels only) is carried by the explicit
    # background channel -> not missing, it is a modeled 'not one of 26 nuclei' class
    bg_diag = dict(
        n_bg_gt_half=int((Sbg > 0.5).sum()), frac_bg_gt_half=float((Sbg > 0.5).mean()),
        n_lowbg=int((Sbg < 0.5).sum()),
        frac_lowbg_LR_sum_eq1=float(np.mean(np.abs((SL + SR) - 1.0)[Sbg < 0.5] < 1e-2)),
        note="channel 0 'Unknown' is the explicit complement (not missing mass): "
             "sum over ALL 53 channels == 1 at every voxel. Where bg<0.5 yet "
             "L-channel+R-channel sum is not ~1, the remainder is the background "
             "channel itself in the 0<bg<0.5 range (partial-volume / model "
             "uncertainty), not a leak and not cross-hemisphere mass.",
    )

    # ---- 4. whole-thalamus aggregation operator comparison (audit only) ----
    # candidate inclusion set for a 'whole-thalamus' geometry under the categorical
    # model: sum over the 26 nucleus channels of the hemisphere = P(voxel in one of
    # the modeled nuclei). Compare operators over the union support.
    def op_stats(Snuc, mask, name):
        # mask: voxels where Snuc>0 (union support of included channels)
        sup = mask
        if sup.sum() == 0:
            return dict(name=name, n_support=0)
        p = Snuc[sup]
        wv = p.sum() * float(abs(np.linalg.det(aff[:3, :3])))
        return dict(name=name, n_support=int(sup.sum()),
                    value_min=float(p.min()), value_max=float(p.max()),
                    mass=float(p.sum()), weighted_volume_mm3=float(wv))

    cmp_rows = []
    for hemi, Sel in (("Left", L_idx), ("Right", R_idx)):
        P = arr[..., Sel]                   # (X,Y,Z,26)
        Ssum = P.sum(axis=3)
        Smax = P.max(axis=3)
        Sunion = 1.0 - np.prod(1.0 - P, axis=3)
        Sclip = np.minimum(1.0, Ssum)
        union_mask = Ssum > 0
        for nm, V in (("SUM", Ssum), ("MAX", Smax),
                      ("PROBABILISTIC_UNION", Sunion), ("CLIPPED_SUM", Sclip)):
            st = op_stats(V, union_mask, nm)
            st["hemisphere"] = hemi
            cmp_rows.append(st)

    # ---- 5. inclusion scope audit (per channel) ----
    # anatomical groups per official FS label. Because channel-0 'Unknown' is
    # background and every modeled nucleus is inside the whole-thalamus manual
    # segmentation, include_candidate is set per group with ontology_review where
    # the current G1 boundary is ambiguous (habenula not present; transition/border).
    group = {
        "LGN": ("metathalamus/geniculate", True), "MGN": ("metathalamus/geniculate", True),
        "PuI": ("pulvinar", True), "PuM": ("pulvinar", True), "PuL": ("pulvinar", True),
        "PuA": ("pulvinar", True), "L-Sg": ("posterior/limitans-sg", True),
        "VPL": ("ventral", True), "VLa": ("ventral", True), "VLp": ("ventral", True),
        "VA": ("ventral", True), "VAmc": ("ventral", True), "VM": ("ventral", True),
        "CM": ("intralaminar", True), "CL": ("intralaminar", True),
        "Pc": ("intralaminar", True), "Pf": ("intralaminar", True),
        "MDm": ("mediodorsal", True), "MDl": ("mediodorsal", True),
        "CeM": ("midline", True), "MV(Re)": ("midline/reuniens", True),
        "R": ("reticular", True), "AV": ("anterior", True),
        "LP": ("posterior/lateral-posterior", True), "LD": ("posterior/laterodorsal", True),
        "Pt": ("paratenial", True),
    }
    # FS official label base names (strip Left/Right prefix)
    for r in ch_rows:
        lbl = r["source_label"]
        base = lbl.replace("Left-", "").replace("Right-", "")
        if base in ("Unknown", ""):
            r["hemisphere"] = "Background/Unknown"
            r["anatomical_group"] = "background/non-nucleus"
            r["include_candidate"] = "exclude(background)"
            r["ontology_review"] = "not a nucleus"
            r["justification"] = "channel 0 is the complement 'not one of 26 nuclei' class"
            continue
        grp, inside = group.get(base, ("UNKNOWN", False))
        r["anatomical_group"] = grp
        if not inside:
            r["include_candidate"] = "exclude(unknown_anatomy)"
            r["ontology_review"] = "METADATA_INCOMPLETE"
            r["justification"] = "no official FreeSurfer label mapping found"
            continue
        r["include_candidate"] = f"include_{r['hemisphere'].lower()}_whole_thalamus_candidate"
        r["ontology_review"] = ("whole-thalamus boundary ok" if grp != "transition/border"
                                else "review")
        r["justification"] = (f"inside Iglesias2018 whole-thalamus manual segmentation; "
                              f"group={grp}; nucleus of the dorsal/ventral/metathalamus")

    # write semantics + channel CSVs
    with open(OUT_SEM, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["metric", "value"])
        for k, v in sem.items():
            w.writerow([k, json.dumps(v, ensure_ascii=False) if not isinstance(v, (int, float, str)) else v])
    ch_cols = ["channel_index", "source_label", "official_name", "hemisphere",
               "anatomical_group", "centroid_x", "include_candidate",
               "ontology_review", "justification"]
    with open(OUT_CH, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=ch_cols, extrasaction="ignore")
        w.writeheader()
        for r in ch_rows:
            w.writerow(r)
    with open(OUT_AGG, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=list(cmp_rows[0].keys()))
        w.writeheader()
        for r in cmp_rows:
            w.writerow(r)

    # ---- 6. verdict ----
    # Evidence gates first. A mutually-exclusive categorical posterior requires
    # sum(all 53 channels) == 1 (tol) AND laterality coherence. If either fails,
    # the verdict must not claim the categorical model at all.
    sem_categorical = (sem["frac_S_all_eq1"] > 0.9999
                       and sem["bg_eq_1_minus_nuc_frac"] > 0.9999)
    if not sem_categorical or not laterality_ok:
        raise SystemExit("FAIL: categorical-posterior evidence or laterality QC failed; "
                         "cannot derive any aggregation operator recommendation")
    # ---- LAYERED status (do NOT collapse all layers into one UNRESOLVED) ----
    # Under a categorical (disjoint-latent-class) model, once the set S of nucleus
    # channels included in the whole-thalamus G1 is fixed, P(Thalamus) = sum_{i in S} P_i.
    # That probability-layer semantics is RESOLVED and the operator is SUM. The
    # PROBABILISTIC_UNION (1-prod(1-P_i)) is an independent-Bernoulli quantity and is
    # measured ~15% BELOW SUM (not equal); MAX likewise undercounts -> both NOT valid.
    # CLIPPED_SUM equals SUM numerically and is not a separate operator here.
    #
    # What remains UNRESOLVED is ONLY the ontology scope: which nucleus channels belong
    # to the current G1 Thalamus (Macro96 'thalamus proper' text vs the Brainnetome G3
    # whole-thalamus rollup that actually populates NGIQ-BR-00000247/56). Reconciling
    # 'whole' vs 'proper' needs spatial geometry this read-only round must not build.
    probability_aggregation_semantics = "RESOLVED"
    probability_aggregation_operator = "SUM"
    aggregation_rule_status = "FROZEN_AT_PROBABILITY_LAYER"
    g1_scope_status = "ONTOLOGY_SCOPE_INCOMPLETE"
    geometry_construction_status = "BLOCKED_BY_ONTOLOGY_SCOPE"
    construction_allowed = False
    verdict = "GEOMETRY_RULE_BLOCKED_BY_ONTOLOGY_SCOPE"
    rationale = (
        "Probability layer RESOLVED: data proves a mutually-exclusive categorical "
        "normalized posterior (sum over all 53 channels == 1.0 at every voxel; "
        "background ch0 == 1 - sum(nuclei)). Therefore for any fixed included set S of "
        "whole-Thalamus nucleus channels, P_Thalamus(x) = sum_{i in S} P_i(x) -> "
        "operator = SUM (identical to CLIPPED_SUM; MAX and PROBABILISTIC_UNION are NOT "
        "valid: UNION is an independent-Bernoulli product measured ~15% below SUM). "
        "Aggregation rule is FROZEN AT THE PROBABILITY LAYER only. Geometry construction "
        "is BLOCKED because the G1 ontology scope is INCOMPLETE: the Macro96 label reads "
        "'thalamus proper' while the frozen G1 target is populated as the Brainnetome G3 "
        "whole-thalamus rollup (8 parcels/hemisphere); which nucleus channels (incl. "
        "LGN/MGN/reticular/border) are INCLUDED_CHANNELS is not yet frozen and cannot be "
        "resolved in this read-only round without spatial geometry. No geometry is built "
        "until INCLUDED_CHANNELS is frozen."
    )

    # ---- 7. provenance chain + summary ----
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    summary = dict(
        verdict=verdict, verdict_rationale=rationale,
        probability_aggregation_semantics=probability_aggregation_semantics,
        probability_aggregation_operator=probability_aggregation_operator,
        aggregation_rule_status=aggregation_rule_status,
        g1_scope_status=g1_scope_status,
        geometry_construction_status=geometry_construction_status,
        construction_allowed=construction_allowed,
        # SUM applicability condition is explicit
        sum_applicability=("SUM applies only to the mutually-exclusive nucleus channels "
                           "included in the same G1 Thalamus once INCLUDED_CHANNELS is "
                           "frozen: P_G1(x)=sum_i P_i(x), i in INCLUDED_CHANNELS. MAX: not "
                           "applicable. PROBABILISTIC_UNION: not applicable (not "
                           "independent Bernoulli). CLIPPED_SUM: numerically == SUM here; "
                           "not a separate operator."),
        canonical=dict(Left=CANON["Left"], Right=CANON["Right"]),
        g1_ontology_scope=("Macro96 pool label 'left/right thalamus proper' (AAL3-derived); "
                           "frozen G1 target NGIQ-BR-00000247/56 populated as whole-thalamus "
                           "rollup of Brainnetome G3 Tha_*_8_1..8_8 (AUTO_HIGH). Scope text "
                           "'proper' vs rollup 'whole' not spatially reconciled => "
                           "ONTOLOGY_SCOPE_INCOMPLETE; geometry BLOCKED"),
        source=dict(asset_id="FS_THAL_ICBM", file=SRC.name, sha256=src_sha,
                    names_file=NAMES.name, names_sha256=names_sha,
                    local_path=str(SRC.relative_to(BACKEND)).replace("\\", "/"),
                    atlas="FreeSurfer SubfieldAtlasesICBMspace Thalamus (Iglesias 2018)",
                    atlas_version="ICBM 2009c symmetric release",
                    paper="Iglesias et al. 2018 NeuroImage (arXiv:1806.08634)",
                    doi="10.1016/j.neuroimage.2018.08.012",
                    official_source="surfer.nmr.mgh.harvard.edu/fswiki/SubfieldAtlasesICBMspace",
                    channel_metadata_source="ThalamusProbs.MNIsymSpace.names.txt (same zip)"),
        header=header, n_channels=nch, n_left=L_idx, n_right=R_idx, n_background=BG_idx,
        channel_count_expected=53, channel_count_actual=nch,
        channel_count_match=(nch == 53),
        laterality=dict(ok=laterality_ok, left_channels=nL, right_channels=nR,
                        background_channels=nBG, mismatches=[r["source_label"] for r in lat_bad]),
        semantics=sem, background_diagnosis=bg_diag,
        aggregation_comparison=cmp_rows,
        coordinate_relation=dict(
            source_space="MNI-ICBM 152 2009c symmetric", target_space="MNI152NLin2009cAsym",
            source_grid="138x106x94 @0.5mm", target_grid="193x229x193 @1mm",
            template_variant_difference="SYMMETRIC_VS_ASYMMETRIC",
            relation="SYMMETRIC_TO_ASYMMETRIC_TEMPLATE_TRANSFORM_REQUIRED",
            transform_executed=False, resampling_executed=False),
        flags=dict(threshold_applied=False, binarization_applied=False,
                   registration_applied=False, resampling_applied=False,
                   geometry_constructed=False),
        provenance_chain=[
            "Iglesias 2018 official paper (26 nuclei, Bayesian)",
            "FS wiki ThalamicNuclei / SubfieldAtlasesICBMspace",
            f"raw sha256 {src_sha}",
            "names.txt channel metadata (same release zip)",
            "data-verified categorical posterior (sum==1)",
            "inclusion/exclusion per channel table",
            "aggregation operator audit (SUM/MAX/UNION/CLIP)",
            "verdict = GEOMETRY_RULE_BLOCKED_BY_ONTOLOGY_SCOPE "
            "(probability layer RESOLVED / SUM; ontology scope INCOMPLETE)",
        ],
        doi_correction=dict(
            old_value="10.1016/j.neuroimage.2018.06.012",
            corrected_value="10.1016/j.neuroimage.2018.08.012",
            reason=("2018.06.012 is not the Iglesias thalamic-nuclei atlas DOI; the "
                    "correct DOI for Iglesias et al., 'A probabilistic atlas of the "
                    "human thalamic nuclei combining ex vivo MRI and histology', "
                    "NeuroImage 183 (2018):314-326 is 2018.08.012"),
            source="official NeuroImage record / publisher page",
            correction_date=ts,
            applies_to="living manifest + this audit metadata only; historical frozen "
                       "snapshots are superseded, not rewritten"),
        script=SCRIPT_VERSION, construction_timestamp=ts,
    )
    with open(OUT_JSON, "w", encoding="utf-8") as fh:
        json.dump(summary, fh, ensure_ascii=False, indent=2)

    md = ["# Phase1.7 V3 - Thalamus probability semantics + aggregation rule audit", "",
          f"verdict = {verdict}",
          f"probability_aggregation_semantics = {probability_aggregation_semantics}",
          f"probability_aggregation_operator = {probability_aggregation_operator}",
          f"aggregation_rule_status = {aggregation_rule_status}",
          f"g1_scope_status = {g1_scope_status}",
          f"geometry_construction_status = {geometry_construction_status}",
          f"construction_allowed = {construction_allowed}",
          "sum_applicability: " + summary["sum_applicability"],
          "semantics = " + sem["interpretation"],
          f"channels = {nch} (expected 53)  L={nL} R={nR} bg={nBG}",
          f"raw sha256 = {src_sha}  freeze_match={freeze_ok}",
          "Iglesias DOI (corrected) = 10.1016/j.neuroimage.2018.08.012",
          "Julich reference shape = 193 x 229 x 193 (1 mm)",
          f"sum(all 53 channels): min/median/max = "
          f"{sem['sum_all_channels']['min']}/{sem['sum_all_channels']['median']}/"
          f"{sem['sum_all_channels']['max']}",
          f"frac S_nuc >1 = {sem['frac_S_nuc_gt1']:.5f}  frac S_nuc ==1 = {sem['frac_S_nuc_eq1']:.5f}",
          f"frac S_nuc ==0 = {sem['frac_Snuc_eq0']:.5f}",
          f"background==1-sum(nuc) frac = {sem['bg_eq_1_minus_nuc_frac']:.5f}",
          f"laterality QC ok = {laterality_ok}",
          f"no geometry constructed; construction BLOCKED by ontology scope (INCLUDED_"
          "CHANNELS not frozen); SUM is the frozen probability-layer operator", "",
          "provenance:", *["- " + x for x in summary["provenance_chain"]], "",
          "DOI correction:", f"- old={summary['doi_correction']['old_value']} -> "
          f"new={summary['doi_correction']['corrected_value']} "
          f"({summary['doi_correction']['reason']})", ""]
    with open(OUT_MD, "w", encoding="utf-8") as fh:
        fh.write("\n".join(md) + "\n")

    print("channels", nch, "L", nL, "R", nR, "bg", nBG, "freeze_ok", freeze_ok)
    print("semantics", sem["interpretation"], "verdict", verdict)
    print("Sall", sem["sum_all_channels"])
    print("frac nuc>1", sem["frac_S_nuc_gt1"], "nuc==1", sem["frac_S_nuc_eq1"], "nuc==0", sem["frac_Snuc_eq0"])
    print("laterality ok", laterality_ok)


if __name__ == "__main__":
    main()
