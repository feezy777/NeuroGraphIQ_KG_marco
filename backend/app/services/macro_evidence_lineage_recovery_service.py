"""Macro Evidence Lineage Recovery V1 — 文献级证据恢复(纯函数规划,零写入)。

目标:输入 final canonical_connection_id,沿数据链路
    final ↓ canonical_connection_lineage(mirror_connection_ids)
         ↓ mirror_region_connections / mirror_evidence_records
恢复结构化文献引用(paper/DOI/PMID),输出 evidence_references 预览,
回填前只生成 preview,暂不修改 final 表。

数据语义(2026-08-25 链路审计确认):
* mirror_evidence_records 99,481 行:94,558 指向 molecular_attr 粒度连接,
  仅 2 条指向 macro 连接(Kim 2026 / LeDoux 1990,paper_doi+paper_pmid+
  citation_json 全字段),4,483 条孤儿(target 已不存在),其余指向
  mirror_circuit/mirror_function/projection。→ 经 lineage 可恢复的
  evidence_records 仅 2 条,覆盖 2 个 final。
* macro 证据的文献信息主要在 mirror_region_connections.evidence_text
  (5,716 条自然语言):阶段 D 已解析 259 条文献线索(203/2485 连接),
  其中 5 条与本地 paper_sources(570 行 europepmc)唯一匹配。
* 本模块零写入:不建表、不改 evidence_reference、不调 LLM/PubMed、
  不改 Final 状态 —— 只产出 preview 规划。

恢复优先级(用户要求):
  A: paper_doi + paper_pmid(evidence_records 结构化,最高)
  B: citation_json 存在(无 doi/pmid 时)
  C: paper 作者+年份文本(evidence_text 解析 + 本地库匹配)
  D: 只有 LLM extraction 文本(无任何文献线索)

Evidence merge 去重(用户要求):同一篇论文按 doi > pmid > citation_hash
> title+year 去重,同一论文的多条 mirror evidence 合并 mirror_evidence_ids,
不生成重复 reference。

reference 元素格式(用户要求):
{
  source_type: "literature" | "database" | "llm_extraction",
  doi, pmid, paper_title, citation, mirror_evidence_ids[], confidence,
  evidence_text, priority("A"|"B"|"C"|"D"), dedup_key
}
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from typing import Iterable

from app.services.macro_evidence_literature_service import (
    match_citation,
    parse_citation,
)

PRIORITY_ORDER = ("A", "B", "C", "D")

# ---- 归一化工具 ----


def _normalize_doi(v) -> str:
    return str(v or "").strip().lower()


def _normalize_pmid(v) -> str:
    return str(v or "").strip()


def _title_year_key(title, year) -> str:
    t = str(title or "").strip().lower()
    y = str(year or "").strip()
    return f"{t}|{y}"


def citation_hash(citation_json) -> str | None:
    """citation_json(dict 或 JSON 文本)→ 确定性 hash(去重键之一)。"""
    if not citation_json:
        return None
    if isinstance(citation_json, str):
        try:
            citation_json = json.loads(citation_json)
        except (ValueError, TypeError):
            citation_json = {"raw": citation_json}
    if isinstance(citation_json, dict):
        s = json.dumps(citation_json, sort_keys=True, ensure_ascii=False)
        return hashlib.sha1(s.encode("utf-8")).hexdigest()[:16]
    return None


def dedup_key_of(ref: dict) -> str:
    """reference → 去重键:doi > pmid > citation_hash > title+year。"""
    doi = _normalize_doi(ref.get("doi"))
    if doi:
        return "doi:" + doi
    pmid = _normalize_pmid(ref.get("pmid"))
    if pmid:
        return "pmid:" + pmid
    ch = ref.get("citation_hash")
    if ch:
        return "hash:" + ch
    return "title_year:" + _title_year_key(
        ref.get("paper_title"), ref.get("year"))


# ---- 1. evidence_record 恢复(优先级 A / B) ----

def _citation_text(rec: dict, cj: dict | None, doi: str, pmid: str,
                   title: str, year, journal: str) -> str:
    authors = (cj or {}).get("authors") if isinstance(cj, dict) else None
    parts = [a for a in [authors or "", f"({year})" if year else "",
                         title, journal] if a]
    suffix = [f"doi={doi}" if doi else "", f"pmid={pmid}" if pmid else ""]
    parts += [s for s in suffix if s]
    return "; ".join(parts)


def recover_from_evidence_record(rec: dict) -> dict | None:
    """mirror_evidence_records 行 → 文献引用(优先级 A/B)。

    rec: {id, paper_doi, paper_pmid, paper_year, paper_title, paper_journal,
          citation_json, evidence_text, verification_status, confidence}
    无 doi/pmid/citation_json → None(该行无法恢复文献,交给 evidence_text 层)。
    """
    doi = _normalize_doi(rec.get("paper_doi"))
    pmid = _normalize_pmid(rec.get("paper_pmid"))
    cj = rec.get("citation_json")
    cj_dict = cj if isinstance(cj, dict) else None
    # citation_json 内嵌 doi/pmid 亦参与身份识别(去重键),优先级定义不变
    if cj_dict:
        doi = doi or _normalize_doi(cj_dict.get("doi"))
        pmid = pmid or _normalize_pmid(cj_dict.get("pmid"))
    has_doi = bool(doi)
    has_pmid = bool(pmid)
    if not has_doi and not has_pmid and not cj:
        return None
    priority = "A" if has_doi and has_pmid else "B"
    title = (rec.get("paper_title")
             or (cj_dict or {}).get("title") or "")
    year = rec.get("paper_year") or (cj_dict or {}).get("year") or ""
    journal = (rec.get("paper_journal")
               or (cj_dict or {}).get("journal") or "")
    confidence = rec.get("confidence") or rec.get("verification_status") or ""
    return {
        "source_type": "literature",
        "priority": priority,
        "doi": doi,
        "pmid": pmid,
        "paper_title": str(title or ""),
        "year": str(year or ""),
        "citation": _citation_text(rec, cj_dict, doi, pmid, title, year,
                                   journal),
        "mirror_evidence_ids": [str(rec.get("id") or "")],
        "mirror_connection_ids": [],
        "confidence": str(confidence),
        "evidence_text": str(rec.get("evidence_text") or "")[:500],
        "citation_hash": citation_hash(cj),
        "dedup_key": "",
    }


# ---- 2. evidence_text 恢复(优先级 C:作者+年份文本 + 本地库匹配) ----

def recover_from_evidence_text(text: str, library: list[dict],
                               mirror_id: str | None = None) -> list[dict]:
    """evidence_text → C 类引用列表(复用阶段 D 解析+匹配)。

    text: mirror evidence_text 自然语言
    library: build_local_paper_library 输出(paper_sources 本地库)
    mirror_id: 来源 mirror 连接 id(填入 mirror_connection_ids)
    仅本地库唯一匹配的引用返回;多篇/无匹配不产生 C 类引用。
    """
    out: list[dict] = []
    for c in parse_citation(text):
        matches = match_citation(c["author"], c["year"], library)
        if len(matches) != 1:
            continue
        m = matches[0]
        out.append({
            "source_type": "literature",
            "priority": "C",
            "doi": _normalize_doi(m.get("doi")),
            "pmid": _normalize_pmid(m.get("pmid")),
            "paper_title": str(m.get("title") or ""),
            "year": str(m.get("year") or ""),
            "citation": f"{c['author']} ({c['year']})",
            "mirror_evidence_ids": [],
            "mirror_connection_ids": [str(mirror_id)] if mirror_id else [],
            "confidence": "",
            "evidence_text": str(text)[:500],
            "author_year": f"{c['author']} ({c['year']})",
            "citation_hash": None,
            "dedup_key": "",
        })
    return out


def text_only_reference(mirror_ids: list[str], texts: list[str]) -> dict:
    """优先级 D:只有 LLM extraction 文本,无任何文献线索。"""
    return {
        "source_type": "llm_extraction",
        "priority": "D",
        "doi": "", "pmid": "", "paper_title": "", "year": "",
        "citation": "",
        "mirror_evidence_ids": [],
        "mirror_connection_ids": sorted({str(i) for i in mirror_ids}),
        "confidence": "",
        "evidence_text": (str(texts[0])[:500] if texts else ""),
        "dedup_key": "",
    }


# ---- 3. Evidence merge 去重(doi > pmid > citation_hash > title+year) ----

def dedup_references(refs: list[dict]) -> list[dict]:
    """同一论文多条引用 → 合并(键 doi > pmid > citation_hash > title+year)。

    合并规则:取最高优先级引用为基底,mirror_evidence_ids /
    mirror_connection_ids 并集,evidence_text 保留基底(高优先级)的。
    同一 mirror evidence 绝不生成多个重复 reference。
    """
    buckets: dict[str, list[dict]] = {}
    for r in refs:
        key = dedup_key_of(r)
        r["dedup_key"] = key
        buckets.setdefault(key, []).append(r)
    out = []
    for key, group in buckets.items():
        group.sort(key=lambda r: PRIORITY_ORDER.index(r["priority"]))
        base = dict(group[0])
        base["mirror_evidence_ids"] = sorted({
            str(i) for r in group for i in (r.get("mirror_evidence_ids") or [])})
        base["mirror_connection_ids"] = sorted({
            str(i) for r in group for i in (r.get("mirror_connection_ids") or [])})
        base["evidence_text"] = next(
            (r["evidence_text"] for r in group if r.get("evidence_text")),
            base.get("evidence_text") or "")
        base["dedup_key"] = key
        out.append(base)
    out.sort(key=lambda r: (PRIORITY_ORDER.index(r["priority"]),
                            r["dedup_key"]))
    return out


# ---- 4. 单条 final 恢复规划 ----

def build_lineage_recovery(
    final: dict,
    lineage_rows: list[dict],
    mirror_map: dict[str, dict],
    evidence_map: dict[str, list[dict]],
    library: list[dict],
) -> dict:
    """单条 final → 恢复规划(纯函数)。

    final: {id, canonical_connection_id, connection_code, evidence_reference}
    lineage_rows: 该 canonical 的全部 lineage 行 {cluster_id, mirror_connection_ids}
    mirror_map: {mirror_id: {evidence_text, ...}}
    evidence_map: {mirror_id: [mirror_evidence_records dicts]}
    library: build_local_paper_library 输出

    returns {
      final_id, canonical_connection_id, connection_code,
      traced_mirror_ids, evidence_references[](去重后),
      resolved(bool: 含 A/B/C), priority_counts, reason, mirrored_records,
      literature_recovered(bool), deduped_count
    }
    """
    fcid = str(final.get("canonical_connection_id") or "")
    mirror_ids: list[str] = []
    for lr in lineage_rows:
        for mid in lr.get("mirror_connection_ids") or []:
            mirror_ids.append(str(mid))
    base = {
        "final_id": str(final.get("id") or ""),
        "canonical_connection_id": fcid,
        "connection_code": final.get("connection_code"),
        "traced_mirror_ids": mirror_ids,
        "mirrored_records": sum(len(evidence_map.get(mid, []))
                                for mid in mirror_ids),
        "evidence_references": [],
        "resolved": False,
        "reason": "",
        "literature_recovered": False,
    }
    if not mirror_ids:
        return {**base, "resolved": False, "reason": "no_lineage",
                "priority_counts": {}, "deduped_count": 0}

    refs: list[dict] = []
    texts: list[str] = []
    for mid in mirror_ids:
        for rec in evidence_map.get(mid, []):
            r = recover_from_evidence_record(rec)
            if r:
                r["mirror_connection_ids"] = [mid]
                refs.append(r)
        m = mirror_map.get(mid) or {}
        t = m.get("evidence_text")
        if t:
            texts.append(str(t))
            refs.extend(recover_from_evidence_text(str(t), library, mid))

    refs = dedup_references(refs)
    has_literature = any(r["priority"] in ("A", "B", "C") for r in refs)
    if not has_literature and texts:
        # 无任何文献线索 → 合并为一条 D 类(纯 LLM 文本)
        refs.append(text_only_reference(mirror_ids, texts))

    priority_counts = dict(Counter(r["priority"] for r in refs))
    return {
        **base,
        "evidence_references": refs,
        "resolved": has_literature,
        "reason": "" if has_literature else (
            "no_evidence_text" if not texts else "text_only_no_citation"),
        "literature_recovered": has_literature,
        "priority_counts": priority_counts,
        "deduped_count": len(refs),
    }



# ---- 5. 全量规划 ----

def plan_lineage_recovery(
    finals: list[dict],
    lineage_map: dict[str, list[dict]],
    mirror_map: dict[str, dict],
    evidence_map: dict[str, list[dict]],
    library: list[dict],
) -> dict:
    """全量恢复规划(纯函数,幂等:同输入 → 同输出)。

    finals: {id, canonical_connection_id, connection_code, evidence_reference}
    lineage_map: {canonical_id: [lineage rows]}
    mirror_map: {mirror_id: {evidence_text}}
    evidence_map: {mirror_id: [evidence_records]}
    library: build_local_paper_library 输出

    returns {items: [...], counts}
    """
    items = []
    for f in finals:
        items.append(build_lineage_recovery(
            f, lineage_map.get(str(f.get("canonical_connection_id"))) or [],
            mirror_map, evidence_map, library))
    counts = {
        "total": len(items),
        "with_lineage": sum(1 for i in items if i["traced_mirror_ids"]),
        "no_lineage": sum(1 for i in items if not i["traced_mirror_ids"]),
        "literature_recovered": sum(1 for i in items
                                    if i["literature_recovered"]),
        "unresolved": sum(1 for i in items
                          if not i["literature_recovered"]),
        "by_priority": dict(Counter(
            p for i in items for p in (i.get("priority_counts") or {}) for _ in
            range(i["priority_counts"][p]))),
        "by_reason": dict(Counter(i["reason"] for i in items)),
        "total_references": sum(i["deduped_count"] for i in items),
        "total_evidence_records_hit": sum(i["mirrored_records"]
                                          for i in items),
    }
    return {"items": items, "counts": counts}


# ---- 6. 报告生成(纯函数) ----

def coverage_before(finals: list[dict]) -> dict:
    """回填前现状(coverage_before.json)。

    finals: {id, evidence_reference, evidence_summary}
    统计:evidence_reference 覆盖率(阶段 C 已 100%)、其中 paper 非空数
    (文献级引用现状)、evidence_count 分布。
    """
    n = len(finals)
    with_refs = sum(1 for f in finals if f.get("evidence_reference"))
    paper_nonempty = sum(
        1 for f in finals
        for r in (f.get("evidence_reference") or []) if r.get("paper"))
    doi_nonempty = sum(
        1 for f in finals
        for r in (f.get("evidence_reference") or [])
        if r.get("doi") or r.get("pmid"))
    es = Counter(int((f.get("evidence_summary") or {}).get("evidence_count")
                     or 0) if isinstance(f.get("evidence_summary"), dict)
                 else 0 for f in finals)
    return {
        "total_final": n,
        "evidence_reference_coverage": {
            "with_references": with_refs,
            "coverage_pct": round(100 * with_refs / n, 2) if n else 0,
            "with_paper_field_nonempty": paper_nonempty,
            "with_doi_or_pmid": doi_nonempty,
            "note": "evidence_reference 已由 Provenance Backfill 100% 回填,"
                    "但均来自 extraction provenance,paper/doi/pmid 为空",
        },
        "evidence_count_distribution": dict(sorted(es.items())),
    }


def coverage_after_preview(plan: dict, evidence_records_hit: int = 0) -> dict:
    """恢复后预览(coverage_after_preview.json)。

    plan: plan_lineage_recovery 输出
    evidence_records_hit: 底层 evidence_record 命中数(审计值 2)
    """
    c = plan["counts"]
    by_priority = Counter()
    by_source = Counter()
    for i in plan["items"]:
        for r in i["evidence_references"]:
            by_priority[r["priority"]] += 1
            by_source[r["source_type"]] += 1
    total = c["total"]
    return {
        "total_final": total,
        "preview_only": True,
        "note": "仅预览:未修改 final_canonical_connections,"
                "回填需后续正式阶段执行",
        "literature_coverage": {
            "with_literature_reference": c["literature_recovered"],
            "coverage_pct": round(100 * c["literature_recovered"] / total, 2)
            if total else 0,
            "by_priority": dict(by_priority),
            "by_source_type": dict(by_source),
        },
        "unresolved": {
            "count": c["unresolved"],
            "pct": round(100 * c["unresolved"] / total, 2) if total else 0,
            "by_reason": c["by_reason"],
            "note": "unresolved = 无文献线索(仅 LLM 文本)或无证据文本,"
                    "需要 LLM 证据增强",
        },
        "lineage": {
            "with_lineage": c["with_lineage"],
            "no_lineage": c["no_lineage"],
            "total_references_preview": c["total_references"],
            "total_evidence_records_hit": c["total_evidence_records_hit"],
            "baseline_evidence_records_hit": evidence_records_hit,
        },
    }


def unresolved_evidence(plan: dict) -> list[dict]:
    """无法恢复文献引用的 final 清单(unresolved_evidence.json)。"""
    out = []
    for i in plan["items"]:
        if i["literature_recovered"]:
            continue
        d_refs = [r for r in i["evidence_references"]
                  if r["priority"] == "D"]
        out.append({
            "final_id": i["final_id"],
            "canonical_connection_id": i["canonical_connection_id"],
            "connection_code": i["connection_code"],
            "reason": i["reason"],
            "traced_mirror_ids": i["traced_mirror_ids"],
            "mirrored_records": i["mirrored_records"],
            "evidence_text_snippets": [
                r.get("evidence_text", "")[:200]
                for r in d_refs if r.get("evidence_text")],
        })
    return out


def literature_recovery_candidates(plan: dict) -> list[dict]:
    """可恢复文献引用的 final 清单(literature_recovery_candidates.json)。"""
    out = []
    for i in plan["items"]:
        refs = [r for r in i["evidence_references"]
                if r["priority"] in ("A", "B", "C")]
        if not refs:
            continue
        out.append({
            "final_id": i["final_id"],
            "canonical_connection_id": i["canonical_connection_id"],
            "connection_code": i["connection_code"],
            "priority_counts": i["priority_counts"],
            "references": refs,
        })
    return out
