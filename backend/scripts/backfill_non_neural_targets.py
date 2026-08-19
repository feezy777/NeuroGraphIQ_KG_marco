"""一次性/可复用回填:为存量佐证任务标记非神经靶标(结构性不存在)。

治理分类只在「新建任务」时生效(T2 创建时判定);本脚本对存量任务补标记:
- 对所有 connection/projection 任务,JOIN 镜像行取靶标名 → classify_target;
- non_neural → item.preprocess_outcome='non_neural_target'(幂等:已标记的跳过)。
- 只改佐证侧 item,不动镜像数据。

用法: backend/.venv/Scripts/python.exe backend/scripts/backfill_non_neural_targets.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text  # noqa: E402

from app.database import AsyncSessionLocal  # noqa: E402
from app.services.evidence_target_classifier import classify_target  # noqa: E402


async def main() -> None:
    if AsyncSessionLocal is None:
        print("AsyncSessionLocal 未初始化,退出。")
        return
    async with AsyncSessionLocal() as s:
        rows = (
            await s.execute(
                text(
                    "SELECT t.id::text, m.target_region_name_cn, m.target_region_name_en "
                    "FROM paper_evidence_tasks t "
                    "JOIN mirror_region_connections m ON m.id = t.target_id "
                    "WHERE t.target_type IN ('connection','projection') AND t.status <> 'cancelled'"
                )
            )
        ).all()
        doomed = [
            tid
            for tid, tgt_cn, tgt_en in rows
            if classify_target(tgt_cn, tgt_en) == "non_neural"
        ]
        if doomed:
            await s.execute(
                text(
                    "UPDATE paper_evidence_task_items i "
                    "SET preprocess_outcome = 'non_neural_target', updated_at = now() "
                    "FROM paper_evidence_tasks t "
                    "WHERE t.id = i.task_id AND t.id::text = ANY(:ids) "
                    "AND i.preprocess_outcome IS DISTINCT FROM 'non_neural_target'"
                ),
                {"ids": doomed},
            )
            await s.commit()
        print(f"scanned {len(rows)} tasks; marked {len(doomed)} non-neural target tasks")


if __name__ == "__main__":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
