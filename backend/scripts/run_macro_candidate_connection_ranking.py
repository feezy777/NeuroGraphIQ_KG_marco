"""Macro Candidate Connection Ranking V1 实施脚本。

paper_region_pair_candidates(17,609 行) → 按无向对聚合五因素评分 →
A/B/C 分级 → paper_connection_candidate_rankings 幂等落库 → 报告 3 份。

约束(用户要求):
* 不创建 canonical connection / 不修改 final_canonical_connections /
  不进入 validation/review/promotion —— 只生成 candidate ranking 数据
* 无 LLM / 无外部 API / 不导入新论文 —— 纯规则确定性计算

可追溯链断言:
  ranking → candidate_pair(paper_region_pair_candidates.id) →
  evidence_segment(paper_region_evidence_segments, title 源为 None) →
  paper_source(paper_sources.id)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

_backend = Path(__file__).resolve().parent.parent
if str(_backend) not in sys.path:
    sys.path.insert(0, str(_backend))

from psycopg.types.json import Jsonb
from sqlalchemy import text

from app.database import AsyncSessionLocal
from app.services.macro_candidate_connection_ranking_service import (
    GENERATION_METHOD,
    INSERT_RANKING_SQL,
    build_ranking_row,
)

OUT_DIR = Path(_backend) / "data" / "exports" / "macro_candidate_ranking"
MIGRATION = Path(_backend) / "migrations" / "20260917_paper_candidate_ranking.sql"

PAIRS_SQL = """\
SELECT id, paper_id, source_region_id, target_region_id,
       evidence_sentence, cooccurrence
FROM paper_region_pair_candidates ORDER BY paper_id"""

SEGMENTS_SQL = """\
SELECT id, paper_id, sentence_text, source_type
FROM paper_region_evidence_segments"""

PAPERS_SQL = "SELECT id, pmid FROM paper_sources ORDER BY id"

COUNTER_SQL = {
    "final_active": "SELECT count(*) FROM final_canonical_connections WHERE final_status='active'",
    "canonical": "SELECT count(*) FROM canonical_connections",
    "mirror_macro": "SELECT count(*) FROM mirror_region_connections WHERE granularity_level='macro'",
    "lineage": "SELECT count(*) FROM canonical_connection_lineage",
    "clusters": "SELECT count(*) FROM mirror_connection_clusters",
}
DISCOVERY_COUNT_SQL = {
    "mentions": "SELECT count(*) FROM paper_region_mentions",
    "pairs": "SELECT count(*) FROM paper_region_pair_candidates",
    "segments": "SELECT count(*) FROM paper_region_evidence_segments",
}


async def _counters(session) -> dict[str, int]:
    out = {}
    for name, sql in COUNTER_SQL.items():
        out[name] = (await session.execute(text(sql))).scalar()
    return out


async def apply_migration() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")
    async with AsyncSessionLocal() as session:
        for stmt in sql.split(";"):
            stmt = stmt.strip()
            if stmt:
                await session.execute(text(stmt))
        await session.commit()
    print(f"[ok] migration applied: {MIGRATION.name}")


def _pair_key(a: str, b: str) -> tuple[str, str]:
    return (a, b) if a <= b else (b, a)


async def main(_args: argparse.Namespace) -> None:
    # ---- 0. 迁移 + 基线 ----
    await apply_migration()
    async with AsyncSessionLocal() as session:
        counters_before = await _counters(session)
        disc_before = {n: (await session.execute(text(s))).scalar()
                       for n, s in DISCOVERY_COUNT_SQL.items()}
        papers_before = (await session.execute(
            text("SELECT count(*) FROM paper_sources"))).scalar()
        r0 = (await session.execute(text(
            "SELECT count(*) FROM paper_connection_candidate_rankings"))).scalar()
    print(f"baseline: {counters_before} | discovery={disc_before} "
          f"| papers={papers_before} | rankings_before={r0}")

    # ---- 1. 加载数据 ----
    async with AsyncSessionLocal() as session:
        pair_rows = [{
            "id": str(r[0]), "paper_id": str(r[1]),
            "source_region_id": str(r[2]), "target_region_id": str(r[3]),
            "evidence_sentence": r[4], "cooccurrence": r[5],
        } for r in (await session.execute(text(PAIRS_SQL))).all()]
        segments = [{
            "id": str(r[0]), "paper_id": str(r[1]),
            "sentence_text": r[2], "source_type": r[3],
        } for r in (await session.execute(text(SEGMENTS_SQL))).all()]
        papers = {str(r[0]): r[1] for r in
                  (await session.execute(text(PAPERS_SQL))).all()}
    print(f"pairs={len(pair_rows)} segments={len(segments)} papers={len(papers)}")

    # ---- 2. 聚合评分 ----
    from app.services.macro_candidate_connection_ranking_service import (
        link_evidence_segments,
    )
    seg_map = link_evidence_segments(pair_rows, segments)
    grouped: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in pair_rows:
        grouped[_pair_key(row["source_region_id"],
                          row["target_region_id"])].append(row)

    rankings = []
    for (src, tgt), rows in sorted(grouped.items()):
        rankings.append(build_ranking_row(src, tgt, rows, seg_map, papers))
    rankings.sort(key=lambda r: (-r["score"], -r["paper_count"],
                                 -r["evidence_count"]))
    print(f"rankings={len(rankings)} "
          f"(聚合自 {len(pair_rows)} 候选行)")

    # ---- 3. 幂等落库 ----
    def _jsonb_ready(row: dict, cols: tuple[str, ...]) -> dict:
        return {k: (Jsonb(v) if k in cols and v is not None else v)
                for k, v in row.items()}

    async with AsyncSessionLocal() as session:
        await session.execute(
            text(INSERT_RANKING_SQL),
            [_jsonb_ready(dict(r), ("candidate_pair_ids", "ranking_reason",
                                    "provenance_json")) for r in rankings])
        await session.commit()
    async with AsyncSessionLocal() as session:
        r1 = (await session.execute(text(
            "SELECT count(*) FROM paper_connection_candidate_rankings"))).scalar()
    print(f"inserted={len(rankings)} | db_rankings={r1}")

    # ---- 4. 断言:零副作用 + 可追溯链 ----
    async with AsyncSessionLocal() as session:
        counters_after = await _counters(session)
        disc_after = {n: (await session.execute(text(s))).scalar()
                      for n, s in DISCOVERY_COUNT_SQL.items()}
        papers_after = (await session.execute(
            text("SELECT count(*) FROM paper_sources"))).scalar()
        for name, before in counters_before.items():
            assert counters_after[name] == before, f"{name} 数量变化"
        assert disc_after == disc_before, "discovery 表数量变化"
        assert papers_after == papers_before, "paper_sources 数量变化"
    print("[ok] zero-side-effect: 5 治理 counters + 3 discovery 表 + "
          "paper_sources 全不变")

    pair_ids = {r["id"] for r in pair_rows}
    seg_ids = {s["id"] for s in segments}
    bad = 0
    for rank in rankings:
        for entry in rank["provenance_json"]["paper_entries"]:
            if entry["candidate_pair_id"] not in pair_ids:
                bad += 1
            if entry["source_type"] == "title":
                assert entry["evidence_segment_id"] is None
            else:
                assert entry["evidence_segment_id"] in seg_ids
    assert bad == 0, f"{bad} 条 ranking 溯源断裂"
    print(f"[ok] traceability: {len(rankings)} 条 ranking × {len(pair_ids)} "
          f"候选对全量可追溯 ranking→pair→segment→paper")

    # ---- 5. 报告 ----
    await _export_reports(rankings, pair_rows, seg_map, papers,
                          counters_before, disc_before, papers_before, r1)


async def _export_reports(rankings, pair_rows, seg_map, papers,
                          counters, disc_before, papers_before, r1) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()
    counts = Counter(r["priority_level"] for r in rankings)
    pair_by_id = {r["id"]: r for r in pair_rows}
    seg_by_id = {s["id"]: s for s in _all_segments(seg_map)}

    def _write(name: str, data) -> None:
        (OUT_DIR / name).write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"[ok] {name}")

    def _evidence_examples(rank: dict) -> list[dict]:
        out = []
        for entry in rank["provenance_json"]["paper_entries"][:2]:
            out.append({
                "pmid": entry["pmid"],
                "source_type": entry["source_type"],
                "cooccurrence": entry["cooccurrence"],
                "snippet": entry["evidence_sentence_snippet"],
            })
        return out

    # 1) ranking_summary.json
    _write("ranking_summary.json", {
        "analysis": "macro_candidate_connection_ranking_v1",
        "date": "2026-08-25",
        "inputs": {
            "candidate_pair_rows": len(pair_rows),
            "evidence_segments": len(seg_by_id),
            "paper_sources": papers_before,
        },
        "total_rankings": len(rankings),
        "priority_distribution": dict(counts),
        "governance": {
            "final_active_unchanged": counters["final_active"],
            "canonical_unchanged": counters["canonical"],
            "mirror_macro_unchanged": counters["mirror_macro"],
            "discovery_tables_unchanged": disc_before,
            "paper_sources_unchanged": papers_before,
            "rankings_inserted_this_run": len(rankings),
            "db_rankings_after": r1,
            "no_llm": True, "no_external_api": True,
            "no_connection_created": True,
            "idempotent": "INSERT ON CONFLICT (source,target) DO NOTHING",
        },
        "answers": {
            "q1_candidates_final_distribution": {
                "A": counts["A"], "B": counts["B"], "C": counts["C"],
                "total": len(rankings),
                "note": "ranking 行 = 唯一 region pair(跨论文聚合),"
                        "候选行 17,609 中重复 pair 已合并",
            },
            "q2_top100": f"见 top_100_candidates.json(按 score 降序)",
            "q3_per_candidate_support": (
                "paper_count = 支持论文数, evidence_count = 证据句数,"
                "每条 ranking 均含,分布见 priority_distribution.json"),
            "q4_recommended_llm_review_scale": {
                "A_level_all": counts["A"],
                "A_plus_top_B": counts["A"] + min(counts["B"], 100),
                "suggestion": (
                    f"建议下一阶段 LLM 审核规模: A 级 {counts['A']} 条全部进入;"
                    f"如需控制成本,可先取 Top "
                    f"{min(counts['A'] + counts['B'], 200)} 条"
                    f"(A 级 + B 级高分),约占总量 "
                    f"{min(counts['A'] + counts['B'], 200) * 100 // max(len(rankings), 1)}%"),
            },
        },
        "generated_at": now,
    })

    # 2) top_100_candidates.json
    top_rows = [{
        "rank": i + 1,
        "source_region_id": r["source_region_id"],
        "target_region_id": r["target_region_id"],
        "score": r["score"],
        "priority_level": r["priority_level"],
        "paper_count": r["paper_count"],
        "evidence_count": r["evidence_count"],
        "keyword_hits": r["ranking_reason"]["keyword_hits"],
        "top_evidence_examples": _evidence_examples(r),
    } for i, r in enumerate(rankings[:100])]
    _write("top_100_candidates.json", {
        "analysis": "macro_candidate_connection_ranking_v1",
        "record": "按 score 降序 Top 100 候选连接",
        "count": len(top_rows),
        "rows": top_rows,
        "generated_at": now,
    })

    # 3) priority_distribution.json
    per_level = {"A": [], "B": [], "C": []}
    for r in rankings:
        per_level[r["priority_level"]].append(r)
    dist = {}
    for level, rows in per_level.items():
        if not rows:
            dist[level] = {"count": 0}
            continue
        scores = sorted(r["score"] for r in rows)
        dist[level] = {
            "count": len(rows),
            "score_range": [scores[0], scores[-1]],
            "avg_paper_count": round(sum(r["paper_count"] for r in rows) /
                                     len(rows), 2),
            "avg_evidence_count": round(
                sum(r["evidence_count"] for r in rows) / len(rows), 2),
            "top_10": [{
                "source_region_id": r["source_region_id"],
                "target_region_id": r["target_region_id"],
                "score": r["score"],
                "paper_count": r["paper_count"],
                "evidence_count": r["evidence_count"],
            } for r in rows[:10]],
        }
    _write("priority_distribution.json", {
        "analysis": "macro_candidate_connection_ranking_v1",
        "priority_definition": {
            "A": "≥2 篇论文 + same_sentence 证据 + 连接关键词",
            "B": "中等(非 A 非 C)",
            "C": "单论文且无 same_sentence 无关键词(低价值共现)",
        },
        "score_formula": ("score = 2^(paper_count-1)[饱和32] × "
                          "evidence_source(fulltext1.0/abstract0.8/title0.5) "
                          "× proximity(sentence1.0/section0.7/paper0.4) "
                          "× (1+0.1×min(keywords,5))"),
        "distribution": dist,
        "generated_at": now,
    })


def _all_segments(seg_map) -> list[dict]:
    """seg_map 值去重(同键同段,值即 segment)。"""
    seen = {}
    for seg in seg_map.values():
        seen[seg["id"]] = seg
    return list(seen.values())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Macro Candidate Connection Ranking V1"
                    "(17,609 候选 → A/B/C 分级排序,幂等)")
    parser.parse_args()
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except Exception:
        pass
    asyncio.run(main(parser.parse_args()))
