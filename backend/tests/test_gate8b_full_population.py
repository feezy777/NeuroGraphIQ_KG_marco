"""Gate 8B — Full Brainnetome BNA246 population tests.

Covers the importer's pure source-parsing / deterministic-naming functions and
read-only completeness/uniqueness assertions against the production database.
The transactional rollback and rerun-idempotency checks are verified separately
via the CLI (see gate_08b review docs).
"""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

import psycopg
import pytest

BACKEND = Path(__file__).resolve().parents[1]
PROD = "neurographiq_human_brain_v1"

spec = importlib.util.spec_from_file_location(
    "imp", BACKEND / "scripts" / "import_brainnetome_pilot.py"
)
imp = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(imp)


def _conn():
    return psycopg.connect(host="127.0.0.1", port=5432, user="postgres",
                           password="postgres", dbname=PROD, autocommit=True)


BANDS = imp._parse_bands()


# ---------------------------------------------------------------------------
# Pure source / naming functions
# ---------------------------------------------------------------------------


def test_source_parser_246():
    assert len(BANDS) == 246


def test_source_validate_ok_left_right():
    info = imp._validate_source(BANDS)  # raises on any issue (fail closed)
    assert info["left"] == 123
    assert info["right"] == 123
    assert len(info["by_gyrus"]) == 25


def test_all_gyri_resolvable_no_unknown_anatomy():
    for b in BANDS:
        assert b["gyrus"] in imp._BNA_ANATOMICAL_NAMES, b["native_name"]


def test_name_generation_deterministic():
    en1, zh1 = imp._canonical_names(BANDS[0])
    en2, zh2 = imp._canonical_names(BANDS[0])
    assert (en1, zh1) == (en2, zh2)


def test_lr_name_correctness():
    for b in BANDS:
        en, zh = imp._canonical_names(b)
        if b["hemi"] == "L":
            assert en.startswith("Left ") and zh.startswith("左侧"), b["native_name"]
        else:
            assert en.startswith("Right ") and zh.startswith("右侧"), b["native_name"]


def test_canonical_en_unique_all():
    names = [imp._canonical_names(b)[0] for b in BANDS]
    assert len(names) == len(set(names))


def test_canonical_zh_unique_all():
    names = [imp._canonical_names(b)[1] for b in BANDS]
    assert len(names) == len(set(names))


# ---------------------------------------------------------------------------
# Database completeness / uniqueness (read-only, production)
# ---------------------------------------------------------------------------


def test_pilot_20_ids_reused():
    base = json.load(open(BACKEND / "_gate8a_baseline.json"))
    conn = _conn()
    try:
        cur = conn.cursor()
        for kind in ("brain_regions", "external_regions"):
            ok = 0
            for src, info in base[kind].items():
                cur.execute("SELECT entity_id FROM kg_entities WHERE entity_type=%s AND source_name_original=%s",
                            ("brain_region" if kind == "brain_regions" else "external_region", src))
                r = cur.fetchone()
                if r and r[0] == info["id"]:
                    ok += 1
            assert ok == 20, f"{kind}: {ok}/20 IDs preserved"
    finally:
        conn.close()


def test_full_246_completeness():
    conn = _conn()
    try:
        cur = conn.cursor()
        for t in ("brain_regions", "external_regions", "region_mappings", "entity_aliases", "entity_xrefs"):
            cur.execute(f"SELECT count(*) FROM {t}")
            assert cur.fetchone()[0] == 246, t
        cur.execute("SELECT count(*) FROM sources"); assert cur.fetchone()[0] == 1
        cur.execute("SELECT count(*) FROM atlases"); assert cur.fetchone()[0] == 1
    finally:
        conn.close()


def test_numeric_xref_unique():
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT count(*) FROM (SELECT external_id FROM entity_xrefs WHERE source_database='Brainnetome' GROUP BY external_id HAVING count(*)>1) x")
        assert cur.fetchone()[0] == 0
        cur.execute("SELECT count(*) FROM entity_xrefs WHERE source_database='Brainnetome' AND external_id ~ '^[0-9]+$'")
        assert cur.fetchone()[0] == 246  # all numeric, no L1/R2 fabrication
    finally:
        conn.close()


def test_native_alias_preserved():
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT count(*) FROM kg_entities e JOIN brain_regions b ON b.entity_pk=e.entity_pk
            LEFT JOIN entity_aliases a ON a.entity_pk=e.entity_pk AND a.alias_type='atlas_label'
            WHERE a.alias_pk IS NULL OR a.alias_text <> e.source_name_original
        """)
        assert cur.fetchone()[0] == 0  # every region has its native atlas label alias
    finally:
        conn.close()


def test_exact_mapping_policy():
    conn = _conn()
    try:
        cur = conn.cursor()
        for sql in ("SELECT count(*) FROM region_mappings WHERE mapping_type<>'exact'",
                    "SELECT count(*) FROM region_mappings WHERE mapping_method<>'automatic'",
                    "SELECT count(*) FROM region_mappings WHERE mapping_source<>'brainnetome_direct'",
                    "SELECT count(*) FROM region_mappings WHERE review_status<>'pending'"):
            cur.execute(sql)
            assert cur.fetchone()[0] == 0
    finally:
        conn.close()


def test_similarity_confidence_null():
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT count(*) FROM region_mappings WHERE name_similarity IS NOT NULL"
                    " OR semantic_similarity IS NOT NULL OR spatial_overlap IS NOT NULL"
                    " OR overall_confidence IS NOT NULL")
        assert cur.fetchone()[0] == 0
    finally:
        conn.close()


def test_proposed_only_human_only_g3_only():
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT count(*) FROM kg_entities e JOIN brain_regions b ON b.entity_pk=e.entity_pk WHERE e.record_status<>'proposed'")
        assert cur.fetchone()[0] == 0
        cur.execute("SELECT count(*) FROM brain_regions WHERE species_taxon_id<>'9606'")
        assert cur.fetchone()[0] == 0
        cur.execute("SELECT count(*) FROM brain_regions WHERE granularity_level<>'G3_MESO_FINE'")
        assert cur.fetchone()[0] == 0
    finally:
        conn.close()


def test_hemisphere_distribution_matches_source():
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT hemisphere, count(*) FROM brain_regions GROUP BY hemisphere")
        db = dict(cur.fetchall())
        assert db == {"left": 123, "right": 123}
    finally:
        conn.close()


def test_aggregation_zero():
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT count(*) FROM brain_region_aggregation_mappings")
        assert cur.fetchone()[0] == 0
    finally:
        conn.close()


def test_schema_still_32():
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT count(*) FROM pg_tables WHERE schemaname='public'")
        assert cur.fetchone()[0] == 32
    finally:
        conn.close()
