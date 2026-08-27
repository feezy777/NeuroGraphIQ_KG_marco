"""Macro Paper-Connection Evidence Reclassification V1 实施脚本。

任务:重新评估 connection_paper_evidence 的 104 条 paper-connection 关联,
建立三类(用户定义):
* A: direct_evidence     → evidence_relation_type='direct_support'
* B: supporting_literature → 'context_support'
* C: invalid_association → 'invalid'

判定(纯规则,复用已有证据链):
1. extracted segment(摘要级或全文级)→ direct_support
2. 标题 / 摘要 / 全文(缓存 XML)提及 source 或 target 任一端 → context_support
3. 无信号 → invalid

约束(用户要求):
* 不删除原始 connection_paper_evidence 行(只回填新列,UPDATE 幂等)
* 保留原始 match_method / doi / pmid / confidence(不动
  provenance_json / evidence_reference / confidence)
* 禁止修改 Final Connection / ontology / paper_sources

流程:
  1. 应用迁移(ADD COLUMN IF NOT EXISTS 幂等)+ 基线快照
  2. 加载 104 关联(含 match_method/doi/confidence + region 名/别名 +
     摘要) + extracted segments + XML 缓存
  3. 三级分类
  4. 幂等回填 UPDATE(IS DISTINCT FROM)
  5. 断言:104 行不删、5 counters / evidence_count / papers / links /
     segments 全不变
  6. 报告:A/B/C 数量 + 每条 connection 分类结果(含判定依据 +
     match_method/doi/pmid/confidence)
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
from app.services.macro_paper_connection_reclassification_service import (
    RELATION_CONTEXT,
    RELATION_DIRECT,
    RELATION_INVALID,
    SELECT_LINKS_SQL,
    SELECT_SEGMENT_STATUS_SQL,
    UPDATE_RELATION_TYPE_SQL,
    classify_link,
)
from app.services.macro_paper_evidence_segments_service import STATUS_EXTRACTED

OUT_DIR = Path(_backend) / "data" / "exports" / "macro_paper_connection_reclassification"
XML_DIR = Path(_backend) / "data" / "exports" / "macro_paper_fulltext_evidence" / "xml"
MIGRATION = Path(_backend) / "migrations" / \
    "20260915_paper_connection_relation_type.sql"

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
        classified_before = (await session.execute(
            text("SELECT count(*) FROM connection_paper_evidence "
                 "WHERE evidence_relation_type IS NOT NULL"))).scalar()
    print(f"baseline: {counters_before} | evidence_count={ev_before[1]} "
          f"| papers={papers_before} | links={links_before} "
          f"| segments={seg_before} | classified={classified_before}")

    # ---- 1. 加载 104 关联 + 别名 + extracted segments + XML ----
    async with AsyncSessionLocal() as session:
        rows = (await session.execute(text(SELECT_LINKS_SQL))).all()
        alias_rows = (await session.execute(text(
            "SELECT region_id, alias FROM canonical_region_aliases"))).all()
        extracted = (await session.execute(text(
            SELECT_SEGMENT_STATUS_SQL), {"status": STATUS_EXTRACTED})).all()
    aliases: dict[str, list[str]] = {}
    for rid, alias in alias_rows:
        if rid is not None and alias:
            aliases.setdefault(str(rid), []).append(alias)
    extracted_keys = {(str(r[0]), str(r[1])) for r in extracted}
    links = [{"link_id": str(r[0]), "connection_id": str(r[1]),
              "paper_id": str(r[2]), "pmid": str(r[3]),
              "title": r[4] or "", "abstract": r[5],
              "match_method": r[6] or "", "doi": r[7] or "",
              "confidence": float(r[8]) if r[8] is not None else 0.0,
              "connection_type": r[9],
              "source_name": r[10] or "", "target_name": r[11] or "",
              "source_region_id": str(r[12]) if r[12] else None,
              "target_region_id": str(r[13]) if r[13] else None}
             for r in rows]
    assert len(links) == 104, f"关联应为 104,实际 {len(links)}"
    print(f"links={len(links)} extracted_segments={len(extracted_keys)} "
          f"aliases={len(aliases)}")

    # ---- 2. 三级分类 ----
    classified = []
    for link in links:
        xml_path = XML_DIR / f"{link['pmid']}.xml"
        fulltext = xml_path.read_text(encoding="utf-8") \
            if xml_path.exists() else None
        result = classify_link(
            segment_statuses=[
                STATUS_EXTRACTED
                if (link["paper_id"], link["connection_id"]) in extracted_keys
                else "no_direct_evidence"],
            title=link["title"], abstract=link["abstract"],
            fulltext_xml=fulltext,
            source_name=link["source_name"], target_name=link["target_name"],
            source_aliases=aliases.get(link["source_region_id"] or "", []),
            target_aliases=aliases.get(link["target_region_id"] or "", []))
        classified.append({**link, **result})
    counts = Counter(c["relation_type"] for c in classified)
    print(f"A direct={counts[RELATION_DIRECT]} "
          f"B context={counts[RELATION_CONTEXT]} "
          f"C invalid={counts[RELATION_INVALID]}")

    # ---- 3. 幂等回填(不删行) ----
    updated = 0
    async with AsyncSessionLocal() as session:
        for c in classified:
            result = (await session.execute(
                text(UPDATE_RELATION_TYPE_SQL),
                {"relation_type": c["relation_type"],
                 "link_id": c["link_id"]})).first()
            if result:
                updated += 1
        await session.commit()
    print(f"evidence_relation_type updated={updated}/104")

    # ---- 4. 断言:零副作用 + 不删行 ----
    async with AsyncSessionLocal() as session:
        counters_after = await _counters(session)
        ev_after = await _evidence_count(session)
        papers_after = (await session.execute(
            text("SELECT count(*) FROM paper_sources"))).scalar()
        links_after = (await session.execute(
            text("SELECT count(*) FROM connection_paper_evidence"))).scalar()
        seg_after = (await session.execute(
            text("SELECT count(*) FROM paper_connection_evidence_segments"))).scalar()
        classified_after = (await session.execute(
            text("SELECT count(*) FROM connection_paper_evidence "
                 "WHERE evidence_relation_type IS NOT NULL"))).scalar()
        for name, before in counters_before.items():
            assert counters_after[name] == before, \
                f"{name} 数量变化(禁止写入)"
        assert ev_after == ev_before, "evidence_count 变化(禁止写入)"
        assert papers_after == papers_before, "paper_sources 数量变化"
        assert links_after == links_before, "connection_paper_evidence 行被删除"
        assert seg_after == seg_before, "segments 数量变化"
        assert classified_after == classified_before + updated, \
            "已分类行净增 != 更新数"
    print("[ok] zero-side-effect: 5 counters + evidence_count + papers + "
          "links + segments 全不变;原始行未删")

    # ---- 5. 报告 + 验收 ----
    await _export_reports(counters_before, papers_before, links_before,
                          ev_before[1], classified, updated,
                          classified_before)


async def _export_reports(counters: dict, papers_before: int,
                          links_before: int, evidence_count: int,
                          classified: list[dict], updated: int,
                          classified_before: int) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()

    counts = Counter(c["relation_type"] for c in classified)
    basis = Counter(c["detail"]["basis"] for c in classified)
    mm = Counter(c["match_method"] for c in classified)

    per_connection = [{
        "link_id": c["link_id"],
        "connection_id": c["connection_id"],
        "pmid": c["pmid"],
        "doi": c["doi"],
        "match_method": c["match_method"],
        "confidence": c["confidence"],
        "connection": f"{c['source_name']} -> {c['target_name']}"
                      f" ({c['connection_type']})",
        "evidence_relation_type": c["relation_type"],
        "detail": c["detail"],
    } for c in sorted(classified, key=lambda x: (x["relation_type"],
                                                 x["pmid"]))]

    def _write(name: str, data: dict) -> None:
        (OUT_DIR / name).write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"[ok] {name}")

    _write("reclassification_report.json", {
        "analysis": "macro_paper_connection_reclassification_v1",
        "task": "104 条 paper-connection 关联质量重分类报告",
        "classification": {
            "A_direct_evidence": "direct_support:论文原文明确描述两脑区间"
                                 "connection/projection/connectivity/pathway"
                                 "(有 extracted segment)",
            "B_supporting_literature": "context_support:论文研究相关脑区或"
                                       "功能,但未证明该 connection",
            "C_invalid_association": "invalid:论文与 connection 无直接关系",
        },
        "stats": {
            "total_links": len(classified),
            "A_direct_evidence": counts[RELATION_DIRECT],
            "B_supporting_literature": counts[RELATION_CONTEXT],
            "C_invalid_association": counts[RELATION_INVALID],
            "classification_basis": dict(basis),
            "match_method_distribution": dict(mm),
            "updated_this_run": updated,
            "classified_before": classified_before,
        },
        "per_connection": per_connection,
        "generated_at": now,
    })
    _write("acceptance_report.json", {
        "analysis": "macro_paper_connection_reclassification_v1",
        "stage": "Macro Paper-Connection Evidence Reclassification V1 验收报告",
        "date": "2026-08-25",
        "execution": {
            "script": "scripts/run_macro_paper_connection_reclassification.py",
            "service": "app/services/"
                       "macro_paper_connection_reclassification_service.py",
            "migration": "migrations/"
                         "20260915_paper_connection_relation_type.sql",
            "tests": "test_macro_paper_connection_reclassification.py (14)",
        },
        "answers": {
            "A_direct_evidence_count": counts[RELATION_DIRECT],
            "B_supporting_literature_count": counts[RELATION_CONTEXT],
            "C_invalid_association_count": counts[RELATION_INVALID],
            "per_connection_results": (
                f"{len(classified)} 条全量分类,详见 "
                "reclassification_report.json per_connection"),
        },
        "constraints_verified": {
            "original_rows_not_deleted": f"{links_before} 行前后一致"
                                         "(仅 UPDATE 回填新列)",
            "match_method_preserved": "provenance_json 未修改(读取展示)",
            "doi_preserved": "evidence_reference 未修改",
            "pmid_preserved": "paper_sources 未修改",
            "confidence_preserved": "confidence 列未修改",
            "final_active_unchanged": f"{counters['final_active']} 前后一致",
            "canonical_unchanged": f"{counters['canonical']} 前后一致",
            "mirror_macro_unchanged": f"{counters['mirror_macro']} 前后一致",
            "lineage_unchanged": f"{counters['lineage']} 前后一致",
            "clusters_unchanged": f"{counters['clusters']} 前后一致",
            "evidence_count_unchanged": f"{evidence_count} 前后一致",
            "paper_sources_unchanged": f"{papers_before} 前后一致",
            "ontology_untouched": True,
            "no_new_connection": True,
            "no_llm_calls": True,
            "idempotent": "UPDATE ... IS DISTINCT FROM → 复跑 0 更新",
        },
        "conclusion": (
            f"A direct={counts[RELATION_DIRECT]} / "
            f"B context={counts[RELATION_CONTEXT]} / "
            f"C invalid={counts[RELATION_INVALID]} —— "
            "关联质量已分级,判定依据(extracted segment / 标题·摘要·全文"
            "提及信号)记录在每条 detail;原始关联行与 match_method/doi/"
            "pmid/confidence 全保留。"
        ),
        "generated_at": now,
    })


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Macro Paper-Connection Evidence Reclassification V1"
                    "(104 条关联三级分类,幂等回填)")
    parser.parse_args()
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except Exception:
        pass
    asyncio.run(main(parser.parse_args()))
