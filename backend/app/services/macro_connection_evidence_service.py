"""Macro Connection Evidence Enrichment — 核心逻辑(纯函数)。

在 canonical connection consolidation(第 3 层)之上,为每条 canonical 生成
标准 Evidence Summary + Evidence Quality Score:

* 标准结构:canonical_connection_id / evidence_count / sources[] /
  confidence_min / confidence_max / confidence_mean / supporting_records[]
* 可追溯:supporting_records 每行含 mirror_connection_id + cluster_id,
  canonical → cluster → mirror 三层完整
* Quality Score:high / medium / low 三档,**不修改 confidence**,
  评分依据(evidence_quality_factors)全量落库可审计

数据来源(mirror_region_connections 无 paper/DOI 字段):
- source 维度 = (llm_run_id, source_atlas) —— 不同 llm_run_id 视为不同提取来源/批次
- "多篇论文支持" 以 distinct llm_run_id 数量近似
"""

from __future__ import annotations

from collections import Counter
from statistics import mean, pstdev
from typing import Any

# ---- 常量 ----

SUPPORTING_RECORD_TEXT_LIMIT = 200      # supporting_records 中 evidence_text 截断长度
EVIDENCE_TEXT_SAMPLE_LIMIT = 10         # evidence_summary 中证据文本样例条数

# Quality Score 权重(总和 1.0,文档化,可审计)
W_EVIDENCE = 0.45        # 证据数量
W_SOURCES = 0.35         # 来源多样性(distinct llm_run_id)
W_CONSISTENCY = 0.20     # extraction 一致性(confidence 变异系数)

HIGH_THRESHOLD = 0.7
MEDIUM_THRESHOLD = 0.45


# ---- 纯函数 ----


def _confidence_stats(values: list[float | None]) -> dict:
    """confidence 列表 → {count, min, max, mean}。None/0 之外的非数值忽略。"""
    vals = [float(v) for v in values if v is not None and v != ""]
    if not vals:
        return {"count": 0}
    return {
        "count": len(vals),
        "min": round(min(vals), 4),
        "max": round(max(vals), 4),
        "mean": round(mean(vals), 4),
    }


def build_sources(mirror_rows: list[dict]) -> list[dict]:
    """按 (llm_run_id, source_atlas) 分组 mirror 行 → 来源列表。

    每个 source:{source_type, source_id(llm_run_id), source_atlas,
    record_count, confidence_min/max/mean}
    """
    groups: dict[tuple, list[float]] = {}
    meta: dict[tuple, dict] = {}
    for m in mirror_rows:
        key = (str(m.get("llm_run_id") or "unknown"), m.get("source_atlas") or "unknown")
        groups.setdefault(key, []).append(m.get("confidence"))
        meta.setdefault(key, {"source_type": "llm_extraction", "record_count": 0})
        meta[key]["record_count"] += 1
    sources = []
    for key, confs in groups.items():
        run_id, atlas = key
        stats = _confidence_stats(confs)
        sources.append({
            "source_type": meta[key]["source_type"],
            "source_id": run_id,
            "source_atlas": atlas,
            "record_count": meta[key]["record_count"],
            "confidence_min": stats.get("min"),
            "confidence_max": stats.get("max"),
            "confidence_mean": stats.get("mean"),
        })
    sources.sort(key=lambda s: -s["record_count"])
    return sources


def build_supporting_records(mirror_rows: list[dict], cluster_id: int | None = None) -> list[dict]:
    """mirror 行明细列表(evidence_text 截断,保留追溯键)。

    每行:{mirror_connection_id, cluster_id, evidence_text(截断),
    confidence, directionality, modality, llm_run_id}
    """
    records = []
    for m in mirror_rows:
        records.append({
            "mirror_connection_id": str(m.get("id") or ""),
            "cluster_id": m.get("cluster_id") if m.get("cluster_id") is not None else cluster_id,
            "evidence_text": (m.get("evidence_text") or "")[:SUPPORTING_RECORD_TEXT_LIMIT],
            "confidence": m.get("confidence"),
            "directionality": m.get("directionality"),
            "modality": m.get("modality"),
            "llm_run_id": str(m.get("llm_run_id") or ""),
        })
    return records


def build_standard_evidence_summary(
    canonical_id: str,
    cluster_ids: list[int],
    mirror_rows: list[dict],
    cluster_meta: dict | None = None,
) -> dict:
    """标准 Evidence Summary(合并第 3 层聚合统计 + 标准结构)。

    canonical_id: canonical 行 id
    cluster_ids: 该 canonical 的 lineage cluster id 列表(可空)
    mirror_rows: 该 canonical 的全部支撑 mirror 行(带 cluster_id 字段可选)
    cluster_meta: 第 3 层 evidence_summary 中的聚合统计(merge_reasons /
                  hemisphere_patterns / modalities),保留兼容

    returns:
    {
      canonical_connection_id, evidence_count, cluster_count, cluster_ids,
      sources[], confidence_min/max/mean, supporting_records[],
      merge_reasons, hemisphere_patterns, modalities,
      llm_run_ids, evidence_texts(截断样例)
    }
    """
    confs = [m.get("confidence") for m in mirror_rows]
    stats = _confidence_stats(confs)
    meta = cluster_meta or {}
    return {
        "canonical_connection_id": canonical_id,
        "evidence_count": len(mirror_rows),
        "cluster_count": len(cluster_ids),
        "cluster_ids": cluster_ids,
        "sources": build_sources(mirror_rows),
        "confidence_min": stats.get("min"),
        "confidence_max": stats.get("max"),
        "confidence_mean": stats.get("mean"),
        "supporting_records": build_supporting_records(mirror_rows),
        "merge_reasons": meta.get("merge_reasons") or {},
        "hemisphere_patterns": meta.get("hemisphere_patterns") or {},
        "modalities": meta.get("modalities") or {},
        "llm_run_ids": sorted({str(m.get("llm_run_id") or "") for m in mirror_rows if m.get("llm_run_id")}),
        "evidence_texts": [m.get("evidence_text", "")[:SUPPORTING_RECORD_TEXT_LIMIT]
                           for m in mirror_rows[:EVIDENCE_TEXT_SAMPLE_LIMIT]],
    }


def compute_evidence_quality(evidence_count: int, mirror_rows: list[dict]) -> tuple[str, dict]:
    """Evidence Quality Score(分析评分,不修改 confidence)。

    factors:
    - S_evidence:证据量,evidence_count/10 封顶
    - S_sources:来源多样性,distinct llm_run_id(≥3 封顶)
    - S_consistency:confidence 变异系数 CV = pstdev/mean;CV<=0.3→1, <=0.6→0.6, else 0.3;
      无 confidence → 0.5(中性)
    score = W_EVIDENCE*S_evidence + W_SOURCES*S_sources + W_CONSISTENCY*S_consistency
    high >= 0.7, medium >= 0.45, low < 0.45

    returns (score_label, factors)
    """
    confs = [float(m["confidence"]) for m in mirror_rows
             if m.get("confidence") not in (None, "")]
    run_ids = {str(m.get("llm_run_id") or "") for m in mirror_rows if m.get("llm_run_id")}

    s_evidence = min(evidence_count, 10) / 10.0
    s_sources = min(len(run_ids), 3) / 3.0
    if confs and len(confs) >= 2:
        m = mean(confs)
        cv = pstdev(confs) / m if m else 1.0
        s_consistency = 1.0 if cv <= 0.3 else (0.6 if cv <= 0.6 else 0.3)
    else:
        s_consistency = 0.5 if confs else 0.0

    score = round(W_EVIDENCE * s_evidence + W_SOURCES * s_sources
                  + W_CONSISTENCY * s_consistency, 4)
    if score >= HIGH_THRESHOLD:
        label = "high"
    elif score >= MEDIUM_THRESHOLD:
        label = "medium"
    else:
        label = "low"
    factors = {
        "score": score,
        "evidence_count": evidence_count,
        "distinct_llm_run_ids": len(run_ids),
        "confidence_count": len(confs),
        "s_evidence": round(s_evidence, 4),
        "s_sources": round(s_sources, 4),
        "s_consistency": round(s_consistency, 4),
        "weights": {"evidence": W_EVIDENCE, "sources": W_SOURCES,
                    "consistency": W_CONSISTENCY},
        "no_evidence": evidence_count == 0,
    }
    return label, factors


# ---- 查询辅助(纯逻辑) ----

CONNECTION_DETAIL_SQL = """
SELECT c.id, c.connection_code, c.connection_type, c.directionality_policy,
       c.evidence_count, c.confidence_statistics, c.evidence_summary,
       c.evidence_quality_score, c.evidence_quality_factors,
       rs.canonical_name_en AS source_region_name,
       rt.canonical_name_en AS target_region_name
FROM canonical_connections c
LEFT JOIN canonical_brain_regions rs ON rs.id = c.source_region_id
LEFT JOIN canonical_brain_regions rt ON rt.id = c.target_region_id
"""


def detail_from_row(r) -> dict:
    """canonical 行 → 单连接证据详情(查询返回结构)。"""
    es = r.evidence_summary or {}
    cs = r.confidence_statistics or {}
    return {
        "canonical_connection_id": str(r.id),
        "connection_code": r.connection_code,
        "source_region": r.source_region_name,
        "target_region": r.target_region_name,
        "connection_type": r.connection_type,
        "directionality_policy": r.directionality_policy,
        "evidence_summary": es,
        "supporting_records": es.get("supporting_records", []),
        "confidence": {
            "min": es.get("confidence_min", cs.get("min")),
            "max": es.get("confidence_max", cs.get("max")),
            "mean": es.get("confidence_mean", cs.get("avg")),
        },
        "evidence_quality_score": r.evidence_quality_score,
        "evidence_quality_factors": r.evidence_quality_factors or {},
    }


def connection_to_summary(r) -> dict:
    """canonical 行 → region 查询中的单条连接摘要。"""
    cs = r.confidence_statistics or {}
    return {
        "canonical_connection_id": str(r.id),
        "connection_code": r.connection_code,
        "source_region": r.source_region_name,
        "target_region": r.target_region_name,
        "connection_type": r.connection_type,
        "directionality_policy": r.directionality_policy,
        "evidence_count": r.evidence_count or 0,
        "confidence": {
            "min": cs.get("min"), "max": cs.get("max"), "mean": cs.get("avg"),
        },
        "evidence_quality_score": r.evidence_quality_score,
    }


def match_region(region_filter: str, region_name: str | None) -> bool:
    """region 过滤:大小写不敏感子串匹配。空 filter 匹配全部。"""
    if not region_filter:
        return True
    return (region_name or "").lower().find(region_filter.strip().lower()) >= 0


def summarize_connections(canonicals: list[dict]) -> dict:
    """region 查询返回结构:{total, connections: [{connection_code, source_region,
    target_region, connection_type, directionality_policy, evidence_count,
    confidence(min/max/mean), evidence_quality_score}]}
    """
    rows = []
    for c in canonicals:
        cs = c.get("confidence_statistics") or {}
        rows.append({
            "canonical_connection_id": c.get("id"),
            "connection_code": c.get("connection_code"),
            "source_region": c.get("source_region_name"),
            "target_region": c.get("target_region_name"),
            "connection_type": c.get("connection_type"),
            "directionality_policy": c.get("directionality_policy"),
            "evidence_count": c.get("evidence_count") or 0,
            "confidence": {
                "min": cs.get("min"),
                "max": cs.get("max"),
                "mean": cs.get("avg"),
            },
            "evidence_quality_score": c.get("evidence_quality_score"),
        })
    return {"total": len(rows), "connections": rows}
