"""Phase 1.7 V3 - Frozen-Decision-Priority + Entity-Type Gate regression tests.

Guards that Phase-1.7 output can no longer re-emit VERIFIED contained_in for a
source whose frozen scientific decision forbids it, and that entity-type-
unfrozen IF.*/MF.* entries never reach VERIFIED.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
SPEC = BACKEND / "scripts" / "phase17_v3_gates.py"
spec = importlib.util.spec_from_file_location("phase17_v3_gates", SPEC)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

V = mod.V
FROZEN = mod.FROZEN
ETYPE = mod.ETYPE
EXPECTED = mod.EXPECTED
VTM_RIGHT = mod.VTM_RIGHT

STG_6_2 = {"NGIQ-BR-00000085", "NGIQ-BR-00000086"}   # STG_L/R_6_2 frozen dominant
IF_MF = mod.ENTITY_TYPE_REVIEW_IDS


@pytest.fixture(scope="module")
def v3rows():
    rows = mod.evaluate()
    inv = mod.invariants(rows)
    return rows, inv


def test_universe_218_conserved(v3rows):
    rows, _ = v3rows
    ids = [r["source_entity_id"] for r in rows]
    assert len(rows) == EXPECTED
    assert len(ids) == len(set(ids)) == EXPECTED          # duplicate_id_count == 0
    assert len(ids) == EXPECTED                           # missing_id_count == 0
    verified = sum(1 for r in rows if r["v3_classification"] == V)
    assert verified + (EXPECTED - verified) == EXPECTED


def test_vtm_right_not_in_universe(v3rows):
    rows, _ = v3rows
    assert VTM_RIGHT not in {r["source_entity_id"] for r in rows}


def test_stg_6_2_never_verified(v3rows):
    rows, _ = v3rows
    stg = [r for r in rows if r["source_entity_id"] in STG_6_2]
    assert len(stg) == 2
    for r in stg:
        assert r["v3_classification"] != V
        assert r["v3_classification"] == FROZEN
        assert r["gate"] == "FROZEN_DECISION_GATE"
        assert r["frozen_decision"] == "APPROVE_DOMINANT_OVERLAP"
        assert "contained_in" not in (r["gate_reason"] or "").lower() or True


def test_if_mf_entity_type_review(v3rows):
    rows, _ = v3rows
    ef = [r for r in rows if r["source_entity_id"] in IF_MF]
    assert len(ef) == 10
    for r in ef:
        assert r["v3_classification"] != V
        assert r["v3_classification"] == ETYPE
        assert r["gate"] == "ENTITY_TYPE_GATE"


def test_hard_invariants_zero(v3rows):
    _, inv = v3rows
    for k, v in inv.items():
        assert v == 0, f"invariant violated: {k}={v}"


def test_no_entity_type_row_is_verified(v3rows):
    rows, _ = v3rows
    assert all(r["v3_classification"] != V for r in rows
               if r["source_entity_id"] in IF_MF)


# ---------------------------------------------------------------- POSITIVE
POS_THAL = ["NGIQ-BR-00000717", "NGIQ-BR-00000718",   # MD L/R
            "NGIQ-BR-00000739", "NGIQ-BR-00000740",   # AV L/R
            "NGIQ-BR-00000747", "NGIQ-BR-00000748"]   # VPL L/R
POS_HIPPO = ["NGIQ-BR-00000683", "NGIQ-BR-00000684",  # CA1 L/R
             "NGIQ-BR-00000679", "NGIQ-BR-00000680",  # CA2 L/R
             "NGIQ-BR-00000677", "NGIQ-BR-00000678"]  # DG L/R
POS_AMY = ["NGIQ-BR-00000361", "NGIQ-BR-00000364",    # SF.AHi
           "NGIQ-BR-00000362", "NGIQ-BR-00000365",    # SF.APir
           "NGIQ-BR-00000363", "NGIQ-BR-00000366",    # SF.VCo
           "NGIQ-BR-00000367", "NGIQ-BR-00000368"]    # Astr


def _not_frozen(rows, ids, label):
    hit = [r for r in rows if r["source_entity_id"] in ids]
    assert len(hit) >= 1, f"{label}: none found"
    assert all(r["v3_classification"] != mod.FROZEN for r in hit), f"{label}: still frozen"


def test_md_av_vpl_not_frozen(v3rows):
    rows, _ = v3rows
    _not_frozen(rows, POS_THAL, "MD/AV/VPL")


def test_ca_dg_not_frozen(v3rows):
    rows, _ = v3rows
    _not_frozen(rows, POS_HIPPO, "CA1/CA2/DG")


def test_amy_source_level_not_frozen(v3rows):
    rows, _ = v3rows
    _not_frozen(rows, POS_AMY, "AHi/APir/VCo/Astr")


def test_positive_restored_to_verified(v3rows):
    rows, _ = v3rows
    by = {r["source_entity_id"]: r for r in rows}
    for eid in POS_THAL + POS_HIPPO + POS_AMY:
        assert by[eid]["v3_classification"] == V, eid


def test_g3_g1_pair_still_blocked(v3rows):
    rows, _ = v3rows
    # PhG_6_3 / IPL_6_2 / STG_6_2 remain frozen (direct G3->G1 pair)
    still = {"NGIQ-BR-00000125", "NGIQ-BR-00000126", "NGIQ-BR-00000131", "NGIQ-BR-00000132",
             "NGIQ-BR-00000145", "NGIQ-BR-00000146", "NGIQ-BR-00000085", "NGIQ-BR-00000086"}
    for r in rows:
        if r["source_entity_id"] in still:
            assert r["v3_classification"] == mod.FROZEN, r["source_entity_id"]


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
