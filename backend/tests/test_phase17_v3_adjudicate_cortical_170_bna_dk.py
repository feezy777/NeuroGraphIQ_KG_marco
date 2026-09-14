"""Phase1.7 V3 - final adjudication of the 170 cortical Brainnetome <-> DK relations.

Validates that every candidate in the frozen 170 universe ends in an explicit adjudication
state, that relation types come from the frozen BR3 vocabulary and are decided from
documented atlas definitions (never from volume), that the review queue is exactly the set
of flagged rows, and that no existing evidence artifact was modified.
"""
from __future__ import annotations

import csv
import json
import subprocess
from collections import Counter
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
D16 = BACKEND / "data" / "integration" / "brainregion_direct_g1_phase16"

UNIV = D16 / "phase17_v3_cortical_170_relation_universe.csv"
EV2 = D16 / "phase17_v3_cortical_170_direct_spatial_evidence_v2.csv"
GMW = D16 / "phase17_v3_cortical_170_gm_weighted_evidence.csv"
G1MAN = D16 / "phase17_v3_cortical_g1_62_reference_geometry_manifest.csv"
SDSTATUS = D16 / "phase17_v3_cortical_support_domain_status.json"
BNA_SUB = (BACKEND / "data" / "atlases" / "brainnetome" / "bna246" /
           "brainnetome_bna246_subregions_authoritative.csv")

CROSS = D16 / "phase17_v3_cortical_bna_dk_macro_gyrus_crosswalk_v1.csv"
ADJ = D16 / "phase17_v3_cortical_170_final_adjudication.csv"
QUEUE = D16 / "phase17_v3_cortical_170_adjudication_review_queue.csv"
SUM = D16 / "phase17_v3_cortical_170_adjudication_summary.json"
MD = D16 / "phase17_v3_cortical_170_adjudication_diagnostics.md"

OUTS = [CROSS, ADJ, QUEUE, SUM, MD]
BR3_TYPES = {"exact", "broader", "narrower", "uncertain"}
STATUS_CODES = {"A", "B", "C", "D", "E", "F"}
# evidence the adjudication must not have touched
FROZEN = [UNIV, EV2, GMW, G1MAN, SDSTATUS,
          D16 / "phase17_v3_cortical_170_gm_weighted_competition_long.csv",
          D16 / "phase17_v3_cortical_170_g1_competition_long.csv",
          D16 / "phase17_v3_cortical_170_support_decomposition.csv",
          D16 / "phase17_v3_cortical_support_distance_qc.csv",
          D16 / "phase17_v3_classification.csv"]


def _j(p):
    return json.load(open(p, encoding="utf-8"))


def _rows(p):
    return list(csv.DictReader(open(p, encoding="utf-8-sig")))


# ---- 1. artifacts exist ----
def test_1_artifacts_exist():
    for p in OUTS:
        assert p.is_file(), p


# ---- 2. universe coverage: every candidate adjudicated exactly once ----
def test_2_full_coverage():
    univ = [r["relation_id"] for r in _rows(UNIV)]
    adj = [r["relation_id"] for r in _rows(ADJ)]
    assert len(univ) == 170
    assert sorted(univ) == sorted(adj)
    assert len(set(adj)) == 170


# ---- 3. every row ends in an explicit allowed state ----
def test_3_explicit_states():
    rows = _rows(ADJ)
    assert len(rows) == 170
    assert all(r["final_adjudication_status"] for r in rows)
    assert all(r["status_code"] in STATUS_CODES for r in rows)
    c = Counter(r["status_code"] for r in rows)
    assert sum(c.values()) == 170
    assert c["B"] == 166
    assert c["C"] == 4
    assert c["A"] == 0 and c["D"] == 0 and c["E"] == 0 and c["F"] == 0


# ---- 4. relation types come from the frozen vocabulary ----
def test_4_relation_type_vocabulary():
    rows = _rows(ADJ)
    types = Counter(r["relation_type"] for r in rows)
    assert set(types) <= BR3_TYPES, f"non-frozen relation type: {set(types) - BR3_TYPES}"
    assert types["narrower"] == 170
    assert types.get("exact", 0) == 0
    assert all(r["hierarchy_predicate"] == "part_of" for r in rows)


# ---- 5. relation type decided definitionally, not from volume ----
def test_5_no_volume_criterion():
    s = _j(SUM)
    assert "Volume ratios were explicitly NOT used" in s["relation_type_rationale"]
    assert "different defining criteria" in s["relation_type_rationale"]
    src = (BACKEND / "scripts" /
           "phase17_v3_adjudicate_cortical_170_bna_dk.py").read_text(encoding="utf-8")
    # no voxel/volume quantities read from the evidence files
    for token in ("fine_voxels", "voxel_count", "volume_mm3", "source_target_volume_ratio"):
        assert token not in src, f"volume quantity {token} must not drive the adjudication"


# ---- 6. forbidden criteria declared unused ----
def test_6_forbidden_criteria():
    f = _j(SUM)["frozen_methodology_basis"]
    for x in ("absolute containment", "COM displacement", "raw outside-union fraction",
              "support-domain volume difference"):
        assert x in f["not_used_as_criteria"]
    for x in ("relative spatial ranking", "GM-weighted ranking and margin"):
        assert any(x == u for u in f["used_as_supporting_only"])


# ---- 7. crosswalk is complete and self-consistent ----
def test_7_crosswalk():
    bna = {int(r["parcel_id"]): r for r in _rows(BNA_SUB)}
    g1 = {r["canonical_region_id"]: r for r in _rows(G1MAN)}
    cw = {r["bna_macro_gyrus"]: r for r in _rows(CROSS)}
    assert all(r["all_used_labels_allowed"] == "True" for r in cw.values())
    for r in _rows(UNIV):
        mg = bna[int(r["parcel_id"])]["macro_gyrus_name"]
        dk = g1[r["proposed_g1_id"]]["dk_label"]
        assert mg in cw, f"macro gyrus not in crosswalk: {mg}"
        assert dk in cw[mg]["allowed_dk_labels"].split("|"), f"{mg} -> {dk} not allowed"


# ---- 8. review queue is exactly the flagged set ----
def test_8_review_queue_consistency():
    adj = _rows(ADJ)
    q = _rows(QUEUE)
    flagged = {r["relation_id"] for r in adj if r["review_required"] == "True"}
    assert {r["relation_id"] for r in q} == flagged
    assert len(q) == 4
    assert all(r["review_reason_codes"] for r in q)
    # queued rows must be state C; all others state B
    for r in adj:
        assert r["status_code"] == ("C" if r["relation_id"] in flagged else "B")


# ---- 9. gate thresholds applied exactly as declared ----
def test_9_gate_thresholds():
    s = _j(SUM)["review_gate"]
    assert s["weak_margin_lt"] == 0.10 and s["midline_crossing_lt"] == 0.96
    for r in _rows(ADJ):
        reasons = r["review_reason_codes"]
        m = float(r["spatial_gm_margin"])
        c = float(r["correct_side_fraction"])
        if "SPATIAL_WEAK_DISCRIMINATION" in reasons:
            assert m < 0.10
        if "LAT_MIDLINE_PARTIAL_CROSSING" in reasons:
            assert c < 0.96


# ---- 10. no laterality rejection: dominant side always correct ----
def test_10_laterality():
    g1 = {r["canonical_region_id"]: r for r in _rows(G1MAN)}
    adj = _rows(ADJ)
    assert all(r["hemisphere"] == g1[r["target_canonical_id"]]["hemisphere"] for r in adj)
    assert all(float(r["correct_side_fraction"]) > 0.5 for r in adj)
    assert _j(SUM)["rejected_laterality"] == 0


# ---- 11. decision trace completeness (task section 6 fields) ----
REQUIRED = ["source_canonical_id", "target_canonical_id", "hemisphere", "relation_type",
            "final_adjudication_status", "semantic_evidence_code", "semantic_evidence_detail",
            "hierarchy_evidence", "spatial_raw_rank", "spatial_gm_weighted_rank",
            "provenance_source", "decision_reason_codes", "review_required"]


def test_11_decision_trace_complete():
    rows = _rows(ADJ)
    for r in rows:
        for k in REQUIRED:
            assert k in r and r[k] != "", f"{r['relation_id']} missing {k}"
    # no long free-prose in production data: reason fields are structured codes
    assert all(len(r["review_reason_codes"]) < 120 for r in rows)
    assert all(len(r["decision_reason_codes"].split("|")) <= 5 for r in rows)


# ---- 12. spatial evidence recorded and all rank-1 ----
def test_12_spatial_supporting():
    rows = _rows(ADJ)
    assert all(int(r["spatial_raw_rank"]) == 1 for r in rows)
    assert all(int(r["spatial_gm_weighted_rank"]) == 1 for r in rows)
    assert all(r["spatial_competitor_target"] for r in rows)


# ---- 13. no new candidate relations created ----
def test_13_no_new_candidates():
    s = _j(SUM)
    assert s["universe"] == 170
    assert s["excluded_parcels"]["count"] == 40
    assert s["new_relation_types_created"] == []
    # the 40 excluded parcels have no adjudication row
    adjudicated = {r["source_canonical_id"] for r in _rows(ADJ)}
    assert len(adjudicated) == 170


# ---- 14. frozen methodology basis recorded ----
def test_14_methodology_basis():
    f = _j(SUM)["frozen_methodology_basis"]
    assert f["commit"] == "b970f48"
    assert f["verdict"] == "CORTICAL_CROSS_ATLAS_SUPPORT_DOMAIN_MISMATCH_CONFIRMED"
    assert f["spatial_compatibility"] == "SPATIALLY_COMPATIBLE"
    assert _j(SDSTATUS)["verdict"] == f["verdict"]


# ---- 15. evidence inputs fingerprinted ----
def test_15_evidence_fingerprints():
    ei = _j(SUM)["evidence_inputs"]
    for k in ("universe", "direct_spatial_v2", "gm_weighted", "g1_manifest", "bna_authoritative"):
        assert len(ei[k]["sha256"]) == 64


# ---- 16. no mutation of frozen/committed evidence ----
def test_16_no_evidence_mutation():
    tracked = [p for p in FROZEN if _is_tracked(p)]
    if tracked:
        r = subprocess.run(["git", "diff", "--quiet", "HEAD", "--"] +
                           [str(p) for p in tracked], cwd=BACKEND.parent, capture_output=True)
        assert r.returncode == 0, "committed evidence was modified"
    s = _j(SUM)
    for k in ("no_mapping_mutation", "no_geometry_change", "no_transform_change",
              "no_new_spatial_evidence", "no_db_write"):
        assert s[k] is True


def _is_tracked(p: Path) -> bool:
    r = subprocess.run(["git", "ls-files", "--error-unmatch", str(p)],
                       cwd=BACKEND.parent, capture_output=True)
    return r.returncode == 0


# ---- 17. diagnostics md states the corrected basis ----
def test_17_diagnostics():
    md = MD.read_text(encoding="utf-8")
    assert "b970f48" in md
    assert "criteria NOT used" in md
    assert "narrower" in md
