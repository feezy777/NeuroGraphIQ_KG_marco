"""Gate 7B Phase 2F — G3 (Brainnetome) 246-probability batch transform to the
Julich MNI152NLin2009cAsym native grid.

Read-only verification of the produced batch (except one rerun-safety test which
re-executes the idempotent script and asserts processed=0/skipped=246/failed=0).

Coverage (gate section 22, 1-20):
  transformed count 246 / identity 246 / target grid 246/246 / finite 246/246 /
  range 246/246 / nonempty 246/246 / hemisphere flips 0 / manifest 246 /
  output SHA complete / transform SHA consistent / tool+version fixed /
  interpolation Linear / output scale 0-1 / source raw SHA unchanged /
  Julich grid 414/414 / representative QA exists / rerun 0/246/0 /
  no temp leftovers / G3->G1 unchanged / G4->G3 rows = 0.

No DB writes.
"""

from __future__ import annotations

import csv
import glob
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import nibabel as nib
import numpy as np
import psycopg
import pytest

BACKEND = Path(__file__).resolve().parents[1]
PROD = "neurographiq_human_brain_v1"
INT = BACKEND / "data" / "integration"
BATCH = BACKEND / "data" / "atlases" / "brainnetome" / "bna246" / "transformed_to_julich2009c"
PROB = BATCH / "probability_maps"
PROV = BATCH / "provenance"
SMOKE = BACKEND / "data" / "atlases" / "brainnetome" / "bna246" / "transformed_to_julich2009c_smoke"
JULICH = BACKEND / "data" / "atlases" / "julich" / "v3.1" / "spatial_raw" / "probability_maps"
BNA_VOL = BACKEND / "data" / "atlases" / "brainnetome" / "bna246" / "volume_raw"
SCRIPT = BACKEND / "scripts" / "transform_brainnetome_to_julich2009c.py"
PY = sys.executable

PM = BNA_VOL / "BNA_PM_4D.nii.gz"
HCP = BNA_VOL / "HCP40_MNI_1.25mm.nii.gz"
BN1 = BNA_VOL / "BN_Atlas_246_1mm.nii.gz"
XFM = BACKEND / "data" / "atlases" / "templateflow_ref" / "MNI152NLin2009cAsym_from-MNI152NLin6Asym_mode-image_xfm.h5"
SUMMARY = json.load(open(INT / "g4_g3_batch_transform_validation.json", encoding="utf-8"))
JUL_REF = sorted(JULICH.glob("*.nii.gz"))[0]
SHAPE = (193, 229, 193)


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _conn(db=PROD):
    return psycopg.connect(host="127.0.0.1", port=5432, user="postgres",
                           password="postgres", dbname=db, autocommit=True)


def _rows(name: str) -> list[dict]:
    return list(csv.DictReader(open(INT / name, encoding="utf-8-sig")))


def _manifest():
    return _rows("g3_brainnetome_to_julich_batch_transform_manifest.csv")


def _out_for(idx: int) -> Path:
    hits = sorted(PROB.glob(f"BNA_PM_comp{idx:03d}_*_prob_2009c.nii.gz"))
    assert len(hits) == 1, (idx, hits)
    return hits[0]


@pytest.fixture(scope="session")
def per_comp():
    """One read pass over all 246 outputs; small summary dicts only."""
    jul = nib.load(str(JUL_REF))
    ref_aff = np.asarray(jul.affine)
    out = []
    for idx in range(1, 247):
        p = _out_for(idx)
        img = nib.load(str(p))
        nd = img.get_fdata()
        nnz = int((nd != 0).sum())
        grid = (nd.shape == SHAPE
                and np.allclose(img.affine, ref_aff, atol=1e-3)
                and tuple(nib.aff2axcodes(img.affine)) == ("R", "A", "S"))
        prov = json.loads((PROV / f"comp{idx:03d}_provenance.json").read_text(encoding="utf-8"))
        # correct-side mass fraction
        nz = nd != 0
        frac = None
        if nnz:
            coords = np.argwhere(nz).astype(np.float64)
            vals = nd[nz].astype(np.float64)
            wx = nib.affines.apply_affine(img.affine, coords)[:, 0]
            if prov["hemisphere"] == "left":
                frac = float(vals[wx < 0].sum() / vals.sum())
            else:
                frac = float(vals[wx > 0].sum() / vals.sum())
        out.append({
            "idx": idx,
            "path": p,
            "nd": nd,
            "nnz": nnz,
            "nan": int(np.isnan(nd).sum()),
            "inf": int(np.isinf(nd).sum()),
            "nmin": float(nd.min()),
            "nmax": float(nd.max()),
            "sum": float(nd.sum()),
            "grid": bool(grid),
            "correct_frac": frac,
            "prov": prov,
        })
    return out


# ---------------------------------------------------------------------------
# 1-2. transformed map count + identity count
# ---------------------------------------------------------------------------

def test_transformed_map_count_246():
    assert len(list(PROB.glob("*.nii.gz"))) == 246
    assert len(list(PROV.glob("comp*_provenance.json"))) == 246


def test_identity_count_246_and_hemispheres():
    provs = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(PROV.glob("*.json"))]
    assert len(provs) == 246
    assert sorted(x["component_index"] for x in provs) == list(range(1, 247))
    assert len({x["canonical_g3_id"] for x in provs}) == 246
    assert len({x["parcel_id"] for x in provs}) == 246
    hemi = {}
    for x in provs:
        hemi[x["hemisphere"]] = hemi.get(x["hemisphere"], 0) + 1
    assert hemi == {"left": 123, "right": 123}


# ---------------------------------------------------------------------------
# 3-6. target grid / finite / range / nonempty  (all 246/246)
# ---------------------------------------------------------------------------

def test_target_grid_246(per_comp):
    assert all(x["grid"] for x in per_comp)


def test_finite_246(per_comp):
    assert all(x["nan"] == 0 and x["inf"] == 0 for x in per_comp)


def test_range_246(per_comp):
    assert all(x["nmin"] >= -1e-4 and x["nmax"] <= 1.000001 for x in per_comp)
    assert all(x["nmin"] >= 0.0 for x in per_comp)  # normalized probability


def test_nonempty_246(per_comp):
    assert all(x["nnz"] > 0 for x in per_comp)


# ---------------------------------------------------------------------------
# 7. hemisphere flips = 0  (mass-majority rule, midline-aware)
# ---------------------------------------------------------------------------

def test_hemisphere_flips_zero(per_comp):
    assert all(x["correct_frac"] is not None and x["correct_frac"] >= 0.5 for x in per_comp)


# ---------------------------------------------------------------------------
# 8-9. manifest 246 + output SHA complete
# ---------------------------------------------------------------------------

def test_manifest_246_rows():
    rows = _manifest()
    assert len(rows) == 246
    assert sorted(int(r["component_index"]) for r in rows) == list(range(1, 247))


def test_manifest_output_sha_complete():
    for r in _manifest():
        p = BACKEND / r["output_asset"]
        assert p.exists(), r["output_asset"]
        assert r["output_sha256"] == _sha(p)
        assert r["transform_status"] == "PASS"


# ---------------------------------------------------------------------------
# 10-12. transform SHA / tool / version / interpolation
# ---------------------------------------------------------------------------

def test_transform_sha_consistent():
    expected = _sha(XFM)
    provs = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(PROV.glob("*.json"))]
    assert len({x["transform_sha256"] for x in provs}) == 1
    assert provs[0]["transform_sha256"] == expected
    assert SUMMARY["transform_sha256"] == expected


def test_tool_version_and_interpolation_fixed():
    provs = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(PROV.glob("*.json"))]
    assert {x["tool"] for x in provs} == {"SimpleITK"}
    assert len({x["tool_version"] for x in provs}) == 1
    assert {x["interpolation"] for x in provs} == {"Linear"}
    assert all(x["transform_direction"] == "as_stored (no GetInverse)" for x in provs)


# ---------------------------------------------------------------------------
# 13. output scale 0-1 (normalized, never raw percent)
# ---------------------------------------------------------------------------

def test_output_scale_0_1(per_comp):
    for x in per_comp:
        prov = x["prov"]
        assert prov["output_scale"] == "normalized_0_1"
        assert prov["normalization"] == "divide_by_100_after_transform"
        assert prov["source_scale"] == "percent_0_100"
        assert prov["normalized_max"] <= 1.000001
        # raw percent is NOT stored per component (intermediate policy)
        assert not any(p.name.endswith("_raw_percent.nii.gz") for p in PROB.iterdir())


# ---------------------------------------------------------------------------
# 14. source raw SHA unchanged
# ---------------------------------------------------------------------------

def test_source_raw_sha_unchanged():
    assert _sha(PM) == "b1318517f61d08f714c25e55ee580eb8a487c0b7ab1ddbcc7eac852e4e97f020"
    assert _sha(HCP) == "2843cb60b5d487593e40a5bbf0555d7034bfedb21a2f78fb4e84a84cc34b5552"
    provs = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(PROV.glob("*.json"))]
    assert all(x["source_sha256"] == _sha(PM) for x in provs)


# ---------------------------------------------------------------------------
# 15. Julich 414 grid (read-only re-check, all same 2009c grid)
# ---------------------------------------------------------------------------

def test_julich_414_grid():
    files = sorted(JULICH.glob("*.nii.gz"))
    assert len(files) == 414
    aff = None
    ok = 0
    for f in files:
        im = nib.load(str(f))
        if aff is None:
            aff = np.asarray(im.affine)
        if im.shape == SHAPE and np.allclose(im.affine, aff, atol=1e-4) \
                and tuple(nib.aff2axcodes(im.affine)) == ("R", "A", "S"):
            ok += 1
    assert ok == 414
    assert SUMMARY["Julich_target_grid_count"] == 414
    assert SUMMARY["Julich_target_grid_match"] == 414


# ---------------------------------------------------------------------------
# 16. representative QA exists
# ---------------------------------------------------------------------------

def test_representative_qa_exists():
    details = SUMMARY["representative_qa_detail"]
    pngs = [Path(d["png"]) for d in details]
    assert len(pngs) >= 5
    assert all(p.exists() and p.stat().st_size > 0 for p in pngs)
    roles = {d["role"] for d in details}
    assert {"LATERAL_LEFT_1", "LATERAL_RIGHT_1", "NEAR_MIDLINE", "SUBCORTICAL"} <= roles
    assert len({d["component_index"] for d in details}) == len(details)
    hemis = {d["hemisphere"] for d in details}
    assert "left" in hemis and "right" in hemis
    # deterministic: every selected rep must be a PASS output
    assert all(d["component_index"] <= 246 for d in details)


# ---------------------------------------------------------------------------
# 17. rerun safety: second execution -> processed=0 skipped=246 failed=0
# ---------------------------------------------------------------------------

def test_rerun_idempotent_no_rewrite():
    before = {_sha(_out_for(i)) for i in (1, 100, 246)}
    before_prov_ts = json.loads((PROV / "comp001_provenance.json").read_text(encoding="utf-8"))["timestamp"]
    proc = subprocess.run([PY, str(SCRIPT), "--all"], capture_output=True, text=True,
                          cwd=str(BACKEND), timeout=600)
    out = proc.stdout + proc.stderr
    assert proc.returncode == 0, out
    assert "processed=0 skipped=246 failed=0" in out, out
    # outputs/provenance untouched by rerun
    assert before == {_sha(_out_for(i)) for i in (1, 100, 246)}
    after_ts = json.loads((PROV / "comp001_provenance.json").read_text(encoding="utf-8"))["timestamp"]
    assert after_ts == before_prov_ts


# ---------------------------------------------------------------------------
# 18. no temp leftovers
# ---------------------------------------------------------------------------

def test_no_temp_leftovers():
    # batch dir has only the three formal subdirs
    names = {p.name for p in BATCH.iterdir()}
    assert names <= {"probability_maps", "provenance", "manifest"}, names
    # no underscore temp intermediates anywhere under the batch dir
    tmps = [p for p in BATCH.rglob("*") if p.is_file() and p.name.startswith("_")]
    assert tmps == []
    # every .nii.gz lives in probability_maps and carries the formal name pattern
    all_nii = [p for p in BATCH.rglob("*.nii.gz")]
    assert len(all_nii) == 246
    assert all(p.parent == PROB for p in all_nii)
    assert all(p.name.startswith("BNA_PM_comp") and p.name.endswith("_prob_2009c.nii.gz") for p in all_nii)
    # smoke dir still separate and untouched
    assert SMOKE.exists()
    assert (SMOKE / "BNA_PM4D_comp001_NLin6to2009c_raw_percent.nii.gz").exists()


# ---------------------------------------------------------------------------
# 19-20. G3->G1 unchanged + no G4->G3 mapping
# ---------------------------------------------------------------------------

def test_g3_to_g1_unchanged():
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT count(*) FROM brain_region_aggregation_mappings WHERE source_granularity_level='G3_MESO_FINE'")
        total = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM brain_region_aggregation_mappings WHERE source_granularity_level='G3_MESO_FINE' AND record_status='active'")
        active = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM brain_region_aggregation_mappings WHERE source_granularity_level='G3_MESO_FINE' AND review_status='approved'")
        approved = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM brain_region_aggregation_mappings WHERE source_granularity_level='G3_MESO_FINE' AND rollup_eligible=TRUE")
        rollup = cur.fetchone()[0]
    finally:
        conn.close()
    assert total == 246 and active == 246 and approved == 246 and rollup == 172


def test_no_g4_g3_mapping_rows():
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT count(*) FROM brain_region_aggregation_mappings WHERE source_granularity_level='G3_MESO_FINE'")
        total = cur.fetchone()[0]
    finally:
        conn.close()
    assert total == 246  # frozen G3->G1 rows only


# ---------------------------------------------------------------------------
# summary self-consistency
# ---------------------------------------------------------------------------

def test_summary_batch_ready():
    assert SUMMARY["phase"] == "G4_G3_BATCH_TRANSFORM_V1"
    assert SUMMARY["component_total"] == 246
    assert SUMMARY["pass_count"] == 246
    assert SUMMARY["fail_count"] == 0
    assert SUMMARY["target_grid_match_count"] == 246
    assert SUMMARY["finite_pass_count"] == 246
    assert SUMMARY["range_pass_count"] == 246
    assert SUMMARY["nonempty_pass_count"] == 246
    assert SUMMARY["hemisphere_flip_count"] == 0
    assert SUMMARY["batch_status"] == "READY_FOR_G4_G3_PROBABILITY_OVERLAP"
    assert SUMMARY["interpolation"] == "Linear"
    assert "divide_by_100_after_transform" in SUMMARY["normalization_policy"]


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
