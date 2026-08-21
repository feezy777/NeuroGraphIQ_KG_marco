"""P1.7 dry-run: eligibility statistics for the three Mirror Function tables.

Read-only. Reports total / term-status distribution / review & promotion
status, so the governance gate (Final accepts only canonical active terms)
is visible before any promotion run.

Usage:
    python scripts/promotion_function_dryrun_p17.py
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


def report(cur, table: str) -> None:
    cur.execute(f"SELECT count(*) FROM {table}")
    total = cur.fetchone()[0]
    print(f"\n[{table}] total={total}")

    cur.execute(f"""SELECT ot.status, count(*) FROM {table} r
                    LEFT JOIN ontology_terms ot ON ot.id = r.term_id GROUP BY 1 ORDER BY 2 DESC""")
    print("  term status:")
    for status, c in cur.fetchall():
        print(f"    {status or 'NO_TERM'}: {c}")

    cur.execute(f"""SELECT mirror_status, review_status, count(*) FROM {table}
                    GROUP BY 1, 2 ORDER BY 3 DESC LIMIT 8""")
    print("  mirror x review status:")
    for ms, rs, c in cur.fetchall():
        print(f"    {ms} / {rs}: {c}")

    cur.execute(f"""SELECT count(*) FROM {table}
                    WHERE mirror_status='human_approved' AND review_status='approved'
                      AND promotion_status='not_promoted'""")
    print("  fully approved & not promoted (eligible-before-term-check):", cur.fetchone()[0])

    cur.execute(f"""SELECT count(*) FROM {table} r JOIN ontology_terms ot ON ot.id = r.term_id
                    WHERE ot.status='active' AND r.mirror_status='human_approved'
                      AND r.review_status='approved' AND r.promotion_status='not_promoted'""")
    print("  + active canonical term (fully eligible):", cur.fetchone()[0])


def main() -> None:
    with psycopg.connect(_url) as conn:
        cur = conn.cursor()
        for table in ("mirror_region_functions", "mirror_projection_functions", "mirror_circuit_functions"):
            report(cur, table)


if __name__ == "__main__":
    main()
