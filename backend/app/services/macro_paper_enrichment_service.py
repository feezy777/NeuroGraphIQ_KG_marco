"""Macro Paper Knowledge Enrichment V1(纯函数规划 + 幂等 SQL)。

为 paper_sources 中 46 篇新 PubMed 论文补充元数据(来源:Europe PMC core):
  abstract / journal / publication_type / keywords / mesh_terms / authors 结构化

约束(用户要求):
* 不覆盖已有非空字段:journal 列非空则保留(COALESCE 语义);富化字段
  在 enrichment_json 内同样只填空值字段(merge_enrichment)
* 保留原始 metadata_json:富化数据写入新列 enrichment_json,不动 metadata_json
* 新增字段必须记录溯源:enrichment_json 内含
  metadata_source='pubmed_enrichment_v1' / retrieved_at / pmid
* 幂等:已富化(metadata_source=pubmed_enrichment_v1)→ skip;
  UPDATE 以 enrichment_json IS DISTINCT FROM 检测变化 → 复跑 update=0

字段映射(Europe PMC core result):
  abstractText              → abstract
  journalInfo.journal.title → journal(同时填已有列,不覆盖非空)
  pubTypeList.pubType       → publication_type []
  keywordList.keyword       → keywords []
  meshHeadingList.meshHeading → mesh_terms ["Descriptor/qualifier", ...]
  authorList.author         → authors [{full_name, last_name, initials,
                                        affiliations}]
"""

from __future__ import annotations

from datetime import datetime, timezone

METADATA_SOURCE = "pubmed_enrichment_v1"
ENRICHMENT_STAGE = "macro_paper_enrichment_v1"


def _as_list(value) -> list[str]:
    """core result 里 keyword/pubType 可能缺失;统一成列表。"""
    if not value:
        return []
    if isinstance(value, list):
        return [str(v) for v in value]
    return [str(value)]


def parse_europepmc_core(item: dict) -> dict:
    """Europe PMC core result → 6 个富化字段(缺失为 None/[])。"""
    journal_info = item.get("journalInfo") or {}
    journal_obj = journal_info.get("journal") or {}
    mesh_terms = []
    for m in ((item.get("meshHeadingList") or {}).get("meshHeading") or []):
        if not isinstance(m, dict):
            continue
        name = m.get("descriptorName", "")
        quals = [q.get("qualifierName", "") for q in
                 ((m.get("meshQualifierList") or {}).get("meshQualifier")
                  or [])]
        mesh_terms.append("/".join([name] + [q for q in quals if q])
                          if name else "")
    mesh_terms = [m for m in mesh_terms if m]
    authors = []
    for a in ((item.get("authorList") or {}).get("author") or []):
        if not isinstance(a, dict):
            continue
        affs = [aff.get("affiliation", "") for aff in
                ((a.get("authorAffiliationDetailsList") or {})
                 .get("authorAffiliation", []) or [])]
        authors.append({
            "full_name": a.get("fullName", "") or "",
            "last_name": a.get("lastName", "") or "",
            "initials": a.get("initials", "") or "",
            "affiliations": [x for x in affs if x],
        })
    return {
        "abstract": item.get("abstractText") or None,
        "journal": journal_obj.get("title") or None,
        "publication_type": _as_list(
            (item.get("pubTypeList") or {}).get("pubType")),
        "keywords": _as_list(
            (item.get("keywordList") or {}).get("keyword")),
        "mesh_terms": mesh_terms,
        "authors": authors,
    }


def enrich_json(pmid: str, parsed: dict,
                retrieved_at: str | None = None) -> dict:
    """富化容器:6 字段 + 溯源(metadata_source/retrieved_at/pmid)。"""
    return {
        "metadata_source": METADATA_SOURCE,
        "retrieved_at": retrieved_at or
        datetime.now(timezone.utc).isoformat(),
        "pmid": str(pmid).strip(),
        **parsed,
    }


def merge_enrichment(existing: dict | None, fresh: dict) -> dict:
    """合并:已富化字段保留(不覆盖非空),fresh 只填空值字段。"""
    base = dict(existing or {})
    for key, value in fresh.items():
        if key in ("metadata_source", "retrieved_at", "pmid"):
            base[key] = value  # 溯源始终刷新(本次检索时间)
            continue
        cur = base.get(key)
        if cur in (None, "", [], {}):
            base[key] = value
    return base


def already_enriched(enrichment_json) -> bool:
    """幂等判定:已按本版本富化过 → 跳过。"""
    if not enrichment_json or not isinstance(enrichment_json, dict):
        return False
    return enrichment_json.get("metadata_source") == METADATA_SOURCE


def plan_enrichment(papers: list[dict]) -> dict:
    """规划:跳过已富化 → to_fetch(需要 API)/skip。

    papers: [{paper_id, pmid, enrichment_json}]
    """
    to_fetch, skip = [], []
    for p in papers:
        (skip if already_enriched(p.get("enrichment_json"))
         else to_fetch).append(p)
    return {"to_fetch": to_fetch, "skip": skip}


def build_update(pm: dict, parsed: dict,
                 retrieved_at: str | None = None) -> dict:
    """单篇论文 UPDATE 参数:journal 不覆盖非空 + enrichment_json 全量合并。

    返回 None 语义(无变化)由调用方以 enrichment_json IS DISTINCT FROM
    检测;本函数只组装参数。
    """
    enrichment = merge_enrichment(
        pm.get("enrichment_json"),
        enrich_json(pm["pmid"], parsed, retrieved_at))
    return {
        "id": pm["paper_id"],
        "enrichment_json": enrichment,
        # journal 已非空 → COALESCE 保留旧值(不覆盖已有非空字段)
        "journal": parsed.get("journal"),
    }


# ---- SQL(幂等) ----

SELECT_PAPERS_TO_ENRICH_SQL = """\
SELECT id, pmid, journal, enrichment_json
FROM paper_sources
WHERE source = 'PubMed'
  AND pmid IS NOT NULL AND pmid <> ''
  AND metadata_json->>'mode' = 'literature'
ORDER BY pmid"""

UPDATE_ENRICHMENT_SQL = """\
UPDATE paper_sources
SET enrichment_json = :enrichment_json,
    journal = COALESCE(NULLIF(journal, ''), :journal)
WHERE id = :id
  AND enrichment_json IS DISTINCT FROM :enrichment_json
RETURNING id"""
