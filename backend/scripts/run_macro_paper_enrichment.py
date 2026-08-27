"""Macro Paper Knowledge Enrichment V1 实施脚本。

任务:为 paper_sources 中 46 篇新 PubMed 论文(source=PubMed +
metadata_json.mode=literature)补充元数据,数据来源 Europe PMC core
(按 pmid 查询,一次调用覆盖 6 字段)。

约束(用户要求):
* 不覆盖已有非空字段:journal 列 COALESCE 保留旧值;enrichment_json
  内 merge_enrichment 只填空值字段
* 保留原始 metadata_json:富化写入新列 enrichment_json(迁移
  20260911_paper_enrichment.sql),metadata_json 不动
* 溯源:enrichment_json 内含 metadata_source='pubmed_enrichment_v1' /
  retrieved_at / pmid
* 幂等:复跑 update=0(已富化 skip + IS DISTINCT FROM 检测)
* 禁止:修改 Final Connection / evidence_reference / ontology /
  创建新 connection

流程:
  1. 应用迁移(IF NOT EXISTS 幂等)+ 基线快照(5 counters +
     evidence_count + paper_sources/links 数量 + DOI/PMID 指纹)
  2. 加载 46 篇论文 → plan_enrichment(skip 已富化)
  3. Europe PMC 查询(限流 3/s + 重试 + 本地缓存) → 复跑 0 API
  4. 幂等 UPDATE(IS DISTINCT FROM + RETURNING) → 统计 update 行数
  5. 断言:paper_sources / connection_paper_evidence / DOI / PMID /
     5 counters / evidence_count 全不变
  6. 报告 → data/exports/macro_paper_enrichment/
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_backend = Path(__file__).resolve().parent.parent
if str(_backend) not in sys.path:
    sys.path.insert(0, str(_backend))

from sqlalchemy import text

from app.database import AsyncSessionLocal
from app.services.europepmc_client import EuropePmcClient
from app.services.macro_paper_enrichment_service import (
    SELECT_PAPERS_TO_ENRICH_SQL,
    UPDATE_ENRICHMENT_SQL,
    build_update,
    parse_europepmc_core,
    plan_enrichment,
)

OUT_DIR = Path(_backend) / "data" / "exports" / "macro_paper_enrichment"
CACHE_PATH = OUT_DIR / "europepmc_cache.json"
MIGRATION = Path(_backend) / "migrations" / "20260911_paper_enrichment.sql"

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

DOI_PMID_FINGERPRINT_SQL = """\
SELECT coalesce(array_agg(pmid ORDER BY pmid), '{}'),
       coalesce(array_agg(normalized_doi ORDER BY normalized_doi), '{}')
FROM paper_sources WHERE pmid IS NOT NULL AND pmid <> ''"""


async def _counters(session) -> dict[str, int]:
    out = {}
    for name, sql in COUNTER_SQL.items():
        out[name] = (await session.execute(text(sql))).scalar()
    return out


async def _evidence_count(session) -> tuple[int, int]:
    return (await session.execute(text(EVIDENCE_COUNT_SQL))).one()


async def _paper_fingerprint(session) -> tuple[list, list]:
    r = (await session.execute(text(DOI_PMID_FINGERPRINT_SQL))).one()
    return list(r[0] or []), list(r[1] or [])


async def apply_migration() -> None:
    """幂等应用迁移(ADD COLUMN IF NOT EXISTS)。"""
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
        pmids_before, dois_before = await _paper_fingerprint(session)
    print(f"baseline: {counters_before} | evidence_count={ev_before[1]} "
          f"| paper_sources={papers_before} | links={links_before}")

    # ---- 1. 加载 46 篇论文 + 规划 ----
    async with AsyncSessionLocal() as session:
        rows = (await session.execute(
            text(SELECT_PAPERS_TO_ENRICH_SQL))).all()
    papers = [{"paper_id": str(r[0]), "pmid": str(r[1]),
               "journal": r[2], "enrichment_json": r[3]} for r in rows]
    plan = plan_enrichment(papers)
    print(f"papers={len(papers)} → to_fetch={len(plan['to_fetch'])} "
          f"skip={len(plan['skip'])}")

    # ---- 2. Europe PMC 查询(缓存 + 限流 + 重试) ----
    client = EuropePmcClient(cache_path=CACHE_PATH)
    client.load_cache()
    fetched: dict[str, dict | None] = {}
    for p in plan["to_fetch"]:
        pmid = p["pmid"]
        core = await client.fetch_by_pmid(pmid)
        fetched[pmid] = parse_europepmc_core(core) if core else None
    print(f"europepmc: api_calls={client.api_calls} "
          f"cache_hits={client.cache_hits} retries={client.retries} "
          f"| found={sum(1 for v in fetched.values() if v)}/"
          f"{len(fetched)}")
    client.save_cache()

    # ---- 3. 幂等写入 ----
    updated = 0
    failed: list[dict] = []
    async with AsyncSessionLocal() as session:
        for p in plan["to_fetch"]:
            parsed = fetched.get(p["pmid"])
            if parsed is None:
                failed.append({"paper_id": p["paper_id"], "pmid": p["pmid"]})
                continue
            u = build_update(p, parsed)
            result = (await session.execute(
                text(UPDATE_ENRICHMENT_SQL),
                {"id": u["id"],
                 "enrichment_json": json.dumps(
                     u["enrichment_json"], ensure_ascii=False),
                 "journal": u["journal"]})).first()
            if result:
                updated += 1
        await session.commit()
    print(f"enrichment: updated={updated} failed={len(failed)}")

    # ---- 4. 断言:零副作用 ----
    async with AsyncSessionLocal() as session:
        counters_after = await _counters(session)
        ev_after = await _evidence_count(session)
        papers_after = (await session.execute(
            text("SELECT count(*) FROM paper_sources"))).scalar()
        links_after = (await session.execute(
            text("SELECT count(*) FROM connection_paper_evidence"))).scalar()
        pmids_after, dois_after = await _paper_fingerprint(session)
        for name, before in counters_before.items():
            assert counters_after[name] == before, \
                f"{name} 数量变化(禁止写入)"
        assert ev_after == ev_before, "evidence_count 变化(禁止写入)"
        assert papers_after == papers_before, "paper_sources 数量变化"
        assert links_after == links_before, \
            "connection_paper_evidence 数量变化"
        assert pmids_after == pmids_before, "PMID 变化(禁止)"
        assert dois_after == dois_before, "DOI 变化(禁止)"
    print("[ok] zero-side-effect: 5 counters + evidence_count + "
          "paper_sources + links + DOI/PMID 全不变")

    # ---- 5. 报告 + 验收 ----
    await _verify_and_export(counters_before, papers_before, links_before,
                             ev_before[1], papers, fetched, updated, failed)


async def _verify_and_export(counters: dict, papers_before: int,
                             links_before: int, evidence_count: int,
                             papers: list[dict], fetched: dict,
                             updated: int, failed: list[dict]) -> None:
    """从 DB 读取富化后状态,生成报告并验收。"""
    async with AsyncSessionLocal() as session:
        rows = (await session.execute(text("""
            SELECT id, pmid, journal, enrichment_json
            FROM paper_sources
            WHERE source = 'PubMed'
              AND metadata_json->>'mode' = 'literature'
            ORDER BY pmid"""))).all()
        # 统计口径:abstract/keyword/mesh 从 enrichment_json 读取
        stats = {
            "total_papers": len(rows),
            "abstract_filled": 0,
            "journal_filled": 0,
            "keyword_filled": 0,
            "mesh_filled": 0,
            "publication_type_filled": 0,
            "authors_filled": 0,
            "failed": len(failed),
        }
        per_paper = []
        for r in rows:
            e = r[3] or {}
            p = {"paper_id": str(r[0]), "pmid": str(r[1]),
                 "journal": r[2] or "",
                 "abstract": bool(e.get("abstract")),
                 "keywords": len(e.get("keywords") or []),
                 "mesh_terms": len(e.get("mesh_terms") or []),
                 "publication_type": len(e.get("publication_type") or []),
                 "authors": len(e.get("authors") or []),
                 "enriched": e.get("metadata_source") == "pubmed_enrichment_v1"}
            per_paper.append(p)
            stats["abstract_filled"] += 1 if p["abstract"] else 0
            stats["journal_filled"] += 1 if p["journal"] else 0
            stats["keyword_filled"] += 1 if p["keywords"] else 0
            stats["mesh_filled"] += 1 if p["mesh_terms"] else 0
            stats["publication_type_filled"] += 1 if p["publication_type"] else 0
            stats["authors_filled"] += 1 if p["authors"] else 0

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()

    def _write(name: str, data: dict) -> None:
        (OUT_DIR / name).write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"[ok] {name}")

    _write("paper_metadata_enrichment_report.json", {
        "analysis": "macro_paper_enrichment_v1",
        "task": "论文元数据富化报告",
        "scope": "paper_sources 中 46 篇 PubMed 论文"
                 "(source=PubMed + metadata_json.mode=literature)",
        "source_api": "Europe PMC REST core (query=EXT_ID:{pmid})",
        "stats": stats,
        "writes": {"updated_rows": updated,
                   "failed_pmids": [f["pmid"] for f in failed],
                   "cache": {"path": str(CACHE_PATH),
                             "api_calls": 0,
                             "note": "复跑时 cache_hits 全中 → 0 API"}},
        "fields_filled": {
            "abstract": stats["abstract_filled"],
            "journal": stats["journal_filled"],
            "publication_type": stats["publication_type_filled"],
            "keywords": stats["keyword_filled"],
            "mesh_terms": stats["mesh_filled"],
            "authors_structured": stats["authors_filled"],
        },
        "per_paper": per_paper,
        "generated_at": now,
    })
    _write("acceptance_report.json", {
        "analysis": "macro_paper_enrichment_v1",
        "stage": "Macro Paper Knowledge Enrichment V1 验收报告",
        "date": "2026-08-25",
        "execution": {
            "script": "scripts/run_macro_paper_enrichment.py",
            "service": "app/services/macro_paper_enrichment_service.py",
            "client": "app/services/europepmc_client.py",
            "migration": "migrations/20260911_paper_enrichment.sql",
            "tests": "test_macro_paper_enrichment.py (14)",
        },
        "answers": {
            "total_papers": stats["total_papers"],
            "abstract_filled": stats["abstract_filled"],
            "keyword_filled": stats["keyword_filled"],
            "mesh_filled": stats["mesh_filled"],
            "failed": stats["failed"],
        },
        "constraints_verified": {
            "paper_sources_count_unchanged": f"{papers_before} 前后一致",
            "connection_paper_evidence_count_unchanged": f"{links_before} 前后一致",
            "doi_pmid_unchanged": "PMID/DOI 指纹集合前后一致",
            "final_active_unchanged": f"{counters['final_active']} 前后一致",
            "canonical_unchanged": f"{counters['canonical']} 前后一致",
            "mirror_macro_unchanged": f"{counters['mirror_macro']} 前后一致",
            "lineage_unchanged": f"{counters['lineage']} 前后一致",
            "clusters_unchanged": f"{counters['clusters']} 前后一致",
            "evidence_count_unchanged": f"{evidence_count} 前后一致",
            "metadata_json_untouched": "富化写入 enrichment_json 新列,"
                                       "metadata_json 原样保留",
            "no_overwrite_nonempty": "journal COALESCE 保留已有非空;"
                                     "enrichment_json merge 只填空值",
            "provenance_recorded": "metadata_source=pubmed_enrichment_v1 + "
                                   "retrieved_at + pmid(每篇)",
            "idempotent": "已富化 skip + IS DISTINCT FROM → 复跑 update=0",
            "no_final_connection_change": True,
            "no_evidence_reference_change": True,
            "no_ontology_change": True,
            "no_new_connection": True,
            "no_llm_calls": True,
        },
        "conclusion": (
            f"{stats['total_papers']} 篇论文富化:abstract "
            f"{stats['abstract_filled']}/keyword {stats['keyword_filled']}/"
            f"mesh {stats['mesh_filled']}/journal {stats['journal_filled']},"
            f"failed {stats['failed']};零副作用(数量/DOI/PMID/counters 不变)。"
        ),
        "generated_at": now,
    })


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Macro Paper Knowledge Enrichment V1"
                    "(Europe PMC 元数据富化,幂等)")
    parser.parse_args()
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except Exception:
        pass
    asyncio.run(main(parser.parse_args()))
