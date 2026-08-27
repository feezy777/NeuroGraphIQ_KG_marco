"""Macro Connection canonical consolidation Pipeline 第 3 层 — 核心逻辑(纯函数)。

Connection Cluster → Canonical Connection + Evidence Summary + Lineage

* 匹配 key:source_region_id + target_region_id + connection_type(归一化)+ directionality(归一化)+ species
* 现有 canonical 完全匹配 → 复用 id;否则新建(status='proposed', assertion_type='reported_fact')
* evidence 上卷:evidence_count / evidence_sources / evidence_summary / confidence_statistics
* lineage:canonical → cluster → mirror 完整追溯
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field

GENERATION_METHOD = "macro_connection_consolidation_v1"

# cluster.connection_type(mirror 原值)→ canonical 词表
TYPE_NORM = {
    "structural_connection": "structural",
    "functional_connectivity": "functional",
    "uncertain_connection": "uncertain",
    "projection": "projection",
    "association": "association",
}

# cluster.directionality → canonical directionality_policy
DIR_NORM = {
    "unknown": "unspecified",
    "directed": "directed",
    "bidirectional": "bidirectional",
}


def norm_type(ctype: str) -> str:
    return TYPE_NORM.get(ctype, ctype)


def norm_dir(direction: str) -> str:
    return DIR_NORM.get(direction, direction)


def canonical_key(src_id, tgt_id, ctype: str, species: str = "human", _direction=None) -> tuple:
    """canonical key = (region 对 + type_norm + species)。

    方向不进入 key:canonical_connections 表级唯一约束 uq_canonical_connection
    (source_region_id, target_region_id, connection_type) 已决定语义——方向是属性
    (directionality_policy),多方向 cluster 合并到同一条 canonical,方向差异保留在
    evidence_summary.original_directions 中。_direction 保留兼容旧调用。
    """
    return (str(src_id), str(tgt_id), norm_type(ctype), species)


def pick_directionality(directions: list[str]) -> str:
    """多 cluster 合并时的 directionality_policy:全部一致用该值,混合用 unspecified。

    值必须落在 canonical 表 CHECK 词表(unspecified/directed/bidirectional),
    因此先做 DIR_NORM 归一化(unknown → unspecified)。
    """
    unique = {norm_dir(d) for d in directions if d}
    if len(unique) == 1:
        return next(iter(unique))
    return "unspecified"


@dataclass
class ClusterRow:
    """mirror_connection_clusters 表行(脚本加载后传入)。"""
    id: int
    cluster_key: str
    source_region_id: str
    target_region_id: str
    source_region_name: str
    target_region_name: str
    connection_type: str
    directionality: str
    modality_norm: str
    modality_original: list
    species: str
    hemisphere_groups: list
    mirror_connection_ids: list
    evidence_count: int
    merge_reason: str
    confidence_distribution: dict
    provenance: dict


@dataclass
class CanonicalPlan:
    """一个 cluster 的 canonical 归属。"""
    cluster: ClusterRow
    canonical_id: str | None      # None = 新建
    existing: bool                # True = 复用现有 canonical

    @property
    def key(self) -> tuple:
        return canonical_key(self.cluster.source_region_id, self.cluster.target_region_id,
                             self.cluster.connection_type, self.cluster.species)


def plan_canonicalization(clusters: list[ClusterRow], existing: list[dict]) -> list[CanonicalPlan]:
    """为每个 cluster 匹配现有 canonical(复用)或标记新建。

    key = (src id, tgt id, type_norm, species)——与 uq_canonical_connection 表约束对齐,
    方向不参与匹配(多方向 cluster 共享同一条 canonical)。

    existing: [{id, source_region_id, target_region_id, connection_type, species}]。
    """
    idx: dict[tuple, str] = {}
    for c in existing:
        k = canonical_key(c["source_region_id"], c["target_region_id"],
                          c["connection_type"], c.get("species") or "human")
        idx.setdefault(k, c["id"])  # 表约束保证 (src,tgt,type) 唯一
    return [
        CanonicalPlan(cluster=cl, canonical_id=idx.get(plan_key), existing=plan_key in idx)
        for cl in clusters
        for plan_key in [canonical_key(cl.source_region_id, cl.target_region_id,
                                       cl.connection_type, cl.species)]
    ]


def snake(name: str) -> str:
    return name.strip().lower().replace(" ", "_").replace("-", "_")


def build_connection_code(ctype: str, src_name: str, tgt_name: str, direction: str,
                          used_codes: set) -> str:
    """生成 ng:cn:{type}_{src}_to_{tgt} 格式;冲突时追加方向后缀保证唯一。"""
    base = f"ng:cn:{norm_type(ctype)}_{snake(src_name)}_to_{snake(tgt_name)}"
    if base not in used_codes:
        return base
    code = f"{base}_{norm_dir(direction)}"
    i = 2
    while code in used_codes:
        code = f"{base}_{norm_dir(direction)}_{i}"
        i += 1
    return code


def build_evidence_aggregation(cluster_to_canonical: dict[int, str],
                               clusters: list[ClusterRow]) -> dict:
    """按 canonical 聚合证据(上卷)。

    cluster_to_canonical: cluster_id → canonical_id,复用 + 新建全部解析完成后传入。
    证据完全来自本批 cluster,不合并历史 evidence_summary —— 保证幂等(重跑重算结果一致,
    且实测旧 summary 为退化值 0,无信息可合并);原始证据由 lineage
    (cluster → mirror_connection_ids)与 mirror 表完整保留。

    returns: {canonical_id: {"evidence_count", "evidence_sources", "evidence_summary",
                             "confidence_statistics", "cluster_ids"}}
    """
    agg: dict[str, dict] = defaultdict(lambda: {
        "cluster_ids": [], "evidence_count": 0, "modalities": Counter(),
        "merge_reasons": Counter(), "hemisphere_patterns": Counter(),
        "llm_run_ids": [], "evidence_texts": [],
        "conf_count": 0, "conf_sum": 0.0, "conf_min": float("inf"), "conf_max": 0.0,
        "buckets": Counter(),
        "original_directions": [], "mirror_connection_ids": [],
    })
    for cl in clusters:
        cid = cluster_to_canonical.get(cl.id)
        if cid is None:
            continue
        a = agg[cid]
        a["cluster_ids"].append(cl.id)
        a["evidence_count"] += cl.evidence_count
        a["modalities"][cl.modality_norm] += 1
        a["merge_reasons"][cl.merge_reason] += 1
        for g in cl.hemisphere_groups:
            a["hemisphere_patterns"][g["pattern"]] += g["evidence_count"]
        a["llm_run_ids"].extend(cl.provenance.get("llm_run_ids", []))
        a["evidence_texts"].extend(cl.provenance.get("evidence_texts", []))
        cd = cl.confidence_distribution or {}
        if cd.get("count"):
            a["conf_count"] += cd["count"]
            a["conf_sum"] += (cd.get("avg") or 0) * cd["count"]
            a["conf_min"] = min(a["conf_min"], cd.get("min") or 0)
            a["conf_max"] = max(a["conf_max"], cd.get("max") or 0)
            a["buckets"].update({float(k): int(v) for k, v in (cd.get("buckets") or {}).items()})
        a["original_directions"].extend(cl.provenance.get("directionality_original", []))
        a["mirror_connection_ids"].extend(cl.mirror_connection_ids)
    result = {}
    for cid, a in agg.items():
        stats = {"count": a["conf_count"]}
        if a["conf_count"]:
            stats.update({
                "min": a["conf_min"], "max": a["conf_max"],
                "avg": round(a["conf_sum"] / a["conf_count"], 4),
                "buckets": {f"{k:.1f}": v for k, v in sorted(a["buckets"].items())},
            })
        summary = {
            "cluster_count": len(a["cluster_ids"]),
            "total_evidence": a["evidence_count"],
            "modalities": dict(a["modalities"]),
            "merge_reasons": dict(a["merge_reasons"]),
            "hemisphere_patterns": dict(a["hemisphere_patterns"]),
            "cluster_ids": a["cluster_ids"],
            "llm_run_ids": sorted(set(a["llm_run_ids"])),
            "evidence_texts": [t[:200] for t in a["evidence_texts"][:10]],
            "original_directions": sorted(set(a["original_directions"])),
            "mirror_connection_ids": a["mirror_connection_ids"],
        }
        result[cid] = {
            "evidence_count": summary["total_evidence"],
            "evidence_sources": {
                "llm_run_ids": summary["llm_run_ids"],
                "evidence_text_count": len(a["evidence_texts"]),
                "source_versions": [],
            },
            "evidence_summary": summary,
            "confidence_statistics": stats,
            "cluster_ids": a["cluster_ids"],
        }
    return result
