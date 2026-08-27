"""FN1 promote executor runner — batched writes into ontology_term_relations.

Writes quality-filtered subclass_of candidates (batch 500–1000, default
500). Each batch re-validates endpoints, duplicates, subclass_of semantics
and cycles before writing. Exports a JSON report to
data/exports/hierarchy_candidates/.

Usage:
    python -m scripts.promote_function_hierarchy [--batch-size 500] [--tier high_confidence] [--dry-run]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

# Ensure backend root is on sys.path for imports
_backend = Path(__file__).resolve().parent.parent
if str(_backend) not in sys.path:
    sys.path.insert(0, str(_backend))

from app.database import AsyncSessionLocal
from app.services.hierarchy_promotion_executor import (
    DEFAULT_BATCH_SIZE,
    DEFAULT_TIER,
    DEFAULT_VERSION,
    promote_candidates,
    promotion_summary_text,
)
from app.services.hierarchy_promotion_service import preview_promotion


async def main(*, batch_size: int, tier: str, dry_run: bool) -> None:
    async with AsyncSessionLocal() as session:
        if dry_run:
            result = await preview_promotion(
                session, candidate_version=DEFAULT_VERSION, tier=tier,
            )
            print("DRY RUN — nothing written\n")
            from app.services.hierarchy_promotion_service import preview_summary_text
            print(preview_summary_text(result))
            return

        result = await promote_candidates(
            session, candidate_version=DEFAULT_VERSION, tier=tier,
            batch_size=batch_size, created_by="function_hierarchy_promotion",
        )
    print(promotion_summary_text(result))

    out = Path(_backend) / "data" / "exports" / "hierarchy_candidates"
    out.mkdir(parents=True, exist_ok=True)
    report = out / "promotion_report.json"
    report.write_text(json.dumps(result, indent=2, default=str, ensure_ascii=False),
                      encoding="utf-8")
    print(f"\nreport → {report}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FN1 promote executor (batched)")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE,
                        help="edges per batch (500–1000)")
    parser.add_argument("--tier", default=DEFAULT_TIER, help="quality tier")
    parser.add_argument("--dry-run", action="store_true",
                        help="preview only — write nothing")
    args = parser.parse_args()

    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except Exception:
        pass
    asyncio.run(main(batch_size=args.batch_size, tier=args.tier, dry_run=args.dry_run))
