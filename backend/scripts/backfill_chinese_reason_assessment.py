# -*- coding: utf-8 -*-
"""历史数据回填:模型理由(reason)与模型判断(assessment)中文化。

扫描四类纯英文文本(不含中文字符)并批量翻译回填:
  1. mirror_evidence_records.model_assessment
  2. mirror_evidence_passages.reason
  3. paper_evidence_task_items.passages_json -> passages[].reason
  4. paper_evidence_task_items.model_assessment(任务页「模型判断」)

幂等:仅处理不含 CJK 的记录;passage 原文不翻译;重复运行安全。

用法: cd backend && ./.venv/Scripts/python.exe scripts/backfill_chinese_reason_assessment.py
"""

import asyncio
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text  # noqa: E402

from app.database import AsyncSessionLocal  # noqa: E402
from app.services.paper_evidence_service import translate_texts  # noqa: E402

_CJK_RE = re.compile(r"[一-鿿]")
BATCH = 20


def is_english_only(s: str | None) -> bool:
    return bool(s and s.strip() and not _CJK_RE.search(s))


async def main() -> None:
    async with AsyncSessionLocal() as s:
        # ── 1. mirror_evidence_records.model_assessment ────────────────────
        rows = (
            await s.execute(
                text(
                    "SELECT id::text, model_assessment FROM mirror_evidence_records "
                    "WHERE model_assessment IS NOT NULL"
                )
            )
        ).all()
        targets = [(r[0], r[1]) for r in rows if is_english_only(r[1])]
        print(f"[1] mirror_evidence_records: {len(rows)} 总,{len(targets)} 条英文 assessment")
        for i in range(0, len(targets), BATCH):
            chunk = targets[i : i + BATCH]
            zh = (await translate_texts([t[1] for t in chunk]))["translations"]
            for (rid, _orig), t in zip(chunk, zh):
                if not t:
                    continue
                await s.execute(
                    text("UPDATE mirror_evidence_records SET model_assessment=:t WHERE id::text=:rid"),
                    {"t": t, "rid": rid},
                )
            await s.commit()

        # ── 2. mirror_evidence_passages.reason ──────────────────────────────
        rows = (
            await s.execute(
                text(
                    "SELECT id::text, reason FROM mirror_evidence_passages "
                    "WHERE reason IS NOT NULL"
                )
            )
        ).all()
        targets = [(r[0], r[1]) for r in rows if is_english_only(r[1])]
        print(f"[2] mirror_evidence_passages: {len(rows)} 总,{len(targets)} 条英文 reason")
        for i in range(0, len(targets), BATCH):
            chunk = targets[i : i + BATCH]
            zh = (await translate_texts([t[1] for t in chunk]))["translations"]
            for (pid, _orig), t in zip(chunk, zh):
                if not t:
                    continue
                await s.execute(
                    text("UPDATE mirror_evidence_passages SET reason=:t WHERE id::text=:pid"),
                    {"t": t, "pid": pid},
                )
            await s.commit()

        # ── 3. paper_evidence_task_items.passages_json -> passages[].reason ─
        rows = (
            await s.execute(
                text(
                    "SELECT id::text, passages_json FROM paper_evidence_task_items "
                    "WHERE passages_json IS NOT NULL"
                )
            )
        ).all()
        fixed_items = 0
        for (iid, pj) in rows:
            try:
                data = json.loads(pj) if isinstance(pj, str) else pj
            except (ValueError, json.JSONDecodeError):
                continue
            passages = data.get("passages") or []
            targets = [
                (i, p["reason"])
                for i, p in enumerate(passages)
                if is_english_only(p.get("reason"))
            ]
            if not targets:
                continue
            for i in range(0, len(targets), BATCH):
                chunk = targets[i : i + BATCH]
                zh = (await translate_texts([t[1] for t in chunk]))["translations"]
                for (pidx, _orig), t in zip(chunk, zh):
                    if t:
                        passages[pidx]["reason"] = t
            await s.execute(
                text(
                    "UPDATE paper_evidence_task_items SET passages_json=CAST(:pj AS jsonb) "
                    "WHERE id::text=:iid"
                ),
                {"pj": json.dumps(data, ensure_ascii=False), "iid": iid},
            )
            fixed_items += 1
            await s.commit()
        print(f"[3] paper_evidence_task_items.passages_json: {fixed_items} 条已回填")

        # ── 4. paper_evidence_task_items.model_assessment(任务页「模型判断」)──
        rows = (
            await s.execute(
                text(
                    "SELECT id::text, model_assessment FROM paper_evidence_task_items "
                    "WHERE model_assessment IS NOT NULL"
                )
            )
        ).all()
        targets = [(r[0], r[1]) for r in rows if is_english_only(r[1])]
        print(f"[4] paper_evidence_task_items.model_assessment: {len(rows)} 总,{len(targets)} 条英文")
        for i in range(0, len(targets), BATCH):
            chunk = targets[i : i + BATCH]
            zh = (await translate_texts([t[1] for t in chunk]))["translations"]
            for (iid, _orig), t in zip(chunk, zh):
                if not t:
                    continue
                await s.execute(
                    text("UPDATE paper_evidence_task_items SET model_assessment=:t WHERE id::text=:iid"),
                    {"t": t, "iid": iid},
                )
            await s.commit()

    print("done")


if __name__ == "__main__":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
