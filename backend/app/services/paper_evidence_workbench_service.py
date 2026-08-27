"""Paper Evidence Workbench —— 证据候选工作台（ranking_id 任务级）。

生命周期（本阶段目标,与用户规格一致）：
  任务上下文(ranking_id) → 论文检索(multi_search 既有) → 论文库去重入库
  (normalize_doi/paper_identity 既有) → 函数规则初筛片段(复用既有 macro
  evidence 纯函数) → LLM Semantic Review(仅判断“原文片段是否支持当前知识”) →
  Evidence Candidate(segment + SUPPORTED|PARTIAL_SUPPORT;NOT_SUPPORTED 保留
  审核记录但默认排除)。

严格复用（禁止另写一套字符串匹配）：
  - macro_paper_evidence_segments_service: split_sentences / region_terms /
    _find_first / _has_connection_verb / find_support_sentence(摘要单段+缩写保护)
  - macro_paper_fulltext_evidence_service: find_fulltext_evidence / _has_connect_word
    / parse_jats_xml(全文多节;复用其连接词+相邻句规则)
  - macro_connection_paper_import_service: normalize_doi / paper_identity /
    build_paper_insert(PMID→DOI→标准化title 去重优先级)
  - paper_search_multi: multi_search(多源检索+自动上下文词构建)

不创建 connection / 不写 final / 不进入 Human Review / 不触发重新 discovery。
"""
from __future__ import annotations

import asyncio
import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from psycopg.types.json import Jsonb
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.macro_paper_evidence_segments_service import (
    _find_first,
    region_terms,
    split_sentences,
)
from app.services.macro_paper_fulltext_evidence_service import (
    parse_jats_xml,
)
from app.services.macro_connection_paper_import_service import (
    build_paper_insert,
    normalize_doi,
    paper_identity,
)
from app.services.paper_search_multi import multi_search
from app.services.llm_providers import get_llm_provider
from app.services.settings_service import get_deepseek_runtime_config

# ── 常量 ─────────────────────────────────────────────────────────────────────────

RETRIEVAL_METHOD_ABSTRACT = "macro_segment_rules_v1"
RETRIEVAL_METHOD_FULLTEXT = "macro_fulltext_rules_v1"
RETRIEVAL_METHOD_FRAGMENT_SCREEN = "stage2_pure_function_screen"
DIRECTION = {"source": "source_region", "target": "target_region"}

XML_DIR = Path(__file__).resolve().parent.parent / "data" / "exports" / "macro_paper_fulltext_evidence" / "xml"

# ── 论文检索（上下文自动生成,复用 multi_search） ─────────────────────────────────

async def search_papers(
    source_region: str,
    target_region: str,
    connection_type: str | None,
    query_override: str | None = None,
    limit: int = 20,
) -> list[dict]:
    """当前任务自动生成检索上下文 → 多源检索（PubMed/OpenAlex/EuropePMC/S2）。

    返回统一论文记录（未入库;入库走 ensure_paper_library）。
    """
    context = {
        "source_region": source_region,
        "target_region": target_region,
        "object_type": "connection" if connection_type else "region",
        "_info_query": query_override or "",
    }
    return await multi_search(context, limit=limit)

# ── 统一论文入库(Paper Library resolve_or_create + 三级去重) ───────────────────

def normalize_title_key(title: str) -> str:
    """规范化标题键:小写 + 空白折叠(用于三级去重第 3 级)。"""
    return re.sub(r"\s+", " ", (title or "").strip().lower())


async def resolve_or_create_paper(session: AsyncSession, record: dict) -> dict:
    """resolve_or_create:PMID exact → normalized DOI exact → normalized title match。
    存在 → 复用原 paper_id;不存在 → 建 paper_sources 行(绝不创建第二行)。
    返回 {paper_id, created, reused}。并发/约束冲突时二次查找,仍失败才抛错。"""
    norm = normalize_doi(record.get("doi") or "") or None
    pmid = (record.get("pmid") or "").strip() or None
    title = (record.get("title") or "").strip()
    tkey = normalize_title_key(title)

    row = None
    if pmid:
        row = (await session.execute(text(
            "SELECT id FROM paper_sources WHERE pmid = :p ORDER BY created_at LIMIT 1"),
            {"p": pmid})).first()
    if row is None and norm:
        row = (await session.execute(text(
            "SELECT id FROM paper_sources WHERE normalized_doi = :d ORDER BY created_at LIMIT 1"),
            {"d": norm})).first()
    if row is None and len(tkey) >= 15:
        row = (await session.execute(text(
            """SELECT id FROM paper_sources
               WHERE lower(regexp_replace(coalesce(title, ''), '\\s+', ' ', 'g')) = :t
               ORDER BY created_at LIMIT 1"""),
            {"t": tkey})).first()
    if row:
        return {"paper_id": str(row[0]), "created": False, "reused": True}

    # 不存在 → 创建(build_paper_insert 兼容:year 需 str;需 authors/refs;metadata_json 需 Jsonb)
    rec_for_insert = dict(record)
    rec_for_insert.setdefault("authors", None)
    rec_for_insert.setdefault("refs", [])
    if rec_for_insert.get("year") not in (None, ""):
        rec_for_insert["year"] = str(rec_for_insert["year"])
    insert = build_paper_insert(rec_for_insert)
    insert.setdefault("abstract_available", bool(record.get("abstract_available")))
    insert.setdefault("fulltext_available", bool(record.get("fulltext_available")))
    insert["metadata_json"] = Jsonb(insert.get("metadata_json") or {"mode": "literature"})
    row = (await session.execute(text("""
        INSERT INTO paper_sources (source, doi, normalized_doi, pmid, title,
            journal, publication_year, abstract_available, fulltext_available, metadata_json)
        VALUES (:source, :doi, :normalized_doi, :pmid, :title, :journal,
                :publication_year, :abstract_available, :fulltext_available, :metadata_json)
        ON CONFLICT DO NOTHING
        RETURNING id"""), insert)).first()
    if row:
        return {"paper_id": str(row[0]), "created": True, "reused": False}

    # 并发冲突 → 再查一次;仍无 → 失败(交由调用方记录)
    row = None
    if norm:
        row = (await session.execute(text(
            "SELECT id FROM paper_sources WHERE normalized_doi = :d"), {"d": norm})).first()
    if row is None and pmid:
        row = (await session.execute(text(
            "SELECT id FROM paper_sources WHERE pmid = :p"), {"p": pmid})).first()
    if row:
        return {"paper_id": str(row[0]), "created": False, "reused": True}
    raise RuntimeError(f"无法解析论文: PMID={pmid or '-'} DOI={norm or '-'} title={title[:60] or '-'}")


async def ensure_paper_library(session: AsyncSession, records: list[dict]) -> list[dict]:
    """records → Paper Library 去重入库(统一走 resolve_or_create_paper)。

    返回 [{paper_id, pmid, doi, title, journal, year, source, state}] state:
    reuse(已入库)/created(刚刚入库)。全部论文以 paper_id 为后续身份引用。
    """
    out: list[dict] = []
    for rec in records:
        pmid = (rec.get("pmid") or "").strip() or None
        title = (rec.get("title") or "").strip()
        try:
            r = await resolve_or_create_paper(session, rec)
        except Exception:
            r = {"paper_id": None, "created": False, "reused": False}
        out.append({
            "paper_id": r["paper_id"],
            "pmid": pmid,
            "doi": rec.get("doi") or "",
            "title": title,
            "journal": rec.get("journal") or "",
            "year": rec.get("year"),
            "authors": rec.get("authors") or "",
            "source": rec.get("source") or "search",
            "abstract_available": bool(rec.get("abstract_available", False)),
            "fulltext_available": bool(rec.get("fulltext_available", False)),
            "state": "created" if r["created"] else "reuse",
        })
    await session.commit()
    return out

# ── 任务论文工作区（ranking_id 绑定） ────────────────────────────────────────────

async def bind_workspace_papers(session: AsyncSession, ranking_id: str, papers: list[dict]) -> int:
    """把(已入库)论文绑定到 ranking_id 的论文工作区(去重 per task)。"""
    n = 0
    for p in papers:
        if not p.get("paper_id"):
            continue
        row = (await session.execute(text("""
            INSERT INTO pew_papers (ranking_id, paper_id, role, title, authors, journal,
                publication_year, pmid, doi, normalized_doi, abstract_available,
                fulltext_available, source, retrieved_at)
            VALUES (:ranking_id, :paper_id, :role, :title, :authors, :journal,
                    :year, :pmid, :doi, :normalized_doi, :abstract_available,
                    :fulltext_available, :source, now())
            ON CONFLICT (ranking_id, paper_id) DO NOTHING
            RETURNING id"""), {
            "ranking_id": ranking_id, "paper_id": p["paper_id"],
            "role": p.get("role", "search"),
            "title": p.get("title"), "authors": p.get("authors"),
            "journal": p.get("journal"), "year": p.get("year"),
            "pmid": p.get("pmid"), "doi": p.get("doi"),
            "normalized_doi": normalize_doi(p.get("doi") or "") or None,
            "abstract_available": p.get("abstract_available", False),
            "fulltext_available": p.get("fulltext_available", False),
            "source": p.get("source", "search"),
        })).first()
        if row:
            n += 1
    await session.commit()
    return n

# ── 已有 Paper Discovery 线索导入（ranking → candidate_pair → paper） ─────────────

async def import_line_papers(session: AsyncSession, ranking_id: str) -> dict:
    """ranking → pair rows → paper_id → Paper Library 复用 → 任务论文工作区。

    只导入「发现阶段线索」,不作任何证据判定。
    """
    ranking = (await session.execute(text(
        "SELECT source_region_id, target_region_id FROM paper_connection_candidate_rankings WHERE id = :rid"),
        {"rid": ranking_id})).first()
    if ranking is None:
        return {"count": 0, "papers": [],
                "stats": {"clues": 0, "resolved": 0, "existing": 0, "created": 0,
                          "unresolved": 0, "task_papers": 0}}
    pairs = (await session.execute(text("""
        SELECT DISTINCT p.paper_id FROM paper_region_pair_candidates p
        WHERE p.source_region_id = :s AND p.target_region_id = :t"""), {
        "s": str(ranking[0]), "t": str(ranking[1]),
    })).all()
    paper_ids = [str(r[0]) for r in pairs if r[0]]
    if not paper_ids:
        return {"count": 0, "papers": [],
                "stats": {"clues": 0, "resolved": 0, "existing": 0, "created": 0,
                          "unresolved": 0, "task_papers": 0}}
    rows = (await session.execute(text("""
        SELECT id, pmid, doi, title, journal, publication_year,
               abstract_available, fulltext_available
        FROM paper_sources WHERE id = ANY(:ids)"""),
        {"ids": paper_ids})).all()
    papers = [{
        "paper_id": str(r[0]), "pmid": r[1], "doi": r[2] or "", "title": r[3] or "",
        "journal": r[4] or "", "year": r[5],
        "abstract_available": bool(r[6]), "fulltext_available": bool(r[7]),
        "role": "imported", "source": "paper_discovery",
    } for r in rows]
    bound = await bind_workspace_papers(session, ranking_id, papers)
    task_papers = (await session.execute(text(
        "SELECT count(*) FROM pew_papers WHERE ranking_id = :rid"),
        {"rid": ranking_id})).scalar() or 0
    return {
        "count": bound, "papers": papers,
        # 分类统计(线索数/已存在库/新增/无法解析/当前任务论文)
        "stats": {
            "clues": len(pairs),
            "resolved": len(papers),
            "existing": len(papers),
            "created": 0,
            "unresolved": len(pairs) - len(papers),
            "task_papers": int(task_papers),
        },
    }


async def auto_init_task_papers(session: AsyncSession, ranking_id: str,
                                force: bool = False) -> dict:
    """进入任务时自动整备 Paper Discovery 线索(幂等,手动「导入」已移除):
    - ranking → pair(region 对) → paper_id → Paper Library(复用,绝不重复创建) → bind workspace。
    - 已完成(pew_papers 存在行,非 force)→ skipped,直接读取现状;
    - 失败以单条粒度收集(不阻塞其他线索)。
    返回 {skipped, stats{clues,existing,created,unresolved,failed,task_papers}, failed:[{paper_id,title,reason}]}。
    """
    ranking = (await session.execute(text(
        "SELECT source_region_id, target_region_id FROM paper_connection_candidate_rankings WHERE id = :rid"),
        {"rid": ranking_id})).first()
    bound_cnt = (await session.execute(text(
        "SELECT count(*) FROM pew_papers WHERE ranking_id = :rid"),
        {"rid": ranking_id})).scalar() or 0
    if ranking is None:
        return {"skipped": False, "stats": {"clues": 0, "existing": 0, "created": 0,
                                            "unresolved": 0, "failed": 0, "task_papers": 0}, "failed": []}
    if bound_cnt > 0 and not force:
        clues = (await session.execute(text("""
            SELECT count(DISTINCT p.paper_id) FROM paper_region_pair_candidates p
            WHERE p.source_region_id = :s AND p.target_region_id = :t"""), {
            "s": str(ranking[0]), "t": str(ranking[1])})).scalar() or 0
        return {"skipped": True,
                "stats": {"clues": int(clues), "existing": int(bound_cnt), "created": 0,
                          "unresolved": 0, "failed": 0, "task_papers": int(bound_cnt)},
                "failed": []}

    pair_ids = (await session.execute(text("""
        SELECT DISTINCT p.paper_id FROM paper_region_pair_candidates p
        WHERE p.source_region_id = :s AND p.target_region_id = :t"""), {
        "s": str(ranking[0]), "t": str(ranking[1])})).all()
    ids = [str(r[0]) for r in pair_ids if r[0]]
    existing = 0
    created = 0
    unresolved = 0
    failed: list[dict] = []
    bind_rows: list[dict] = []
    for pid in ids:
        row = (await session.execute(text(
            "SELECT id, pmid, doi, title, journal, publication_year, abstract_available, fulltext_available "
            "FROM paper_sources WHERE id = :pid"), {"pid": pid})).first()
        if row is None:
            unresolved += 1
            failed.append({"paper_id": pid, "title": None,
                           "reason": "paper_sources 不存在(线索指向失效引用)"})
            continue
        existing += 1
        bind_rows.append({
            "paper_id": str(row[0]), "pmid": row[1], "doi": row[2] or "",
            "title": row[3] or "", "journal": row[4] or "", "year": row[5],
            "abstract_available": bool(row[6]), "fulltext_available": bool(row[7]),
            "role": "imported", "source": "paper_discovery",
        })
    await bind_workspace_papers(session, ranking_id, bind_rows)
    task_papers = (await session.execute(text(
        "SELECT count(*) FROM pew_papers WHERE ranking_id = :rid"),
        {"rid": ranking_id})).scalar() or 0
    return {"skipped": False,
            "stats": {"clues": len(ids), "existing": existing, "created": created,
                      "unresolved": unresolved, "failed": len(failed),
                      "task_papers": int(task_papers)},
            "failed": failed}

# ── 检索词建议 + 任务论文 Workspace 维护 ────────────────────────────────────────

CONNECTION_TYPE_SYNONYMS: dict[str, list[str]] = {
    "structural_connection": ["projection", "connection", "pathway", "tract", "connectivity"],
    "projection": ["connection", "pathway", "tract", "connectivity"],
    "functional_connectivity": ["functional connectivity", "connectivity", "resting-state", "correlation"],
    "association": ["association", "connection", "connectivity"],
}


async def _canonical_aliases(session: AsyncSession, name: str) -> list[str]:
    """canonical 名 + 别名(小写去重;英文优先;复用 canonical_region_aliases)。"""
    if not name:
        return []
    rows = (await session.execute(text("""
        SELECT a.alias FROM canonical_region_aliases a
        JOIN canonical_brain_regions c ON c.id = a.region_id
        WHERE lower(c.canonical_name_en) = lower(:n)"""), {"n": name})).all()
    terms: list[str] = []
    for t in [name] + [r[0] for r in rows]:
        t = (t or "").strip().lower()
        if len(t) >= 2 and t not in terms:
            terms.append(t)
    # 英文别名优先(中文别名对 PubMed 检索几乎无命中)
    return terms


async def suggest_discovery_queries(session: AsyncSession, source_name: str,
                                    target_name: str, connection_type: str | None) -> list[dict]:
    """默认检索词(2~4 条可编辑):canonical 对 + aliases + connection type 同义词。
    不生成新造别名;全部来自 canonical_region_aliases / 类型同义词表。"""
    src_terms = await _canonical_aliases(session, source_name)
    tgt_terms = await _canonical_aliases(session, target_name)
    src_core = (source_name or "").strip().lower()
    tgt_core = (target_name or "").strip().lower()
    syn = CONNECTION_TYPE_SYNONYMS.get(
        connection_type or "structural_connection",
        ["connection", "connectivity", "pathway", "tract"])

    def add(out: list[dict], q: str, label: str, source: str) -> None:
        if any(x["q"] == q for x in out):
            return
        out.append({"q": q, "label": label, "source": source})

    out: list[dict] = []
    add(out, f'"{src_core}" AND "{tgt_core}" AND {syn[0]}', "canonical + 连接类型", "canonical")
    add(out, f'"{src_core}" AND "{tgt_core}" AND connectivity', "canonical + connectivity", "type_synonym")
    alt_src = next((t for t in src_terms if t != src_core and len(t) > 2), None)
    alt_tgt = next((t for t in tgt_terms if t != tgt_core and len(t) > 2), None)
    if alt_src and alt_tgt:
        add(out, f'"{alt_src}" AND "{alt_tgt}" AND {syn[0]}', f"alias:{alt_src}·{alt_tgt}", "alias")
    elif alt_src:
        add(out, f'"{alt_src}" AND "{tgt_core}" AND {syn[0]}', f"alias:{alt_src}", "alias")
    elif alt_tgt:
        add(out, f'"{src_core}" AND "{alt_tgt}" AND {syn[0]}', f"alias:{alt_tgt}", "alias")
    _or_terms = list(dict.fromkeys([syn[1], syn[2], "tract", "connectivity"]))[:3]
    add(out, f'"{src_core}" AND "{tgt_core}" AND (' + " OR ".join(f'"{t}"' for t in _or_terms) + ')',
        f"canonical + ({'/'.join(_or_terms)})", "type_synonym")
    return out[:4]


async def remove_task_paper(session: AsyncSession, ranking_id: str, paper_id: str) -> int:
    """移出当前任务(Task Paper Workspace);论文自身仍保留在 Paper Library。"""
    result = await session.execute(text(
        "DELETE FROM pew_papers WHERE ranking_id = :rid AND paper_id = :pid"),
        {"rid": ranking_id, "pid": paper_id})
    await session.commit()
    return result.rowcount or 0

# ── 函数规则初筛（复用既有纯函数;不含 LLM） ──────────────────────────────────────

def _region_payload_terms(name: str | None,
                          aliases: list[str]) -> tuple[list[str], list[str]]:
    """term 词表 + “大写缩写独立成词”提示（复用 region_terms/_find_first）。"""
    terms = region_terms(name or "", aliases)
    return terms, []


async def _region_terms_from_db(session: AsyncSession, source_name: str,
                                 target_name: str) -> tuple[list[str], list[str]]:
    """canonical 名精确匹配取别名(复用 region_terms 缩写保护)。"""
    src_rows = (await session.execute(text("""
        SELECT a.alias FROM canonical_region_aliases a
        JOIN canonical_brain_regions c ON c.id = a.region_id
        WHERE lower(c.canonical_name_en) = lower(:n)"""),
        {"n": source_name})).all()
    tgt_rows = (await session.execute(text("""
        SELECT a.alias FROM canonical_region_aliases a
        JOIN canonical_brain_regions c ON c.id = a.region_id
        WHERE lower(c.canonical_name_en) = lower(:n)"""),
        {"n": target_name})).all()
    return (
        region_terms(source_name, [r[0] for r in src_rows]),
        region_terms(target_name, [r[0] for r in tgt_rows]),
    )
# ── Step 2: 系统函数筛选疑似证据片段(零 LLM;复用 split_sentences/_find_first/region_terms) ──

RELATION_KEYWORDS = (
    "project", "projects", "projection", "projecting",
    "connect", "connected", "connection", "connectivity",
    "pathway", "tract", "fiber", "fibre", "bundle",
    "innervat", "afferent", "efferent", "input", "output",
    "terminat", "originate",
    "correlat", "coupling", "functional connectivity",
)

TYPE_RELATION_BOOST: dict[str, tuple[str, ...]] = {
    "projection": ("projection", "project", "terminat", "innervat"),
    "structural_connection": ("tract", "fiber", "bundle", "connect"),
    "functional_connectivity": ("functional connectivity", "coupling", "correlat"),
}

PRIOR_SECTION_KEYS = ("results", "discussion", "introduction")


def _sentence_rel_terms(text: str) -> list[str]:
    """句中命中的关系词(全量;仅作 retrieval signal,不判定 connection_type)。"""
    tl = (text or "").lower()
    return [w for w in RELATION_KEYWORDS if w in tl]


def _section_priority_bonus(section_name: str) -> float:
    sn = (section_name or "").lower()
    return 0.02 if sn in PRIOR_SECTION_KEYS else 0.0


def _screen_paragraph(section_name: str, para: str, source_terms: list[str],
                      target_terms: list[str], boost_terms: tuple[str, ...]) -> list[dict]:
    """段内句级扫描(复用 _find_first 缩写边界防护):
    strong = 同句双命中 + 关系词;medium = 相邻句双命中 + 关系词;段级(同段不同句)+ 段内关系词。"""
    out: list[dict] = []
    sents = split_sentences(para)
    s_idx = [i for i, s in enumerate(sents) if _find_first(source_terms, s)[0]]
    t_idx = [i for i, s in enumerate(sents) if _find_first(target_terms, s)[0]]
    if not s_idx or not t_idx:
        return out

    def _mk(i: int, level: str, proximity: str, score: float,
            matched_s: str, matched_t: str, rels: list[str]) -> dict:
        sent = sents[i]
        return {
            "sentence": sent,
            "sentence_index": i + 1,
            "context_before": sents[i - 1] if i > 0 else "",
            "context_after": sents[i + 1] if i + 1 < len(sents) else "",
            "matched_source": matched_s, "matched_target": matched_t,
            "relation_keyword": rels[0] if rels else None,
            "relation_terms": rels,
            "proximity": proximity,
            "level": level,
            "confidence": min(0.92, score + _section_priority_bonus(section_name)),
        }

    def _rels(sent: str) -> list[str]:
        terms = _sentence_rel_terms(sent)
        if not terms:
            return []
        # type 高权词前置(ranking 权重) — 仅信号
        hl = [w for w in terms if w in boost_terms]
        return hl + [w for w in terms if w not in boost_terms]

    # strong:同句
    for i in s_idx:
        if i not in t_idx:
            continue
        sent = sents[i]
        rels = _rels(sent)
        if not rels:
            continue
        s_t, s_pos = _find_first(source_terms, sent)
        t_t, t_pos = _find_first(target_terms, sent)
        score = 0.90 if s_pos < t_pos else 0.86
        out.append(_mk(i, "strong", "same_sentence", score, s_t or "", t_t or "", rels))
    # medium:相邻句(±1)
    for i in s_idx:
        if i in t_idx:
            continue
        for j in (i - 1, i + 1):
            if j not in t_idx or j < 0 or j >= len(sents):
                continue
            rels = _rels(sents[i]) or _rels(sents[j])
            if not rels:
                continue
            t_t, _ = _find_first(target_terms, sents[j])
            s_t, _ = _find_first(source_terms, sents[i])
            out.append(_mk(i, "medium", "adjacent_sentence", 0.65, s_t or "", t_t or "", rels))
            break
    # 段级(同段不同句,无句级命中时)
    if not any(c["level"] in ("strong", "medium") for c in out):
        rels = _sentence_rel_terms(para)
        if rels:
            i = s_idx[0]
            s_t, _ = _find_first(source_terms, sents[i])
            t_i = t_idx[0]
            t_t, _ = _find_first(target_terms, sents[t_i])
            out.append(_mk(i, "medium", "same_paragraph", 0.58, s_t or "", t_t or "", rels))
    return out


def _screen_sections(sections: list[dict], source_terms: list[str], target_terms: list[str],
                     boost_terms: tuple[str, ...]) -> list[dict]:
    """逐 section 扫描;section 级 weak(跨段共现 + 段内关系词弱)互补产出。"""
    out: list[dict] = []
    for sec in sections:
        name = sec.get("name", "") or "Body"
        paras = sec.get("paragraphs", [])
        segs = []
        for para in paras:
            for seg in _screen_paragraph(name, para, source_terms, target_terms, boost_terms):
                seg["section_name"] = name
                segs.append(seg)
        if not segs:
            # weak:同一 section 存在 s 句与 t 句(不同句)且 section 文本含关系词
            all_sents = [s for p in paras for s in split_sentences(p)]
            s_set = [i for i, s in enumerate(all_sents) if _find_first(source_terms, s)[0]]
            t_set = [i for i, s in enumerate(all_sents) if _find_first(target_terms, s)[0]]
            if s_set and t_set and len(set(s_set) & set(t_set)) == 0:
                rels = _sentence_rel_terms(" ".join(all_sents))
                if rels:
                    i = s_set[0]
                    current = all_sents[i]
                    s_t, _ = _find_first(source_terms, current)
                    t_i = t_set[0]
                    t_t, _ = _find_first(target_terms, all_sents[t_i])
                    out.append({
                        "sentence": current,
                        "section_name": name,
                        "sentence_index": i + 1,
                        "context_before": all_sents[i - 1] if i > 0 else "",
                        "context_after": all_sents[i + 1] if i + 1 < len(all_sents) else "",
                        "matched_source": s_t or "", "matched_target": t_t or "",
                        "relation_keyword": rels[0],
                        "relation_terms": rels,
                        "proximity": "same_section",
                        "level": "weak",
                        "confidence": 0.45 + _section_priority_bonus(name),
                    })
        else:
            out.extend(segs)
    return out


async def run_rule_segments(session: AsyncSession, ranking_id: str,
                            paper_ids: list[str], connection_type: str | None = None) -> dict:
    """Step 2:系统纯函数筛选疑似证据片段(零 LLM;仅当前 Task Paper Workspace)。

    文本优先级:Full Text → Abstract → Title(标题只产 weak + source_type='title')。
    定级:strong(同句+关系词) / medium(相邻句|同段+关系词) / weak(同 section 跨段+关系词)。
    写入 pew_segments(幂等:唯一键冲突 → 更新等级/信号,不生成重复片段)。
    返回 {"inserted", "updated", "stats"{processed,fulltext,abstract,title,no_text,strong,medium,weak}}。
    """
    ranking = (await session.execute(text(
        "SELECT source_region_id, target_region_id FROM paper_connection_candidate_rankings WHERE id = :rid"),
        {"rid": ranking_id})).first()
    if ranking is None:
        return {"inserted": 0, "updated": 0, "stats": {"processed": 0, "fulltext": 0, "abstract": 0,
                                                       "title": 0, "no_text": 0, "strong": 0, "medium": 0, "weak": 0}}
    names = (await session.execute(text("""
        SELECT id, canonical_name_en FROM canonical_brain_regions WHERE id = ANY(:ids)"""),
        {"ids": [str(ranking[0]), str(ranking[1])]})).all()
    source_name = next((n for i, n in names if str(i) == str(ranking[0])), None) or ""
    target_name = next((n for i, n in names if str(i) == str(ranking[1])), None) or ""
    source_terms, target_terms = await _region_terms_from_db(
        session, source_name, target_name)
    boost_terms = TYPE_RELATION_BOOST.get(connection_type or "", ())

    stats = {"processed": 0, "fulltext": 0, "abstract": 0, "title": 0, "no_text": 0,
             "strong": 0, "medium": 0, "weak": 0}
    inserted = 0
    updated = 0
    for pid in paper_ids:
        paper = (await session.execute(text(
            "SELECT id, pmid, title FROM paper_sources WHERE id = :pid"),
            {"pid": pid})).first()
        if paper is None:
            continue
        pmid, title = paper[1], (paper[2] or "").strip()

        sections: list[dict] = []
        src_type = ""
        # 1) Full Text(paper_passages + JATS xml 缓存)
        ft_rows = (await session.execute(text(
            "SELECT section_title, passage_text FROM paper_passages WHERE paper_id = :pid AND source_scope = 'fulltext' ORDER BY paragraph_index"),
            {"pid": pid})).all()
        ft_map: dict[str, list[str]] = {}
        for st, pt in ft_rows:
            if pt:
                ft_map.setdefault(st or "Body", []).append(pt)
        if pmid:
            f = XML_DIR / f"{pmid}.xml"
            if f.exists():
                try:
                    parsed = parse_jats_xml(f.read_text(encoding="utf-8"))
                    for s in parsed.get("sections", []):
                        ft_map.setdefault(s.get("name") or "Body", []).extend(s.get("paragraphs", []))
                except Exception:
                    pass
        if ft_map:
            src_type = "fulltext"
            stats["fulltext"] += 1
            sections = [{"name": k, "paragraphs": v} for k, v in ft_map.items()]
        else:
            # 2) Abstract
            abs_paras: list[str] = []
            abs_rows = (await session.execute(text(
                "SELECT passage_text FROM paper_passages WHERE paper_id = :pid AND source_scope = 'abstract' ORDER BY paragraph_index"),
                {"pid": pid})).all()
            abs_paras += [r[0] for r in abs_rows if r[0]]
            if abs_paras:
                src_type = "abstract"
                stats["abstract"] += 1
                sections = [{"name": "Abstract", "paragraphs": abs_paras}]
            elif title:
                # 3) Title(仅低等级候选)
                src_type = "title"
                stats["title"] += 1
                sections = [{"name": "Title", "paragraphs": [title]}]
            else:
                stats["no_text"] += 1
                continue
        stats["processed"] += 1

        cands = _screen_sections(sections, source_terms, target_terms, boost_terms)
        if src_type == "title":
            # 标题只允许低等级 candidate,不得伪装成正文证据
            for c in cands:
                c["level"] = "weak"
                c["confidence"] = min(c["confidence"], 0.35)
        for c in cands:
            is_new = await _write_stage2_segment(
                session, ranking_id, pid, src_type, c)
            if is_new:
                inserted += 1
            else:
                updated += 1
            stats[c["level"]] += 1
    await session.commit()
    return {"inserted": inserted, "updated": updated, "stats": stats}


async def _write_stage2_segment(session, ranking_id, paper_id, source_type, cand) -> int:
    """写 Step-2 疑似片段(幂等:唯一键冲突 → 更新 等级/信号/上下文,绝不重复建行)。
    返回 1=新插入,0=更新。"""
    row = (await session.execute(text("""
        INSERT INTO pew_segments (ranking_id, paper_id, section_name, source_type,
            sentence_id, sentence_text, context_before, context_after,
            matched_source_term, matched_target_term, relation_keyword,
            matched_relation_terms, proximity, retrieval_method, rule_score, candidate_level)
        VALUES (:ranking_id, :paper_id, :section_name, :source_type,
                :sentence_id, :sentence_text, :context_before, :context_after,
                :matched_source_term, :matched_target_term, :relation_keyword,
                :matched_relation_terms, :proximity, :method, :rule_score, :level)
        ON CONFLICT (ranking_id, paper_id, sentence_text, section_name) DO UPDATE SET
            context_before = EXCLUDED.context_before,
            context_after = EXCLUDED.context_after,
            matched_source_term = EXCLUDED.matched_source_term,
            matched_target_term = EXCLUDED.matched_target_term,
            relation_keyword = EXCLUDED.relation_keyword,
            matched_relation_terms = EXCLUDED.matched_relation_terms,
            source_type = EXCLUDED.source_type,
            proximity = EXCLUDED.proximity,
            retrieval_method = EXCLUDED.retrieval_method,
            rule_score = EXCLUDED.rule_score,
            candidate_level = EXCLUDED.candidate_level
        RETURNING (xmax = 0) AS is_new"""), {
        "ranking_id": ranking_id, "paper_id": paper_id,
        "section_name": cand["section_name"], "source_type": source_type,
        "sentence_id": cand["sentence_index"],
        "sentence_text": cand["sentence"],
        "context_before": cand.get("context_before") or "",
        "context_after": cand.get("context_after") or "",
        "matched_source_term": cand["matched_source"],
        "matched_target_term": cand["matched_target"],
        "relation_keyword": cand.get("relation_keyword"),
        "matched_relation_terms": Jsonb(cand.get("relation_terms") or []),
        "proximity": cand["proximity"], "method": RETRIEVAL_METHOD_FRAGMENT_SCREEN,
        "rule_score": cand["confidence"], "level": cand["level"],
    })).first()
    return 1 if row and row[0] else 0

# ── Step 4: Evidence Candidate 整理(引用 segment/review;含完整性 Gate + 中文辅助翻译) ────

TRANSLATION_PROMPT_VERSION = "stage4_zh_v1"

TRANSLATION_SYSTEM = """Translate the provided biomedical/neuroscience evidence faithfully into Simplified Chinese.

Requirements:
- Preserve scientific meaning.
- Preserve brain-region terminology.
- Preserve directionality.
- Preserve relation semantics such as projection, tract, connectivity, pathway.
- Do not summarize.
- Do not infer.
- Do not strengthen or weaken the original claim.
- Do not add information not present in the source text.

Only output JSON {"translated_text": "..."} without any other text."""

TRANSLATION_USER = """## Original evidence sentence
{sentence}
## Optional context (only resolve pronouns/antecedents if needed; do not add content)
{context}

请输出简体中文译文 JSON。"""


async def _required_terms(session, ranking_id) -> tuple[list[str], list[str]]:
    """当前 ranking 的 source/target 别名词表(用于完整性 Gate)。"""
    rank_row = (await session.execute(text(
        "SELECT source_region_id, target_region_id "
        "FROM paper_connection_candidate_rankings WHERE id = :rid"),
        {"rid": ranking_id})).first()
    if not rank_row:
        return [], []
    names = (await session.execute(text(
        "SELECT id, canonical_name_en FROM canonical_brain_regions WHERE id = ANY(:ids)"),
        {"ids": [str(rank_row[0]), str(rank_row[1])]})).all()
    src_name = next((n for i, n in names if str(i) == str(rank_row[0])), "") or ""
    tgt_name = next((n for i, n in names if str(i) == str(rank_row[1])), "") or ""
    return await _region_terms_from_db(session, src_name, tgt_name)


async def sync_evidence_candidates(session: AsyncSession, ranking_id: str) -> dict:
    """Step 3 结果 → Evidence Candidate(只引用 segment/review,不复制原文)。

    规则:
    - SUPPORTED/PARTIAL → 完整性 Gate: supporting_phrase 必须同时命中当前 source+target 别名词表;
      通过 → candidate_status='candidate'(SUPPORTED 默认选中,PARTIAL 不选中);
      未通过 → 'review_required'(Step 3 误判嫌疑,不自动进入正式候选)。
    - UNCERTAIN/NOT_SUPPORTED/FAILED → 不进入候选表(保留 AI Review 历史)。
    幂等:UNIQUE(ranking_id,segment_id) 行冲突 → 更新候选级字段,不覆盖 selected/translated。
    """
    reviews = (await session.execute(text("""
        SELECT r.id, s.paper_id, r.segment_id, r.decision, r.confidence, r.evidence_type,
               r.supporting_phrase
        FROM pew_reviews r JOIN pew_segments s ON s.id = r.segment_id
        WHERE r.ranking_id = :rid ORDER BY r.created_at"""),
        {"rid": ranking_id})).all()
    if not reviews:
        return {"synced": 0, "stats": {}}
    source_terms, target_terms = await _required_terms(session, ranking_id)
    stats = {"candidate": 0, "review_required": 0}
    for r in reviews:
        if r[3] not in ("supported", "partial_support"):
            continue
        phrase = r[6] or ""
        s_hit = _find_first(source_terms, phrase)[0] is not None
        t_hit = _find_first(target_terms, phrase)[0] is not None
        status = "candidate" if (s_hit and t_hit) else "review_required"
        stats[status] += 1
        default_selected = status == "candidate" and r[3] == "supported"
        await session.execute(text("""
            INSERT INTO pew_evidence_candidates (ranking_id, segment_id, paper_id, llm_review_id,
                candidate_status, evidence_type, ai_decision, ai_confidence, selected_for_review)
            VALUES (:rid, :sid, :pid, :rid2, :status, :et, :dec, :conf, :sel)
            ON CONFLICT (ranking_id, segment_id) DO UPDATE SET
                llm_review_id = EXCLUDED.llm_review_id,
                candidate_status = EXCLUDED.candidate_status,
                evidence_type = EXCLUDED.evidence_type,
                ai_decision = EXCLUDED.ai_decision,
                ai_confidence = EXCLUDED.ai_confidence,
                updated_at = now()
            """), {"rid": ranking_id, "sid": r[2], "pid": r[1], "rid2": r[0],
                   "status": status, "et": r[5], "dec": r[3], "conf": r[4],
                   "sel": default_selected})
    await session.commit()
    return {"synced": len(reviews), "stats": stats}


async def get_or_create_translation(session: AsyncSession, segment_id: str,
                                     paper_id: str, sentence: str, context: str,
                                     prompt_version: str, force: bool = False) -> dict:
    """翻译资产读取器(先查库,后调模型):
    - segment_id + target_language='zh-CN' + prompt_version 命中 → 返回已有译文(reused,0 调用)
    - 未命中 → 调 LLM → INSERT(UNIQUE 并发保护;冲突则重查) → created
    - force(用户重新翻译)→ 生成版本号 v{n+1},旧译保留,返回最新 active
    返回 {translation_id, segment_id, translated_text, target_language, prompt_version, model, state}
    """
    # 1) 先查数据库(force 时也先查最新版,仅在需要新版本时才调模型)
    if not force:
        row = (await session.execute(text("""
            SELECT id, translated_text, translation_model, translation_prompt_version
            FROM evidence_segment_translations
            WHERE segment_id = :sid AND target_language = 'zh-CN'
              AND translation_prompt_version = :ver
            ORDER BY created_at DESC LIMIT 1"""),
            {"sid": segment_id, "ver": prompt_version})).first()
        if row:
            return {"translation_id": str(row[0]), "segment_id": segment_id,
                    "translated_text": row[1], "target_language": "zh-CN",
                    "prompt_version": row[2], "model": row[3], "state": "reused"}
    # 2) (force 或不存在)生成版本号: 基础版取当前 active;force 递增 v_n+1
    version = prompt_version
    if force:
        latest = (await session.execute(text("""
            SELECT translation_prompt_version FROM evidence_segment_translations
            WHERE segment_id = :sid AND target_language = 'zh-CN'
            ORDER BY created_at DESC LIMIT 1"""),
            {"sid": segment_id})).first()
        if latest:
            base = latest[0].rsplit('_v', 1)[0] if '_v' in latest[0] else latest[0]
            try:
                n = int(latest[0].rsplit('_v', 1)[1]) + 1
            except ValueError:
                n = 2
            version = f"{base}_v{n}"
    # 3) 调 LLM(生成后才写库)
    provider = get_llm_provider("deepseek")
    llm_cfg = get_deepseek_runtime_config()
    model = llm_cfg.default_model or "deepseek-chat"
    resp = await provider.complete_json(
        model=model,
        system_prompt=TRANSLATION_SYSTEM,
        user_prompt=TRANSLATION_USER.format(sentence=sentence[:600], context=context[:300]),
        temperature=0.1, max_tokens=800)
    if resp.error_message:
        raise RuntimeError(resp.error_message)
    translated_text = (resp.parsed_json or {}).get("translated_text") or ""
    if not translated_text.strip():
        raise RuntimeError("empty translation")
    usage = resp.usage.as_dict() if resp.usage else {}
    provenance = {
        "model": resp.model or model,
        "prompt_version": version,
        "prompt_tokens": int(usage.get("prompt_tokens") or 0),
        "completion_tokens": int(usage.get("completion_tokens") or 0),
        "total_tokens": int(usage.get("total_tokens") or 0),
    }
    row = (await session.execute(text("""
        INSERT INTO evidence_segment_translations (segment_id, paper_id, target_language,
            translated_text, translation_model, translation_prompt_version, provenance_json)
        VALUES (:sid, :pid, 'zh-CN', :txt, :model, :ver, :prov)
        ON CONFLICT (segment_id, target_language, translation_prompt_version) DO NOTHING
        RETURNING id"""), {
        "sid": segment_id, "pid": paper_id, "txt": translated_text,
        "model": resp.model or model, "ver": version, "prov": Jsonb(provenance),
    })).first()
    if row is None:
        # 并发冲突 → 重新读取已有译文
        existing = (await session.execute(text("""
            SELECT id, translated_text, translation_model, translation_prompt_version
            FROM evidence_segment_translations
            WHERE segment_id = :sid AND target_language = 'zh-CN'
              AND translation_prompt_version = :ver LIMIT 1"""),
            {"sid": segment_id, "ver": version})).first()
        return {"translation_id": str(existing[0]), "segment_id": segment_id,
                "translated_text": existing[1], "target_language": "zh-CN",
                "prompt_version": existing[2], "model": existing[3], "state": "reused"}
    return {"translation_id": str(row[0]), "segment_id": segment_id,
            "translated_text": translated_text, "target_language": "zh-CN",
            "prompt_version": version, "model": resp.model or model, "state": "created"}


async def translate_evidence_candidates(session: AsyncSession, ranking_id: str,
                                        segment_ids: list[str] | None = None,
                                        force: bool = False) -> dict:
    """Evidence Candidate 中文翻译 → evidence_segment_translations(生成一次,全流程复用)。

    统一走 get_or_create_translation:先查库(同 version)命中 → 复用 0 调用;
    未命中/force → 只对缺失段调 LLM。译文与 token 沉淀于翻译资产表,
    Candidate 仅按 segment_id 引用(J OIN 返回)。
    """
    rows = (await session.execute(text("""
        SELECT c.segment_id, c.paper_id, s.sentence_text, s.context_before, s.context_after
        FROM pew_evidence_candidates c
        JOIN pew_segments s ON s.id = c.segment_id
        WHERE c.ranking_id = :rid AND c.candidate_status = 'candidate'
        AND c.ai_decision IN ('supported', 'partial_support')
        AND (CAST(:ids AS uuid[]) IS NULL OR c.segment_id = ANY(CAST(:ids AS uuid[])))
        ORDER BY c.created_at"""),
        {"rid": ranking_id, "ids": segment_ids})).all()
    results = []
    translated = reused = kept = 0
    total_tokens = 0
    model = None
    for r in rows:
        sid, pid, sentence, ctx_b, ctx_a = r
        if not (sentence or '').strip():
            kept += 1
            results.append({"segment_id": str(sid), "state": "no_text"})
            continue
        try:
            out = await get_or_create_translation(
                session, str(sid), str(pid), sentence,
                " ".join(x for x in (ctx_b or "", ctx_a or "") if x),
                TRANSLATION_PROMPT_VERSION, force=force)
            if out["state"] == "created":
                translated += 1
                prov_row = (await session.execute(text(
                    "SELECT provenance_json FROM evidence_segment_translations WHERE id = :tid"),
                    {"tid": out["translation_id"]})).first()
                tokens = (prov_row[0] or {}).get("total_tokens", 0) if prov_row else 0
                total_tokens += int(tokens or 0)
            else:
                reused += 1
            model = out["model"] or model
            results.append({
                "translation_id": out["translation_id"], "segment_id": out["segment_id"],
                "translated_text": out["translated_text"],
                "target_language": out["target_language"],
                "prompt_version": out["prompt_version"], "model": out["model"],
                "state": out["state"],
            })
        except Exception as exc:
            kept += 1
            results.append({"segment_id": str(sid), "state": "failed", "reason": str(exc)[:120]})
    await session.commit()
    return {"translated": translated, "reused": reused, "kept": kept,
            "total_tokens": total_tokens, "model": model, "results": results}


# ── LLM Semantic Review（仅判定片段是否支持当前知识;不搜库不重新提取） ──────────────

REVIEW_PROMPT_VERSION = "stage3_v1"

REVIEW_SYSTEM = """你是神经科学知识图谱的语义审核员。你的唯一职责:
判断「给定论文原文片段(及其局部上下文)是否实际支持当前待验证知识关系」。

严格原则:
1. 只能根据提供的论文原文判断;不得检索、不得补全、不得依据医学常识替论文补充结论。
2. source 与 target 同时出现 ≠ 存在连接。
3. 疾病研究中间接提及两个脑区 ≠ 连接证据。
4. ROI 列表 / 解剖区域枚举 / 统计学脑区列表 / 分区说明(如 "95 anatomical regions"、"gray matter regions including ...") ≠ 连接证据 ——
   即使 source/target 词均命中,也判 not_supported,不得依据列举顺序或位置推断连接。
5. "associated with disease" ≠ region connection。
6. 判 supported 必须存在明确关系语义(投射/连接/通路/纤维束/神经支配/耦合等),且与当前事实一致。
7. connection_type 必须与原文关系类型一致才支持。
8. direction:原文无法确定时输出 undetermined,严禁臆测。
9. 背景性描述最多 partial(evidence_type=context),不能升级为 direct。
10. 不确定时优先 uncertain / not_supported;禁止制造假阳性。
11. supporting_phrase 必须逐字来自输入原文;不存在则 null,禁止生成原文不存在的短语。
12. 只输出 JSON,无其他文字。

## 输出 JSON
{"decision":"supported"|"partial_support"|"uncertain"|"not_supported",
 "confidence":0.0-1.0,
 "evidence_type":"direct"|"indirect"|"context"|"contradictory"|"none",
 "connection_type_supported":"projection"|"structural_connection"|"functional_connectivity"|"association"|"unknown",
 "direction_support":"source_to_target"|"target_to_source"|"bidirectional"|"undetermined",
 "reason":"...",
 "supporting_phrase":"..."|null,
 "contradiction_reason":null|"..."
}"""

REVIEW_USER = """## 当前待验证知识(Candidate Fact)
- source: {source_region}
- target: {target_region}
- connection_type: {connection_type}
- direction: {direction}
- granularity: macro

## 论文(仅元数据)
- title: {title}
- pmid: {pmid}

## 候选原文片段(仅局部上下文)
- section: {section}
- original_sentence: {sentence}
- previous_sentence: {context_before}
- next_sentence: {context_after}

## 规则初筛信号(仅表明"疑似",不代表真值)
- candidate_level: {candidate_level}
- rule_score: {rule_score}
- matched_source_term: {matched_source}
- matched_target_term: {matched_target}
- matched_relation_terms: {relation_terms}
- proximity: {proximity}
- source_type: {source_type}

请严格按 SYSTEM 原则判定并输出 JSON。"""


async def run_semantic_review(session: AsyncSession, ranking_id: str,
                              segment_ids: list[str],
                              connection_type_param: str | None = None,
                              force: bool = False) -> dict:
    """Step 3:批量 LLM 语义审核(并发 5;单条重试 1 次;失败不中断整批)。

    仅写入 pew_segments→pew_reviews;同 prompt_version 已审的 segment 直接复用(跳过),
    用户「重新 AI 审核」才覆盖重调。返回 {results, model, summary}。
    """
    start = time.monotonic()
    rows = (await session.execute(text("""
        SELECT s.id, s.paper_id, s.section_name, s.sentence_text,
               s.context_before, s.context_after,
               s.matched_source_term, s.matched_target_term, s.proximity, s.rule_score,
               s.candidate_level, s.matched_relation_terms, s.source_type,
               p.title, p.pmid, p.doi,
               r.id AS review_id, r.prompt_version, r.decision
        FROM pew_segments s
        JOIN paper_sources p ON p.id = s.paper_id
        LEFT JOIN pew_reviews r ON r.segment_id = s.id
        WHERE s.id = ANY(:ids) AND s.ranking_id = :rid ORDER BY s.created_at"""),
        {"ids": segment_ids, "rid": ranking_id})).all()
    if not rows:
        return {"results": [], "model": None, "summary": {}}

    rank_row = (await session.execute(text(
        "SELECT source_region_id, target_region_id "
        "FROM paper_connection_candidate_rankings WHERE id = :rid"),
        {"rid": ranking_id})).first()
    src_name = tgt_name = ""
    if rank_row:
        nm = (await session.execute(text(
            "SELECT id, canonical_name_en FROM canonical_brain_regions "
            "WHERE id = ANY(:ids)"),
            {"ids": [str(rank_row[0]), str(rank_row[1])]})).all()
        src_name = next((n for i, n in nm if str(i) == str(rank_row[0])), "") or ""
        tgt_name = next((n for i, n in nm if str(i) == str(rank_row[1])), "") or ""

    provider = get_llm_provider("deepseek")  # 系统默认 DeepSeek(settings 源)
    llm_cfg = get_deepseek_runtime_config()
    model = llm_cfg.default_model or "deepseek-chat"
    temperature = llm_cfg.temperature if llm_cfg.temperature is not None else 0.1
    max_tokens = llm_cfg.max_tokens or 1500
    sem = asyncio.Semaphore(5)
    results: list[dict] = []
    total_tokens = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    skipped_reviews = 0

    def _system_prompt(r) -> str:
        return REVIEW_SYSTEM

    def _user_prompt(r, connection_type: str) -> str:
        return REVIEW_USER.format(
            source_region=src_name or "",
            target_region=tgt_name or "",
            connection_type=connection_type or "",
            direction="unknown",
            title=r[13] or "", pmid=r[14] or "",
            section=r[2] or "", sentence=r[3] or "",
            context_before=r[4] or "", context_after=r[5] or "",
            candidate_level=r[10] or "",
            rule_score=r[9] or 0,
            matched_source=r[6] or "", matched_target=r[7] or "",
            relation_terms=", ".join(r[11] or []),
            proximity=r[8] or "", source_type=r[12] or "",
        )

    async def one(r) -> None:
        nonlocal skipped_reviews
        # 同 prompt_version 已审核 → 直接复用(0 调用);force(用户「重新 AI 审核」)除外
        if not force and r[15] and r[15] == REVIEW_PROMPT_VERSION and r[16]:
            skipped_reviews += 1
            return
        system_prompt = _system_prompt(r)
        user_prompt = _user_prompt(r, connection_type_param or "")
        raw_response: dict = {}
        usage = {}
        parsed: dict = {"decision": "uncertain", "confidence": None, "evidence_type": None,
                        "connection_type_supported": None, "direction_support": None,
                        "reason": "LLM 调用失败", "supporting_phrase": None,
                        "contradiction_reason": None}
        failed = True
        model_name = model
        async with sem:
            for attempt in (0, 1):  # 1 次重试
                try:
                    response = await provider.complete_json(
                        model=model, system_prompt=system_prompt,
                        user_prompt=user_prompt,
                        temperature=temperature, max_tokens=max_tokens,
                        timeout_seconds=120)
                    if response.error_message:
                        raise RuntimeError(response.error_message)
                    raw_response = response.raw_response_redacted if hasattr(response, "raw_response_redacted") else {}
                    parsed = _normalize_review(response.parsed_json or {})
                    usage = response.usage.as_dict() if response.usage else {}
                    model_name = response.model or model
                    failed = False
                    break
                except Exception as exc:
                    if attempt == 0:
                        continue
                    parsed = {"decision": "uncertain", "confidence": None, "evidence_type": None,
                              "connection_type_supported": None, "direction_support": None,
                              "reason": f"LLM 调用失败: {exc}", "supporting_phrase": None,
                              "contradiction_reason": None}
                    raw_response = {"error": str(exc)[:200]}
        # token 汇总
        for k in ("prompt_tokens", "completion_tokens", "total_tokens"):
            total_tokens[k] += int(usage.get(k) or 0)
        await session.execute(text("""
            INSERT INTO pew_reviews (ranking_id, segment_id, decision, confidence,
                evidence_type, reason, suggested_connection_type, direction_support,
                connection_type_supported, supporting_phrase, contradiction_reason,
                model_name, raw_response_json, prompt_version, token_usage, failed, reviewed_at)
            VALUES (:rid, :sid, :d, :c, :et, :reason, :sct, :ds,
                :cts, :sp, :cr, :model, :raw, :version, :usage, :failed, now())
            ON CONFLICT (segment_id) DO UPDATE SET
                decision = EXCLUDED.decision, confidence = EXCLUDED.confidence,
                evidence_type = EXCLUDED.evidence_type, reason = EXCLUDED.reason,
                suggested_connection_type = EXCLUDED.suggested_connection_type,
                direction_support = EXCLUDED.direction_support,
                connection_type_supported = EXCLUDED.connection_type_supported,
                supporting_phrase = EXCLUDED.supporting_phrase,
                contradiction_reason = EXCLUDED.contradiction_reason,
                model_name = EXCLUDED.model_name, raw_response_json = EXCLUDED.raw_response_json,
                prompt_version = EXCLUDED.prompt_version, token_usage = EXCLUDED.token_usage,
                failed = EXCLUDED.failed, reviewed_at = now()
            """),
            {"rid": ranking_id, "sid": r[0], "d": parsed["decision"],
             "c": parsed["confidence"], "et": parsed["evidence_type"],
             "reason": parsed["reason"], "sct": parsed["connection_type_supported"],
             "ds": parsed["direction_support"], "cts": parsed["connection_type_supported"],
             "sp": parsed["supporting_phrase"], "cr": parsed["contradiction_reason"],
             "model": model_name, "raw": Jsonb({"parsed": parsed, "raw": raw_response}),
             "version": REVIEW_PROMPT_VERSION, "usage": Jsonb(usage or {}),
             "failed": failed})
        results.append({"segment_id": str(r[0]), "decision": parsed["decision"],
                        "failed": failed, "model": model_name,
                        **{k: parsed[k] for k in ("confidence", "evidence_type", "reason",
                                                  "connection_type_supported", "direction_support",
                                                  "supporting_phrase", "contradiction_reason")}})

    under_review = [r for r in rows if force or not (r[15] and r[15] == REVIEW_PROMPT_VERSION and r[16])]
    pending_skips = len(rows) - len(under_review)
    await asyncio.gather(*(one(r) for r in under_review))
    await session.commit()
    from collections import Counter
    dcount = Counter(x["decision"] for x in results)
    return {
        "results": results, "model": model,
        "summary": {
            "reviewed": len(results),
            "skipped": skipped_reviews + pending_skips,
            "by_decision": dict(dcount),
            "failed": sum(1 for x in results if x["failed"]),
            "total_tokens": total_tokens,
            "elapsed_seconds": round(time.monotonic() - start, 1),
        },
    }


def _normalize_review(raw) -> dict:
    decision = str((raw or {}).get("decision", "uncertain"))
    if decision not in ("supported", "partial_support", "uncertain", "not_supported"):
        decision = "uncertain"
    conf = raw.get("confidence")
    try:
        conf = max(0.0, min(1.0, float(conf))) if conf is not None else None
    except (TypeError, ValueError):
        conf = None
    et = raw.get("evidence_type")
    if et not in ("direct", "indirect", "context", "contradictory", "none"):
        et = None
    cts = raw.get("connection_type_supported")
    if cts not in ("projection", "structural_connection", "functional_connectivity", "association", "unknown"):
        cts = None
    ds = raw.get("direction_support")
    if ds not in ("source_to_target", "target_to_source", "bidirectional", "undetermined"):
        ds = None
    return {
        "decision": decision, "confidence": conf, "evidence_type": et,
        "reason": raw.get("reason") or "",
        "connection_type_supported": cts,
        "suggested_connection_type": cts,
        "direction_support": ds,
        "supporting_phrase": raw.get("supporting_phrase") or None,
        "contradiction_reason": raw.get("contradiction_reason") or None,
    }
