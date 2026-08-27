"""Macro Evidence Literature PubMed Backfill V1 — 匹配分级核心(纯函数)。

目标:对 Literature Backfill 解析出的 C_local_unmatched 文献线索
(author + year),按 本地 paper_sources → PubMed API 的匹配策略补充
DOI/PMID,生成 macro_evidence_pubmed_candidates —— 只生成 candidate,
不修改 final_canonical_connections。

匹配策略(用户要求,按优先级):
  1. 作者 + 年份(local paper_sources,复用阶段 D 匹配;随后 PubMed esearch)
  2. 作者 + 年份 + brain region keywords(PubMed 查询加 region 词消歧)
  3. title similarity(PubMed 多篇候选时,evidence_text 中若含标题形态
     则计算相似度;多数候选原文无标题,退化为 region 消歧)

数据语义(2026-08-25 探查确认):
* literature_candidates.json 254 条 C_local_unmatched(200 连接),
  original_text 均为 "Author et al. (YYYY)" 括号形态,无 title 片段。
* paper_sources 570 行(阶段 D 已匹配,254 条本地零命中 —— 需 PubMed)。
* PubMed eutils 可达;httpx 0.28.1 可用。

candidate 字段(用户要求):
{
  connection_id, connection_code, mirror_evidence_ids,
  author_query, year, matched_title, doi, pmid,
  match_score, match_method, status("matched"|"ambiguous"|"not_found")
}

match_method:
  local_paper_sources            —— 本地库唯一匹配(理论上 0,幂等验证)
  pubmed_author_year             —— PubMed 作者+年份唯一命中
  pubmed_author_year_region      —— PubMed 作者+年份多篇,region 词消歧到 1
  pubmed_title_similarity        —— PubMed 多篇,标题相似度消歧到 1
  not_found                      —— 本地+PubMed 均无匹配
"""

from __future__ import annotations

import re
from collections import Counter

from app.services.macro_evidence_literature_service import (
    extract_surnames,
    match_citation,
)

STATUS_MATCHED = "matched"
STATUS_AMBIGUOUS = "ambiguous"
STATUS_NOT_FOUND = "not_found"

METHOD_LOCAL = "local_paper_sources"
METHOD_PUBMED_AY = "pubmed_author_year"
METHOD_PUBMED_AY_REGION = "pubmed_author_year_region"
METHOD_PUBMED_TITLE = "pubmed_title_similarity"
METHOD_NOT_FOUND = "not_found"

_REGION_WORD = re.compile(r"[a-z]{3,}")


def build_author_query(author: str) -> str:
    """作者串 → PubMed Author 查询("Surname[Author]" 组合)。

    "Habas et al."          → "Habas[Author]"
    "Petrides & Pandya"     → "(Petrides[Author] AND Pandya[Author])"
    "Mesulam, M.M."         → "Mesulam[Author]"
    "Von Der Heide et al."  → "Von Der Heide[Author]"(多词姓氏整体保留)
    "Goldman-Rakic et al."  → "Goldman-Rakic[Author]"
    """
    core = re.sub(r"\bet al\.?", "", str(author or "")).strip().rstrip(",")
    if not core:
        return ""
    parts = []
    for a in re.split(r"\s*[,&]\s*|\s+and\s+", core):
        words = [w for w in a.split()
                 if not (w.replace(".", "").isupper()
                         and len(w.replace(".", "")) <= 3)]
        if words:
            parts.append(" ".join(w.title() for w in words))
    if not parts:
        return ""
    if len(parts) == 1:
        return f"{parts[0]}[Author]"
    return "(" + " AND ".join(f"{p}[Author]" for p in parts) + ")"


def build_year_query(year: str) -> str:
    """年份 → PubMed 日期限定(兼容 2010a 后缀)。"""
    m = re.match(r"(\d{4})", str(year or ""))
    return f"{m.group(1)}[Date - Publication]" if m else ""


def full_query(author: str, year: str, region_words: list[str]) -> str:
    """完整 PubMed query:作者+年份+可选 region 词。"""
    aq = build_author_query(author)
    yq = build_year_query(year)
    if not aq or not yq:
        return ""
    parts = [f"({aq})", yq]
    for w in region_words:
        parts.append(w)
    return " AND ".join(parts)


def region_keywords(connection_code: str | None, limit: int = 3) -> list[str]:
    """connection_code → brain region 关键词(消歧用,保留复合词)。

    "ng:cn:structural_lateral_orbitofrontal_to_superior_parietal"
      → ["lateral_orbitofrontal", "superior_parietal"]
    消歧匹配时复合词拆单词检测(PubMed title 用空格不用下划线)。
    """
    if not connection_code:
        return []
    segs = str(connection_code).split(":")[-1].split("_")
    skip = {"structural", "functional", "to", "and"}
    words = [w for w in segs if w and w not in skip]
    compound = []
    for w in words:
        if compound and len(compound[-1].split("_")) < 2:
            compound[-1] += "_" + w
        else:
            compound.append(w)
    return compound[:limit]


def title_hint_from_text(text: str | None, author: str, year: str) -> str:
    """evidence_text 中候选的标题片段(形态 "Author (1995). Title. Journal.")。

    原文含作者+年份后跟 ". Title" 时提取标题词;否则空串。
    """
    if not text:
        return ""
    # "Author (1995). Title." —— 取作者年份之后到句号/期刊前的部分
    m = re.search(
        r"\.\s*([A-Z][A-Za-z ,'\-]{8,}?)(?:\.|$)", str(text))
    if not m:
        return ""
    hint = m.group(1).strip()
    return hint if len(hint) >= 8 else ""


def similarity(a: str, b: str) -> float:
    """词交集 Jaccard 相似度(标题消歧)。"""
    if not a or not b:
        return 0.0
    wa = set(re.findall(r"[a-z]+", a.lower()))
    wb = set(re.findall(r"[a-z]+", b.lower()))
    if not wa or not wb:
        return 0.0
    return round(len(wa & wb) / len(wa | wb), 4)


# ---- PubMed 结果分级 ----

def classify_pubmed_hits(
    hits: list[dict],
    region_words: list[str],
    title_hint: str = "",
) -> tuple[str, dict | None, float, str]:
    """PubMed 命中列表 → (status, chosen, match_score, match_method)。

    hits: [{pmid, title, doi}]
    * 1 篇 → matched(method=pubmed_author_year, score=0.9)
    * 多篇 → region 词消歧(标题含 region 词 → 唯一 → matched 0.8);
      title_hint 相似度消歧(唯一且 >0.3 → matched 0.7);
      仍多 → ambiguous(score=0.5)
    * 0 篇 → not_found
    """
    if not hits:
        return STATUS_NOT_FOUND, None, 0.0, METHOD_NOT_FOUND
    if len(hits) == 1:
        return STATUS_MATCHED, hits[0], 0.9, METHOD_PUBMED_AY

    def _region_score(h: dict) -> float:
        if not region_words:
            return 0.0
        t = (h.get("title") or "").lower()
        # 复合词(lateral_orbitofrontal)拆单词检测:title 用空格
        tokens = [w for word in region_words for w in word.split("_")]
        return sum(1 for w in tokens if w in t)

    scored = [(_region_score(h), h) for h in hits]
    best = max(s for s, _ in scored)
    if best > 0:
        top = [h for s, h in scored if s == best]
        if len(top) == 1:
            return STATUS_MATCHED, top[0], 0.8, METHOD_PUBMED_AY_REGION

    if title_hint:
        sims = [(similarity(title_hint, h.get("title") or ""), h)
                for h in hits]
        best_sim = max(s for s, _ in sims)
        if best_sim >= 0.3:
            top = [h for s, h in sims if s == best_sim]
            if len(top) == 1:
                return STATUS_MATCHED, top[0], 0.7, METHOD_PUBMED_TITLE

    return STATUS_AMBIGUOUS, None, 0.5, METHOD_PUBMED_AY


# ---- 候选构建 ----

def build_pubmed_candidates(
    literature_candidates: list[dict],
    lineage_map: dict[str, list[dict]],
    mirror_map: dict[str, dict],
    local_library: list[dict],
    pubmed_lookup,
    do_pubmed: bool = True,
) -> list[dict]:
    """文献线索候选 → pubmed 候选(分级)。

    literature_candidates: [{connection_id, connection_code, author, year,
      original_text, evidence_text_snippet, match_status}]
    lineage_map: {canonical_id: [{mirror_connection_ids}]}
    mirror_map: {mirror_id: {evidence_text}}
    local_library: build_local_paper_library 输出
    pubmed_lookup: (query_str) -> list[dict] (测试传 mock,脚本传缓存+API 层)

    returns candidates [{connection_id, connection_code, mirror_evidence_ids,
      author_query, year, matched_title, doi, pmid, match_score,
      match_method, status, ...}]
    """
    out: list[dict] = []
    seen: set[tuple[str, str]] = set()  # (connection_id, author_query|year)
    for c in literature_candidates:
        if c.get("match_status") == "A_unique":
            continue  # 阶段 D 已本地匹配,不重复
        cid = str(c.get("connection_id") or "")
        author = str(c.get("author") or "")
        year = str(c.get("year") or "")
        ccid = str(c.get("canonical_connection_id") or "")
        aq = build_author_query(author)
        if not aq:
            continue
        key = (cid, f"{aq}|{year}")
        if key in seen:
            continue
        seen.add(key)

        # 证据定位:original_text 出现在哪些 mirror evidence_text
        mirror_ids = _locate_mirror_evidence(
            c.get("original_text"), ccid, lineage_map, mirror_map)

        region_words = region_keywords(c.get("connection_code"))
        title_hint = title_hint_from_text(c.get("evidence_text_snippet"),
                                          author, year)

        # L1:本地 paper_sources(作者+年份)
        local_hits = match_citation(author, year, local_library)
        if len(local_hits) == 1:
            m = local_hits[0]
            out.append(_candidate(c, mirror_ids, aq, year,
                                  m.get("title"), m.get("doi"),
                                  str(m.get("pmid") or ""), 1.0,
                                  METHOD_LOCAL, STATUS_MATCHED))
            continue
        if len(local_hits) > 1:
            out.append(_candidate(c, mirror_ids, aq, year, "", "", "",
                                  0.5, METHOD_LOCAL, STATUS_AMBIGUOUS))
            continue

        # L2:PubMed
        if not do_pubmed:
            out.append(_candidate(c, mirror_ids, aq, year, "", "", "",
                                  0.0, METHOD_NOT_FOUND, STATUS_NOT_FOUND))
            continue
        hits = pubmed_lookup(full_query(author, year, [])) or []
        status, chosen, score, method = classify_pubmed_hits(
            hits, region_words, title_hint)
        if status == STATUS_NOT_FOUND and region_words:
            # 退化:纯作者+年份无结果(多 region 词不会改善),不重查
            pass
        out.append(_candidate(
            c, mirror_ids, aq, year,
            (chosen or {}).get("title", ""),
            (chosen or {}).get("doi", ""),
            str((chosen or {}).get("pmid", "") or ""),
            score, method, status))
    out.sort(key=lambda c: (c["connection_id"], c["author_query"],
                            c["year"]))
    return out


def _candidate(c: dict, mirror_ids: list[str], aq: str, year: str,
               title: str, doi: str, pmid: str, score: float,
               method: str, status: str) -> dict:
    return {
        "connection_id": str(c.get("connection_id") or ""),
        "connection_code": c.get("connection_code"),
        "mirror_evidence_ids": mirror_ids,
        "author_query": aq,
        "year": year,
        "matched_title": title,
        "doi": doi,
        "pmid": pmid,
        "match_score": score,
        "match_method": method,
        "status": status,
        "original_text": c.get("original_text"),
        "evidence_text_snippet": (c.get("evidence_text_snippet") or "")[:120],
    }


def _locate_mirror_evidence(
    original_text: str | None,
    canonical_id: str,
    lineage_map: dict[str, list[dict]],
    mirror_map: dict[str, dict],
) -> list[str]:
    """定位文献线索原文出现在哪些 mirror evidence_text(可追溯)。"""
    if not original_text:
        return []
    found: list[str] = []
    for lr in lineage_map.get(canonical_id) or []:
        for mid in lr.get("mirror_connection_ids") or []:
            t = (mirror_map.get(str(mid)) or {}).get("evidence_text") or ""
            if original_text and original_text in str(t):
                found.append(str(mid))
    return sorted(set(found))


# ---- 报告 ----

def match_summary(candidates: list[dict]) -> dict:
    """候选集合 → 统计报告(match_summary.json)。

    * 按 candidate 计数:total / matched / ambiguous / not_found
    * 按连接计数(去重 connection_id)
    * 按 match_method 分布
    * doi/pmid 唯一性校验
    """
    n = len(candidates)
    by_status = Counter(c["status"] for c in candidates)
    by_method = Counter(c["match_method"] for c in candidates)
    conns = {c["connection_id"] for c in candidates}
    conn_status = Counter(
        next(c["status"] for c in sorted(
            (x for x in candidates if x["connection_id"] == cid),
            key=lambda x: (x["status"] != STATUS_MATCHED, -x["match_score"]))
            ) for cid in conns)
    matched = [c for c in candidates if c["status"] == STATUS_MATCHED]
    dois = [c["doi"] for c in matched if c.get("doi")]
    pmids = [c["pmid"] for c in matched if c.get("pmid")]
    # 唯一性语义:同一篇论文支撑多条连接时 doi/pmid 重复是合法的(每条连接
    # 独立引用);验证的是"冲突"——同 doi 对应不同 pmid,或同连接内重复引用。
    by_doi: dict[str, set] = {}
    by_pmid: dict[str, set] = {}
    for c in matched:
        if c.get("doi"):
            by_doi.setdefault(c["doi"], set()).add(c.get("pmid") or "")
        if c.get("pmid"):
            by_pmid.setdefault(c["pmid"], set()).add(c.get("doi") or "")
    # 同一连接内相同 key 重复出现 = 重复引用
    per_conn_dup = 0
    for cid in conns:
        conn_matched = [c for c in candidates
                        if c["connection_id"] == cid
                        and c["status"] == STATUS_MATCHED]
        for key in ("doi", "pmid"):
            vals = [c[key] for c in conn_matched if c.get(key)]
            if len(set(vals)) != len(vals):
                per_conn_dup += 1
    return {
        "candidate_total": n,
        "connection_total": len(conns),
        "by_status": dict(by_status),
        "by_connection": {
            "matched": conn_status.get(STATUS_MATCHED, 0),
            "ambiguous": conn_status.get(STATUS_AMBIGUOUS, 0),
            "not_found": conn_status.get(STATUS_NOT_FOUND, 0),
        },
        "by_match_method": dict(by_method),
        "doi_pmid_uniqueness": {
            "matched_with_doi": len(dois),
            "matched_with_pmid": len(pmids),
            "doi_conflict_count": sum(1 for v in by_doi.values() if len(v) > 1),
            "pmid_conflict_count": sum(1 for v in by_pmid.values() if len(v) > 1),
            "no_doi_conflict": all(len(v) == 1 for v in by_doi.values()),
            "no_pmid_conflict": all(len(v) == 1 for v in by_pmid.values()),
        },
    }


def split_by_status(candidates: list[dict]) -> dict[str, list[dict]]:
    """候选 → {matched, ambiguous, not_found} 分组。"""
    return {
        "matched": [c for c in candidates if c["status"] == STATUS_MATCHED],
        "ambiguous": [c for c in candidates if c["status"] == STATUS_AMBIGUOUS],
        "not_found": [c for c in candidates if c["status"] == STATUS_NOT_FOUND],
    }
