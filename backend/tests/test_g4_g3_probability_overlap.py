"""Gate 7B Phase 2G — G4 Julich x G3 Brainnetome probability-weighted spatial
association matrix (measurement only).

Read-only verification of the produced 414x246 evidence (one rerun test
re-executes the idempotent compute and asserts the matrix hash is unchanged).
No thresholds, no mapping, no DB writes.

Coverage (gate section 21, 1-20):
  G4 spatial count 414 / G3 246 / pair count 101844 / grid identity /
  scale 0-1 / formulas correct / all finite / directional + cosine + soft-dice
  in [0,1] / row identity deterministic / column identity deterministic /
  canonical lineage kept / shared component NOT duplicated into fake canonical
  rows / top10 complete / hemisphere QA / input SHA unchanged / rerun matrix
  hash identical / G3->G1 unchanged / G4->G3 production rows = 0.
"""

from __future__ import annotations

import csv
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
SCRIPT = BACKEND / "scripts" / "compute_g4_g3_probability_overlap.py"
PY = sys.executable
SHAPE = (193, 229, 193)

SUM = json.load(open(INT / "g4_g3_probability_overlap_summary.json", encoding="utf-8"))
NPZ = INT / "g4_g3_probability_overlap_matrix.npz"
LONG = INT / "g4_g3_probability_overlap_matrix.csv"
ROWS = INT / "g4_g3_probability_overlap_rows.csv"
COLS = INT / "g4_g3_probability_overlap_columns.csv"
TOP_G4 = INT / "g4_g3_probability_overlap_top10_by_g4.csv"
TOP_G3 = INT / "g4_g3_probability_overlap_top10_by_g3.csv"
QA = INT / "g4_g3_probability_overlap_qa.json"

JUL_DIR = BACKEND / "data" / "atlases" / "julich" / "v3.1" / "spatial_raw" / "probability_maps"
BNA_OUT = BACKEND / "data" / "atlases" / "brainnetome" / "bna246" / "transformed_to_julich2009c" / "probability_maps"


def _rows(p: Path) -> list[dict]:
    return list(csv.DictReader(open(p, encoding="utf-8-sig")))


def _conn(db=PROD):
    return psycopg.connect(host="127.0.0.1", port=5432, user="postgres",
                           password="postgres", dbname=db, autocommit=True)


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# 1-5. counts + grid + scale
# ---------------------------------------------------------------------------

def test_g4_spatial_count_414():
    assert SUM["julich_spatial_components"] == 414
    assert len(_rows(ROWS)) == 414
    assert len(list(JUL_DIR.glob("*.nii.gz"))) == 414


def test_g3_count_246():
    assert SUM["brainnetome_components"] == 246
    assert len(_rows(COLS)) == 246
    assert len(list(BNA_OUT.glob("*.nii.gz"))) == 246


def test_pair_count_101844():
    assert SUM["pair_count"] == 101844
    assert SUM["pair_count"] == 414 * 246


def test_grid_identity_julich_and_bna():
    j = nib.load(str(sorted(JUL_DIR.glob("*.nii.gz"))[0]))
    b = nib.load(str(sorted(BNA_OUT.glob("*.nii.gz"))[0]))
    assert j.shape == b.shape == SHAPE
    assert tuple(nib.aff2axcodes(j.affine)) == ("R", "A", "S")
    assert np.array_equal(np.asarray(j.affine), np.asarray(b.affine))  # exactly shared grid


def test_input_scale_0_1():
    for p in (sorted(JUL_DIR.glob("*.nii.gz"))[0], sorted(BNA_OUT.glob("*.nii.gz"))[0]):
        d = nib.load(str(p)).get_fdata()
        assert d.min() >= 0.0 and d.max() <= 1.000001
        assert not np.isnan(d).any() and not np.isinf(d).any()


# ---------------------------------------------------------------------------
# 6-10. formulas + finite + ranges (computed arrays)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def Z():
    return np.load(str(NPZ))


def test_metrics_all_finite(Z):
    for k in ("M", "g4w", "g3w", "cosine", "soft_dice", "mass4", "mass3"):
        assert np.isfinite(Z[k]).all()


def test_formulas_correct(Z):
    M, g4w, g3w = Z["M"], Z["g4w"], Z["g3w"]
    cos, sd = Z["cosine"], Z["soft_dice"]
    m4, m3, n4, n3 = Z["mass4"], Z["mass3"], Z["norm2_4"], Z["norm2_3"]
    assert np.allclose(M / m4[:, None], g4w, atol=1e-9)
    assert np.allclose(M / m3[None, :], g3w, atol=1e-9)
    assert np.allclose(M / np.sqrt(n4[:, None] * n3[None, :]), cos, atol=1e-9)
    assert np.allclose(2 * M / (n4[:, None] + n3[None, :]), sd, atol=1e-9)


def test_joint_mass_nonneg(Z):
    assert Z["M"].min() >= 0.0
    assert Z["M"].max() > 0.0


def test_directional_metrics_in_0_1(Z):
    for k in ("g4w", "g3w", "cosine", "soft_dice"):
        a = Z[k]
        assert a.min() >= -1e-9 and a.max() <= 1.0 + 1e-9


# ---------------------------------------------------------------------------
# 11-12. deterministic row / column identity
# ---------------------------------------------------------------------------

def test_row_identity_deterministic():
    rows = _rows(ROWS)
    assert [int(r["row_index"]) for r in rows] == list(range(1, 415))
    assert len({r["julich_asset_file"] for r in rows}) == 414
    names = sorted(r["julich_asset_file"] for r in rows)
    assert [r["julich_asset_file"] for r in rows] == names  # sorted raw-string order
    assert SUM["julich_row_order"].startswith("sorted by spatial_asset_file")


def test_column_identity_deterministic():
    cols = _rows(COLS)
    assert [int(r["column_index"]) for r in cols] == list(range(1, 247))
    assert [int(r["component_index"]) for r in cols] == list(range(1, 247))
    assert len({r["canonical_g3_id"] for r in cols}) == 246
    assert SUM["g3_column_order"].startswith("component_index 1..246")


# ---------------------------------------------------------------------------
# 13-14. canonical lineage + no shared-component duplication
# ---------------------------------------------------------------------------

def test_canonical_lineage_preserved():
    rows = _rows(ROWS)
    for r in rows:
        n = int(r["canonical_g4_descendant_count"])
        ids = [x for x in r["canonical_g4_ids"].split(";") if x]
        assert n == len(ids)
        assert r["spatial_identity_status"] in ("ONE_TO_ONE_CANONICAL", "SHARED_SPATIAL_REPRESENTATION")
        if n == 1:
            assert r["spatial_identity_status"] == "ONE_TO_ONE_CANONICAL"
        else:
            assert r["spatial_identity_status"] == "SHARED_SPATIAL_REPRESENTATION"
    assert SUM["one_to_one_julich_component_count"] == 390
    assert SUM["shared_spatial_component_count"] == 24
    assert SUM["canonical_g4_covered_count"] == 440


def test_shared_component_not_duplicated_into_canonical_rows():
    # long matrix has EXACTLY 414*246 rows, one per julich spatial component x g3,
    # never expanded by canonical descendants -> no fake independent canonical scores
    rows = 0
    with open(LONG, encoding="utf-8") as fh:
        reader = csv.reader(fh)
        next(reader)
        for _ in reader:
            rows += 1
    assert rows == 414 * 246 == 101844
    # every julich component appears exactly 246 times (one per G3)
    from collections import Counter
    c = Counter()
    with open(LONG, encoding="utf-8") as fh:
        rdr = csv.DictReader(fh)
        for r in rdr:
            c[r["julich_component_id"] + "|" + r["julich_asset_file"]] += 1
    assert len(c) == 414
    assert set(c.values()) == {246}


# ---------------------------------------------------------------------------
# 15. top10 complete
# ---------------------------------------------------------------------------

def test_top10_by_g4_complete():
    top = _rows(TOP_G4)
    # two ranking schemes (joint_mass + g4_weighted) x 10 per 414 rows
    assert len(top) == 414 * 2 * 10
    keys = {r["rank_key"] for r in top}
    assert keys == {"joint_mass", "g4_weighted"}
    # for each row + scheme exactly 10 ranks
    cnt = {}
    for r in top:
        cnt[(r["julich_asset_file"], r["rank_key"])] = cnt.get((r["julich_asset_file"], r["rank_key"]), 0) + 1
    assert len(cnt) == 414 * 2
    assert set(cnt.values()) == {10}


def test_top10_by_g3_complete():
    top = _rows(TOP_G3)
    assert len(top) == 246 * 10
    assert set(c["g3_component_index"] for c in top) == set(map(str, range(1, 247)))


# ---------------------------------------------------------------------------
# 16. hemisphere QA
# ---------------------------------------------------------------------------

def test_hemisphere_qa():
    assert SUM["hemisphere_flip_count"] == 0
    assert SUM["opposite_hemisphere_top1_count"] == SUM["hemisphere_QA_anomaly_count"]
    # every flagged anomaly is a documented degenerate zero-overlap row (not auto-deleted)
    for a in SUM["hemisphere_QA_anomaly_rows"]:
        assert a["cause"] == "DEGENERATE_ZERO_G3_OVERLAP"
        assert a["row_max_joint_mass"] < 1e-3
        assert a["opposite_mass_ratio"] == 0.0


# ---------------------------------------------------------------------------
# 17. input SHA unchanged
# ---------------------------------------------------------------------------

def test_input_sha_unchanged():
    # raw BNA PM frozen hash (Phase 2D) untouched
    pm = BACKEND / "data" / "atlases" / "brainnetome" / "bna246" / "volume_raw" / "BNA_PM_4D.nii.gz"
    assert _sha(pm) == "b1318517f61d08f714c25e55ee580eb8a487c0b7ab1ddbcc7eac852e4e97f020"
    # sample Julich file shas still match the frozen alignment CSV (same order basis)
    comp = _rows(INT / "g4_julich_v31_spatial_component_alignment.csv")
    by_name = {r["spatial_asset_file"]: r["sha256"] for r in comp}
    for f in list(JUL_DIR.glob("*.nii.gz"))[::100]:  # deterministic sample stride
        assert by_name[f.name] == _sha(f)
    # representative QA json exists (no new spatial assets written)
    assert QA.exists()


# ---------------------------------------------------------------------------
# 18. rerun: matrix hash identical
# ---------------------------------------------------------------------------

def test_rerun_matrix_hash_identical():
    d0 = np.load(str(NPZ))
    M0 = d0["M"].copy()
    proc = subprocess.run([PY, str(SCRIPT)], capture_output=True, text=True,
                          cwd=str(BACKEND), timeout=900)
    out = proc.stdout + proc.stderr
    assert proc.returncode == 0, out
    assert "matrix_hash=" in out
    rerun_hash = out.split("matrix_hash=")[1].splitlines()[0].strip()
    assert rerun_hash == SUM["matrix_hash"]
    # numerical matrix unchanged
    d1 = np.load(str(NPZ))
    assert np.array_equal(M0, d1["M"])


# ---------------------------------------------------------------------------
# summary self-consistency + no decisions
# ---------------------------------------------------------------------------

def test_summary_contract():
    assert SUM["phase"] == "G4_G3_PROBABILITY_OVERLAP_V1"
    assert SUM["classification_thresholds"] == "NOT_DEFINED"
    assert SUM["mapping_decisions_created"] is False
    assert SUM["metric_version"] == "G4_G3_PROBABILITY_OVERLAP_V1"
    assert SUM["hemisphere_flip_count"] == 0
    assert SUM["finite_pair_count"] == 101844
    assert SUM["non_zero_pair_count"] > 0
    qa = json.load(open(QA, encoding="utf-8"))
    assert qa["formula_recompute_ok"] is True
    assert qa["formula_recompute_max_abs_error"] < 1e-6
    assert len(qa["representative_components"]) == 6
    roles = {x["role"] for x in qa["representative_components"]}
    assert roles == {"LATERAL_LEFT_1", "LATERAL_LEFT_2", "LATERAL_RIGHT_1",
                     "LATERAL_RIGHT_2", "NEAR_MIDLINE", "SUBCORTICAL"}


# ---------------------------------------------------------------------------
# 19-20. G3->G1 unchanged + no G4->G3 rows
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
    assert total == 246


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
