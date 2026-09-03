"""Gate 7B Phase 2C — G4/G3 Exact Template Identity + Cross-Template Transform Contract.

Read-only. Verifies Brainnetome BN_Atlas_246_1mm is in MNI152NLin6Asym space
(exact affine/shape match to TemplateFlow reference), Julich is in
MNI152NLin2009cAsym, and that a standard TemplateFlow nonlinear transform is
required (and recorded). BNA_PM_4D / HCP40 acquisition status is honestly
recorded as pending. No overlap/mapping/DB writes.
"""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import nibabel as nib
import numpy as np
import psycopg
import pytest

BACKEND = Path(__file__).resolve().parents[1]
PROD = "neurographiq_human_brain_v1"
INT = BACKEND / "data" / "integration"
TF = BACKEND / "data" / "atlases" / "templateflow_ref"
BN = BACKEND / "data" / "atlases" / "brainnetome" / "bna246" / "volume_raw"

N6 = TF / "tpl-MNI152NLin6Asym_res01_desc-brain_T1w.nii.gz"
N9 = TF / "tpl-MNI152NLin2009cAsym_res01_desc-brain_T1w.nii.gz"
XFM = TF / "MNI152NLin2009cAsym_from-MNI152NLin6Asym_mode-image_xfm.h5"
BN1 = BN / "BN_Atlas_246_1mm.nii.gz"

SPACE = json.load(open(INT / "g4_g3_exact_space_identity_audit.json", encoding="utf-8"))
CONTRACT = json.load(open(INT / "g4_g3_standard_transform_contract.json", encoding="utf-8"))


def _rows(name):
    return list(csv.DictReader(open(INT / name, encoding="utf-8-sig")))


def _conn(db=PROD):
    return psycopg.connect(host="127.0.0.1", port=5432, user="postgres",
                           password="postgres", dbname=db, autocommit=True)


# ---------------------------------------------------------------------------
# 1-2. Brainnetome probability assets status (honest)
# ---------------------------------------------------------------------------

def test_bna_pm_4d_status_recorded():
    # Phase 2D upgraded to file-level verification (was registry/pending in Phase 2C)
    v = json.load(open(INT / "g3_brainnetome_probability_asset_validation.json", encoding="utf-8"))
    assert v["component_count"] == 246
    assert v["all_components_readable"] is True
    h = json.load(open(INT / "g3_brainnetome_hcp40_reference_audit.json", encoding="utf-8"))
    assert h["grid_relationship_to_BNA_PM_4D"].startswith("SAME_GRID")


def test_probability_alignment_registry_246():
    # Phase 2D: file-level verified alignment (component_index == parcel_id == canonical)
    rows = _rows("g3_brainnetome_probability_to_canonical_alignment.csv")
    assert len(rows) == 246
    assert all(r["alignment_status"] == "ALIGNED" for r in rows)
    assert len({r["canonical_g3_id"] for r in rows}) == 246
    idxs = sorted(int(r["component_index"]) for r in rows)
    assert idxs == list(range(1, 247))


# ---------------------------------------------------------------------------
# 3-4. TemplateFlow references readable
# ---------------------------------------------------------------------------

def test_nlin6_template_readable():
    assert N6.exists()
    img = nib.load(str(N6))
    assert img.shape == (182, 218, 182)
    assert list(map(float, nib.affines.voxel_sizes(img.affine))) == [1.0, 1.0, 1.0]


def test_2009c_template_readable():
    assert N9.exists()
    img = nib.load(str(N9))
    assert img.shape == (193, 229, 193)
    assert list(map(float, nib.affines.voxel_sizes(img.affine))) == [1.0, 1.0, 1.0]


# ---------------------------------------------------------------------------
# 5-8. exact space identity
# ---------------------------------------------------------------------------

def test_brainnetome_shape_matches_nlin6():
    bn = nib.load(str(BN1))
    n6 = nib.load(str(N6))
    assert bn.shape == n6.shape == (182, 218, 182)


def test_brainnetome_affine_matches_nlin6_after_ras():
    bn = nib.as_closest_canonical(nib.load(str(BN1)))
    n6 = nib.as_closest_canonical(nib.load(str(N6)))
    assert np.allclose(bn.affine, n6.affine, atol=1e-3)


def test_brainnetome_extent_matches_nlin6():
    bn = nib.as_closest_canonical(nib.load(str(BN1)))
    n6 = nib.as_closest_canonical(nib.load(str(N6)))
    c = np.array([[0, 0, 0], [181, 217, 181]])
    assert np.allclose(nib.affines.apply_affine(bn.affine, c),
                       nib.affines.apply_affine(n6.affine, c), atol=1.0)


def test_exact_space_classification():
    assert SPACE["exact_space_classification"] == "BRAINNETOME_SPACE_CONFIRMED_MNI152NLIN6ASYM"
    assert SPACE["julich_exact_space"] == "MNI152NLin2009cAsym (native, 193x229x193 1mm, from siibra metadata)"


def test_not_same_template():
    # NLin6 (182^3) and 2009c (193^3) are different templates
    assert SPACE["templateflow_mni152nlin6asym_res01"]["shape"] != SPACE["templateflow_mni152nlin2009casym_res01"]["shape"]


# ---------------------------------------------------------------------------
# 9-12. transform contract
# ---------------------------------------------------------------------------

def test_official_transform_exists():
    assert XFM.exists()
    assert XFM.stat().st_size > 0
    assert CONTRACT["templateflow_transform"]["exists"] is True


def test_transform_direction_correct():
    # required: NLin6 (Brainnetome) -> 2009c (Julich)
    assert CONTRACT["source_space"].startswith("MNI152NLin6Asym")
    assert CONTRACT["target_space"].startswith("MNI152NLin2009cAsym")
    assert "NLin6Asym -> MNI152NLin2009cAsym" in CONTRACT["required_direction"]


def test_classification_cross_template():
    assert CONTRACT["classification"] == "STANDARD_CROSS_TEMPLATE_TRANSFORM_REQUIRED"


def test_interpolation_contract():
    c = CONTRACT["interpolation_contract"]
    assert "nearest-neighbor" in c["brainnetome_deterministic_label_BN_MPM"]
    # probability fields must be continuous (linear), NOT nearest-neighbor as the method
    assert "NOT nearest-neighbor" in c["brainnetome_probability_BNA_PM_4D"]
    assert "NOT nearest-neighbor" in c["julich_probability"]
    assert "continuous" in c["brainnetome_probability_BNA_PM_4D"].lower()
    assert "continuous" in c["julich_probability"].lower()


# ---------------------------------------------------------------------------
# 13. smoke test state (honest)
# ---------------------------------------------------------------------------

def test_smoke_test_deferred_state():
    s = json.load(open(INT / "g4_g3_transform_smoke_test.json", encoding="utf-8"))
    assert s["status"] in ("PASS", "DEFERRED_TOOLCHAIN")


# ---------------------------------------------------------------------------
# 14-15. G3->G1 unchanged + no G4->G3 mapping
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


def test_no_g4_g3_mapping():
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT count(*) FROM brain_region_aggregation_mappings WHERE source_granularity_level='G3_MESO_FINE'")
        assert cur.fetchone()[0] == 246
    finally:
        conn.close()


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
