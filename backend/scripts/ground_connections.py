"""CN1 connection canonical grounding runner.

Builds the Mirror Connection → Canonical Connection grounding table in
batches (500–1000, idempotent) and exports a JSON report. Never modifies
mirror_region_connections; no roll-up / inference / promotion.

Usage:
    python -m scripts.ground_connections [--batch-size 500] [--dry-run] [--analyze-only]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

_backend = Path(__file__).resolve().parent.parent
if str(_backend) not in sys.path:
    sys.path.insert(0, str(_backend))

from app.database import AsyncSessionLocal
from app.services.connection_grounding_service import (
    DEFAULT_BATCH_SIZE,
    analyze_mirror_connection_data,
    build_connection_grounding,
    grounding_stats,
    unresolved_report,
)


def _fmt(d: dict, indent: int = 0) -> str:
    pad = " " * indent
    lines = []
    for k, v in d.items():
        if isinstance(v, dict):
            lines.append(f"{pad}{k}:")
            lines.append(_fmt(v, indent + 2))
        else:
            lines.append(f"{pad}{k}: {v}")
    return "\n".join(lines)


async def main(*, batch_size: int, dry_run: bool, analyze_only: bool) -> None:
    async with AsyncSessionLocal() as session:
        print("=" * 60)
        print("CN1 analysis — mirror connection data")
        print("=" * 60)
        analysis = await analyze_mirror_connection_data(session)
        print(_fmt(analysis))
        if analyze_only:
            return

        print("\n" + "=" * 60)
        print("CN1 grounding build" + (" (DRY RUN — nothing written)" if dry_run else ""))
        print("=" * 60)
        result = await build_connection_grounding(
            session, batch_size=batch_size, dry_run=dry_run,
            created_by="cn1_connection_grounding",
        )
        print(_fmt(result))

        if not dry_run:
            print("\n" + "=" * 60)
            print("Grounding stats")
            print("=" * 60)
            print(_fmt(await grounding_stats(session)))
            print("\nUnresolved sample:")
            print(_fmt(await unresolved_report(session, limit=10)))

    out = Path(_backend) / "data" / "exports" / "connection_grounding"
    out.mkdir(parents=True, exist_ok=True)
    report = out / ("grounding_report.json" if not dry_run else "grounding_report_dry.json")
    report.write_text(
        json.dumps(
            {"analysis": analysis, "grounding": result},
            indent=2, default=str, ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(f"\nreport → {report}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CN1 connection canonical grounding")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE,
                        help=f"rows per batch ({DEFAULT_BATCH_SIZE}–1000)")
    parser.add_argument("--dry-run", action="store_true", help="predict only — write nothing")
    parser.add_argument("--analyze-only", action="store_true", help="run analysis only, no build")
    args = parser.parse_args()

    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except Exception:
        pass
    asyncio.run(main(batch_size=args.batch_size, dry_run=args.dry_run, analyze_only=args.analyze_only))
