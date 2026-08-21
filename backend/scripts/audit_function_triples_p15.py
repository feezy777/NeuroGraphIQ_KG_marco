"""P1.5 pre-audit: existing Function Triple provenance, references, collisions.

Read-only. Usage:
    python scripts/audit_function_triples_p15.py
"""

from __future__ import annotations

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg  # noqa: E402

ENV_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
_url = None
with open(ENV_PATH, encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if line.startswith("DATABASE_URL=") and not line.startswith("#"):
            _url = line.split("=", 1)[1].strip().strip('"').strip("'")
            break
_url = re.sub(r"^postgresql\+[a-z_]+://", "postgresql://", _url)


def main() -> None:
    with psycopg.connect(_url) as conn:
        cur = conn.cursor()

        print("=" * 70)
        print("A) FUNCTION TRIPLE CURRENT STATE")
        print("=" * 70)
        cur.execute("SELECT count(*) FROM mirror_kg_triples")
        total = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM mirror_kg_triples WHERE object_type='function'")
        fn_total = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM mirror_kg_triples WHERE object_type='function' AND object_id IS NULL")
        fn_null = cur.fetchone()[0]
        print(f"triples_total={total} function_total={fn_total} function_object_id_NULL={fn_null}")

        print()
        print("B) SOURCE BREAKDOWN OF NULL-OBJECT FUNCTION TRIPLES")
        cur.execute("""SELECT
            count(*) FILTER (WHERE source_mirror_function_id IS NOT NULL AND source_mirror_circuit_id IS NULL) AS from_region_fn,
            count(*) FILTER (WHERE source_mirror_circuit_id IS NOT NULL AND source_mirror_function_id IS NULL) AS from_circuit,
            count(*) FILTER (WHERE source_mirror_function_id IS NULL AND source_mirror_circuit_id IS NULL) AS from_unknown
            FROM mirror_kg_triples WHERE object_type='function' AND object_id IS NULL""")
        r = cur.fetchone()
        print(f"  source_region_function={r[0]} source_circuit={r[1]} source_unknown={r[2]}")
        cur.execute("""SELECT raw_payload_json->>'source', count(*) FROM mirror_kg_triples
                       WHERE object_type='function' AND object_id IS NULL
                       GROUP BY 1 ORDER BY 2 DESC LIMIT 10""")
        print("  raw source tag:")
        for tag, c in cur.fetchall():
            print(f"    {tag!r}: {c}")

        print()
        print("C) EXTERNAL REFERENCES TO FUNCTION TRIPLES (review / evidence / audit)")
        for probe in ("mirror_human_review_records", "mirror_evidence_records", "mirror_promotion_records"):
            try:
                cur.execute(f"SELECT count(*) FROM {probe}")
                total_rows = cur.fetchone()[0]
                cur.execute(f"""SELECT count(*) FROM {probe} WHERE evidence_target_type='mirror_triple'
                                OR final_target_type='mirror_triple' OR target_type='mirror_triple'""")
                direct = cur.fetchone()[0]
                print(f"  [{probe}] rows={total_rows} referencing mirror_triple={direct}")
            except Exception as exc:  # noqa: BLE001
                print(f"  [{probe}] probe failed: {exc}")
        # any table with FK to mirror_kg_triples?
        cur.execute("""SELECT conrelid::regclass::text AS tbl, confrelid::regclass::text AS ref_tbl
                       FROM pg_constraint WHERE contype='f' AND confrelid='mirror_kg_triples'::regclass""")
        fks = cur.fetchall()
        print("  FKs referencing mirror_kg_triples:", fks if fks else "none")

        print()
        print("D) CANONICAL KEY / LABEL DEPENDENCE CHECK")
        cur.execute("""SELECT count(*) FROM mirror_kg_triples
                       WHERE object_type='function' AND object_id IS NULL
                       AND (raw_payload_json->>'term_id') IS NOT NULL""")
        print("  NULL-object triples that already carry term_id in payload:",
              cur.fetchone()[0])

        print()
        print("E) MULTI-SOURCE SPO (same subject+predicate+object across relations)")
        cur.execute("""SELECT count(*) FROM (
            SELECT subject_type, subject_id, predicate, object_type, object_id,
                   count(DISTINCT coalesce(source_mirror_function_id::text,'') || '|' ||
                         coalesce(source_mirror_circuit_id::text,'') || '|' ||
                         coalesce(source_mirror_connection_id::text,'')) AS srcs
            FROM mirror_kg_triples WHERE object_type='function'
            GROUP BY 1,2,3,4,5 HAVING count(DISTINCT coalesce(source_mirror_function_id::text,'') || '|' ||
                         coalesce(source_mirror_circuit_id::text,'') || '|' ||
                         coalesce(source_mirror_connection_id::text,'')) > 1
        ) s""")
        print("  SPO with >1 distinct source relation:", cur.fetchone()[0])

        print()
        print("F) PREDICATE MAPPING SNAPSHOT (current function predicates)")
        cur.execute("""SELECT predicate, count(*) FROM mirror_kg_triples WHERE object_type='function'
                       GROUP BY 1 ORDER BY 2 DESC""")
        for pred, c in cur.fetchall():
            print(f"  {pred}: {c}")

        print()
        print("G) CONNECTION TRIPLES (must not be touched)")
        cur.execute("""SELECT predicate, count(*) FROM mirror_kg_triples
                       WHERE object_type='region_candidate' AND object_id IS NOT NULL
                       GROUP BY 1 ORDER BY 2 DESC""")
        for pred, c in cur.fetchall():
            print(f"  {pred}: {c}")

        print()
        print("H) EXISTING INDEXES ON mirror_kg_triples")
        cur.execute("""SELECT indexname, indexdef FROM pg_indexes WHERE tablename='mirror_kg_triples'""")
        for name, d in cur.fetchall():
            print(f"  {name}: {d}")


if __name__ == "__main__":
    main()
