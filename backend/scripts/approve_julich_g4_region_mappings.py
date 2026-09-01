"""G4 Julich-Brain v3.1 — 440 direct exact RegionMapping review approval (PLAN / APPLY).

Narrow, Julich-G4-ONLY approval of the 440 direct exact RegionMappings:

    ExternalRegion (Julich v3.1 leaf) -> canonical G4 BrainRegion

that have completed identity + 1:1 cardinality validation:

    review_status  pending -> approved     (kg_entities AND region_mappings subtype)
    record_status  active  -> active       (unchanged)

This mirrors the approved G4 BrainRegion promotion contract (promote_julich_g4_registry.py):
PLAN default, explicit --apply, --allow-production production guard, single transaction,
fail-closed, idempotent.

Approval is provenance- and identity-locked (NOT a name/type-only filter). A candidate
mapping must have:
  * atlas provenance  = Julich-Brain v3.1 (atlases.atlas_family + atlas_version)
  * target            = G4_MICROSTRUCTURAL_FINE canonical BrainRegion whose
                        canonical_source_pk is the frozen Julich v3.1 source
  * mapping_type      = exact, mapping_source = julich_direct
  * external source_region_id == the canonical BrainRegion's official
    julich_source_region_id (identity authority) — 440/440 exact, else FAIL CLOSED
  * strict 1:1:1 cardinality (1 ExternalRegion : 1 RegionMapping : 1 BrainRegion)

Only review lifecycle metadata is written:
  kg_entities.review_status, region_mappings.review_status,
  kg_entities.updated_by_agent (reviewer marker), kg_entities.remark.
No BrainRegion / mapping scientific content, no new/deleted mappings, no aggregation/spatial.

Usage:
  python scripts/approve_julich_g4_region_mappings.py --plan
  python scripts/approve_julich_g4_region_mappings.py --apply                     # TEST DB only
  python scripts/approve_julich_g4_region_mappings.py --apply --allow-production --db=<MAIN_DATABASE>
"""

from __future__ import annotations

import argparse
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

DB_DEFAULT = "neurographiq_human_brain_v1_e2e"

# Frozen Julich v3.1 identity (must match import_julich_g4_registry.py).
SOURCE_NAME_EN = "Julich-Brain Cytoarchitectonic Atlas v3.1"
SOURCE_VERSION = "3.1.0"
ATLAS_FAMILY = "Julich-Brain"
MAPPING_SOURCE = "julich_direct"
MAPPING_TYPE = "exact"
GRANULARITY = "G4_MICROSTRUCTURAL_FINE"
EXPECTED = 440

# Review metadata (frozen, not a fabricated human name).
REVIEWER = "gate9_g4_julich_mapping_review"
NOTE = (
    "Julich-Brain v3.1 direct ExternalRegion-to-G4 identity mapping reviewed and "
    "approved after exact source-identity and 1:1 cardinality validation."
)

# The ONLY writes this approval performs (reused verbatim by tests).
KG_APPROVE_SQL = (
    "UPDATE kg_entities SET review_status='approved', updated_by_agent=%s, remark=%s"
    " WHERE entity_pk = ANY(%s)"
)
RM_APPROVE_SQL = (
    "UPDATE region_mappings SET review_status='approved' WHERE entity_pk = ANY(%s)"
)

# Provenance-locked scope: Julich v3.1 atlas -> external -> region_mapping ->
# G4 canonical BrainRegion -> Julich v3.1 source.
_SCOPE = (
    "FROM region_mappings rm"
    " JOIN external_regions x ON x.entity_pk = rm.external_region_pk"
    " JOIN atlases a ON a.entity_pk = x.atlas_pk"
    " JOIN brain_regions br ON br.entity_pk = rm.brain_region_pk"
    " JOIN sources s ON s.source_pk = br.canonical_source_pk"
    " JOIN kg_entities km ON km.entity_pk = rm.entity_pk"
    " WHERE a.atlas_family = 'Julich-Brain' AND a.atlas_version = '3.1.0'"
    "  AND rm.mapping_type = 'exact' AND rm.mapping_source = 'julich_direct'"
    "  AND br.granularity_level = 'G4_MICROSTRUCTURAL_FINE'"
    "  AND s.name_en = %(src_en)s AND s.version = %(src_ver)s"
)


def _connect(args):
    return psycopg.connect(
        host=args.host, port=args.port, user=args.user,
        password=args.password, dbname=args.db, autocommit=False,
    )


def _scope_params():
    return {"src_en": SOURCE_NAME_EN, "src_ver": SOURCE_VERSION}


def _eligible(cur) -> list[int]:
    """Julich G4 direct exact mappings still pending (kg + subtype)."""
    cur.execute("SELECT rm.entity_pk " + _SCOPE +
                " AND km.record_status='active' AND km.review_status='pending'"
                " AND rm.review_status='pending'", _scope_params())
    return [r[0] for r in cur.fetchall()]


def _already(cur) -> int:
    """Julich G4 direct exact mappings already approved (kg + subtype)."""
    cur.execute("SELECT count(*) " + _SCOPE +
                " AND km.record_status='active' AND km.review_status='approved'"
                " AND rm.review_status='approved'", _scope_params())
    return cur.fetchone()[0]


def _conflict(cur) -> int:
    """Julich G4 direct exact mappings in any OTHER lifecycle state."""
    cur.execute("SELECT count(*) " + _SCOPE +
                " AND NOT (km.record_status='active' AND km.review_status='pending'"
                "          AND rm.review_status='pending')"
                " AND NOT (km.record_status='active' AND km.review_status='approved'"
                "          AND rm.review_status='approved')", _scope_params())
    return cur.fetchone()[0]


def _foreign_exact(cur) -> int:
    """exact mappings NOT owned by the frozen Julich v3.1 scope (must be 0, informational)."""
    cur.execute(
        "SELECT count(*) FROM region_mappings rm"
        " JOIN external_regions x ON x.entity_pk = rm.external_region_pk"
        " JOIN atlases a ON a.entity_pk = x.atlas_pk"
        " WHERE a.atlas_family='Julich-Brain' AND rm.mapping_type='exact'"
        " AND NOT (a.atlas_version='3.1.0' AND rm.mapping_source='julich_direct')")
    return cur.fetchone()[0]


def _identity_mismatch(cur) -> int:
    """Julich mappings whose external source_region_id != canonical official identity.

    The canonical identity authority is the BRAIN entity's metadata_json
    julich_source_region_id (set by the importer), compared against the external
    region's source_region_id column. Uses kb (brain entity), not km (mapping entity).
    """
    cur.execute(
        "SELECT count(*) FROM region_mappings rm"
        " JOIN external_regions x ON x.entity_pk = rm.external_region_pk"
        " JOIN atlases a ON a.entity_pk = x.atlas_pk"
        " JOIN brain_regions br ON br.entity_pk = rm.brain_region_pk"
        " JOIN sources s ON s.source_pk = br.canonical_source_pk"
        " JOIN kg_entities kb ON kb.entity_pk = rm.brain_region_pk"
        " WHERE a.atlas_family='Julich-Brain' AND a.atlas_version='3.1.0'"
        "  AND rm.mapping_type='exact' AND rm.mapping_source='julich_direct'"
        "  AND br.granularity_level='G4_MICROSTRUCTURAL_FINE'"
        "  AND s.name_en=%s AND s.version=%s"
        "  AND x.source_region_id IS DISTINCT FROM kb.metadata_json->>'julich_source_region_id'",
        (SOURCE_NAME_EN, SOURCE_VERSION))
    return cur.fetchone()[0]


def _cardinality_violations(cur) -> int:
    """external_region or brain_region mapped more than once (breaks 1:1:1)."""
    cur.execute(
        "SELECT count(*) FROM ("
        " SELECT x.entity_pk FROM region_mappings rm"
        " JOIN external_regions x ON x.entity_pk = rm.external_region_pk"
        " JOIN atlases a ON a.entity_pk = x.atlas_pk"
        " WHERE a.atlas_family='Julich-Brain' AND a.atlas_version='3.1.0'"
        " GROUP BY x.entity_pk HAVING count(*) > 1"
        " UNION"
        " SELECT rm.brain_region_pk FROM region_mappings rm"
        " JOIN external_regions x ON x.entity_pk = rm.external_region_pk"
        " JOIN atlases a ON a.entity_pk = x.atlas_pk"
        " WHERE a.atlas_family='Julich-Brain' AND a.atlas_version='3.1.0'"
        " GROUP BY rm.brain_region_pk HAVING count(*) > 1"
        ") t")
    return cur.fetchone()[0]


def _mapping_count(cur) -> int:
    cur.execute(
        "SELECT count(*) FROM region_mappings rm"
        " JOIN external_regions x ON x.entity_pk = rm.external_region_pk"
        " JOIN atlases a ON a.entity_pk = x.atlas_pk"
        " WHERE a.atlas_family='Julich-Brain' AND a.atlas_version='3.1.0'"
        " AND rm.mapping_type='exact' AND rm.mapping_source='julich_direct'")
    return cur.fetchone()[0]


def _approve_plan(args) -> int:
    conn = _connect(args)
    try:
        cur = conn.cursor()
        ids = _eligible(cur)
        already = _already(cur)
        conflict = _conflict(cur)
        foreign = _foreign_exact(cur)
        id_mismatch = _identity_mismatch(cur)
        card_viol = _cardinality_violations(cur)
        total = _mapping_count(cur)

        print("G4 Julich-Brain v3.1 RegionMapping approval PLAN (read-only, no writes)")
        print(f"  identity scope        : Julich-Brain v3.1 atlas + G4 canonical + julich_direct exact")
        print(f"  eligible              : {len(ids)}  (active + pending, kg & subtype)")
        print(f"  already_approved      : {already}")
        print(f"  conflict              : {conflict}")
        print(f"  foreign exact         : {foreign}")
        print(f"  identity mismatches   : {id_mismatch}  (external vs canonical official id)")
        print(f"  cardinality violations: {card_viol}  (must be 0 for 1:1:1)")
        print(f"  mapping total (scope) : {total}")
        print(f"  planned transitions   : pending->approved = {len(ids)} | record_status changes = 0")
        print(f"  created/deleted maps  : 0 / 0")

        core_clean = (total == EXPECTED and conflict == 0 and foreign == 0
                      and id_mismatch == 0 and card_viol == 0)
        if not core_clean:
            status = "fail"
        elif len(ids) == EXPECTED and already == 0:
            status = "ready"
        elif len(ids) == 0 and already == EXPECTED:
            status = "done"
        else:
            status = "fail"

        if status == "ready":
            print("PLAN OK — READY_FOR_G4_MAPPING_APPROVAL")
        elif status == "done":
            print("PLAN OK — idempotent: all 440 Julich G4 mappings already approved "
                  "(0 planned updates)")
        else:
            print("PLAN FAIL CLOSED — no mapping approval may run until every line is clean.")
        return 0 if status in ("ready", "done") else 3
    finally:
        conn.close()


def _already_fully_approved(ids, already, conflict, foreign, id_mismatch, card_viol) -> bool:
    return (len(ids) == 0 and already == EXPECTED and conflict == 0
            and foreign == 0 and id_mismatch == 0 and card_viol == 0)


def _approve(args) -> int:
    if args.db == MAIN_DATABASE and not args.allow_production:
        print(f"ERROR: APPROVE to production '{MAIN_DATABASE}' requires the explicit "
              f"--allow-production flag. Refusing.")
        return 2
    if args.allow_production and args.db != MAIN_DATABASE:
        print(f"ERROR: --allow-production set but --db='{args.db}' != production "
              f"'{MAIN_DATABASE}'. STOP.")
        return 2
    if args.db != MAIN_DATABASE and not is_allowed_test_database(args.db):
        print(f"ERROR: APPROVE refused — '{args.db}' is not an allowed database.")
        return 2

    conn = _connect(args)
    try:
        cur = conn.cursor()
        ids = _eligible(cur)
        already = _already(cur)
        conflict = _conflict(cur)
        foreign = _foreign_exact(cur)
        id_mismatch = _identity_mismatch(cur)
        card_viol = _cardinality_violations(cur)

        # Idempotent no-op: a second APPLY must change nothing (0 rows, no re-write).
        if _already_fully_approved(ids, already, conflict, foreign, id_mismatch, card_viol):
            print(f"idempotent no-op: all {EXPECTED} Julich G4 mappings already approved. "
                  f"0 rows updated.")
            return 0

        if len(ids) != EXPECTED:
            conn.rollback()
            print(f"ABORT: eligible={len(ids)} != {EXPECTED}. No approval performed.")
            return 3
        if already != 0 or conflict != 0 or foreign != 0 or id_mismatch != 0 or card_viol != 0:
            conn.rollback()
            print(f"ABORT: fail-closed guard hit (already={already} conflict={conflict} "
                  f"foreign={foreign} id_mismatch={id_mismatch} card_viol={card_viol}). "
                  f"No approval performed.")
            return 3

        cur.execute(KG_APPROVE_SQL, (REVIEWER, NOTE, ids))
        kg_rows = cur.rowcount
        cur.execute(RM_APPROVE_SQL, (ids,))
        rm_rows = cur.rowcount
        if kg_rows != EXPECTED or rm_rows != EXPECTED:
            conn.rollback()
            print(f"ABORT: rowcount kg={kg_rows} rm={rm_rows} != {EXPECTED}. Rolled back.")
            return 3
        conn.commit()
        print(f"approved: {kg_rows} mapping kg_entities + {rm_rows} region_mappings"
              f" -> review_status=approved (reviewer={REVIEWER})")
    finally:
        conn.close()
    return 0


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="G4 Julich-Brain v3.1 direct exact RegionMapping approval (PLAN/APPLY).")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--plan", action="store_true",
                   help="dry-run approval plan (read-only, safe on production)")
    g.add_argument("--apply", action="store_true",
                   help="apply approval (TEST DB; production requires --allow-production)")
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
        return _approve_plan(args)
    if args.apply:
        return _approve(args)
    return 1


if __name__ == "__main__":
    sys.exit(main())
