"""Activate curated ontology seed terms + synonyms (human-batch approved).

Reads backend/data/ontology_seed_candidates.json, activates the top-N
canonical terms (default 2872 = 95% record coverage) as `active` and the
rest as `proposed`, then inserts synonym rows. Idempotent.

Usage:
    python scripts/activate_ontology_seed.py [--top 2872]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.database import AsyncSessionLocal
from app.models.ontology import OntologyTerm, OntologyTermSynonym
from app.services.ontology_service import _term_code, normalize_term_key

DATA_JSON = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "ontology_seed_candidates.json",
)


async def main(top_n: int) -> None:
    with open(DATA_JSON, encoding="utf-8") as f:
        report = json.load(f)
    total_by_canon = {c["canonical"]: c["total"] for c in report["synonym_clusters"]}
    variants_by_canon = {c["canonical"]: c["variants"] for c in report["synonym_clusters"]}
    items = [
        (t["term"], total_by_canon.get(t["term"], t["count"]))
        for t in report["canonical_terms"]
    ]
    items.sort(key=lambda x: x[1], reverse=True)
    active_terms = [term for term, _ in items[:top_n]]
    proposed_terms = [term for term, _ in items[top_n:]]

    async with AsyncSessionLocal() as session:
        term_rows = [
            dict(
                term_code=_term_code(term, "function"),
                canonical_term_en=term,
                status="active",
                created_by="manual",
            )
            for term in active_terms
        ]
        term_rows += [
            dict(
                term_code=_term_code(term, "function"),
                canonical_term_en=term,
                status="proposed",
                created_by="system",
            )
            for term in proposed_terms
        ]
        if term_rows:
            await session.execute(
                pg_insert(OntologyTerm)
                .values(term_rows)
                .on_conflict_do_nothing(index_elements=["term_code"])
            )
            await session.commit()

        terms = (await session.execute(select(OntologyTerm))).scalars().all()
        by_canon = {t.canonical_term_en: t for t in terms}

        synonym_rows = []
        for canonical in active_terms:
            term = by_canon.get(canonical)
            if term is None:
                continue
            for variant in variants_by_canon.get(canonical, []):
                raw = variant["term"]
                if raw.replace("_", " ") == canonical:
                    continue
                if normalize_term_key(raw) == normalize_term_key(canonical):
                    continue
                synonym_rows.append(
                    dict(
                        term_id=term.id,
                        synonym_text=raw,
                        lang="en",
                        match_type="synonym",
                        confidence=1.0,
                        status="active",
                    )
                )
        if synonym_rows:
            await session.execute(
                pg_insert(OntologyTermSynonym)
                .values(synonym_rows)
                .on_conflict_do_nothing(constraint="uq_ontology_synonym")
            )
            await session.commit()

    covered = sum(c for _, c in items[:top_n])
    total_records = sum(c for _, c in items)
    print(
        f"active_terms={len(active_terms)} proposed_terms={len(proposed_terms)} "
        f"synonyms={len(synonym_rows)} coverage={covered / total_records:.1%}"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--top", type=int, default=2872)
    args = parser.parse_args()
    asyncio.run(main(args.top))
