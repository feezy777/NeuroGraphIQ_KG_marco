"""P1.5 post-audit: Function Triple integrity + graph closure sampling.

Read-only. Usage:
    python scripts/audit_function_triples_after_p15.py
"""

from __future__ import annotations

import os
import random
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
    random.seed(42)
    with psycopg.connect(_url) as conn:
        cur = conn.cursor()

        print("=" * 70)
        print("A) MIRROR TRIPLE OVERALL")
        print("=" * 70)
        cur.execute("SELECT count(*) FROM mirror_kg_triples")
        total = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM mirror_kg_triples WHERE object_type='function'")
        fn_total = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM mirror_kg_triples WHERE object_type='function' AND object_id IS NULL")
        fn_null = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM mirror_kg_triples WHERE object_type='function' AND object_id IS NOT NULL")
        fn_ok = cur.fetchone()[0]
        print(f"triples_total={total} function_total={fn_total} object_id_NULL={fn_null} object_id_set={fn_ok}")

        print()
        print("B) FUNCTION TRIPLE OBJECT INTEGRITY")
        cur.execute("""SELECT
            count(*) FILTER (WHERE ot.id IS NULL) AS orphan,
            count(*) FILTER (WHERE ot.term_type <> 'function') AS invalid_type,
            count(*) FILTER (WHERE ot.status = 'merged') AS merged,
            count(*) FILTER (WHERE ot.status = 'deprecated') AS deprecated
            FROM mirror_kg_triples t LEFT JOIN ontology_terms ot ON ot.id = t.object_id
            WHERE t.object_type='function' AND t.object_id IS NOT NULL""")
        orphan, invalid_type, merged, deprecated = cur.fetchone()
        print(f"orphan={orphan} invalid_type={invalid_type} merged={merged} deprecated={deprecated}")

        cur.execute("""SELECT count(*) FROM (
            SELECT subject_type, subject_id, predicate, object_id FROM mirror_kg_triples
            WHERE object_type='function' GROUP BY 1,2,3,4 HAVING count(*) > 1) s""")
        print("duplicate canonical SPO:", cur.fetchone()[0])

        cur.execute("""SELECT count(*) FROM (
            SELECT subject_type, subject_id, predicate, object_id, count(*) c FROM mirror_kg_triples
            WHERE object_type='function' GROUP BY 1,2,3,4) s WHERE c > 1""")
        print("rows inside duplicate SPOs:", cur.fetchone()[0])

        cur.execute("""SELECT count(*) FROM mirror_kg_triples t JOIN ontology_terms ot ON ot.id=t.object_id
                       WHERE t.object_type='function' AND t.object_id IS NOT NULL
                       AND lower(regexp_replace(btrim(t.object_label),'[^a-z0-9]+',' ','g'))
                           <> lower(regexp_replace(btrim(ot.canonical_term_en),'[^a-z0-9]+',' ','g'))""")
        print("object_label != canonical name (normalize):", cur.fetchone()[0])

        cur.execute("""SELECT count(*) FROM (
            SELECT subject_type, subject_id, predicate, object_id,
                   jsonb_array_length(raw_payload_json->'provenance'->'source_relation_ids') AS n
            FROM mirror_kg_triples WHERE object_type='function'
            AND jsonb_typeof(raw_payload_json->'provenance'->'source_relation_ids') = 'array'
            AND jsonb_array_length(raw_payload_json->'provenance'->'source_relation_ids') > 1) s""")
        print("multi-source SPO (lineage >1):", cur.fetchone()[0])

        print()
        print("C) NON-FUNCTION TRIPLES (must be untouched)")
        cur.execute("""SELECT object_type, predicate, count(*) FROM mirror_kg_triples
                       WHERE object_type <> 'function' GROUP BY 1,2 ORDER BY 3 DESC LIMIT 10""")
        for r in cur.fetchall():
            print(f"  {r[0]}: {r[1]} = {r[2]}")
        cur.execute("SELECT count(*) FROM mirror_kg_triples WHERE object_type <> 'function'")
        print("non-function total:", cur.fetchone()[0])

        print()
        print("D) PROJECTION VERSION TAGGING")
        cur.execute("SELECT projection_version, count(*) FROM mirror_kg_triples WHERE object_type='function' GROUP BY 1")
        print("  by version:", cur.fetchall())

        print()
        print("E) GRAPH CLOSURE SAMPLING")
        samples = {"region": 50, "projection": 50, "circuit": 100}
        for kind, n in samples.items():
            if kind == "region":
                subj = "region_candidate"
                rel = "mirror_region_functions"
                rel_subj = "region_candidate_id"
            elif kind == "projection":
                subj = "connection"
                rel = "mirror_projection_functions"
                rel_subj = "projection_id"
            else:
                subj = "circuit"
                rel = "mirror_circuit_functions"
                rel_subj = "circuit_id"
            cur.execute(f"""SELECT t.id, t.subject_id, t.predicate, t.object_id, t.object_label
                           FROM mirror_kg_triples t WHERE t.subject_type=%s AND t.object_type='function'
                           ORDER BY random() LIMIT %s""", (subj, n))
            rows = cur.fetchall()
            closed = 0
            label_mismatch = 0
            for tid, sid, pred, oid, label in rows:
                cur.execute(f"""SELECT ot.canonical_term_en, ot.status FROM ontology_terms ot WHERE ot.id=%s""", (oid,))
                term = cur.fetchone()
                cur.execute(f"""SELECT count(*) FROM {rel} r WHERE r.term_id=%s AND r.{rel_subj}=%s""", (oid, sid))
                rel_hit = cur.fetchone()[0]
                if term and rel_hit > 0:
                    closed += 1
                if term and label != term[0]:
                    label_mismatch += 1
            print(f"  [{kind}] sampled={len(rows)} closure_ok={closed} label_mismatch={label_mismatch}")

        print()
        print("F) EXAMPLE TRIPLES (10)")
        cur.execute("""SELECT t.subject_type, t.subject_label, t.predicate, t.object_label, ot.term_code
                       FROM mirror_kg_triples t JOIN ontology_terms ot ON ot.id=t.object_id
                       WHERE t.object_type='function' AND t.subject_type='region_candidate'
                       ORDER BY random() LIMIT 4""")
        for r in cur.fetchall():
            print(f"  Region {r[1][:28]:28} -- {r[2]} --> {r[3][:28]:28} [{r[4]}]")
        cur.execute("""SELECT t.subject_type, t.subject_label, t.predicate, t.object_label, ot.term_code
                       FROM mirror_kg_triples t JOIN ontology_terms ot ON ot.id=t.object_id
                       WHERE t.object_type='function' AND t.subject_type='connection'
                       ORDER BY random() LIMIT 3""")
        for r in cur.fetchall():
            print(f"  Projection {r[1][:28]:28} -- {r[2]} --> {r[3][:28]:28} [{r[4]}]")
        cur.execute("""SELECT t.subject_type, t.subject_label, t.predicate, t.object_label, ot.term_code
                       FROM mirror_kg_triples t JOIN ontology_terms ot ON ot.id=t.object_id
                       WHERE t.object_type='function' AND t.subject_type='circuit'
                       ORDER BY random() LIMIT 3""")
        for r in cur.fetchall():
            print(f"  Circuit {r[1][:28]:28} -- {r[2]} --> {r[3][:28]:28} [{r[4]}]")


if __name__ == "__main__":
    main()
