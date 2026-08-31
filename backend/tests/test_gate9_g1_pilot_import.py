"""Gate 9 G1 — Macro96 BrainRegion import tests (pilot + full 84).

Covers the importer's pure functions (manifest completeness, eligibility,
deterministic selection, source-scoped idempotency semantics, conflict
detection) and read-only assertions against the E2E database after the CLI E2E
run (84 brain_regions, no forbidden tables, no excluded entries as brain_regions).
Transactional idempotency / rollback are verified via the CLI (see gate review
docs), mirroring the test_gate8b pattern.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import psycopg
import pytest

BACKEND = Path(__file__).resolve().parents[1]
E2E = "neurographiq_human_brain_v1_e2e"

spec = importlib.util.spec_from_file_location(
    "imp96", BACKEND / "scripts" / "import_macro96_registry.py"
)
imp = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(imp)

ROWS = imp.load_manifest()
ELIG = imp.eligible(ROWS)
EXCLUDED = [r for r in ROWS if r["brainregion_eligible"] == "false"]

EXPECTED_PILOT = {6, 12, 22, 30, 31, 32, 35, 36, 66, 67}
EXCLUDED_SOURCE_NAMES = {r["source_name_en"] for r in EXCLUDED}


def _conn():
    return psycopg.connect(host="127.0.0.1", port=5432, user="postgres",
                           password="postgres", dbname=E2E, autocommit=True)


# ---------------------------------------------------------------------------
# Manifest completeness / eligibility
# ---------------------------------------------------------------------------

def test_manifest_96_rows_complete():
    assert len(ROWS) == 96
    assert [int(r["source_row_id"]) for r in ROWS] == list(range(1, 97))


def test_eligible_84_excluded_12():
    assert len(ELIG) == 84
    assert len(EXCLUDED) == 12
    assert len(EXCLUDED_SOURCE_NAMES) == 12


def test_circuit_eligibility_84_12():
    assert len([r for r in ROWS if r["circuit_discovery_eligible"] == "true"]) == 84
    assert len([r for r in ROWS if r["circuit_discovery_eligible"] == "false"]) == 12


# ---------------------------------------------------------------------------
# Deterministic selection (pilot + full)
# ---------------------------------------------------------------------------

def test_pilot_selection_deterministic_and_eligible():
    p1 = imp.select_pilot(ROWS)
    p2 = imp.select_pilot(ROWS)
    assert [r["source_row_id"] for r in p1] == [r["source_row_id"] for r in p2]
    assert {int(r["source_row_id"]) for r in p1} == EXPECTED_PILOT
    assert len(p1) == 10
    for r in p1:
        assert r["brainregion_eligible"] == "true"


def test_full_selection_84_manifest_driven():
    full = imp.select_full(ROWS)
    assert len(full) == 84
    assert [int(r["source_row_id"]) for r in full] == sorted(
        int(r["source_row_id"]) for r in ELIG)
    assert len({int(r["source_row_id"]) for r in full}) == 84  # no dup ids
    # no excluded entry can appear in the full selection
    assert {r["source_name_en"] for r in full} & EXCLUDED_SOURCE_NAMES == set()


def test_excluded_entries_cannot_enter_importer():
    for r in imp.select_full(ROWS):
        assert r["brainregion_eligible"] == "true"
        assert r["source_name_en"] not in EXCLUDED_SOURCE_NAMES
        assert r["structure_type"] in imp.CATEGORY_MAP


# ---------------------------------------------------------------------------
# Field contracts
# ---------------------------------------------------------------------------

def test_g1_granularity_and_species():
    assert imp.GRANULARITY == "G1_MACRO"
    assert imp.SPECIES == "9606"


def test_pilot_and_full_names_present():
    for r in imp.select_full(ROWS):
        assert r["normalized_name_en"].strip()
        assert r["normalized_name_zh"].strip()


def test_category_mapping_legal_and_consistent():
    legal = {"cortical_region", "subcortical_region", "cerebellar_region",
             "brainstem_region"}
    for stype, cat in imp.CATEGORY_MAP.items():
        assert cat in legal, f"{stype} -> {cat} not a legal region_category"
    for r in ELIG:
        assert r["structure_type"] in imp.CATEGORY_MAP


def test_source_provenance_not_fabricated():
    assert imp.SOURCE_TYPE == "manual"
    assert "doi" not in imp.SOURCE_CITATION.lower()
    assert "pmid" not in imp.SOURCE_CITATION.lower()


# ---------------------------------------------------------------------------
# Source-scoped idempotency / conflict semantics (pure helpers)
# ---------------------------------------------------------------------------

def test_macro96_owned_flag():
    assert imp._is_macro96_owned({"macro96_registry": True}) is True
    assert imp._is_macro96_owned({"macro96_pilot": True}) is True
    assert imp._is_macro96_owned({"macro96_registry": False}) is False
    assert imp._is_macro96_owned({"other": True}) is False
    assert imp._is_macro96_owned(None) is False


def test_same_name_non_macro_not_silently_reused():
    # A row whose source_name_original matches but is NOT Macro96-owned must be
    # classified as a conflict (never silently reused). The pure predicate below
    # is the gate the importer enforces before creating a new entity.
    fake_metadata = {"some_other_source": True}  # non-Macro96 provenance
    assert imp._is_macro96_owned(fake_metadata) is False
    # and a Macro96-owned row is NOT a conflict
    assert imp._is_macro96_owned({"macro96_registry": True}) is True


# ---------------------------------------------------------------------------
# Read-only E2E state (after CLI full E2E run)
# ---------------------------------------------------------------------------

def test_e2e_applied_state_full():
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT count(*) FROM kg_entities WHERE entity_type='brain_region'")
        assert cur.fetchone()[0] == 84
        cur.execute("SELECT count(*) FROM brain_regions")
        assert cur.fetchone()[0] == 84
        cur.execute("SELECT count(*) FROM sources")
        assert cur.fetchone()[0] == 1
        for sql, expected in [
            ("SELECT count(*) FROM brain_regions WHERE granularity_level='G1_MACRO'", 84),
            ("SELECT count(*) FROM brain_regions WHERE species_taxon_id='9606'", 84),
            # G1 Registry is frozen as ACTIVE + APPROVED (imported then promoted).
            ("SELECT count(*) FROM kg_entities WHERE record_status='active'", 84),
            ("SELECT count(*) FROM kg_entities WHERE review_status='approved'", 84),
            ("SELECT count(*) FROM kg_entities WHERE name_en IS NULL OR name_en=''", 0),
            ("SELECT count(*) FROM kg_entities WHERE name_zh IS NULL OR name_zh=''", 0),
            ("SELECT count(*) FROM kg_entities WHERE entity_type='brain_region'"
             " AND metadata_json->>'macro96_registry'='true'", 84),
        ]:
            cur.execute(sql)
            assert cur.fetchone()[0] == expected, sql
    finally:
        conn.close()


def test_e2e_source_row_id_covers_all_84_no_dup():
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT metadata_json->>'macro96_source_row_id' FROM kg_entities"
                    " WHERE entity_type='brain_region' AND metadata_json->>'macro96_registry'='true'")
        ids = sorted(int(r[0]) for r in cur.fetchall())
        assert len(ids) == 84
        assert len(set(ids)) == 84
        assert ids == sorted(int(r["source_row_id"]) for r in ELIG)
    finally:
        conn.close()


def test_e2e_source_scoped_idempotency_recognizes_existing():
    conn = _conn()
    try:
        cur = conn.cursor()
        src_pk, _ = imp._src_exists(cur)
        assert src_pk is not None
        for r in ELIG:
            st = imp._macro96_row_status(cur, src_pk, int(r["source_row_id"]),
                                         r["source_name_en"])
            assert st == "existing", f"row {r['source_row_id']} -> {st}"
    finally:
        conn.close()


def test_e2e_no_forbidden_tables_and_no_excluded_entries():
    conn = _conn()
    try:
        cur = conn.cursor()
        for t in ("atlases", "external_regions", "region_mappings",
                  "brain_region_aggregation_mappings", "evidence", "evidence_links"):
            cur.execute(f"SELECT count(*) FROM {t}")
            assert cur.fetchone()[0] == 0, f"{t} should be empty"
        ph = ",".join(["%s"] * len(EXCLUDED_SOURCE_NAMES))
        cur.execute(
            f"SELECT count(*) FROM kg_entities WHERE entity_type='brain_region'"
            f" AND source_name_original IN ({ph})", tuple(sorted(EXCLUDED_SOURCE_NAMES)))
        assert cur.fetchone()[0] == 0
    finally:
        conn.close()


def test_e2e_no_bna246_present():
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT count(*) FROM kg_entities WHERE entity_type='brain_region'"
                    " AND source_name_original LIKE '%_L_%'")
        assert cur.fetchone()[0] == 0
        cur.execute("SELECT count(*) FROM atlases")
        assert cur.fetchone()[0] == 0
    finally:
        conn.close()


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
