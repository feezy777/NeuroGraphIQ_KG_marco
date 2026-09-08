"""Phase1.7 V3 - Thalamus postconstruction gate closure + final freeze tests.

Validates the supersession (DEC-THAL-DIRECT-02-S1), effective 16-relation state,
postconstruction gate closure and THALAMUS_PHASE17_FINAL_FREEZE_V1. Read-only;
never modifies DB / lifecycle / classification / promotion; no commit.
"""
from __future__ import annotations

import csv
import json
import subprocess
from collections import Counter
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
D16 = BACKEND / "data" / "integration" / "brainregion_direct_g1_phase16"

HIST_DEC = D16 / "phase17_v3_thalamus_bn_direct_spatial_decisions.csv"
SUP = D16 / "phase17_v3_thalamus_direct_decision_supersession.json"
EFF = D16 / "phase17_v3_thalamus_bn_direct_effective_decisions.csv"
GATE = D16 / "phase17_v3_thalamus_postconstruction_gate_closure.json"
FREEZE = D16 / "phase17_v3_thalamus_final_freeze_v1.json"
FREEZE_MD = D16 / "phase17_v3_thalamus_final_freeze_diagnostics.md"
AUDIT_SUM = D16 / "phase17_v3_thalamus_l8_2_discrepancy_summary.json"
CLASS = D16 / "phase17_v3_classification.csv"
V1 = D16 / "phase17_v3_thalamus_g1_scope_contract.json"
V2 = D16 / "phase17_v3_thalamus_g1_scope_contract_v2.json"
V3 = D16 / "phase17_v3_thalamus_g1_scope_contract_v3.json"

G1_LEFT_SHA = "bd431608fcea3c5f0f7387b1b0e1010582fa2e39dae95a300b3bba976a10cc87"
G1_RIGHT_SHA = "73e4242b581f2420c316593f6cd85183ea7f99c29e2b817b0257cdf267c5bd3b"
SUP_LEFT = "37a82b65d86d81b1558582dee301e79ee367d60856f95d6a55b0219cf28a87a1"
SUP_RIGHT = "1c9b8b8de9103c1e091c9fb6e0577182416d5a6ba0c1b7f6d41e1e913958253f"
SUPPORTED = "KEEP_FROZEN_MAPPING_DIRECTLY_SUPPORTED"
UNCERT = "KEEP_FROZEN_MAPPING_WITH_SPATIAL_UNCERTAINTY"
REVIEW = "FROZEN_MAPPING_REQUIRES_REVIEW"
CONFLICT = "FROZEN_MAPPING_DIRECT_CONFLICT"
HAS = SUP.exists() and EFF.exists() and GATE.exists() and FREEZE.exists()


def _sum(p):
    return json.load(open(p, encoding="utf-8"))


def _rows(p):
    return list(csv.DictReader(open(p, encoding="utf-8-sig")))


def _eff():
    return _rows(EFF)


def _freeze():
    return _sum(FREEZE)


def _git_clean(*paths: Path) -> bool:
    r = subprocess.run(["git", "diff", "--quiet", "HEAD", "--", *[str(p) for p in paths]],
                       cwd=BACKEND.parent, capture_output=True)
    return r.returncode == 0


# ---- 1. historical DIRECT-02 remains REVIEW in historical snapshot ----
def test_1_historical_direct02_remains_review():
    hist = {r["decision_id"]: r for r in _rows(HIST_DEC)}
    assert hist["DEC-THAL-DIRECT-02"]["mapping_verdict"] == REVIEW


# ---- 2. supersession points to DIRECT-02 ----
def test_2_supersession_targets_direct02():
    s = _sum(SUP)
    assert s["supersession_id"] == "DEC-THAL-DIRECT-02-S1"
    assert s["supersedes"] == "DEC-THAL-DIRECT-02"
    assert s["g3_official_code"] == "Tha_L_8_2"


# ---- 3. effective DIRECT-02 = WITH_SPATIAL_UNCERTAINTY ----
def test_3_effective_direct02_uncertainty():
    eff = {r["decision_id"]: r for r in _eff()}
    assert eff["DEC-THAL-DIRECT-02"]["effective_mapping_verdict"] == UNCERT
    assert eff["DEC-THAL-DIRECT-02"]["supersession_id"] == "DEC-THAL-DIRECT-02-S1"


# ---- 4. TRUE_MAPPING_INCOMPATIBILITY = FALSE ----
def test_4_true_mapping_incompatibility_false():
    s = _sum(SUP)
    assert s["mapping_conflict"] is False
    assert s["mapping_review_required"] is False
    f = _freeze()
    assert f["direct_02_true_mapping_incompatibility"] is False


# ---- 5. effective universe = 16 ----
def test_5_effective_universe_16():
    eff = _eff()
    assert len(eff) == 16
    assert _freeze()["relation_counts"]["total"] == 16


# ---- 6/7/8/9/10. counts ----
def test_678910_counts():
    c = Counter(x["effective_mapping_verdict"] for x in _eff())
    assert c[SUPPORTED] == 7
    assert c[UNCERT] == 9
    assert c[REVIEW] == 0
    assert c[CONFLICT] == 0
    rc = _freeze()["relation_counts"]
    assert rc["supported"] == 7 and rc["uncertainty"] == 9
    assert rc["review"] == 0 and rc["conflict"] == 0 and rc["insufficient"] == 0


# ---- 11. L8_2 root-cause provenance complete ----
def test_11_root_cause_provenance_complete():
    import hashlib
    s = _sum(SUP)
    aud = s["root_cause_audit"]
    assert aud["path"].endswith("phase17_v3_thalamus_l8_2_discrepancy_summary.json")
    assert len(aud["sha256"]) == 64
    ondisk = BACKEND / aud["path"]
    if ondisk.exists():
        h = hashlib.sha256(ondisk.read_bytes()).hexdigest()
        assert h == aud["sha256"]
    assert s["root_cause_primary"] == "G1_PROBABILITY_ENVELOPE_BOUNDARY_LIMITATION"
    assert s["root_cause_secondary"] == "SHARED_TEMPLATE_VARIANT_BOUNDARY_MISMATCH"
    assert s["raw_bna_intrinsic_asymmetry"] == "PRESENT"
    assert s["template_variant_uncertainty"] == "PRESENT"
    assert s["provenance_sha256"]


# ---- 12. R8_4 retained as nonblocking uncertainty ----
def test_12_r8_4_nonblocking():
    eff = {r["decision_id"]: r for r in _eff()}
    assert eff["DEC-THAL-DIRECT-12"]["effective_mapping_verdict"] == UNCERT
    assert eff["DEC-THAL-DIRECT-12"]["nonblocking_spatial_uncertainty"] == "TRUE"
    nbu = _freeze()["nonblocking_uncertainties"]
    assert any("DEC-THAL-DIRECT-12" in x["decision"] for x in nbu)


# ---- 13. postconstruction gate CLOSED ----
def test_13_gate_closed():
    g = _sum(GATE)
    assert g["gate_status"] == "CLOSED_NO_MAPPING_CONFLICT"
    assert g["gate_id"] == "THALAMUS_BN_POSTCONSTRUCTION_GATE_V1"


# ---- 14. no mapping conflicts ----
def test_14_no_mapping_conflicts():
    g = _sum(GATE)
    assert g["confirmed_mapping_conflicts"] == 0
    assert g["mapping_review_items"] == 0


# ---- 15. ontology FROZEN ----
def test_15_ontology_frozen():
    f = _freeze()
    assert f["ontology_status"] == "FROZEN"
    assert f["ontology_identity"] == "THALAMUS_PROPER"


# ---- 16. scope V3 FROZEN ----
def test_16_scope_v3_frozen():
    f = _freeze()
    assert f["scope_contract"] == "THALAMUS_G1_SCOPE_CONTRACT_V3"
    assert f["scope_status"] == "FROZEN"
    assert f["scope_contract_sha256"] == "22e24a31bab9659769f7e550ee32f8e3b37887d0ae1a4c4c4cf64974c3c05f68"


# ---- 17. geometry current SHA correct ----
def test_17_current_shas_correct():
    f = _freeze()
    assert f["current_g1_geometry"]["left_sha256"] == G1_LEFT_SHA
    assert f["current_g1_geometry"]["right_sha256"] == G1_RIGHT_SHA
    assert f["reference_grid_geometry_ids"] == ["GEO-G1-THAL-L-MNI2009CASYM-V1",
                                                "GEO-G1-THAL-R-MNI2009CASYM-V1"]
    assert len(f["native_geometry_ids"]) == 2


# ---- 18. superseded SyN geometry not current ----
def test_18_superseded_not_current():
    f = _freeze()
    ss = f["superseded_syn_geometry"]
    assert ss["left"] == SUP_LEFT and ss["right"] == SUP_RIGHT
    assert ss["status"] == "SUPERSEDED / NOT_CURRENT"
    assert ss["left"] != G1_LEFT_SHA and ss["right"] != G1_RIGHT_SHA


# ---- 19. spatial bridge limitation retained ----
def test_19_spatial_bridge_limitation():
    f = _freeze()
    assert f["spatial_bridge_status"] == "FROZEN_SHARED_COORDINATE_RESAMPLE"
    assert f["spatial_bridge_id"] == "SPB-MNI2009C-SYM-ASYM-SHARED-FRAME-V1"
    assert f["template_variant_uncertainty"] == "PRESENT"
    assert "TEMPLATE_VARIANT_ANATOMICAL_MISMATCH_NOT_EXPLICITLY_WARP_CORRECTED" in \
        f["residual_spatial_limitation"]
    assert f["authoritative_nonlinear_sym_asym_transform"] == "NOT_AVAILABLE_NOT_USED"
    assert f["evidence_mode"] == "DIRECT_SPATIAL_OVERLAP_IN_SHARED_MNI2009C_COORDINATE_FRAME"
    assert "NOT" in f["evidence_mode_note"]


# ---- 20/21. BN gates ----
def test_2021_bn_gates():
    f = _freeze()
    assert f["bn_preconstruction_gate"] == "PASSED"
    assert f["bn_postconstruction_gate"] == "CLOSED_NO_MAPPING_CONFLICT"
    assert f["bn_direct_validation_status"] == "PASSED_WITH_RECORDED_SPATIAL_UNCERTAINTY"


# ---- 22. remaining blocking Thalamus items = 0 ----
def test_22_no_blocking_items():
    f = _freeze()
    assert f["remaining_blocking_thalamus_items"] == []


# ---- 23. Promotion not executed ----
def test_23_promotion_not_executed():
    f = _freeze()
    assert f["promotion_executed"] is False
    assert f["promotion_readiness"] == "READY_FOR_LATER_GLOBAL_PROMOTION_REVIEW"


# ---- 24. classification byte-identical ----
def test_24_classification_unchanged():
    assert _git_clean(CLASS)
    rows = list(csv.DictReader(open(CLASS, encoding="utf-8-sig")))
    c = Counter(x["v3_classification"] for x in rows)
    assert len(rows) == 218
    assert c["VERIFIED_DIRECT_CONTAINED"] == 86
    assert sum(c.values()) - c["VERIFIED_DIRECT_CONTAINED"] == 132
    assert c["LIKELY_CONTAINED_NEEDS_SPATIAL_REVIEW"] == 93
    assert _freeze()["classification_csv_unchanged"] is True


# ---- 25. DB zero-write ----
def test_25_db_zero_write():
    assert _freeze()["db_zero_write"] is True
    txt = FREEZE_MD.read_text(encoding="utf-8")
    assert "brain_regions 770" in txt and "active mappings 707" in txt


# ---- 26. V1/V2/V3 unchanged ----
def test_26_contracts_unchanged():
    assert _git_clean(V1, V2, V3)


# ---- 27. provenance chain complete ----
def test_27_provenance_chain_complete():
    f = _freeze()
    chain = f["provenance_chain"]
    roles = [c["role"] for c in chain]
    for needle in ("effective direct decisions", "L8_2 supersession",
                   "historical direct decisions", "L8_2 discrepancy root-cause audit summary",
                   "frozen G3->G1 relations", "BNA NLin6Asym->2009cAsym batch transform manifest",
                   "spatial bridge manifest", "V3 scope contract"):
        assert any(needle in r for r in roles), needle
    withsha = [c for c in chain if c.get("sha256")]
    assert len(withsha) >= 10
    for c in withsha:
        assert len(c["sha256"]) == 64


# ---- additional structural checks ----
def test_gate_closure_fields():
    g = _sum(GATE)
    assert g["previous_status"] == "OPEN_DUE_TO_MATERIAL_UNRESOLVED_DISCREPANCY"
    assert g["root_cause_resolution"] == "COMPLETED"
    assert g["nonblocking_spatial_uncertainties"] == 9
    assert g["direct_validation_status"] == "PASSED_WITH_RECORDED_SPATIAL_UNCERTAINTY"
    assert "PERFECT_GEOMETRIC_CONTAINMENT" in g["note"]


def test_supersession_previous_effective_verdicts():
    s = _sum(SUP)
    assert s["previous_verdict"] == "FROZEN_MAPPING_REQUIRES_REVIEW"
    assert s["effective_verdict"] == "KEEP_FROZEN_MAPPING_WITH_SPATIAL_UNCERTAINTY"
    assert s["historical_outputs_rewritten"] is False


def test_effective_rows_link_all_16():
    eff = _eff()
    assert sorted(x["decision_id"] for x in eff) == \
        [f"DEC-THAL-DIRECT-{i:02d}" for i in range(1, 17)]
    # exactly one supersession id present (only DIRECT-02)
    ss = [x for x in eff if x["supersession_id"]]
    assert len(ss) == 1 and ss[0]["decision_id"] == "DEC-THAL-DIRECT-02"


def test_nonblocking_uncertainty_true_only_for_uncertain_rows():
    for x in _eff():
        expect = x["effective_mapping_verdict"] == UNCERT
        assert (x["nonblocking_spatial_uncertainty"] == "TRUE") == expect, x["decision_id"]


def test_diagnostics_preserves_uncertainty_wording():
    txt = FREEZE_MD.read_text(encoding="utf-8")
    assert "PASSED does NOT equal PERFECT_GEOMETRIC_CONTAINMENT" in txt
    assert "weighted containment 0.12-0.82" in txt
    assert "template_variant_uncertainty PRESENT" in txt
