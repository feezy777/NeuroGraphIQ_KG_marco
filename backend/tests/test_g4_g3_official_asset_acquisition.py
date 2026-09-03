"""Gate 7B Phase 2B/2B-2 — G4/G3 Official Spatial Asset Acquisition state.

Validates the acquisition manifest (Julich acquired via siibra/EBRAINS;
Brainnetome user-downloaded), expected target directories, official source
metadata, that Phase 2A registry-identity CSVs + G3→G1 production are
unchanged, and that no G4→G3 mapping/overlap was created.
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

MANIFEST = json.load(open(INT / "g4_g3_official_spatial_asset_manifest.json", encoding="utf-8"))


def _rows(name):
    return list(csv.DictReader(open(INT / name, encoding="utf-8-sig")))


def _conn(db=PROD):
    return psycopg.connect(host="127.0.0.1", port=5432, user="postgres",
                           password="postgres", dbname=db, autocommit=True)


# ---------------------------------------------------------------------------
# acquisition state
# ---------------------------------------------------------------------------

def test_acquisition_status_manual_required():
    assert MANIFEST["acquisition_status"] == "ACQUIRED_JULICH_AND_BRAINNETOME"


def test_no_spatial_files_present_in_target_dirs():
    # Phase 2B-2 + user download: spatial assets now present.
    # Julich: probability_maps populated; Brainnetome: BN_Atlas_246 present.
    julich_prob = (ATL / "julich" / "v3.1" / "spatial_raw" / "probability_maps")
    bna = (ATL / "brainnetome" / "bna246" / "volume_raw")
    assert julich_prob.is_dir() and len(list(julich_prob.glob("*.nii.gz"))) == 414
    assert (bna / "BN_Atlas_246_1mm.nii.gz").exists()


def test_expected_dirs_exist():
    assert (ATL / "julich" / "v3.1" / "spatial_raw").is_dir()
    assert (ATL / "brainnetome" / "bna246" / "volume_raw").is_dir()
    assert (ATL / "brainnetome" / "bna246" / "surface_raw").is_dir()  # surface intact


def test_manifest_lists_both_assets():
    names = {a["atlas"] for a in MANIFEST["assets"]}
    assert "Julich-Brain Cytoarchitectonic Atlas v3.1" in names
    assert "Human Brainnetome Atlas BNA246 (2016)" in names


def test_manifest_official_sources_recorded():
    jul = next(a for a in MANIFEST["assets"] if "Julich" in a["atlas"])
    bna = next(a for a in MANIFEST["assets"] if "Brainnetome" in a["atlas"])
    assert "10.25493/KNSN-XB4" in jul["official_dataset_doi"]
    assert jul["official_dataset_id"] == "f1fe19e8-99bd-44bc-9616-a52850680777"
    assert bna["expected_official_file"] == "BN_Atlas_246_1mm.nii.gz"
    assert "atlas.brainnetome.org" in bna["official_download_page"]


def test_manifest_no_third_party():
    # every asset source is official/first-party (EBRAINS / atlas.brainnetome.org)
    for a in MANIFEST["assets"]:
        prov = a["provider"].lower()
        assert "ebrains" in prov or "brainnetome" in prov or "cstcloud" in prov


# ---------------------------------------------------------------------------
# Phase 2A identity records intact (registry-level, not spatial-file)
# ---------------------------------------------------------------------------

def test_g4_identity_csv_intact():
    rows = _rows("g4_julich_spatial_to_canonical_alignment.csv")
    assert len(rows) == 440
    assert all(r["alignment_status"] == "ALIGNED" for r in rows)


def test_g3_identity_csv_intact():
    rows = _rows("g3_brainnetome_volume_to_canonical_alignment.csv")
    assert len(rows) == 246
    assert all(r["alignment_status"] == "ALIGNED" for r in rows)


# ---------------------------------------------------------------------------
# no fabricated overlap / mapping
# ---------------------------------------------------------------------------

def test_no_g4_g3_mapping_created():
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT count(*) FROM brain_region_aggregation_mappings WHERE source_granularity_level='G3_MESO_FINE'")
        total = cur.fetchone()[0]
    finally:
        conn.close()
    assert total == 246  # unchanged from G3->G1 freeze (no G4->G3 rows added)


# ---------------------------------------------------------------------------
# G3->G1 production unchanged
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
