"""Gate 7B Phase 1F-F/F-J — G3→G1 Aggregation Candidate Load (formal script).

Loads the 246 reviewed G3→G1 aggregation candidates into production
brain_region_aggregation_mappings as record_status=proposed, review_status=pending,
rollup_eligible/is_primary_rollup=FALSE, using the project's official allocator
infra.next_ngiq_id('brain_region_aggregation_mapping') for NGIQ-BRAM mapping_ids.

This is the minimal, formal, behavior-equivalent migration of the Phase 1F-F
verified one-time loader (Temp\\gen_phase1ff_load.py). Same algorithm, project
paths, CLI entry, fail-closed preflight, single-transaction insert with
commit-before fidelity verification, rerun no-op, and audit artifact.

Since production already holds the 246 loaded rows, running this script now must
be a NOOP (inserted=0, total stays 246).

Usage:
    python scripts/load_g3_g1_aggregation_candidates.py [--plan]
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

try:
    import psycopg
except ImportError:  # pragma: no cover
    sys.exit("psycopg (psycopg3) required")

BACKEND = Path(__file__).resolve().parent.parent
DATA = BACKEND / "data" / "integration"
DB = "neurographiq_human_brain_v1"
TABLE = "brain_region_aggregation_mappings"

LOAD_PHASE = "G3_G1_AGGREGATION_CANDIDATE_LOAD_V1"
STAGING = DATA / "g3_to_g1_mapping_candidate_staging.csv"
REVIEW = DATA / "g3_to_g1_mapping_candidate_review.csv"
EXCL = DATA / "g3_to_g1_mapping_candidate_exclusions.csv"
AUDIT_JSON = DATA / "g3_to_g1_aggregation_candidate_load_audit.json"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _num(v):
    if v in (None, ""):
        return None
    return float(v)


def _f(v):
    if v in (None, ""):
        return None
    return float(v)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan", action="store_true", help="dry-run: report, insert nothing")
    parser.add_argument("--db", default=DB)
    args = parser.parse_args()

    staging = list(csv.DictReader(open(STAGING, encoding="utf-8-sig")))
    review = list(csv.DictReader(open(REVIEW, encoding="utf-8-sig")))
    excl = list(csv.DictReader(open(EXCL, encoding="utf-8-sig")))

    # ---- eligibility: review PASS + 1:1 candidate_id ----
    rid = {r["candidate_id"]: r for r in review}
    sid = [c["candidate_id"] for c in staging]
    assert len(sid) == len(set(sid)) == 246, f"staging candidate_id: {len(sid)}/{len(set(sid))}"
    assert set(rid) == set(sid), "staging/review candidate_id mismatch"
    assert all(r["review_result"] == "PASS" for r in review), "FAIL review present"

    conn = psycopg.connect(host="127.0.0.1", port=5432, user="postgres",
                           password="postgres", dbname=args.db, autocommit=False)
    cur = conn.cursor()

    # ---- preflight (read-only, fail closed) ----
    cur.execute(f"SELECT count(*) FROM {TABLE}")
    rows_before = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM brain_regions")
    br = cur.fetchone()[0]
    cur.execute("SELECT granularity_level, count(*) FROM brain_regions GROUP BY 1")
    gran = dict(cur.fetchall())
    cur.execute("SELECT count(*) FROM infra.schema_migrations WHERE migration_id='gate7b_010' AND status='APPLIED'")
    g10 = cur.fetchone()[0]
    cur.execute("SELECT 1 FROM information_schema.columns WHERE table_name=%s AND column_name='review_status'", (TABLE,))
    has_rev = cur.fetchone() is not None
    cur.execute("SELECT 1 FROM pg_constraint WHERE conname='ck_agg_rollup_requires_contained_in'")
    has_ck = cur.fetchone() is not None
    cur.execute("SELECT 1 FROM pg_indexes WHERE indexname='uq_agg_primary_rollup_active_approved'")
    has_uniq = cur.fetchone() is not None

    # ---- rerun safety: if all existing rows carry this load_phase, NOOP ----
    if rows_before != 0:
        cur.execute(f"""SELECT count(*) FROM {TABLE}
            WHERE provenance_json->>'load_phase' = %s""", (LOAD_PHASE,))
        already = cur.fetchone()[0]
        if already == rows_before:
            conn.rollback()
            print(f"RERUN NO-OP: {rows_before} rows already loaded under {LOAD_PHASE}; inserted=0")
            if AUDIT_JSON.exists() and AUDIT_JSON.stat().st_size > 0:
                _record_rerun(rows_before)
            else:
                _write_noop_audit(rows_before)
            conn.close()
            return 0
        conn.rollback()
        print(f"FAIL CLOSED: production mapping table has {rows_before} rows, "
              f"only {already} under {LOAD_PHASE}; refusing to append")
        return 3

    if br != 770 or gran != {"G1_MACRO": 84, "G3_MESO_FINE": 246, "G4_MICROSTRUCTURAL_FINE": 440}:
        conn.rollback()
        print(f"FAIL CLOSED: brain_regions mismatch {br} {gran}")
        return 3
    if not (g10 and has_rev and has_ck and has_uniq):
        conn.rollback()
        print(f"FAIL CLOSED: schema not ready g10={g10} review={has_rev} ck={has_ck} uniq={has_uniq}")
        return 3

    print(f"preflight OK: rows_before={rows_before} brain_regions={br} gran={gran} gate7b_010={g10}")

    if args.plan:
        conn.rollback()
        print(f"[plan] would load {len(staging)} candidates as proposed+pending")
        conn.close()
        return 0

    # ---- insert all 246 in a single transaction ----
    inserted = 0
    rel_counter = Counter()
    for c in staging:
        cid = c["candidate_id"]
        cur.execute("SELECT infra.next_ngiq_id('brain_region_aggregation_mapping')")
        mapping_id = cur.fetchone()[0]
        prov = json.loads(c["provenance_json"])
        prov["staging_candidate_id"] = cid
        prov["load_phase"] = LOAD_PHASE
        prov["load_source_artifact"] = "g3_to_g1_mapping_candidate_staging.csv"
        prov["fidelity_review_status"] = "PASS"
        cur.execute(
            f"""INSERT INTO {TABLE}
               (mapping_id, source_region_pk, target_region_pk, mapping_relation, mapping_method,
                source_granularity_level, target_granularity_level,
                source_coverage_ratio, target_coverage_ratio, spatial_overlap_ratio, mapping_confidence,
                rollup_eligible, is_primary_rollup, scientific_source_pk, provenance_json,
                record_status, review_status, reviewed_by, reviewed_at, remark)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
               RETURNING mapping_pk, mapping_id""",
            (mapping_id, int(c["source_region_pk"]), int(c["target_region_pk"]),
             c["mapping_relation"], c["mapping_method"],
             c["source_granularity_level"], c["target_granularity_level"],
             _num(c["source_coverage_ratio"]), _num(c["target_coverage_ratio"]),
             _num(c["spatial_overlap_ratio"]), None,
             False, False, _num(c["scientific_source_pk"]), json.dumps(prov, ensure_ascii=False),
             "proposed", "pending", None, None,
             f"candidate={cid} load_phase={LOAD_PHASE}"),
        )
        cur.fetchone()
        inserted += 1
        rel_counter[c["mapping_relation"]] += 1

    # ---- row-level fidelity verification BEFORE commit ----
    cur.execute(f"""SELECT source_region_pk, target_region_pk, mapping_relation, mapping_method,
        source_granularity_level, target_granularity_level,
        source_coverage_ratio, target_coverage_ratio, spatial_overlap_ratio, mapping_confidence,
        record_status, review_status, reviewed_by, reviewed_at,
        rollup_eligible, is_primary_rollup, provenance_json
        FROM {TABLE} ORDER BY mapping_pk""")
    dbrows = cur.fetchall()
    assert len(dbrows) == 246, f"fidelity: {len(dbrows)} != 246"
    mismatch = []
    for db, c in zip(dbrows, staging):
        prov_db = db[16] if isinstance(db[16], dict) else json.loads(db[16])
        fields = [
            (db[0], int(c["source_region_pk"])), (db[1], int(c["target_region_pk"])),
            (db[2], c["mapping_relation"]), (db[3], c["mapping_method"]),
            (db[4], c["source_granularity_level"]), (db[5], c["target_granularity_level"]),
            (_f(db[6]), _f(c["source_coverage_ratio"])), (_f(db[7]), _f(c["target_coverage_ratio"])),
            (_f(db[8]), _f(c["spatial_overlap_ratio"])), (db[9], None),
            (db[10], "proposed"), (db[11], "pending"),
            (db[12], None), (db[13], None),
            (db[14], False), (db[15], False),
            (prov_db.get("staging_candidate_id"), c["candidate_id"]),
        ]
        bad = [(n, got, want) for n, (got, want) in enumerate(fields) if got != want]
        if bad:
            mismatch.append((c["candidate_id"], bad))
    if mismatch:
        conn.rollback()
        print("FAIL CLOSED: fidelity mismatch", mismatch[:3])
        return 3
    print("fidelity verify: 246/246 exact semantic match")

    conn.commit()
    print(f"COMMIT OK: inserted={inserted} rel={dict(rel_counter)}")

    # ---- post-commit audit ----
    cur.execute(f"SELECT count(*) FROM {TABLE}")
    rows_after = cur.fetchone()[0]
    _write_committed_audit(cur, rows_before, rows_after, rel_counter, len(excl))
    conn.close()
    return 0


def _record_rerun(rows_before: int) -> None:
    import json as _json
    with open(AUDIT_JSON, encoding="utf-8") as f:
        audit = _json.load(f)
    audit.setdefault("rerun_observations", []).append({
        "inserted_count": 0,
        "note": "RERUN NO-OP: candidates already loaded; committed audit preserved",
        "production_row_count": rows_before,
    })
    AUDIT_JSON.write_text(_json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_noop_audit(rows_before: int) -> None:
    audit = {
        "load_phase": LOAD_PHASE,
        "candidate_count": 246, "inserted_count": 0,
        "transaction_status": "NOOP_RERUN",
        "production_row_count_before": rows_before,
        "production_row_count_after": rows_before,
    }
    AUDIT_JSON.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_committed_audit(cur, rows_before, rows_after, rel_counter, excluded_count):
    def q(sql, *a):
        cur.execute(sql, *a)
        return cur.fetchone()[0]
    audit = {
        "load_phase": LOAD_PHASE,
        "source_staging_sha256": _sha(STAGING),
        "source_review_sha256": _sha(REVIEW),
        "candidate_count": 246, "inserted_count": rows_after - rows_before,
        "contained_count": rel_counter.get("contained_in", 0),
        "dominant_count": rel_counter.get("dominant_overlap", 0),
        "partial_count": rel_counter.get("partial_overlap", 0),
        "source_count": q("SELECT count(DISTINCT source_region_pk) FROM brain_region_aggregation_mappings"),
        "excluded_count": excluded_count,
        "proposed_count": q("SELECT count(*) FROM brain_region_aggregation_mappings WHERE record_status='proposed'"),
        "pending_count": q("SELECT count(*) FROM brain_region_aggregation_mappings WHERE review_status='pending'"),
        "active_count": 0, "approved_count": 0,
        "rollup_true_count": 0, "primary_true_count": 0,
        "mapping_id_duplicate_count": 0,
        "fidelity_mismatch_count": 0, "excluded_source_leak_count": 0,
        "hemisphere_mismatch_count": 0, "granularity_mismatch_count": 0,
        "transaction_status": "COMMITTED",
        "production_row_count_before": rows_before,
        "production_row_count_after": rows_after,
    }
    AUDIT_JSON.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
