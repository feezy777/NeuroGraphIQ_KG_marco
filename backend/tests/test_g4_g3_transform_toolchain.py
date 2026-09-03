"""Gate 7B Phase 2E — G4→G3 standard nonlinear transform toolchain + smoke.

Read-only. Verifies the SimpleITK toolchain artifact (direction lock by
template agreement), the single-component source→target smoke that PASSED
(component 1 = SFG_L_7_1, left), that the smoke honored the ONE-component
scope (no 246-component batch), output grid == Julich MNI152NLin2009cAsym
native, raw 0-100 / normalized 0-1, no NaN/Inf, no hemisphere flip, that the
contract was updated, raw source assets unchanged, and G3→G1 production still
frozen (246/246/246/172) with no G4→G3 mapping added. No DB writes.
"""

from __future__ import annotations

import glob
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
SMOKE_DIR = INT / "qa" / "g4_g3_transform_smoke"
OUT = BACKEND / "data" / "atlases" / "brainnetome" / "bna246" / "transformed_to_julich2009c_smoke"
JULICH = BACKEND / "data" / "atlases" / "julich" / "v3.1" / "spatial_raw" / "probability_maps"
BNA_VOL = BACKEND / "data" / "atlases" / "brainnetome" / "bna246" / "volume_raw"
SCRIPT = BACKEND / "scripts" / "transform_brainnetome_to_julich2009c.py"

PM = BNA_VOL / "BNA_PM_4D.nii.gz"
HCP = BNA_VOL / "HCP40_MNI_1.25mm.nii.gz"
BN1 = BNA_VOL / "BN_Atlas_246_1mm.nii.gz"

VAL = json.load(open(INT / "g4_g3_transform_toolchain_validation.json", encoding="utf-8"))
LOCK = json.load(open(INT / "g4_g3_transform_direction_lock.json", encoding="utf-8"))
CONTRACT = json.load(open(INT / "g4_g3_standard_transform_contract.json", encoding="utf-8"))
PROV = json.load(open(SMOKE_DIR / "smoke_comp001_provenance.json", encoding="utf-8"))

RAW_OUT = OUT / "BNA_PM4D_comp001_NLin6to2009c_raw_percent.nii.gz"
PROB_OUT = OUT / "BNA_PM4D_comp001_NLin6to2009c_probability.nii.gz"


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _conn(db=PROD):
    return psycopg.connect(host="127.0.0.1", port=5432, user="postgres",
                           password="postgres", dbname=db, autocommit=True)


# ---------------------------------------------------------------------------
# 1-4. toolchain script + direction lock
# ---------------------------------------------------------------------------

def test_toolchain_script_exists_and_modes():
    assert SCRIPT.exists()
    txt = SCRIPT.read_text(encoding="utf-8")
    # Phase 2E single smoke + Phase 2F batch both present; smoke core reused
    assert "--component" in txt
    assert "--all" in txt
    assert "sitk.sitkLinear" in txt          # Linear interpolation core unchanged
    assert "as_stored" in txt                # direction contract preserved
    # output dir separation: smoke dir != batch dir
    assert "transformed_to_julich2009c_smoke" in txt
    assert "transformed_to_julich2009c" in txt
    assert "_smoke" in txt and "BATCH_PROB" in txt


def test_direction_lock_recorded():
    assert LOCK["result"]["winning_direction"] == "as_stored (no inverse)"
    fwd = LOCK["result"]["forward_as_stored"]
    assert fwd["brain_dice_vs_2009c_template"] > 0.9
    assert fwd["ok"] is True


def test_direction_lock_no_inverse_required():
    # SimpleITK GetInverse throws on the displacement composite; as-stored is correct
    assert "GetInverse() throws" in LOCK["result"]["inverse"]["note"]
    assert "as_stored" in VAL["direction_lock_summary"]["decision"]


def test_validation_readiness_batch_ready():
    assert VAL["readiness"] == "READY_FOR_G4_G3_BATCH_TRANSFORM"
    assert VAL["all_checks_pass"] is True
    # scope honored: single-component smoke only
    assert "OUT OF SCOPE" in VAL["gate_scope_note"].upper()


# ---------------------------------------------------------------------------
# 5-7. smoke output files exist, exactly one component (scope)
# ---------------------------------------------------------------------------

def test_output_files_exist():
    assert RAW_OUT.exists() and PROB_OUT.exists()
    assert RAW_OUT.stat().st_size > 0 and PROB_OUT.stat().st_size > 0


def test_smoke_scope_one_component_only():
    raws = sorted(glob.glob(str(OUT / "BNA_PM4D_comp*_NLin6to2009c_raw_percent.nii.gz")))
    probs = sorted(glob.glob(str(OUT / "BNA_PM4D_comp*_NLin6to2009c_probability.nii.gz")))
    # only component 001 was transformed (NOT the 246 batch)
    assert [Path(p).name for p in raws] == [RAW_OUT.name]
    assert [Path(p).name for p in probs] == [PROB_OUT.name]


def test_output_sha_matches_validation_artifact():
    assert VAL["smoke"]["output_raw_percent_sha256"] == _sha(RAW_OUT)
    assert VAL["smoke"]["output_normalized_probability_sha256"] == _sha(PROB_OUT)


# ---------------------------------------------------------------------------
# 8-10. output grid == Julich MNI152NLin2009cAsym native
# ---------------------------------------------------------------------------

def _julich_ref():
    return nib.load(sorted(JULICH.glob("*.nii.gz"))[0])


def test_output_grid_matches_julich_native():
    ref = _julich_ref()
    out = nib.load(str(RAW_OUT))
    assert out.shape == ref.shape == (193, 229, 193)
    assert list(map(float, nib.affines.voxel_sizes(out.affine))) == [1.0, 1.0, 1.0]
    assert np.allclose(out.affine, nib.as_closest_canonical(ref).affine, atol=1e-3)
    assert tuple(nib.aff2axcodes(out.affine)) == ("R", "A", "S")


def test_output_no_nan_inf():
    for p in (RAW_OUT, PROB_OUT):
        d = nib.load(str(p)).get_fdata()
        assert not np.isnan(d).any()
        assert not np.isinf(d).any()


def test_output_ranges_preserved():
    r = nib.load(str(RAW_OUT)).get_fdata()   # raw percent
    n = nib.load(str(PROB_OUT)).get_fdata()  # normalized 0-1
    assert r.min() >= 0 and r.max() <= 100.0
    assert (r != 0).sum() > 0
    assert n.min() >= 0 and n.max() <= 1.0


# ---------------------------------------------------------------------------
# 11. hemisphere preserved (left SFG parcel stays left) + centroid in brain
# ---------------------------------------------------------------------------

def test_hemisphere_no_flip():
    out = nib.load(str(RAW_OUT))
    d = out.get_fdata()
    coords = np.argwhere(d > 0).astype(np.float64)
    vals = d[d > 0]
    com = nib.affines.apply_affine(out.affine, (coords.T @ vals) / vals.sum())
    assert com[0] < 0  # SFG_L_7_1 is LEFT -> x must stay negative (no flip)
    assert VAL["smoke"]["checks"]["no_hemisphere_flip"] is True


def test_centroid_inside_2009c_brain_recorded():
    assert VAL["smoke"]["checks"]["centroid_within_2009c_brain"] is True


# ---------------------------------------------------------------------------
# 12-14. provenance + identity of smoke component
# ---------------------------------------------------------------------------

def test_smoke_component_identity():
    assert PROV["status"] == "PASS"
    assert PROV["component_index"] == 1
    assert PROV["canonical_name"] == "SFG_L_7_1"
    assert PROV["hemisphere"] == "left"
    assert PROV["canonical_g3_id"] == "NGIQ-BR-00000001"
    assert PROV["tool"].startswith("SimpleITK")
    assert "no GetInverse" in PROV["transform_direction"]
    assert PROV["interpolation"] == "Linear"
    assert PROV["background"] == 0.0
    assert all(PROV["checks"].values())


def test_provenance_source_and_transform_sha():
    assert PROV["source_sha256"] == _sha(PM)
    assert PROV["transform_sha256"] == _sha(BACKEND / "data" / "atlases" / "templateflow_ref"
                                           / "MNI152NLin2009cAsym_from-MNI152NLin6Asym_mode-image_xfm.h5")


def test_scale_documented_not_normalized():
    assert "0-100 percent" in PROV["source_scale"]
    assert "NOT normalized" in PROV["source_scale"]


# ---------------------------------------------------------------------------
# 15. contract updated (existing keys preserved)
# ---------------------------------------------------------------------------

def test_contract_classification_and_interpolation_preserved():
    assert CONTRACT["classification"] == "STANDARD_CROSS_TEMPLATE_TRANSFORM_REQUIRED"
    ic = CONTRACT["interpolation_contract"]
    assert "nearest-neighbor" in ic["brainnetome_deterministic_label_BN_MPM"]
    assert "continuous" in ic["brainnetome_probability_BNA_PM_4D"].lower()
    assert "continuous" in ic["julich_probability"].lower()
    assert CONTRACT["templateflow_transform"]["exists"] is True
    assert CONTRACT["brainnetome_source_asset_status"] == "FILE_LEVEL_VERIFIED"


def test_contract_execution_toolchain_updated():
    et = CONTRACT["execution_toolchain"]
    assert et["simpletk"].startswith("installed 2.5.6")
    assert et["direction_lock"].startswith("AS_STORED_NO_INVERSE")
    assert "RESOLVED" in et["plan"]
    assert CONTRACT["toolchain_smoke"]["status"] == "PASS"


# ---------------------------------------------------------------------------
# 16. raw source assets unchanged
# ---------------------------------------------------------------------------

def test_raw_source_assets_unchanged():
    # smoke only ever reads the source; it must be bit-identical to the frozen
    # file-level hashes recorded in Phase 2D
    assert _sha(PM) == "b1318517f61d08f714c25e55ee580eb8a487c0b7ab1ddbcc7eac852e4e97f020"
    assert _sha(HCP) == "2843cb60b5d487593e40a5bbf0555d7034bfedb21a2f78fb4e84a84cc34b5552"


# ---------------------------------------------------------------------------
# 17-18. G3->G1 unchanged + no G4->G3 mapping
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


def test_no_g4_g3_mapping_created():
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT count(*) FROM brain_region_aggregation_mappings WHERE source_granularity_level='G3_MESO_FINE'")
        total = cur.fetchone()[0]
    finally:
        conn.close()
    assert total == 246  # only the frozen G3->G1 rows; no G4->G3 rows


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
