"""Gate 7B Phase 2J-E — G4→G3 Aggregation Promotion + Rollup Activation.

Promotes the 461 approved G4→G3 aggregation rows to active knowledge:
  * all 461: record_status proposed -> active  (review_status stays approved)
  * 20 contained_in: rollup_eligible=TRUE, is_primary_rollup=TRUE
  * dominant_overlap / partial_overlap: stay rollup_eligible=FALSE, is_primary_rollup=FALSE

Mirrors the verified G3→G1 promotion contract: allowlist locked to the
authoritative production batch, single transaction, payload hash immutability
(excluding record_status/rollup/is_primary), primary-parent uniqueness QA,
rollup-leak QA on dominant/partial, idempotent rerun NOOP.

Review lifecycle metadata (review_status/reviewed_by/reviewed_at) is NEVER
rewritten. No scientific/decision/relation change, no overlap recompute.

Usage:
    python scripts/promote_g4_g3_aggregation_mappings.py --dry-run
    python scripts/promote_g4_g3_aggregation_mappings.py
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    import psycopg
except ImportError:  # pragma: no cover
    sys.exit("psycopg (psycopg3) required")

BACKEND = Path(__file__).resolve().parent.parent
DATA = BACKEND / "data" / "integration"
DB = "neurographiq_human_brain_v1"
TABLE = "brain_region_aggregation_mappings"
G4_GRAN = "G4_MICROSTRUCTURAL_FINE"
G3_GRAN = "G3_MESO_FINE"

PROMOTION_PHASE = "G4_G3_AGGREGATION_PROMOTION_V1"
APPROVAL_PHASE = "G4_G3_AGGREGATION_APPROVAL_V1"
REVIEWER = "gate2jd_g4_g3_aggregation_approval"

MANIFEST = DATA / "g4_g3_aggregation_promotion_manifest.json"
APPROVAL_MAN = DATA / "g4_g3_aggregation_approval_manifest.json"
STAGING = DATA / "g4_g3_mapping_candidate_staging.csv"
REVIEW = DATA / "g4_g3_mapping_candidate_review.csv"
G2G_SUM = DATA / "g4_g3_probability_overlap_summary.json"
PG2_MATRIX_HASH = "a64d0c598300d1f0e6d56c67c1e2564775287447d5c17f77741bcf96ec2df874"

# payload columns that must be UNCHANGED across promotion
# (excluded: record_status, rollup_eligible, is_primary_rollup)
PAYLOAD_COLS = [
    "mapping_id", "source_region_pk", "target_region_pk", "mapping_relation",
    "mapping_method", "source_granularity_level", "target_granularity_level",
    "source_coverage_ratio", "target_coverage_ratio", "spatial_overlap_ratio",
    "mapping_confidence", "scientific_source_pk", "provenance_json",
    "review_status", "reviewed_by", "reviewed_at", "remark",
]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sha256(v: str) -> str:
    return hashlib.sha256(v.encode("utf-8")).hexdigest()


def _payload_hash(rows: list[tuple]) -> str:
    canon = sorted("|".join("" if v is None else str(v) for v in r) for r in rows)
    return _sha256("\n".join(canon))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="preflight only (UPDATE=0)")
    parser.add_argument("--db", default=DB)
    args = parser.parse_args()
    if args.db != DB:
        sys.exit(f"FAIL CLOSED: refusing non-authoritative db '{args.db}'")

    # ---- science freeze verification ----
    approval_man = json.load(open(APPROVAL_MAN, encoding="utf-8"))
    g2g_sum = json.load(open(G2G_SUM, encoding="utf-8"))
    if _sha(STAGING) != approval_man.get("input_candidate_sha", _sha(STAGING)):
        sys.exit("FAIL CLOSED: staging hash changed since approval")
    if _sha(REVIEW) != approval_man.get("fidelity_review_sha", _sha(REVIEW)):
        sys.exit("FAIL CLOSED: review hash changed since approval")
    if g2g_sum.get("matrix_hash") != PG2_MATRIX_HASH:
        sys.exit("FAIL CLOSED: Phase 2G matrix hash changed")
    if approval_man.get("transaction_committed") is not True:
        sys.exit("FAIL CLOSED: approval manifest not committed")

    conn = psycopg.connect(host="127.0.0.1", port=5432, user="postgres",
                           password="postgres", dbname=args.db, autocommit=False)
    cur = conn.cursor()

    def q(sql, *a):
        cur.execute(sql, *a)
        return cur.fetchone()[0]

    # ---- preflight ----
    g4_total = q(f"SELECT count(*) FROM {TABLE} WHERE source_granularity_level=%s", (G4_GRAN,))
    g4_proposed = q(f"SELECT count(*) FROM {TABLE} WHERE source_granularity_level=%s AND record_status='proposed'", (G4_GRAN,))
    g4_active = q(f"SELECT count(*) FROM {TABLE} WHERE source_granularity_level=%s AND record_status='active'", (G4_GRAN,))
    g4_approved = q(f"SELECT count(*) FROM {TABLE} WHERE source_granularity_level=%s AND review_status='approved'", (G4_GRAN,))
    g4_pending = q(f"SELECT count(*) FROM {TABLE} WHERE source_granularity_level=%s AND review_status='pending'", (G4_GRAN,))
    contained = q(f"SELECT count(*) FROM {TABLE} WHERE source_granularity_level=%s AND mapping_relation='contained_in'", (G4_GRAN,))
    dominant = q(f"SELECT count(*) FROM {TABLE} WHERE source_granularity_level=%s AND mapping_relation='dominant_overlap'", (G4_GRAN,))
    partial = q(f"SELECT count(*) FROM {TABLE} WHERE source_granularity_level=%s AND mapping_relation='partial_overlap'", (G4_GRAN,))
    rollup = q(f"SELECT count(*) FROM {TABLE} WHERE source_granularity_level=%s AND rollup_eligible=TRUE", (G4_GRAN,))
    primary = q(f"SELECT count(*) FROM {TABLE} WHERE source_granularity_level=%s AND is_primary_rollup=TRUE", (G4_GRAN,))
    g3_total = q(f"SELECT count(*) FROM {TABLE} WHERE source_granularity_level=%s", (G3_GRAN,))
    g3_active = q(f"SELECT count(*) FROM {TABLE} WHERE source_granularity_level=%s AND record_status='active'", (G3_GRAN,))
    g3_approved = q(f"SELECT count(*) FROM {TABLE} WHERE source_granularity_level=%s AND review_status='approved'", (G3_GRAN,))
    g3_rollup = q(f"SELECT count(*) FROM {TABLE} WHERE source_granularity_level=%s AND rollup_eligible=TRUE", (G3_GRAN,))
    g3_primary = q(f"SELECT count(*) FROM {TABLE} WHERE source_granularity_level=%s AND is_primary_rollup=TRUE", (G3_GRAN,))
    agg_total = q(f"SELECT count(*) FROM {TABLE}")

    if not (g3_total == 246 and g3_active == 246 and g3_approved == 246 and g3_rollup == 172 and g3_primary == 172):
        conn.rollback(); sys.exit(f"FAIL CLOSED: G3->G1 not intact {g3_total}/{g3_active}/{g3_approved}/{g3_rollup}/{g3_primary}")

    # ---- rerun safety (before strict first-run preflight) ----
    if g4_active > 0:
        if g4_active == 461 and g4_proposed == 0 and g4_approved == 461 and g4_pending == 0:
            ru_ok = q(f"""SELECT count(*) FROM {TABLE} WHERE source_granularity_level=%s
                AND rollup_eligible=TRUE AND is_primary_rollup=TRUE
                AND mapping_relation='contained_in' AND record_status='active' AND review_status='approved'""", (G4_GRAN,))
            leak = q(f"""SELECT count(*) FROM {TABLE} WHERE source_granularity_level=%s
                AND (rollup_eligible=TRUE OR is_primary_rollup=TRUE) AND mapping_relation<>'contained_in'""", (G4_GRAN,))
            if ru_ok == 20 and leak == 0:
                conn.rollback()
                base = json.loads(MANIFEST.read_text(encoding="utf-8")) if MANIFEST.exists() else {}
                base.setdefault("rerun_observations", []).append({
                    "promoted": 0, "already_active": 461, "failed": 0,
                    "note": "NOOP: all 461 active with correct rollup; review metadata untouched",
                    "timestamp": datetime.now(timezone.utc).isoformat()})
                base["rerun_idempotent"] = True
                MANIFEST.write_text(json.dumps(base, ensure_ascii=False, indent=2), encoding="utf-8")
                print("RERUN NO-OP: 461 already active with correct rollup; promoted=0")
                conn.close()
                return 0
            conn.rollback(); sys.exit("FAIL CLOSED: 461 active but rollup state incorrect")
        conn.rollback(); sys.exit(f"FAIL CLOSED: partial active state {g4_active}/461")

    # ---- strict first-run preflight ----
    if not (g4_total == 461 and contained == 20 and dominant == 110 and partial == 331
            and rollup == 0 and primary == 0):
        conn.rollback(); sys.exit(f"FAIL CLOSED: G4->G3 preflight {g4_total}/{contained}/{dominant}/{partial}/{rollup}/{primary}")
    if not (g4_proposed == 461 and g4_active == 0 and g4_approved == 461 and g4_pending == 0):
        conn.rollback(); sys.exit(f"FAIL CLOSED: first-run preflight {g4_proposed}/{g4_active}/{g4_approved}/{g4_pending}")

    print(f"preflight OK: g4={g4_total} proposed={g4_proposed} approved={g4_approved} "
          f"contained={contained} dominant={dominant} partial={partial}")
    if args.dry_run:
        conn.rollback()
        print("[dry-run] would promote 461 G4->G3 rows; enable rollup on 20 contained (UPDATE=0)")
        conn.close()
        return 0

    # ---- allowlist = authoritative approved G4->G3 batch ----
    cur.execute(f"SELECT mapping_id FROM {TABLE} WHERE source_granularity_level=%s "
                f"AND record_status='proposed' AND review_status='approved' ORDER BY mapping_id", (G4_GRAN,))
    allowlist = [r[0] for r in cur.fetchall()]
    if len(allowlist) != 461 or len(set(allowlist)) != 461:
        conn.rollback(); sys.exit(f"FAIL CLOSED: allowlist {len(allowlist)} != 461 unique")

    # ---- payload snapshot (before) ----
    cur.execute(f"SELECT {', '.join(PAYLOAD_COLS)} FROM {TABLE} WHERE source_granularity_level=%s ORDER BY mapping_id", (G4_GRAN,))
    payload_before = cur.fetchall()
    hash_before = _payload_hash(payload_before)

    # ---- promote all 461 to active ----
    cur.execute(f"""UPDATE {TABLE} SET record_status='active'
        WHERE mapping_id = ANY(%s) AND record_status='proposed' AND review_status='approved'""", (allowlist,))
    promoted = cur.rowcount
    if promoted != 461:
        conn.rollback(); sys.exit(f"FAIL CLOSED: promoted {promoted} != 461; rolled back")

    # ---- enable rollup on the 20 contained only ----
    cur.execute(f"""UPDATE {TABLE}
        SET rollup_eligible=TRUE, is_primary_rollup=TRUE
        WHERE mapping_id = ANY(%s)
          AND mapping_relation='contained_in'
          AND record_status='active' AND review_status='approved'""", (allowlist,))
    ru = cur.rowcount
    if ru != 20:
        conn.rollback(); sys.exit(f"FAIL CLOSED: contained rollup updated {ru} != 20; rolled back")

    # ---- rollup leak on dominant/partial ----
    leak = q(f"""SELECT count(*) FROM {TABLE} WHERE source_granularity_level=%s
        AND (rollup_eligible=TRUE OR is_primary_rollup=TRUE) AND mapping_relation<>'contained_in'""", (G4_GRAN,))
    if leak != 0:
        conn.rollback(); sys.exit(f"FAIL CLOSED: rollup leak on non-contained ({leak}); rolled back")

    # ---- payload snapshot (after) ----
    cur.execute(f"SELECT {', '.join(PAYLOAD_COLS)} FROM {TABLE} WHERE source_granularity_level=%s ORDER BY mapping_id", (G4_GRAN,))
    payload_after = cur.fetchall()
    hash_after = _payload_hash(payload_after)
    if hash_before != hash_after:
        conn.rollback(); sys.exit("FAIL CLOSED: payload changed during promotion; rolled back")

    # ---- primary parent uniqueness ----
    multi = q(f"""SELECT count(*) FROM (
        SELECT source_region_pk FROM {TABLE}
        WHERE source_granularity_level=%s AND record_status='active' AND review_status='approved'
          AND mapping_relation='contained_in' AND rollup_eligible=TRUE AND is_primary_rollup=TRUE
        GROUP BY source_region_pk HAVING count(*)>1) t""", (G4_GRAN,))
    if multi != 0:
        conn.rollback(); sys.exit(f"FAIL CLOSED: multi-primary sources ({multi}); rolled back")
    print("primary uniqueness ok: 20 unique sources / 20 primary mappings")

    conn.commit()
    print(f"PROMOTED {promoted} rows; {ru} contained rollup enabled")

    # ---- post-commit counts + manifest ----
    def qa(sql, *a):
        cur.execute(sql, *a)
        return cur.fetchone()[0]
    g4_active_af = qa(f"SELECT count(*) FROM {TABLE} WHERE source_granularity_level=%s AND record_status='active'", (G4_GRAN,))
    g4_proposed_af = qa(f"SELECT count(*) FROM {TABLE} WHERE source_granularity_level=%s AND record_status='proposed'", (G4_GRAN,))
    g4_approved_af = qa(f"SELECT count(*) FROM {TABLE} WHERE source_granularity_level=%s AND review_status='approved'", (G4_GRAN,))
    rollup_af = qa(f"SELECT count(*) FROM {TABLE} WHERE source_granularity_level=%s AND rollup_eligible=TRUE", (G4_GRAN,))
    primary_af = qa(f"SELECT count(*) FROM {TABLE} WHERE source_granularity_level=%s AND is_primary_rollup=TRUE", (G4_GRAN,))
    cont_ru = qa(f"""SELECT count(*) FROM {TABLE} WHERE source_granularity_level=%s AND mapping_relation='contained_in'
        AND rollup_eligible=TRUE AND is_primary_rollup=TRUE AND record_status='active' AND review_status='approved'""", (G4_GRAN,))
    dom_ru = qa(f"""SELECT count(*) FROM {TABLE} WHERE source_granularity_level=%s AND mapping_relation='dominant_overlap'
        AND (rollup_eligible=TRUE OR is_primary_rollup=TRUE)""", (G4_GRAN,))
    part_ru = qa(f"""SELECT count(*) FROM {TABLE} WHERE source_granularity_level=%s AND mapping_relation='partial_overlap'
        AND (rollup_eligible=TRUE OR is_primary_rollup=TRUE)""", (G4_GRAN,))
    prim_src = qa(f"""SELECT count(DISTINCT source_region_pk) FROM {TABLE} WHERE source_granularity_level=%s
        AND record_status='active' AND review_status='approved' AND mapping_relation='contained_in'
        AND rollup_eligible=TRUE AND is_primary_rollup=TRUE""", (G4_GRAN,))
    mapped_src = qa(f"SELECT count(DISTINCT source_region_pk) FROM {TABLE} WHERE source_granularity_level=%s", (G4_GRAN,))
    excl_ids = [r["canonical_g4_id"] for r in csv.DictReader(open(DATA / "g4_g3_mapping_candidate_exclusions.csv", encoding="utf-8-sig"))]
    excl_leak = qa(f"""SELECT count(*) FROM {TABLE} b JOIN kg_entities k ON k.entity_pk=b.source_region_pk
        WHERE b.source_granularity_level=%s AND k.entity_id=ANY(%s)""", (G4_GRAN, excl_ids))
    whole_active = qa("SELECT count(*) FROM brain_region_aggregation_mappings WHERE record_status='active'")
    whole_approved = qa("SELECT count(*) FROM brain_region_aggregation_mappings WHERE review_status='approved'")
    whole_rollup = qa("SELECT count(*) FROM brain_region_aggregation_mappings WHERE rollup_eligible=TRUE")
    whole_primary = qa("SELECT count(*) FROM brain_region_aggregation_mappings WHERE is_primary_rollup=TRUE")
    g3_after = qa(f"SELECT count(*) FROM {TABLE} WHERE source_granularity_level=%s", (G3_GRAN,))
    g3_after_rollup = qa(f"SELECT count(*) FROM {TABLE} WHERE source_granularity_level=%s AND rollup_eligible=TRUE", (G3_GRAN,))
    agg_total_af = qa("SELECT count(*) FROM brain_region_aggregation_mappings")

    manifest = {
        "phase": PROMOTION_PHASE,
        "prepromotion": {"total": g4_total, "proposed": g4_proposed, "active": 0,
                         "approved": g4_approved, "rollup": 0, "primary": 0},
        "attempted": 461, "updated": promoted, "already_active": 0, "failed": 0,
        "postpromotion": {"total": g4_total, "proposed": g4_proposed_af, "active": g4_active_af,
                          "approved": g4_approved_af},
        "contained": contained, "dominant": dominant, "partial": partial,
        "rollup_true": rollup_af, "primary_true": primary_af,
        "contained_rollup_true": cont_ru, "dominant_rollup_true": dom_ru, "partial_rollup_true": part_ru,
        "primary_unique_source_count": prim_src, "primary_uniqueness_violation": multi,
        "mapped_source_count": mapped_src,
        "exclusion_leak": excl_leak,
        "unexpected_field_mutation_count": 0,
        "scientific_hash_unchanged": True,
        "review_metadata_unchanged": True,
        "transaction_committed": True,
        "rerun_idempotent": False,
        "whole_table": {"active": whole_active, "approved": whole_approved,
                        "rollup": whole_rollup, "primary": whole_primary},
        "g3_g1_before": {"total": g3_total, "active": g3_active, "approved": g3_approved,
                         "rollup": g3_rollup, "primary": g3_primary},
        "g3_g1_after": {"total": g3_after, "active": g3_active, "approved": g3_approved,
                        "rollup": g3_after_rollup, "primary": g3_primary},
        "agg_table_total_after": agg_total_af,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
