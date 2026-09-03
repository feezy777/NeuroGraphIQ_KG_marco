"""Gate 7B Phase 2A — G4 Julich→G3 Brainnetome Spatial Asset Feasibility Audit.

Read-only audit of what official spatial assets exist for G4 (Julich-Brain v3.1)
and G3 (Brainnetome BNA246), and whether voxel-level overlap is currently
possible. Confirms identity chains are deterministic even where map files are
absent, and that the G3→G1 production state is untouched.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import psycopg
import pytest

BACKEND = Path(__file__).resolve().parents[1]
PROD = "neurographiq_human_brain_v1"
INT = BACKEND / "data" / "integration"
ATL = BACKEND / "data" / "atlases"


def _conn(db=PROD):
    return psycopg.connect(host="127.0.0.1", port=5432, user="postgres",
                           password="postgres", dbname=db, autocommit=True)


def _rows(name):
    return list(csv.DictReader(open(INT / name, encoding="utf-8-sig")))


# ---------------------------------------------------------------------------
# 1-2. canonical counts
# ---------------------------------------------------------------------------

def test_g4_canonical_count_440():
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT count(*) FROM brain_regions b JOIN kg_entities e ON e.entity_pk=b.entity_pk"
                    " WHERE b.granularity_level='G4_MICROSTRUCTURAL_FINE' AND e.record_status='active'")
        assert cur.fetchone()[0] == 440
    finally:
        conn.close()


def test_g3_canonical_count_246():
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT count(*) FROM brain_regions b JOIN kg_entities e ON e.entity_pk=b.entity_pk"
                    " WHERE b.granularity_level='G3_MESO_FINE' AND e.record_status='active'")
        assert cur.fetchone()[0] == 246
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 3-4. spatial asset readability (as present in repo)
# ---------------------------------------------------------------------------

def test_g4_spatial_asset_readability():
    # G4 map inventory is readable metadata; actual maps NOT in repo
    inv = json.load(open(ATL / "julich" / "v3.1" / "julich_v3_1_map_inventory.json", encoding="utf-8"))
    assert "spaces" in inv and "datasets" in inv
    assert "MNI" in inv["spaces"][0]  # declared MNI spaces


def test_g3_volume_asset_readability():
    # BN.mgz (subject volume from FreeSurfer pkg) must be nibabel-readable
    import nibabel as nib
    p = ATL / "brainnetome" / "bna246" / "surface_raw" / "extracted" / \
        "BN_Atlas_freesurfer" / "001" / "mri" / "BN.mgz"
    assert p.exists(), "BN.mgz missing"
    img = nib.load(str(p))
    assert img.shape == (256, 256, 256)


# ---------------------------------------------------------------------------
# 5-6. identity determinism
# ---------------------------------------------------------------------------

def test_g4_identity_deterministic_440():
    rows = _rows("g4_julich_spatial_to_canonical_alignment.csv")
    assert len(rows) == 440
    assert all(r["alignment_status"] == "ALIGNED" for r in rows)
    assert len({r["g4_entity_id"] for r in rows}) == 440


def test_g3_identity_deterministic_246():
    rows = _rows("g3_brainnetome_volume_to_canonical_alignment.csv")
    assert len(rows) == 246
    assert all(r["alignment_status"] == "ALIGNED" for r in rows)
    assert len({r["g3_entity_id"] for r in rows}) == 246
    # volumetric label index 1..246, one per parcel
    idxs = [int(r["volumetric_label_index"]) for r in rows]
    assert sorted(idxs) == list(range(1, 247))


# ---------------------------------------------------------------------------
# 7. affine/orientation audit
# ---------------------------------------------------------------------------

def test_bn_mgz_affine_orientation():
    ref = json.load(open(INT / "g3_brainnetome_volume_reference_audit.json", encoding="utf-8"))
    info = ref["subject_volume_bn_mgz"]
    assert info["voxel_size_mm"] == [1.0, 1.0, 1.0]
    assert info["shape"] == [256, 256, 256]
    assert "affine" in info and "orientation" in info


# ---------------------------------------------------------------------------
# 8. common-space classification deterministic
# ---------------------------------------------------------------------------

def test_feasibility_classification():
    feas = json.load(open(INT / "g4_g3_common_space_feasibility_audit.json", encoding="utf-8"))
    assert feas["primary_classification"] == "SPATIAL_ASSET_ACQUISITION_REQUIRED"
    assert feas["probabilistic_overlap_required"] is True


# ---------------------------------------------------------------------------
# 9. hemisphere preservation
# ---------------------------------------------------------------------------

def test_g4_hemisphere_preserved():
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT b.hemisphere, count(*) FROM brain_regions b"
                    " JOIN kg_entities e ON e.entity_pk=b.entity_pk"
                    " WHERE b.granularity_level='G4_MICROSTRUCTURAL_FINE' AND e.record_status='active' GROUP BY 1")
        d = dict(cur.fetchall())
    finally:
        conn.close()
    assert d == {"left": 220, "right": 220}


def test_g3_hemisphere_preserved():
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT b.hemisphere, count(*) FROM brain_regions b"
                    " JOIN kg_entities e ON e.entity_pk=b.entity_pk"
                    " WHERE b.granularity_level='G3_MESO_FINE' AND e.record_status='active'"
                    " GROUP BY 1")
        d = dict(cur.fetchall())
    finally:
        conn.close()
    assert d == {"left": 123, "right": 123}


# ---------------------------------------------------------------------------
# 10. G3→G1 production unchanged
# ---------------------------------------------------------------------------

def test_g3_to_g1_production_unchanged():
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


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
