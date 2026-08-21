"""P1.3: backfill canonical Function term_id on mirror function relation tables.

Processes rows whose term_id is NULL or points to a merged/deprecated / wrong
type term. Uses the unified resolver (function_term_service) with auto-propose;
never touches function text. Idempotent — safe to re-run.

Usage:
    python scripts/backfill_function_term_id.py [--target-type region_function|projection_function|circuit_function]
                                               [--batch-size 1000] [--max-batches N]
                                               [--stats-only] [--before-stats]
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from app.database import AsyncSessionLocal
from app.services.function_term_service import (
    backfill_function_grounding,
    count_function_grounding_states,
)

ALL_TYPES = ("region_function", "projection_function", "circuit_function")


def _fmt(stats: dict[str, int]) -> str:
    order = (
        "total", "grounded_active", "grounded_proposed", "merged_redirect",
        "unresolved", "ambiguous", "invalid_type", "merged_redirect_dup_superseded",
        "total_scanned", "rows_updated", "proposed_created", "dup_superseded",
    )
    return ", ".join(f"{k}={stats.get(k, 0)}" for k in order if k in stats)


async def run() -> None:
    parser = argparse.ArgumentParser(description="P1.3 function term_id backfill")
    parser.add_argument("--target-type", choices=ALL_TYPES + ("all",), default="all")
    parser.add_argument("--batch-size", type=int, default=1000)
    parser.add_argument("--max-batches", type=int, default=None)
    parser.add_argument("--stats-only", action="store_true")
    parser.add_argument("--before-stats", action="store_true")
    args = parser.parse_args()

    types = ALL_TYPES if args.target_type == "all" else (args.target_type,)

    if args.before_stats:
        async with AsyncSessionLocal() as session:
            for t in types:
                print(f"[before] {t}: {_fmt(await count_function_grounding_states(session, target_type=t))}")

    if not args.stats_only:
        for t in types:
            async with AsyncSessionLocal() as session:
                stats = await backfill_function_grounding(
                    session,
                    target_type=t,
                    batch_size=args.batch_size,
                    max_batches=args.max_batches,
                    created_by="backfill:p1.3",
                )
                print(f"[backfill] {t}: {_fmt(stats)}")

    async with AsyncSessionLocal() as session:
        for t in types:
            print(f"[after] {t}: {_fmt(await count_function_grounding_states(session, target_type=t))}")


if __name__ == "__main__":
    asyncio.run(run())
