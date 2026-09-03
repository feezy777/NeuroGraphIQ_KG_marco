"""Gate 8C — Brainnetome BrainRegion Registry controlled promotion (production DB).

Promotes the 246 BNA246 canonical BrainRegion candidates from proposed to active
(Accepted Canonical Registry), and approves their direct canonicalization
RegionMappings (pending -> approved).

Scope is defined by provenance (NOT name LIKE / NOT a blanket entity_type update):
    brain_region -> region_mappings(mapping_source='brainnetome_direct')
                  -> external_regions -> atlases('Human Brainnetome Atlas')

Lifecycle (CURRENT contract):
  * BrainRegion (kg_entities): record_status proposed -> active;
    review_status NULL -> approved (review_status vocab includes 'approved').
  * RegionMapping (kg_entities): record_status is ALREADY 'active' (set at import) —
    no proposed->active transition needed; only review_status pending -> approved.
  * reviewer = process-level marker 'gate8c_registry_review' (not a fabricated human name).

Usage:
    python scripts/promote_brainnetome_registry.py [--plan|--apply] [--db ...]
    Default is --plan (read-only).
"""

from __future__ import annotations

import argparse
import os
import sys

try:
    import psycopg
except ImportError:
    print("ERROR: psycopg (psycopg3) required")
    sys.exit(2)

DB_DEFAULT = "neurographiq_human_brain_v1"
ATLAS_NAME_EN = "Human Brainnetome Atlas"
MAPPING_SOURCE = "brainnetome_direct"
REVIEWER = "gate8c_registry_review"
EXPECTED = 246


def _redact(secret: str | None) -> str:
    return "<REDACTED>" if secret else "<EMPTY>"


def _scope(cur) -> list[int]:
    """Brainnetome BNA246 canonical BrainRegion entity_pk set (provenance-scoped)."""
    cur.execute(
        """
        SELECT DISTINCT br.entity_pk
        FROM brain_regions br
        JOIN region_mappings rm ON rm.brain_region_pk = br.entity_pk
        JOIN external_regions x ON x.entity_pk = rm.external_region_pk
        JOIN atlases a ON a.entity_pk = x.atlas_pk
        JOIN kg_entities ae ON ae.entity_pk = a.entity_pk
        WHERE rm.mapping_source = %s
          AND ae.entity_type = 'atlas'
          AND ae.name_en = %s
        ORDER BY br.entity_pk
        """,
        (MAPPING_SOURCE, ATLAS_NAME_EN),
    )
    return [r[0] for r in cur.fetchall()]


def _eligibility(cur, scope: list[int]) -> dict:
    """Return violation counts for the promotion eligibility checks."""
    v: dict = {}
    def n(sql, *p):
        cur.execute(sql, p)
        return cur.fetchone()[0]

    ids = tuple(scope)
    if not ids:
        v["scope_empty"] = 1
        return v
    plc = ",".join(["%s"] * len(ids))

    v["total_scope"] = len(ids)
    v["non_brain_region"] = n(f"SELECT count(*) FROM kg_entities WHERE entity_pk IN ({plc}) AND entity_type<>'brain_region'", *ids)
    v["duplicate_entity_id"] = n("SELECT count(*) FROM (SELECT entity_id FROM kg_entities WHERE entity_pk IN (" + plc + ") GROUP BY entity_id HAVING count(*)>1) x", *ids)
    v["missing_name_en"] = n(f"SELECT count(*) FROM kg_entities WHERE entity_pk IN ({plc}) AND (name_en IS NULL OR name_en='')", *ids)
    v["missing_name_zh"] = n(f"SELECT count(*) FROM kg_entities WHERE entity_pk IN ({plc}) AND (name_zh IS NULL OR name_zh='')", *ids)
    v["missing_source_name_original"] = n(f"SELECT count(*) FROM kg_entities WHERE entity_pk IN ({plc}) AND (source_name_original IS NULL OR source_name_original='')", *ids)
    v["name_source_not_normalized"] = n(f"SELECT count(*) FROM kg_entities WHERE entity_pk IN ({plc}) AND (name_en_source<>'normalized' OR name_zh_source<>'normalized')", *ids)
    v["dup_canonical_en"] = n("SELECT count(*) FROM (SELECT name_en FROM kg_entities WHERE entity_pk IN (" + plc + ") GROUP BY name_en HAVING count(*)>1) x", *ids)
    v["dup_canonical_zh"] = n("SELECT count(*) FROM (SELECT name_zh FROM kg_entities WHERE entity_pk IN (" + plc + ") GROUP BY name_zh HAVING count(*)>1) x", *ids)
    v["non_human"] = n(f"SELECT count(*) FROM brain_regions WHERE entity_pk IN ({plc}) AND (species_taxon_id IS NULL OR species_taxon_id<>'9606')", *ids)
    v["wrong_granularity"] = n(f"SELECT count(*) FROM brain_regions WHERE entity_pk IN ({plc}) AND granularity_level<>'G3_MESO_FINE'", *ids)
    v["hemisphere_mismatch"] = n(
        "SELECT count(*) FROM kg_entities e JOIN brain_regions b ON b.entity_pk=e.entity_pk"
        " WHERE e.entity_pk IN (" + plc + ") AND ("
        "(b.hemisphere='left' AND left(e.name_en,5)<>'Left ') OR (b.hemisphere='right' AND left(e.name_en,6)<>'Right '))", *ids)
    v["missing_alias"] = n(
        "SELECT count(*) FROM kg_entities e JOIN brain_regions b ON b.entity_pk=e.entity_pk"
        " LEFT JOIN entity_aliases a ON a.entity_pk=e.entity_pk AND a.alias_type='atlas_label'"
        " WHERE e.entity_pk IN (" + plc + ") AND a.alias_pk IS NULL", *ids)
    v["missing_xref"] = n(
        "SELECT count(*) FROM kg_entities e JOIN brain_regions b ON b.entity_pk=e.entity_pk"
        " LEFT JOIN entity_xrefs xr ON xr.entity_pk=e.entity_pk AND xr.source_database='Brainnetome'"
        " WHERE e.entity_pk IN (" + plc + ") AND xr.xref_pk IS NULL", *ids)
    v["missing_mapping"] = n(
        "SELECT count(*) FROM kg_entities e JOIN brain_regions b ON b.entity_pk=e.entity_pk"
        " LEFT JOIN region_mappings rm ON rm.brain_region_pk=b.entity_pk"
        " WHERE e.entity_pk IN (" + plc + ") AND rm.entity_pk IS NULL", *ids)
    v["mapping_not_exact"] = n(
        "SELECT count(*) FROM region_mappings WHERE brain_region_pk IN (" + plc + ") AND"
        " (mapping_type<>'exact' OR mapping_method<>'automatic' OR mapping_source<>'brainnetome_direct'"
        " OR name_similarity IS NOT NULL OR semantic_similarity IS NOT NULL"
        " OR spatial_overlap IS NOT NULL OR overall_confidence IS NOT NULL)", *ids)
    v["unexpected_status"] = n(f"SELECT count(*) FROM kg_entities WHERE entity_pk IN ({plc}) AND record_status NOT IN ('proposed','active')", *ids)
    v["already_active"] = n(f"SELECT count(*) FROM kg_entities WHERE entity_pk IN ({plc}) AND record_status='active'", *ids)
    v["mapping_already_approved"] = n(f"SELECT count(*) FROM region_mappings WHERE brain_region_pk IN ({plc}) AND review_status='approved'", *ids)
    return v


def _connect(args):
    return psycopg.connect(host=args.host, port=args.port, user=args.user,
                           password=args.password, dbname=args.db, autocommit=False)


def _plan(args) -> int:
    conn = _connect(args)
    try:
        cur = conn.cursor()
        scope = _scope(cur)
        v = _eligibility(cur, scope)
        print("=== Gate 8C Brainnetome Registry Promotion PLAN ===")
        print(f"  scope (provenance): {len(scope)} Brainnetome brain_regions")
        print(f"  eligible BrainRegion: {v.get('total_scope', 0)}")
        print(f"  ineligible (violations): {sum(v[k] for k in v if k != 'total_scope')}")
        for k in sorted(v):
            if k != "total_scope":
                print(f"    {k}: {v[k]}")
        print(f"  proposed -> active: {v['total_scope'] - v['already_active']}")
        print(f"  already active: {v['already_active']}")
        print(f"  mapping pending -> approved: 246 - {v['mapping_already_approved']}")
        print(f"  mapping entity lifecycle: already active (import-time); no transition needed")
        print(f"  reviewer: {REVIEWER}")
        core = [k for k in v if k not in ("total_scope", "already_active", "mapping_already_approved")]
        violations = sum(v[k] for k in core)
        if v["total_scope"] == EXPECTED and violations == 0:
            print("\nPROMOTION_READY")
            return 0
        print("\nPROMOTION_BLOCKED")
        return 1
    finally:
        conn.rollback()
        conn.close()


def _apply(args) -> int:
    conn = _connect(args)
    try:
        cur = conn.cursor()
        scope = _scope(cur)
        v = _eligibility(cur, scope)
        core = [k for k in v if k not in ("total_scope", "already_active", "mapping_already_approved")]
        violations = sum(v[k] for k in core)
        if v["total_scope"] != EXPECTED or violations != 0:
            print(f"PROMOTION_BLOCKED (scope={v['total_scope']}, violations={violations})")
            return 1

        ids = tuple(scope)
        plc = ",".join(["%s"] * len(ids))

        # 1. BrainRegion: proposed -> active; review_status NULL -> approved
        cur.execute(
            f"UPDATE kg_entities SET record_status='active', review_status='approved'"
            f" WHERE entity_pk IN ({plc}) AND record_status='proposed'",
            ids,
        )
        br_updated = cur.rowcount
        # 2. RegionMapping: pending -> approved + process reviewer
        cur.execute(
            f"UPDATE region_mappings SET review_status='approved', reviewer=%s, reviewed_at=NOW()"
            f" WHERE brain_region_pk IN ({plc}) AND review_status='pending'",
            (REVIEWER,) + ids,
        )
        rm_updated = cur.rowcount
        # 3. RegionMapping entity lifecycle: already active at import — no-op (verify)
        cur.execute(
            f"SELECT count(*) FROM kg_entities e JOIN region_mappings rm ON rm.entity_pk=e.entity_pk"
            f" WHERE rm.brain_region_pk IN ({plc}) AND e.record_status<>'active'",
            ids,
        )
        rm_not_active = cur.fetchone()[0]

        conn.commit()
        print("=== Gate 8C Brainnetome Registry Promotion APPLY RESULT ===")
        print(f"  BrainRegion proposed->active: {br_updated}")
        print(f"  BrainRegion review_status -> approved: {br_updated}")
        print(f"  RegionMapping pending->approved: {rm_updated}")
        print(f"  RegionMapping lifecycle not-active (must be 0): {rm_not_active}")
        print("OK — committed.")
        return 0
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Gate 8C Brainnetome registry promotion")
    p.add_argument("--plan", action="store_true", help="dry-run (default)")
    p.add_argument("--apply", action="store_true", help="promote in a transaction")
    p.add_argument("--db", default=os.environ.get("PGDATABASE", DB_DEFAULT))
    p.add_argument("--host", default=os.environ.get("PGHOST", "127.0.0.1"))
    p.add_argument("--port", default=os.environ.get("PGPORT", "5432"))
    p.add_argument("--user", default=os.environ.get("PGUSER", "postgres"))
    p.add_argument("--password", default=os.environ.get("PGPASSWORD", "postgres"))
    return p.parse_args()


def main() -> int:
    args = _parse_args()
    print(f"  target: {args.db}  conn: {args.user}@{args.host}:{args.port} (password {_redact(args.password)})")
    if args.apply and not args.plan:
        return _apply(args)
    return _plan(args)


if __name__ == "__main__":
    sys.exit(main())
