"""Apply BR3 multiscale migrations (idempotent) to the dev/e2e database.

Usage (from backend/):
    .venv/Scripts/python.exe scripts/apply_multiscale_migrations.py [migration_file ...]

Windows note: psycopg3 async needs SelectorEventLoop — handled below.
"""

from __future__ import annotations

import asyncio
import selectors
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text

from app.database import AsyncSessionLocal

# 20260826/20260827: BR3 multiscale migrations must sort AFTER
# 20260822_canonical_brain_region.sql / 20260823_macro96_canonical_l2.sql
# (fresh installs apply migrations in filename order).
MIGRATIONS = [
    Path(__file__).resolve().parents[1] / "migrations" / "20260826_multiscale_granularity_refactor.sql",
    Path(__file__).resolve().parents[1] / "migrations" / "20260827_multiscale_atlas_layer.sql",
]


async def apply_one(session, path: Path) -> None:
    sql = path.read_text(encoding="utf-8")
    # psycopg3 executes the whole file as one multi-statement batch (idempotent SQL)
    await session.execute(text(sql))
    print(f"  applied: {path.name}")


async def main() -> None:
    targets = [Path(p) for p in sys.argv[1:]] or MIGRATIONS
    async with AsyncSessionLocal() as session:
        for path in targets:
            if not path.exists():
                print(f"  SKIP (missing): {path}")
                continue
            await apply_one(session, path)
            await session.commit()
    print("OK")


if __name__ == "__main__":
    asyncio.run(main(), loop_factory=lambda: asyncio.SelectorEventLoop(selectors.SelectSelector()))
