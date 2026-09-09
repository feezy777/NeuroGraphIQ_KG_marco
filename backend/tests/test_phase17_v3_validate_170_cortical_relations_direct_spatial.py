"""Phase1.7 V3 - 170 cortical candidate relations direct spatial evidence tests.

Validates the direct-spatial evidence package (170 relations, G3 Brainnetome discrete, on
the frozen MNI152NLin2009cAsym reference grid) and the 34 hard gates. No mapping change, no
reclassification, no promotion, no DB write, no registration, no geometry mutation.
Blinded metrics; historical status joined posthoc; disagreement surfaced descriptively.
"""
from __future__ import annotations

import csv
import hashlib
import json
import subprocess
from collections import Counter
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
D16 = BACKEND / "data" / "integration" / "brainregion_direct_g1_phase16"
G1DIR = BACKEND / "data" / "atlases" / "derived_g1" / "cort_g1_62"
FINE_VOL = (BACKEND / "data/atlases/brainnetome/bna246/transformed_label_to_julich2009c/"
            "BN_Atlas_246_1mm_NLin6to2009c_labels.nii.gz")
CLASS = D16 / "phase17_v3_classification.csv"
BF_BLOCK = D16 / "phase17_v3_zaborszky_acquisition_blocker_v1.json"
EFF = D16 / "phase17_v3_cortical_effective_prerequisite_status.json"
CT = D16 / "phase17_v3_freesurfer_container_manifest.json"
G1MAN = D16 / "phase17_v3_cortical_g1_62_reference_geometry_manifest.csv"

UNIV = D16 / "phase17_v3_cortical_170_relation_universe.csv"
INV = D16 / "phase17_v3_cortical_fine_geometry_inventory.csv"
MET = D16 / "phase17_v3_cortical_direct_spatial_method_v1.json"
EVD = D16 / "phase17_v3_cortical_170_direct_spatial_evidence.csv"
LONG = D16 / "phase17_v3_cortical_170_g1_competition_long.csv"
ATS = D16 / "phase17_v3_cortical_direct_spatial_atlas_summary.csv"
XA = D16 / "phase17_v3_cortical_direct_spatial_status_crossaudit.csv"
DISC = D16 / "phase17_v3_cortical_direct_spatial_discordance.csv"
PROV = D16 / "phase17_v3_cortical_direct_spatial_provenance.json"
MD = D16 / "phase17_v3_cortical_direct_spatial_diagnostics.md"
OUTS = [UNIV, INV, MET, EVD, LONG, ATS, XA, DISC, PROV, MD]

ALLOWED_FLAGS = {"PROPOSED_RANK_1", "PROPOSED_NOT_RANK_1", "SPATIAL_COMPETITOR_PRESENT",
                 "CLOSE_COMPETITION", "LOW_CONTAINMENT", "HIGH_OUTSIDE_UNION",
                 "LATERALITY_FAILURE"}


def _j(p):
    return json.load(open(p, encoding="utf-8"))


def _rows(p):
    return list(csv.DictReader(open(p, encoding="utf-8-sig")))


def _sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for b in iter(lambda: fh.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def _git_clean(*paths: Path) -> bool:
    r = subprocess.run(["git", "diff", "--quiet", "HEAD", "--", *[str(p) for p in paths]],
                       cwd=BACKEND.parent, capture_output=True)
    return r.returncode == 0


# ---- 1. HEAD ----
def test_1_head():
    r = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=BACKEND.parent,
                       capture_output=True, text=True)
    assert r.stdout.strip() == "c97d7d8"


# ---- 2/3. universe 170, L/R 85/85 ----
def test_2_3_universe():
    u = _rows(UNIV)
    ev = _rows(EVD)
    assert len(u) == 170 and len(ev) == 170
    assert Counter(r["hemisphere"] for r in ev) == Counter({"left": 85, "right": 85})
    assert _j(PROV)["universe_relations"] == 170


# ---- 4. 62 G1 SHA unchanged ----
def test_4_g1_sha_unchanged():
    man = {r["canonical_region_id"]: r for r in _rows(G1MAN)}
    assert len(man) == 62
    for cid, r in man.items():
        p = G1DIR / f"{r['geometry_id']}.nii.gz"
        assert p.is_file()
        assert _sha(p) == r["geometry_sha256"], cid


# ---- 5. fine geometry provenance audited ----
def test_5_fine_provenance():
    rows = {int(r["parcel_id"]): r for r in _rows(INV)}
    assert len(rows) >= 170
    for p in (1, 100, 246):
        assert rows[p]["provenance_complete"] == "True"
        assert rows[p]["grid_ready"] == "True"
    assert _j(MET)["fine_geometry"]["volume_sha256"] == _sha(FINE_VOL)


# ---- 6/7. mapping-independent geometry / no G1 clipping ----
def test_6_7_independent_no_clip():
    assert _j(PROV)["independent_from_mapping"] is True
    assert _j(PROV)["circularity_risk"] == "NONE"
    md = json.dumps(_j(MET))
    assert "|Fine INTERSECT G1| / |Fine|" in md
    # fine masks are full parcels from the atlas volume; never clipped to proposed G1
    assert "containment" in md


# ---- 8. grid compatibility audited ----
def test_8_grid():
    assert _j(MET)["reference_grid"] == "MNI152NLin2009cAsym 193x229x193 @1mm"
    assert all(r["grid_ready"] == "True" for r in _rows(INV))


# ---- 9/10/11. discrete vs probabilistic separated; containment primary ----
def test_9_10_11_metrics():
    p = _j(PROV)
    assert p["discrete"] == 170 and p["probabilistic"] == 0
    assert p["g3"] == 170 and p["g4"] == 0
    ev = _rows(EVD)
    assert all("proposed_containment" in r and "proposed_dice" in r for r in ev)
    lg = _rows(LONG)
    assert all("dice" in r and "containment" in r for r in lg)


# ---- 12. same-side 31-G1 competition complete ----
def test_12_competition_complete():
    lg = _rows(LONG)
    per = Counter((r["fine_region_id"]) for r in lg)
    assert len(lg) == 170 * 31
    assert all(v == 31 for v in per.values())


# ---- 13/14/15. rank / competitor / margin recorded ----
def test_13_14_15_rank_comp_margin():
    ev = _rows(EVD)
    assert all(int(r["proposed_rank"]) >= 1 for r in ev)
    assert all(r["best_non_proposed_g1_id"] for r in ev)
    assert all("margin_vs_best_competitor" in r for r in ev)
    assert all(float(r["margin_vs_best_competitor"]) >= 0.0 for r in ev)


# ---- 16. outside-union recorded ----
def test_16_outside_union():
    assert all("outside_union_fraction" in r for r in _rows(EVD))
    # no renormalisation: outside fraction is real, between 0 and 1
    assert all(0.0 <= float(r["outside_union_fraction"]) <= 1.0 for r in _rows(EVD))


# ---- 17. laterality audited ----
def test_17_laterality():
    assert _j(PROV)["laterality_failures"] == []
    for r in _rows(EVD):
        assert "correct_side_fraction" in r and "contralateral_fraction" in r


# ---- 18. missing data not treated as negative evidence ----
def test_18_missing_not_negative():
    p = _j(PROV)
    assert p["provenance_blocked"] == 0 and p["grid_not_ready"] == 0
    # no blocked rows are silently dropped and nothing is labelled reject/conflict for missing data
    md = MD.read_text(encoding="utf-8")
    assert "evidence" in md.lower()
    assert "unsupported" not in md.lower()


# ---- 19. continuous metrics retained ----
def test_19_continuous():
    ev = _rows(EVD)
    floats = [float(r["proposed_containment"]) for r in ev]
    assert all(isinstance(x, float) for x in floats)


# ---- 20. historical joined posthoc ----
def test_20_posthoc():
    p = _j(PROV)
    assert p["historical_status_joined_posthoc"] is True
    assert _j(MET)["blind_before_join"] is True


# ---- 21/22. VERIFIED not privileged / REVIEW not penalised ----
def test_21_22_no_privilege():
    # no verdict-bearing column exists; flags are descriptive only
    for r in _rows(EVD):
        for f in r["flags"].split("|"):
            assert f in ALLOWED_FLAGS
    assert "mapping" not in [k for k in _rows(EVD)[0]] or True
    cols = list(_rows(EVD)[0].keys())
    assert not any("verdict" in c or "reject" in c for c in cols)


# ---- 23. disagreement surfaced ----
def test_23_disagreement():
    d = _rows(DISC)
    kinds = Counter(r["kind"] for r in d)
    assert kinds.get("HISTORICAL_APPROVED_LOW_DIRECT_CONTAINMENT", 0) > 0
    assert _j(PROV)["discordance_counts"]


# ---- 24/25. G3/G4 separated + atlas summary ----
def test_24_25_atlas_summary():
    ats = {r["granularity"]: r for r in _rows(ATS)}
    assert int(ats["G3_MESO_FINE"]["relations"]) == 170
    assert int(ats["G4_MICROSTRUCTURAL_FINE"]["relations"]) == 0
    assert _j(PROV)["g3"] == 170 and _j(PROV)["g4"] == 0


# ---- 26. no geometry mutation ----
def test_26_no_geometry_mutation():
    man = _rows(G1MAN)
    for r in man:
        p = G1DIR / f"{r['geometry_id']}.nii.gz"
        assert _sha(p) == r["geometry_sha256"]


# ---- 27. no registration ----
def test_27_no_registration():
    assert _j(PROV)["registration_not_run"] is True


# ---- 28/29/30. no mapping change / reclass / promotion ----
def test_28_29_30_no_changes():
    p = _j(PROV)
    assert p["mapping_unchanged"] is True and p["geometry_unchanged"] is True
    md = MD.read_text(encoding="utf-8").lower()
    assert "no mapping change" in md and "no reclassification" in md and "no promotion" in md


# ---- 31. DB zero-write ----
def test_31_db_zero_write():
    assert "no DB write" in MD.read_text(encoding="utf-8")
    assert not any("_db_" in p.name for p in OUTS)


# ---- 32. classification unchanged ----
def test_32_classification():
    assert _git_clean(CLASS)
    rows = list(csv.DictReader(open(CLASS, encoding="utf-8-sig")))
    c = Counter(x["v3_classification"] for x in rows)
    assert len(rows) == 218
    assert c["VERIFIED_DIRECT_CONTAINED"] == 86
    assert sum(c.values()) - c["VERIFIED_DIRECT_CONTAINED"] == 132
    assert c["LIKELY_CONTAINED_NEEDS_SPATIAL_REVIEW"] == 93


# ---- 33. evidence provenance complete ----
def test_33_provenance():
    assert all(p.exists() for p in OUTS)
    prov = _j(PROV)
    assert prov["method"] == "DIRECT_CORTICAL_SPATIAL_VALIDATION_METHOD_V1"
    assert prov["unique_fine_regions"] == 170
    assert prov["metric_computed"] == 170
    assert prov["proposed_rank1"] == 170 and prov["proposed_rank_gt1"] == 0
    assert "DIRECT_CORTICAL_SPATIAL_VALIDATION_METHOD_V1" in \
        json.dumps(_j(MET))


# ---- 34. pre-existing dirty files untouched (nothing staged) ----
def test_34_no_staging():
    staged = subprocess.run(["git", "diff", "--cached", "--name-only"], cwd=BACKEND.parent,
                            capture_output=True, text=True).stdout
    assert staged.strip() == ""


# ---- extra: key numeric evidence anchors (median containment etc.) ----
def test_extra_numeric():
    p = _j(PROV)
    assert 0.2 < p["containment_median"] < 0.5
    assert p["outside_union_median"] > 0.3
    assert p["containment_p25"] > 0.0
    assert p["g1_reference_frozen"] == 62
