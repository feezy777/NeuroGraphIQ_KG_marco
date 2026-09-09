"""Phase1.7 V3 - Correct laterality field semantics of the 170 direct-spatial evidence (V2).

Confirmed bug (a32e20e V1): column `correct_side_fraction` held
  side_ok = (fine & left_grid).sum() / fine_vox      == LEFT_HEMISPHERE_FRACTION
so for RIGHT-hemisphere rows it reported correct_side_fraction ~= 0 and
contralateral_fraction ~= 1, i.e. field semantics were wrong even though the ad-hoc
failure check (left needs left_frac>=0.9 / right needs left_frac<=0.1) still behaved.

This round ONLY fixes the laterality representation:
  left_fraction   = |fine & {RAS x<0}| / |fine|
  right_fraction  = 1 - left_fraction (grid has no exact-midline voxel centres)
  hemisphere==left :  correct_side_fraction = left_fraction,
                      contralateral_fraction = right_fraction
  hemisphere==right:  correct_side_fraction = right_fraction,
                      contralateral_fraction = left_fraction
laterality failure gate kept unchanged: correct_side_fraction < 0.90 -> LATERALITY_FAILURE.

HARD INVARIANT: all non-laterality scientific metrics (containment, rank, best/second/
best-non-proposed, margin, fine_voxels, outside-union, Dice, historical metadata, flags
except laterality) are copied BYTE-FOR-BYTE from the frozen V1 rows and a per-field diff is
emitted; any difference in a non-laterality field is an UNEXPECTED diff (must be 0).

a32e20e V1 history is preserved (not overwritten). No mapping / geometry / classification /
DB changes; no ontology adjudication.
"""
from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import nibabel as nib

BACKEND = Path(__file__).resolve().parents[1]
D16 = BACKEND / "data" / "integration" / "brainregion_direct_g1_phase16"
SCRIPT_VERSION = "phase17_v3_correct_cortical_direct_spatial_laterality_v2.py v1"
V1 = D16 / "phase17_v3_cortical_170_direct_spatial_evidence.csv"
UNIV = D16 / "phase17_v3_cortical_170_relation_universe.csv"
FINE_VOL = (BACKEND / "data/atlases/brainnetome/bna246/transformed_label_to_julich2009c/"
            "BN_Atlas_246_1mm_NLin6to2009c_labels.nii.gz")
OUT_V2 = D16 / "phase17_v3_cortical_170_direct_spatial_evidence_v2.csv"
OUT_CORR = D16 / "phase17_v3_cortical_direct_spatial_laterality_correction.json"
OUT_DIFF = D16 / "phase17_v3_cortical_direct_spatial_v1_v2_diff.csv"
OUT_PROV = D16 / "phase17_v3_cortical_direct_spatial_provenance_v2.json"
OUT_MD = D16 / "phase17_v3_cortical_direct_spatial_diagnostics_v2.md"

LAT_COLS = ["left_fraction", "right_fraction", "correct_side_fraction",
            "contralateral_fraction"]
NON_LAT_INVARIANT = ["containment", "rank", "best", "margin", "fine", "outside", "dice",
                     "historical", "proposed", "intersection"]


def main() -> None:
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    v1_rows = list(csv.DictReader(open(V1, encoding="utf-8-sig")))
    assert len(v1_rows) == 170
    univ = {r["fine_region_id"]: r for r in csv.DictReader(open(UNIV, encoding="utf-8-sig"))}
    m = np.asanyarray(nib.load(str(FINE_VOL)).dataobj).astype(np.int16)
    aff = nib.load(str(FINE_VOL)).affine
    sh = m.shape
    ii, jj, kk = np.ogrid[:sh[0], :sh[1], :sh[2]]
    xgrid = aff[0, 0] * (ii + 0.5) + aff[0, 1] * (jj + 0.5) + aff[0, 2] * (kk + 0.5) + aff[0, 3]
    left_grid = xgrid < 0

    cols_v1 = list(v1_rows[0].keys())
    cols_v2 = [c for c in cols_v1 if c not in LAT_COLS] + LAT_COLS
    diff_rows = []
    unexpected = []
    v2_rows = []
    for r in v1_rows:
        pid = int(univ[r["fine_region_id"]]["parcel_id"])
        hemi = r["hemisphere"]
        fine = m == pid
        fv = int(fine.sum())
        left_frac = float((fine & left_grid).sum()) / fv
        right_frac = 1.0 - left_frac
        if hemi == "left":
            correct, contra = left_frac, right_frac
        else:
            correct, contra = right_frac, left_frac
        out = {k: r[k] for k in cols_v1}          # byte-copy V1 fields
        out["left_fraction"] = round(left_frac, 5)
        out["right_fraction"] = round(right_frac, 5)
        out["correct_side_fraction"] = round(correct, 5)
        out["contralateral_fraction"] = round(contra, 5)
        # flags: keep V1 flags; ensure laterality flag matches corrected gate
        base_flags = [f for f in r["flags"].split("|") if f != "LATERALITY_FAILURE"]
        if correct < 0.90:
            base_flags.append("LATERALITY_FAILURE")
        out["flags"] = "|".join(base_flags)
        # non-laterality invariance audit
        changed = [k for k in cols_v1
                   if k not in LAT_COLS and k != "flags" and str(out[k]) != str(r[k])]
        if changed:
            unexpected.append(dict(fine_region_id=r["fine_region_id"], changed_fields=changed))
        # diff for laterality-related fields
        if hemi == "right":
            diff_rows.append(dict(fine_region_id=r["fine_region_id"], hemisphere=hemi,
                                  field="correct_side_fraction",
                                  v1=r["correct_side_fraction"], v2=str(round(correct, 5)),
                                  reason="V1 held left_fraction; corrected to right_fraction"))
            diff_rows.append(dict(fine_region_id=r["fine_region_id"], hemisphere=hemi,
                                  field="contralateral_fraction",
                                  v1=r["contralateral_fraction"], v2=str(round(contra, 5)),
                                  reason="V1 held 1-left_fraction; corrected to left_fraction"))
        v2_rows.append(out)

    # verify left rows semantic equivalence to V1 (correct_side == left_fraction == V1 side_ok)
    left_equiv = all(abs(float(r["left_fraction"]) - float(r["correct_side_fraction"])) < 1e-9 and
                     abs(float(r["left_fraction"]) - float(v1_rows[i]["correct_side_fraction"])) < 1e-6
                     for i, r in enumerate(v2_rows) if r["hemisphere"] == "left")
    right_ok = all(abs(float(r["correct_side_fraction"]) - float(r["right_fraction"])) < 1e-9
                   for r in v2_rows if r["hemisphere"] == "right")
    sum_ok = all(abs((float(r["correct_side_fraction"]) + float(r["contralateral_fraction"])) - 1.0)
                 < 1e-6 for r in v2_rows)
    fails = [r["fine_region_id"] for r in v2_rows if float(r["correct_side_fraction"]) < 0.90]
    right_corrected = sum(1 for r in v2_rows if r["hemisphere"] == "right")
    assert not unexpected, unexpected[:3]
    assert left_equiv and right_ok and sum_ok

    with open(OUT_V2, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=cols_v2)
        w.writeheader()
        for row in v2_rows:
            w.writerow(row)
    with open(OUT_CORR, "w", encoding="utf-8") as fh:
        json.dump(dict(
            correction_id="REPORTING_SEMANTICS_CORRECTION_V1",
            schema="DIRECT_SPATIAL_EVIDENCE_SCHEMA_V2",
            v1_bug="correct_side_fraction column stored LEFT_HEMISPHERE_FRACTION (side_ok) for all "
                   "rows; hemisphere-unaware for right parcels",
            root_cause="side_ok = |fine & left_grid|/|fine| reused as correct_side for both sides",
            containment_rank_unaffected=True,
            definition=dict(
                left_fraction="|fine & {RAS x<0}| / |fine|",
                right_fraction="1 - left_fraction (no exact-midline voxel centres on this grid)",
                correct_side_fraction="left_fraction if hemisphere==left else right_fraction",
                contralateral_fraction="1 - correct_side_fraction"),
            laterality_gate_kept="correct_side_fraction >= 0.90",
            method_algorithm_unchanged=True,
            method_id="DIRECT_CORTICAL_SPATIAL_VALIDATION_METHOD_V1 (schema V2 reporting fix)",
            v1_history_preserved="phase17_v3_cortical_170_direct_spatial_evidence.csv (a32e20e)",
            created_at=ts, script_version=SCRIPT_VERSION), fh, ensure_ascii=False, indent=2)
    with open(OUT_DIFF, "w", newline="", encoding="utf-8-sig") as fh:
        cols = ["fine_region_id", "hemisphere", "field", "v1", "v2", "reason"]
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for row in diff_rows:
            w.writerow(row)
    with open(OUT_PROV, "w", encoding="utf-8") as fh:
        json.dump(dict(
            provenance_id="DIRECT_SPATIAL_EVIDENCE_V2_PROVENANCE",
            universe=len(v2_rows), left=sum(1 for r in v2_rows if r["hemisphere"] == "left"),
            right=right_corrected,
            non_laterality_field_unexpected_diffs=len(unexpected),
            laterality_corrected_right_rows=right_corrected,
            left_rows_semantic_equivalent=left_equiv,
            right_correct_side_equals_right_fraction=right_ok,
            correct_plus_contralateral_eq_1=sum_ok,
            laterality_failures_after_correction=fails,
            laterality_qc=("LATERALITY_QC_CONFIRMED_AFTER_SEMANTIC_CORRECTION" if not fails
                           else "LATERALITY_FAILURE_PRESENT"),
            containment_unchanged="170/170 byte-identical (copied from V1; 0 diffs)",
            ranking_unchanged="170/170 identical",
            geometry_unchanged=True, mapping_unchanged=True,
            v1_history_preserved=True,
            created_at=ts, script_version=SCRIPT_VERSION), fh, ensure_ascii=False, indent=2)

    md = [
        "# Phase1.7 V3 - direct spatial evidence laterality semantics correction (V2)", "",
        "Confirmed V1 bug: correct_side_fraction stored LEFT_HEMISPHERE_FRACTION for all rows "
        "(hemisphere-unaware). Corrected in V2 without changing any scientific metric.",
        f"universe {len(v2_rows)} (L {sum(1 for r in v2_rows if r['hemisphere']=='left')} / "
        f"R {right_corrected}).",
        f"left/right fractions explicit; correct/contralateral assigned by hemisphere; "
        f"left semantic equivalent {left_equiv}, right correct==right_fraction {right_ok}, "
        f"correct+contralateral==1 {sum_ok}.",
        f"non-laterality field diffs = {len(unexpected)}; containment/rank/outside-union/"
        f"competition/margin unchanged 170/170 (byte-copied from V1).",
        f"laterality failures after corrected semantics = {fails or 'none'} -> "
        f"{'LATERALITY_QC_CONFIRMED_AFTER_SEMANTIC_CORRECTION' if not fails else 'failures present'}.",
        "a32e20e V1 preserved. No mapping change. No ontology adjudication. No geometry change. "
        "No classification change. No DB write.", ""]
    with open(OUT_MD, "w", encoding="utf-8") as fh:
        fh.write("\n".join(md) + "\n")

    print("v2 written; right corrected", right_corrected, "| non-lat diffs", len(unexpected),
          "| left equiv", left_equiv, "| sum ok", sum_ok, "| failures", fails)


if __name__ == "__main__":
    main()
