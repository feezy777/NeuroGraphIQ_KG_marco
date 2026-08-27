"""FN1 promote preview runner (read-only, no writes).

Runs the full promotion preview pipeline for a candidate version + tier
and prints the recommended promotion count. Never writes to
ontology_term_relations.

Usage:
    python -m scripts.preview_hierarchy_promotion [--version v2] [--tier high_confidence] [--json]
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
from app.services.hierarchy_promotion_service import (
    DEFAULT_TIER,
    DEFAULT_VERSION,
    preview_promotion,
    preview_summary_text,
)


async def main(*, candidate_version: str, tier: str, as_json: bool) -> None:
    async with AsyncSessionLocal() as session:
        result = await preview_promotion(
            session,
            candidate_version=candidate_version,
            tier=tier,
        )
    if as_json:
        print(json.dumps(result, indent=2, default=str, ensure_ascii=False))
    else:
        print(preview_summary_text(result))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FN1 promote preview (read-only)")
    parser.add_argument("--version", default=DEFAULT_VERSION, help="candidate generation version")
    parser.add_argument("--tier", default=DEFAULT_TIER, help="quality tier to preview")
    parser.add_argument("--json", action="store_true", help="dump full JSON result")
    args = parser.parse_args()

    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except Exception:
        pass
    asyncio.run(main(candidate_version=args.version, tier=args.tier, as_json=args.json))
