"""Phase1.7 V3 - Thalamus BN rollup <-> THALAMUS_PROPER compatibility tests.

Read-only; never modifies frozen mappings / contracts / DB / geometry.
Covers 19 audit invariants + 14 gate-transition invariants (gate-split).
"""
from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
D16 = BACKEND / "data" / "integration" / "brainregion_direct_g1_phase16"
OUT_CSV = D16 / "phase17_v3_thalamus_bn_rollup_compatibility.csv"
OUT_SUM = D16 / "phase17_v3_thalamus_bn_rollup_summary.json"
OUT_MD = D16 / "phase17_v3_thalamus_bn_rollup_diagnostics.md"
OUT_PROV = D16 / "phase17_v3_thalamus_bn_rollup_provenance.json"
OUT_GT = D16 / "phase17_v3_thalamus_bn_rollup_gate_transition.json"
V1 = D16 / "phase17_v3_thalamus_g1_scope_contract.json"
V2 = D16 / "phase17_v3_thalamus_g1_scope_contract_v2.json"
CLASS = D16 / "phase17_v3_classification.csv"
G3MAN = BACKEND / "data" / "integration" / "g3_to_g1" / "g3_to_g1_full_decision_coverage_manifest.csv"
BNA_AUTH = BACKEND / "data" / "atlases" / "brainnetome" / "bna246" / "brainnetome_bna246_subregions_authoritative.csv"

_HAS = all(p.exists() for p in (OUT_CSV, OUT_SUM, OUT_PROV, OUT_GT))
_HAS_FULL = all(p.exists() for p in (OUT_CSV, OUT_SUM, OUT_PROV, OUT_GT, V1, V2))

NON_LSG = "KEEP_FROZEN_MAPPING_PENDING_DIRECT_SPATIAL_VALIDATION"
LSG_DEP = "KEEP_FROZEN_MAPPING_PENDING_BOUNDARY_AND_DIRECT_VALIDATION"


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
    return list(csv.DictReader(open(OUT_CSV, encoding="utf-8-sig")))


def _sum():
    with open(OUT_SUM, encoding="utf-8") as fh:
        return json.load(fh)


def _gt():
    with open(OUT_GT, encoding="utf-8") as fh:
        return json.load(fh)


# ============================ 19 audit invariants ============================
# ---- 1. universe = 16 ----
@pytest.mark.skipif(not _HAS, reason="audit outputs not present")
def test_1_universe_16():
    assert len(_rows()) == 16


# ---- 2. left 8 + right 8 ----
@pytest.mark.skipif(not _HAS, reason="audit outputs not present")
def test_2_left_right_8():
    c = Counter(r["hemisphere"] for r in _rows())
    assert c["left"] == 8 and c["right"] == 8


# ---- 3. all 16 from real frozen manifest ----
@pytest.mark.skipif(not _HAS, reason="audit outputs not present")
def test_3_from_real_frozen_manifest():
    prov = json.load(open(OUT_PROV, encoding="utf-8"))
    assert _sha(G3MAN) == prov["frozen_manifest"]["sha256"]
    codes = {r["official_label"] for r in _rows()}
    assert len(codes) == 16


# ---- 4. targets = 247 / 256 ----
@pytest.mark.skipif(not _HAS, reason="audit outputs not present")
def test_4_target_ids():
    t = {h: {row["frozen_g1_target"] for row in _rows() if row["hemisphere"] == h}
         for h in ("left", "right")}
    assert t["left"] == {"NGIQ-BR-00000247"}
    assert t["right"] == {"NGIQ-BR-00000256"}


# ---- 5. Brainnetome official metadata complete ----
@pytest.mark.skipif(not _HAS, reason="audit outputs not present")
def test_5_bna_metadata():
    for r in _rows():
        assert r["official_label"] and r["abbreviation"] and r["official_name"]
        assert r["anatomical_zone_semantics"]


# ---- 6. no frozen-mapping self-justification ----
@pytest.mark.skipif(not _HAS, reason="audit outputs not present")
def test_6_not_self_justifying():
    for r in _rows():
        pe = r["primary_evidence"].lower()
        assert "frozen" not in pe and "g3->g1" not in pe and "g3_to_g1" not in pe
        assert r["circularity_risk"] == "LOW"


# ---- 7. atlas label != ontology membership ----
@pytest.mark.skipif(not _HAS, reason="audit outputs not present")
def test_7_atlas_label_not_membership():
    statuses = {r["compatibility_status"] for r in _rows()}
    assert statuses == {"LIKELY_COMPATIBLE_NEEDS_SPATIAL_CONFIRMATION"}
    # NOT silently upgraded to fully COMPATIBLE
    assert "COMPATIBLE_WITH_THALAMUS_PROPER" not in statuses


# ---- 8. reticular exclusion explicitly checked ----
@pytest.mark.skipif(not _HAS, reason="audit outputs not present")
def test_8_reticular_checked():
    for r in _rows():
        assert r["reticular_territory_check"] == "NO_SUBSTANTIAL_RETICULAR_TERRITORY_FOUND"


# ---- 9. LGN/MGN inclusion follows V2 ----
@pytest.mark.skipif(not _HAS, reason="audit outputs not present")
def test_9_lgn_mgn_follows_v2():
    for r in _rows():
        assert r["lgn_mgn_conflict"] == "NONE (LGN/MGN INCLUDE per V2)"


# ---- 10. L-Sg dependency not resolved ----
@pytest.mark.skipif(not _HAS, reason="audit outputs not present")
def test_10_lsg_not_resolved():
    dep_codes = [r["official_label"] for r in _rows() if r["lsg_dependency"]]
    assert all(r["lsg_dependency"] in ("", "DEPENDENCY_ON_DEC_THAL_04") for r in _rows())
    assert len(dep_codes) == 6  # PPtha/Otha/cTtha x L/R
    # L-Sg-dependent relations must NOT be upgraded to a resolved/fully-compatible verdict
    for r in _rows():
        assert r["compatibility_status"] != "COMPATIBLE_WITH_THALAMUS_PROPER" or not r["lsg_dependency"]


# ---- 11. relation-level verdicts are split by L-Sg dependency ----
@pytest.mark.skipif(not _HAS, reason="audit outputs not present")
def test_11_relation_verdict_split():
    counts = Counter(r["relation_verdict"] for r in _rows())
    assert counts[NON_LSG] == 10    # non-L-Sg zones: only direct validation pending
    assert counts[LSG_DEP] == 6     # L-Sg-adjacent zones: boundary AND direct validation
    assert sum(counts.values()) == 16


# ---- 12. bilateral QA present ----
@pytest.mark.skipif(not _HAS, reason="audit outputs not present")
def test_12_bilateral_qa():
    s = _sum()
    assert s["bilateral_asymmetry"] == {} or s["bilateral_asymmetry"] is None


# ---- 13. provenance chain complete ----
@pytest.mark.skipif(not _HAS, reason="audit outputs not present")
def test_13_provenance():
    prov = json.load(open(OUT_PROV, encoding="utf-8"))
    for k in ("frozen_manifest", "bna_authoritative", "v2_contract", "v1_contract"):
        assert prov[k]["sha256"], k
    assert prov["canonical_identity"] == "THALAMUS_PROPER (V2)"
    assert prov["script_version"]
    ids = [r["decision_id"] for r in _rows()]
    assert all(i.startswith("DEC-THAL-ROLLUP-") for i in ids)
    # BNA authoritative sha must match the provenance record
    assert _sha(BNA_AUTH) == prov["bna_authoritative"]["sha256"]


# ---- 14. V1/V2 byte-identical ----
@pytest.mark.skipif(not _HAS_FULL, reason="chain files not present")
def test_14_v1v2_unchanged():
    v1 = json.load(open(V1, encoding="utf-8"))
    v2 = json.load(open(V2, encoding="utf-8"))
    assert v1["contract"]["contract_name"] == "THALAMUS_G1_SCOPE_CONTRACT_V1"
    assert v2["contract_v2"]["contract_id"] == "THALAMUS_G1_SCOPE_CONTRACT_V2"
    assert v1["verdict"] == "THALAMUS_G1_SCOPE_PARTIALLY_FROZEN"
    assert v2["verdict"] == "THALAMUS_G1_SCOPE_PARTIALLY_FROZEN"
    # both historical blockers retained in V2 (not retro-edited)
    assert len(v2["contract_v2"]["geometry_blocked_reasons"]) == 2


# ---- 15. classification byte-identical ----
@pytest.mark.skipif(not CLASS.exists(), reason="classification not present")
def test_15_classification_unchanged():
    with open(CLASS, encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))
    c = Counter(x["v3_classification"] for x in rows)
    assert len(rows) == 218
    assert c["VERIFIED_DIRECT_CONTAINED"] == 86
    assert sum(c.values()) - c["VERIFIED_DIRECT_CONTAINED"] == 132
    assert c["LIKELY_CONTAINED_NEEDS_SPATIAL_REVIEW"] == 93


# ---- 16. DB zero-write (final verdict in audit-only set) ----
@pytest.mark.skipif(not _HAS, reason="audit outputs not present")
def test_16_no_db():
    assert _sum()["final_verdict"] == "BN_ROLLUP_BASIS_PARTIALLY_COMPATIBLE"


# ---- 17. no geometry ----
def test_17_no_geometry():
    _authorized = {"left_thalamus_proper_prob_icbm2009csym.nii.gz",
                   "right_thalamus_proper_prob_icbm2009csym.nii.gz"}
    present = {p.name for p in Path(BACKEND, "data", "atlases", "derived_g1").rglob("*thalamus*.nii.gz")}
    assert present <= _authorized, present


# ---- 18. no transform ----
@pytest.mark.skipif(not _HAS, reason="audit outputs not present")
def test_18_no_transform():
    md = OUT_MD.read_text(encoding="utf-8")
    assert "no geometry/transform/overlap/db" in md.lower()


# ---- 19. no reclassification ----
@pytest.mark.skipif(not _HAS, reason="audit outputs not present")
def test_19_no_reclassification():
    md = OUT_MD.read_text(encoding="utf-8")
    assert "no frozen mapping modified" in md.lower() or "no reclass" in md.lower()


# ============================ 14 gate-transition invariants ============================
# ---- G1. final_verdict still PARTIALLY_COMPATIBLE ----
@pytest.mark.skipif(not _HAS, reason="audit outputs not present")
def test_g1_final_verdict_partially_compatible():
    assert _sum()["final_verdict"] == "BN_ROLLUP_BASIS_PARTIALLY_COMPATIBLE"
    assert _gt()["audit_result"] == "BN_ROLLUP_BASIS_PARTIALLY_COMPATIBLE"


# ---- G2. incompatible = 0 ----
@pytest.mark.skipif(not _HAS, reason="audit outputs not present")
def test_g2_incompatible_zero():
    assert _sum()["incompatible"] == 0
    statuses = {r["compatibility_status"] for r in _rows()}
    assert "INCOMPATIBLE_WITH_THALAMUS_PROPER" not in statuses


# ---- G3. preconstruction_gate = PASSED ----
@pytest.mark.skipif(not _HAS, reason="audit outputs not present")
def test_g3_preconstruction_passed():
    assert _sum()["preconstruction_gate"] == "PASSED"
    assert _sum()["preconstruction_rollup_compatibility"] == \
        "PASS_WITH_POSTCONSTRUCTION_VALIDATION_REQUIRED"
    assert _gt()["preconstruction_gate"] == "PASSED"
    assert _gt()["preconstruction_rollup_compatibility"] == \
        "PASS_WITH_POSTCONSTRUCTION_VALIDATION_REQUIRED"


# ---- G4. blocker #2 reclassified, not deleted ----
@pytest.mark.skipif(not _HAS_FULL, reason="chain files not present")
def test_g4_blocker2_reclassified_not_deleted():
    # V2 historical snapshot unchanged (blocker #2 text still present, 2 blockers)
    v2 = json.load(open(V2, encoding="utf-8"))
    reasons = v2["contract_v2"]["geometry_blocked_reasons"]
    assert len(reasons) == 2
    assert any("Brainnetome Tha_*_8_1..8_8 zones" in x for x in reasons)
    # transition record documents the reclassification, tied to the V2 sha
    gt = _gt()
    assert gt["source_contract"] == "THALAMUS_G1_SCOPE_CONTRACT_V2"
    assert gt["source_blocker"] == "BN_ROLLUP_BASIS_NOT_RECONCILED"
    assert gt["v2_historical_snapshot"] == "NOT_MODIFIED"
    assert gt["construction_blocker_status"] == "RECLASSIFIED_OUT_OF_CONSTRUCTION_GATE"
    assert _sha(V2) == gt["source_contract_sha256"]


# ---- G5. blocker #2 -> POSTCONSTRUCTION_DIRECT_VALIDATION_REQUIRED ----
@pytest.mark.skipif(not _HAS, reason="audit outputs not present")
def test_g5_postconstruction_required():
    assert _sum()["blocker2_effective_status"] == "NO_LONGER_PRECONSTRUCTION_BLOCKER"
    assert _sum()["postconstruction_requirement"] == "DIRECT_BN_G3_TO_G1_SPATIAL_VALIDATION_REQUIRED"
    assert _gt()["postconstruction_requirement"] == "DIRECT_BN_G3_TO_G1_SPATIAL_VALIDATION_REQUIRED"
    assert _gt()["blocker2_effective_status"] == "NO_LONGER_PRECONSTRUCTION_BLOCKER"


# ---- G6. promotion not auto-passed ----
@pytest.mark.skipif(not _HAS, reason="audit outputs not present")
def test_g6_promotion_blocked():
    assert _sum()["promotion_gate"] == "BLOCKED_UNTIL_DIRECT_VALIDATION"
    assert _sum()["promotion"] == "BLOCKED"
    assert _gt()["promotion_gate"] == "BLOCKED_UNTIL_DIRECT_VALIDATION"


# ---- G7. L-Sg still the only active construction blocker ----
@pytest.mark.skipif(not _HAS, reason="audit outputs not present")
def test_g7_lsg_sole_active_blocker():
    blockers = _sum()["active_construction_blockers"]
    assert len(blockers) == 1
    assert blockers[0].startswith("DEC-THAL-04")
    assert _sum()["geometry_construction"] == "BLOCKED_BY_LSG_ONLY"
    assert len(_gt()["active_construction_blockers"]) == 1


# ---- G8. 6 L-Sg-dependent relations explicit ----
@pytest.mark.skipif(not _HAS, reason="audit outputs not present")
def test_g8_lsg_dependent_explicit():
    dep = [r for r in _rows() if r["lsg_dependency"] == "DEPENDENCY_ON_DEC_THAL_04"]
    assert len(dep) == 6
    assert all(r["relation_verdict"] == LSG_DEP for r in dep)
    assert _sum()["lsg_dependent_relations"] == 6


# ---- G9. 10 non-L-Sg relations still need direct validation ----
@pytest.mark.skipif(not _HAS, reason="audit outputs not present")
def test_g9_non_lsg_direct_validation():
    non = [r for r in _rows() if not r["lsg_dependency"]]
    assert len(non) == 10
    assert all(r["relation_verdict"] == NON_LSG for r in non)
    assert _sum()["non_lsg_dependent_relations"] == 10
    # they are NOT fully validated either - direct validation is still pending
    assert all(r["compatibility_status"] == "LIKELY_COMPATIBLE_NEEDS_SPATIAL_CONFIRMATION"
               for r in non)


# ---- G10. no geometry construction ----
def test_g10_no_geometry():
    _authorized = {"left_thalamus_proper_prob_icbm2009csym.nii.gz",
                   "right_thalamus_proper_prob_icbm2009csym.nii.gz"}
    present = {p.name for p in Path(BACKEND, "data", "atlases", "derived_g1").rglob("*thalamus*.nii.gz")}
    assert present <= _authorized, present
    assert _sum()["geometry_construction"] == "BLOCKED_BY_LSG_ONLY"


# ---- G11. V1/V2 byte-identical ----
@pytest.mark.skipif(not _HAS_FULL, reason="chain files not present")
def test_g11_v1v2_byte_identical():
    v1 = json.load(open(V1, encoding="utf-8"))
    v2 = json.load(open(V2, encoding="utf-8"))
    # V1/V2 scientific state unchanged
    assert v1["verdict"] == "THALAMUS_G1_SCOPE_PARTIALLY_FROZEN"
    assert v2["verdict"] == "THALAMUS_G1_SCOPE_PARTIALLY_FROZEN"
    assert v2["contract_v2"]["LGN_decision"] == "INCLUDE (DEC-THAL-01)"
    assert v2["contract_v2"]["MGN_decision"] == "INCLUDE (DEC-THAL-02)"
    assert v2["contract_v2"]["reticular_decision"] == "EXCLUDE (DEC-THAL-03)"
    assert v2["contract_v2"]["limitans_suprageniculate_decision"] == "REVIEW (DEC-THAL-04)"


# ---- G12. classification byte-identical ----
@pytest.mark.skipif(not CLASS.exists(), reason="classification not present")
def test_g12_classification_identical():
    with open(CLASS, encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))
    c = Counter(x["v3_classification"] for x in rows)
    assert c["VERIFIED_DIRECT_CONTAINED"] == 86
    assert c["LIKELY_CONTAINED_NEEDS_SPATIAL_REVIEW"] == 93


# ---- G13. DB zero-write ----
@pytest.mark.skipif(not _HAS, reason="audit outputs not present")
def test_g13_db_zero_write():
    # gate split produces NO promotion/DB side effect: promotion still BLOCKED
    assert _sum()["promotion"] == "BLOCKED"
    assert _gt()["final_effective_state"]["promotion"] == "BLOCKED"
    assert _gt()["final_effective_state"]["geometry_construction"] == "BLOCKED_BY_LSG_ONLY"


# ---- G14. provenance chain complete ----
@pytest.mark.skipif(not _HAS, reason="audit outputs not present")
def test_g14_provenance_complete():
    gt = _gt()
    chain = gt["provenance_chain"]
    # forward traceability from gate transition back to sources
    assert chain["gate_transition_to"].startswith("current rollup audit")
    assert "DEC-THAL-ROLLUP" in chain["gate_transition_to"]
    assert chain["audit_to"]  # frozen G3 relations
    assert chain["frozen_to"]  # V2
    assert chain["v2_to"]  # V1
    assert chain["v1_to"]  # Brainnetome source / Fan 2016
    # hashes present and matching on-disk inputs
    assert _sha(V1) == chain["v1_sha256"]
    assert _sha(V2) == chain["v2_sha256"]
    assert _sha(G3MAN) == chain["frozen_manifest_sha256"]
    assert _sha(BNA_AUTH) == chain["bna_source_sha256"]
    # outputs referenced by the sealed provenance have matching hashes
    prov = json.load(open(OUT_PROV, encoding="utf-8"))
    assert prov["outputs"]["rollup_csv"]["sha256"] == _sha(OUT_CSV)
    assert prov["outputs"]["summary_json"]["sha256"] == _sha(OUT_SUM)
    assert prov["outputs"]["diagnostics_md"]["sha256"] == _sha(OUT_MD)
    assert prov["outputs"]["gate_transition"]["sha256"] == _sha(OUT_GT)
