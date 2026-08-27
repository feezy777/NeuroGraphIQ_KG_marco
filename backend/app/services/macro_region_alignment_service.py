"""Macro96 Region Hierarchy Alignment V1 — 核心逻辑(纯函数)。

解决 Macro Connection Coverage 补缺中发现的 BrainRegion 粒度映射问题:
  Macro96 池细分概念(cerebellum exterior / cerebellum white matter /
  ventral diencephalon)在 canonical 层无实体、无 part_of 边,但 candidate
  层已对齐到宏观概念(Cerebellum / Diencephalon)。

本服务生成 part_of_candidate 候选:
  cerebellum exterior   part_of_candidate -> Cerebellum
  cerebellum white matter part_of_candidate -> Cerebellum
  ventral diencephalon  part_of_candidate -> Diencephalon

生成规则(硬约束):
* 仅基于 candidate 层 alignment + 解剖学先验(ALIGNMENT_MAP),禁止 LLM /
  外部数据库。
* 候选不写入 canonical_region_hierarchy(正式边),需人工确认。
* 不创建 connection、不修改 Final KG、不做 promotion / CN2 inference。

治理定位:候选是独立层,child 为 candidate_brain_regions 行(左右各一),
parent 为 canonical 宏观概念(active)。
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from app.services.macro_connection_coverage_gap_service import (
    normalize_region_name,
)

# 解剖学先验:Macro96 池细分概念 → 宏观归属概念
ALIGNMENT_MAP: dict[str, str] = {
    "cerebellum exterior": "Cerebellum",
    "cerebellum white matter": "Cerebellum",
    "ventral diencephalon": "Diencephalon",
}

GENERATION_METHOD = "macro_region_alignment_v1"
RELATION_TYPE = "part_of_candidate"
ASSERTION_TYPE = "candidate"
CONFIDENCE = 0.9  # 解剖学明确 + candidate 层对齐佐证
EVIDENCE_SOURCE = "macro96_pool_anatomy + candidate_layer_alignment"


def normalize_concept(name: str | None) -> str:
    """概念名归一化(与 coverage/对称性阶段一致:小写、折叠空白)。"""
    return " ".join((name or "").strip().lower().split())


def analyze_region_status(
    concepts: list[str],
    canonical_names: list[str],
    hierarchy_edges: list[dict],
    alias_rows: list[dict],
    atlas_mapping_rows: list[dict],
    candidate_rows: list[dict],
) -> dict[str, dict]:
    """对每个概念输出在 ontology 各层的存在状态。

    canonical_names: [{canonical_name_en}] — canonical 层区域
    hierarchy_edges: [{child_region_name, parent_region_name}] — 既有 part_of 边
    alias_rows:      [{alias, region_name}] — canonical 区域别名
    atlas_mapping_rows: [{atlas_region_name}] — atlas 映射(atlas 区域侧名称)
    candidate_rows:  [{en_name, alignment_status, canonical_region_name}]
                     — candidate 层区域(candidate_brain_regions)
    """
    canon_set = {normalize_concept(n) for n in canonical_names}
    child_set = {normalize_concept(e["child_region_name"]) for e in hierarchy_edges}
    alias_set = {normalize_concept(a["alias"]) for a in alias_rows}
    atlas_set = {normalize_concept(a["atlas_region_name"]) for a in atlas_mapping_rows}

    status: dict[str, dict] = {}
    for c in concepts:
        key = normalize_concept(c)
        # candidate 行名带 left/right 前缀 → 用 normalize_region_name(剥侧别)匹配
        aligned = [r for r in candidate_rows
                   if normalize_region_name(r["en_name"]) == key
                   and r["alignment_status"] == "aligned"
                   and r["canonical_region_name"]]
        status[c] = {
            "has_canonical_region": key in canon_set,
            "has_parent_edge": key in child_set,
            "has_alias": key in alias_set,
            "has_atlas_mapping": key in atlas_set,
            "candidate_alignment_count": len(aligned),
            "candidate_alignment_targets": sorted({
                r["canonical_region_name"] for r in aligned}),
            "expected_parent": ALIGNMENT_MAP.get(c),
        }
    return status


def _find_candidate_rows(
    candidate_rows: list[dict],
    concept: str,
) -> list[dict]:
    """该概念在 candidate 层已 aligned 的行(left/right 各一)。"""
    key = normalize_concept(concept)
    return [r for r in candidate_rows
            if normalize_region_name(r["en_name"]) == key
            and r["alignment_status"] == "aligned"
            and r["canonical_region_name"]]


def build_hierarchy_candidates(
    candidate_rows: list[dict],
    canonical_by_name: dict[str, dict],
) -> list[dict]:
    """生成 part_of_candidate 候选(纯 dict,未落库)。

    candidate_rows: [{id, en_name, alignment_status, canonical_region_id,
                      canonical_region_name}]
    canonical_by_name: {normalize(名): {id, canonical_name_en, status}}

    每个 (概念, 侧别) 生成一条:child = candidate 层行,parent = canonical
    宏观概念。左右成对信息写入 provenance.bilateral_pair。
    """
    out: list[dict] = []
    for concept, parent_name in ALIGNMENT_MAP.items():
        parent = canonical_by_name.get(normalize_concept(parent_name))
        if not parent:
            continue  # 宏观概念缺失 → 无法生成(plan 层报 unresolved)
        rows = _find_candidate_rows(candidate_rows, concept)
        for r in rows:
            provenance = {
                "rule": "anatomical_part_of",
                "child_region": r["en_name"],
                "parent_region": parent_name,
                "basis": ["macro96_pool_anatomy", "candidate_layer_alignment"],
                "candidate_alignment": {
                    "candidate_region_id": r["id"],
                    "alignment_status": r["alignment_status"],
                    "canonical_region_id": r["canonical_region_id"],
                    "canonical_region_name": r["canonical_region_name"],
                },
                "bilateral_pair": _bilateral_pair(r["en_name"], rows),
                "precedent": (
                    "canonical_region_hierarchy 已有 Macro96 池细分先例: "
                    "Cerebellar vermal lobules -> Cerebellum (macro96_pool_mapping)"),
                "generation_method": GENERATION_METHOD,
            }
            out.append({
                "child_region_id": r["id"],
                "child_region_name": r["en_name"],
                "parent_region_id": parent["id"],
                "parent_region_name": parent_name,
                "relation_type": RELATION_TYPE,
                "evidence_source": EVIDENCE_SOURCE,
                "confidence": CONFIDENCE,
                "provenance_json": provenance,
                "generation_method": GENERATION_METHOD,
                "assertion_type": ASSERTION_TYPE,
                "status": "candidate",
                "concept": concept,
            })
    return out


def _bilateral_pair(name: str, rows: list[dict]) -> str:
    """对侧行名称(provenance 成对说明)。"""
    other = [r["en_name"] for r in rows if r["en_name"] != name]
    return other[0] if other else ""


def has_cycle(
    edges: list[tuple[str, str]],
    new_edges: list[tuple[str, str]],
) -> bool:
    """新边加入既有 hierarchy 后是否产生环(DFS)。

    edges / new_edges: (child_id, parent_id)。child != parent 校验与
    环检测同时进行:环存在 → True。
    """
    adj: dict[str, list[str]] = defaultdict(list)
    for u, v in edges + new_edges:
        if u == v:
            return True  # 自环即破坏(child == parent)
        adj[u].append(v)

    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[str, int] = {}

    def dfs(u: str) -> bool:
        color[u] = GRAY
        for w in adj.get(u, []):
            cw = color.get(w, WHITE)  # 未访问节点 get 返回 None,须给默认值
            if cw == GRAY:
                return True
            if cw == WHITE and dfs(w):
                return True
        color[u] = BLACK
        return False

    for u in list(adj):
        if color.get(u, WHITE) == WHITE and dfs(u):
            return True
    return False


def candidate_key(cand: dict) -> tuple:
    """幂等键:同 (child, parent, relation_type) 只建一次。"""
    return (cand["child_region_id"], cand["parent_region_id"],
            cand["relation_type"])


def is_duplicate_candidate(cand: dict, existing_candidates: list[dict]) -> bool:
    """与已落库候选重复?(幂等锚同义)"""
    key = candidate_key(cand)
    return any(candidate_key(e) == key for e in existing_candidates)


def plan_alignment(
    concepts: list[str],
    canonical_rows: list[dict],
    hierarchy_edges: list[dict],
    alias_rows: list[dict],
    atlas_mapping_rows: list[dict],
    candidate_rows: list[dict],
    existing_candidates: list[dict],
) -> dict:
    """全流程规划(纯函数):状态分析 + 候选生成 + 质量检查分类。

    返回 {status, candidates, existing, unresolved, conflict, counts}
    """
    canonical_names = [r.get("canonical_name_en") or "" for r in canonical_rows]
    status = analyze_region_status(
        concepts, canonical_names, hierarchy_edges, alias_rows,
        atlas_mapping_rows, candidate_rows)

    canonical_by_name = {}
    for r in canonical_rows:
        name = normalize_concept(r.get("canonical_name_en"))
        if name:
            canonical_by_name[name] = r

    # 对齐目标与解剖先验不一致 → conflict(人工裁决),该概念不生成候选
    conflict: list[dict] = []
    conflict_concepts: set[str] = set()
    for c in concepts:
        st = status[c]
        expected = normalize_concept(st["expected_parent"] or "")
        for t in st["candidate_alignment_targets"]:
            if normalize_concept(t) != expected:
                conflict.append({"concept": c, "aligned_to": t,
                                 "expected": st["expected_parent"],
                                 "reason": "alignment_mismatch"})
                conflict_concepts.add(c)

    candidates = [c for c in build_hierarchy_candidates(candidate_rows,
                                                        canonical_by_name)
                  if c["concept"] not in conflict_concepts]

    # 质量检查
    existing: list[dict] = []
    duplicate: list[dict] = []
    for cand in candidates:
        if is_duplicate_candidate(cand, existing_candidates):
            duplicate.append(cand)
            continue
        existing.append(cand)

    # 环检测:既有 hierarchy 边 + 新候选边
    existing_edges = [(e["child_region_id"], e["parent_region_id"])
                      for e in hierarchy_edges if e.get("child_region_id")]
    new_edges = [(c["child_region_id"], c["parent_region_id"]) for c in candidates]
    cyclic = has_cycle(existing_edges, new_edges)

    # unresolved:expected_parent 存在但无 aligned candidate 行 / 宏观概念缺失
    unresolved = []
    for c in concepts:
        st = status[c]
        if not st["expected_parent"]:
            unresolved.append({"concept": c, "reason": "no_expected_parent"})
            continue
        if st["candidate_alignment_count"] == 0:
            unresolved.append({"concept": c,
                               "reason": "no_candidate_alignment"})
        elif canonical_by_name.get(normalize_concept(st["expected_parent"])) is None:
            unresolved.append({"concept": c,
                               "reason": "expected_parent_missing_in_canonical"})

    counts = {
        "concepts_total": len(concepts),
        "existing_mapped_rows": sum(st["candidate_alignment_count"]
                                    for st in status.values()),
        "generated_candidates": len(existing),
        "duplicate_candidates": len(duplicate),
        "unresolved_concepts": len(unresolved),
        "conflict_candidates": len(conflict),
        "cycle_detected": cyclic,
    }
    return {
        "status": status,
        "candidates": existing,
        "duplicate": duplicate,
        "unresolved": unresolved,
        "conflict": conflict,
        "counts": counts,
    }
