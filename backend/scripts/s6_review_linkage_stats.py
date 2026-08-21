# -*- coding: utf-8 -*-
"""S6 历史数据只读分类统计(只 SELECT,不 UPDATE/INSERT/DELETE)。

用法(backend 目录):
    .\\.venv\\Scripts\\python.exe scripts\\s6_review_linkage_stats.py
"""
from __future__ import annotations

import asyncio
import sys

asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
sys.path.insert(0, ".")

from sqlalchemy import text  # noqa: E402

from app.database import AsyncSessionLocal  # noqa: E402


async def main() -> None:
    async with AsyncSessionLocal() as s:
        print("=" * 72)
        print("paper_evidence_reviews 关联分类只读统计")
        print("=" * 72)

        total = (
            await s.execute(text("SELECT COUNT(*) FROM paper_evidence_reviews"))
        ).scalar_one()
        print(f"review 总数: {total}")

        linked = (
            await s.execute(
                text("SELECT COUNT(*) FROM paper_evidence_reviews WHERE task_item_id IS NOT NULL")
            )
        ).scalar_one()
        print(f"1) 已有 task_item_id 的 review(linked): {linked}")

        task_only = (
            await s.execute(
                text(
                    "SELECT COUNT(*) FROM paper_evidence_reviews "
                    "WHERE task_item_id IS NULL AND task_id IS NOT NULL"
                )
            )
        ).scalar_one()
        print(f"2) 只有 task_id 的 review(task-only/legacy): {task_only}")

        standalone = (
            await s.execute(
                text(
                    "SELECT COUNT(*) FROM paper_evidence_reviews "
                    "WHERE task_id IS NULL AND task_item_id IS NULL"
                )
            )
        ).scalar_one()
        print(f"3) 两者都为空的 review(standalone): {standalone}")

        # 4) 无关联(target 未挂任何任务)且 target 恰好匹配一个 task item
        unique_match = (
            await s.execute(
                text(
                    """
                    SELECT COUNT(*) FROM paper_evidence_reviews r
                    WHERE r.task_item_id IS NULL AND r.task_id IS NULL
                      AND (SELECT COUNT(*) FROM paper_evidence_task_items i
                           WHERE i.target_type = r.target_type AND i.target_id = r.target_id) = 1
                    """
                )
            )
        ).scalar_one()
        print(f"4) standalone 且 target 只匹配一个 task item(唯一匹配,可治理候选): {unique_match}")

        ambiguous = (
            await s.execute(
                text(
                    """
                    SELECT COUNT(*) FROM paper_evidence_reviews r
                    WHERE r.task_item_id IS NULL AND r.task_id IS NULL
                      AND (SELECT COUNT(*) FROM paper_evidence_task_items i
                           WHERE i.target_type = r.target_type AND i.target_id = r.target_id) > 1
                    """
                )
            )
        ).scalar_one()
        print(f"5) standalone 且 target 匹配多个 task item(歧义,禁止自动回填): {ambiguous}")

        mismatch = (
            await s.execute(
                text(
                    """
                    SELECT COUNT(*) FROM paper_evidence_reviews r
                    JOIN paper_evidence_task_items i ON i.id = r.task_item_id
                    WHERE i.target_type <> r.target_type OR i.target_id <> r.target_id
                    """
                )
            )
        ).scalar_one()
        print(f"6) review target 与关联 task item 不一致的异常数量: {mismatch}")

        orphan_item = (
            await s.execute(
                text(
                    """
                    SELECT COUNT(*) FROM paper_evidence_reviews r
                    WHERE r.task_item_id IS NOT NULL
                      AND NOT EXISTS (SELECT 1 FROM paper_evidence_task_items i WHERE i.id = r.task_item_id)
                    """
                )
            )
        ).scalar_one()
        print(f"   补充:task_item_id 指向不存在 item 的孤儿 review: {orphan_item}")

        orphan_task = (
            await s.execute(
                text(
                    """
                    SELECT COUNT(*) FROM paper_evidence_reviews r
                    WHERE r.task_id IS NOT NULL
                      AND NOT EXISTS (SELECT 1 FROM paper_evidence_tasks t WHERE t.id = r.task_id)
                    """
                )
            )
        ).scalar_one()
        print(f"   补充:task_id 指向不存在任务的孤儿 review: {orphan_task}")

        print("-" * 72)
        print("只读统计完成,未执行任何 UPDATE/INSERT/DELETE。")


asyncio.run(main())
