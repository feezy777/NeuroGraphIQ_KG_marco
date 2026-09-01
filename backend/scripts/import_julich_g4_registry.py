"""G4 Julich-Brain v3.1 Gate7B-native registry importer (E2E pilot).

Builds the full reference chain for a fixed 10-entry pilot:
  Source -> Atlas -> ExternalRegion (x10) -> exact RegionMapping (x10)
        -> canonical G4 BrainRegion (x10)

Uses ONLY the frozen Julich v3.1 snapshots under backend/data/atlases/julich/v3.1/.
Reuses the Gate7B NGIQ ID machinery, transaction, plan/apply, and idempotency
patterns of the Gate8B/Gate9 importers. Never writes legacy canonical_* tables.

Identity rules (frozen):
  * Julich source identity   = (Julich v3.1 Source) + (official source_region_id)
  * ExternalRegion identity  = (Julich Atlas) + (official source_region_id)
  * G4 canonical identity    = (Julich v3.1) + (official source_region_id)
  * A same/similar name across G1/G3/G4 is NOT identity and is never merged.

Safety:
  * PLAN is read-only (preflight).
  * APPLY refuses any database that is not an allowed TEST database unless the
    explicit --allow-production flag is given (production apply is NOT authorized
    for this pilot; the flag is only wired for a future authorized operation).
  * Idempotent: re-running APPLY produces 0 new objects.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

try:
    import psycopg
except ImportError:
    print("ERROR: psycopg (psycopg3) required")
    sys.exit(2)

from app.database_guard import (
    MAIN_DATABASE,
    assert_allowed_database,
    is_allowed_test_database,
)

JULICH_DIR = BACKEND_DIR / "data" / "atlases" / "julich" / "v3.1"
PREVIEW = JULICH_DIR / "julich_v3_1_g4_nomenclature_preview.csv"

DB_DEFAULT = "neurographiq_human_brain_v1_e2e"

# Frozen Julich v3.1 provenance (from julich_v3_1_parcellation_metadata.json).
SOURCE_NAME_EN = "Julich-Brain Cytoarchitectonic Atlas v3.1"
SOURCE_NAME_ZH = "人脑细胞构筑图谱 v3.1"
SOURCE_ABBR = "Julich-Brain"
SOURCE_VERSION = "3.1.0"
SOURCE_TYPE = "atlas"
SOURCE_PROVIDER = "Forschungszentrum Jülich (INM-1 / EBRAINS)"
SOURCE_SPECIES = "Homo sapiens (NCBI:9606)"
PARCELLATION_ID = "minds/core/parcellationatlas/v1.0.0/94c1125b-b87e-45e4-901c-00daee7f2579-310"
ATLAS_DOI = "10.25493/KNSN-XB4"
SOURCE_CITATION = (
    "Amunts, K., Mohlberg, H., Bludau, S., Zilles, K. (2020). Julich-Brain – A 3D probabilistic "
    "atlas of human brain's cytoarchitecture. Science 369, 988-992. "
    "Atlas DOI: 10.25493/KNSN-XB4"
)

GRANULARITY = "G4_MICROSTRUCTURAL_FINE"
SPECIES = "9606"
MAPPING_SOURCE = "julich_direct"
MAPPING_METHOD = "automatic"
MAPPING_TYPE = "exact"

# external_regions.source_region_id (now VARCHAR(255), gate7b_009) is the authority for the
# official Julich region id; the FULL id is stored verbatim. metadata_json.julich_source_region_id
# is a redundant provenance copy only — never the identity authority.
# kg_entities.source_name_original holds the official Julich region NAME (not the id).

# Fixed 10-entry pilot (biological_base_name, hemisphere) — frozen, deterministic.
PILOTS = [
    ("Area hOc1 (V1, 17, CalcS)", "left"),
    ("Area hOc1 (V1, 17, CalcS)", "right"),
    ("Area Op1 (POperc)", "left"),
    ("Area Op5 (Frontal Operculum)", "right"),
    ("Area p24c.pv24c (pACC)", "left"),
    ("CM.AAA (Amygdala)", "right"),
    ("TrS (Hippocampus, Transsubiculum)", "left"),
    ("BST (Basal Forebrain, Bed Nucleus)", "right"),
    ("MV (Thalamus, medioventral Nucleus)", "left"),
    ("Area 5L (SPL)", "right"),
]


def _redact(secret: str | None) -> str:
    return "<REDACTED>" if secret else "<EMPTY>"


def load_preview() -> list[dict]:
    with open(PREVIEW, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def select_pilots(preview: list[dict]) -> list[dict]:
    """Deterministically select the fixed 10 pilot records (canonical + resolved only)."""
    out = []
    for base, hemi in PILOTS:
        hits = [p for p in preview
                if p["biological_base_name"] == base and p["hemisphere"] == hemi
                and p["zh_status"] == "resolved"]
        if not hits:
            raise RuntimeError(f"pilot not found: {base} / {hemi}")
        out.append(hits[0])
    assert len(out) == 10, "pilot != 10"
    return out


def select_all(preview: list[dict]) -> list[dict]:
    """All canonical + resolved entries (440/440 for the frozen v3.1 nomenclature)."""
    out = [p for p in preview if p["zh_status"] == "resolved"]
    assert len(out) == 440, f"select_all != 440: {len(out)}"
    return out


def _category_for(base: str) -> str:
    if "Amygdala" in base:
        return "amygdalar_nucleus"
    if "Hippocampus" in base:
        return "hippocampal_subfield"
    if "Thalamus" in base:
        return "thalamic_nucleus"
    if "Basal Forebrain" in base:
        return "subcortical_region"
    return "cortical_region"


def _connect(args):
    return psycopg.connect(
        host=args.host, port=args.port, user=args.user,
        password=args.password, dbname=args.db, autocommit=False,
    )


def _row(cur, sql, *params):
    cur.execute(sql, params)
    r = cur.fetchone()
    return r[0] if r else None


def _src_exists(cur):
    cur.execute("SELECT source_pk, source_id FROM sources WHERE name_en=%s AND version=%s",
                (SOURCE_NAME_EN, SOURCE_VERSION))
    r = cur.fetchone()
    return (r[0], r[1]) if r else (None, None)


def _atlas_exists(cur):
    cur.execute(
        "SELECT e.entity_pk, e.entity_id FROM kg_entities e"
        " JOIN atlases a ON a.entity_pk = e.entity_pk"
        " WHERE e.entity_type='atlas' AND e.name_en=%s AND a.atlas_version=%s",
        (SOURCE_NAME_EN, SOURCE_VERSION))
    r = cur.fetchone()
    return (r[0], r[1]) if r else (None, None)


def _external_exists(cur, atlas_pk, full_region_id):
    cur.execute(
        "SELECT e.entity_pk FROM kg_entities e JOIN external_regions x ON x.entity_pk=e.entity_pk"
        " WHERE e.entity_type='external_region' AND x.atlas_pk=%s AND x.source_region_id=%s",
        (atlas_pk, full_region_id))
    r = cur.fetchone()
    return r[0] if r else None


def _brain_exists(cur, src_pk, full_region_id):
    # G4 canonical identity = Julich source + official source_region_id (redundant copy in metadata)
    cur.execute(
        "SELECT ke.entity_pk FROM kg_entities ke JOIN brain_regions br ON br.entity_pk=ke.entity_pk"
        " WHERE ke.entity_type='brain_region' AND br.canonical_source_pk=%s"
        " AND ke.metadata_json->>'julich_source_region_id'=%s",
        (src_pk, full_region_id))
    r = cur.fetchone()
    return r[0] if r else None


def _mapping_exists(cur, xpk, bpk):
    cur.execute(
        "SELECT e.entity_pk FROM kg_entities e JOIN region_mappings rm ON rm.entity_pk=e.entity_pk"
        " WHERE e.entity_type='region_mapping' AND rm.external_region_pk=%s AND rm.brain_region_pk=%s",
        (xpk, bpk))
    r = cur.fetchone()
    return r[0] if r else None


def _name_collisions(cur, pilots):
    """Existing brain_regions (G1/G3) sharing a G4 normalized name — informational only."""
    cols = []
    for p in pilots:
        cur.execute(
            "SELECT ke.entity_id, ke.name_en, br.granularity_level FROM kg_entities ke"
            " JOIN brain_regions br ON br.entity_pk=ke.entity_pk"
            " WHERE ke.entity_type='brain_region' AND ke.name_en=%s"
            " AND (ke.metadata_json->>'julich_source_region_id' IS DISTINCT FROM %s)",
            (p["normalized_name_en"], p["source_region_id"]))
        for eid, en, gl in cur.fetchall():
            cols.append((p["biological_base_name"], p["source_region_name"], eid, en, gl))
    return cols


def _plan(args) -> int:
    preview = load_preview()
    target = select_all(preview) if getattr(args, "full", False) else select_pilots(preview)
    ids = [p["source_region_id"] for p in target]
    n = len(target)
    assert len(set(ids)) == n, "source_region_id not unique"
    lengths = [len(i) for i in ids]
    # full preflight stats (informational)
    print(f"selected = {n} (full={bool(getattr(args,'full',False))})")
    print(f"source_region_id unique = {len(set(ids))} | left={sum(1 for p in target if p['hemisphere']=='left')} "
          f"right={sum(1 for p in target if p['hemisphere']=='right')}")
    print(f"normalized_name_en unique = {len({p['normalized_name_en'] for p in target})} | "
          f"normalized_name_zh unique = {len({p['normalized_name_zh'] for p in target})}")
    print(f"name/zh non-null = {sum(1 for p in target if p['normalized_name_en'] and p['normalized_name_zh'])}")
    print(f"ZH resolved = {sum(1 for p in target if p['zh_status']=='resolved')} | GapMap = {sum(1 for p in target if 'GapMap' in p['source_region_name'])}")
    print(f"source_region_id len: min={min(lengths)} max={max(lengths)} >64={sum(1 for L in lengths if L>64)} "
          f">128={sum(1 for L in lengths if L>128)} >255={sum(1 for L in lengths if L>255)}")
    if max(lengths) > 255:
        print("ABORT: source_region_id exceeds VARCHAR(255).")
        return 3
    conn = _connect(args)
    try:
        cur = conn.cursor()
        src_pk, _ = _src_exists(cur)
        atlas_pk, _ = _atlas_exists(cur)
        existing_ext, existing_br, existing_map, conflicts = 0, 0, 0, 0
        for p in target:
            x = _external_exists(cur, atlas_pk, p["source_region_id"]) if atlas_pk else None
            b = _brain_exists(cur, src_pk, p["source_region_id"]) if src_pk else None
            if x is not None:
                existing_ext += 1
            else:
                cur.execute(
                    "SELECT count(*) FROM external_regions WHERE source_region_id=%s AND atlas_pk<>%s",
                    (p["source_region_id"], atlas_pk or 0))
                if cur.fetchone()[0] > 0:
                    conflicts += 1
            if b is not None:
                existing_br += 1
            if x is not None and b is not None and _mapping_exists(cur, x, b) is not None:
                existing_map += 1
        name_cols = _name_collisions(cur, target)
    finally:
        conn.close()
    print(f"existing Julich ExternalRegion = {existing_ext} | BrainRegion = {existing_br} | Mapping = {existing_map}")
    print(f"to add: ExternalRegion={n-existing_ext} BrainRegion={n-existing_br} Mapping={n-existing_map}")
    print(f"true Julich identity conflicts = {conflicts}")
    print(f"name-only collisions with G1/G3 = {len(name_cols)}")
    for c in name_cols[:10]:
        print(f"  name-collision: {c[0][:28]} ~ existing {c[2]} '{c[3]}' ({c[4]})")
    return 0 if conflicts == 0 else 3


def _apply(args) -> int:
    if args.allow_production and args.db != MAIN_DATABASE:
        print(f"ERROR: --allow-production but --db='{args.db}' != production. STOP.")
        return 2
    if args.db == MAIN_DATABASE and not args.allow_production:
        print(f"ERROR: APPLY to production requires --allow-production (not authorized this round).")
        return 2
    if args.db != MAIN_DATABASE and not is_allowed_test_database(args.db):
        print(f"ERROR: APPLY refused — '{args.db}' is not an allowed TEST database.")
        return 2

    preview = load_preview()
    target = select_all(preview) if getattr(args, "full", False) else select_pilots(preview)
    print(f"target rows = {len(target)} (full={bool(getattr(args,'full',False))})")
    conn = _connect(args)
    try:
        cur = conn.cursor()
        stats = {"source": 0, "atlas": 0, "external": 0, "brain": 0, "mapping": 0}

        # 1. Source (reuse)
        src_pk, src_id = _src_exists(cur)
        if src_pk is None:
            src_id = _row(cur, "SELECT infra.next_ngiq_id('source')")
            cur.execute(
                "INSERT INTO sources (source_id, name_en, name_zh, abbreviation, source_type,"
                " version, species_scope, url, provider, citation_text, last_checked_at, record_status)"
                " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW(),'active')",
                (src_id, SOURCE_NAME_EN, SOURCE_NAME_ZH, SOURCE_ABBR, SOURCE_TYPE,
                 SOURCE_VERSION, SOURCE_SPECIES, f"https://doi.org/{ATLAS_DOI}",
                 SOURCE_PROVIDER, SOURCE_CITATION))
            cur.execute("SELECT source_pk FROM sources WHERE source_id=%s", (src_id,))
            r = cur.fetchone()
            if r is not None:
                src_pk = r[0]
            stats["source"] = 1
        print(f"  source: {src_id} (new={stats['source']})")

        # 2. Atlas (reuse)
        atlas_pk, atlas_id = _atlas_exists(cur)
        if atlas_pk is None:
            atlas_id = _row(cur, "SELECT infra.next_ngiq_id('atlas')")
            meta = json.dumps({"parcellation_id": PARCELLATION_ID, "atlas_version": SOURCE_VERSION,
                               "atlas_doi": ATLAS_DOI}, ensure_ascii=False)
            cur.execute(
                "INSERT INTO kg_entities (entity_id, entity_type, name_en, name_zh,"
                " source_name_original, name_en_source, name_zh_source, record_status, metadata_json)"
                " VALUES (%s,'atlas',%s,%s,%s,'source','source','active',%s)",
                (atlas_id, SOURCE_NAME_EN, SOURCE_NAME_ZH, SOURCE_NAME_EN, meta))
            cur.execute("SELECT entity_pk FROM kg_entities WHERE entity_id=%s", (atlas_id,))
            r = cur.fetchone()
            if r is not None:
                atlas_pk = r[0]
            cur.execute(
                "INSERT INTO atlases (entity_pk, atlas_family, atlas_version, species,"
                " parcellation_method, region_count, citation_doi, license)"
                " VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                (atlas_pk, "Julich-Brain", SOURCE_VERSION, "Homo sapiens",
                 "cytoarchitectonic mapping", 454, ATLAS_DOI, "CC BY 4.0"))
            stats["atlas"] = 1
        print(f"  atlas: {atlas_id} (new={stats['atlas']})")

        # 3-5. Per target: ExternalRegion -> RegionMapping -> canonical BrainRegion
        for p in target:
            rid = p["source_region_id"]
            xpk = _external_exists(cur, atlas_pk, rid)
            if xpk is None:
                xid = _row(cur, "SELECT infra.next_ngiq_id('external_region')")
                xmeta = json.dumps({"julich_source_region_id": rid, "atlas_version": SOURCE_VERSION},
                                   ensure_ascii=False)
                cur.execute(
                    "INSERT INTO kg_entities (entity_id, entity_type, name_en, name_zh,"
                    " source_name_original, name_en_source, name_zh_source, record_status, metadata_json)"
                    " VALUES (%s,'external_region',%s,%s,%s,'source','normalized','active',%s)",
                    (xid, p["source_region_name"], p["normalized_name_zh"],
                     p["source_region_name"], xmeta))
                cur.execute("SELECT entity_pk FROM kg_entities WHERE entity_id=%s", (xid,))
                r = cur.fetchone()
                if r is not None:
                    xpk = r[0]
                cur.execute(
                    "INSERT INTO external_regions (entity_pk, atlas_pk, source_region_id,"
                    " hemisphere, granularity_level, granularity_basis)"
                    " VALUES (%s,%s,%s,%s,%s,%s)",
                    (xpk, atlas_pk, rid, p["hemisphere"], GRANULARITY,
                     "cytoarchitectonic"))
                stats["external"] += 1

            bpk = _brain_exists(cur, src_pk, rid)
            if bpk is None:
                bid = _row(cur, "SELECT infra.next_ngiq_id('brain_region')")
                bmeta = json.dumps({"julich_source_region_id": rid, "atlas_version": SOURCE_VERSION,
                                    "parcellation_id": PARCELLATION_ID}, ensure_ascii=False)
                cur.execute(
                    "INSERT INTO kg_entities (entity_id, entity_type, name_en, name_zh,"
                    " source_name_original, name_en_source, name_zh_source, record_status,"
                    " review_status, metadata_json)"
                    " VALUES (%s,'brain_region',%s,%s,%s,'source','normalized','proposed',"
                    " 'pending',%s)",
                    (bid, p["normalized_name_en"], p["normalized_name_zh"],
                     p["source_region_name"], bmeta))
                cur.execute("SELECT entity_pk FROM kg_entities WHERE entity_id=%s", (bid,))
                r = cur.fetchone()
                if r is not None:
                    bpk = r[0]
                cur.execute(
                    "INSERT INTO brain_regions (entity_pk, region_category, hemisphere,"
                    " granularity_level, species_taxon_id, canonical_source_pk)"
                    " VALUES (%s,%s,%s,%s,%s,%s)",
                    (bpk, _category_for(p["biological_base_name"]), p["hemisphere"],
                     GRANULARITY, SPECIES, src_pk))
                stats["brain"] += 1

            if _mapping_exists(cur, xpk, bpk) is None:
                mid = _row(cur, "SELECT infra.next_ngiq_id('region_mapping')")
                mmap_meta = json.dumps({"mapping_basis": "same Julich leaf identity",
                                        "mapping_source": MAPPING_SOURCE}, ensure_ascii=False)
                cur.execute(
                    "INSERT INTO kg_entities (entity_id, entity_type, name_en, name_zh,"
                    " source_name_original, name_en_source, name_zh_source, record_status,"
                    " review_status, metadata_json)"
                    " VALUES (%s,'region_mapping',%s,%s,%s,'normalized','source','active',"
                    " 'pending',%s)",
                    (mid,
                     f"Julich {p['source_region_name']} -> G4 canonical",
                     f"{p['source_region_name']} → G4 canonical", rid, mmap_meta))
                cur.execute("SELECT entity_pk FROM kg_entities WHERE entity_id=%s", (mid,))
                r = cur.fetchone()
                if r is not None:
                    mpk = r[0]
                cur.execute(
                    "INSERT INTO region_mappings (entity_pk, external_region_pk, brain_region_pk,"
                    " mapping_type, mapping_method, mapping_source, review_status)"
                    " VALUES (%s,%s,%s,%s,%s,%s,'pending')",
                    (mpk, xpk, bpk, MAPPING_TYPE, MAPPING_METHOD, MAPPING_SOURCE))
                stats["mapping"] += 1

        conn.commit()
        print(f"  applied: source={stats['source']} atlas={stats['atlas']} "
              f"external={stats['external']} brain={stats['brain']} mapping={stats['mapping']}")
    finally:
        conn.close()
    return 0


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="G4 Julich-Brain v3.1 Gate7B registry importer (E2E pilot).")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--plan", action="store_true", help="dry-run preflight, no writes")
    g.add_argument("--apply", action="store_true", help="apply to an allowed TEST database only")
    p.add_argument("--full", action="store_true",
                   help="process all 440 canonical+resolved entries instead of the 10-entry pilot")
    p.add_argument("--host", default=os.environ.get("PGHOST", "127.0.0.1"))
    p.add_argument("--port", default=os.environ.get("PGPORT", "5432"))
    p.add_argument("--user", default=os.environ.get("PGUSER", "postgres"))
    p.add_argument("--password", default=os.environ.get("PGPASSWORD", "postgres"))
    p.add_argument("--db", default=os.environ.get("PGDATABASE", DB_DEFAULT))
    p.add_argument("--allow-production", action="store_true",
                   help="EXPLICIT authorization to APPLY to MAIN database (NOT authorized this round).")
    return p.parse_args()


def main() -> int:
    args = _parse_args()
    assert_allowed_database(args.db)
    if args.plan:
        return 0 if _plan(args) == 0 else 3
    if args.apply:
        return _apply(args)
    return 1


if __name__ == "__main__":
    sys.exit(main())
