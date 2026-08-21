"""Full molecular-granularity projection function extraction (concurrent batch).

Extracts mirror_projection_functions for every molecular_attr connection that
does not already have functions, using deepseek-v4-flash in concurrent chunks.
Each chunk commits independently; run it in the background and watch the log.
"""

from __future__ import annotations

import asyncio
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import func, select

from app.database import AsyncSessionLocal
from app.models.mirror_kg import MirrorRegionConnection
from app.models.mirror_macro_clinical import MirrorProjectionFunction
from app.services.llm_projection_function_extraction_service import (
    run_projection_function_extraction_batch,
)

logger = logging.getLogger("molecular_fn_extract")

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        stream=sys.stdout,
        force=True,
    )


async def main() -> None:
    if AsyncSessionLocal is None:
        logger.error("AsyncSessionLocal unavailable")
        return

    async with AsyncSessionLocal() as s:
        total = int(
            (
                await s.execute(
                    select(func.count())
                    .select_from(MirrorRegionConnection)
                    .where(MirrorRegionConnection.granularity_level == "molecular_attr")
                )
            ).scalar_one()
        )
        ids = list(
            (
                await s.execute(
                    select(MirrorRegionConnection.id).where(
                        MirrorRegionConnection.granularity_level == "molecular_attr"
                    )
                )
            )
            .scalars()
            .all()
        )
        existing_rows = (
            await s.execute(select(MirrorProjectionFunction.projection_id))
        ).scalars().all()

    existing_ids = set(existing_rows)
    pending = [pid for pid in ids if pid not in existing_ids]
    already_done = len(ids) - len(pending)
    logger.info(
        "molecular connections total=%s already_have_functions=%s pending=%s",
        total,
        already_done,
        len(pending),
    )
    if not pending:
        logger.info("nothing to extract; all molecular connections already have functions")
        return

    started = time.monotonic()
    summary = await run_projection_function_extraction_batch(
        projection_ids=pending,
        provider_name="deepseek",
        model_name="deepseek-v4-flash",
        projections_per_pack=50,
        concurrency=4,
        temperature=0.2,
        max_tokens=12000,
        include_circuit_context=True,
        include_region_context=True,
        create_mirror_records=True,
        create_triples=True,
        create_evidence=True,
    )
    elapsed_min = round((time.monotonic() - started) / 60, 1)
    logger.info(
        "batch done in %s min: requested=%s chunks=%s created=%s skipped_dup=%s "
        "skipped_existing=%s triples=%s evidence=%s failed_chunks=%s errors=%s",
        elapsed_min,
        summary["requested_projection_count"],
        summary["chunk_count"],
        summary["created_count"],
        summary["skipped_duplicate_count"],
        summary["skipped_existing_count"],
        summary["triple_created_count"],
        summary["evidence_created_count"],
        summary["failed_chunk_count"],
        len(summary["errors"]),
    )
    for err in summary["errors"][:20]:
        logger.error("chunk error: %s", err)


if __name__ == "__main__":
    _configure_logging()
    asyncio.run(main())
