"""P1.4: materialize mirror_circuit_functions relations for legacy circuits
that only carry mirror_region_circuits.function_association text.

Idempotent — create_circuit_function dedups by (circuit_id, term_id, domain,
role, effect_type). Skips circuits that already have at least one relation.

Usage:
    python scripts/backfill_circuit_function_relations_p14.py [--batch-size 500]
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.mirror_kg import MirrorRegionCircuit
from app.models.mirror_macro_clinical import MirrorCircuitFunction
from app.services import mirror_macro_clinical_service


async def run() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-size", type=int, default=500)
    args = parser.parse_args()

    total_synced = 0
    total_skipped = 0
    total_processed = 0
    while True:
        async with AsyncSessionLocal() as session:
            rows = (
                await session.execute(
                    select(MirrorRegionCircuit)
                    .where(
                        MirrorRegionCircuit.function_association.isnot(None),
                        MirrorRegionCircuit.function_association != "",
                        ~MirrorRegionCircuit.id.in_(
                            select(MirrorCircuitFunction.circuit_id).distinct()
                        ),
                    )
                    .order_by(MirrorRegionCircuit.id)
                    .limit(args.batch_size)
                )
            ).scalars().all()
            if not rows:
                break
            for circuit in rows:
                await mirror_macro_clinical_service.sync_circuit_function_from_association(
                    session,
                    circuit=circuit,
                    function_association=circuit.function_association,
                    created_by="backfill:p1.4",
                )
                total_processed += 1
            await session.commit()
            total_synced += len(rows)
            print(f"processed batch of {len(rows)} (cumulative {total_processed})")

    print(f"done: circuits_with_association_synced={total_processed} (skipped_if_existing_relation)")


if __name__ == "__main__":
    asyncio.run(run())
