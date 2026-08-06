"""Import generated UBERON alignment candidates into the review table."""

from __future__ import annotations

import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.database import AsyncSessionLocal
from app.models.ontology import OntologyAlignmentCandidate

DATA_JSON = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "region_alignment_candidates.json",
)


async def main() -> None:
    with open(DATA_JSON, encoding="utf-8") as f:
        report = json.load(f)
    rows = []
    for item in report["items"]:
        iri = item.get("uberon_iri")
        if not iri:
            continue
        rows.append(
            {
                "target_type": "region",
                "target_id": item["region_id"],
                "external_system": "UBERON",
                "external_id": iri.rstrip("/").split("/")[-1],
                "external_iri": iri,
                "external_label": item.get("uberon_label"),
                "match_type": item["match_type"],
                "match_score": item["confidence"],
                "match_details": {},
                "status": "pending",
            }
        )
    async with AsyncSessionLocal() as session:
        if rows:
            await session.execute(
                pg_insert(OntologyAlignmentCandidate)
                .values(rows)
                .on_conflict_do_nothing(
                    constraint="uq_ontology_alignment_candidate"
                )
            )
            await session.commit()
    print(f"imported {len(rows)} alignment candidates")


if __name__ == "__main__":
    asyncio.run(main())
