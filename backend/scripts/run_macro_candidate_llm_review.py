"""Macro Candidate Connection LLM Scientific Review V1 实施脚本。

Top 200 ranking(score 降序) → LLM evidence judge(deepseek) →
macro_candidate_connection_llm_reviews 幂等落库 → 报告 3 份。

流程: paper_candidate_ranking → LLM evidence judge → review results

约束(用户要求):
* 允许 LLM 调用 + 创建 candidate review 结果
* 禁止:创建 canonical connection / validation / promotion /
  Final KG 写入 / 修改已有连接 / 修改 ranking
* LLM 经 llm_providers/factory.py 抽象;保存 prompt+response+model+token
* 失败重试 + 幂等(已审核的 ranking 复跑跳过)
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
from app.services.macro_candidate_llm_review_service import (
    INSERT_REVIEW_SQL,
    review_candidates_batch,
)

OUT_DIR = Path(_backend) / "data" / "exports" / "macro_candidate_llm_review"
MIGRATION = Path(_backend) / "migrations" / "20260918_macro_candidate_llm_review.sql"
TOP_N = 200
PROVIDER = "deepseek"

RANKINGS_SQL = """\
SELECT r.id, r.source_region_id, r.target_region_id, r.paper_count,
       r.evidence_count, r.score, r.priority_level, r.candidate_pair_ids,
       r.provenance_json,
       rs.canonical_name_en AS source_name,
       rt.canonical_name_en AS target_name
FROM paper_connection_candidate_rankings r
JOIN canonical_brain_regions rs ON rs.id = r.source_region_id
JOIN canonical_brain_regions rt ON rt.id = r.target_region_id
ORDER BY r.score DESC, r.paper_count DESC
LIMIT :top_n"""

PAIRS_SQL = """\
SELECT id, paper_id, evidence_sentence, cooccurrence, section_name
FROM paper_region_pair_candidates
WHERE id = ANY(:ids)"""

PAPERS_SQL = "SELECT id, title, pmid FROM paper_sources WHERE id = ANY(:ids)"

COUNTER_SQL = {
    "final_active": "SELECT count(*) FROM final_canonical_connections WHERE final_status='active'",
    "canonical": "SELECT count(*) FROM canonical_connections",
    "mirror_macro": "SELECT count(*) FROM mirror_region_connections WHERE granularity_level='macro'",
    "rankings": "SELECT count(*) FROM paper_connection_candidate_rankings",
}


async def _counters(session) -> dict[str, int]:
    return {n: (await session.execute(text(s))).scalar()
            for n, s in COUNTER_SQL.items()}


async def apply_migration() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")
    async with AsyncSessionLocal() as session:
        for stmt in sql.split(";"):
            stmt = stmt.strip()
            if stmt:
                await session.execute(text(stmt))
        await session.commit()
    print(f"[ok] migration applied: {MIGRATION.name}")


async def load_top_rankings(session) -> list[dict]:
    rows = (await session.execute(
        text(RANKINGS_SQL).bindparams(top_n=TOP_N))).all()
    out = []
    for r in rows:
        out.append({
            "id": str(r[0]), "source_region_id": str(r[1]),
            "target_region_id": str(r[2]), "paper_count": r[3],
            "evidence_count": r[4], "score": float(r[5]),
            "priority_level": r[6],
            "candidate_pair_ids": [str(x) for x in (r[7] or [])],
            "source_name": r[9] or str(r[1]),
            "target_name": r[10] or str(r[2]),
        })
    return out


async def load_evidences(session, candidate_pair_ids: list[str]) -> dict:
    """candidate_pair_id → [evidence dicts](每条: 论文 title/PMID/section/句子)。

    按共现质量排序(same_sentence 优先),由 review service 截取 top 3。
    """
    pair_rows = (await session.execute(
        text(PAIRS_SQL).bindparams(
            ids=[str(x) for x in candidate_pair_ids]))).all()
    if not pair_rows:
        return {}
    paper_ids = list({str(r[1]) for r in pair_rows})
    paper_rows = (await session.execute(
        text(PAPERS_SQL).bindparams(ids=paper_ids))).all()
    paper_info = {str(p[0]): {"title": p[1], "pmid": p[2]} for p in paper_rows}

    quality = {"same_sentence": 0, "same_section": 1, "same_paper": 2}
    out: dict[str, list[dict]] = defaultdict(list)
    for pair_id, paper_id, sentence, cooccurrence, section in pair_rows:
        info = paper_info.get(str(paper_id), {"title": None, "pmid": None})
        out[str(pair_id)].append({
            "paper_title": info["title"],
            "pmid": info["pmid"],
            "section_name": section or "",
            "sentence": sentence,
            "cooccurrence": cooccurrence,
            "_quality": quality.get(cooccurrence, 9),
        })
    for pair_id, evs in out.items():
        evs.sort(key=lambda e: e["_quality"])
        for e in evs:
            e.pop("_quality", None)
    return dict(out)


async def main(_args: argparse.Namespace) -> None:
    # ---- 0. 迁移 + 基线 ----
    await apply_migration()
    async with AsyncSessionLocal() as session:
        counters_before = await _counters(session)
        reviewed_before = (await session.execute(text(
            "SELECT count(*) FROM macro_candidate_connection_llm_reviews"
        ))).scalar()
        papers_before = (await session.execute(text(
            "SELECT count(*) FROM paper_sources"))).scalar()
    print(f"baseline: {counters_before} | reviewed_before={reviewed_before} "
          f"| papers={papers_before}")

    # ---- 1. Top 200 rankings + 证据 ----
    async with AsyncSessionLocal() as session:
        rankings = await load_top_rankings(session)
        all_pair_ids = [pid for r in rankings for pid in r["candidate_pair_ids"]]
        evidences = await load_evidences(session, all_pair_ids)
    print(f"top_rankings={len(rankings)} (score DESC)")

    # 幂等:跳过已有审核结果的 ranking(UUID 统一 str 比较!)
    async with AsyncSessionLocal() as session:
        reviewed_ids = set(str(r[0]) for r in (await session.execute(text(
            "SELECT ranking_id FROM macro_candidate_connection_llm_reviews"
        ))).all())
    pending = [r for r in rankings if r["id"] not in reviewed_ids]
    print(f"pending_reviews={len(pending)} "
          f"(skipped_already_reviewed={len(rankings) - len(pending)})")

    # ---- 2. 批量 LLM 审核(并发 5,逐条重试) ----
    for r in pending:
        r["evidences"] = [e for pid in r["candidate_pair_ids"]
                          for e in evidences.get(pid, [])][:3]
    reviews: list[dict] = []
    if pending:
        reviews = await review_candidates_batch(
            pending, provider_key=PROVIDER, concurrency=5)
        print(f"llm_reviews_completed={len(reviews)}")
    else:
        print("[skip] 全部已审核,无待处理")

    # ---- 3. 幂等落库 ----
    def _jsonb_ready(row: dict, cols: tuple[str, ...]) -> dict:
        return {k: (Jsonb(v) if k in cols and v is not None else v)
                for k, v in row.items()}

    async with AsyncSessionLocal() as session:
        if reviews:
            await session.execute(
                text(INSERT_REVIEW_SQL),
                [_jsonb_ready(dict(r), ("raw_response_json",
                                        "provenance_json", "token_usage"))
                 for r in reviews])
        await session.commit()
    async with AsyncSessionLocal() as session:
        reviewed_after = (await session.execute(text(
            "SELECT count(*) FROM macro_candidate_connection_llm_reviews"
        ))).scalar()
    print(f"inserted={len(reviews)} | db_reviews={reviewed_after}")

    # ---- 4. 断言:零副作用 + 完整性 ----
    async with AsyncSessionLocal() as session:
        counters_after = await _counters(session)
        papers_after = (await session.execute(text(
            "SELECT count(*) FROM paper_sources"))).scalar()
        for name, before in counters_before.items():
            assert counters_after[name] == before, f"{name} 数量变化"
        assert papers_after == papers_before, "paper_sources 数量变化"
    print("[ok] zero-side-effect: rankings + final + canonical + mirror "
          "+ paper_sources 全不变")

    if reviews:
        missing = [r for r in reviews if not r["ranking_id"]]
        assert not missing, "存在无 ranking_id 的审核行"
        dup = len(reviews) != len({r["ranking_id"] for r in reviews})
        assert not dup, "同一 ranking 重复审核"
    print(f"[ok] integrity: {len(reviews)} 条审核行全部绑定唯一 ranking_id")

    # ---- 5. 报告 ----
    # 本次 review 行补名字/paper_count(来自 rankings 映射)
    name_by_ranking = {r["id"]: r for r in rankings}
    for rv in reviews:
        rk = name_by_ranking.get(rv["ranking_id"])
        rv["source_name"] = rk["source_name"] if rk else rv["source_region_id"]
        rv["target_name"] = rk["target_name"] if rk else rv["target_region_id"]
        rv["paper_count"] = rk["paper_count"] if rk else 0
    await _export_reports(rankings, reviews, reviewed_after,
                          counters_before, papers_before)


async def _export_reports(rankings, reviews, reviewed_after,
                          counters, papers_before) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()
    # 合并本次 + 历史(幂等复跑报告全量)
    all_rows = list(reviews)
    if reviewed_after > len(reviews):
        async with AsyncSessionLocal() as session:
            rows = (await session.execute(text("""\
SELECT rv.ranking_id, rv.source_region_id, rv.target_region_id,
       rv.decision, rv.connection_type, rv.direction, rv.confidence,
       rv.evidence_strength, rv.model_name, rv.provenance_json,
       rs.canonical_name_en AS source_name,
       rt.canonical_name_en AS target_name,
       r.paper_count
FROM macro_candidate_connection_llm_reviews rv
JOIN canonical_brain_regions rs ON rs.id = rv.source_region_id
JOIN canonical_brain_regions rt ON rt.id = rv.target_region_id
LEFT JOIN paper_connection_candidate_rankings r ON r.id = rv.ranking_id
ORDER BY rv.created_at"""))).all()
        for r in rows:
            prov = r[9] or {}
            all_rows.append({
                "ranking_id": str(r[0]),
                "source_region_id": str(r[1]),
                "target_region_id": str(r[2]),
                "decision": r[3], "connection_type": r[4],
                "direction": r[5], "confidence": float(r[6] or 0),
                "evidence_strength": r[7], "model_name": r[8],
                "source_name": r[10] or str(r[1]),
                "target_name": r[11] or str(r[2]),
                "paper_count": r[12],
                "supporting_papers": [e.get("pmid") for e in
                                      prov.get("evidence_refs", [])],
            })

    counts = Counter(r["decision"] for r in all_rows)
    def _write(name: str, data) -> None:
        (OUT_DIR / name).write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"[ok] {name}")

    # 1) review_summary.json
    _write("review_summary.json", {
        "analysis": "macro_candidate_llm_review_v1",
        "date": "2026-08-25",
        "inputs": {
            "top_n": TOP_N,
            "provider": PROVIDER,
            "rankings_loaded": len(rankings),
            "reviews_inserted_this_run": len(reviews),
            "db_reviews_total": reviewed_after,
        },
        "total_reviewed": len(all_rows),
        "decision_distribution": dict(counts),
        "governance": {
            "ranking_table_unchanged": counters["rankings"],
            "final_active_unchanged": counters["final_active"],
            "canonical_unchanged": counters["canonical"],
            "mirror_macro_unchanged": counters["mirror_macro"],
            "paper_sources_unchanged": papers_before,
            "no_final_kg_write": True,
            "no_connection_created": True,
            "idempotent": "ON CONFLICT (ranking_id) DO NOTHING,复跑跳过已审核",
        },
        "answers": {
            "q1_supported": counts["supported"],
            "q2_uncertain": counts["uncertain"],
            "q3_not_supported_false_cooccurrence": counts["not_supported"],
            "q4_most_common_connection_type": dict(Counter(
                r["connection_type"] for r in all_rows)),
            "q5_recommended_human_review": {
                "supported_all": counts["supported"],
                "supported_high_confidence": sum(
                    1 for r in all_rows if r["decision"] == "supported"
                    and r["confidence"] >= 0.7),
                "suggestion": (
                    f"建议人工审核 {counts['supported']} 条 supported "
                    f"(或先取 high confidence {sum(1 for r in all_rows if r['decision']=='supported' and r['confidence']>=0.7)} 条);"
                    f"uncertain {counts['uncertain']} 条可作第二轮 LLM 复核"),
            },
        },
        "generated_at": now,
    })

    # 2) decision_distribution.json
    by_decision: dict[str, list[dict]] = defaultdict(list)
    for r in all_rows:
        by_decision[r["decision"]].append(r)
    dist = {}
    for decision, rows in by_decision.items():
        confs = sorted(r["confidence"] for r in rows)
        dist[decision] = {
            "count": len(rows),
            "confidence_range": [confs[0], confs[-1]] if confs else [],
            "avg_confidence": round(sum(confs) / len(confs), 3) if confs else 0,
            "connection_types": dict(Counter(r["connection_type"] for r in rows)),
        }
    _write("decision_distribution.json", {
        "analysis": "macro_candidate_llm_review_v1",
        "decision_definition": {
            "supported": "论文原文明确支持两脑区存在连接",
            "uncertain": "证据不足/模糊,保留不确定",
            "not_supported": "仅共同出现/背景介绍/疾病相关,无连接关系(假共现)",
        },
        "distribution": dist,
        "generated_at": now,
    })

    # 3) top_supported_candidates.json
    supported = [r for r in all_rows if r["decision"] == "supported"]
    supported.sort(key=lambda r: (-r["confidence"], -(
        r.get("paper_count") or 0)))
    top_rows = [{
        "rank": i + 1,
        "source_region": r["source_name"],
        "target_region": r["target_name"],
        "source_region_id": r["source_region_id"],
        "target_region_id": r["target_region_id"],
        "decision": r["decision"],
        "confidence": r["confidence"],
        "connection_type": r["connection_type"],
        "direction": r["direction"],
        "evidence_strength": r["evidence_strength"],
        "paper_count": r["paper_count"],
        "supporting_papers": r.get("supporting_papers", []),
    } for i, r in enumerate(supported[:100])]
    _write("top_supported_candidates.json", {
        "analysis": "macro_candidate_llm_review_v1",
        "record": "LLM 判定 supported 的候选(按 confidence 降序)",
        "count": len(top_rows),
        "rows": top_rows,
        "generated_at": now,
    })


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Macro Candidate Connection LLM Scientific Review V1"
                    "(Top 200 → LLM judge → review results,幂等)")
    parser.add_argument("--top-n", type=int, default=TOP_N,
                        help="处理排名前 N(默认 200)")
    parser.add_argument("--concurrency", type=int, default=5,
                        help="LLM 并发数(默认 5)")
    parser.add_argument("--provider", default=PROVIDER,
                        help="LLM provider(默认 deepseek)")
    parser.add_argument("--model", default=None, help="模型名(默认用配置)")
    args = parser.parse_args()
    TOP_N = args.top_n
    PROVIDER = args.provider
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except Exception:
        pass
    asyncio.run(main(args))
