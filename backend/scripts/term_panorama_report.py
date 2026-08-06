"""Term panorama report: distinct function terms + counts (read-only, no LLM).

Usage:
    python scripts/term_panorama_report.py [--target-type circuit_function|projection_function|region_function] [--limit 5000]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from sqlalchemy import text

from app.database import AsyncSessionLocal


async def fetch_panorama(target_type: str, limit: int) -> dict:
    column = {
        "circuit_function": "function_term_en",
        "projection_function": "function_term",
        "region_function": "function_term",
    }.get(target_type)
    if column is None:
        raise SystemExit(f"unsupported target_type: {target_type}")
    sql = text(
        f"""
        SELECT lower(trim({column})) AS term_key,
               COUNT(*) AS cnt
        FROM mirror_{'circuit' if target_type == 'circuit_function' else 'projection' if target_type == 'projection_function' else 'region'}_functions
        WHERE {column} IS NOT NULL AND trim({column}) <> ''
        GROUP BY lower(trim({column}))
        ORDER BY cnt DESC
        LIMIT :limit
        """
    )
    async with AsyncSessionLocal() as session:
        rows = (await session.execute(sql, {"limit": limit})).all()
    return {
        "target_type": target_type,
        "total_distinct": len(rows),
        "items": [{"term_key": r[0], "count": r[1]} for r in rows],
    }


def render_markdown(report: dict) -> str:
    lines = [
        f"# 术语全景报告：{report['target_type']}",
        "",
        f"去重术语数（限 `limit`）：**{report['total_distinct']}**",
        "",
        "| 排名 | 术语（小写） | 出现次数 |",
        "|---|---|---|",
    ]
    for idx, item in enumerate(report["items"], start=1):
        lines.append(f"| {idx} | `{item['term_key']}` | {item['count']} |")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target-type", default="projection_function")
    parser.add_argument("--limit", type=int, default=5000)
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    args = parser.parse_args()
    report = asyncio.run(fetch_panorama(args.target_type, args.limit))
    if args.format == "markdown":
        print(render_markdown(report))
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
