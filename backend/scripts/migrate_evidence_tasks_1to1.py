"""一次性存量迁移:多对象佐证任务 → 一对一对象任务(幂等,可重复执行)。

用法: backend/.venv/Scripts/python.exe backend/scripts/migrate_evidence_tasks_1to1.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import AsyncSessionLocal  # noqa: E402
from app.services import paper_evidence_service as pes  # noqa: E402


async def main() -> None:
    if AsyncSessionLocal is None:
        print("AsyncSessionLocal 未初始化(数据库未配置),退出。")
        return
    async with AsyncSessionLocal() as session:
        stats = await pes.migrate_tasks_to_1to1(session)
    print("迁移完成:", stats)


if __name__ == "__main__":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
