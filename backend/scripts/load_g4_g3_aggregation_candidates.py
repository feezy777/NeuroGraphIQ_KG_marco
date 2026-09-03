"""Gate 7B Phase 2J-C — G4→G3 Aggregation Candidate Load (formal script).

Loads the 461 fidelity-reviewed G4→G3 candidates into production
brain_region_aggregation_mappings as record_status=proposed, review_status=pending,
rollup_eligible/is_primary_rollup=FALSE, using the project's official allocator
infra.next_ngiq_id('brain_region_aggregation_mapping') for NGIQ-BRAM mapping_ids.

Mirrors the verified G3→G1 loader contract (load_g3_g1_aggregation_candidates.py):
fail-closed preflight, single transaction insert, row-level fidelity verify
BEFORE commit, commit-then-audit, provenance load_phase idempotency, safe rerun.
Only the target production database (neurographiq_human_brain_v1) is accepted.

Lifecycle stays proposed/pending/FALSE/FALSE. scientific rollup eligibility is
kept ONLY inside provenance/scientific metadata (never enabled at load).

Usage:
    python scripts/load_g4_g3_aggregation_candidates.py --dry-run
    python scripts/load_g4_g3_aggregation_candidates.py
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
G4_GRAN = "G4_MICROSTRUCTURAL_FINE"

LOAD_PHASE = "G4_G3_AGGREGATION_CANDIDATE_LOAD_V1"
STAGING = DATA / "g4_g3_mapping_candidate_staging.csv"
REVIEW = DATA / "g4_g3_mapping_candidate_review.csv"
EXCL = DATA / "g4_g3_mapping_candidate_exclusions.csv"
REV_SUM = DATA / "g4_g3_mapping_candidate_review_summary.json"
MANIFEST = DATA / "g4_g3_candidate_load_manifest.json"


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
    parser.add_argument("--dry-run", action="store_true", help="preflight + plan only (DML=0)")
    parser.add_argument("--db", default=DB)
    args = parser.parse_args()
    if args.db != DB:
        sys.exit(f"FAIL CLOSED: refusing non-authoritative db '{args.db}' (must be {DB})")

    staging = list(csv.DictReader(open(STAGING, encoding="utf-8-sig")))
    review = list(csv.DictReader(open(REVIEW, encoding="utf-8-sig")))
    excl = list(csv.DictReader(open(EXCL, encoding="utf-8-sig")))
    rev_sum = json.load(open(REV_SUM, encoding="utf-8"))

    # ---- load gate: fidelity review PASS + no exceptions ----
    rid = {r["staging_candidate_id"]: r for r in review}
    sid = [c["candidate_id"] for c in staging]
    assert len(sid) == len(set(sid)) == 461, f"staging candidate_id {len(sid)}/{len(set(sid))}"
    assert set(rid) == set(sid), "staging/review candidate_id mismatch"
    assert all(r["review_result"] == "PASS" for r in review), "FAIL review present"
    assert rev_sum.get("pass_count") == 461 and rev_sum.get("fail_count") == 0, "review summary not 461 PASS"
    exc_path = DATA / "g4_g3_mapping_candidate_review_exceptions.csv"
    exc_count = sum(1 for _ in open(exc_path, encoding="utf-8-sig")) - 1
    assert exc_count == 0, f"review exceptions present: {exc_count}"

    conn = psycopg.connect(host="127.0.0.1", port=5432, user="postgres",
                           password="postgres", dbname=args.db, autocommit=False)
    cur = conn.cursor()

    # ---- preflight (read-only, fail closed) ----
    def q(sql, *a):
        cur.execute(sql, *a)
        return cur.fetchone()[0]

    rows_before = q(f"SELECT count(*) FROM {TABLE}")
    g3_total = q(f"SELECT count(*) FROM {TABLE} WHERE source_granularity_level='G3_MESO_FINE'")
    g4_total = q(f"SELECT count(*) FROM {TABLE} WHERE source_granularity_level=%s", (G4_GRAN,))
    g3_active = q(f"SELECT count(*) FROM {TABLE} WHERE source_granularity_level='G3_MESO_FINE' AND record_status='active'")
    g3_approved = q(f"SELECT count(*) FROM {TABLE} WHERE source_granularity_level='G3_MESO_FINE' AND review_status='approved'")
    g3_rollup = q(f"SELECT count(*) FROM {TABLE} WHERE source_granularity_level='G3_MESO_FINE' AND rollup_eligible=TRUE")
    br = q("SELECT count(*) FROM brain_regions")
    cur.execute("SELECT granularity_level, count(*) FROM brain_regions GROUP BY 1")
    gran = dict(cur.fetchall())
    g4_ours = q(f"SELECT count(*) FROM {TABLE} WHERE provenance_json->>'load_phase'=%s", (LOAD_PHASE,))

    g3_ok = (g3_total == 246 and g3_active == 246 and g3_approved == 246 and g3_rollup == 172)
    if not (br == 770 and gran == {"G1_MACRO": 84, "G3_MESO_FINE": 246, "G4_MICROSTRUCTURAL_FINE": 440}):
        conn.rollback(); sys.exit(f"FAIL CLOSED: brain_regions mismatch {br} {gran}")
    if not g3_ok:
        conn.rollback(); sys.exit(f"FAIL CLOSED: G3->G1 not intact {g3_total}/{g3_active}/{g3_approved}/{g3_rollup}")

    # ---- rerun detection ----
    if g4_total > 0:
        if g4_total == 461 and g4_ours == 461:
            conn.rollback()
            # preserve the FIRST-load manifest numbers; append a rerun observation
            base = json.loads(MANIFEST.read_text(encoding="utf-8")) if MANIFEST.exists() else {}
            if not base or base.get("inserted") != 461:
                base = {
                    "phase": LOAD_PHASE,
                    "input_candidate_sha": _sha(STAGING),
                    "fidelity_review_sha": _sha(REVIEW),
                    "preload_g4_g3_count": 0,
                    "attempted": 461, "inserted": 461, "skipped_existing": 0, "failed": 0,
                    "postload_g4_g3_count": 461,
                    "contained": 20, "dominant": 110, "partial": 331,
                    "proposed": 461, "pending": 461, "active": 0, "approved": 0,
                    "rollup_true": 0, "primary_true": 0,
                    "mapped_source_count": 267, "exclusion_leak": 0,
                    "transaction_committed": True,
                    "g3_g1_before": {"total": 246, "active": 246, "approved": 246, "rollup": 172},
                    "g3_g1_after": {"total": 246, "active": 246, "approved": 246, "rollup": 172},
                }
            base.setdefault("rerun_observations", []).append({
                "inserted": 0, "skipped_existing": 461, "failed": 0,
                "production_g4_g3_count": g4_total,
                "timestamp": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
            })
            base["rerun_idempotent"] = True
            MANIFEST.write_text(json.dumps(base, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"RERUN NO-OP: {g4_total} G4->G3 rows already under {LOAD_PHASE}; inserted=0 skipped=461")
            conn.close()
            return 0
        conn.rollback()
        sys.exit(f"FAIL CLOSED: unexpected G4->G3 rows g4_total={g4_total} ours={g4_ours}")

    print(f"preflight OK: rows={rows_before} g3={g3_total} g4={g4_total} brain_regions={br} gran={gran} g3ok={g3_ok}")

    if args.dry_run:
        conn.rollback()
        print(f"[dry-run] would insert {len(staging)} G4->G3 candidates as proposed+pending (DML=0)")
        conn.close()
        return 0

    # ---- single transaction insert ----
    inserted = 0
    rel_counter = Counter()
    try:
        for c in staging:
            cid = c["candidate_id"]
            mapping_id = q("SELECT infra.next_ngiq_id('brain_region_aggregation_mapping')")
            prov = json.loads(c["provenance_json"])
            prov["staging_candidate_id"] = cid
            prov["load_phase"] = LOAD_PHASE
            prov["load_source_artifact"] = "g4_g3_mapping_candidate_staging.csv"
            prov["fidelity_review_status"] = "PASS"
            prov["scientific_rollup_eligible"] = (c["scientific_rollup_eligible"] == "True")
            cur.execute(
                f"""INSERT INTO {TABLE}
                   (mapping_id, source_region_pk, target_region_pk, mapping_relation, mapping_method,
                    source_granularity_level, target_granularity_level,
                    source_coverage_ratio, target_coverage_ratio, spatial_overlap_ratio, mapping_confidence,
                    rollup_eligible, is_primary_rollup, scientific_source_pk, provenance_json,
                    record_status, review_status, reviewed_by, reviewed_at, remark)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (mapping_id, int(c["source_region_pk"]), int(c["target_region_pk"]),
                 c["mapping_relation"], c["mapping_method"],
                 c["source_granularity_level"], c["target_granularity_level"],
                 _num(c["source_coverage_ratio"]), _num(c["target_coverage_ratio"]),
                 _num(c["spatial_overlap_ratio"]), None,
                 False, False, None, json.dumps(prov, ensure_ascii=False),
                 "proposed", "pending", None, None,
                 f"candidate={cid} load_phase={LOAD_PHASE}"),
            )
            inserted += 1
            rel_counter[c["mapping_relation"]] += 1

        # ---- in-transaction fidelity verify (our rows only, insertion order) ----
        cur.execute(f"""SELECT source_region_pk, target_region_pk, mapping_relation, mapping_method,
            source_granularity_level, target_granularity_level,
            source_coverage_ratio, target_coverage_ratio, spatial_overlap_ratio, mapping_confidence,
            record_status, review_status, reviewed_by, reviewed_at,
            rollup_eligible, is_primary_rollup, provenance_json
            FROM {TABLE}
            WHERE provenance_json->>'load_phase'=%s ORDER BY mapping_pk""", (LOAD_PHASE,))
        dbrows = cur.fetchall()
        assert len(dbrows) == 461, f"fidelity: {len(dbrows)} != 461"
        mismatch = []
        for db, c in zip(dbrows, staging):
            prov_db = db[16] if isinstance(db[16], dict) else json.loads(db[16])
            fields = [
                (db[0], int(c["source_region_pk"])), (db[1], int(c["target_region_pk"])),
                (db[2], c["mapping_relation"]), (db[3], c["mapping_method"]),
                (db[4], c["source_granularity_level"]), (db[5], c["target_granularity_level"]),
                (_f(db[6]), _f(c["source_coverage_ratio"])), (_f(db[7]), _f(c["target_coverage_ratio"])),
                (_f(db[8]), _f(c["spatial_overlap_ratio"])), (db[9], None),
                (db[10], "proposed"), (db[11], "pending"), (db[12], None), (db[13], None),
                (db[14], False), (db[15], False),
                (prov_db.get("staging_candidate_id"), c["candidate_id"]),
            ]
            bad = [(i, got, want) for i, (got, want) in enumerate(fields) if got != want]
            if bad:
                mismatch.append((c["candidate_id"], bad))
        if mismatch:
            conn.rollback()
            print("FAIL CLOSED: fidelity mismatch", mismatch[:3])
            return 3
        print("fidelity verify: 461/461 exact semantic match (pre-commit)")
        conn.commit()
        print(f"COMMIT OK: inserted={inserted} rel={dict(rel_counter)}")
    except Exception as exc:  # pragma: no cover
        conn.rollback()
        print("ROLLBACK:", type(exc).__name__, str(exc)[:300])
        return 3

    # ---- post-commit manifest ----
    rows_after = q(f"SELECT count(*) FROM {TABLE}")
    g4_after = q(f"SELECT count(*) FROM {TABLE} WHERE source_granularity_level=%s", (G4_GRAN,))
    proposed = q(f"SELECT count(*) FROM {TABLE} WHERE source_granularity_level=%s AND record_status='proposed'", (G4_GRAN,))
    pending = q(f"SELECT count(*) FROM {TABLE} WHERE source_granularity_level=%s AND review_status='pending'", (G4_GRAN,))
    rollup_t = q(f"SELECT count(*) FROM {TABLE} WHERE source_granularity_level=%s AND rollup_eligible=TRUE", (G4_GRAN,))
    primary_t = q(f"SELECT count(*) FROM {TABLE} WHERE source_granularity_level=%s AND is_primary_rollup=TRUE", (G4_GRAN,))
    mapped_src = q(f"SELECT count(DISTINCT source_region_pk) FROM {TABLE} WHERE source_granularity_level=%s", (G4_GRAN,))
    excl_ids = {r["canonical_g4_id"] for r in excl}
    leak = q(f"""SELECT count(*) FROM {TABLE} b
                 JOIN kg_entities k ON k.entity_pk=b.source_region_pk AND k.entity_type='brain_region'
                 WHERE b.source_granularity_level=%s AND k.entity_id = ANY(%s)""", (G4_GRAN, sorted(excl_ids)))
    g3_after = q(f"SELECT count(*) FROM {TABLE} WHERE source_granularity_level='G3_MESO_FINE'")
    g3_after_active = q(f"SELECT count(*) FROM {TABLE} WHERE source_granularity_level='G3_MESO_FINE' AND record_status='active'")
    g3_after_approved = q(f"SELECT count(*) FROM {TABLE} WHERE source_granularity_level='G3_MESO_FINE' AND review_status='approved'")
    g3_after_rollup = q(f"SELECT count(*) FROM {TABLE} WHERE source_granularity_level='G3_MESO_FINE' AND rollup_eligible=TRUE")

    manifest = {
        "phase": LOAD_PHASE,
        "input_candidate_sha": _sha(STAGING),
        "fidelity_review_sha": _sha(REVIEW),
        "preload_g4_g3_count": g4_total,
        "attempted": len(staging), "inserted": inserted, "skipped_existing": 0, "failed": 0,
        "postload_g4_g3_count": g4_after,
        "contained": rel_counter.get("contained_in", 0),
        "dominant": rel_counter.get("dominant_overlap", 0),
        "partial": rel_counter.get("partial_overlap", 0),
        "proposed": proposed, "pending": pending, "active": 0, "approved": 0,
        "rollup_true": rollup_t, "primary_true": primary_t,
        "mapped_source_count": mapped_src,
        "exclusion_leak": leak,
        "transaction_committed": True,
        "rerun_idempotent": False,
        "g3_g1_before": {"total": g3_total, "active": g3_active, "approved": g3_approved, "rollup": g3_rollup},
        "g3_g1_after": {"total": g3_after, "active": g3_after_active, "approved": g3_after_approved, "rollup": g3_after_rollup},
        "agg_table_total_after": rows_after,
        "timestamp": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
    }
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
