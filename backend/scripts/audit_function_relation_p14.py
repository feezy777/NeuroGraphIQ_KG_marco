"""P1.4 read-only audit: function relation closure + function_association consistency.

Usage:
    python scripts/audit_function_relation_p14.py
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


def norm(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", (text or "").lower()))


def main() -> None:
    with psycopg.connect(_url) as conn:
        cur = conn.cursor()

        print("=" * 70)
        print("A) RELATION TERM_ID INTEGRITY")
        print("=" * 70)
        for t in ("mirror_region_functions", "mirror_projection_functions", "mirror_circuit_functions"):
            cur.execute(f"SELECT count(*) FROM {t}")
            total = cur.fetchone()[0]
            cur.execute(f"SELECT count(*) FROM {t} WHERE term_id IS NULL")
            nulls = cur.fetchone()[0]
            cur.execute(f"""SELECT count(*) FROM {t} r LEFT JOIN ontology_terms ot ON ot.id = r.term_id
                            WHERE r.term_id IS NOT NULL AND (ot.id IS NULL
                            OR ot.status IN ('merged','deprecated')
                            OR ot.term_type <> 'function'
                            OR ot.term_code NOT LIKE 'ng:func:%')""")
            invalid = cur.fetchone()[0]
            cur.execute(f"SELECT count(*) FROM {t} r JOIN ontology_terms ot ON ot.id = r.term_id WHERE ot.status = 'merged'")
            merged = cur.fetchone()[0]
            print(f"[{t}] total={total} term_id_NULL={nulls} invalid_or_merged={invalid} merged_residue={merged}")

        print()
        print("B) FUNCTION_ASSOCIATION CONSISTENCY (mirror_region_circuits)")
        cur.execute("SELECT count(*) FROM mirror_region_circuits")
        circ_total = cur.fetchone()[0]
        cur.execute("SELECT count(*) FROM mirror_region_circuits WHERE function_association IS NOT NULL AND btrim(function_association) <> ''")
        non_empty = cur.fetchone()[0]
        cur.execute("SELECT count(DISTINCT function_association) FROM mirror_region_circuits WHERE function_association IS NOT NULL")
        distinct_raw = cur.fetchone()[0]
        cur.execute("""SELECT count(*) FROM (SELECT DISTINCT lower(regexp_replace(btrim(function_association), '[^a-z0-9]+', ' ', 'g'))
                       FROM mirror_region_circuits WHERE function_association IS NOT NULL) s""")
        distinct_norm = cur.fetchone()[0]

        # matchable against active/proposed function terms (normalize key)
        cur.execute("SELECT canonical_term_en FROM ontology_terms WHERE term_type='function' AND status IN ('active','proposed')")
        term_keys = {norm(r[0]) for r in cur.fetchall()}
        cur.execute("""SELECT function_association FROM mirror_region_circuits
                       WHERE function_association IS NOT NULL AND btrim(function_association) <> ''""")
        assoc_texts = [r[0] for r in cur.fetchall()]
        matchable = sum(1 for t in assoc_texts if norm(t) in term_keys)
        unmatchable = len(assoc_texts) - matchable

        # circuits with association vs circuits with mirror_circuit_functions
        cur.execute("""SELECT count(DISTINCT circuit_id) FROM mirror_circuit_functions""")
        circ_with_fn = cur.fetchone()[0]
        cur.execute("""SELECT count(*) FROM mirror_region_circuits c
                       WHERE (c.function_association IS NOT NULL AND btrim(c.function_association) <> '')
                       AND NOT EXISTS (SELECT 1 FROM mirror_circuit_functions cf WHERE cf.circuit_id = c.id)""")
        assoc_no_fn = cur.fetchone()[0]
        cur.execute("""SELECT count(*) FROM mirror_region_circuits c
                       WHERE (c.function_association IS NULL OR btrim(c.function_association) = '')
                       AND EXISTS (SELECT 1 FROM mirror_circuit_functions cf WHERE cf.circuit_id = c.id)""")
        fn_no_assoc = cur.fetchone()[0]

        # semantic agreement: association normalize-key matches at least one
        # relation term of the same circuit (via relation term canonical name)
        cur.execute("""SELECT c.function_association, cf.circuit_id, ot.canonical_term_en
                       FROM mirror_region_circuits c
                       JOIN mirror_circuit_functions cf ON cf.circuit_id = c.id
                       JOIN ontology_terms ot ON ot.id = cf.term_id
                       WHERE c.function_association IS NOT NULL AND btrim(c.function_association) <> ''
                       AND cf.term_id IS NOT NULL""")
        rows = cur.fetchall()
        by_circuit: dict = {}
        for assoc, cid, canon in rows:
            by_circuit.setdefault(cid, (assoc, set()))
            by_circuit[cid][1].add(canon)
        agree = 0
        disagree = 0
        for cid, (assoc, canons) in by_circuit.items():
            if any(norm(assoc) == norm(c) or norm(assoc) in (norm(c) for c in canons) for c in canons):
                agree += 1
            else:
                disagree += 1

        print(f"circuits_total={circ_total}")
        print(f"association_non_empty={non_empty}")
        print(f"distinct_raw={distinct_raw} distinct_norm={distinct_norm}")
        print(f"association_matchable_to_function_term={matchable} unmatchable={unmatchable}")
        print(f"circuits_with_relation={circ_with_fn}")
        print(f"association_present_but_no_relation={assoc_no_fn}")
        print(f"relation_present_but_no_association={fn_no_assoc}")
        print(f"circuits_with_both_and_agree={agree} disagree={disagree}")

        print()
        print("C) TRIPLE SOURCE PREVIEW (dry-run candidate counts)")
        cur.execute("""SELECT count(*) FROM mirror_region_circuits c
                       WHERE (c.function_association IS NOT NULL AND btrim(c.function_association) <> '')
                       AND c.mirror_status NOT IN ('human_rejected','superseded','promoted_to_final')
                       AND c.review_status <> 'rejected'
                       AND c.promotion_status NOT IN ('failed','promoted')""")
        old_candidates = cur.fetchone()[0]
        cur.execute("""SELECT count(*) FROM mirror_circuit_functions cf
                       WHERE cf.mirror_status NOT IN ('human_rejected','superseded','promoted_to_final')
                       AND cf.review_status <> 'rejected'
                       AND cf.promotion_status NOT IN ('failed','promoted')""")
        new_candidates = cur.fetchone()[0]
        print(f"old_circuit_function_triple_candidates (from function_association)={old_candidates}")
        print(f"new_circuit_function_triple_candidates (from mirror_circuit_functions)={new_candidates}")


if __name__ == "__main__":
    main()
