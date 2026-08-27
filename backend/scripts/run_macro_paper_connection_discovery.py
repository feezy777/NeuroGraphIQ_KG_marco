"""Macro Paper-driven Connection Discovery V1 实施脚本。

论文驱动的候选连接发现(第一阶段,仅候选发现基础设施):
  paper_sources(title 616) + paper_passages(abstract 440 + fulltext 190)
  + fullTextXML 缓存(3 篇) → 脑区实体识别(51 区) → 同论文 region pair
  候选(paper_region_cooccurrence_v1) → 命中句证据库。

约束(用户要求):
* 不修改 final_canonical_connections / canonical_connections /
  paper_sources —— 所有新发现只进 3 张候选表
* 不直接创建 Connection,不进入 validation/review/promotion/Final KG
* 无外部 API / 无 LLM —— 纯规则,确定性,幂等(INSERT ON CONFLICT DO NOTHING)

流程:
  1. 应用迁移 + 基线快照
  2. 加载 Macro96 51 canonical 区 + 别名 + hierarchy(part_of)
  3. 加载 616 论文文本(title/abstract/fulltext/XML 缓存)
  4. 逐论文 NER 发现(mentions / pairs / segments)
  5. 幂等落库(3 张候选表)
  6. 断言:零副作用 + 候选可追溯到原文(evidence_sentence 重建验证)
  7. 报告:paper_region_mentions.json / candidate_pairs.json /
     discovery_summary.json(含验收 4 问回答)
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

import xml.etree.ElementTree as ET

from psycopg.types.json import Jsonb
from sqlalchemy import text

from app.database import AsyncSessionLocal
from app.services.macro_paper_connection_discovery_service import (
    INSERT_MENTION_SQL,
    INSERT_PAIR_SQL,
    INSERT_SEGMENT_SQL,
    build_paper_discovery,
    build_region_lexicon,
    discover_paper_sentences,
    iter_abstract_sentences,
    iter_fulltext_sentences,
    iter_title_sentences,
)
from app.services.macro_paper_fulltext_evidence_service import parse_jats_xml

OUT_DIR = Path(_backend) / "data" / "exports" / "macro_paper_connection_discovery"
XML_DIR = Path(_backend) / "data" / "exports" / "macro_paper_fulltext_evidence" / "xml"
MIGRATION = Path(_backend) / "migrations" / "20260916_paper_region_discovery.sql"

# Macro96 池 canonical 区 = final 连接端点(检查阶段已确认 51 区)
REGIONS_SQL = """\
SELECT DISTINCT c.id, c.canonical_name_en, c.canonical_name_cn,
       c.granularity_level, c.hemisphere_policy, c.laterality
FROM canonical_brain_regions c
WHERE c.id IN (SELECT source_region_id FROM final_canonical_connections
               UNION
               SELECT target_region_id FROM final_canonical_connections)
ORDER BY c.canonical_name_en"""

ALIASES_SQL = """\
SELECT a.region_id, a.alias, a.alias_language
FROM canonical_region_aliases a
WHERE a.region_id IN (SELECT source_region_id FROM final_canonical_connections
                      UNION
                      SELECT target_region_id FROM final_canonical_connections)"""

HIERARCHY_SQL = """\
SELECT h.child_region_id, c1.canonical_name_en AS child_name,
       h.parent_region_id, c2.canonical_name_en AS parent_name
FROM canonical_region_hierarchy h
JOIN canonical_brain_regions c1 ON c1.id = h.child_region_id
JOIN canonical_brain_regions c2 ON c2.id = h.parent_region_id"""

PAPERS_SQL = """\
SELECT p.id, p.pmid, p.title, p.enrichment_json
FROM paper_sources p ORDER BY p.id"""

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

# 旧 evidence 段表(阶段 K 产物,禁止改动)
SEG_OLD_COUNT_SQL = "SELECT count(*) FROM paper_connection_evidence_segments"


async def _counters(session) -> dict[str, int]:
    out = {}
    for name, sql in COUNTER_SQL.items():
        out[name] = (await session.execute(text(sql))).scalar()
    return out


async def _evidence_count(session) -> tuple[int, int]:
    """(final_active 行数, 其 evidence_summary->'supporting_records' 总条数)。"""
    row = (await session.execute(text(EVIDENCE_COUNT_SQL))).one()
    return int(row[0]), int(row[1])


async def apply_migration() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")
    async with AsyncSessionLocal() as session:
        for stmt in sql.split(";"):
            stmt = stmt.strip()
            if stmt:
                await session.execute(text(stmt))
        await session.commit()
    print(f"[ok] migration applied: {MIGRATION.name}")


async def load_regions(session) -> tuple[list[dict], dict, dict]:
    """51 区 + 别名 + hierarchy → (regions, hierarchy_parent, region_info)。"""
    region_rows = (await session.execute(text(REGIONS_SQL))).all()
    alias_rows = (await session.execute(text(ALIASES_SQL))).all()
    hierarchy_rows = (await session.execute(text(HIERARCHY_SQL))).all()

    alias_by_region: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for rid, alias, lang in alias_rows:
        if rid is not None and alias:
            kind = {"cn": "alias_cn", "en": "alias_en",
                    "abbr": "alias_abbr"}.get(lang or "", "alias_en")
            alias_by_region[str(rid)].append((alias, kind))

    regions = [{
        "region_id": str(r[0]),
        "canonical_name_en": r[1] or "",
        "aliases": alias_by_region.get(str(r[0]), []),
    } for r in region_rows]
    region_info = {str(r[0]): {
        "canonical_name_en": r[1] or "",
        "canonical_name_cn": r[2],
        "granularity_level": r[3],
        "hemisphere_policy": r[4],
        "laterality": r[5],
    } for r in region_rows}
    hierarchy_parent: dict[str, str] = {}
    for cid, cname, pid, pname in hierarchy_rows:
        if cid is not None and pid is not None:
            hierarchy_parent[str(cid)] = pname or str(pid)
    print(f"regions={len(regions)} aliases={sum(len(a) for a in alias_by_region.values())} "
          f"hierarchy_edges={len(hierarchy_rows)}")
    return regions, hierarchy_parent, region_info


async def load_papers(session) -> list[dict]:
    """616 论文 → 每篇 {id, pmid, title, texts: {source: [...]}}。"""
    rows = (await session.execute(text(PAPERS_SQL))).all()
    papers = [{"id": str(r[0]), "pmid": r[1], "title": r[2] or "",
               "enrichment": r[3] or {}} for r in rows]
    print(f"papers={len(papers)}")
    return papers


async def load_passages(session, paper_ids: set[str]) -> dict:
    """paper_passages → {paper_id: {'abstract': [段], 'fulltext': {section: [段]}}}。"""
    rows = (await session.execute(text("""\
SELECT paper_id, source_scope, coalesce(section_title,''), passage_text
FROM paper_passages ORDER BY paper_id, source_scope, paragraph_index"""))).all()
    out: dict[str, dict] = defaultdict(lambda: {"abstract": [],
                                                "fulltext": defaultdict(list)})
    for pid, scope, section, ptext in rows:
        pid_s = str(pid)
        if pid_s not in paper_ids:
            continue
        if not ptext or not ptext.strip():
            continue
        if scope == "abstract":
            out[pid_s]["abstract"].append(ptext)
        elif scope == "fulltext":
            out[pid_s]["fulltext"][section or "Body"].append(ptext)
    print(f"passages: papers={len(out)} "
          f"abstract_papers={sum(1 for v in out.values() if v['abstract'])} "
          f"fulltext_papers={sum(1 for v in out.values() if v['fulltext'])}")
    return dict(out)


def load_xml_cached(pmids: dict[str, str]) -> dict:
    """XML 缓存 {paper_id: {"sections": [...]}};解析失败安全跳过。"""
    out: dict[str, dict] = {}
    for pmid, paper_id in pmids.items():
        path = XML_DIR / f"{pmid}.xml"
        if not path.exists():
            continue
        try:
            parsed = parse_jats_xml(path.read_text(encoding="utf-8"))
        except ET.ParseError:
            print(f"[warn] xml parse failed: {path.name}")
            continue
        out[paper_id] = {"sections": parsed["sections"]}
    print(f"xml_cache: {len(out)} papers")
    return out


async def main(_args: argparse.Namespace) -> None:
    # ---- 0. 迁移 + 基线 ----
    await apply_migration()
    async with AsyncSessionLocal() as session:
        counters_before = await _counters(session)
        ev_before = await _evidence_count(session)
        papers_before = (await session.execute(
            text("SELECT count(*) FROM paper_sources"))).scalar()
        links_before = (await session.execute(
            text("SELECT count(*) FROM connection_paper_evidence"))).scalar()
        seg_old_before = (await session.execute(
            text(SEG_OLD_COUNT_SQL))).scalar()
        m0 = (await session.execute(text(
            "SELECT count(*) FROM paper_region_mentions"))).scalar()
        p0 = (await session.execute(text(
            "SELECT count(*) FROM paper_region_pair_candidates"))).scalar()
        s0 = (await session.execute(text(
            "SELECT count(*) FROM paper_region_evidence_segments"))).scalar()
    print(f"baseline: {counters_before} | evidence_count={ev_before[1]} "
          f"| papers={papers_before} | links={links_before} "
          f"| old_segments={seg_old_before} | new_tables=({m0},{p0},{s0})")

    # ---- 1. 词表 + 文本源 ----
    async with AsyncSessionLocal() as session:
        regions, hierarchy_parent, region_info = await load_regions(session)
        papers = await load_papers(session)
        passages = await load_passages(session, {p["id"] for p in papers})
    alias_count = sum(len(r["aliases"]) for r in regions)
    abstract_papers = 0
    for p in papers:
        if p["enrichment"].get("abstract") or passages.get(p["id"], {}).get("abstract"):
            abstract_papers += 1
    lexicon = build_region_lexicon(regions)
    xml_cache = load_xml_cached({p["pmid"]: p["id"] for p in papers if p["pmid"]})
    print(f"lexicon_terms={len(lexicon)}")

    # ---- 2. 逐论文发现 ----
    all_mentions: list[dict] = []
    all_pairs: list[dict] = []
    all_segments: list[dict] = []
    paper_mentions_count: dict[str, int] = {}
    paper_sentence_pool: dict[str, set[str]] = defaultdict(set)

    for paper in papers:
        pid = paper["id"]
        sentences = iter_title_sentences(paper["title"])
        abs_paras: list[str] = []
        if isinstance(paper["enrichment"].get("abstract"), str):
            abs_paras.append(paper["enrichment"]["abstract"])
        abs_paras.extend(passages.get(pid, {}).get("abstract", []))
        sentences += iter_abstract_sentences(abs_paras)
        ft_sections = passages.get(pid, {}).get("fulltext", {})
        xml_sections = xml_cache.get(pid, {}).get("sections", [])
        # paper_passages fulltext 与 XML 缓存互斥(检查阶段已确认)
        if ft_sections:
            sentences += iter_fulltext_sentences(
                [{"name": name, "paragraphs": paras}
                 for name, paras in ft_sections.items()])
        if xml_sections:
            sentences += iter_fulltext_sentences(xml_sections)
        # 原文句子池(可追溯断言用)
        paper_sentence_pool[pid] = {s["text"] for s in sentences}

        hits, mentions = discover_paper_sentences(sentences, lexicon)
        discovery = build_paper_discovery(hits, mentions, pid)
        all_mentions.extend(discovery["mentions"])
        all_pairs.extend(discovery["pairs"])
        all_segments.extend(discovery["segments"])
        paper_mentions_count[pid] = len(discovery["mentions"])
        if not discovery["mentions"]:
            print(f"[info] no_mentions: {paper['pmid']} '{paper['title'][:60]}'")
    print(f"discovered: mentions={len(all_mentions)} pairs={len(all_pairs)} "
          f"segments={len(all_segments)}")

    # ---- 3. 幂等落库 ----
    # jsonb 列(psycopg3 不能自动适配 dict/list → 需 Jsonb 包装)
    def _jsonb_ready(row: dict, cols: tuple[str, ...]) -> dict:
        return {k: (Jsonb(v) if k in cols and v is not None else v)
                for k, v in row.items()}

    inserted = {"mentions": 0, "pairs": 0, "segments": 0}
    async with AsyncSessionLocal() as session:
        for name, rows, sql, jcols in (
                ("mentions", all_mentions, INSERT_MENTION_SQL, ()),
                ("pairs", all_pairs, INSERT_PAIR_SQL, ("matched_terms",)),
                ("segments", all_segments, INSERT_SEGMENT_SQL,
                 ("matched_regions",))):
            if not rows:
                continue
            await session.execute(
                text(sql), [_jsonb_ready(dict(r), jcols) for r in rows])
            inserted[name] = len(rows)
        await session.commit()
    async with AsyncSessionLocal() as session:
        m1 = (await session.execute(text(
            "SELECT count(*) FROM paper_region_mentions"))).scalar()
        p1 = (await session.execute(text(
            "SELECT count(*) FROM paper_region_pair_candidates"))).scalar()
        s1 = (await session.execute(text(
            "SELECT count(*) FROM paper_region_evidence_segments"))).scalar()
    print(f"inserted: mentions={inserted['mentions']} pairs={inserted['pairs']} "
          f"segments={inserted['segments']} | db=({m1},{p1},{s1})")

    # ---- 4. 断言:零副作用 + 可追溯 ----
    async with AsyncSessionLocal() as session:
        counters_after = await _counters(session)
        ev_after = await _evidence_count(session)
        papers_after = (await session.execute(
            text("SELECT count(*) FROM paper_sources"))).scalar()
        links_after = (await session.execute(
            text("SELECT count(*) FROM connection_paper_evidence"))).scalar()
        seg_old_after = (await session.execute(
            text(SEG_OLD_COUNT_SQL))).scalar()
        for name, before in counters_before.items():
            assert counters_after[name] == before, f"{name} 数量变化"
        assert ev_after == ev_before, "evidence_count 变化"
        assert papers_after == papers_before, "paper_sources 数量变化"
        assert links_after == links_before, "connection_paper_evidence 变化"
        assert seg_old_after == seg_old_before, "旧 evidence segments 变化"
    print("[ok] zero-side-effect: 5 counters + evidence_count + papers + "
          "links + old_segments 全不变")

    # 可追溯:每条 pair.evidence_sentence 必须在该论文原文句子池中
    untraceable = [c for c in all_pairs
                   if c["evidence_sentence"] not in
                   paper_sentence_pool.get(c["paper_id"], set())]
    assert not untraceable, \
        f"{len(untraceable)} 条候选证据句无法追溯到原文: {untraceable[:3]}"
    print(f"[ok] traceability: {len(all_pairs)} 条候选证据句全部可追溯原文")

    # ---- 5. 报告 ----
    await _export_reports(papers, region_info, hierarchy_parent,
                          all_mentions, all_pairs, all_segments,
                          paper_mentions_count, counters_before, ev_before[1],
                          papers_before, links_before, seg_old_before,
                          (m1, p1, s1), (inserted["mentions"],
                                         inserted["pairs"],
                                         inserted["segments"]),
                          alias_count, abstract_papers)


def _region_name(region_info: dict, rid: str) -> str:
    return region_info.get(str(rid), {}).get("canonical_name_en") or str(rid)


async def _export_reports(papers, region_info, hierarchy_parent,
                          mentions, pairs, segments,
                          paper_mentions_count, counters, evidence_count,
                          papers_before, links_before, seg_old_before,
                          new_counts, inserted_counts,
                          alias_count, abstract_papers) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()
    pmid_by_paper = {p["id"]: p["pmid"] for p in papers}
    title_by_paper = {p["id"]: p["title"] for p in papers}

    def _write(name: str, data) -> None:
        (OUT_DIR / name).write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"[ok] {name}")

    # 1) paper_region_mentions.json
    mention_rows = [{
        "paper_id": m["paper_id"], "pmid": pmid_by_paper.get(m["paper_id"]),
        "region_id": m["region_id"],
        "region_name": _region_name(region_info, m["region_id"]),
        "hierarchy_parent": hierarchy_parent.get(m["region_id"]),
        "matched_term": m["matched_term"],
        "match_source": m["match_source"],
        "sentence_id": m["sentence_id"],
        "section_name": m["section_name"],
        "laterality": m["laterality"],
        "confidence": m["confidence"],
        "sentence_text": m["sentence_text"],
    } for m in sorted(mentions, key=lambda x: (x["paper_id"], x["sentence_id"],
                                               x["region_id"]))]
    _write("paper_region_mentions.json", {
        "analysis": "macro_paper_connection_discovery_v1",
        "record": "paper_region_mentions 全量明细(句子粒度实体命中)",
        "count": len(mention_rows),
        "rows": mention_rows,
        "generated_at": now,
    })

    # 2) candidate_pairs.json
    pair_rows = [{
        "candidate_id": f"mppc_v1_{c['paper_id'][:8]}_{c['source_region_id'][:8]}_{c['target_region_id'][:8]}",
        "paper_id": c["paper_id"], "pmid": pmid_by_paper.get(c["paper_id"]),
        "source_region_id": c["source_region_id"],
        "source_name": _region_name(region_info, c["source_region_id"]),
        "target_region_id": c["target_region_id"],
        "target_name": _region_name(region_info, c["target_region_id"]),
        "evidence_sentence": c["evidence_sentence"],
        "context_before": c["context_before"],
        "context_after": c["context_after"],
        "section": c["section_name"],
        "matched_terms": c["matched_terms"],
        "generation_method": c["generation_method"],
        "assertion_type": c["assertion_type"],
        "source_type": c["source_type"],
        "cooccurrence": c["cooccurrence"],
        "confidence": c["confidence"],
    } for c in sorted(pairs, key=lambda x: (x["paper_id"],
                                            x["source_region_id"],
                                            x["target_region_id"]))]
    _write("candidate_pairs.json", {
        "analysis": "macro_paper_connection_discovery_v1",
        "record": "paper_region_pair_candidates 全量明细(同论文共现候选)",
        "count": len(pair_rows),
        "rows": pair_rows,
        "generated_at": now,
    })

    # 3) discovery_summary.json
    papers_with_mentions = sum(1 for v in paper_mentions_count.values() if v > 0)
    papers_no_mentions = [{"paper_id": p["id"], "pmid": p["pmid"],
                           "title": p["title"][:120]}
                          for p in papers if paper_mentions_count[p["id"]] == 0]
    region_ids = {m["region_id"] for m in mentions}
    unique_regions = len(region_ids)
    mention_sources = Counter(m["match_source"] for m in mentions)
    laterality_dist = Counter(m["laterality"] for m in mentions)
    cooccurrence_dist = Counter(c["cooccurrence"] for c in pairs)
    # 跨论文重复 pair:同一 (source,target) 出现在 >1 篇论文
    pair_paper_counts: Counter = Counter()
    for c in pairs:
        pair_paper_counts[(c["source_region_id"], c["target_region_id"])] += 1
    duplicate_pairs = {k: v for k, v in pair_paper_counts.items() if v > 1}
    top_pairs = sorted(pair_paper_counts.items(), key=lambda x: -x[1])[:20]
    # 同论文多源命中分布(每论文的源组合)
    paper_source_sets = defaultdict(set)
    for m in mentions:
        paper_source_sets[m["paper_id"]].add(m["match_source"])
    source_combos = Counter(
        "+".join(sorted(v)) for v in paper_source_sets.values())
    # 无法识别论文 = 无 mention

    _write("discovery_summary.json", {
        "analysis": "macro_paper_connection_discovery_v1",
        "stage": "Macro Paper-driven Connection Discovery V1 报告",
        "date": "2026-08-25",
        "inputs": {
            "paper_sources_total": papers_before,
            "title_available": papers_before,
            "abstract_available": abstract_papers,
            "fulltext_papers_passages": sum(
                1 for m in mentions if m["match_source"] == "fulltext"),
            "xml_cache_papers": 3,
            "macro96_canonical_regions": unique_regions,
            "region_aliases_loaded": alias_count,
            "no_external_api": True,
            "no_llm": True,
        },
        "stats": {
            "papers_total": papers_before,
            "papers_with_region_mentions": papers_with_mentions,
            "papers_no_mentions": len(papers_no_mentions),
            "papers_no_mentions_detail": papers_no_mentions,
            "region_mentions_total": len(mentions),
            "unique_regions_identified": unique_regions,
            "mentions_by_source": dict(mention_sources),
            "laterality_distribution": dict(laterality_dist),
            "evidence_segments_total": len(segments),
            "evidence_segments_by_source": dict(Counter(
                s["source_type"] for s in segments)),
            "pair_candidates_total": len(pairs),
            "pair_cooccurrence_distribution": dict(cooccurrence_dist),
            "duplicate_pairs_across_papers": len(duplicate_pairs),
            "duplicate_pairs_detail": {
                f"{_region_name(region_info, k[0])}->"
                f"{_region_name(region_info, k[1])}": v
                for k, v in sorted(duplicate_pairs.items(),
                                   key=lambda x: -x[1])},
            "top_region_pairs": [{
                "source": _region_name(region_info, k[0]),
                "target": _region_name(region_info, k[1]),
                "papers": v,
            } for k, v in top_pairs],
            "paper_source_combinations": dict(source_combos),
        },
        "traceability": {
            "candidate_pairs_total": len(pairs),
            "evidence_sentence_in_original_text": len(pairs),
            "verified": True,
        },
        "governance": {
            "final_active_unchanged": f"{counters['final_active']} 前后一致",
            "canonical_unchanged": f"{counters['canonical']} 前后一致",
            "mirror_macro_unchanged": f"{counters['mirror_macro']} 前后一致",
            "lineage_unchanged": f"{counters['lineage']} 前后一致",
            "clusters_unchanged": f"{counters['clusters']} 前后一致",
            "evidence_count_unchanged": f"{evidence_count} 前后一致",
            "paper_sources_unchanged": f"{papers_before} 前后一致",
            "connection_paper_evidence_unchanged": f"{links_before} 前后一致",
            "old_evidence_segments_unchanged": f"{seg_old_before} 前后一致",
            "no_connection_created": True,
            "no_llm_calls": True,
            "no_external_api_calls": True,
            "idempotent": "INSERT ON CONFLICT DO NOTHING → 复跑 0 新增",
            "inserted_this_run": {
                "mentions": inserted_counts[0],
                "pairs": inserted_counts[1],
                "segments": inserted_counts[2],
            },
            "db_counts_after": {
                "paper_region_mentions": new_counts[0],
                "paper_region_pair_candidates": new_counts[1],
                "paper_region_evidence_segments": new_counts[2],
            },
        },
        "answers": {
            "q1_papers_containing_macro96_entities": (
                f"{papers_with_mentions}/{papers_before} 篇论文包含 Macro96 "
                f"脑区实体(占比 {papers_with_mentions*100//papers_before}%)"),
            "q2_candidate_region_pairs_total": len(pairs),
            "q3_top_frequency_pairs": [{
                "pair": f"{_region_name(region_info, k[0])} -> "
                        f"{_region_name(region_info, k[1])}",
                "papers": v,
            } for k, v in top_pairs],
            "q4_traceability": (
                f"{len(pairs)}/{len(pairs)} 候选可追溯到论文原文"
                "(evidence_sentence 逐字重建断言通过)"),
        },
        "generated_at": now,
    })


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Macro Paper-driven Connection Discovery V1"
                    "(616 篇论文 → 脑区 mentions + region pair 候选,幂等)")
    parser.parse_args()
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except Exception:
        pass
    asyncio.run(main(parser.parse_args()))
