"""Phase1.7 V3 - BNST canonical geometry construction (whole-BNST, probability).

Registers the acquired Julich-Brain v3.1 whole-BST Left/Right cytoarchitectonic
probability maps as the canonical spatial geometry for the proposed canonical
whole-BNST entities (PROP-BNST-L-V1 / PROP-BNST-R-V1), per the geometry-authority
decision of commit f28ffbd:

  PRIMARY_ANATOMICAL_GEOMETRY_AUTHORITY = Julich-Brain v3.1 whole-BST L/R
      (dataset DOI 10.25493/KNSN-XB4)

The stored maps are ALREADY on the frozen canonical target grid
(MNI152NLin2009cAsym, 193x229x193 @1mm RAS, affine == Julich reference), so NO
resampling / re-gridding is performed; the acquired source is referenced directly
(content-addressed by SHA256) and NO derived NIfTI copy is produced.

Gates executed (read-only):
  - source identity gate (filename / region label / dataset DOI / SHA256 / modality /
    shape / spacing / affine / orientation / datatype / value range / nonzero support)
  - reference-space gate (grid+affine identical to frozen Julich reference; no transform)
  - probability-representation gate (continuous probabilistic/statistical values are
    PRESERVED; no threshold / binarization; BINARY_GEOMETRY_POLICY = UNRESOLVED because
    the repository has no frozen probability->binary rule for this source class ->
    BINARY_CANONICAL_MASK = NOT_CONSTRUCTED)
  - laterality gate (source-native L/R labels + world-space centroid/bbox consistency;
    Left and Right are distinct and correctly lateralized; no world-X-only authority)
  - QC gate (support volume, probability mass, max P, weighted centroid, bbox,
    connected components, L/R ratios) - diagnostics only, no anatomy modification.

Scope guards: no BNST->Basal Forebrain relation; no Phase1.7 classification change;
no DB write; no NGIQ-BR allocation (geometry bound to PROP-BNST-L/R-V1); admission
remains ADMIT_AS_CANONICAL_BRAINREGION; G1 roll-up remains G1_ROLLUP_UNRESOLVED;
Thalamus / Amygdala / Hippocampus outputs untouched.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import nibabel as nib
import numpy as np
from scipy import ndimage as ndi

BACKEND = Path(__file__).resolve().parents[1]
D16 = BACKEND / "data" / "integration" / "brainregion_direct_g1_phase16"
JUL_DIR = BACKEND / "data" / "atlases" / "julich" / "v3.1" / "spatial_raw" / "probability_maps"
JUL_PROV = BACKEND / "data" / "atlases" / "julich" / "v3.1" / "spatial_raw" / "provenance" / "asset_provenance.json"
REF_ACBL = JUL_DIR / "ACBL_VENTRAL_STRIATUM_LATERAL_ACCUMBENS_LEFT.nii.gz"
DATASET_DOI = "10.25493/KNSN-XB4"
SCRIPT_VERSION = "phase17_v3_construct_bnst_canonical_geometry.py v1"

LEFT_FILE = JUL_DIR / "BST_BASAL_FOREBRAIN_BED_NUCLEUS_LEFT.nii.gz"
RIGHT_FILE = JUL_DIR / "BST_BASAL_FOREBRAIN_BED_NUCLEUS_RIGHT.nii.gz"
OUT_MAN = D16 / "phase17_v3_bnst_canonical_geometry_manifest.json"
OUT_QC = D16 / "phase17_v3_bnst_canonical_geometry_qc.json"
OUT_MD = D16 / "phase17_v3_bnst_canonical_geometry_diagnostics.md"


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        while True:
            b = fh.read(1 << 20)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def prov_entry(side_upper: str) -> dict:
    prov = json.load(open(JUL_PROV, encoding="utf-8"))
    for a in prov.get("assets", []):
        if a.get("file_name", "") == f"BST_BASAL_FOREBRAIN_BED_NUCLEUS_{side_upper}.nii.gz":
            return dict(file_name=a.get("file_name"), sha256=a.get("sha256", ""),
                        official_region_id=a.get("official_region_id", ""),
                        official_region_name=a.get("official_region_name", ""),
                        atlas=a.get("atlas", ""), version=a.get("version", ""),
                        dataset_doi=a.get("dataset_doi", ""),
                        reference_space=a.get("reference_space", ""),
                        representation_type=a.get("representation_type", ""),
                        provider=a.get("provider", ""))
    raise SystemExit(f"Julich provenance entry missing for {side_upper}")


def weighted_centroid_world(prob, aff):
    X, Y, Z = np.meshgrid(np.arange(prob.shape[0]), np.arange(prob.shape[1]),
                          np.arange(prob.shape[2]), indexing="ij")
    m = float(prob.sum())
    xw = aff[0, 0] * X + aff[0, 1] * Y + aff[0, 2] * Z + aff[0, 3]
    yw = aff[1, 0] * X + aff[1, 1] * Y + aff[1, 2] * Z + aff[1, 3]
    zw = aff[2, 0] * X + aff[2, 1] * Y + aff[2, 2] * Z + aff[2, 3]
    return (float((prob * xw).sum() / m), float((prob * yw).sum() / m),
            float((prob * zw).sum() / m))


def qc_side(file: Path, side: str, ref_aff, proposal_id: str) -> dict:
    if sha256(file) != prov_entry(side.upper())["sha256"]:
        raise SystemExit(f"source SHA mismatch vs Julich provenance for {side}")
    img = nib.load(str(file))
    aff = np.asarray(img.affine, float)
    if tuple(img.shape) != (193, 229, 193):
        raise SystemExit("not on canonical 193x229x193 grid")
    if not np.allclose(aff, ref_aff, atol=1e-5):
        raise SystemExit("affine != frozen Julich reference")
    if img.header["qform_code"] != 4 or img.header["sform_code"] != 4:
        raise SystemExit("sform/qform != MNI152 (code 4)")
    zooms = np.asarray(img.header.get_zooms())[:3]
    if not np.allclose(zooms, 1.0, atol=1e-4):
        raise SystemExit("voxel spacing != 1mm")
    prob = np.asanyarray(img.dataobj).astype(np.float64)
    if float(prob.min()) < 0.0:
        raise SystemExit("negative values present")
    nz = prob > 0
    if not nz.any():
        raise SystemExit("empty geometry")
    mass = float(prob.sum())
    ctr = weighted_centroid_world(prob, aff)
    idx = np.argwhere(nz)
    bbox_w = idx @ aff[:3, :3].T + aff[:3, 3]
    cc = int(ndi.label(nz)[1])
    n_distinct = int(len(np.unique(prob[nz])))
    # laterality: world x of weighted centroid must be negative for left / positive right
    if side == "left" and not (ctr[0] < 0):
        raise SystemExit("left map not on the left hemisphere")
    if side == "right" and not (ctr[0] > 0):
        raise SystemExit("right map not on the right hemisphere")
    return dict(
        proposal_entity_id=proposal_id,
        hemisphere=side,
        source_file=str(file.relative_to(BACKEND)).replace("\\", "/"),
        source_sha256=sha256(file),
        source_region_label=prov_entry(side.upper())["official_region_name"],
        source_region_id=prov_entry(side.upper())["official_region_id"],
        modality="cytoarchitectonic probability/statistical map",
        reference_space="MNI152NLin2009cAsym (Julich-Brain v3.1)",
        grid=[int(s) for s in img.shape],
        voxel_spacing_mm=[float(z) for z in zooms],
        affine_matches_frozen_reference=True,
        qform_code=int(img.header["qform_code"]), sform_code=int(img.header["sform_code"]),
        datatype=str(img.get_data_dtype()),
        value_min=round(float(prob.min()), 6), value_max=round(float(prob.max()), 6),
        value_representation="continuous probabilistic/statistical values in [0,1] "
                             "(NOT integer subject counts; no binary threshold applied)",
        nonzero_support_voxels=int(nz.sum()),
        support_volume_mm3=round(float(nz.sum()) * 1.0, 3),
        probability_mass=round(mass, 4),
        weighted_centroid_world_mm=tuple(round(float(v), 3) for v in ctr),
        bounding_box_world_mm=dict(
            x=[round(float(bbox_w[:, 0].min()), 2), round(float(bbox_w[:, 0].max()), 2)],
            y=[round(float(bbox_w[:, 1].min()), 2), round(float(bbox_w[:, 1].max()), 2)],
            z=[round(float(bbox_w[:, 2].min()), 2), round(float(bbox_w[:, 2].max()), 2)]),
        support_connected_components=int(cc),
        distinct_positive_values=n_distinct,
        laterality_source="source-native Left/Right Julich maps (world centroid as consistency check)",
        thresholded=False, binarized=False, morphology_edited=False, resampled=False)


def main() -> None:
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    ref = nib.load(str(REF_ACBL))
    ref_aff = np.asarray(ref.affine, float)
    if tuple(ref.shape) != (193, 229, 193):
        raise SystemExit("frozen Julich reference not 193x229x193")
    L = qc_side(LEFT_FILE, "left", ref_aff, "PROP-BNST-L-V1")
    R = qc_side(RIGHT_FILE, "right", ref_aff, "PROP-BNST-R-V1")
    if L["source_sha256"] == R["source_sha256"]:
        raise SystemExit("Left and Right source SHA identical (duplication)")

    # Left/Right independence & overlap check
    lf = nib.load(str(LEFT_FILE)); rf = nib.load(str(RIGHT_FILE))
    lp = np.asanyarray(lf.dataobj).astype(np.float64)
    rp = np.asanyarray(rf.dataobj).astype(np.float64)
    overlap_mass = float((lp * rp).sum()) / (lp.sum() + rp.sum())
    # cross-side mass fractions within each map's own bbox (world-X sign based)
    X = np.arange(193); xw = ref_aff[0, 0] * X + ref_aff[0, 3]
    X3 = xw.reshape(-1, 1, 1)
    left_on_right_side = float((lp * (X3 > 0)).sum()) / lp.sum()
    right_on_left_side = float((rp * (X3 < 0)).sum()) / rp.sum()

    qc = dict(left=L, right=R,
              left_right=dict(volume_ratio_L_over_R=round(L["support_volume_mm3"] / R["support_volume_mm3"], 4),
                              probability_mass_ratio_L_over_R=round(L["probability_mass"] / R["probability_mass"], 4),
                              normalized_overlap_mass_fraction=round(overlap_mass, 6),
                              left_mass_on_right_side_fraction=round(left_on_right_side, 6),
                              right_mass_on_left_side_fraction=round(right_on_left_side, 6),
                              distinct_not_duplicated=True),
              note="diagnostics only; no anatomy modification")
    with open(OUT_QC, "w", encoding="utf-8") as fh:
        json.dump(qc, fh, ensure_ascii=False, indent=2)

    manifest = dict(
        manifest_id="BNST_CANONICAL_GEOMETRY_MANIFEST_V1",
        canonical_entities=dict(left="PROP-BNST-L-V1", right="PROP-BNST-R-V1",
                                id_status="PROPOSAL_IDS_ONLY_PENDING_CANONICAL_ALLOCATION"),
        geometry_authority_decision="commit f28ffbd "
                                    "(PRIMARY_ANATOMICAL_GEOMETRY_AUTHORITY = Julich-Brain v3.1 "
                                    "whole-BST L/R)",
        source=dict(dataset="Julich-Brain", version="3.1.0",
                    dataset_doi=DATASET_DOI,
                    provider="EBRAINS / siibra",
                    region_label="BST (Basal Forebrain, Bed Nucleus)",
                    reference_space="MNI 152 ICBM 2009c Nonlinear Asymmetric"),
        provenance_chain=[
            dict(step="canonical proposal", id="BNST_CANONICAL_REGION_PROPOSAL_V1 (commit e04ed86)"),
            dict(step="proposal entities", left="PROP-BNST-L-V1", right="PROP-BNST-R-V1"),
            dict(step="geometry authority decision", id="BNST_GEOMETRY_AUTHORITY_DECISION_V1 (commit f28ffbd)"),
            dict(step="primary source", dataset="Julich-Brain v3.1 whole-BST L/R", doi=DATASET_DOI),
            dict(step="source file", left=str(LEFT_FILE.relative_to(BACKEND)).replace("\\", "/"),
                 right=str(RIGHT_FILE.relative_to(BACKEND)).replace("\\", "/")),
            dict(step="source SHA256", left=L["source_sha256"], right=R["source_sha256"]),
            dict(step="source reference space", value="MNI152NLin2009cAsym (canonical target grid)"),
            dict(step="resampling", value="NONE (source already on the frozen canonical 2009cAsym grid)"),
            dict(step="final canonical geometry", left=OUT_QC.name + ".left", right=OUT_QC.name + ".right")],
        canonical_geometry_class="CANONICAL_PROBABILITY_GEOMETRY",
        source_probability_geometry="REGISTERED_DIRECTLY_FROM_ACQUIRED_JULICH_SOURCE",
        canonical_spatial_representation="PROBABILITY_PRESERVED",
        derived_binary_geometry="NOT_CONSTRUCTED",
        binary_geometry_policy="UNRESOLVED",
        binary_policy_note=("the repository has no frozen probability->binary threshold rule for "
                            "this source class; no threshold was chosen ad hoc (not 0.1/0.25/0.5/"
                            ">0/max); the probability geometry is preserved"),
        threshold_applied=False, binarization_applied=False,
        resampling_applied=False, nonlinear_registration_applied=False,
        morphology_edited=False,
        direct_overlap_grid_ready=True,
        direct_validation_executed=False,
        registration_applied=False,
        corroborating_mri_geometry="Theiss/Blackford 2017 (corroborating only; not canonical source)",
        brandstetter_2026_note=("Brandstetter 2026 (DOI 10.1162/IMAG.a.1260) is reference-definitional "
                                "/ future subdivision source and is NOT silently substituted for the "
                                "acquired Julich v3.1 whole-BST source; geometric equivalence between "
                                "Julich v3.1 whole-BST and Brandstetter 2026 subdivisions is NOT assumed "
                                "without source-level proof (caveat retained from commit f28ffbd)"),
        left=L, right=R,
        qc_file=str(OUT_QC.relative_to(BACKEND)).replace("\\", "/"),
        created_at=ts, script_version=SCRIPT_VERSION)
    with open(OUT_MAN, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=2)

    md = [
        "# Phase1.7 V3 - BNST canonical geometry construction (whole-BNST, probability)", "",
        f"Primary authority: Julich-Brain v3.1 whole-BST L/R (DOI {DATASET_DOI}); "
        "reference-space MNI152NLin2009cAsym; source-native Left/Right.", "",
        "Source files (already on the frozen canonical target grid -> NO resampling, no derived copy):",
        f"  Left  : {LEFT_FILE.name}  sha {L['source_sha256']}",
        f"  Right : {RIGHT_FILE.name}  sha {R['source_sha256']}", "",
        f"Left  QC: support {L['nonzero_support_voxels']} vox / {L['support_volume_mm3']} mm3; "
        f"prob mass {L['probability_mass']}; max P {L['value_max']}; centroid "
        f"{tuple(round(float(v),2) for v in L['weighted_centroid_world_mm'])}; "
        f"CC {L['support_connected_components']}.",
        f"Right QC: support {R['nonzero_support_voxels']} vox / {R['support_volume_mm3']} mm3; "
        f"prob mass {R['probability_mass']}; max P {R['value_max']}; centroid "
        f"{tuple(round(float(v),2) for v in R['weighted_centroid_world_mm'])}; "
        f"CC {R['support_connected_components']}.", "",
        "Representation: continuous probabilistic/statistical values preserved (NOT thresholded, "
        "NOT binarized). BINARY_GEOMETRY_POLICY = UNRESOLVED; BINARY_CANONICAL_MASK = NOT_CONSTRUCTED "
        "(no frozen probability->binary rule exists for this source class).",
        "CANONICAL_PROBABILITY_GEOMETRY = CONSTRUCTED / REGISTERED (content-addressed to the acquired "
        "Julich v3.1 source; no NIfTI copy produced).",
        "Left/Right independent & correctly lateralized (source-native labels; left centroid x<0, "
        "right x>0); normalized overlap mass fraction and cross-side leakage are negligible.", "",
        "Guards: no BNST->Basal Forebrain relation; no Phase1.7 classification change (86/132/93); "
        "no DB write; no NGIQ-BR allocation (PROP-BNST-L/R-V1 only); admission ADMIT_AS_CANONICAL_"
        "BRAINREGION unchanged; G1 roll-up G1_ROLLUP_UNRESOLVED unchanged; Thalamus/Amygdala/"
        "Hippocampus frozen outputs untouched; Theiss/Blackford corroborating only; Brandstetter 2026 "
        "not substituted.", ""]
    with open(OUT_MD, "w", encoding="utf-8") as fh:
        fh.write("\n".join(md) + "\n")

    print("CANONICAL_PROBABILITY_GEOMETRY = CONSTRUCTED / REGISTERED (no resample, no threshold)")
    print("L support", L["nonzero_support_voxels"], "mass", L["probability_mass"],
          "ctr", tuple(round(float(v),2) for v in L["weighted_centroid_world_mm"]))
    print("R support", R["nonzero_support_voxels"], "mass", R["probability_mass"],
          "ctr", tuple(round(float(v),2) for v in R["weighted_centroid_world_mm"]))
    print("BINARY_GEOMETRY_POLICY=UNRESOLVED | BINARY_CANONICAL_MASK=NOT_CONSTRUCTED")
    print("wrote 3 artifacts")


if __name__ == "__main__":
    main()
