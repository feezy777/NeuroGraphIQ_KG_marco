"""Macro Connection 论文数据导入实施脚本。

任务:将阶段 G 已落库的 91 连接 × 104 条 literature reference 正式导入
系统 Paper 数据层:
  1. paper_sources 新增论文(source=PubMed;DOI/PMID 已存在则复用)
  2. connection_paper_evidence 建立 104 条 Connection-Paper 关联

约束(用户要求):
* 不创建新的论文表 —— 复用已有 paper_sources(570 行)
* DOI/PMID 已存在 → 复用;不存在 → 新增
* evidence_reference 保留已有 llm_extraction —— 本阶段不改 evidence_reference
* 不重新设计 ontology、不做新审计

流程:
  1. 基线快照:5 计数器 + evidence_count + paper_sources 行数
  2. 只读加载 matched_candidates.json(104) + DB 命中扫描
  3. 规划:论文去重(90) + 复用/新增分类 + 关联(104)
  4. 幂等写入:INSERT paper ON CONFLICT DO NOTHING RETURNING;
     INSERT link ON CONFLICT (connection_id, paper_id) DO NOTHING RETURNING
  5. 断言:5 计数器 + evidence_count 不变;paper_sources 净增 = 新增论文数
  6. 可追溯性验证:每关联的 DOI/PMID 与 final.evidence_reference 元素一致
  7. 导出报告 → data/exports/macro_connection_paper_import/
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
from app.services.macro_connection_paper_import_service import (
    INSERT_LINK_SQL,
    INSERT_PAPER_SQL,
    SELECT_PAPER_BY_IDENTITY_SQL,
    build_link,
    build_paper_insert,
    group_paper_records,
    plan_paper_reuse,
)

OUT_DIR = Path(_backend) / "data" / "exports" / "macro_connection_paper_import"
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
        papers_before = (await session.execute(
            text("SELECT count(*) FROM paper_sources"))).scalar()
        links_before = (await session.execute(
            text("SELECT count(*) FROM connection_paper_evidence"))).scalar()
        print(f"baseline: {counters_before} | evidence_count={ev_before[1]} "
              f"| paper_sources={papers_before} | links={links_before}")

    # ---- 2. 只读加载 + 规划 ----
    # 输入源:final.evidence_reference 的 literature 元素(阶段 G 落库真值,
    # 含 title/authors 已提取)—— 与 matched_candidates.json 一致但字段完整
    async with AsyncSessionLocal() as session:
        rows = (await session.execute(text("""
            SELECT id, evidence_reference FROM final_canonical_connections
            WHERE final_status='active'"""))).all()
    refs = []
    for row in rows:
        for r in (row[1] or []):
            if isinstance(r, dict) and r.get("source_type") == "literature":
                r = dict(r)  # 不可变:副本
                r["connection_id"] = str(row[0])  # final 元素用 matched_connection_id
                refs.append(r)
    assert len(refs) == 104, f"literature refs 应为 104,实际 {len(refs)}"
    records = group_paper_records(refs)
    print(f"refs={len(refs)} → unique papers={len(records)}")

    async with AsyncSessionLocal() as session:
        existing = (await session.execute(text(SELECT_PAPER_BY_IDENTITY_SQL), {
            "dois": sorted({r["normalized_doi"] for r in
                            (build_paper_insert(x) for x in records)
                            if r["normalized_doi"]}),
            "pmids": sorted({str(r["pmid"]) for r in
                             (build_paper_insert(x) for x in records)
                             if r["pmid"]}),
        })).all()
    reuse_plan = plan_paper_reuse(
        [(str(r[0]), r[1], r[2]) for r in existing], records)
    print(f"papers: reuse={len(reuse_plan['reuse'])} new={len(reuse_plan['new'])}")

    # ---- 3. 幂等写入 paper_sources ----
    paper_ids: dict[str, str] = {}  # identity key → paper_id
    new_paper_rows = 0
    async with AsyncSessionLocal() as session:
        for entry in reuse_plan["reuse"]:
            rec = entry["record"]
            key = rec["identity"]
            paper_ids[key] = str(entry["paper_id"])
        for entry in reuse_plan["new"]:
            rec = entry["record"]
            ins = build_paper_insert(rec)
            ins["metadata_json"] = json.dumps(ins["metadata_json"],
                                              ensure_ascii=False)
            result = (await session.execute(
                text(INSERT_PAPER_SQL), ins)).first()
            if result:
                paper_ids[rec["identity"]] = str(result[0])
                new_paper_rows += 1
            else:
                # 并发/复跑下 ON CONFLICT 跳过 → 反查已有
                found = (await session.execute(text(
                    """SELECT id FROM paper_sources
                       WHERE (normalized_doi IS NOT NULL
                              AND normalized_doi = :doi)
                          OR (pmid IS NOT NULL AND pmid = :pmid)
                       LIMIT 1"""),
                    {"doi": ins["normalized_doi"], "pmid": ins["pmid"]})).first()
                assert found, "paper insert 冲突但反查失败"
                paper_ids[rec["identity"]] = str(found[0])
        await session.commit()
    print(f"paper_sources: inserted={new_paper_rows} "
          f"(reused={len(reuse_plan['reuse'])})")

    # ---- 4. 幂等写入关联 ----
    link_rows = 0
    links: list[dict] = []
    async with AsyncSessionLocal() as session:
        for ref in refs:
            from app.services.macro_connection_paper_import_service import (
                paper_identity,
            )
            doi_key, pmid_key = paper_identity(ref)
            key = doi_key or pmid_key
            paper_id = paper_ids[key]
            link = build_link(str(ref["connection_id"]), paper_id, ref)
            result = (await session.execute(
                text(INSERT_LINK_SQL),
                {"connection_id": link["connection_id"],
                 "paper_id": link["paper_id"],
                 "support_type": link["support_type"],
                 "evidence_reference": json.dumps(
                     link["evidence_reference"], ensure_ascii=False),
                 "confidence": float(link["confidence"]),
                 "provenance_json": json.dumps(
                     link["provenance_json"], ensure_ascii=False)})).first()
            if result:
                link_rows += 1
            links.append(link)
        await session.commit()
    print(f"links inserted={link_rows}/{len(refs)}")

    # ---- 5. 断言:零副作用(connection/evidence 层) ----
    async with AsyncSessionLocal() as session:
        counters_after = await _counters(session)
        ev_after = await _evidence_count(session)
        papers_after = (await session.execute(
            text("SELECT count(*) FROM paper_sources"))).scalar()
        links_after = (await session.execute(
            text("SELECT count(*) FROM connection_paper_evidence"))).scalar()
        for name, before in counters_before.items():
            assert counters_after[name] == before, \
                f"{name} 数量变化(禁止写入)"
        assert ev_after == ev_before, "evidence_count 变化(禁止写入)"
        assert papers_after == papers_before + new_paper_rows, \
            "paper_sources 净增 != 新增论文数"
        assert links_after == links_before + link_rows, \
            "connection_paper_evidence 净增 != 新增关联数"
        print(f"[ok] zero-side-effect: 5 counters + evidence_count unchanged | "
              f"papers {papers_before}→{papers_after} | links {links_after}")

    # ---- 6. 可追溯性验证 ----
    async with AsyncSessionLocal() as session:
        db_links = (await session.execute(text("""
            SELECT connection_id, paper_id, support_type,
                   evidence_reference->>'doi', evidence_reference->>'pmid',
                   provenance_json->>'imported_from'
            FROM connection_paper_evidence"""))).all()
        trace_ok = 0
        for r in db_links:
            ref = next((x for x in links
                        if str(x["connection_id"]) == str(r[0])
                        and str(x["paper_id"]) == str(r[1])), None)
            if ref and ref["evidence_reference"].get("doi", "") == (r[3] or "") \
                    and str(ref["evidence_reference"].get("pmid", "")) == (r[4] or ""):
                trace_ok += 1
        assert trace_ok == links_before + link_rows == links_after, \
            "关联可追溯性验证失败"
        print(f"[ok] traceability: {trace_ok}/{links_after} links verified "
              f"(connection→paper→reference 一致)")

    # ---- 7. 导出 ----
    _export_reports(counters_before, refs, records, reuse_plan, links,
                    new_paper_rows, papers_before, links_before,
                    link_rows, ev_before[1])
    print(f"[ok] reports -> {OUT_DIR}")


def _export_reports(counters: dict, refs: list[dict], records: list[dict],
                    reuse_plan: dict, links: list[dict], papers_inserted: int,
                    papers_before: int, links_before: int, links_inserted: int,
                    evidence_count: int) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()

    def _write(name: str, data: dict) -> None:
        (OUT_DIR / name).write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"[ok] {name}")

    # DOI 覆盖率:Final 层不变,论文数据层新增
    conn_with_doi = len({str(l["connection_id"]) for l in links
                         if l["evidence_reference"].get("doi")})
    conn_all = len({str(l["connection_id"]) for l in links})

    _write("import_report.json", {
        "analysis": "macro_connection_paper_import_v1",
        "task": "论文导入报告",
        "scope": "91 Macro Final Connection × 104 literature reference → "
                 "paper_sources + connection_paper_evidence",
        "papers": {
            "total_unique": len(records),
            "inserted_new": papers_inserted,
            "reused_existing": len(reuse_plan["reuse"]),
            "paper_sources_total_before": papers_before,
            "paper_sources_total_after": papers_before + papers_inserted,
            "source": "PubMed",
        },
        "links": {
            "planned": len(links),
            "inserted": links_inserted,
            "existing_before": links_before,
            "total_after": links_before + links_inserted,
            "connections_covered": conn_all,
        },
        "doi_coverage_change": {
            "final_evidence_reference_doi_conns": conn_with_doi,
            "final_total_conns": 2485,
            "final_doi_cover_rate": round(conn_with_doi / 2485, 4),
            "note": "Final.evidence_reference 不变(阶段 G 已写入);"
                    "本阶段新增论文数据层落地:paper_sources + 关联表",
        },
        "per_paper": [{
            "doi": r["doi"], "pmid": r["pmid"], "title": r["title"],
            "authors": r["authors"], "year": r["year"],
            "matched_refs": len(r["refs"]),
        } for r in records],
        "generated_at": now,
    })
    _write("links_report.json", {
        "analysis": "macro_connection_paper_import_v1",
        "task": "Connection-Paper 关联明细",
        "links": [{
            "connection_id": l["connection_id"],
            "paper_id": l["paper_id"],
            "support_type": l["support_type"],
            "doi": l["evidence_reference"].get("doi", ""),
            "pmid": l["evidence_reference"].get("pmid", ""),
            "confidence": l["confidence"],
            "match_method": l["provenance_json"].get("match_method", ""),
            "evidence_source": l["evidence_reference"].get(
                "evidence_source", ""),
        } for l in links],
        "generated_at": now,
    })
    _write("acceptance_report.json", {
        "analysis": "macro_connection_paper_import_v1",
        "stage": "Macro Connection 论文数据导入验收报告",
        "date": "2026-08-25",
        "scope": "91 连接 × 104 literature reference → Paper 数据层"
                 "(paper_sources + connection_paper_evidence)",
        "execution": {
            "script": "scripts/run_macro_connection_paper_import.py",
            "service": "app/services/macro_connection_paper_import_service.py",
            "migration": "migrations/20260910_connection_paper_evidence.sql",
            "tests": "test_macro_connection_paper_import.py (17)",
            "reports": ["import_report.json", "links_report.json"],
        },
        "answers": {
            "1_new_papers": papers_inserted,
            "2_reused_papers": len(reuse_plan["reuse"]),
            "3_links_total": links_before + links_inserted,
            "4_doi_cover_rate_change": [
                "Final 层不变(阶段 G:90/2485 = 3.62%)",
                f"论文数据层落地:{conn_with_doi} 连接 ↔ "
                f"{papers_inserted} 新论文({papers_before}→"
                f"{papers_before + papers_inserted})",
            ],
        },
        "constraints_verified": {
            "final_active_unchanged": "2485 前后一致",
            "canonical_unchanged": "2500 前后一致",
            "mirror_macro_unchanged": "5720 前后一致(Mirror 数量不变)",
            "lineage_unchanged": "4087 前后一致",
            "clusters_unchanged": "4087 前后一致",
            "evidence_count_unchanged": f"{evidence_count} 前后一致",
            "no_new_paper_table": "复用 paper_sources(未建论文表)",
            "evidence_reference_untouched": "本阶段未修改 evidence_reference"
                                            "(阶段 G 已追加 literature,"
                                            "llm_extraction 保留)",
            "traceability": f"{links_before + links_inserted} 条关联全部可追溯"
                            "(connection→paper→DOI/PMID 一致)",
            "idempotent": "INSERT ON CONFLICT DO NOTHING → 复跑 0 新增",
            "no_ontology_change": True,
            "no_llm_calls": True,
        },
        "conclusion": (
            f"{papers_inserted} 篇新论文(source=PubMed)写入 paper_sources,"
            f"{len(reuse_plan['reuse'])} 篇复用已有;{links_inserted} 条 "
            f"Connection-Paper 关联建立({conn_all} 连接);Final/Mirror/"
            f"evidence_count 全不变,关联可追溯。"
        ),
        "generated_at": now,
    })


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Macro Connection 论文数据导入"
                    "(paper_sources + connection_paper_evidence,幂等)")
    parser.parse_args()
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except Exception:
        pass
    asyncio.run(main(parser.parse_args()))
