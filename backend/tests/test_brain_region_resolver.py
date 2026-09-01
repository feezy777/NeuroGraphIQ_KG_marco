"""BrainRegion Resolver Phase 1 — deterministic Gate7B core tests.

Covers the resolver contract: canonical EN/ZH/source exact, alias, xref, atlas
RegionMapping, safe normalization, hemisphere/granularity constraints, alias/xref/
mapping type policy, inactive-target exclusion, ambiguity handling (never LIMIT 1).

E2E read-only for G1 paths; rolled-back fixtures for ambiguous/alias/xref/mapping
policy; pure functions for normalization and decision logic. Production-only paths
(Julich source id -> RESOLVED, Brainnetome xref) are covered by the read-only
production smoke script, not here.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import psycopg
import pytest

BACKEND = Path(__file__).resolve().parents[1]
E2E = "neurographiq_human_brain_v1_e2e"

spec = importlib.util.spec_from_file_location(
    "brain_region_resolver_service",
    BACKEND / "app" / "services" / "brain_region_resolver_service.py")
svc = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = svc  # dataclass needs its module registered
assert spec.loader is not None
spec.loader.exec_module(svc)

R = svc.BrainRegionResolveRequest


def _conn():
    return psycopg.connect(host="127.0.0.1", port=5432, user="postgres",
                           password="postgres", dbname=E2E, autocommit=True)


def _tx():
    conn = psycopg.connect(host="127.0.0.1", port=5432, user="postgres",
                           password="postgres", dbname=E2E, autocommit=False)
    return conn, conn.cursor()


def _g1_region(cur, name_en="Left Thalamus"):
    cur.execute("SELECT ke.entity_pk, ke.name_en, ke.name_zh, ke.source_name_original,"
                " br.hemisphere, br.granularity_level FROM kg_entities ke"
                " JOIN brain_regions br ON br.entity_pk=ke.entity_pk"
                " WHERE ke.name_en=%s AND br.granularity_level='G1_MACRO'"
                " AND ke.record_status='active' AND ke.review_status='approved'",
                (name_en,))
    return cur.fetchone()


# --------------------------------------------------------------------------- #
# 1-3. Canonical EN / ZH / source-name exact (E2E G1)
# --------------------------------------------------------------------------- #

def test_canonical_en_exact_resolved():
    conn = _conn()
    try:
        res = svc.resolve_brain_region(conn, R(query_text="Left Thalamus"))
        assert res.status == "RESOLVED"
        assert res.match_type == "EXACT_CANONICAL_NAME"
        assert res.candidate_count == 1
        assert res.candidates[0].name_en == "Left Thalamus"
        assert res.candidates[0].hemisphere == "left"
        assert res.candidates[0].granularity_level == "G1_MACRO"
    finally:
        conn.close()


def test_canonical_zh_exact_resolved():
    conn = _conn()
    try:
        cur = conn.cursor()
        row = _g1_region(cur, "Left Thalamus")
        zh = row[2]
        assert zh
        res = svc.resolve_brain_region(conn, R(query_text=zh, language="zh"))
        assert res.status == "RESOLVED"
        assert res.match_type == "EXACT_CANONICAL_NAME"
        assert res.candidates[0].name_zh == zh
    finally:
        conn.close()


def test_source_name_exact_resolved():
    conn = _conn()
    try:
        cur = conn.cursor()
        src = _g1_region(cur, "Left Thalamus")[3]  # 'left thalamus proper'
        assert src and src != "Left Thalamus"
        res = svc.resolve_brain_region(conn, R(query_text=src))
        assert res.status == "RESOLVED"
        assert res.match_type == "EXACT_SOURCE_NAME"
    finally:
        conn.close()


# --------------------------------------------------------------------------- #
# 4-5. Alias / xref resolution (rolled-back fixtures)
# --------------------------------------------------------------------------- #

def test_alias_exact_resolved():
    conn, cur = _tx()
    try:
        pk = _g1_region(cur, "Left Thalamus")[0]
        cur.execute("INSERT INTO entity_aliases (alias_id, entity_pk, alias_text, alias_type)"
                    " VALUES ('tst_alias_1', %s, 'THAL_ABBR', 'abbreviation')", (pk,))
        res = svc.resolve_brain_region(conn, R(query_text="THAL_ABBR"))
        assert res.status == "RESOLVED"
        assert res.match_type == "EXACT_ALIAS"
        assert res.candidates[0].alias_type == "abbreviation"
        assert res.candidates[0].entity_pk == pk
    finally:
        conn.rollback()
        conn.close()


def test_xref_with_namespace_resolved():
    conn, cur = _tx()
    try:
        pk = _g1_region(cur, "Left Thalamus")[0]
        cur.execute("INSERT INTO entity_xrefs (xref_id, entity_pk, source_database,"
                    " external_id, match_type) VALUES ('tst_xref_1', %s, 'TESTDB',"
                    " 'PAR-42', 'exact')", (pk,))
        res = svc.resolve_brain_region(
            conn, R(source_database="TESTDB", external_id="PAR-42"))
        assert res.status == "RESOLVED"
        assert res.match_type == "EXACT_XREF"
        assert res.candidates[0].source_database == "TESTDB"
        assert res.candidates[0].external_id == "PAR-42"
    finally:
        conn.rollback()
        conn.close()


# --------------------------------------------------------------------------- #
# 6, 13-16. Bare number / descriptor tokens -> UNRESOLVED
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("q", ["1", "17", "44", "SPL", "Thalamus", "V1", "BA17", "AM"])
def test_unresolved_inputs(q):
    conn = _conn()
    try:
        res = svc.resolve_brain_region(conn, R(query_text=q))
        assert res.status == "UNRESOLVED"
        assert res.match_type == "NONE"
        assert res.candidate_count == 0
    finally:
        conn.close()


# --------------------------------------------------------------------------- #
# 8. Wrong Julich source id -> UNRESOLVED (no fixture needed)
# --------------------------------------------------------------------------- #

def test_wrong_julich_source_id_unresolved():
    conn = _conn()
    try:
        res = svc.resolve_brain_region(
            conn, R(atlas_family="Julich-Brain", atlas_version="3.1.0",
                    source_region_id="JULICH_BRAIN_CYTOARCHITECTONIC_ATLAS_V3_1_DOES_NOT_EXIST"))
        assert res.status == "UNRESOLVED"
    finally:
        conn.close()


# --------------------------------------------------------------------------- #
# 9, 11. Hemisphere + granularity constraints (E2E G1)
# --------------------------------------------------------------------------- #

def test_hemisphere_constraint():
    conn = _conn()
    try:
        left = svc.resolve_brain_region(conn, R(query_text="Left Thalamus", hemisphere="left"))
        assert left.status == "RESOLVED" and left.candidates[0].hemisphere == "left"
        # hemisphere=right must reject the left region
        wrong = svc.resolve_brain_region(conn, R(query_text="Left Thalamus", hemisphere="right"))
        assert wrong.status == "UNRESOLVED"
    finally:
        conn.close()


def test_granularity_constraint():
    conn = _conn()
    try:
        g1 = svc.resolve_brain_region(conn, R(query_text="Left Thalamus",
                                             granularity_level="G1_MACRO"))
        assert g1.status == "RESOLVED"
        g4 = svc.resolve_brain_region(conn, R(query_text="Left Thalamus",
                                             granularity_level="G4_MICROSTRUCTURAL_FINE"))
        assert g4.status == "UNRESOLVED"
    finally:
        conn.close()


# --------------------------------------------------------------------------- #
# 10, 17, 24. Ambiguity: one alias -> many (never LIMIT 1)
# --------------------------------------------------------------------------- #

def test_alias_one_to_many_ambiguous():
    conn, cur = _tx()
    try:
        left_pk = _g1_region(cur, "Left Thalamus")[0]
        right_pk = _g1_region(cur, "Right Thalamus")[0]
        assert left_pk != right_pk
        cur.execute("INSERT INTO entity_aliases (alias_id, entity_pk, alias_text, alias_type)"
                    " VALUES ('tst_amb_1', %s, 'AMB_TH', 'exact')", (left_pk,))
        cur.execute("INSERT INTO entity_aliases (alias_id, entity_pk, alias_text, alias_type)"
                    " VALUES ('tst_amb_2', %s, 'AMB_TH', 'exact')", (right_pk,))
        res = svc.resolve_brain_region(conn, R(query_text="AMB_TH"))
        assert res.status == "AMBIGUOUS"
        assert res.candidate_count == 2
        hems = {c.hemisphere for c in res.candidates}
        assert hems == {"left", "right"}
    finally:
        conn.rollback()
        conn.close()


# --------------------------------------------------------------------------- #
# 12. Cross-granularity multiple -> AMBIGUOUS (decision logic)
# --------------------------------------------------------------------------- #

def test_decision_multiple_candidates_ambiguous_regardless_of_granularity():
    c1 = svc.ResolverCandidate(entity_id="A", entity_pk=1, name_en="X", name_zh=None,
                               source_name_original=None, granularity_level="G1_MACRO",
                               hemisphere="left", species_taxon_id="9606",
                               match_type="EXACT_CANONICAL_NAME", matched_value="X",
                               match_provenance="name_en")
    c2 = svc.ResolverCandidate(entity_id="B", entity_pk=2, name_en="X", name_zh=None,
                               source_name_original=None, granularity_level="G4_MICROSTRUCTURAL_FINE",
                               hemisphere="left", species_taxon_id="9606",
                               match_type="EXACT_CANONICAL_NAME", matched_value="X",
                               match_provenance="name_en")
    res = svc._result_from_candidates(R(query_text="X"), [c1, c2], "EXACT_CANONICAL_NAME")
    assert res.status == "AMBIGUOUS"
    assert res.candidate_count == 2


# --------------------------------------------------------------------------- #
# 18-20. Alias / xref / mapping type policy (non-exact never resolves)
# --------------------------------------------------------------------------- #

def test_alias_semantic_hint_types_not_resolved():
    conn, cur = _tx()
    try:
        pk = _g1_region(cur, "Left Thalamus")[0]
        cur.execute("INSERT INTO entity_aliases (alias_id, entity_pk, alias_text, alias_type)"
                    " VALUES ('tst_broad_1', %s, 'BROAD_TH', 'broad')", (pk,))
        res = svc.resolve_brain_region(conn, R(query_text="BROAD_TH"))
        assert res.status == "UNRESOLVED"
    finally:
        conn.rollback()
        conn.close()


def test_xref_non_exact_not_resolved():
    conn, cur = _tx()
    try:
        pk = _g1_region(cur, "Left Thalamus")[0]
        cur.execute("INSERT INTO entity_xrefs (xref_id, entity_pk, source_database,"
                    " external_id, match_type) VALUES ('tst_xref_close', %s, 'TESTDB',"
                    " 'PAR-99', 'close')", (pk,))
        res = svc.resolve_brain_region(conn, R(source_database="TESTDB", external_id="PAR-99"))
        assert res.status == "UNRESOLVED"
    finally:
        conn.rollback()
        conn.close()


def test_mapping_non_exact_not_resolved():
    # Make an E2E Julich mapping non-exact AND approved with an active target; it
    # must still NOT resolve (mapping_type filter is hard).
    conn, cur = _tx()
    try:
        cur.execute(
            "SELECT rm.entity_pk, rm.brain_region_pk, x.source_region_id"
            " FROM region_mappings rm JOIN external_regions x ON x.entity_pk=rm.external_region_pk"
            " JOIN atlases a ON a.entity_pk=x.atlas_pk WHERE a.atlas_family='Julich-Brain' LIMIT 1")
        rm_pk, br_pk, sid = cur.fetchone()
        # make the mapping approved + non-exact, and its target active+approved
        cur.execute("UPDATE kg_entities SET record_status='active', review_status='approved'"
                    " WHERE entity_pk=%s", (rm_pk,))
        cur.execute("UPDATE region_mappings SET mapping_type='close' WHERE entity_pk=%s", (rm_pk,))
        cur.execute("UPDATE kg_entities SET record_status='active', review_status='approved'"
                    " WHERE entity_pk=%s", (br_pk,))
        res = svc.resolve_brain_region(conn, R(atlas_family="Julich-Brain", atlas_version="3.1.0",
                                               source_region_id=sid))
        assert res.status == "UNRESOLVED"
    finally:
        conn.rollback()
        conn.close()


# --------------------------------------------------------------------------- #
# 21. Inactive / unapproved target -> not resolved (E2E G4 is proposed/pending)
# --------------------------------------------------------------------------- #

def test_inactive_target_not_resolved():
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT ke.name_en FROM kg_entities ke JOIN brain_regions br"
                    " ON br.entity_pk=ke.entity_pk WHERE br.granularity_level='G4_MICROSTRUCTURAL_FINE'"
                    " LIMIT 1")
        g4_name = cur.fetchone()[0]
        assert g4_name
        res = svc.resolve_brain_region(conn, R(query_text=g4_name))
        assert res.status == "UNRESOLVED"
    finally:
        conn.close()


# --------------------------------------------------------------------------- #
# 22-23. Safe normalization (format only; never strips hemisphere)
# --------------------------------------------------------------------------- #

def test_safe_normalization_case_whitespace():
    conn = _conn()
    try:
        res = svc.resolve_brain_region(conn, R(query_text="  left   thalamus  "))
        assert res.status == "RESOLVED"
        assert res.match_type == "NORMALIZED_LEXICAL_MATCH"
        assert res.candidates[0].name_en == "Left Thalamus"
    finally:
        conn.close()


def test_normalization_does_not_strip_hemisphere():
    # "thalamus" (no hemisphere) must NOT collapse to "Left Thalamus"
    conn = _conn()
    try:
        res = svc.resolve_brain_region(conn, R(query_text="thalamus"))
        assert res.status == "UNRESOLVED"
    finally:
        conn.close()


# --------------------------------------------------------------------------- #
# Pure: safe_normalize + alias type policy
# --------------------------------------------------------------------------- #

def test_safe_normalize_pure():
    assert svc.safe_normalize("  Left   Thalamus ") == "left thalamus"
    assert svc.safe_normalize("LEFT THALAMUS") == "left thalamus"
    assert svc.safe_normalize("left") == "left"       # never strips hemisphere
    assert svc.safe_normalize("thalamus") != "left thalamus"


def test_alias_type_policy_constants():
    assert "abbreviation" in svc.ALLOWED_ALIAS_TYPES
    assert "atlas_label" in svc.ALLOWED_ALIAS_TYPES
    for t in ("narrow", "broad", "related"):
        assert t not in svc.ALLOWED_ALIAS_TYPES
        assert t in svc.SEMANTIC_HINT_ALIAS_TYPES


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
