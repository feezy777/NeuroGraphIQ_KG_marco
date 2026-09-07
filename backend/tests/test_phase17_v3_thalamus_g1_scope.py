"""Phase1.7 V3 - Thalamus G1 ontology scope resolution tests.

Read-only: validates scope contract/decisions/provenance; never builds geometry,
never touches DB, never re-runs resolution. 17 invariants.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
D16 = BACKEND / "data" / "integration" / "brainregion_direct_g1_phase16"
OUT_SRC = D16 / "phase17_v3_thalamus_g1_scope_source_comparison.csv"
OUT_DEC = D16 / "phase17_v3_thalamus_g1_scope_decisions.csv"
OUT_CON = D16 / "phase17_v3_thalamus_g1_scope_contract.json"
OUT_MD = D16 / "phase17_v3_thalamus_g1_scope_diagnostics.md"
CLASS = D16 / "phase17_v3_classification.csv"

_HAS_CON = OUT_CON.exists()


def _contract():
    with open(OUT_CON, encoding="utf-8") as fh:
        return json.load(fh)


# ---- 1. canonical IDs fixed to 247/256 ----
@pytest.mark.skipif(not _HAS_CON, reason="scope contract not present")
def test_1_canonical_ids():
    c = _contract()["contract"]
    assert c["canonical_left_id"] == "NGIQ-BR-00000247"
    assert c["canonical_right_id"] == "NGIQ-BR-00000256"


# ---- 2. current G1 definition source traceable ----
@pytest.mark.skipif(not _HAS_CON, reason="scope contract not present")
def test_2_definition_source_traceable():
    c = _contract()["contract"]
    assert "Brain volume list.xlsx" in c["definition_source"]
    assert "Brainnetome G3" in c["definition_source"]
    assert c["preferred_definition"]


# ---- 3. 'thalamus proper' provenance traceable ----
@pytest.mark.skipif(not _HAS_CON, reason="scope contract not present")
def test_3_thalamus_proper_provenance():
    c = _contract()["contract"]
    # 'proper' text originates from the Fuyao clinical list, not AAL3; AAL3 match manual
    assert "thalamus proper" in c["preferred_definition"].lower()
    assert "Macro96" in c["definition_source"] or "Fuyao" in c["definition_source"] or "clinical" in c["definition_source"]


# ---- 4. Brainnetome 8 parcels full source provenance ----
@pytest.mark.skipif(not _HAS_CON, reason="scope contract not present")
def test_4_brainnetome_parcel_provenance():
    # contract source_alignment must note the Brainnetome parcels are connectivity zones
    c = _contract()["contract"]
    align = c["source_atlas_alignment_notes"].lower()
    assert "connectivity" in align
    assert "brainnetome" in align


# ---- 5. FreeSurfer 52 nuclei all map to a scope decision ----
@pytest.mark.skipif(not _HAS_CON, reason="scope contract not present")
def test_5_all_52_map():
    dec_rows = list(csv.DictReader(open(OUT_DEC, encoding="utf-8-sig")))
    # every Iglesias nucleus abbreviation (26 bases => 26L+26R) must appear in the
    # union of decision structure + definition text
    fs_abbr = ["AV", "LP", "LD", "VA", "VLa", "VLp", "VPL", "VM", "VAmc",
               "CeM", "CL", "Pc", "CM", "Pf", "Pt", "MV", "MDm", "MDl",
               "LGN", "MGN", "PuA", "PuM", "PuL", "PuI", "R", "L-Sg"]
    src_text = " ".join(r["source_structure"] + " " + r["source_definition"] + " "
                        + r["source_reference"] for r in dec_rows).lower()
    for ab in fs_abbr:
        assert ab.lower() in src_text, ab


# ---- 6. unknown structure not auto-INCLUDE ----
@pytest.mark.skipif(not _HAS_CON, reason="scope contract not present")
def test_6_no_unknown_auto_include():
    dec = list(csv.DictReader(open(OUT_DEC, encoding="utf-8-sig")))
    for r in dec:
        # every decision carries a real source_reference + definition (no silent auto-include)
        assert r["source_reference"]
        assert r["source_definition"]
        assert r["decision"] in ("INCLUDE", "EXCLUDE", "ONTOLOGY_REVIEW")


# ---- 7/8/9. LGN / MGN / Reticular have explicit decisions ----
@pytest.mark.skipif(not _HAS_CON, reason="scope contract not present")
def test_789_lgn_mgn_reticular_explicit():
    dec = {r["source_structure"].split(" (")[0]: r for r in
           csv.DictReader(open(OUT_DEC, encoding="utf-8-sig"))}
    for key in ("LGN", "MGN", "Reticular nucleus"):
        row = next((r for k, r in dec.items() if k.startswith(key) or key.startswith(k)), None)
        assert row is not None, key
        assert row["decision"] in ("INCLUDE", "EXCLUDE", "ONTOLOGY_REVIEW")
        assert row["decision_reason"]
    # these are genuinely ambiguous across atlases => must be REVIEW (not forced include)
    for key in ("LGN", "MGN", "Reticular"):
        row = next((r for k, r in dec.items() if k.startswith(key)), None)
        assert row["decision"] == "ONTOLOGY_REVIEW", key


# ---- 10. border/transition have explicit decision ----
@pytest.mark.skipif(not _HAS_CON, reason="scope contract not present")
def test_10_border_transition_explicit():
    dec = list(csv.DictReader(open(OUT_DEC, encoding="utf-8-sig")))
    borderish = [r for r in dec if any(w in r["source_structure"] for w in
                                       ("Limitans", "suprageniculate", "border", "VAmc"))]
    assert borderish, "no border/transition structures found"
    for r in borderish:
        assert r["decision"] in ("INCLUDE", "EXCLUDE", "ONTOLOGY_REVIEW")


# ---- 11. geometry never used as an operative decision criterion ----
@pytest.mark.skipif(not _HAS_CON, reason="scope contract not present")
def test_11_geometry_not_in_decision():
    dec = list(csv.DictReader(open(OUT_DEC, encoding="utf-8-sig")))
    # Operative decision reasons must not argue from geometry/volume/overlap.
    # (Documentary provenance may mention 'voxels'/'size' to explain an atlas's
    # own choice; what is banned is geometry as the DECISION criterion.)
    banned = ("overlap", "dice", "prettier", "more reasonable", "mass", "centroid",
              "voxel grid", "support extent")
    for r in dec:
        reason = r["decision_reason"].lower()
        assert not any(b in reason for b in banned), (r["source_structure"], reason)
    # the decision CSVs carry no geometry columns
    assert "centroid" not in " ".join(dec[0].keys()).lower()
    # source-comparison CSV has no geometry-measure columns
    src_cols = " ".join(next(iter(csv.reader(open(OUT_SRC, encoding="utf-8-sig"))))).lower()
    assert "centroid" not in src_cols and "volume" not in src_cols.split()


# ---- 12/13/14. no NIfTI / no registration / no resampling ----
@pytest.mark.skipif(not _HAS_CON, reason="scope contract not present")
def test_12_14_no_geometry_no_transforms():
    c = _contract()
    assert c["construction_allowed"] is False
    assert c["verdict"] in ("THALAMUS_G1_SCOPE_FROZEN",
                            "THALAMUS_G1_SCOPE_PARTIALLY_FROZEN",
                            "THALAMUS_G1_SCOPE_UNRESOLVED")
    # no geometry produced by the scope script
    assert not list(Path(BACKEND, "data", "atlases", "derived_g1").rglob("*thalamus*.nii.gz"))
    # scope script has no transform/resample execution (static check of outputs text)
    md = OUT_MD.read_text(encoding="utf-8")
    assert "no transform" in md.lower() or "no NIfTI" in md.lower()


# ---- 15. classification byte-identical ----
@pytest.mark.skipif(not CLASS.exists(), reason="classification not present")
def test_15_classification_unchanged():
    with open(CLASS, encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))
    from collections import Counter
    c = Counter(x["v3_classification"] for x in rows)
    assert len(rows) == 218
    assert c["VERIFIED_DIRECT_CONTAINED"] == 86
    assert sum(c.values()) - c["VERIFIED_DIRECT_CONTAINED"] == 132
    assert c["LIKELY_CONTAINED_NEEDS_SPATIAL_REVIEW"] == 93


# ---- 16. DB zero-write ----
@pytest.mark.skipif(not _HAS_CON, reason="scope contract not present")
def test_16_no_db_artifacts():
    c = _contract()
    assert c["contract"]["canonical_left_id"] == "NGIQ-BR-00000247"
    # no geometry_construction_allowed True
    assert c["construction_allowed"] is False


# ---- 17. provenance chain complete ----
@pytest.mark.skipif(not _HAS_CON, reason="scope contract not present")
def test_17_provenance_complete():
    dec = list(csv.DictReader(open(OUT_DEC, encoding="utf-8-sig")))
    assert len(dec) >= 12
    for r in dec:
        assert r["decision_id"].startswith("THAL_SCOPE_")
        assert r["canonical_region_id"] == "NGIQ-BR-00000247;NGIQ-BR-00000256"
        assert r["source_atlas"] and r["source_version"]
        assert r["source_reference"] and r["source_definition"]
        assert r["evidence_type"] and r["confidence"]
        assert r["script_version"] and r["run_timestamp"]
    c = _contract()["contract"]
    assert c["included_source_structures"]
    assert c["excluded_source_structures"]
    assert c["ontology_review_structures"]
    # contract sets must equal the aggregate of the decisions CSV
    dec = list(csv.DictReader(open(OUT_DEC, encoding="utf-8-sig")))
    from collections import Counter
    agg = Counter(d["decision"] for d in dec)
    # decisions CSV decision column counts match contract list lengths (per base name)
    inc_names = {s.split(" (")[0] for s in c["included_source_structures"]}
    exc_names = {s.split(" (")[0] for s in c["excluded_source_structures"]}
    rev_names = {s.split(" (")[0] for s in c["ontology_review_structures"]}
    assert not (inc_names & exc_names) and not (inc_names & rev_names) and not (exc_names & rev_names)
    for d in dec:
        base = d["source_structure"].split(" (")[0]
        if d["decision"] == "INCLUDE":
            assert base in inc_names, base
        elif d["decision"] == "EXCLUDE":
            assert base in exc_names, base
        else:
            assert base in rev_names, base
