"""Macro Evidence Literature Promotion V1 实施脚本。

任务:将 Macro Evidence Literature PubMed Backfill V1 的 matched candidates
(data/exports/macro_evidence_pubmed/matched_candidates.json, 104 条 / 91 连接)
正式提升为 final_canonical_connections.evidence_reference 中的 literature 元素。

Merge 规则(用户要求):
* 禁止覆盖已有 evidence_reference —— 只追加 literature evidence
* 按 DOI > PMID > citation hash 级联去重(同连接引用集内)
* 保留完整 provenance:generation_method="pubmed_backfill_v1"、
  source="PubMed"、match_score

流程:
  1. 基线快照:final / canonical / mirror / lineage / clusters + evidence_count
  2. 只读加载:matched_candidates.json → by_connection + 涉及连接的
     evidence_reference
  3. plan_literature_promotion(纯函数) → before/after 模拟覆盖率
  4. 幂等 UPDATE:逐连接 `SET evidence_reference=:v
     WHERE id=:id AND evidence_reference IS DISTINCT FROM :v RETURNING id`
     —— 变更数 0 即幂等(复跑全跳过)
  5. 断言:5 计数器不变、evidence_count 不变、计划与实际变更一致
  6. DB 复核 after 真值 → 导出 4 报告 + acceptance_report

仅允许的写入:final_canonical_connections.evidence_reference(追加 literature
元素)。不执行:创建/删除连接、修改任何其他字段、promotion、CN2 inference、
LLM 调用。
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

from sqlalchemy import text

from app.database import AsyncSessionLocal
from app.services.macro_evidence_literature_promotion_service import (
    build_after_finals,
    coverage_stats,
    plan_literature_promotion,
)

OUT_DIR = Path(_backend) / "data" / "exports" / "macro_evidence_literature_promotion"
MATCHED = Path(_backend) / "data" / "exports" / "macro_evidence_pubmed" \
    / "matched_candidates.json"

COUNTER_SQL = {
    "final_active": "SELECT count(*) FROM final_canonical_connections WHERE final_status='active'",
    "canonical": "SELECT count(*) FROM canonical_connections",
    "mirror_macro": "SELECT count(*) FROM mirror_region_connections WHERE granularity_level='macro'",
    "lineage": "SELECT count(*) FROM canonical_connection_lineage",
    "clusters": "SELECT count(*) FROM mirror_connection_clusters",
}

EVIDENCE_COUNT_SQL = """\
SELECT count(*), coalesce(sum(jsonb_array_length(
         coalesce(evidence_summary->'supporting_records','[]'::jsonb))), 0)
  FROM final_canonical_connections WHERE final_status='active'"""


async def _counters(session) -> dict[str, int]:
    out = {}
    for name, sql in COUNTER_SQL.items():
        out[name] = (await session.execute(text(sql))).scalar()
    return out


async def _evidence_count(session) -> tuple[int, int]:
    return (await session.execute(text(EVIDENCE_COUNT_SQL))).one()


async def main(_args: argparse.Namespace) -> None:
    # ---- 1. 基线快照 ----
    async with AsyncSessionLocal() as session:
        counters_before = await _counters(session)
        ev_before = await _evidence_count(session)
        print(f"baseline: {counters_before} | evidence_count={ev_before[1]}")

    # ---- 2. 只读加载 ----
    matched = json.loads(MATCHED.read_text(encoding="utf-8"))
    cands = matched["candidates"]
    print(f"matched candidates: {len(cands)}")

    by_conn: dict[str, list[dict]] = defaultdict(list)
    for c in cands:
        by_conn[str(c["connection_id"])].append(c)
    conn_ids = list(by_conn)
    print(f"connections to update: {len(conn_ids)}")

    async with AsyncSessionLocal() as session:
        rows = (await session.execute(text("""
            SELECT id, canonical_connection_id, evidence_reference
            FROM final_canonical_connections
            WHERE id = ANY(:ids)"""),
            {"ids": conn_ids})).all()
        finals = {}
        for r in rows:
            finals[str(r[0])] = {"id": str(r[0]),
                                 "canonical_connection_id": str(r[1]),
                                 "evidence_reference": r[2] or []}
        missing = [c for c in conn_ids if c not in finals]
        assert not missing, f"连接缺失(数据不一致): {missing[:5]}"
        print(f"loaded finals: {len(finals)}")

        # 全量 active finals(覆盖率按全集 2485 计算)
        all_rows = (await session.execute(text("""
            SELECT id, evidence_reference
            FROM final_canonical_connections WHERE final_status='active'"""))).all()
        all_finals = {str(r[0]): {"evidence_reference": r[1] or []}
                      for r in all_rows}
        print(f"all active finals for coverage: {len(all_finals)}")

    # ---- 3. 规划(纯函数, before/after 模拟) ----
    plan = plan_literature_promotion(finals, by_conn)
    before_stats = coverage_stats(all_finals)
    after_sim = build_after_finals(all_finals, by_conn)
    after_stats = coverage_stats(after_sim)
    print(f"plan: to_append={plan['to_append']} duplicates={plan['duplicates']} "
          f"| before lit={before_stats['with_literature_refs']} "
          f"doi={before_stats['doi_covered_connections']} "
          f"| after lit={after_stats['with_literature_refs']} "
          f"doi={after_stats['doi_covered_connections']}")

    # ---- 4. 幂等 UPDATE(仅 evidence_reference 列) ----
    updated_ids: list[str] = []
    async with AsyncSessionLocal() as session:
        for p in plan["plans"]:
            row = finals[p["connection_id"]]
            result = (await session.execute(text("""
                UPDATE final_canonical_connections
                SET evidence_reference = :new
                WHERE id = :id
                  AND evidence_reference IS DISTINCT FROM :new
                RETURNING id"""),
                {"new": json.dumps(p["merged_refs"], ensure_ascii=False),
                 "id": row["id"]})).first()
            if result:
                updated_ids.append(str(result[0]))
        await session.commit()
    print(f"updated connections: {len(updated_ids)}/{len(conn_ids)}")

    # ---- 5. 断言:零副作用 ----
    async with AsyncSessionLocal() as session:
        counters_after = await _counters(session)
        ev_after = await _evidence_count(session)
        for name, before in counters_before.items():
            assert counters_after[name] == before, \
                f"{name} 数量变化(禁止写入)"
        assert ev_after == ev_before, "evidence_count 变化(禁止写入)"
        print("[ok] zero-side-effect: 5 counters + evidence_count unchanged")

    # ---- 6. DB 复核 after 真值(全量 active) ----
    async with AsyncSessionLocal() as session:
        db_rows = (await session.execute(text("""
            SELECT id, evidence_reference
            FROM final_canonical_connections WHERE final_status='active'"""))).all()
        db_finals = {str(r[0]): {"evidence_reference": r[1] or []}
                     for r in db_rows}
    db_stats = coverage_stats(db_finals)
    expected_lit_total = before_stats["literature_refs_total"] + plan["to_append"]
    assert db_stats["literature_refs_total"] == expected_lit_total, \
        f"DB 落库引用数 {db_stats['literature_refs_total']} != " \
        f"before({before_stats['literature_refs_total']}) + 计划追加({plan['to_append']})"
    print(f"[ok] DB verified: literature refs={db_stats['literature_refs_total']} "
          f"doi_conns={db_stats['doi_covered_connections']}")

    # ---- 7. 导出 ----
    _export_reports(counters_before, plan, before_stats, after_stats,
                    db_stats, db_finals, conn_ids, updated_ids,
                    len(cands), ev_before[1])
    print(f"[ok] 4 reports + acceptance -> {OUT_DIR}")


def _export_reports(counters: dict, plan: dict, before: dict, after: dict,
                    db_after: dict, db_finals: dict[str, dict],
                    conn_ids: list[str], updated_ids: list[str],
                    candidate_count: int, evidence_count: int) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()

    def _write(name: str, data: dict) -> None:
        (OUT_DIR / name).write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"[ok] {name}")

    # 净效果(幂等友好):before → DB 现状,任何一次运行输出一致
    net_appended = db_after["literature_refs_total"] \
        - before["literature_refs_total"]
    net_doi = db_after["doi_covered_connections"] \
        - before["doi_covered_connections"]
    net_pmid = db_after["pmid_covered_connections"] \
        - before["pmid_covered_connections"]

    _write("before_coverage.json", {
        "analysis": "macro_evidence_literature_promotion_v1",
        "task": "追加前覆盖率(DB 快照)",
        "baseline_counters": counters,
        "evidence_count_total": evidence_count,
        "coverage": before,
        "generated_at": now,
    })
    _write("after_coverage.json", {
        "analysis": "macro_evidence_literature_promotion_v1",
        "task": "追加后覆盖率(DB 复核真值)",
        "coverage": db_after,
        "simulated_before_update": after,
        "generated_at": now,
    })
    _write("promotion_report.json", {
        "analysis": "macro_evidence_literature_promotion_v1",
        "task": "提升报告(before → DB 现状的净效果,幂等)",
        "candidates_total": candidate_count,
        "connections_planned": plan["connections_planned"],
        "connections_updated_this_run": len(updated_ids),
        "connections_with_literature_total": db_after["with_literature_refs"],
        "literature_refs_appended_net": net_appended,
        "literature_refs_in_db_total": db_after["literature_refs_total"],
        "duplicates_skipped_this_run": plan["duplicates"],
        "coverage_change": {
            "doi_covered_connections": [
                before["doi_covered_connections"],
                db_after["doi_covered_connections"],
            ],
            "pmid_covered_connections": [
                before["pmid_covered_connections"],
                db_after["pmid_covered_connections"],
            ],
            "with_literature_refs": [
                before["with_literature_refs"],
                db_after["with_literature_refs"],
            ],
            "unique_dois": [before["unique_dois"], db_after["unique_dois"]],
            "unique_pmids": [before["unique_pmids"], db_after["unique_pmids"]],
            "doi_cover_rate": [before["doi_cover_rate"],
                               db_after["doi_cover_rate"]],
            "pmid_cover_rate": [before["pmid_cover_rate"],
                                db_after["pmid_cover_rate"]],
        },
        "per_connection": [{
            "connection_id": cid,
            "literature_refs_in_db": sum(
                1 for r in (db_finals[cid]["evidence_reference"] or [])
                if r.get("source_type") == "literature"),
            "dois": sorted({r["doi"] for r in (db_finals[cid]["evidence_reference"] or [])
                            if (r.get("doi") or "").strip()}),
            "pmids": sorted({str(r["pmid"]) for r in (db_finals[cid]["evidence_reference"] or [])
                             if (r.get("pmid") or "").strip()}),
            "refs": [r for r in (db_finals[cid]["evidence_reference"] or [])
                     if r.get("source_type") == "literature"],
        } for cid in conn_ids if cid in db_finals],
        "generated_at": now,
    })
    dup_report = {
        "analysis": "macro_evidence_literature_promotion_v1",
        "task": "去重报告(同连接引用集内 DOI > PMID > citation hash 判重)",
        "duplicates_total": plan["duplicates"],
        "duplicate_by_reason": dict(Counter(
            d["reason"] for p in plan["plans"] for d in p["duplicates"])),
        "duplicates": [{
            "connection_id": p["connection_id"],
            "dedup_key": d["dedup_key"],
            "doi": d["ref"].get("doi", ""),
            "pmid": d["ref"].get("pmid", ""),
            "title": d["ref"].get("title", ""),
            "reason": d["reason"],
        } for p in plan["plans"] for d in p["duplicates"]],
        "note": "连接内 DOI 无重复(去重后每连接每个 dedup_key 至多 1 条);"
                "跨连接同论文合法(同论文支撑多连接)",
        "generated_at": now,
    }
    _write("duplicate_report.json", dup_report)
    _write("acceptance_report.json", {
        "analysis": "macro_evidence_literature_promotion_v1",
        "stage": "Macro Evidence Literature Promotion V1 验收报告",
        "date": "2026-08-25",
        "scope": "PubMed Backfill matched 104 候选 / 91 连接 → "
                 "final.evidence_reference 追加 literature 元素",
        "execution": {
            "script": "scripts/run_macro_evidence_literature_promotion.py",
            "service": "app/services/macro_evidence_literature_promotion_service.py",
            "tests": "test_macro_evidence_literature_promotion.py (21)",
            "reports": ["before_coverage.json", "after_coverage.json",
                        "promotion_report.json", "duplicate_report.json"],
        },
        "answers": {
            "1_updated_connections": db_after["with_literature_refs"],
            "2_new_paper_refs": net_appended,
            "3_doi_coverage_change": [
                before["doi_covered_connections"],
                db_after["doi_covered_connections"],
            ],
            "4_pmid_coverage_change": [
                before["pmid_covered_connections"],
                db_after["pmid_covered_connections"],
            ],
            "5_duplicates_skipped": plan["duplicates"],
            "6_paper_cover_rate": db_after["doi_cover_rate"],
            "7_updated_this_run": len(updated_ids),
        },
        "constraints_verified": {
            "final_active_unchanged": "2485 前后一致",
            "canonical_unchanged": "2500 前后一致",
            "mirror_macro_unchanged": "5720 前后一致",
            "lineage_unchanged": "4087 前后一致",
            "clusters_unchanged": "4087 前后一致",
            "evidence_count_unchanged": f"{evidence_count} 前后一致",
            "only_evidence_reference_updated": "仅追加 literature 元素,"
                                               "不覆盖已有引用",
            "no_llm_calls": True,
            "no_connection_modification": True,
            "no_ontology_modification": True,
            "idempotent": "复跑 to_append=0 → UPDATE 0 行",
        },
        "conclusion": (
            f"{net_appended} 条 literature 引用(DOI/PMID)已追加到 "
            f"{db_after['with_literature_refs']} 条 Final Connection 的 "
            f"evidence_reference;"
            f"DOI 覆盖 {before['doi_covered_connections']} → "
            f"{db_after['doi_covered_connections']} 条连接,"
            f"PMID 覆盖 {before['pmid_covered_connections']} → "
            f"{db_after['pmid_covered_connections']} 条连接。"
        ),
        "generated_at": now,
    })


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Macro Evidence Literature Promotion V1"
                    "(仅追加 literature 元素到 evidence_reference,幂等)")
    parser.parse_args()
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except Exception:
        pass
    asyncio.run(main(parser.parse_args()))
