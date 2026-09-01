"""G4 Julich-Brain v3.1 — canonical BrainRegion promotion (PLAN / APPLY).

Narrow, Julich-G4-ONLY promotion of the 440 canonical G4 BrainRegions that have
completed human review + final semantic QA (julich_v3_1_g4_final_qa.json):

    record_status  proposed -> active
    review_status  pending  -> approved

This is a MINIMAL adapter of the approved G1 Macro96 promotion contract
(import_macro96_registry.py --promote): PLAN default, explicit --apply,
--allow-production production guard, single transaction, fail-closed, idempotent.

Selection is IDENTITY-scoped. A candidate must be a G4_MICROSTRUCTURAL_FINE
BrainRegion whose canonical_source_pk is the frozen Julich-Brain v3.1 source
(identity = exact source name+version, never name/status/granularity alone) AND
which still carries the exact Julich ExternalRegion mapping AND is proposed+pending.
It can never sweep in other G4 data, nor G1/G3.

Only kg_entities lifecycle columns are written: record_status, review_status,
updated_by_agent (reviewer marker), remark. No scientific content, no
RegionMapping / ExternalRegion / Atlas / Source, no aliases / xrefs / hierarchy /
spatial / aggregation.

Usage:
  python scripts/promote_julich_g4_registry.py --plan
  python scripts/promote_julich_g4_registry.py --apply                     # allowed TEST DB only
  python scripts/promote_julich_g4_registry.py --apply --allow-production --db=<MAIN_DATABASE>
"""

from __future__ import annotations

import argparse
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
QA_ARTIFACT = JULICH_DIR / "julich_v3_1_g4_final_qa.json"

DB_DEFAULT = "neurographiq_human_brain_v1_e2e"

# Frozen Julich v3.1 identity (must match import_julich_g4_registry.py).
SOURCE_NAME_EN = "Julich-Brain Cytoarchitectonic Atlas v3.1"
SOURCE_VERSION = "3.1.0"
ATLAS_FAMILY = "Julich-Brain"

GRANULARITY = "G4_MICROSTRUCTURAL_FINE"
SPECIES = "9606"
EXPECTED = 440

# Promotion reviewer marker — process-level, stable, NOT a fabricated human name.
PROMOTE_REVIEWER = "gate9_g4_julich_human_review"
# remark is TEXT (no length limit); shortened only if schema changes.
PROMOTE_NOTE = (
    "Julich-Brain v3.1 canonical G4 BrainRegion registry reviewed and approved "
    "after identity, bilingual nomenclature, semantic QA, and extraction-readiness "
    "validation."
)

# The ONLY write this promotion performs. Reused verbatim by the tests so the apply
# path and the test harness can never drift apart.
PROMOTE_SQL = (
    "UPDATE kg_entities SET record_status='active', review_status='approved',"
    " updated_by_agent=%s, remark=%s WHERE entity_pk = ANY(%s)"
)

# Scope base: canonical BrainRegions owned by the frozen Julich v3.1 source.
# Identity = canonical_source_pk -> Julich source (exact name+version), NOT a bare
# granularity/name/status filter.
_SCOPE_BASE = (
    "FROM kg_entities ke"
    " JOIN brain_regions br ON br.entity_pk = ke.entity_pk"
    " JOIN sources s ON s.source_pk = br.canonical_source_pk"
    " WHERE br.granularity_level = 'G4_MICROSTRUCTURAL_FINE'"
    "  AND s.name_en = %(src_en)s AND s.version = %(src_ver)s"
)


def load_qa_artifact() -> dict:
    """Load the frozen final-semantic-QA artifact (audit basis for this plan)."""
    with open(QA_ARTIFACT, encoding="utf-8") as f:
        return json.load(f)


def _qa_ok(qa: dict) -> bool:
    """The promotion requires the frozen QA to be clean and 440/220 complete."""
    return (
        qa.get("extraction_ready") is True
        and qa.get("semantic_rule_failures") == []
        and qa.get("g4_total") == EXPECTED
        and qa.get("pair_total") == EXPECTED // 2
    )


def _connect(args):
    return psycopg.connect(
        host=args.host, port=args.port, user=args.user,
        password=args.password, dbname=args.db, autocommit=False,
    )


def _julich_source_pk(cur) -> int | None:
    cur.execute("SELECT source_pk FROM sources WHERE name_en=%s AND version=%s",
                (SOURCE_NAME_EN, SOURCE_VERSION))
    r = cur.fetchone()
    return r[0] if r else None


def _eligible(cur) -> list[int]:
    """Julich G4 canonical BrainRegions still proposed+pending (the promotion scope)."""
    cur.execute("SELECT ke.entity_pk " + _SCOPE_BASE +
                " AND ke.record_status='proposed' AND ke.review_status='pending'",
                {"src_en": SOURCE_NAME_EN, "src_ver": SOURCE_VERSION})
    return [r[0] for r in cur.fetchall()]


def _already(cur) -> int:
    """Julich G4 canonical BrainRegions already active+approved (idempotency)."""
    cur.execute("SELECT count(*) " + _SCOPE_BASE +
                " AND ke.record_status='active' AND ke.review_status='approved'",
                {"src_en": SOURCE_NAME_EN, "src_ver": SOURCE_VERSION})
    return cur.fetchone()[0]


def _not_eligible(cur) -> int:
    """Julich G4 canonical BrainRegions in any OTHER lifecycle state (e.g. deprecated)."""
    cur.execute("SELECT count(*) " + _SCOPE_BASE +
                " AND NOT (ke.record_status='proposed' AND ke.review_status='pending')"
                " AND NOT (ke.record_status='active' AND ke.review_status='approved')",
                {"src_en": SOURCE_NAME_EN, "src_ver": SOURCE_VERSION})
    return cur.fetchone()[0]


def _g4_foreign(cur) -> int:
    """G4 BrainRegions NOT owned by the frozen Julich source — a conflict that must be 0."""
    cur.execute(
        "SELECT count(*) FROM brain_regions br JOIN sources s ON s.source_pk=br.canonical_source_pk"
        " WHERE br.granularity_level='G4_MICROSTRUCTURAL_FINE'"
        " AND NOT (s.name_en=%s AND s.version=%s)",
        (SOURCE_NAME_EN, SOURCE_VERSION))
    return cur.fetchone()[0]


def _violations(cur, ids: list[int]) -> int:
    """Fail-closed: any eligible row violating a promotion precondition (see gate §七)."""
    if not ids:
        return 0
    cur.execute(
        "SELECT count(*) FROM kg_entities ke"
        " JOIN brain_regions br ON br.entity_pk = ke.entity_pk"
        " JOIN sources s ON s.source_pk = br.canonical_source_pk"
        " WHERE ke.entity_pk = ANY(%s) AND ("
        "  br.species_taxon_id <> %s"
        "  OR br.hemisphere NOT IN ('left','right')"
        "  OR ke.name_en IS NULL OR ke.name_en = ''"
        "  OR ke.name_zh IS NULL OR ke.name_zh = ''"
        "  OR ke.name_en_source IS NULL OR ke.name_zh_source IS NULL"
        "  OR ke.name_en_source = 'unknown' OR ke.name_zh_source = 'unknown'"
        "  OR COALESCE(ke.metadata_json->>'julich_source_region_id','') = ''"
        "  OR ke.name_en ~ 'GapMap' OR ke.source_name_original ~ 'GAPMAP'"
        "  OR NOT EXISTS ("
        "    SELECT 1 FROM region_mappings rm"
        "    JOIN external_regions x ON x.entity_pk = rm.external_region_pk"
        "    JOIN atlases a ON a.entity_pk = x.atlas_pk"
        "    WHERE rm.brain_region_pk = ke.entity_pk AND rm.mapping_type='exact'"
        "      AND a.atlas_family = %s)"
        ")",
        (ids, SPECIES, ATLAS_FAMILY))
    return cur.fetchone()[0]


def _hemi_split(cur, ids: list[int]) -> tuple[int, int]:
    if not ids:
        return 0, 0
    cur.execute("SELECT count(*) FROM brain_regions WHERE entity_pk = ANY(%s) AND hemisphere='left'",
                (ids,))
    left = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM brain_regions WHERE entity_pk = ANY(%s) AND hemisphere='right'",
                (ids,))
    right = cur.fetchone()[0]
    return left, right


def _granularity_lifecycle(cur, level: str, status: str, review: str) -> int:
    cur.execute(
        "SELECT count(*) FROM kg_entities ke JOIN brain_regions br ON br.entity_pk=ke.entity_pk"
        " WHERE br.granularity_level=%s AND ke.record_status=%s AND ke.review_status=%s",
        (level, status, review))
    return cur.fetchone()[0]


def _mapping_count(cur) -> int:
    cur.execute(
        "SELECT count(*) FROM region_mappings rm"
        " JOIN external_regions x ON x.entity_pk=rm.external_region_pk"
        " JOIN atlases a ON a.entity_pk=x.atlas_pk"
        " WHERE a.atlas_family=%s AND rm.mapping_type='exact'",
        (ATLAS_FAMILY,))
    return cur.fetchone()[0]


def _promote_plan(args) -> int:
    conn = _connect(args)
    try:
        cur = conn.cursor()
        src_pk = _julich_source_pk(cur)
        ids = _eligible(cur) if src_pk is not None else []
        already = _already(cur) if src_pk is not None else 0
        not_eligible = _not_eligible(cur) if src_pk is not None else 0
        foreign = _g4_foreign(cur)
        violations = _violations(cur, ids)
        left, right = _hemi_split(cur, ids)
        g1 = _granularity_lifecycle(cur, "G1_MACRO", "active", "approved")
        g3 = _granularity_lifecycle(cur, "G3_MESO_FINE", "active", "approved")
        mappings = _mapping_count(cur)
        qa = load_qa_artifact()
        qa_ok = _qa_ok(qa)

        projected_g4 = already + len(ids)
        projected_total = g1 + g3 + projected_g4

        print("G4 Julich-Brain v3.1 promotion PLAN (read-only, no writes)")
        print(f"  identity scope        : Julich-Brain v3.1 source + G4_MICROSTRUCTURAL_FINE")
        print(f"  eligible              : {len(ids)}  (proposed+pending)")
        print(f"  already_promoted      : {already}  (active+approved)")
        print(f"  not_eligible          : {not_eligible}")
        print(f"  conflict (foreign G4) : {foreign}")
        print(f"  fail-closed violations: {violations}")
        print(f"  hemisphere            : left={left} right={right}")
        print(f"  planned transitions   : proposed->active = {len(ids)} | pending->approved = {len(ids)}")
        print(f"  G1 active+approved    : {g1}  (planned update 0)")
        print(f"  G3 active+approved    : {g3}  (planned update 0)")
        print(f"  projected G4 active   : {projected_g4}")
        print(f"  projected canonical total: {projected_total}  (G1+G3+G4 brain_regions only)")
        print(f"  RegionMapping         : {mappings} exact Julich mappings (unchanged)")
        print(f"  QA artifact           : {'OK' if qa_ok else 'FAIL'} "
              f"(extraction_ready={qa.get('extraction_ready')}, "
              f"failures={qa.get('semantic_rule_failures')}, "
              f"g4_total={qa.get('g4_total')}, pair_total={qa.get('pair_total')})")

        status = _plan_status(len(ids), already, not_eligible, foreign, violations,
                              left, right, g1, g3, qa_ok)
        if status == "ready":
            print("PLAN OK — READY_FOR_G4_PROMOTION_APPLY")
        elif status == "done":
            print("PLAN OK — idempotent: all 440 Julich G4 brain_regions already "
                  "active/approved (0 planned updates)")
        else:
            print("PLAN FAIL CLOSED — no promotion may run until every line above is clean.")
        return 0 if status in ("ready", "done") else 3
    finally:
        conn.close()


def _plan_status(eligible, already, not_eligible, foreign, violations,
                 left, right, g1, g3, qa_ok) -> str:
    """PLAN verdict: 'ready' (440 eligible), 'done' (idempotent: 440 already active),
    or 'fail'. A fully-promoted registry is a clean OK, never FAIL CLOSED."""
    core_clean = (not_eligible == 0 and foreign == 0 and violations == 0
                  and qa_ok and g1 == 84 and g3 == 246)
    if not core_clean:
        return "fail"
    if eligible == EXPECTED and already == 0 and left == EXPECTED // 2 and right == EXPECTED // 2:
        return "ready"
    if eligible == 0 and already == EXPECTED and left == 0 and right == 0:
        return "done"
    return "fail"


def _idempotent_noop(ids, already, not_eligible, foreign, violations, qa_ok) -> bool:
    """True when every Julich G4 BrainRegion is already active+approved (0 eligible).

    This is the idempotent second-APPLY case: a re-run must be a 0-row no-op that
    never re-writes remark / updated_by_agent. Partial state (eligible=0 but
    already != 440) is NOT a no-op — it stays fail-closed.
    """
    return (len(ids) == 0
            and already == EXPECTED
            and not_eligible == 0
            and foreign == 0
            and violations == 0
            and qa_ok)


def _promote(args) -> int:
    # Production guard (identical to G1 Macro96 contract).
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
        src_pk = _julich_source_pk(cur)
        ids = _eligible(cur) if src_pk is not None else []
        already = _already(cur) if src_pk is not None else 0
        not_eligible = _not_eligible(cur) if src_pk is not None else 0
        foreign = _g4_foreign(cur)
        violations = _violations(cur, ids)
        qa_ok = _qa_ok(load_qa_artifact())

        # Idempotent no-op: a second APPLY must change nothing (0 rows, no re-write).
        if _idempotent_noop(ids, already, not_eligible, foreign, violations, qa_ok):
            print(f"idempotent no-op: all {EXPECTED} Julich G4 brain_regions already "
                  f"active/approved. 0 rows updated.")
            return 0

        if len(ids) != EXPECTED:
            conn.rollback()
            print(f"ABORT: eligible={len(ids)} != {EXPECTED}. No promotion performed.")
            return 3
        if already != 0 or not_eligible != 0 or foreign != 0 or violations != 0 or not qa_ok:
            conn.rollback()
            print(f"ABORT: fail-closed guard hit (already={already} not_eligible={not_eligible} "
                  f"conflict={foreign} violations={violations} qa_ok={qa_ok}). No promotion performed.")
            return 3

        cur.execute(PROMOTE_SQL, (PROMOTE_REVIEWER, PROMOTE_NOTE, ids))
        if cur.rowcount != EXPECTED:
            conn.rollback()
            print(f"ABORT: rowcount={cur.rowcount} != {EXPECTED}. Rolled back.")
            return 3
        conn.commit()
        print(f"promoted: {cur.rowcount} G4 Julich brain_regions -> active/approved "
              f"(reviewer={PROMOTE_REVIEWER})")
    finally:
        conn.close()
    return 0


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="G4 Julich-Brain v3.1 canonical BrainRegion promotion (PLAN/APPLY).")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--plan", action="store_true",
                   help="dry-run promotion plan (read-only, safe on production)")
    g.add_argument("--apply", action="store_true",
                   help="apply promotion (TEST DB; production requires --allow-production)")
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
        return _promote_plan(args)
    if args.apply:
        return _promote(args)
    return 1


if __name__ == "__main__":
    sys.exit(main())
