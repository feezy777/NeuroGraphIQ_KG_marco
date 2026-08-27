"""Macro Evidence Literature Backfill V1 — 文献线索解析(纯函数,零写入)。

目标:将 Macro Final Connection 对应 mirror evidence_text 中的文献线索
(作者+年份)解析为结构化 candidate,并与本地 paper 库(paper_sources)
匹配,产出 A/B/C 质量分级 —— 为后续 PubMed API 文献回填提供候选清单。

数据语义(2026-08-25 探查确认):
* mirror_region_connections.evidence_text(5716 条)含文献线索:
  196 条 "et al"、320 条年份括号,0 DOI/PMID;形态: "Author et al. (2007)"、
  "(Author et al., 2009)"、"A & B (1984)"、"Mesulam, M.M. (1995). Title. Journal."
* 项目已有 paper 资源:paper_sources 570 行(europepmc,全含 publication_year +
  metadata_json.authors + doi + pmid),paper_evidence_extraction_items 340 行,
  mirror_evidence_records 99,481 行(macro 连接层仅 2 行有 paper 关联)。
* macro 连接层结构化文献引用覆盖 2/5720 —— 文献级引用缺失确认。
* 本模块零写入:不建表(已有 paper_sources)、不改 evidence_reference、
  不调 LLM/PubMed、不改 Final 状态。

candidate 字段(任务 2 格式):
{
  connection_id, author, year, original_text,
  match_status: "A_unique" | "B_multiple" | "C_local_unmatched" | "C_no_clue",
  possible_reference: "{doi=..., pmid=..., title=...}"(匹配时)
}
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Iterable

YEAR = r"(?:1[89]\d{2}|20\d{2})[a-z]?"
NAME = r"[A-Z][A-Za-z'\-]+"
ETAL = r"et al\.?"
# 作者组:1-3 词姓氏 + 可选 &/and 第二作者 + 可选 et al./缩写(任意序,可重复)
AUTHORS_GROUP = (
    rf"(?:{NAME}\s+){{0,2}}{NAME}"
    rf"(?:\s*(?:&|and)\s+(?:{NAME}\s+){{0,2}}{NAME})?"
    rf"(?:\s*,?\s*(?:{ETAL}|[A-Z]\.?))*"
)
# 形态 A: "Author et al. (2007)" / "A & B (1984)" / "Mesulam, M.M. (1995)"
PAT_AUTHOR_YEAR = re.compile(
    rf"(?<![A-Za-z])({AUTHORS_GROUP})\s*,?\s*\(\s*({YEAR})\s*\)")
# 形态 B: "(Habas et al., 2009)" / "(Greicius et al., 2004; Buckner et al., 2008)"
# —— 括号内作者, 年份(支持分号分隔多引用,最多 3 组)
PAT_PAREN_YEAR = re.compile(
    rf"\(\s*({AUTHORS_GROUP})\s*,\s*({YEAR})"
    rf"(?:\s*;\s*({AUTHORS_GROUP})\s*,\s*({YEAR}))?"
    rf"(?:\s*;\s*({AUTHORS_GROUP})\s*,\s*({YEAR}))?"
    rf"\s*\)")

STATUS_UNIQUE = "A_unique"          # 本地库唯一匹配
STATUS_MULTIPLE = "B_multiple"      # 本地库多篇候选
STATUS_UNMATCHED = "C_local_unmatched"  # 解析成功但本地库无匹配
STATUS_NO_CLUE = "C_no_clue"        # 无文献线索


def parse_citation(text: str | None) -> list[dict]:
    """单条 evidence_text → [{author, year, original_text}]。

    同时跑两种形态正则,按 (原文起始位置) 去重排序。
    """
    if not text:
        return []
    out: list[dict] = []
    seen: set[tuple[int, str, str]] = set()
    for pat in (PAT_AUTHOR_YEAR, PAT_PAREN_YEAR):
        for m in pat.finditer(text):
            # 括号形态:第 1-2 组是作者+年份;分号后第 3-6 组为附加引用
            pairs = [(m.group(1), m.group(2))]
            if m.lastindex and m.lastindex >= 3 and m.group(3):
                pairs.append((m.group(3), m.group(4)))
            if m.lastindex and m.lastindex >= 5 and m.group(5):
                pairs.append((m.group(5), m.group(6)))
            for (author_raw, year) in pairs:
                author = re.sub(r"\s+", " ", author_raw).strip().rstrip(",")
                key = (m.start(), author, year)
                if key in seen:
                    continue
                seen.add(key)
                out.append({"author": author, "year": year,
                            "original_text": m.group(0),
                            "original_text_pos": m.start()})
    out.sort(key=lambda c: (c["original_text_pos"], c["author"], c["year"]))
    return out


def extract_surnames(author_string: str) -> list[str]:
    """作者串 → 姓氏列表(小写,去 et al/缩写)。

    "Goldman-Rakic et al." → ["goldman-rakic"]
    "Petrides & Pandya"   → ["petrides", "pandya"]
    "Von Der Heide et al."→ ["von", "der", "heide"]  → 组合与单词均匹配
    "Mesulam, M.M."       → ["mesulam"]
    """
    s = re.sub(r"\bet al\.?", "", author_string)
    s = s.replace("&", ",").replace(" and ", ",")
    parts = [p.strip() for p in s.split(",") if p.strip()]
    names: list[str] = []
    for p in parts:
        for w in re.split(r"\s+", p):
            if not w:
                continue
            core = w.replace(".", "")
            # 跳过大写缩写("LD" / "PS" / "M.M." / "N.R."),保留真实姓氏
            if core.isupper() and len(core) <= 3:
                continue
            names.append(w.lower())
    return names


def build_local_paper_library(paper_rows: Iterable[dict]) -> list[dict]:
    """paper_sources 行 → 本地匹配库。

    paper_rows: {publication_year, metadata_json{authors}, doi, pmid, title,
    journal, source}
    """
    lib = []
    for r in paper_rows:
        meta = r.get("metadata_json") or {}
        authors = meta.get("authors") or ""
        year = r.get("publication_year")
        if not year or not authors:
            continue
        lib.append({
            "surnames": extract_surnames(authors),
            "year": int(year),
            "doi": r.get("doi"), "pmid": str(r.get("pmid") or ""),
            "title": r.get("title"), "journal": r.get("journal"),
            "source": r.get("source"),
            "authors": authors,
        })
    return lib


def match_citation(author: str, year: str, library: list[dict]) -> list[dict]:
    """(作者串, 年份) → 本地库匹配行(姓氏交集 + 同年)。"""
    surnames = extract_surnames(author)
    if not surnames:
        return []
    y = int(re.match(r"\d{4}", year).group(0)) if re.match(r"\d{4}", year) else None
    if y is None:
        return []
    hits = []
    for p in library:
        if p["year"] != y:
            continue
        if any(sn in p["surnames"] for sn in surnames) or \
           any(pn in surnames for pn in p["surnames"]):
            hits.append(p)
    return hits


def classify_match(matches: list[dict]) -> tuple[str, str]:
    """匹配数 → (match_status, possible_reference 文本)。"""
    if not matches:
        return STATUS_UNMATCHED, ""
    if len(matches) == 1:
        m = matches[0]
        ref = ("{doi=%s, pmid=%s, title=%s, journal=%s}" % (
            m['doi'] or '-', m['pmid'] or '-', m['title'] or '-',
            m['journal'] or '-'))
        return STATUS_UNIQUE, ref
    refs = "; ".join(f"{m['doi'] or m['pmid'] or m['title']}" for m in matches[:5])
    return STATUS_MULTIPLE, refs


def scan_literature_candidates(
    finals: list[dict],
    lineage_map: dict[str, list[dict]],
    mirror_map: dict[str, dict],
    library: list[dict],
) -> list[dict]:
    """全量扫描:final → lineage → mirror evidence_text → 解析 → 匹配。

    finals: {id, canonical_connection_id, connection_code}
    lineage_map: {canonical_id: [{mirror_connection_ids}]}
    mirror_map: {mirror_id: {evidence_text}}
    library: build_local_paper_library 输出

    returns: candidates [{connection_id, connection_code, author, year,
    original_text, evidence_text_snippet, match_status, possible_reference,
    match_count}]
    """
    out: list[dict] = []
    seen: set[tuple[str, str, str]] = set()
    for f in finals:
        cid = str(f.get("id") or "")
        ccid = str(f.get("canonical_connection_id") or "")
        texts: list[str] = []
        for lr in lineage_map.get(ccid) or []:
            for mid in lr.get("mirror_connection_ids") or []:
                m = mirror_map.get(str(mid))
                if m and m.get("evidence_text"):
                    texts.append(str(m["evidence_text"]))
        for t in texts:
            for c in parse_citation(t):
                key = (cid, c["author"], c["year"])
                if key in seen:
                    continue
                seen.add(key)
                matches = match_citation(c["author"], c["year"], library)
                status, ref = classify_match(matches)
                out.append({
                    "connection_id": cid,
                    "connection_code": f.get("connection_code"),
                    "author": c["author"],
                    "year": c["year"],
                    "original_text": c["original_text"],
                    "evidence_text_snippet": t[:120],
                    "match_status": status,
                    "possible_reference": ref,
                    "match_count": len(matches),
                })
    out.sort(key=lambda c: (c["connection_id"], c["author"], c["year"]))
    return out


def literature_match_report(candidates: list[dict]) -> dict:
    """candidate 集合 → 统计报告(任务 3)。

    * 按 candidate 计数:总 / A_unique / B_multiple / C_local_unmatched /
      C_no_clue(本层无 no_clue —— 无线索不进 candidate;在连接级统计)
    * 按连接计数:有线索连接数 / 至少一 A / 至少一 B / 仅 C
    * 去重 (author, year) 元组
    """
    n = len(candidates)
    by_status = Counter(c["match_status"] for c in candidates)
    conn_ids = {c["connection_id"] for c in candidates}
    conn_with_a = {c["connection_id"] for c in candidates
                   if c["match_status"] == STATUS_UNIQUE}
    conn_with_b = {c["connection_id"] for c in candidates
                   if c["match_status"] == STATUS_MULTIPLE}
    conn_with_match = {c["connection_id"] for c in candidates
                       if c["match_status"] in (STATUS_UNIQUE, STATUS_MULTIPLE)}
    pairs = {(c["author"], c["year"]) for c in candidates}
    return {
        "by_candidate": {
            "total": n,
            "A_unique": by_status.get(STATUS_UNIQUE, 0),
            "B_multiple": by_status.get(STATUS_MULTIPLE, 0),
            "C_local_unmatched": by_status.get(STATUS_UNMATCHED, 0),
        },
        "by_connection": {
            "with_citation_clue": len(conn_ids),
            "with_unique_match": len(conn_with_a),
            "with_ambiguous_match": len(conn_with_b),
            "with_any_match": len(conn_with_match),
        },
        "distinct_author_year_pairs": len(pairs),
    }


def priority_literature_stats(
    candidates: list[dict],
    priority_connection_ids: set[str],
    total_priority: int,
) -> dict:
    """829 条低质量连接(evidence enrichment A 类)的文献线索统计(任务 4)。

    * 有文献线索(parse 出 ≥1 candidate)的连接数
    * 其中可匹配(A_unique + B_multiple)数量
    * 无法匹配(无线索或本地无匹配)数量
    """
    relevant = [c for c in candidates if c["connection_id"] in priority_connection_ids]
    with_clue = {c["connection_id"] for c in relevant}
    with_match = {c["connection_id"] for c in relevant
                  if c["match_status"] in (STATUS_UNIQUE, STATUS_MULTIPLE)}
    matched_status = Counter(c["match_status"] for c in relevant)
    return {
        "priority_total": total_priority,
        "with_citation_clue": len(with_clue),
        "no_citation_clue": total_priority - len(with_clue),
        "matchable": len(with_match),
        "matchable_unique": sum(1 for cid in with_match
                                if any(c["match_status"] == STATUS_UNIQUE
                                       for c in relevant if c["connection_id"] == cid)),
        "unmatchable": total_priority - len(with_match),
        "by_candidate_status": dict(matched_status),
        "priority_candidates": [c for c in relevant],
    }
