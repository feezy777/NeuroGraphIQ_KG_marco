"""Macro Evidence Literature Promotion V1 — 文献证据提升(纯函数规划)。

将 Macro Evidence Literature PubMed Backfill V1 生成的 matched candidates
(data/exports/macro_evidence_pubmed/matched_candidates.json, 104 条 / 91 连接)
提升为 final_canonical_connections.evidence_reference 中的 literature 元素。

Merge 规则(用户要求, verbatim):
* 禁止覆盖已有 evidence_reference —— 只允许追加 literature evidence
* 按 DOI > PMID > citation hash 去重(对同一 final connection 的引用集)
* 保留完整 provenance:generation_method="pubmed_backfill_v1"、
  source="PubMed"、match_score

reference 元素结构(用户指定追加):
{
  source_type: "literature",
  doi, pmid, title, authors, journal, year,
  evidence_source: "pubmed_backfill_v1",
  confidence, matched_connection_id
}
+ provenance 扩展:generation_method, source, match_score, match_method,
  mirror_evidence_ids, original_text

本模块只做纯函数规划(plan_* / *_stats / dedup),不触碰数据库;
幂等 UPDATE 由 scripts/run_macro_evidence_literature_promotion.py 执行。
"""

from __future__ import annotations

import hashlib
import re

EVIDENCE_SOURCE = "pubmed_backfill_v1"
GENERATION_METHOD = "pubmed_backfill_v1"
SOURCE = "PubMed"

# 年份:非捕获组避免 group 下标错位(旧文献 1xxx 与 20xx 均可)
_YEAR = r"(?:1[89]\d{2}|20\d{2})[a-z]?"
# 结尾的年份,兼容 "(2009)" / ", 2009" / "2009"
_TRAIL_YEAR = re.compile(rf"\s*,?\s*\(?{_YEAR}\)?\s*$")


def extract_author_display(text: str) -> str:
    """从文献线索文本提取作者显示串。

    输入格式(阶段 D/F 解析所得):
      "Mesulam, M.M. (1995)"     → "Mesulam, M.M."
      "(Habas et al., 2009)"     → "Habas et al."
      "Petrides & Pandya (2002)" → "Petrides & Pandya"
      "Haber & Knutson 2010"     → "Haber & Knutson"
    """
    t = (text or "").strip()
    if not t:
        return ""
    if t.startswith("("):
        t = t[1:]
    if t.endswith(")"):
        t = t[:-1]
    t = t.strip()
    m = _TRAIL_YEAR.search(t)
    if m:
        t = t[: m.start()]
    return t.strip().rstrip(",").strip()[:120]


def build_literature_reference(candidate: dict) -> dict:
    """matched candidate → literature reference 元素(用户指定结构 + provenance)。"""
    return {
        # ---- 用户指定字段 ----
        "source_type": "literature",
        "doi": candidate.get("doi", "") or "",
        "pmid": str(candidate.get("pmid", "") or ""),
        "title": candidate.get("matched_title", "") or "",
        "authors": extract_author_display(candidate.get("original_text", "")),
        "journal": candidate.get("journal", "") or "",
        "year": str(candidate.get("year", "") or ""),
        "evidence_source": EVIDENCE_SOURCE,
        "confidence": candidate.get("match_score", 0.5),
        "matched_connection_id": str(candidate.get("connection_id", "") or ""),
        # ---- provenance(用户要求保留完整溯源) ----
        "generation_method": GENERATION_METHOD,
        "source": SOURCE,
        "match_score": candidate.get("match_score", 0),
        "match_method": candidate.get("match_method", "") or "",
        "mirror_evidence_ids": candidate.get("mirror_evidence_ids", []) or [],
        "original_text": candidate.get("original_text", "") or "",
    }


def lit_dedup_key(ref: dict) -> str:
    """去重键:DOI > PMID > citation hash(title+year+authors)。

    同一篇论文支撑多条连接时,键在各自连接内独立判定 —— 跨连接同论文合法。
    """
    doi = (ref.get("doi") or "").strip().lower()
    if doi:
        return "doi:" + doi
    pmid = str(ref.get("pmid") or "").strip()
    if pmid:
        return "pmid:" + pmid
    title = (ref.get("title") or "").strip().lower()
    year = str(ref.get("year") or "").strip()
    authors = (ref.get("authors") or "").strip().lower()
    h = hashlib.sha1(f"{title}|{year}|{authors}".encode()).hexdigest()[:16]
    return "hash:" + h


def _same_paper(a: dict, b: dict) -> bool:
    """级联等价判定(用户规则:DOI > PMID > citation hash)。

    DOI 双方非空且相等 → 同文;否则 PMID 双方非空且相等 → 同文;
    否则 hash(title+year+authors) 相等 → 同文。
    """
    doi_a = (a.get("doi") or "").strip().lower()
    doi_b = (b.get("doi") or "").strip().lower()
    if doi_a and doi_b and doi_a == doi_b:
        return True
    pmid_a = str(a.get("pmid") or "").strip()
    pmid_b = str(b.get("pmid") or "").strip()
    if pmid_a and pmid_b and pmid_a == pmid_b:
        return True
    return lit_dedup_key(a) == lit_dedup_key(b)


def plan_literature_merge(existing_refs: list[dict], lit_ref: dict) -> tuple[str, list[dict]]:
    """规划单个 literature 元素合并:追加或去重跳过。

    返回 (verdict, merged_refs):
      "append"    —— 无冲突,追加到末尾
      "duplicate" —— 与任一已有引用同级联判重(DOI/PMID/hash),跳过,禁止覆盖
    """
    for r in existing_refs:
        if _same_paper(r, lit_ref):
            return "duplicate", list(existing_refs)
    return "append", list(existing_refs) + [lit_ref]


def plan_connection_promotion(connection_id: str, existing_refs: list[dict],
                              candidates: list[dict]) -> dict:
    """规划单条连接的提升:合并该连接的全部 literature candidates。

    同连接多候选:逐条 plan_literature_merge —— 同论文(同 DOI/PMID/hash)
    后续候选判 duplicate,不同论文全部追加。
    """
    merged = list(existing_refs or [])
    appended: list[dict] = []
    duplicates: list[dict] = []
    for c in candidates:
        ref = build_literature_reference(c)
        verdict, merged = plan_literature_merge(merged, ref)
        if verdict == "append":
            appended.append(ref)
        else:
            duplicates.append({
                "ref": ref,
                "reason": "dedup_key_collision",
                "dedup_key": lit_dedup_key(ref),
            })
    return {
        "connection_id": connection_id,
        "before_count": len(existing_refs or []),
        "after_count": len(merged),
        "appended": appended,
        "duplicates": duplicates,
        "merged_refs": merged,
    }


def plan_literature_promotion(finals: dict[str, dict],
                              candidates_by_connection: dict[str, list[dict]]) -> dict:
    """全量规划:finals {conn_id: {"evidence_reference": [...]}} × candidates。"""
    plans = []
    total_candidates = 0
    for cid in sorted(candidates_by_connection):
        cands = candidates_by_connection[cid]
        if not cands:
            continue
        total_candidates += len(cands)
        plans.append(plan_connection_promotion(
            cid, (finals.get(cid, {}).get("evidence_reference") or []), cands))
    return {
        "connections_planned": len(plans),
        "candidates_total": total_candidates,
        "to_append": sum(len(p["appended"]) for p in plans),
        "duplicates": sum(len(p["duplicates"]) for p in plans),
        "plans": plans,
    }


def coverage_stats(finals: dict[str, dict]) -> dict:
    """覆盖率统计(纯模拟):finals {conn_id: {"evidence_reference": [...]}}。

    按连接计数:DOI/PMID 覆盖 = 该连接任一引用含非空 doi/pmid。
    """
    refs_all = [r for f in finals.values() for r in (f.get("evidence_reference") or [])]
    lit_refs = [r for r in refs_all if r.get("source_type") == "literature"]
    dois = sorted({r["doi"].strip().lower() for r in refs_all
                   if (r.get("doi") or "").strip()})
    pmids = sorted({str(r["pmid"]).strip() for r in refs_all
                    if (r.get("pmid") or "").strip()})
    return {
        "total_connections": len(finals),
        "with_literature_refs": sum(
            1 for f in finals.values()
            if any(r.get("source_type") == "literature"
                   for r in (f.get("evidence_reference") or []))),
        "doi_covered_connections": sum(
            1 for f in finals.values()
            if any((r.get("doi") or "").strip()
                   for r in (f.get("evidence_reference") or []))),
        "pmid_covered_connections": sum(
            1 for f in finals.values()
            if any((r.get("pmid") or "").strip()
                   for r in (f.get("evidence_reference") or []))),
        "literature_refs_total": len(lit_refs),
        "unique_dois": len(dois),
        "unique_pmids": len(pmids),
        "doi_cover_rate": round(
            sum(1 for f in finals.values()
                if any((r.get("doi") or "").strip()
                       for r in (f.get("evidence_reference") or []))) / len(finals),
            4) if finals else 0.0,
        "pmid_cover_rate": round(
            sum(1 for f in finals.values()
                if any((r.get("pmid") or "").strip()
                       for r in (f.get("evidence_reference") or []))) / len(finals),
            4) if finals else 0.0,
    }


def build_after_finals(finals: dict[str, dict],
                       candidates_by_connection: dict[str, list[dict]]) -> dict[str, dict]:
    """规划后的模拟 final 集(用于 after_coverage 与幂等复跑验证)。"""
    after = {cid: {"evidence_reference": list(f.get("evidence_reference") or [])}
             for cid, f in finals.items()}
    for cid, cands in candidates_by_connection.items():
        if not cands:
            continue
        p = plan_connection_promotion(
            cid, (finals.get(cid, {}).get("evidence_reference") or []), cands)
        after.setdefault(cid, {})["evidence_reference"] = p["merged_refs"]
    return after
