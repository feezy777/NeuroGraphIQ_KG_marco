"""P1.5: Function Triple entity-ization rebuild (desired-set diff & apply).

Idempotent — the second run must report insert=0 / changes=0.

Usage:
    python scripts/rebuild_function_triples_p15.py [--apply] [--version function_entity_v1]
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
from app.services.function_triple_rebuild_service import (
    PROJECTION_VERSION,
    rebuild_function_triples,
)


def _fmt(s) -> str:
    return (
        f"existing_function_triples={s.existing_function_triples} "
        f"desired_function_triples={s.desired_function_triples} "
        f"multi_source_spo={s.multi_source_spo_count} "
        f"upgraded={s.upgraded_count} inserted={s.inserted_count} "
        f"stale_deleted={s.stale_deleted_count} stale_superseded={s.stale_superseded_count} "
        f"filtered_invalid={s.filtered_invalid_count}"
    )


async def run() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="apply changes (default: dry-run)")
    parser.add_argument("--version", default=PROJECTION_VERSION)
    args = parser.parse_args()

    async with AsyncSessionLocal() as session:
        stats = await rebuild_function_triples(
            session,
            dry_run=not args.apply,
            projection_version=args.version,
        )
        print(f"[{'apply' if args.apply else 'dry-run'}] {_fmt(stats)}")
        if stats.warnings:
            print(f"  warnings ({len(stats.warnings)}):")
            for w in stats.warnings[:15]:
                print(f"    - {w}")
            if len(stats.warnings) > 15:
                print(f"    ... and {len(stats.warnings) - 15} more")
        await session.commit()


if __name__ == "__main__":
    asyncio.run(run())
