"""Run deterministic grounding batches for all function target types."""

from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from app.database import AsyncSessionLocal
from app.services.ontology_service import run_deterministic_grounding_batch

TARGET_TYPES = ["projection_function", "circuit_function", "region_function"]
BATCH = 2000


async def run_type(target_type: str) -> dict:
    total = grounded = ungrounded = 0
    while True:
        async with AsyncSessionLocal() as session:
            result = await run_deterministic_grounding_batch(
                session, target_type, limit=BATCH
            )
            await session.commit()
        total += result["processed"]
        grounded += result["grounded"]
        ungrounded += result["ungrounded"]
        print(
            f"[{target_type}] processed={result['processed']} "
            f"grounded={result['grounded']} ungrounded={result['ungrounded']} "
            f"cumulative={total}",
            flush=True,
        )
        if result["processed"] == 0:
            break
    return {
        "target_type": target_type,
        "processed": total,
        "grounded": grounded,
        "ungrounded": ungrounded,
    }


async def main() -> None:
    results = []
    for target_type in TARGET_TYPES:
        results.append(await run_type(target_type))
    for result in results:
        print(
            f"RESULT {result['target_type']}: processed={result['processed']} "
            f"grounded={result['grounded']} ungrounded={result['ungrounded']}",
            flush=True,
        )


if __name__ == "__main__":
    asyncio.run(main())
