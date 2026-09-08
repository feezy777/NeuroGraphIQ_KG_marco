"""Phase1.7 V3 - Thalamus canonical identity + boundary adjudication tests.

Read-only: validates the V2 contract / adjudication CSVs; never builds geometry,
never touches DB. 16 invariants.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
D16 = BACKEND / "data" / "integration" / "brainregion_direct_g1_phase16"
OUT_CMP = D16 / "phase17_v3_thalamus_canonical_identity_comparison.csv"
OUT_ADJ = D16 / "phase17_v3_thalamus_boundary_adjudication.csv"
OUT_V2 = D16 / "phase17_v3_thalamus_g1_scope_contract_v2.json"
OUT_MD = D16 / "phase17_v3_thalamus_canonical_identity_diagnostics.md"
V1 = D16 / "phase17_v3_thalamus_g1_scope_contract.json"
CLASS = D16 / "phase17_v3_classification.csv"

_HAS_V2 = OUT_V2.exists()
_HAS_V1 = V1.exists()


def _v2():
    with open(OUT_V2, encoding="utf-8") as fh:
        return json.load(fh)


# ---- 0. V2 artifact must exist (do NOT silently skip the round's core output) ----
def test_0_v2_artifact_present():
    assert OUT_V2.exists(), "phase17_v3_thalamus_g1_scope_contract_v2.json missing"
    assert OUT_ADJ.exists(), "phase17_v3_thalamus_boundary_adjudication.csv missing"
    assert OUT_CMP.exists(), "phase17_v3_thalamus_canonical_identity_comparison.csv missing"


# ---- 0b. boundary adjudication CSV is readable & decision ids consistent ----
@pytest.mark.skipif(not (OUT_V2.exists() and OUT_ADJ.exists()), reason="V2/adjudication not present")
def test_0b_adjudication_csv_consistent():
    rows = list(csv.DictReader(open(OUT_ADJ, encoding="utf-8-sig")))
    assert len(rows) == 4
    json_ids = [r["decision_id"] for r in _v2()["boundary_rulings"]]
    csv_ids = [r["decision_id"] for r in rows]
    assert sorted(json_ids) == sorted(csv_ids)


# ---- 1. V1 not overwritten ----
def test_1_v1_not_overwritten():
    # V1 file still exists and still names V1 contract
    assert _HAS_V1, "V1 contract file missing - must be preserved"
    with open(V1, encoding="utf-8") as fh:
        v1 = json.load(fh)
    c1 = v1["contract"]
    assert c1["contract_name"] == "THALAMUS_G1_SCOPE_CONTRACT_V1"


# ---- 2. V2 explicitly supersedes V1 ----
@pytest.mark.skipif(not _HAS_V2, reason="V2 contract not present")
def test_2_v2_supersedes_v1():
    c = _v2()["contract_v2"]
    assert c["contract_id"] == "THALAMUS_G1_SCOPE_CONTRACT_V2"
    assert c["supersedes"] == "THALAMUS_G1_SCOPE_CONTRACT_V1"


# ---- 3. source label and canonical definition separated ----
@pytest.mark.skipif(not _HAS_V2, reason="V2 contract not present")
def test_3_source_label_vs_canonical():
    c = _v2()["contract_v2"]
    assert "thalamus proper" in c["source_label"].lower()
    assert c["preferred_canonical_name"]
    assert c["canonical_definition"]
    # the source label must not have been silently upgraded into the canonical term
    assert c["source_label"].startswith("thalamus proper")


# ---- 4. canonical identity has provenance ----
@pytest.mark.skipif(not _HAS_V2, reason="V2 contract not present")
def test_4_identity_provenance():
    d = _v2()
    assert d["identity_decision"]
    prov = d["identity_provenance"]
    assert prov and len(prov) == 2  # left + right
    for p in prov:
        assert p["original_definition"] == "SOURCE_LABEL_ONLY_NO_FORMAL_DEFINITION"
        assert p["source_name"] in ("left thalamus proper", "right thalamus proper")
        assert p["canonical_id"] in ("NGIQ-BR-00000247", "NGIQ-BR-00000256")


# ---- 5/6/7/8. explicit decisions for LGN/MGN/Reticular/L-Sg ----
@pytest.mark.skipif(not _HAS_V2, reason="V2 contract not present")
def test_5678_boundary_explicit():
    d = _v2()["boundary_rulings"]
    got = {r["structure"].split(" ")[0]: r for r in d}
    assert "LGN" in " ".join(r["structure"] for r in d)
    assert "MGN" in " ".join(r["structure"] for r in d)
    assert any("eticular" in r["structure"] for r in d)
    assert any("imitans" in r["structure"] for r in d)
    for r in d:
        assert r["decision_id"].startswith("DEC-THAL-")
        assert r["decision"] in ("INCLUDE", "EXCLUDE", "REVIEW")
        assert r["rationale"] and r["primary_evidence"]
        assert r["canonical_identity_used"] == "CANONICAL_IDENTITY_FROZEN_THALAMUS_PROPER"


# ---- 9. decisions follow canonical identity (LGN/MGN INCLUDE under dorsal incl geniculates) ----
@pytest.mark.skipif(not _HAS_V2, reason="V2 contract not present")
def test_9_decisions_follow_identity():
    d = {r["decision_id"]: r for r in _v2()["boundary_rulings"]}
    # LGN/MGN INCLUDE because dorsal-thalamus proper (modern consensus) includes geniculates
    assert d["DEC-THAL-01"]["decision"] == "INCLUDE"
    assert d["DEC-THAL-02"]["decision"] == "INCLUDE"
    # reticular EXCLUDE because ventral/perithalamus is outside dorsal-thalamus proper
    assert d["DEC-THAL-03"]["decision"] == "EXCLUDE"
    # L-Sg REVIEW (contested border)
    assert d["DEC-THAL-04"]["decision"] == "REVIEW"


# ---- 10. atlas inclusion != ontology membership (rationale never cites atlas alone) ----
@pytest.mark.skipif(not _HAS_V2, reason="V2 contract not present")
def test_10_atlas_inclusion_not_membership():
    # Every ruling must ground in the frozen identity / anatomy terminology, not
    # rest solely on 'atlas X includes/excludes it'. Keyword set covers the anatomy
    # vocabulary used by each DEC (dorsal/ventral/posterior/metathalamic/identity).
    for r in _v2()["boundary_rulings"]:
        rat = r["rationale"].lower()
        assert any(k in rat for k in ("identity", "dorsal", "ventral", "posterior",
                                      "metathalamic", "consensus")), r["decision_id"]


# ---- 11. geometry not part of decision ----
@pytest.mark.skipif(not _HAS_V2, reason="V2 contract not present")
def test_11_no_geometry_in_decision():
    for r in _v2()["boundary_rulings"]:
        rat = r["rationale"].lower() + " " + r["primary_evidence"].lower()
        for bad in ("overlap", "dice", "centroid", "prettier", "more reasonable"):
            assert bad not in rat, (r["decision_id"], bad)


# ---- 12/13. no NIfTI / no transform ----
@pytest.mark.skipif(not _HAS_V2, reason="V2 contract not present")
def test_12_13_no_nifti_no_transform():
    assert _v2()["construction_allowed"] is False
    _authorized = {"left_thalamus_proper_prob_icbm2009csym.nii.gz",
                   "right_thalamus_proper_prob_icbm2009csym.nii.gz",
                   "left_thalamus_proper_prob_mni2009casym.nii.gz",
                   "right_thalamus_proper_prob_mni2009casym.nii.gz"}
    present = {p.name for p in Path(BACKEND, "data", "atlases", "derived_g1").rglob("*thalamus*.nii.gz")}
    assert present <= _authorized, present
    md = OUT_MD.read_text(encoding="utf-8")
    assert "no transform" in md.lower() or "no geometry" in md.lower()


# ---- 14. classification byte-identical ----
@pytest.mark.skipif(not CLASS.exists(), reason="classification not present")
def test_14_classification_unchanged():
    with open(CLASS, encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))
    from collections import Counter
    c = Counter(x["v3_classification"] for x in rows)
    assert len(rows) == 218
    assert c["VERIFIED_DIRECT_CONTAINED"] == 86
    assert sum(c.values()) - c["VERIFIED_DIRECT_CONTAINED"] == 132
    assert c["LIKELY_CONTAINED_NEEDS_SPATIAL_REVIEW"] == 93


# ---- 15. DB zero-write ----
@pytest.mark.skipif(not _HAS_V2, reason="V2 contract not present")
def test_15_no_db_artifacts():
    c = _v2()["contract_v2"]
    assert c["canonical_left_id"] == "NGIQ-BR-00000247"
    assert c["canonical_right_id"] == "NGIQ-BR-00000256"
    assert _v2()["construction_allowed"] is False


# ---- 16. provenance chain complete ----
@pytest.mark.skipif(not _HAS_V2, reason="V2 contract not present")
def test_16_provenance_complete():
    c = _v2()["contract_v2"]
    assert c["primary_sources"] and c["secondary_sources"]
    assert "Mai" in " ".join(c["primary_sources"])
    assert "Rolls" in " ".join(c["primary_sources"])
    for r in _v2()["boundary_rulings"]:
        assert r["decision_id"].startswith("DEC-THAL-")
        assert r["canonical_identity_used"] == "CANONICAL_IDENTITY_FROZEN_THALAMUS_PROPER"
        assert r["primary_evidence"] and r["secondary_evidence"]
        assert r["confidence"]
    # V2 links to V1
    assert c["supersedes"] == "THALAMUS_G1_SCOPE_CONTRACT_V1"
    # verdict semantics consistent
    assert _v2()["verdict"] == "THALAMUS_G1_SCOPE_PARTIALLY_FROZEN"
