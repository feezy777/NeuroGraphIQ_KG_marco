"""Gate 7B Phase 1F-J — G3→G1 Final QA + Freeze verification.

Read-only confirmation that the G3→G1 aggregation pipeline is fully frozen:
246 decisions close to 246 production mappings, formal/reverse queries return
the contracted results, no rollup/exclusion/hemisphere leakage, provenance
chain complete, all three lifecycle scripts rerun as NOOP, and the freeze
manifest is consistent.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import psycopg
import pytest

BACKEND = Path(__file__).resolve().parents[1]
PROD = "neurographiq_human_brain_v1"
INT = BACKEND / "data" / "integration"
TABLE = "brain_region_aggregation_mappings"

MAN = _rows = None


def _rows(name):
    return list(csv.DictReader(open(INT / name, encoding="utf-8-sig")))


MAN = _rows("g3_to_g1_full_decision_coverage_manifest.csv")
FREEZE = json.load(open(INT / "g3_to_g1_final_freeze_manifest.json", encoding="utf-8"))


def _conn(db=PROD):
    return psycopg.connect(host="127.0.0.1", port=5432, user="postgres",
                           password="postgres", dbname=db, autocommit=True)


def _db_rows():
    """G3→G1 slice only. The later G4→G3 chain shares the table and is out of
    scope for this G3→G1 final-freeze gate."""
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute(f"SELECT * FROM {TABLE} "
                    f"WHERE source_granularity_level='G3_MESO_FINE' AND target_granularity_level='G1_MACRO' "
                    f"ORDER BY mapping_pk")
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]
    finally:
        conn.close()


DB = _db_rows()


# ---------------------------------------------------------------------------
# 1-4. brain_regions + decision coverage
# ---------------------------------------------------------------------------

def test_brain_regions_770():
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT count(*) FROM brain_regions")
        assert cur.fetchone()[0] == 770
    finally:
        conn.close()


def test_granularity_counts():
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT granularity_level, count(*) FROM brain_regions GROUP BY 1")
        assert dict(cur.fetchall()) == {"G1_MACRO": 84, "G3_MESO_FINE": 246,
                                        "G4_MICROSTRUCTURAL_FINE": 440}
    finally:
        conn.close()


def test_decision_coverage_246():
    assert len(MAN) == 246
    assert len({m["g3_entity_id"] for m in MAN}) == 246


def test_decision_distribution():
    from collections import Counter
    dist = Counter(m["effective_scientific_decision"] for m in MAN)
    assert dist == Counter({"APPROVE_CONTAINED_IN": 172, "APPROVE_DOMINANT_OVERLAP": 34,
                            "PARTIAL_OVERLAP": 20, "NO_G1_ROLLUP": 10,
                            "CONFLICT_REVIEW": 10})
    assert all("PENDING" not in m["effective_scientific_decision"] for m in MAN)


# ---------------------------------------------------------------------------
# 5-13. production mapping state
# ---------------------------------------------------------------------------

def test_mappings_246():
    assert len(DB) == 246


def test_active_246():
    assert sum(1 for r in DB if r["record_status"] == "active") == 246


def test_approved_246():
    assert sum(1 for r in DB if r["review_status"] == "approved") == 246


def test_contained_172():
    assert sum(1 for r in DB if r["mapping_relation"] == "contained_in") == 172


def test_dominant_34():
    assert sum(1 for r in DB if r["mapping_relation"] == "dominant_overlap") == 34


def test_partial_40():
    assert sum(1 for r in DB if r["mapping_relation"] == "partial_overlap") == 40


def test_primary_query_172():
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute(f"""SELECT count(*) FROM {TABLE}
            WHERE source_granularity_level='G3_MESO_FINE' AND target_granularity_level='G1_MACRO'
              AND mapping_relation='contained_in' AND record_status='active'
              AND review_status='approved' AND rollup_eligible=TRUE AND is_primary_rollup=TRUE""")
        assert cur.fetchone()[0] == 172
    finally:
        conn.close()


def test_all_relation_query_246():
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute(f"""SELECT count(*) FROM {TABLE}
            WHERE source_granularity_level='G3_MESO_FINE' AND target_granularity_level='G1_MACRO'
              AND record_status='active' AND review_status='approved'""")
        assert cur.fetchone()[0] == 246
    finally:
        conn.close()


def test_overlap_query_74():
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute(f"""SELECT count(*) FROM {TABLE}
            WHERE source_granularity_level='G3_MESO_FINE' AND target_granularity_level='G1_MACRO'
              AND record_status='active' AND review_status='approved'
              AND mapping_relation IN ('dominant_overlap','partial_overlap')""")
        assert cur.fetchone()[0] == 74
    finally:
        conn.close()


def test_each_contained_source_one_parent():
    from collections import Counter
    rollup = [r for r in DB if r["rollup_eligible"] and r["is_primary_rollup"]]
    assert len(rollup) == 172
    per_src = Counter(r["source_region_pk"] for r in rollup)
    assert len(per_src) == 172
    assert all(v == 1 for v in per_src.values())
    assert FREEZE["primary_invariant_failure_count"] == 0


def test_dominant_partial_rollup_leak_zero():
    leak = [r for r in DB if r["mapping_relation"] in ("dominant_overlap", "partial_overlap")
            and (r["rollup_eligible"] or r["is_primary_rollup"])]
    assert leak == []


def test_exclusions_leak_zero():
    exc = list(csv.DictReader(open(INT / "g3_to_g1_mapping_candidate_exclusions.csv", encoding="utf-8-sig")))
    eids = list({m["g3_entity_id"] for m in exc})
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute(f"""SELECT count(*) FROM {TABLE}
            WHERE source_region_pk IN (SELECT b.entity_pk FROM brain_regions b
                JOIN kg_entities e ON e.entity_pk=b.entity_pk WHERE e.entity_id = ANY(%s))""",
            (eids,))
        assert cur.fetchone()[0] == 0
    finally:
        conn.close()
    assert FREEZE["excluded_leak_count"] == 0


def test_hemisphere_mismatch_zero():
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute(f"""SELECT count(*) FROM {TABLE} b
            JOIN brain_regions s ON s.entity_pk=b.source_region_pk
            JOIN brain_regions t ON t.entity_pk=b.target_region_pk
            WHERE b.source_granularity_level='G3_MESO_FINE' AND b.target_granularity_level='G1_MACRO'
              AND s.hemisphere<>t.hemisphere""")
        assert cur.fetchone()[0] == 0
    finally:
        conn.close()
    assert FREEZE["hemisphere_mismatch_count"] == 0


def test_confidence_null_semantics():
    assert all(r["mapping_confidence"] is None for r in DB)


def test_provenance_chain_246():
    stage_ids = {c["candidate_id"] for c in _rows("g3_to_g1_mapping_candidate_staging.csv")}
    for r in DB:
        p = r["provenance_json"]
        assert p.get("staging_candidate_id") in stage_ids
        assert p.get("load_phase") == "G3_G1_AGGREGATION_CANDIDATE_LOAD_V1"
        assert p.get("effective_scientific_decision")
        assert p.get("source_frozen_artifact")
        assert p.get("human_reviewed") is False
    assert FREEZE["provenance_complete_count"] == 246


def test_reverse_query_works():
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute(f"""SELECT target_region_pk, count(DISTINCT source_region_pk)
            FROM {TABLE}
            WHERE source_granularity_level='G3_MESO_FINE' AND target_granularity_level='G1_MACRO'
              AND record_status='active' AND review_status='approved'
              AND mapping_relation='contained_in' AND rollup_eligible=TRUE
            GROUP BY target_region_pk""")
        rows = cur.fetchall()
        assert len(rows) > 0
        assert sum(c for _, c in rows) == 172
    finally:
        conn.close()


def test_representative_query_semantics():
    # contained sample -> parent; dominant -> not in primary query
    cont = next(m for m in MAN if m["effective_scientific_decision"] == "APPROVE_CONTAINED_IN")
    dom = next(m for m in MAN if m["effective_scientific_decision"] == "APPROVE_DOMINANT_OVERLAP")
    part = next(m for m in MAN if m["effective_scientific_decision"] == "PARTIAL_OVERLAP")
    no = next(m for m in MAN if m["effective_scientific_decision"] == "NO_G1_ROLLUP")
    conf = next(m for m in MAN if m["effective_scientific_decision"] == "CONFLICT_REVIEW")
    conn = _conn()
    try:
        cur = conn.cursor()
        def rows_for(eid):
            cur.execute(f"""SELECT mapping_relation FROM {TABLE} b
                JOIN kg_entities e ON e.entity_pk=b.source_region_pk WHERE e.entity_id=%s""", (eid,))
            return [r[0] for r in cur.fetchall()]
        assert rows_for(cont["g3_entity_id"]) == ["contained_in"]
        assert rows_for(dom["g3_entity_id"]) == ["dominant_overlap"]
        assert rows_for(part["g3_entity_id"]) == ["partial_overlap", "partial_overlap"]
        assert rows_for(no["g3_entity_id"]) == []
        assert rows_for(conf["g3_entity_id"]) == []
    finally:
        conn.close()


def test_loader_rerun_noop():
    assert FREEZE["loader_script"] == "scripts/load_g3_g1_aggregation_candidates.py"
    audit = json.load(open(INT / "g3_to_g1_aggregation_candidate_load_audit.json", encoding="utf-8"))
    assert audit["transaction_status"] == "COMMITTED"
    assert "rerun_observations" in audit  # rerun appended, did not reinsert


def test_approval_rerun_noop():
    audit = json.load(open(INT / "g3_to_g1_aggregation_approval_audit.json", encoding="utf-8"))
    assert audit["transaction_status"] == "COMMITTED"
    assert audit["updated_count"] == 246
    assert "rerun_observations" in audit


def test_promotion_rerun_noop():
    audit = json.load(open(INT / "g3_to_g1_aggregation_promotion_audit.json", encoding="utf-8"))
    assert audit["transaction_status"] == "COMMITTED"
    assert audit["promoted_count"] == 246
    assert "rerun_observations" in audit


def test_freeze_manifest_consistent():
    assert FREEZE["freeze_status"] == "FROZEN"
    assert FREEZE["G3_decision_count"] == 246
    assert FREEZE["production_mapping_count"] == 246
    assert FREEZE["contained_relation_count"] == 172
    assert FREEZE["dominant_relation_count"] == 34
    assert FREEZE["partial_relation_count"] == 40
    assert FREEZE["primary_rollup_source_count"] == 172
    assert FREEZE["formal_primary_query_count"] == 172
    assert FREEZE["formal_all_mapping_query_count"] == 246
    assert FREEZE["formal_overlap_query_count"] == 74
    assert FREEZE["provenance_complete_count"] == 246


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
