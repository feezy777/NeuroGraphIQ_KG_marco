"""Macro Connection 论文数据导入(纯函数规划 + 幂等 SQL)。

将 Macro Evidence Literature Promotion V1 已落库的 91 连接 × 104 条
literature reference 正式导入系统 Paper 数据层:
  1. paper_sources 新增论文(source=PubMed;DOI/PMID 已存在则复用)
  2. connection_paper_evidence 建立 Connection-Paper 关联
     {connection_id, paper_id, support_type, evidence_reference,
      confidence, provenance_json}

约束(用户要求):
* 不创建新的论文表 —— 复用已有 paper_sources
* DOI/PMID 已存在 → 直接复用;不存在 → 新增 paper record
* evidence_reference 保留已有 llm_extraction —— 只追加 literature
  (阶段 G 已完成,本阶段不改 evidence_reference)
* 不重新设计 ontology、不做新审计

幂等:paper 插入用 INSERT ... ON CONFLICT DO NOTHING RETURNING(无返回则
复用已有行);关联插入用 ON CONFLICT (connection_id, paper_id) DO NOTHING。
"""

from __future__ import annotations

from datetime import datetime, timezone

PAPER_SOURCE = "PubMed"  # 用户指定 source=PubMed
SUPPORT_TYPE = "literature"
IMPORT_STAGE = "macro_connection_paper_import_v1"


def normalize_doi(doi: str) -> str:
    """DOI 归一化:strip + 小写(与 paper_sources.normalized_doi 对齐)。"""
    return (doi or "").strip().lower()


def paper_identity(ref: dict) -> tuple[str, str]:
    """论文唯一标识:优先 DOI(归一化),无 DOI 用 PMID。

    返回 (doi_key, pmid_key),至少一个非空。
    """
    return (normalize_doi(ref.get("doi") or ""),
            str(ref.get("pmid") or "").strip())


def group_paper_records(refs: list[dict]) -> list[dict]:
    """104 条 reference → 去重后的论文记录(同论文多条 ref 合并)。

    去重键 = DOI(归一化);无 DOI 用 PMID。每条记录保留全部 refs
    (多连接引用同论文时 mirror_evidence_ids/original_text 聚合)。
    """
    groups: dict[str, dict] = {}
    order: list[str] = []
    for ref in refs:
        doi_key, pmid_key = paper_identity(ref)
        # 主身份:有 DOI 仅用 DOI(PMID 差异不分裂);无 DOI 用 PMID
        key = doi_key or pmid_key
        if key not in groups:
            groups[key] = {
                "identity": key,
                "doi": ref.get("doi", "") or "",
                "pmid": str(ref.get("pmid", "") or ""),
                "title": ref.get("title", "") or "",
                "authors": ref.get("authors", "") or "",
                "journal": ref.get("journal", "") or "",
                "year": str(ref.get("year", "") or ""),
                "refs": [],
            }
            order.append(key)
        groups[key]["refs"].append(ref)
    return [groups[k] for k in order]


def build_paper_insert(record: dict) -> dict:
    """论文记录 → paper_sources 插入字段(用户指定导入字段)。"""
    year_raw = record["year"]
    year = int(year_raw) if year_raw and year_raw.isdigit() else None
    return {
        "source": PAPER_SOURCE,
        "doi": record["doi"] or None,
        "normalized_doi": normalize_doi(record["doi"]) or None,
        "pmid": record["pmid"] or None,
        "title": record["title"] or None,
        "journal": record["journal"] or None,
        "publication_year": year,
        "metadata_json": {
            "mode": "literature",
            "authors": record["authors"],
            "matched_refs": [r.get("original_text", "") for r in record["refs"]],
        },
    }


def build_link(connection_id: str, paper_id: str, ref: dict) -> dict:
    """reference → connection_paper_evidence 关联字段(用户指定结构)。"""
    return {
        "connection_id": connection_id,
        "paper_id": paper_id,
        "support_type": SUPPORT_TYPE,
        "evidence_reference": ref,  # 与 final.evidence_reference 元素同构
        "confidence": ref.get("confidence") or ref.get("match_score", 0),
        "provenance_json": {
            "imported_from": IMPORT_STAGE,
            "source": PAPER_SOURCE,
            "generation_method": ref.get("generation_method", ""),
            "match_method": ref.get("match_method", ""),
            "match_score": ref.get("match_score", 0),
            "evidence_source": ref.get("evidence_source", ""),
            "original_text": ref.get("original_text", ""),
            "imported_at": datetime.now(timezone.utc).isoformat(),
        },
    }


# ---- SQL(幂等) ----

INSERT_PAPER_SQL = """\
INSERT INTO paper_sources (source, doi, normalized_doi, pmid, title,
                           journal, publication_year, metadata_json)
VALUES (:source, :doi, :normalized_doi, :pmid, :title,
        :journal, :publication_year, :metadata_json)
ON CONFLICT DO NOTHING
RETURNING id"""

SELECT_PAPER_BY_IDENTITY_SQL = """\
SELECT id, normalized_doi, pmid FROM paper_sources
WHERE (normalized_doi IS NOT NULL AND normalized_doi <> ''
       AND normalized_doi = ANY(:dois))
   OR (pmid IS NOT NULL AND pmid <> '' AND pmid = ANY(:pmids))"""

INSERT_LINK_SQL = """\
INSERT INTO connection_paper_evidence
    (connection_id, paper_id, support_type, evidence_reference,
     confidence, provenance_json)
VALUES (:connection_id, :paper_id, :support_type,
        :evidence_reference, :confidence, :provenance_json)
ON CONFLICT (connection_id, paper_id) DO NOTHING
RETURNING id"""


def plan_paper_reuse(existing: list[tuple[str, str, str]], records: list[dict]) -> dict:
    """规划论文复用:DB 命中(DOI 或 PMID)→ 复用;未命中 → 新增。

    existing: [(id, normalized_doi, pmid)] —— paper_sources 命中扫描结果。
    """
    by_doi = {}
    by_pmid = {}
    for pid, nd, pmid in existing:
        if nd:
            by_doi[nd.strip().lower()] = pid
        if pmid:
            by_pmid[str(pmid).strip()] = pid
    out = {"reuse": [], "new": []}
    for rec in records:
        doi_key, pmid_key = paper_identity({"doi": rec["doi"], "pmid": rec["pmid"]})
        paper_id = by_doi.get(doi_key) if doi_key else None
        if not paper_id and pmid_key:
            paper_id = by_pmid.get(pmid_key)
        entry = {"record": rec, "paper_id": paper_id,
                 "matched_by": "doi" if (doi_key and paper_id == by_doi.get(doi_key))
                 else "pmid" if paper_id else None}
        (out["reuse"] if paper_id else out["new"]).append(entry)
    return out
