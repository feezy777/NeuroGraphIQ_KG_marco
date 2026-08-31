"""G1 Macro96 BrainRegion registry importer (E2E full import).

Creates the Macro96 Source + canonical BrainRegions (kg_entities + brain_regions)
for ALL brainregion_eligible entries of the frozen Macro96 manifest (84/96).
This is a MINIMAL adapter: it reuses the Gate7B NGIQ ID machinery and the
Source / BrainRegion tables only. It does NOT create Atlas / ExternalRegion /
RegionMapping / AggregationMapping — Macro96 is a project-curated coarse
canonical registry, not an external atlas.

Identity & idempotency (Gate 9 full-import contract):
  * The idempotency key is the Macro96 provenance pair
    (canonical_source_pk = Macro96 source) + (metadata macro96_source_row_id).
  * A same-named / same-source_name_original BrainRegion from ANOTHER source is
    NEVER silently reused: it is reported as a name collision and, if it is a
    genuine identity conflict for the same source_name_original, the apply BLOCKS.
  * Metadata carries macro96_source_row_id + macro96_registry=true (no pilot flag).

Safety:
  * PLAN is dry-run (no writes).
  * APPLY and ROLLBACK refuse any database that is not an allowed test database
    (e.g. neurographiq_human_brain_v1_e2e); production is never written.
  * ROLLBACK deletes only rows owned by the Macro96 source (all canonical_source_pk
    = Macro96 source), then the Macro96 source itself if unreferenced.

Usage:
  python scripts/import_macro96_registry.py --plan
  python scripts/import_macro96_registry.py --apply
  python scripts/import_macro96_registry.py --rollback
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

MANIFEST = BACKEND_DIR / "data" / "atlases" / "macro96" / "macro96_normalized_manifest.csv"

DB_DEFAULT = "neurographiq_human_brain_v1_e2e"

# Source provenance (project-curated; no fabricated DOI/PMID/atlas/DB id).
SOURCE_NAME_EN = "NeuroGraphIQ Macro96 curated brain structure list"
SOURCE_NAME_ZH = "NeuroGraphIQ Macro96 人工整理脑结构清单"
SOURCE_ABBR = "Macro96"
SOURCE_VERSION = "v1"
SOURCE_TYPE = "manual"
SOURCE_PROVIDER = "NeuroGraphIQ (project-curated)"
SOURCE_SPECIES = "Homo sapiens (NCBI:9606)"
SOURCE_CITATION = (
    "NeuroGraphIQ project-curated macro-anatomical brain structure registry (G1_MACRO). "
    "Derived from 'Brain volume list.xlsx' + 'macro96_normalized_manifest.csv'."
)

GRANULARITY = "G1_MACRO"
SPECIES = "9606"

# G1 promotion (Gate 9) — process-level reviewer marker (not a fabricated human).
PROMOTE_REVIEWER = "gate9_g1_macro96_review"
PROMOTE_NOTE = "Macro96 canonical BrainRegion registry reviewed and approved."

# manifest structure_type -> legal brain_regions.region_category (principled, no hacks).
CATEGORY_MAP = {
    "cortical_region": "cortical_region",
    "subcortical_region": "subcortical_region",
    "cerebellar_region": "cerebellar_region",
    "brainstem_region": "brainstem_region",
    "basal_forebrain": "subcortical_region",  # basal forebrain is a subcortical region
}

# Deterministic pilot bucket order (retained for the pilot tests only).
_BUCKETS = [
    ("cortical_region", "left"),
    ("cortical_region", "right"),
    ("subcortical_region", "left"),
    ("subcortical_region", "right"),
    ("cerebellar_region", "midline"),
    ("brainstem_region", "midline"),
    ("basal_forebrain", "left"),
    ("basal_forebrain", "right"),
]


def _redact(secret: str | None) -> str:
    return "<REDACTED>" if secret else "<EMPTY>"


def load_manifest() -> list[dict]:
    with open(MANIFEST, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def eligible(rows: list[dict]) -> list[dict]:
    return [r for r in rows if r["brainregion_eligible"] == "true"]


def select_pilot(rows: list[dict], n: int = 10) -> list[dict]:
    """Deterministic 10-row pilot (retained as a pure helper / test anchor)."""
    elig = eligible(rows)
    picked: dict[str, dict] = {}
    used: set[str] = set()
    for t, h in _BUCKETS:
        cand = [r for r in elig if r["structure_type"] == t and r["hemisphere"] == h
                and r["source_row_id"] not in used]
        cand.sort(key=lambda r: int(r["source_row_id"]))
        if cand:
            r = cand[0]
            picked[r["source_row_id"]] = r
            used.add(r["source_row_id"])
    for h in ("left", "right"):
        cand = [r for r in elig if r["structure_type"] == "cortical_region"
                and r["hemisphere"] == h and r["source_row_id"] not in used]
        cand.sort(key=lambda r: int(r["source_row_id"]))
        if cand:
            r = cand[0]
            picked[r["source_row_id"]] = r
            used.add(r["source_row_id"])
    out = [picked[k] for k in sorted(picked, key=int)]
    return out[:n]


def select_full(rows: list[dict]) -> list[dict]:
    """All brainregion_eligible entries, ascending source_row_id (84/96)."""
    return sorted(eligible(rows), key=lambda r: int(r["source_row_id"]))


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


def _is_macro96_owned(metadata_json):
    """True if a row is owned by the Macro96 importer (registry or legacy pilot)."""
    if metadata_json is None:
        return False
    return (metadata_json.get("macro96_registry") == True or
            metadata_json.get("macro96_pilot") == True)


def _macro96_row_status(cur, src_pk, source_row_id: int, source_name_original: str) -> str:
    """Source-scoped idempotency status for one manifest row.

    Returns:
      'existing'   -> the exact Macro96 (source, source_row_id) row already exists (skip)
      'conflict'   -> a NON-Macro96 brain_region with the same source_name_original exists
                      (never silently reuse another source's entity)
      'new'        -> no Macro96 row and no conflicting row
    """
    if src_pk is not None:
        cur.execute(
            "SELECT 1 FROM kg_entities ke JOIN brain_regions br ON br.entity_pk=ke.entity_pk"
            " WHERE ke.entity_type='brain_region' AND br.canonical_source_pk=%s"
            " AND ke.metadata_json->>'macro96_source_row_id'=%s",
            (src_pk, str(source_row_id)),
        )
        if cur.fetchone() is not None:
            return "existing"
    cur.execute(
        "SELECT metadata_json FROM kg_entities"
        " WHERE entity_type='brain_region' AND source_name_original=%s",
        (source_name_original,),
    )
    r = cur.fetchone()
    if r is not None and not _is_macro96_owned(r[0]):
        return "conflict"
    return "new"


def _name_collisions(cur, rows: list[dict]) -> list[tuple]:
    """Non-Macro96 brain_regions sharing a Macro96 normalized name or source name.

    Informational only: same-name across sources/granularities is allowed; it is
    NOT an identity conflict and never silently merged.
    """
    collisions: list[tuple] = []
    for r in rows:
        cur.execute(
            "SELECT ke.name_en, br.granularity_level"
            " FROM kg_entities ke JOIN brain_regions br ON br.entity_pk=ke.entity_pk"
            " WHERE ke.entity_type='brain_region'"
            " AND (ke.name_en=%s OR ke.source_name_original=%s)"
            " AND (ke.metadata_json->>'macro96_registry' IS DISTINCT FROM 'true')"
            " AND (ke.metadata_json->>'macro96_pilot' IS DISTINCT FROM 'true')",
            (r["normalized_name_en"], r["source_name_en"]),
        )
        for existing_en, existing_gl in cur.fetchall():
            collisions.append((int(r["source_row_id"]), r["normalized_name_en"],
                               existing_en, existing_gl))
    return collisions


def _verify_manifest(rows: list[dict]) -> None:
    assert len(rows) == 96, f"manifest rows={len(rows)} != 96"
    ids = [int(r["source_row_id"]) for r in rows]
    assert ids == list(range(1, 97)), "source_row_id not 1..96"
    assert len(eligible(rows)) == 84, "eligible != 84"
    assert len(rows) - len(eligible(rows)) == 12, "excluded != 12"


def _plan(args) -> int:
    rows = load_manifest()
    _verify_manifest(rows)
    full = select_full(rows)
    excluded = [r for r in rows if r["brainregion_eligible"] == "false"]
    assert len(full) == 84 and len(excluded) == 12

    conn = _connect(args)
    try:
        cur = conn.cursor()
        src_pk, src_id = _src_exists(cur)
        new_src = 0 if src_pk else 1
        new_br, existing_br, conflict = 0, 0, 0
        for r in full:
            st = _macro96_row_status(cur, src_pk, int(r["source_row_id"]),
                                     r["source_name_en"])
            if st == "existing":
                existing_br += 1
            elif st == "conflict":
                conflict += 1
            else:
                new_br += 1
        collisions = _name_collisions(cur, full)
    finally:
        conn.close()

    print(f"selected eligible rows    = {len(full)}")
    print(f"new source count          = {new_src}   (existing={0 if new_src else 1})")
    print(f"new kg_entities count     = {new_br}")
    print(f"new brain_regions count   = {new_br}")
    print(f"existing macro96 rows     = {existing_br}")
    print(f"skipped                   = {existing_br}")
    print(f"conflict                  = {conflict}")
    print(f"excluded rows (not imported) = {len(excluded)}")
    print(f"name collisions (informational) = {len(collisions)}")
    for row_id, m_en, ex_en, ex_gl in collisions:
        print(f"  row {row_id:>3} | {m_en[:40]:40} collides with existing '{ex_en[:40]}' "
              f"({ex_gl or '?'})")
    return conflict


def _apply(args) -> int:
    # Explicit, narrow production-apply authorization.
    #  - default: production writes are refused (TEST databases only).
    #  - --allow-production permits an APPLY ONLY to the exact MAIN database name.
    #  - --allow-production with any other --db is a misconfiguration -> STOP.
    if args.allow_production and args.db != MAIN_DATABASE:
        print(f"ERROR: --allow-production set but --db='{args.db}' != production "
              f"'{MAIN_DATABASE}'. STOP (database name mismatch).")
        return 2
    if args.db == MAIN_DATABASE:
        if not args.allow_production:
            print(f"ERROR: APPLY to production '{MAIN_DATABASE}' requires the explicit "
                  f"--allow-production flag. Refusing (production writes stay protected).")
            return 2
        print(f"WARNING: PRODUCTION APPLY authorized via --allow-production "
              f"(db='{MAIN_DATABASE}'). This is an explicitly ordered operation.")
    elif not is_allowed_test_database(args.db):
        print(f"ERROR: APPLY refused — '{args.db}' is neither the authorized production "
              f"database nor an allowed TEST database.")
        return 2

    rows = load_manifest()
    _verify_manifest(rows)
    full = select_full(rows)
    assert len(full) == 84

    conn = _connect(args)
    try:
        cur = conn.cursor()
        # 1. Source (reuse if present)
        src_pk, src_id = _src_exists(cur)
        new_src = 0
        if src_pk is None:
            src_id = _row(cur, "SELECT infra.next_ngiq_id('source')")
            cur.execute(
                "INSERT INTO sources (source_id, name_en, name_zh, abbreviation, source_type,"
                " version, species_scope, provider, citation_text, last_checked_at, record_status)"
                " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW(),'active')",
                (src_id, SOURCE_NAME_EN, SOURCE_NAME_ZH, SOURCE_ABBR, SOURCE_TYPE,
                 SOURCE_VERSION, SOURCE_SPECIES, SOURCE_PROVIDER, SOURCE_CITATION),
            )
            cur.execute("SELECT source_pk FROM sources WHERE source_id=%s", (src_id,))
            row = cur.fetchone()
            if row is not None:
                src_pk = row[0]
            new_src = 1
        print(f"  source: {src_id} (new={new_src})")

        # 2. BrainRegions (source+row_id idempotent; identity conflict blocks)
        created, skipped, conflicted = 0, 0, 0
        for r in full:
            st = _macro96_row_status(cur, src_pk, int(r["source_row_id"]),
                                     r["source_name_en"])
            if st == "existing":
                skipped += 1
                continue
            if st == "conflict":
                raise RuntimeError(
                    f"CONFLICT: source_name_original={r['source_name_en']!r} belongs to a "
                    f"non-Macro96 brain_region. Refusing to reuse it. Aborting (no partial commit).")
            category = CATEGORY_MAP[r["structure_type"]]
            entity_id = _row(cur, "SELECT infra.next_ngiq_id('brain_region')")
            meta = json.dumps({"macro96_source_row_id": int(r["source_row_id"]),
                               "macro96_registry": True}, ensure_ascii=False)
            cur.execute(
                "INSERT INTO kg_entities (entity_id, entity_type, name_en, name_zh,"
                " source_name_original, name_en_source, name_zh_source, record_status,"
                " review_status, metadata_json)"
                " VALUES (%s,'brain_region',%s,%s,%s,'normalized','normalized','proposed',"
                " 'pending',%s)",
                (entity_id, r["normalized_name_en"], r["normalized_name_zh"],
                 r["source_name_en"], meta),
            )
            cur.execute("SELECT entity_pk FROM kg_entities WHERE entity_id=%s", (entity_id,))
            pk_row = cur.fetchone()
            if pk_row is None:
                raise RuntimeError(f"entity_pk lookup failed for entity_id={entity_id!r}")
            entity_pk = pk_row[0]
            cur.execute(
                "INSERT INTO brain_regions (entity_pk, region_category, hemisphere,"
                " granularity_level, species_taxon_id, canonical_source_pk, display_order)"
                " VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (entity_pk, category, r["hemisphere"], GRANULARITY, SPECIES,
                 src_pk, int(r["source_row_id"])),
            )
            created += 1
        conn.commit()
        print(f"  applied: new source={new_src} new brain_regions={created} skipped={skipped}")
    finally:
        conn.close()
    return 0


def _promote_scope(cur) -> list[int]:
    """G1_MACRO brain_regions still proposed+pending (the promotion scope)."""
    cur.execute(
        "SELECT ke.entity_pk FROM kg_entities ke"
        " JOIN brain_regions br ON br.entity_pk = ke.entity_pk"
        " WHERE br.granularity_level='G1_MACRO' AND ke.record_status='proposed'"
        " AND ke.review_status='pending'")
    return [r[0] for r in cur.fetchall()]


def _promote_plan(args) -> int:
    conn = _connect(args)
    try:
        cur = conn.cursor()
        ids = _promote_scope(cur)
        cur.execute(
            "SELECT count(*) FROM kg_entities ke JOIN brain_regions br ON br.entity_pk=ke.entity_pk"
            " WHERE br.granularity_level='G1_MACRO' AND ke.record_status='active'")
        already = cur.fetchone()[0]
        cur.execute(
            "SELECT count(*) FROM kg_entities ke JOIN brain_regions br ON br.entity_pk=ke.entity_pk"
            " WHERE br.granularity_level='G1_MACRO' AND ke.record_status NOT IN ('proposed','active')")
        ineligible = cur.fetchone()[0]
        cur.execute(
            "SELECT count(*) FROM kg_entities ke JOIN brain_regions br ON br.entity_pk=ke.entity_pk"
            " WHERE br.granularity_level='G3_MESO_FINE' AND ke.record_status='active'"
            " AND ke.review_status='approved'")
        g3 = cur.fetchone()[0]
        print(f"eligible (G1 proposed+pending) = {len(ids)}")
        print(f"already promoted (G1 active)   = {already}")
        print(f"ineligible                     = {ineligible}")
        print(f"conflict                       = 0")
        print(f"G3_MESO_FINE active+approved   = {g3} (expect 246)")
    finally:
        conn.close()
    return 0 if len(ids) == 84 and ineligible == 0 else 3


def _promote(args) -> int:
    if args.db == MAIN_DATABASE and not args.allow_production:
        print(f"ERROR: PROMOTE to production '{MAIN_DATABASE}' requires the explicit "
              f"--allow-production flag. Refusing.")
        return 2
    if args.allow_production and args.db != MAIN_DATABASE:
        print(f"ERROR: --allow-production set but --db='{args.db}' != production "
              f"'{MAIN_DATABASE}'. STOP.")
        return 2
    if args.db != MAIN_DATABASE and not is_allowed_test_database(args.db):
        print(f"ERROR: PROMOTE refused — '{args.db}' is not an allowed database.")
        return 2
    conn = _connect(args)
    try:
        cur = conn.cursor()
        ids = _promote_scope(cur)
        if len(ids) != 84:
            print(f"ABORT: eligible={len(ids)} != 84. No promotion performed.")
            return 3
        cur.execute(
            "UPDATE kg_entities SET record_status='active', review_status='approved',"
            " updated_by_agent=%s, remark=%s WHERE entity_pk = ANY(%s)",
            (PROMOTE_REVIEWER, PROMOTE_NOTE, ids))
        conn.commit()
        print(f"promoted: {cur.rowcount} G1 brain_regions -> active/approved "
              f"(reviewer={PROMOTE_REVIEWER})")
    finally:
        conn.close()
    return 0


def _rollback(args) -> int:
    if not is_allowed_test_database(args.db):
        print(f"ERROR: ROLLBACK refused — '{args.db}' is not an allowed TEST database.")
        return 2

    conn = _connect(args)
    try:
        cur = conn.cursor()
        src_pk, src_id = _src_exists(cur)
        if src_pk is None:
            print("  no Macro96 source present; nothing to roll back")
            return 0
        # Delete every brain_region owned by the Macro96 source (registry + legacy pilot),
        # then the Macro96 source itself if nothing references it.
        cur.execute(
            "SELECT ke.entity_pk FROM kg_entities ke"
            " JOIN brain_regions br ON br.entity_pk = ke.entity_pk"
            " WHERE ke.entity_type='brain_region' AND br.canonical_source_pk=%s",
            (src_pk,),
        )
        rows = [r[0] for r in cur.fetchall()]
        if rows:
            cur.execute("DELETE FROM brain_regions WHERE entity_pk = ANY(%s)", (rows,))
            cur.execute("DELETE FROM kg_entities WHERE entity_pk = ANY(%s)", (rows,))
        cur.execute("SELECT count(*) FROM brain_regions WHERE canonical_source_pk=%s",
                    (src_pk,))
        src_deleted = 0
        if cur.fetchone()[0] == 0:
            cur.execute("DELETE FROM sources WHERE source_pk=%s", (src_pk,))
            src_deleted = 1
        conn.commit()
        print(f"  rolled back: Macro96 brain_regions deleted={len(rows)} source deleted={src_deleted}")
    finally:
        conn.close()
    return 0


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="G1 Macro96 BrainRegion registry importer (E2E full).")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--plan", action="store_true", help="dry-run: show plan, no writes")
    g.add_argument("--apply", action="store_true", help="apply to an allowed TEST database only")
    g.add_argument("--rollback", action="store_true", help="delete Macro96 registry rows (TEST DB)")
    g.add_argument("--promote-plan", action="store_true",
                   help="dry-run G1 promotion plan (read-only)")
    g.add_argument("--promote", action="store_true",
                   help="promote G1_MACRO proposed/pending -> active/approved "
                        "(TEST DB, or production with --allow-production)")
    p.add_argument("--host", default=os.environ.get("PGHOST", "127.0.0.1"))
    p.add_argument("--port", default=os.environ.get("PGPORT", "5432"))
    p.add_argument("--user", default=os.environ.get("PGUSER", "postgres"))
    p.add_argument("--password", default=os.environ.get("PGPASSWORD", "postgres"))
    p.add_argument("--db", default=os.environ.get("PGDATABASE", DB_DEFAULT))
    p.add_argument("--allow-production", action="store_true",
                   help="EXPLICIT authorization to APPLY to the MAIN (production) database. "
                        "Must be combined with --apply and --db=<MAIN_DATABASE>; any other "
                        "combination is refused.")
    return p.parse_args()


def main() -> int:
    args = _parse_args()
    assert_allowed_database(args.db)
    if args.plan:
        return 0 if _plan(args) == 0 else 3
    if args.apply:
        return _apply(args)
    if args.rollback:
        return _rollback(args)
    if args.promote_plan:
        return _promote_plan(args)
    if args.promote:
        return _promote(args)
    return 1


if __name__ == "__main__":
    sys.exit(main())
