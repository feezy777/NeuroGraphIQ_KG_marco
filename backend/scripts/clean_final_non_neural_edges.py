"""一次性清理:final_kg 中靶标为非神经结构(脑室/脑脊液/脑膜/脉络丛)的连接。

靶标判定:优先 JOIN mirror_region_connections(source_mirror_connection_id)取 target_region 名;
镜像行缺失时回退 raw_payload_json 中的 target 名称字段(如 target_region_name_en/cn)。
仅删除 final 行,镜像数据保留(审计留痕)。

用法: backend/.venv/Scripts/python.exe backend/scripts/clean_final_non_neural_edges.py
"""

import asyncio
import json
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
                    "SELECT f.id, m.target_region_name_cn, m.target_region_name_en, f.raw_payload_json "
                    "FROM final_region_connections f "
                    "LEFT JOIN mirror_region_connections m ON m.id = f.source_mirror_connection_id"
                )
            )
        ).all()
        doomed: list[str] = []
        for rid, tgt_cn, tgt_en, raw in rows:
            if tgt_cn or tgt_en:
                kind = classify_target(tgt_cn, tgt_en)
            else:
                payload = raw or {}
                kind = classify_target(
                    payload.get("target_region_name_cn") or payload.get("target_name_cn"),
                    payload.get("target_region_name_en") or payload.get("target_name_en"),
                )
            if kind == "non_neural":
                doomed.append(str(rid))
        if doomed:
            await s.execute(
                text("DELETE FROM final_region_connections WHERE id::text = ANY(:ids)"),
                {"ids": doomed},
            )
            await s.commit()
        print(f"scanned {len(rows)} final connections; deleted {len(doomed)} non-neural-target edges")


if __name__ == "__main__":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
