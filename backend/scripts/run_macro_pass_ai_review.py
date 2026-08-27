"""Rule PASS 候选的 LLM 科学审核补充(Phase 4 novel 队列前置)。

数据现实:PASS 30 条(脑室/CSF 等候选)尚无 AI review → novel 队列为空。
本脚本对「无 review 的 PASS ranking」定向补审(复用 Phase 1 管线,幂等:
已有 review 的 ranking 跳过;ON CONFLICT DO NOTHING)。

约束:只读 rankings/rule results/paper_region_pair_candidates,仅写
macro_candidate_connection_llm_reviews(候选层);不改 final/canonical/mirror。
"""

from __future__ import annotations

import asyncio
import sys
from collections import Counter
from pathlib import Path

_backend = Path(__file__).resolve().parent.parent
if str(_backend) not in sys.path:
    sys.path.insert(0, str(_backend))

from psycopg.types.json import Jsonb
from sqlalchemy import text

from app.database import AsyncSessionLocal
from app.services.macro_candidate_llm_review_service import (
    INSERT_REVIEW_SQL,
    review_one_candidate,
)

PASS_NO_REVIEW_SQL = """\
SELECT rk.id, rk.source_region_id, rk.target_region_id,
       rs.canonical_name_en AS src, rt.canonical_name_en AS tgt,
       rk.paper_count, rk.score, rk.candidate_pair_ids
FROM macro_candidate_rule_validation_results v
JOIN paper_connection_candidate_rankings rk ON rk.id = v.ranking_id
JOIN canonical_brain_regions rs ON rs.id = rk.source_region_id
JOIN canonical_brain_regions rt ON rt.id = rk.target_region_id
WHERE v.validation_status = 'PASS'
  AND NOT EXISTS (SELECT 1 FROM macro_candidate_connection_llm_reviews rv
                  WHERE rv.ranking_id = rk.id)
ORDER BY rk.score DESC"""

PAIRS_SQL = """\
SELECT id, paper_id, evidence_sentence, section_name, cooccurrence
FROM paper_region_pair_candidates
WHERE id = ANY(:ids)"""

PAPER_TITLE_SQL = """\
SELECT id, title, pmid FROM paper_sources WHERE id = ANY(:ids)"""


async def main() -> None:
    async with AsyncSessionLocal() as s:
        rows = (await s.execute(text(PASS_NO_REVIEW_SQL))).all()
        print(f"PASS no-review rankings: {len(rows)}")
        if not rows:
            print("[skip] 无待补审候选")
            return

        pair_ids = [str(pid) for r in rows for pid in (r[7] or [])]
        pair_rows = (await s.execute(
            text(PAIRS_SQL), {"ids": pair_ids})).all() if pair_ids else []
        paper_ids = list({str(r[1]) for r in pair_rows})
        paper_rows = (await s.execute(
            text(PAPER_TITLE_SQL), {"ids": paper_ids})).all()
        paper_info = {str(p[0]): (p[1], p[2]) for p in paper_rows}

        # ranking_id → top2 证据句(按共现质量排序)
        q = {"same_sentence": 0, "same_section": 1, "same_paper": 2}
        ev_by_ranking: dict[str, list[dict]] = {}
        for pid, paper_id, sentence, section, coocc in pair_rows:
            rid = next((str(r[0]) for r in rows if pid in (r[7] or [])), None)
            if rid is None:
                continue
            ev_by_ranking.setdefault(rid, []).append({
                "paper_title": paper_info.get(str(paper_id), ("unknown", None))[0],
                "pmid": paper_info.get(str(paper_id), ("unknown", None))[1],
                "section_name": section or "",
                "sentence": sentence,
                "_q": q.get(coocc, 9),
            })
        for rid, evs in ev_by_ranking.items():
            evs.sort(key=lambda e: e["_q"])
            for e in evs:
                e.pop("_q", None)

        reviews = []
        for r in rows:
            ranking = {
                "id": str(r[0]),
                "source_region_id": str(r[1]),
                "target_region_id": str(r[2]),
                "source_name": r[3], "target_name": r[4],
                "paper_count": r[5],
                "candidate_pair_ids": [str(x) for x in (r[7] or [])],
            }
            evidences = ev_by_ranking.get(str(r[0]), [])[:2]
            reviews.append(await review_one_candidate(
                ranking, evidences, provider_key="deepseek",
            ))

        async with AsyncSessionLocal() as s2:
            for rv in reviews:
                row = dict(rv)
                for col in ("raw_response_json", "provenance_json", "token_usage"):
                    row[col] = Jsonb(row[col] or {})
                await s2.execute(text(INSERT_REVIEW_SQL), row)
            await s2.commit()
        print(f"reviews built: {len(reviews)} (idempotent insert)")
        print("decision distribution:", dict(Counter(r["decision"] for r in reviews)))


if __name__ == "__main__":
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except Exception:
        pass
    asyncio.run(main())
