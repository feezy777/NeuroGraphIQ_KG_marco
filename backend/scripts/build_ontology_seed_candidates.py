"""Build candidate canonical terms + synonym merge suggestions (pure rules, no LLM).

Reads distinct function terms from mirror tables, clusters near-identical
variants (token-order, singular/plural, known alias map), and writes:
  - backend/data/ontology_seed_candidates.json
  - backend/data/ontology_seed_review.md

Usage:
    python scripts/build_ontology_seed_candidates.py [--min-count 2]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from sqlalchemy import text

from app.database import AsyncSessionLocal

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")

TARGET_COLUMNS = {
    "projection_function": "mirror_projection_functions.function_term",
    "circuit_function": "mirror_circuit_functions.function_term_en",
    "region_function": "mirror_region_functions.function_term",
}

FULL_TERM_ALIASES = {
    "unknown": "unknown",
    "unknown function": "unknown",
    "unknown functional association": "unknown",
    "unknown association": "unknown",
    "not specified": "unknown",
    "n/a": "unknown",
    "na": "unknown",
}

TOKEN_ALIASES = {
    "emotional": "emotion",
    "modulational": "modulation",
}


def _singularize(token: str) -> str:
    if len(token) <= 4:
        return token
    if token.endswith("ies") and len(token) > 4:
        return token[:-3] + "y"
    if token.endswith("s") and not token.endswith("ss"):
        return token[:-1]
    return token


def canonical_key(term: str) -> str:
    raw = (term or "").lower().strip()
    if raw in FULL_TERM_ALIASES:
        return FULL_TERM_ALIASES[raw]
    tokens = [TOKEN_ALIASES.get(t, _singularize(t)) for t in re.findall(r"[a-z0-9]+", raw)]
    if not tokens:
        return ""
    return " ".join(sorted(tokens))


def _surface_penalty(term: str) -> int:
    """Prefer clean space-separated forms over underscore/hyphen variants."""
    return term.count("_") * 10 + term.count("-")


async def load_terms() -> dict[str, Counter]:
    """Return per-target-type Counter of lower(trim(column))."""
    result: dict[str, Counter] = {}
    async with AsyncSessionLocal() as session:
        for target_type, column in TARGET_COLUMNS.items():
            table = column.split(".")[0]
            sql = text(
                f"SELECT lower(trim({column.split('.')[1]})) AS term_key, COUNT(*) AS cnt "
                f"FROM {table} "
                f"WHERE {column.split('.')[1]} IS NOT NULL AND trim({column.split('.')[1]}) <> '' "
                f"GROUP BY 1"
            )
            rows = (await session.execute(sql)).all()
            result[target_type] = Counter({r[0]: r[1] for r in rows})
    return result


def build_candidates(per_type: dict[str, Counter], min_count: int = 2) -> dict:
    # Merge counts across types.
    total_counter: Counter = Counter()
    source_map: dict[str, set[str]] = defaultdict(set)
    for target_type, counter in per_type.items():
        for term, count in counter.items():
            total_counter[term] += count
            source_map[term].add(target_type)

    clusters: dict[str, list[tuple[str, int]]] = defaultdict(list)
    for term, count in total_counter.items():
        key = canonical_key(term)
        if key:
            clusters[key].append((term, count))

    canonical_terms: list[dict] = []
    synonym_clusters: list[dict] = []
    covered_records = 0
    for key, members in clusters.items():
        members.sort(key=lambda x: (-x[1], _surface_penalty(x[0]), x[0]))
        raw_canonical, canonical_count = members[0]
        canonical_term = raw_canonical.replace("_", " ")
        canonical_terms.append(
            {
                "key": key,
                "term": canonical_term,
                "count": canonical_count,
                "source_types": sorted(source_map[raw_canonical]),
            }
        )
        covered_records += sum(c for _, c in members)
        if len(members) > 1:
            synonym_clusters.append(
                {
                    "canonical": canonical_term,
                    "total": sum(c for _, c in members),
                    "variants": [{"term": t, "count": c} for t, c in members],
                }
            )

    canonical_terms.sort(key=lambda x: x["count"], reverse=True)
    synonym_clusters.sort(key=lambda x: x["total"], reverse=True)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "stats": {
            "total_distinct_terms": len(total_counter),
            "clusters": len(clusters),
            "canonical_candidates": len(canonical_terms),
            "synonym_clusters": len(synonym_clusters),
            "covered_records": covered_records,
            "min_count_used": min_count,
        },
        "canonical_terms": canonical_terms,
        "synonym_clusters": synonym_clusters,
    }


def render_markdown(report: dict) -> str:
    stats = report["stats"]
    lines = [
        "# 本体种子候选：canonical 词表 + 同义词合并建议",
        "",
        f"> 生成时间：{report['generated_at']}（纯规则，无 LLM）",
        "",
        "## 统计",
        "",
        f"- 去重术语总数：**{stats['total_distinct_terms']}**",
        f"- 聚类后 canonical 候选：**{stats['canonical_candidates']}**",
        f"- 同义词簇（需要合并的变体组）：**{stats['synonym_clusters']}**",
        f"- 覆盖记录数：**{stats['covered_records']}**",
        "",
        "## 同义词合并建议（按覆盖量排序，Top 60）",
        "",
        "| canonical（建议保留） | 变体（建议归入同义词） | 覆盖量 |",
        "|---|---|---|",
    ]
    for cluster in report["synonym_clusters"][:60]:
        variants = ", ".join(f"`{v['term']}`({v['count']})" for v in cluster["variants"][1:])
        lines.append(f"| `{cluster['canonical']}` | {variants} | {cluster['total']} |")
    lines += ["", "## 高频 canonical 候选（Top 100）", "", "| 排名 | canonical | 覆盖量 | 来源 |", "|---|---|---|---|"]
    for idx, item in enumerate(report["canonical_terms"][:100], start=1):
        lines.append(
            f"| {idx} | `{item['term']}` | {item['count']} | {', '.join(item['source_types'])} |"
        )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--min-count", type=int, default=2)
    args = parser.parse_args()
    os.makedirs(DATA_DIR, exist_ok=True)
    per_type = asyncio.run(load_terms())
    report = build_candidates(per_type, min_count=args.min_count)
    json_path = os.path.join(DATA_DIR, "ontology_seed_candidates.json")
    md_path = os.path.join(DATA_DIR, "ontology_seed_review.md")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(render_markdown(report))
    print(f"stats={json.dumps(report['stats'], ensure_ascii=False)}")
    print(f"written: {json_path}")
    print(f"written: {md_path}")


if __name__ == "__main__":
    main()
