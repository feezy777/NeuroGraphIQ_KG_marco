"""Macro96 Region Hierarchy Alignment 收口 — canonicalization 核心逻辑(纯函数)。

将已验证的 Macro96 池细分概念(part_of_candidate 6 条, confidence=0.9)正式
纳入 BrainRegion ontology,为 A1 hemisphere symmetry candidate 提供 canonical
region anchor:

  cerebellum exterior     -> canonical anchor 'Cerebellum Exterior'
  cerebellum white matter -> canonical anchor 'Cerebellum White Matter'
  ventral diencephalon    -> canonical anchor 'Ventral Diencephalon'

本服务(收口阶段)职责:
* REGION_ANCHORS:3 个 anchor 概念定义(region_code / 名称 / 父概念 / 别名),
  由实施脚本据此落 canonical_brain_regions + canonical_region_hierarchy +
  canonical_region_aliases(本文件只定义,不写库)。
* resolve_region_name:名称解析器 —— 带侧别名 -> 剥侧别 -> canonical 名称,
  与 connection_grounding_service.resolve_region_by_name 语义一致(其索引
  canonical_region_aliases + canonical 名称)。
* canonicalize_symmetry_candidates:重解析 A1 27 条 symmetry candidates ——
  已映射侧保留原 region_id,未映射侧(left/right 细分概念)解析到新 anchor。
* plan_canonicalization:组合 + 统计。

硬边界(用户指定):不 promotion、不创建 connection、不 CN2 inference、
不外部数据导入;只改 region ontology + 候选解析标注。
"""

from __future__ import annotations

from app.services.macro_connection_coverage_gap_service import (
    normalize_region_name,
)

# 解剖归属先验(与 alignment 阶段 ALIGNMENT_MAP 一致)
REGION_ANCHORS: dict[str, dict] = {
    "cerebellum exterior": {
        "region_code": "ng:br:cerebellum_exterior",
        "canonical_name_en": "Cerebellum Exterior",
        "canonical_name_cn": "小脑外部",
        "parent_name": "Cerebellum",
        "granularity_level": "clinical",
        "aliases": [
            "left cerebellum exterior",
            "right cerebellum exterior",
            "cerebellum exterior",
        ],
    },
    "cerebellum white matter": {
        "region_code": "ng:br:cerebellum_white_matter",
        "canonical_name_en": "Cerebellum White Matter",
        "canonical_name_cn": "小脑白质",
        "parent_name": "Cerebellum",
        "granularity_level": "clinical",
        "aliases": [
            "left cerebellum white matter",
            "right cerebellum white matter",
            "cerebellum white matter",
        ],
    },
    "ventral diencephalon": {
        "region_code": "ng:br:ventral_diencephalon",
        "canonical_name_en": "Ventral Diencephalon",
        "canonical_name_cn": "腹侧间脑",
        "parent_name": "Diencephalon",
        "granularity_level": "clinical",
        "aliases": [
            "left ventral diencephalon",
            "right ventral diencephalon",
            "ventral diencephalon",
        ],
    },
}

CONFIRMATION_METHOD = "macro_region_alignment_v1"
CONFIDENCE = 0.9
RESOLVED_STATUS = "canonical_region_resolved"
SOURCE_METHOD = "canonical_region_anchor"


def normalize_concept(name: str | None) -> str:
    """概念名归一化(小写、折叠空白,不剥侧别)。"""
    return " ".join((name or "").strip().lower().split())


def build_alias_map(alias_rows: list[dict]) -> dict[str, str]:
    """{normalize(alias): region_id} — resolver 索引(与 grounding service 同源)。"""
    out: dict[str, str] = {}
    for r in alias_rows:
        key = normalize_concept(r.get("alias"))
        if key:
            out[key] = str(r["region_id"])
    return out


def build_canonical_name_map(canonical_rows: list[dict]) -> dict[str, str]:
    """{normalize(canonical_name_en): region_id} — 解析兜底。"""
    out: dict[str, str] = {}
    for r in canonical_rows:
        key = normalize_concept(r.get("canonical_name_en"))
        if key:
            out[key] = str(r["id"])
    return out


def resolve_region_name(
    name: str | None,
    alias_map: dict[str, str],
    canonical_name_map: dict[str, str],
) -> str | None:
    """名称 -> canonical region id。

    解析顺序(与 grounding service 分层语义一致):
      1. 原样(含 side 前缀)命中别名 —— 'left cerebellum exterior' 直接落 anchor
      2. 剥 left/right 前缀后命中别名 —— 'cerebellum exterior' 落 anchor
      3. 剥侧别后命中 canonical 名称 —— 既有概念兜底
    全部不中 -> None(调用方记 unresolved)。
    """
    if not name:
        return None
    direct = normalize_concept(name)
    rid = alias_map.get(direct)
    if rid:
        return rid
    stripped = normalize_region_name(name)
    rid = alias_map.get(stripped)
    if rid:
        return rid
    return canonical_name_map.get(stripped)


def canonicalize_symmetry_candidates(
    candidates: list[dict],
    alias_map: dict[str, str],
    canonical_name_map: dict[str, str],
) -> dict:
    """重解析 A1 symmetry candidates。

    candidates: [{id, source_region_id, source_region_name, target_region_id,
                  target_region_name, connection_type, ...}]

    规则:
      * 已映射侧(source/target_region_id 非 NULL)保留原 id —— 不触碰幂等锚
      * 未映射侧(NULL)用 resolve_region_name 解析到新 canonical anchor
      * 双侧都解析成功 -> resolved(状态可升 canonical_region_resolved)
      * 任一失败 -> unresolved(附 missing 侧说明)

    返回 {resolved: [...], unresolved: [...]},纯函数零写入。
    """
    resolved: list[dict] = []
    unresolved: list[dict] = []
    for c in candidates:
        source_id = c.get("source_region_id")
        source_anchor = None
        if not source_id:
            source_id = resolve_region_name(
                c.get("source_region_name"), alias_map, canonical_name_map)
            source_anchor = source_id
        target_id = c.get("target_region_id")
        target_anchor = None
        if not target_id:
            target_id = resolve_region_name(
                c.get("target_region_name"), alias_map, canonical_name_map)
            target_anchor = target_id

        base = {
            "candidate_id": str(c["id"]),
            "source_region_name": c.get("source_region_name"),
            "target_region_name": c.get("target_region_name"),
            "connection_type": c.get("connection_type"),
        }
        if source_id and target_id:
            resolved.append({
                **base,
                "source_region_id": str(source_id),
                "target_region_id": str(target_id),
                "resolved_source_region_id": str(source_id),
                "resolved_target_region_id": str(target_id),
                "source_was_anchor_resolved": bool(source_anchor),
                "target_was_anchor_resolved": bool(target_anchor),
            })
        else:
            missing = []
            if not source_id:
                missing.append("source")
            if not target_id:
                missing.append("target")
            unresolved.append({**base, "missing": missing,
                               "reason": "unresolvable_region_name"})
    return {"resolved": resolved, "unresolved": unresolved}


def plan_canonicalization(
    candidates: list[dict],
    alias_rows: list[dict],
    canonical_rows: list[dict],
    hierarchy_edges: list[dict],
) -> dict:
    """全流程规划(纯函数):anchor 就绪检查 + 候选重解析 + 环检查 + 统计。

    alias_rows: [{alias, region_id}] — canonical_region_aliases 全量
    canonical_rows: [{id, canonical_name_en}] — canonical_brain_regions 全量
    hierarchy_edges: [{child_region_id, parent_region_id}] — 正式边全量

    返回 {anchors, alias_stats, resolution, counts}
    """
    alias_map = build_alias_map(alias_rows)
    canon_map = build_canonical_name_map(canonical_rows)

    # anchor 就绪检查:3 概念在 canonical 有实体 + 有别名 + 父概念存在
    anchors: list[dict] = []
    for concept, spec in REGION_ANCHORS.items():
        cid = canon_map.get(normalize_concept(spec["canonical_name_en"]))
        pid = canon_map.get(normalize_concept(spec["parent_name"]))
        alias_hits = [a for a in spec["aliases"]
                      if alias_map.get(normalize_concept(a))]
        anchors.append({
            "concept": concept,
            "region_code": spec["region_code"],
            "canonical_name_en": spec["canonical_name_en"],
            "canonical_region_id": cid,
            "parent_region_id": pid,
            "alias_ready": len(alias_hits),
            "alias_total": len(spec["aliases"]),
            "ready": bool(cid and pid) and len(alias_hits) == len(spec["aliases"]),
        })

    resolution = canonicalize_symmetry_candidates(
        candidates, alias_map, canon_map)

    edges = [(e["child_region_id"], e["parent_region_id"])
             for e in hierarchy_edges if e.get("child_region_id")]
    # 环检查:既有正式边本身(新 anchor 边已含,全图必须无环)
    from app.services.macro_region_alignment_service import has_cycle
    cyclic = has_cycle(edges, [])

    counts = {
        "anchor_total": len(REGION_ANCHORS),
        "anchor_ready": sum(1 for a in anchors if a["ready"]),
        "candidates_total": len(candidates),
        "resolved_candidates": len(resolution["resolved"]),
        "unresolved_candidates": len(resolution["unresolved"]),
        "hierarchy_cycle_detected": cyclic,
    }
    return {
        "anchors": anchors,
        "alias_map_size": len(alias_map),
        "resolution": resolution,
        "counts": counts,
    }
