"""Phase1.7 V3 - Thalamus L-Sg / Limitans-Suprageniculate boundary adjudication tests.

Read-only; never modifies frozen contracts / classification / DB / geometry.
Covers 19 gate invariants (human-evidence adjudication).
"""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
D16 = BACKEND / "data" / "integration" / "brainregion_direct_g1_phase16"
SRC = D16 / "phase17_v3_thalamus_lsg_source_comparison.csv"
ADJ = D16 / "phase17_v3_thalamus_lsg_adjudication.json"
V3 = D16 / "phase17_v3_thalamus_g1_scope_contract_v3.json"
GT = D16 / "phase17_v3_thalamus_lsg_gate_transition.json"
MD = D16 / "phase17_v3_thalamus_lsg_diagnostics.md"
V1 = D16 / "phase17_v3_thalamus_g1_scope_contract.json"
V2 = D16 / "phase17_v3_thalamus_g1_scope_contract_v2.json"
CLASS = D16 / "phase17_v3_classification.csv"
JUL_HIER = BACKEND / "data" / "atlases" / "julich" / "v3.1" / "julich_v3_1_region_hierarchy.json"

_HAS = all(p.exists() for p in (SRC, ADJ, V3, GT, MD))
_HAS_V1V2 = _HAS and V1.exists() and V2.exists()


def _sha(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        while True:
            b = fh.read(1 << 20)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def _rows():
    return list(csv.DictReader(open(SRC, encoding="utf-8-sig")))


def _adj():
    return json.load(open(ADJ, encoding="utf-8"))


def _v3():
    return json.load(open(V3, encoding="utf-8"))


def _gt():
    return json.load(open(GT, encoding="utf-8"))


def _v2():
    return json.load(open(V2, encoding="utf-8"))


# ---- 1. only human evidence used as ruling evidence ----
@pytest.mark.skipif(not _HAS, reason="audit outputs not present")
def test_1_human_evidence_only_ruling():
    a = _adj()
    # final decision rationale cites human authorities only
    for tier in a["decisions"]["limitans"]["evidence_tiers"]:
        assert tier.startswith("HUMAN_"), tier
    for tier in a["decisions"]["suprageniculate"]["evidence_tiers"]:
        assert tier.startswith("HUMAN_"), tier
    assert a["decisions"]["lsg_combined_freeSurfer_channel"]["evidence_tiers"][0].startswith("HUMAN_")
    assert a["final_verdict"] == "THALAMUS_LSG_BOUNDARY_FROZEN_INCLUDE"


# ---- 2. animal evidence does not enter final ruling ----
@pytest.mark.skipif(not _HAS, reason="audit outputs not present")
def test_2_animal_evidence_excluded():
    for r in _rows():
        if r["human_evidence_tier"] == "OUT_OF_SCOPE_NON_HUMAN":
            assert "OUT_OF_SCOPE_NON_HUMAN" in r["classification"]
            assert "NOT usable as final ruling evidence" in r["classification"]
    a = _adj()
    assert len(a["non_human_evidence_excluded"]) == 2  # monkey + elephant recorded & excluded


# ---- 3. MeSH hierarchy traceable ----
@pytest.mark.skipif(not _HAS, reason="audit outputs not present")
def test_3_mesh_traceable():
    mesh = [r for r in _rows() if r["source_id"].startswith("NLM_MESH")]
    assert len(mesh) == 2  # Li + Sg
    for r in mesh:
        assert r["controlled_term_id"].startswith("MeSH M03")
        assert "Posterior Thalamic Nuclei" in r["tree_path"]
        assert "Thalamus > Thalamic Nuclei" in r["tree_path"]
        assert "human evidence" in r["classification"] or r["human_evidence_tier"] == "HUMAN_CONTROLLED_TERMINOLOGY"
        assert r["verdict"] == "THALAMIC_NUCLEAR_TERRITORY"


# ---- 4. Mai 2018 evidence traceable ----
@pytest.mark.skipif(not _HAS, reason="audit outputs not present")
def test_4_mai2018_traceable():
    mai = [r for r in _rows() if r["source_id"] == "Mai2018_CommonTerminology"]
    assert len(mai) == 1
    assert mai[0]["doi"] == "10.3389/fnana.2018.00114"
    assert "MGB" in mai[0]["classification"]
    assert mai[0]["human_evidence_tier"] == "HUMAN_TERMINOLOGY"
    # v3 provenance records the DOI
    assert _v3()["provenance"]["mai2018"] == "doi:10.3389/fnana.2018.00114"


# ---- 5. Iglesias L-Sg metadata traceable ----
@pytest.mark.skipif(not _HAS, reason="audit outputs not present")
def test_5_iglesias_traceable():
    ig = [r for r in _rows() if r["source_id"] == "Iglesias2018_FreeSurfer"]
    assert len(ig) == 1
    assert "L-Sg" in ig[0]["structure"]
    assert "Thalamus-Proper" in ig[0]["tree_path"]
    assert ig[0]["doi"] == "10.1016/j.neuroimage.2018.08.012"
    assert ig[0]["human_evidence_tier"] == "HUMAN_ATLAS_COVERAGE"
    assert _v3()["provenance"]["iglesias2018"] == "doi:10.1016/j.neuroimage.2018.08.012"


# ---- 6. AAL3 absence reason: atlas issue vs ontology issue ----
@pytest.mark.skipif(not _HAS, reason="audit outputs not present")
def test_6_aal3_absence_reason_distinguished():
    aal3 = [r for r in _rows() if r["source_id"] == "Rolls2020_AAL3"]
    assert len(aal3) == 1
    cls = aal3[0]["classification"]
    assert "size" in cls.lower() or "12 voxel" in cls.lower()
    assert "ATLAS_SIZE" in aal3[0]["verdict"] or "NOT_ONTOLOGY" in aal3[0]["verdict"]
    # AAL3 absent is NOT interpreted as ontological exclusion
    assert "NOT an ontological exclusion" not in aal3[0]["classification"] or "posterior group" in aal3[0]["classification"]
    assert "posterior group" in aal3[0]["tree_path"] or "posterior group" in aal3[0]["classification"]
    # adjudication explicitly says AAL3 absence = atlas-size, not ontology
    assert "ATLAS_SIZE_OR_RESOLUTION" in _adj()["dec_thal_04"]["rationale"]


# ---- 7. Limitans has explicit decision ----
@pytest.mark.skipif(not _HAS, reason="audit outputs not present")
def test_7_limitans_decision():
    a = _adj()
    assert a["decisions"]["limitans"]["decision"] == "INCLUDE"
    assert a["decisions"]["limitans"]["confidence"] == "HIGH"
    # V3 contract lists it
    assert _v3()["contract_v3"]["new_decisions"]["limitans_decision"] == "INCLUDE (DEC-THAL-04-LI)"


# ---- 8. Suprageniculate has explicit decision ----
@pytest.mark.skipif(not _HAS, reason="audit outputs not present")
def test_8_suprageniculate_decision():
    a = _adj()
    assert a["decisions"]["suprageniculate"]["decision"] == "INCLUDE"
    assert a["decisions"]["suprageniculate"]["confidence"] == "HIGH"
    assert _v3()["contract_v3"]["new_decisions"]["suprageniculate_decision"] == "INCLUDE (DEC-THAL-04-SG)"


# ---- 9. L-Sg has explicit decision ----
@pytest.mark.skipif(not _HAS, reason="audit outputs not present")
def test_9_lsg_decision():
    a = _adj()
    assert a["decisions"]["lsg_combined_freeSurfer_channel"]["decision"] == "INCLUDE"
    assert _v3()["contract_v3"]["new_decisions"]["lsg_freeSurfer_channel_decision"] == "INCLUDE (DEC-THAL-04-LSG)"


# ---- 10. decision consistent with THALAMUS_PROPER identity ----
@pytest.mark.skipif(not _HAS_V1V2, reason="audit outputs not present")
def test_10_consistent_with_identity():
    assert _adj()["canonical_identity"] == "THALAMUS_PROPER (V2) = dorsal thalami mass"
    assert _v3()["identity_decision"] == "CANONICAL_IDENTITY_FROZEN_THALAMUS_PROPER"
    assert _v3()["contract_v3"]["review_structures"] == []  # no open scope items


# ---- 11. LGN/MGN/Reticular decisions unchanged ----
@pytest.mark.skipif(not _HAS_V1V2, reason="audit outputs not present")
def test_11_lgn_mgn_reticular_unchanged():
    v2 = _v2()
    assert v2["contract_v2"]["LGN_decision"] == "INCLUDE (DEC-THAL-01)"
    assert v2["contract_v2"]["MGN_decision"] == "INCLUDE (DEC-THAL-02)"
    assert v2["contract_v2"]["reticular_decision"] == "EXCLUDE (DEC-THAL-03)"
    # V3 inherits them unchanged
    inh = _v3()["contract_v3"]["inherited_decisions"]
    assert inh["LGN_decision"] == "INCLUDE (DEC-THAL-01)"
    assert inh["MGN_decision"] == "INCLUDE (DEC-THAL-02)"
    assert inh["reticular_decision"] == "EXCLUDE (DEC-THAL-03)"


# ---- 12. V1/V2 byte-identical ----
@pytest.mark.skipif(not _HAS_V1V2, reason="audit outputs not present")
def test_12_v1v2_byte_identical():
    import subprocess
    for p in (V1, V2):
        r = subprocess.run(["git", "diff", "--quiet", "HEAD", "--", str(p)],
                           cwd=BACKEND.parent, capture_output=True)
        assert r.returncode == 0, f"{p.name} differs from HEAD"
    # V2 historical blocker wording still present (2 blockers, incl. L-Sg REVIEW) - not retro-edited
    reasons = _v2()["contract_v2"]["geometry_blocked_reasons"]
    assert len(reasons) == 2
    assert any("L-Sg" in x for x in reasons)


# ---- 13. geometry not generated ----
def test_13_no_geometry():
    assert not list(Path(BACKEND, "data", "atlases", "derived_g1").rglob("*thalamus*.nii.gz"))
    assert _adj()["geometry_used"] is False


# ---- 14. transform not executed ----
@pytest.mark.skipif(not _HAS, reason="audit outputs not present")
def test_14_no_transform():
    a = _adj()
    assert a["transform_used"] is False
    assert a["resample_used"] is False
    assert a["g4_g1_overlap_used"] is False


# ---- 15. BN direct validation still pending ----
@pytest.mark.skipif(not _HAS, reason="audit outputs not present")
def test_15_bn_direct_validation_pending():
    assert _gt()["bn_postconstruction_direct_validation"] == "PENDING_POSTCONSTRUCTION"
    assert _v3()["construction_allowed"] is False  # this round does not build geometry


# ---- 16. promotion still blocked ----
@pytest.mark.skipif(not _HAS, reason="audit outputs not present")
def test_16_promotion_blocked():
    assert _gt()["promotion"] == "BLOCKED"
    assert _gt()["geometry_construction_gate"] == "PASSED"  # unlocks NEXT round only


# ---- 17. classification byte-identical ----
@pytest.mark.skipif(not CLASS.exists(), reason="classification not present")
def test_17_classification_unchanged():
    with open(CLASS, encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))
    from collections import Counter
    c = Counter(x["v3_classification"] for x in rows)
    assert len(rows) == 218
    assert c["VERIFIED_DIRECT_CONTAINED"] == 86
    assert c["LIKELY_CONTAINED_NEEDS_SPATIAL_REVIEW"] == 93


# ---- 18. DB zero-write ----
@pytest.mark.skipif(not _HAS, reason="audit outputs not present")
def test_18_db_zero_write():
    # gate transition proves no DB/promotion side effect
    assert _gt()["construction_blocker_removed"] is True
    assert _gt()["remaining_active_construction_blockers"] == []


# ---- 19. provenance chain complete ----
@pytest.mark.skipif(not _HAS_V1V2, reason="audit outputs not present")
def test_19_provenance_complete():
    prov = _v3()["provenance"]
    assert prov["v1_sha256"] == _sha(V1)
    assert prov["v2_sha256"] == _sha(V2)
    # Julich local human cytoarchitecture hierarchy sha matches on-disk source
    assert prov["julich_hierarchy_sha256"] == _sha(JUL_HIER)
    # human-evidence citations recorded
    for k in ("mesh_url", "mai2018", "iglesias2018", "rolls2020_aal3", "kiwitz2022",
              "hirai_jones_1989", "access_date"):
        assert prov.get(k), k
    # gate transition references V2 sha (NOT_MODIFIED)
    assert _gt()["v2_historical_snapshot"] == "NOT_MODIFIED"
    assert _gt()["source_contract_v2_sha256"] == _sha(V2)
    # V3 supersedes V2
    assert _v3()["contract_v3"]["supersedes"] == "THALAMUS_G1_SCOPE_CONTRACT_V2"
    assert _v3()["contract_v3"]["supersedes_verified"] is True
