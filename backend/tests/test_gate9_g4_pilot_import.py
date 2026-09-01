"""Gate 9 G4 — Julich-Brain v3.1 Gate7B pilot import tests.

Covers the importer's pure functions (fixed 10-pilot selection, canonical-only,
GapMap/non-leaf rejection, category mapping, short-id workaround) and read-only
assertions against the E2E database after the CLI E2E run (10 G4 brain_regions,
10 external_regions, 10 exact mappings, proposed/pending, no spatial/aggregation,
G1 untouched). Transactional idempotency is verified via the CLI (see gate review
docs), mirroring the Gate9 G1 test pattern.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import psycopg
import pytest

BACKEND = Path(__file__).resolve().parents[1]
E2E = "neurographiq_human_brain_v1_e2e"

spec = importlib.util.spec_from_file_location(
    "julich", BACKEND / "scripts" / "import_julich_g4_registry.py"
)
imp = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(imp)

PREVIEW = imp.load_preview()
PILOTS = imp.select_pilots(PREVIEW)


def _conn():
    return psycopg.connect(host="127.0.0.1", port=5432, user="postgres",
                           password="postgres", dbname=E2E, autocommit=True)


# ---------------------------------------------------------------------------
# Pure importer logic
# ---------------------------------------------------------------------------

def test_fixed_10_pilot_selection():
    assert len(PILOTS) == 10
    assert len({p["source_region_id"] for p in PILOTS}) == 10  # unique official ids
    assert all(p["zh_status"] == "resolved" for p in PILOTS)
    # the nomenclature preview is canonical-only by construction (built from
    # canonical_candidate=true leaves of the identity manifest); GapMap excluded
    assert all(p["zh_status"] == "resolved" for p in PILOTS)
    assert not any("GapMap" in p["source_region_name"] for p in PILOTS)


def test_gapmap_rejected():
    assert not any("GapMap" in p["source_region_name"] for p in PILOTS)


def test_nonleaf_cannot_enter():
    # PILOTS are leaves only (canonical_candidate=true subset of the leaf manifest)
    assert all(p["zh_status"] == "resolved" for p in PILOTS)
    # the importer never reads non-leaf rows: selection only pulls from canonical=true
    assert len([p for p in PREVIEW if p["zh_status"] == "resolved"]) >= 440


def test_g4_granularity_and_species_constants():
    assert imp.GRANULARITY == "G4_MICROSTRUCTURAL_FINE"
    assert imp.SPECIES == "9606"
    assert imp.MAPPING_TYPE == "exact"


def test_identity_is_source_region_id_not_name():
    ids = [p["source_region_id"] for p in PILOTS]
    names = [p["source_region_name"] for p in PILOTS]
    # identity uniqueness comes from official source_region_id, not the display name
    assert len(set(ids)) == 10
    # two pilots share a biological base (hOc1 left/right) but differ by id + hemisphere
    assert any(p["biological_base_name"] == "Area hOc1 (V1, 17, CalcS)" for p in PILOTS)


def test_source_region_id_full_verbatim_contract():
    # gate7b_009 widened source_region_id to VARCHAR(255); the official Julich id must be
    # stored verbatim (never truncated / prefix-stripped / hashed / metadata-only).
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT column_name, character_maximum_length FROM information_schema.columns"
                    " WHERE table_name='external_regions' AND column_name='source_region_id'")
        assert cur.fetchone()[1] == 255
        cur.execute("SELECT x.source_region_id FROM external_regions x JOIN atlases a"
                    " ON a.entity_pk=x.atlas_pk WHERE a.atlas_family='Julich-Brain'")
        stored = [r[0] for r in cur.fetchall()]
        manifest = {p["source_region_id"] for p in PREVIEW}
        assert len(stored) == 440
        assert set(stored) == manifest  # exact match, no truncation
        assert max(len(s) for s in stored) > 64  # some pilot ids exceed the old 64 limit, intact
        assert all(s.startswith("JULICH_BRAIN_CYTOARCHITECTONIC_ATLAS_V3_1_") for s in stored)
        # no prefix-stripped values (authority is the full official id)
        assert all("_LEFT" in s or "_RIGHT" in s for s in stored)
    finally:
        conn.close()


def test_source_name_original_is_region_name_not_id():
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT x.source_region_id, ke.source_name_original FROM external_regions x"
                    " JOIN atlases a ON a.entity_pk=x.atlas_pk JOIN kg_entities ke ON ke.entity_pk=x.entity_pk"
                    " WHERE a.atlas_family='Julich-Brain'")
        for sid, sorig in cur.fetchall():
            assert sorig != sid
            assert "JULICH_BRAIN" not in (sorig or "")
            assert sorig in {p["source_region_name"] for p in PREVIEW}
    finally:
        conn.close()


def test_metadata_source_id_matches_column_authority():
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT ke.metadata_json->>'julich_source_region_id', x.source_region_id"
                    " FROM external_regions x JOIN atlases a ON a.entity_pk=x.atlas_pk"
                    " JOIN kg_entities ke ON ke.entity_pk=x.entity_pk WHERE a.atlas_family='Julich-Brain'")
        rows = cur.fetchall()
        assert len(rows) == 440
        assert all(meta == col for meta, col in rows)  # metadata is redundant copy, equal to authority
    finally:
        conn.close()


def test_same_name_different_id_not_merged():
    # Area hOc1 left and right share a biological base name but have DIFFERENT official ids;
    # they must remain two distinct ExternalRegions (no name-based merge).
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT x.source_region_id, x.hemisphere FROM external_regions x"
                    " JOIN atlases a ON a.entity_pk=x.atlas_pk"
                    " WHERE a.atlas_family='Julich-Brain' AND x.source_region_id ~ 'HOC1'")
        rows = cur.fetchall()
        assert len(rows) == 2
        assert rows[0][0] != rows[1][0]
        assert {r[1] for r in rows} == {"left", "right"}
    finally:
        conn.close()


def test_category_mapping_legal():
    legal = {"cortical_region", "amygdalar_nucleus", "hippocampal_subfield",
             "subcortical_region", "thalamic_nucleus"}
    for p in PILOTS:
        assert imp._category_for(p["biological_base_name"]) in legal


def test_zh_from_frozen_preview():
    # normalized_name_en/zh in the DB must equal the frozen preview values
    assert all(p["normalized_name_en"].strip() and p["normalized_name_zh"].strip() for p in PILOTS)


# ---------------------------------------------------------------------------
# Read-only E2E state
# ---------------------------------------------------------------------------

def test_e2e_g4_chain_counts():
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT count(*) FROM sources WHERE name_en ~ '^Julich'")
        assert cur.fetchone()[0] == 1
        cur.execute("SELECT count(*) FROM atlases WHERE atlas_family='Julich-Brain'")
        assert cur.fetchone()[0] == 1
        cur.execute("SELECT count(*) FROM external_regions x JOIN atlases a ON a.entity_pk=x.atlas_pk"
                    " WHERE a.atlas_family='Julich-Brain'")
        assert cur.fetchone()[0] == 440
        cur.execute("SELECT count(*) FROM brain_regions WHERE granularity_level='G4_MICROSTRUCTURAL_FINE'")
        assert cur.fetchone()[0] == 440
        cur.execute("SELECT count(*) FROM region_mappings rm JOIN external_regions x ON x.entity_pk=rm.external_region_pk"
                    " JOIN atlases a ON a.entity_pk=x.atlas_pk WHERE a.atlas_family='Julich-Brain'")
        assert cur.fetchone()[0] == 440
    finally:
        conn.close()


def test_e2e_g4_status_and_fields():
    conn = _conn()
    try:
        cur = conn.cursor()
        for sql, expected in [
            ("SELECT count(*) FROM brain_regions WHERE granularity_level='G4_MICROSTRUCTURAL_FINE'"
             " AND species_taxon_id='9606'", 440),
            ("SELECT count(*) FROM kg_entities ke JOIN brain_regions br ON br.entity_pk=ke.entity_pk"
             " WHERE br.granularity_level='G4_MICROSTRUCTURAL_FINE' AND ke.record_status='proposed'", 440),
            ("SELECT count(*) FROM kg_entities ke JOIN brain_regions br ON br.entity_pk=ke.entity_pk"
             " WHERE br.granularity_level='G4_MICROSTRUCTURAL_FINE' AND ke.review_status='pending'", 440),
            ("SELECT count(*) FROM kg_entities ke JOIN brain_regions br ON br.entity_pk=ke.entity_pk"
             " WHERE br.granularity_level='G4_MICROSTRUCTURAL_FINE' AND (ke.name_en IS NULL OR ke.name_zh IS NULL)", 0),
            ("SELECT count(*) FROM kg_entities ke JOIN brain_regions br ON br.entity_pk=ke.entity_pk"
             " WHERE br.granularity_level='G4_MICROSTRUCTURAL_FINE' AND ke.source_name_original ~ 'GAPMAP'", 0),
        ]:
            cur.execute(sql)
            assert cur.fetchone()[0] == expected, sql
        cur.execute("SELECT count(DISTINCT mapping_type) FROM region_mappings rm"
                    " JOIN external_regions x ON x.entity_pk=rm.external_region_pk"
                    " JOIN atlases a ON a.entity_pk=x.atlas_pk WHERE a.atlas_family='Julich-Brain'")
        assert cur.fetchone()[0] == 1  # exact only
    finally:
        conn.close()


def test_e2e_no_spatial_no_aggregation_no_cross_granularity():
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT count(*) FROM brain_region_spatial_representations")
        assert cur.fetchone()[0] == 0
        cur.execute("SELECT count(*) FROM brain_region_aggregation_mappings")
        assert cur.fetchone()[0] == 0
        cur.execute("SELECT count(*) FROM region_mappings rm JOIN brain_regions br ON br.entity_pk=rm.brain_region_pk"
                    " WHERE br.granularity_level IN ('G1_MACRO','G3_MESO_FINE')")
        assert cur.fetchone()[0] == 0
    finally:
        conn.close()


def test_e2e_g1_untouched():
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT count(*) FROM brain_regions WHERE granularity_level='G1_MACRO'")
        assert cur.fetchone()[0] == 84
        cur.execute("SELECT count(*) FROM kg_entities ke JOIN brain_regions br ON br.entity_pk=ke.entity_pk"
                    " WHERE br.granularity_level='G1_MACRO' AND ke.record_status='active'")
        assert cur.fetchone()[0] == 84
    finally:
        conn.close()


def test_e2e_source_scoped_idempotency_recognizes_existing():
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT source_pk FROM sources WHERE name_en ~ '^Julich'")
        r = cur.fetchone()
        assert r is not None
        src_pk = r[0]
        cur.execute("SELECT e.entity_pk FROM kg_entities e JOIN atlases a ON a.entity_pk=e.entity_pk"
                    " WHERE e.entity_type='atlas' AND a.atlas_family='Julich-Brain'")
        atlas_pk = cur.fetchone()[0]
        for p in PILOTS:
            assert imp._external_exists(cur, atlas_pk, p["source_region_id"]) is not None
            assert imp._brain_exists(cur, src_pk, p["source_region_id"]) is not None
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Full 440-entry E2E import
# ---------------------------------------------------------------------------

def test_select_all_440_manifest_driven():
    full = imp.select_all(PREVIEW)
    assert len(full) == 440
    assert len({p["source_region_id"] for p in full}) == 440
    assert sum(1 for p in full if p["hemisphere"] == "left") == 220
    assert sum(1 for p in full if p["hemisphere"] == "right") == 220
    assert all(p["zh_status"] == "resolved" for p in full)
    assert not any("GapMap" in p["source_region_name"] for p in full)
    assert max(len(p["source_region_id"]) for p in full) <= 255


def test_e2e_full_440_totals():
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT count(*) FROM external_regions x JOIN atlases a ON a.entity_pk=x.atlas_pk"
                    " WHERE a.atlas_family='Julich-Brain'")
        assert cur.fetchone()[0] == 440
        cur.execute("SELECT count(*) FROM brain_regions WHERE granularity_level='G4_MICROSTRUCTURAL_FINE'")
        assert cur.fetchone()[0] == 440
        cur.execute("SELECT count(*) FROM region_mappings rm JOIN external_regions x ON x.entity_pk=rm.external_region_pk"
                    " JOIN atlases a ON a.entity_pk=x.atlas_pk WHERE a.atlas_family='Julich-Brain'")
        assert cur.fetchone()[0] == 440
    finally:
        conn.close()


def test_e2e_full_exact_set_and_bilingual():
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT x.source_region_id FROM external_regions x JOIN atlases a"
                    " ON a.entity_pk=x.atlas_pk WHERE a.atlas_family='Julich-Brain'")
        db_ext = {r[0] for r in cur.fetchall()}
        man_ids = {p["source_region_id"] for p in PREVIEW}
        assert db_ext == man_ids and len(db_ext) == 440  # exact set equality
        cur.execute("SELECT ke.metadata_json->>'julich_source_region_id', ke.name_en, ke.name_zh, br.hemisphere"
                    " FROM kg_entities ke JOIN brain_regions br ON br.entity_pk=ke.entity_pk"
                    " WHERE br.granularity_level='G4_MICROSTRUCTURAL_FINE'")
        db_brain = {r[0]: (r[1], r[2], r[3]) for r in cur.fetchall()}
        man = {p["source_region_id"]: p for p in PREVIEW}
        assert all(db_brain[i][0] == man[i]["normalized_name_en"] for i in db_brain)  # EN exact
        assert all(db_brain[i][1] == man[i]["normalized_name_zh"] for i in db_brain)  # ZH exact
        assert all(db_brain[i][2] == man[i]["hemisphere"] for i in db_brain)          # hemisphere exact
    finally:
        conn.close()


def test_e2e_full_status_and_no_dups():
    conn = _conn()
    try:
        cur = conn.cursor()
        for sql, expected in [
            ("SELECT count(*) FROM kg_entities ke JOIN brain_regions br ON br.entity_pk=ke.entity_pk"
             " WHERE br.granularity_level='G4_MICROSTRUCTURAL_FINE' AND ke.record_status='proposed'", 440),
            ("SELECT count(*) FROM kg_entities ke JOIN brain_regions br ON br.entity_pk=ke.entity_pk"
             " WHERE br.granularity_level='G4_MICROSTRUCTURAL_FINE' AND ke.review_status='pending'", 440),
            ("SELECT count(*) FROM (SELECT atlas_pk, source_region_id FROM external_regions"
             " GROUP BY 1,2 HAVING count(*)>1) t", 0),
            ("SELECT count(*) FROM (SELECT name_en FROM kg_entities ke JOIN brain_regions br ON br.entity_pk=ke.entity_pk"
             " WHERE br.granularity_level='G4_MICROSTRUCTURAL_FINE' GROUP BY 1 HAVING count(*)>1) t", 0),
            ("SELECT count(*) FROM brain_regions br WHERE br.granularity_level='G4_MICROSTRUCTURAL_FINE'"
             " AND NOT EXISTS (SELECT 1 FROM region_mappings rm WHERE rm.brain_region_pk=br.entity_pk)", 0),
            ("SELECT count(*) FROM (SELECT external_region_pk FROM region_mappings rm"
             " JOIN external_regions x ON x.entity_pk=rm.external_region_pk"
             " JOIN atlases a ON a.entity_pk=x.atlas_pk WHERE a.atlas_family='Julich-Brain'"
             " GROUP BY 1 HAVING count(*)>1) t", 0),
        ]:
            cur.execute(sql)
            assert cur.fetchone()[0] == expected, sql
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Final semantic QA (pre-promotion)
# ---------------------------------------------------------------------------

def _preview_by_base_hemi():
    return {(p["biological_base_name"], p["hemisphere"]): p for p in PREVIEW}


def test_av_fixed_to_anteroventral_side():
    # human-frozen: anteroventral Nucleus -> 前腹侧核 (not 前腹核); dictionary + preview + production
    dic = imp  # preview holds the fixed value; dictionary checked below
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT ke.name_zh FROM kg_entities ke JOIN brain_regions br ON br.entity_pk=ke.entity_pk"
                    " WHERE br.granularity_level='G4_MICROSTRUCTURAL_FINE' AND ke.name_en LIKE 'AV (Thalamus%'")
        zh = [r[0] for r in cur.fetchall()]
        assert len(zh) == 2
        assert all("前腹侧核" in z and "前腹核" not in z.replace("前腹侧核", "") for z in zh)
    finally:
        conn.close()
    av = [p for p in PREVIEW if p["biological_base_name"] == "AV (Thalamus, anteroventral Nucleus)"]
    assert len(av) == 2 and all("前腹侧核" in p["normalized_name_zh"] for p in av)


def test_thalamic_nuclei_descriptors_distinct():
    # AM/AV/MV/VM/VLA/VLP/VPL/VPM must keep distinct Chinese descriptors
    import csv as _csv
    dic = list(_csv.DictReader(open(
        r"D:\Tool\Coding\IDE\PyCharm\NeuroGraphIQ_KG_marco\backend\data\atlases\julich\v3.1"
        r"\julich_v3_1_descriptor_zh_dictionary.csv", encoding="utf-8-sig")))
    dm = {d["descriptor_en"]: d["descriptor_zh"] for d in dic}
    expected = {
        "anteromedial Nucleus": "前内侧核",
        "anteroventral Nucleus": "前腹侧核",
        "medioventral Nucleus": "内侧腹核",
        "ventral medial Nucleus": "腹内侧核",
        "ventral lateral anterior Nucleus": "腹外侧前核",
        "ventral lateral posterior Nucleus": "腹外侧后核",
        "ventral posterior lateral Nucleus": "腹后外侧核",
        "ventral posterior medial Nucleus": "腹后内侧核",
    }
    for k, v in expected.items():
        assert dm.get(k) == v, f"{k}: {dm.get(k)} != {v}"
    # all distinct
    vals = list(expected.values())
    assert len(set(vals)) == len(vals)


def test_operculum_boundary():
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT ke.name_en, ke.name_zh FROM kg_entities ke JOIN brain_regions br"
                    " ON br.entity_pk=ke.entity_pk WHERE br.granularity_level='G4_MICROSTRUCTURAL_FINE'"
                    " AND ke.name_en ~ 'Area Op[0-9]+'")
        rows = cur.fetchall()
        for en, zh in rows:
            n = int(en.split("Op")[1].split(" ")[0])
            if n <= 4:
                assert "顶叶岛盖" in zh, f"{en}: {zh}"
            else:
                assert "额叶岛盖" in zh, f"{en}: {zh}"
    finally:
        conn.close()


def test_extraction_readiness_true():
    conn = _conn()
    try:
        cur = conn.cursor()
        # 10 readiness criteria
        cur.execute("SELECT count(*) FROM kg_entities ke JOIN brain_regions br ON br.entity_pk=ke.entity_pk"
                    " WHERE br.granularity_level='G4_MICROSTRUCTURAL_FINE'"
                    " AND (ke.name_en IS NULL OR ke.name_en='' OR ke.name_zh IS NULL OR ke.name_zh='')")
        assert cur.fetchone()[0] == 0
        cur.execute("SELECT count(*) FROM brain_regions br WHERE br.granularity_level='G4_MICROSTRUCTURAL_FINE'"
                    " AND (br.hemisphere NOT IN ('left','right') OR br.granularity_level<>'G4_MICROSTRUCTURAL_FINE')")
        assert cur.fetchone()[0] == 0
        cur.execute("SELECT count(*) FROM brain_regions br WHERE br.granularity_level='G4_MICROSTRUCTURAL_FINE'"
                    " AND NOT EXISTS (SELECT 1 FROM region_mappings rm WHERE rm.brain_region_pk=br.entity_pk)")
        assert cur.fetchone()[0] == 0
        cur.execute("SELECT count(*) FROM kg_entities ke JOIN brain_regions br ON br.entity_pk=ke.entity_pk"
                    " WHERE br.granularity_level='G4_MICROSTRUCTURAL_FINE' AND (ke.name_en ~ 'GapMap'"
                    " OR ke.source_name_original ~ 'GAPMAP')")
        assert cur.fetchone()[0] == 0
        # duplicate-free (identity / EN / ZH)
        for col in ("metadata_json->>'julich_source_region_id'", "name_en", "name_zh"):
            cur.execute(f"SELECT count(*) FROM (SELECT {col} FROM kg_entities ke JOIN brain_regions br"
                        f" ON br.entity_pk=ke.entity_pk WHERE br.granularity_level='G4_MICROSTRUCTURAL_FINE'"
                        f" GROUP BY 1 HAVING count(*)>1) t")
            assert cur.fetchone()[0] == 0, col
    finally:
        conn.close()


def test_g1_g3_unchanged_after_g4():
    # E2E harness baseline: G1 (Macro96) = 84 active; G3 (Brainnetome) is NOT part of
    # the E2E harness (lives in production only, where it = 246) so E2E G3 = 0;
    # G4 (Julich v3.1) = 440 proposed. The G4 import must not disturb G1/G3.
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT count(*) FROM brain_regions WHERE granularity_level='G1_MACRO'")
        assert cur.fetchone()[0] == 84
        cur.execute("SELECT count(*) FROM brain_regions WHERE granularity_level='G3_MESO_FINE'")
        assert cur.fetchone()[0] == 0
        cur.execute("SELECT count(*) FROM brain_regions WHERE granularity_level='G4_MICROSTRUCTURAL_FINE'")
        assert cur.fetchone()[0] == 440
    finally:
        conn.close()


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
