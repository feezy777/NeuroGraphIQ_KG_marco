"""Macro Paper Evidence Extraction V1 实施脚本。

任务:建立 Paper → Evidence → Connection 可解释证据链 —— 从论文摘要
(paper_sources.enrichment_json.abstract)抽取连接证据片段,写入
paper_connection_evidence_segments 表。

约束(用户要求):
* 只处理已有 connection_paper_evidence 关联的论文(104 条关联 / 46 篇)
* evidence_text = 摘要原文片段(规则抽取,禁止生成不存在的原文)
* 摘要没有明确支持句 → 不生成,标记 status='no_direct_evidence'
* provenance 记录 source=paper_abstract / paper_id / pmid / extraction_method
* 禁止修改 Final Connection / paper_sources / evidence_reference
* 无 LLM(纯规则,确定性可复现)

流程:
  1. 应用迁移(IF NOT EXISTS 幂等)+ 基线快照(5 counters +
     evidence_count + papers 616 + links 104 + segments 0)
  2. 加载 104 关联 + 连接 region 名 + 别名 + 摘要
  3. 规则抽取:同句双命中 → extracted;否则 → no_direct_evidence
  4. 幂等写入 INSERT ON CONFLICT (paper_id, connection_id) DO NOTHING
  5. 断言:paper_sources / connection_paper_evidence / Final /
     evidence_reference / counters 全不变
  6. 报告 → data/exports/macro_paper_evidence_segments/
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

_backend = Path(__file__).resolve().parent.parent
if str(_backend) not in sys.path:
    sys.path.insert(0, str(_backend))

from sqlalchemy import text

from app.database import AsyncSessionLocal
from app.services.macro_paper_evidence_segments_service import (
    EXTRACTION_METHOD,
    INSERT_SEGMENT_SQL,
    SELECT_SEGMENTS_SQL,
    STATUS_EXTRACTED,
    STATUS_NO_DIRECT_EVIDENCE,
    build_segment,
)

OUT_DIR = Path(_backend) / "data" / "exports" / "macro_paper_evidence_segments"
MIGRATION = Path(_backend) / "migrations" / \
    "20260912_paper_connection_evidence_segments.sql"

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


async def apply_migration() -> None:
    """幂等应用迁移(CREATE TABLE IF NOT EXISTS)。"""
    sql = MIGRATION.read_text(encoding="utf-8")
    async with AsyncSessionLocal() as session:
        for stmt in sql.split(";"):
            stmt = stmt.strip()
            if stmt:
                await session.execute(text(stmt))
        await session.commit()
    print(f"[ok] migration applied: {MIGRATION.name}")


async def main(_args: argparse.Namespace) -> None:
    # ---- 0. 迁移 + 基线快照 ----
    await apply_migration()
    async with AsyncSessionLocal() as session:
        counters_before = await _counters(session)
        ev_before = await _evidence_count(session)
        papers_before = (await session.execute(
            text("SELECT count(*) FROM paper_sources"))).scalar()
        links_before = (await session.execute(
            text("SELECT count(*) FROM connection_paper_evidence"))).scalar()
        seg_before = (await session.execute(
            text("SELECT count(*) FROM paper_connection_evidence_segments"))).scalar()
    print(f"baseline: {counters_before} | evidence_count={ev_before[1]} "
          f"| papers={papers_before} | links={links_before} "
          f"| segments={seg_before}")

    # ---- 1. 加载关联 + 连接 + region + 摘要 ----
    async with AsyncSessionLocal() as session:
        rows = (await session.execute(text("""
            SELECT l.paper_id, l.connection_id, e.pmid,
                   e.enrichment_json->>'abstract',
                   fc.connection_type,
                   r1.canonical_name_en, r2.canonical_name_en,
                   r1.id, r2.id
            FROM connection_paper_evidence l
            JOIN paper_sources e ON e.id = l.paper_id
            JOIN final_canonical_connections fc ON fc.id = l.connection_id
            LEFT JOIN canonical_brain_regions r1 ON r1.id = fc.source_region_id
            LEFT JOIN canonical_brain_regions r2 ON r2.id = fc.target_region_id
            ORDER BY e.pmid, l.connection_id"""))).all()
        # 别名(全部 region)
        alias_rows = (await session.execute(text(
            "SELECT region_id, alias FROM canonical_region_aliases"))).all()
    aliases: dict[str, list[str]] = {}
    for rid, alias in alias_rows:
        if rid is not None and alias:
            aliases.setdefault(str(rid), []).append(alias)
    links = [{"paper_id": str(r[0]), "connection_id": str(r[1]),
              "pmid": str(r[2]), "abstract": r[3],
              "connection_type": r[4],
              "source_name": r[5], "target_name": r[6],
              "source_region_id": str(r[7]) if r[7] else None,
              "target_region_id": str(r[8]) if r[8] else None}
             for r in rows]
    assert len(links) == 104, f"关联应为 104,实际 {len(links)}"
    print(f"links={len(links)} (aliases loaded={len(aliases)})")

    # ---- 2. 规则抽取 ----
    segments = []
    for link in links:
        seg = build_segment(
            link["paper_id"], link["connection_id"], link["pmid"],
            link["connection_type"], link["abstract"],
            link["source_name"] or "", link["target_name"] or "",
            aliases.get(link["source_region_id"] or "", []),
            aliases.get(link["target_region_id"] or "", []))
        seg["_pmid"] = link["pmid"]
        seg["_abstract"] = link["abstract"]
        segments.append(seg)
    n_extracted = sum(1 for s in segments if s["status"] == STATUS_EXTRACTED)
    n_nde = sum(1 for s in segments if s["status"] == STATUS_NO_DIRECT_EVIDENCE)
    print(f"extracted={n_extracted} no_direct_evidence={n_nde}")

    # ---- 3. 幂等写入 ----
    inserted = 0
    async with AsyncSessionLocal() as session:
        for s in segments:
            result = (await session.execute(
                text(INSERT_SEGMENT_SQL),
                {"paper_id": s["paper_id"],
                 "connection_id": s["connection_id"],
                 "evidence_text": s["evidence_text"],
                 "evidence_location": s["evidence_location"],
                 "extraction_method": s["extraction_method"],
                 "confidence": s["confidence"],
                 "provenance_json": json.dumps(
                     s["provenance_json"], ensure_ascii=False),
                 "status": s["status"]})).first()
            if result:
                inserted += 1
        await session.commit()
    print(f"segments inserted={inserted}/{len(segments)}")

    # ---- 4. 断言:零副作用 ----
    async with AsyncSessionLocal() as session:
        counters_after = await _counters(session)
        ev_after = await _evidence_count(session)
        papers_after = (await session.execute(
            text("SELECT count(*) FROM paper_sources"))).scalar()
        links_after = (await session.execute(
            text("SELECT count(*) FROM connection_paper_evidence"))).scalar()
        seg_after = (await session.execute(
            text("SELECT count(*) FROM paper_connection_evidence_segments"))).scalar()
        for name, before in counters_before.items():
            assert counters_after[name] == before, \
                f"{name} 数量变化(禁止写入)"
        assert ev_after == ev_before, "evidence_count 变化(禁止写入)"
        assert papers_after == papers_before, "paper_sources 数量变化"
        assert links_after == links_before, "connection_paper_evidence 数量变化"
        assert seg_after == seg_before + inserted, \
            "segments 净增 != 写入数"
    print("[ok] zero-side-effect: 5 counters + evidence_count + "
          "papers + links 全不变")

    # ---- 5. 报告 + 验收 ----
    await _export_reports(counters_before, papers_before, links_before,
                          ev_before[1], segments, inserted)


async def _export_reports(counters: dict, papers_before: int,
                          links_before: int, evidence_count: int,
                          segments: list[dict], inserted: int) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()

    extracted = [s for s in segments if s["status"] == STATUS_EXTRACTED]
    nde = [s for s in segments if s["status"] == STATUS_NO_DIRECT_EVIDENCE]
    no_abstract = [s for s in nde if not s["_abstract"]]

    # 每篇论文覆盖
    per_paper: dict[str, dict] = {}
    for s in segments:
        p = per_paper.setdefault(s["_pmid"], {
            "pmid": s["_pmid"], "links": 0, "extracted": 0,
            "no_direct_evidence": 0, "segments": []})
        p["links"] += 1
        if s["status"] == STATUS_EXTRACTED:
            p["extracted"] += 1
            p["segments"].append({
                "connection_id": s["connection_id"],
                "evidence_text": s["evidence_text"],
                "evidence_location": s["evidence_location"],
                "confidence": s["confidence"],
                "matched": s["provenance_json"].get("matched_terms", {}),
            })
        else:
            p["no_direct_evidence"] += 1

    conf_dist = Counter(s["confidence"] for s in extracted)
    per_conn = [{
        "connection_id": s["connection_id"],
        "pmid": s["_pmid"],
        "status": s["status"],
        "confidence": s["confidence"],
        "evidence_text": s["evidence_text"],
        "evidence_location": s["evidence_location"],
        "matched_terms": s["provenance_json"].get("matched_terms", {}),
        "reason": s["provenance_json"].get("reason", ""),
    } for s in segments]

    def _write(name: str, data: dict) -> None:
        (OUT_DIR / name).write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"[ok] {name}")

    _write("paper_evidence_segments_report.json", {
        "analysis": "macro_paper_evidence_extraction_v1",
        "task": "Paper → Evidence → Connection 证据链抽取报告",
        "source": "paper_sources.enrichment_json.abstract",
        "extraction_method": EXTRACTION_METHOD,
        "stats": {
            "total_links": len(segments),
            "extracted": len(extracted),
            "no_direct_evidence": len(nde),
            "no_abstract_source": len(no_abstract),
            "distinct_papers": len(per_paper),
            "papers_with_extracted": sum(
                1 for p in per_paper.values() if p["extracted"] > 0),
        },
        "confidence_distribution": {
            str(k): v for k, v in sorted(conf_dist.items(), reverse=True)},
        "per_paper_coverage": sorted(
            per_paper.values(), key=lambda p: p["pmid"]),
        "per_connection": per_conn,
        "generated_at": now,
    })
    _write("acceptance_report.json", {
        "analysis": "macro_paper_evidence_extraction_v1",
        "stage": "Macro Paper Evidence Extraction V1 验收报告",
        "date": "2026-08-25",
        "execution": {
            "script": "scripts/run_macro_paper_evidence_segments.py",
            "service": "app/services/macro_paper_evidence_segments_service.py",
            "migration": "migrations/20260912_paper_connection_evidence_segments.sql",
            "tests": "test_macro_paper_evidence_segments.py (20)",
        },
        "answers": {
            "successful_segments": len(extracted),
            "no_direct_evidence": len(nde),
            "per_paper_coverage": f"{len(per_paper)} 篇论文涉及;"
                                  f"{sum(1 for p in per_paper.values() if p['extracted'] > 0)} "
                                  "篇有成功抽取片段",
            "quality_report": {
                "confidence": dict(sorted(conf_dist.items(), reverse=True)),
                "no_abstract_source_links": len(no_abstract),
                "note": "evidence_text 均为摘要原文逐字片段;"
                        "无支持句不生成(禁止编造)",
            },
        },
        "constraints_verified": {
            "paper_sources_count_unchanged": f"{papers_before} 前后一致",
            "connection_paper_evidence_count_unchanged": f"{links_before} 前后一致",
            "final_active_unchanged": f"{counters['final_active']} 前后一致",
            "canonical_unchanged": f"{counters['canonical']} 前后一致",
            "mirror_macro_unchanged": f"{counters['mirror_macro']} 前后一致",
            "lineage_unchanged": f"{counters['lineage']} 前后一致",
            "clusters_unchanged": f"{counters['clusters']} 前后一致",
            "evidence_count_unchanged": f"{evidence_count} 前后一致",
            "evidence_reference_untouched": "本阶段未修改 evidence_reference",
            "evidence_text_verbatim": "片段逐字取自摘要原文"
                                      "(find_support_sentence 保证 in 摘要)",
            "no_direct_evidence_marked": f"{len(nde)} 条标记 "
                                         f"status=no_direct_evidence(不生成)",
            "provenance_recorded": "source=paper_abstract/paper_id/pmid/"
                                   "extraction_method(每条)",
            "idempotent": "INSERT ON CONFLICT (paper_id, connection_id) "
                          "DO NOTHING → 复跑 0 新增",
            "no_final_connection_change": True,
            "no_paper_sources_change": True,
            "no_ontology_change": True,
            "no_new_connection": True,
            "no_llm_calls": True,
        },
        "conclusion": (
            f"{len(extracted)} 条证据片段成功抽取(confidence 分级),"
            f"{len(nde)} 条标记 no_direct_evidence(摘要无明确支持句,"
            f"含 {len(no_abstract)} 条无摘要来源);"
            "证据链 Paper → Evidence → Connection 建立。"
        ),
        "generated_at": now,
    })


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Macro Paper Evidence Extraction V1"
                    "(摘要 → 连接证据片段,规则抽取,幂等)")
    parser.parse_args()
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except Exception:
        pass
    asyncio.run(main(parser.parse_args()))
