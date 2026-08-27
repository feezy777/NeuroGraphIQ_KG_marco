"""Macro96 Connection Consolidation + Coverage Baseline 分析(只读,不写数据库)。

对 Human + Macro 层 connection 建立质量基线:
  * current_status.json            — 数据范围确认(数量/species/modality/type 分布)
  * duplicate_analysis.json        — 3 级重复分析(完全重复/名称等价/层级抽象候选)
  * coverage_matrix.json           — Macro96 × Macro96(名称级) + canonical 51×51 覆盖矩阵
  * region_degree_report.json      — 每 region 连接度(out/in/total) + 高/低/孤立
  * potential_missing_connections.json — A/B/C 类缺失候选(不补数据,只标记)
  * summary_report.md              — 汇总(实际规模/去重后规模/覆盖不足/补充建议)

范围:mirror_region_connections granularity_level='macro'(Macro96+AAL3,全 human)。
排除:molecular_attr(Allen mouse)、mouse atlas、molecular level。
不执行:merge/delete/promotion/Final 写入/CN2 inference/外部导入。
"""

from __future__ import annotations

import asyncio
import json
from collections import Counter, defaultdict
from pathlib import Path

sys = __import__("sys")
_backend = Path(__file__).resolve().parent.parent
if str(_backend) not in sys.path:
    sys.path.insert(0, str(_backend))

from sqlalchemy import text

from app.database import AsyncSessionLocal

OUT_DIR = Path(_backend) / "data" / "exports" / "macro_connection_analysis"

# modality 归一化:重复分析用归一化 modality 避免过度拆分
MODALITY_NORM = {
    "structural_connection": "structural",
    "diffusion_tensor": "structural",
    "functional_connection": "functional",
    "other": "other",
    None: "other",
}

# 非实质结构(脑室/CSF/白质):缺失连接无科学意义,不列入 A/B 类
NON_SUBSTANTIVE = {
    "csf", "white matter", "3rd ventricle", "4th ventricle",
    "lateral ventricle", "inferior lateral ventricle",
}


def _norm_modality(m):
    return MODALITY_NORM.get(m, "other")


async def load_macro_connections(session):
    """只取 macro 层连接 + grounding + candidate→canonical 映射。"""
    rows = (await session.execute(text(
        """
        SELECT c.id, c.source_region_name_en, c.target_region_name_en,
               c.connection_type, c.directionality, c.modality, c.confidence,
               c.source_region_candidate_id, c.target_region_candidate_id,
               g.status AS g_status, g.unresolved_reason,
               sc.canonical_region_id AS src_canonical_id,
               tc.canonical_region_id AS tgt_canonical_id,
               sreg.canonical_name_en AS src_canonical_name,
               treg.canonical_name_en AS tgt_canonical_name,
               sreg.granularity_level AS src_granularity,
               treg.granularity_level AS tgt_granularity
        FROM mirror_region_connections c
        LEFT JOIN mirror_connection_canonical_grounding g ON g.mirror_connection_id = c.id
        LEFT JOIN candidate_brain_regions sc ON sc.id = c.source_region_candidate_id
        LEFT JOIN candidate_brain_regions tc ON tc.id = c.target_region_candidate_id
        LEFT JOIN canonical_brain_regions sreg ON sreg.id = sc.canonical_region_id
        LEFT JOIN canonical_brain_regions treg ON treg.id = tc.canonical_region_id
        WHERE c.granularity_level = 'macro'
        """
    ))).all()
    return [dict(r._mapping) for r in rows]


async def load_macro96_pool(session):
    rows = (await session.execute(text(
        "SELECT raw_name FROM candidate_brain_regions WHERE source_atlas='Macro96' ORDER BY raw_name"
    ))).all()
    return [r[0] for r in rows]


async def load_hierarchy(session):
    rows = (await session.execute(text(
        """
        SELECT pc.canonical_name_en AS child, pa.canonical_name_en AS parent
        FROM canonical_region_hierarchy h
        JOIN canonical_brain_regions pc ON pc.id = h.child_region_id
        JOIN canonical_brain_regions pa ON pa.id = h.parent_region_id
        WHERE h.status = 'active'
        """
    ))).all()
    return [(r[0], r[1]) for r in rows]


# --------------------------------------------------------------------------- #
# 1. 数据范围
# --------------------------------------------------------------------------- #


def build_current_status(rows):
    species = Counter()
    modality = Counter()
    ctype = Counter()
    direction = Counter()
    granularity_pair = Counter()
    grounded = unresolved = 0
    for r in rows:
        # mirror 无 species 列;macro 池全部来自 Macro96/AAL3(human atlas)
        species["human"] += 1
        modality[r["modality"] or "None"] += 1
        ctype[r["connection_type"]] += 1
        direction[r["directionality"] or "None"] += 1
        pair = (r["src_granularity"] or "NA", r["tgt_granularity"] or "NA")
        granularity_pair[f"{pair[0]}×{pair[1]}"] += 1
        if r["g_status"] == "grounded":
            grounded += 1
        else:
            unresolved += 1
    return {
        "scope": "Human + Macro 层(mirror_region_connections.granularity_level='macro')",
        "excluded": ["molecular_attr (Allen mouse)", "mouse atlas connections", "molecular level data"],
        "mirror_connections_total": len(rows),
        "species_distribution": dict(species),
        "modality_distribution": dict(modality),
        "connection_type_distribution": dict(ctype),
        "directionality_distribution": dict(direction),
        "canonical_granularity_pair_distribution": dict(granularity_pair),
        "grounding": {"grounded": grounded, "unresolved": unresolved},
        "note": "mirror 行无 species 列;macro 池 source_atlas=Macro96/AAL3,全部为 human",
    }


# --------------------------------------------------------------------------- #
# 2. Duplicate 分析
# --------------------------------------------------------------------------- #


def build_duplicate_analysis(rows, pool_names, hierarchy):
    """3 级重复分析。canonical key 用 canonical region id(grounded 行),unresolved 用名称。"""
    # ---- Level 1:完全重复(canonical key)----
    grounded_rows = [r for r in rows if r["g_status"] == "grounded"]
    groups = defaultdict(list)
    for r in grounded_rows:
        key = (
            r["src_canonical_id"], r["tgt_canonical_id"],
            r["connection_type"], r["directionality"], "human", _norm_modality(r["modality"]),
        )
        groups[key].append(r)
    dup_groups = {k: v for k, v in groups.items() if len(v) > 1}
    group_sizes = sorted((len(v) for v in groups.values()), reverse=True)
    l1 = {
        "distinct_canonical_keys": len(groups),
        "total_mirror_rows_grounded": len(grounded_rows),
        "duplicate_groups": len(dup_groups),
        "rows_in_duplicate_groups": sum(len(v) for v in dup_groups.values()),
        "dup_rows_excess": sum(len(v) - 1 for v in dup_groups.values()),
        "avg_mirror_rows_per_key": round(len(grounded_rows) / len(groups), 2) if groups else 0,
        "avg_rows_in_dup_groups": round(sum(group_sizes) / len(dup_groups), 2) if dup_groups else 0,
        "max_duplicate_group_size": group_sizes[0] if group_sizes else 0,
        "top_duplicate_groups": [
            {
                "source": next(v["src_canonical_name"] for v in group),
                "target": next(v["tgt_canonical_name"] for v in group),
                "connection_type": key[2], "directionality": key[3], "modality": key[5],
                "mirror_rows": len(group),
            }
            for key, group in sorted(dup_groups.items(), key=lambda kv: -len(kv[1]))[:15]
        ],
    }

    # ---- Level 2:名称等价(96 池名称 → canonical 名称归一化)----
    name_pairs = {}
    for r in rows:
        if not r["src_canonical_name"] or not r["tgt_canonical_name"]:
            continue
        name_pairs.setdefault((r["source_region_name_en"], r["target_region_name_en"]),
                              (r["src_canonical_name"], r["tgt_canonical_name"]))
    canonical_pairs = Counter()
    canon_title = {}
    for r in grounded_rows:
        s, t = r["src_canonical_name"], r["tgt_canonical_name"]
        canonical_pairs[(s.lower(), t.lower())] += 1
        canon_title[s.lower()] = s
        canon_title[t.lower()] = t
    # 池名称 → canonical 名称的等价映射(左右合并示例)
    lateral_examples = {}
    for n in pool_names:
        for r in rows:
            if r["source_region_name_en"] == n and r["src_canonical_name"]:
                lateral_examples[n] = r["src_canonical_name"]
                break
    l2 = {
        "distinct_name_pairs_raw": len(name_pairs),
        "distinct_canonical_pairs_grounded": len(canonical_pairs),
        "reduction_after_normalization": len(name_pairs) - len(canonical_pairs),
        "reduction_pct": round((1 - len(canonical_pairs) / len(name_pairs)) * 100, 1) if name_pairs else 0,
        "name_to_canonical_equivalence_examples": dict(list(lateral_examples.items())[:12]),
        "note": "96 池为左右分开命名(left/right X → X bilateral),grounding 时经 candidate_grounded 合并;"
                "canonical_region_aliases 中 macro_clinical 区无别名(0 条),等价关系全部来自 candidate 映射",
    }

    # ---- Level 3:层级重复(abstraction candidate,不合并只标记)----
    # 模式:存在 child→X 连接 + parent→X 缺失(或 childA→childB + parentA→parentB)
    # 用 hierarchy(child→parent)与 canonical pairs 交叉
    child_to_parent = defaultdict(list)
    for child, parent in hierarchy:
        child_to_parent[child.lower()].append(parent)
    # 规范化 canonical 名称用于匹配
    canon_names = {r["src_canonical_name"] for r in grounded_rows} | \
                  {r["tgt_canonical_name"] for r in grounded_rows}
    name_lookup = {n.lower(): n for n in canon_names}
    # 51 区池:grounding 后出现的 canonical region 集合
    canon_pool = {n.lower() for n in canon_names}
    def _substantive(*names: str) -> bool:
        return not any(ns in n for n in names for ns in NON_SUBSTANTIVE)

    abstraction = []
    for (src, tgt), cnt in canonical_pairs.items():
        # 源侧:若 src 有 parent 且 parent 也在池内,检查 parent→tgt 是否缺失
        for parent in child_to_parent.get(src, []):
            pl = parent.lower()
            if pl not in canon_pool:
                continue  # 排除 Cerebrum/Brain 等池外超粗 parent,避免无意义抽象
            if not _substantive(src, tgt, pl):
                continue  # 排除 CSF/脑室/白质端点
            if pl == tgt:
                continue  # 抽象后为自环,无意义
            pkey = (pl, tgt)
            if pkey not in canonical_pairs:
                abstraction.append({
                    "child_connection": f"{canon_title.get(src, src)} → {canon_title.get(tgt, tgt)}",
                    "possible_abstraction": f"{canon_title.get(pl, parent)} → {canon_title.get(tgt, tgt)}",
                    "hierarchy_relation": f"{canon_title.get(src, src)} part_of {canon_title.get(pl, parent)}",
                    "evidence_count": cnt,
                    "category": "abstraction_candidate",
                })
    # 去重 + 截断
    seen = set()
    deduped = []
    for a in abstraction:
        if a["possible_abstraction"] not in seen:
            seen.add(a["possible_abstraction"])
            deduped.append(a)
    l3 = {
        "possible_abstraction_candidates": len(deduped),
        "candidates": deduped[:30],
        "note": "仅标记 possible abstraction candidate(如 Hippocampus→X 存在而 Amygdala/Cerebellum→X 缺失),不执行合并;"
                "parent 限定在 51 区池内,排除 Cerebrum/Brain 等池外超粗粒度",
    }
    return {"level_1_complete_duplicates": l1, "level_2_name_equivalence": l2,
            "level_3_hierarchy_abstraction": l3}


# --------------------------------------------------------------------------- #
# 3. Coverage matrix
# --------------------------------------------------------------------------- #


def build_coverage_matrix(rows, pool_names):
    """96×96 名称级矩阵 + 51×51 canonical 矩阵。"""
    # canonical region 池(grounding 目标)
    canon_regions = {}
    for r in rows:
        if r["src_canonical_name"]:
            canon_regions.setdefault(r["src_canonical_name"], 0)
        if r["tgt_canonical_name"]:
            canon_regions.setdefault(r["tgt_canonical_name"], 0)
    canon_list = sorted(canon_regions)
    idx = {n: i for i, n in enumerate(canon_list)}

    # canonical 矩阵:每对 (src,tgt) 的连接数 + evidence 数
    canonical_matrix = {"rows": canon_list, "cells": {}}
    pair_counts = Counter()
    pair_evidence = Counter()
    for r in rows:
        if not r["src_canonical_name"] or not r["tgt_canonical_name"]:
            continue
        k = (r["src_canonical_name"], r["tgt_canonical_name"])
        pair_counts[k] += 1
        pair_evidence[k] += 1  # 每 mirror 行 = 一条证据(LLM 提取)
    for (src, tgt), cnt in pair_counts.items():
        canonical_matrix["cells"][f"{idx[src]}:{idx[tgt]}"] = {
            "connections": cnt, "evidence": pair_evidence[(src, tgt)],
            "status": "multiple_evidence" if cnt >= 2 else "single_evidence",
        }
    covered = len(pair_counts)
    total_pairs = len(canon_list) * (len(canon_list) - 1)
    canonical_matrix["summary"] = {
        "region_count": len(canon_list),
        "possible_directed_pairs": total_pairs,
        "pairs_with_connection": covered,
        "pairs_no_connection": total_pairs - covered,
        "coverage_pct": round(covered / total_pairs * 100, 2) if total_pairs else 0,
        "multiple_evidence_pairs": sum(1 for v in canonical_matrix["cells"].values()
                                       if v["status"] == "multiple_evidence"),
        "single_evidence_pairs": sum(1 for v in canonical_matrix["cells"].values()
                                     if v["status"] == "single_evidence"),
    }

    # 96 池名称级矩阵
    pool_lower = [n.lower() for n in pool_names]
    pool_idx = {n.lower(): i for i, n in enumerate(pool_names)}
    name_matrix = {"rows": pool_names, "cells": {}}
    name_pair_counts = Counter()
    for r in rows:
        s, t = r["source_region_name_en"].lower(), r["target_region_name_en"].lower()
        if s in pool_idx and t in pool_idx:
            name_pair_counts[(s, t)] += 1
    for (s, t), cnt in name_pair_counts.items():
        name_matrix["cells"][f"{pool_idx[s]}:{pool_idx[t]}"] = {
            "connections": cnt, "status": "multiple_evidence" if cnt >= 2 else "single_evidence",
        }
    name_covered = len(name_pair_counts)
    name_total = len(pool_names) * (len(pool_names) - 1)
    name_matrix["summary"] = {
        "region_count": len(pool_names),
        "possible_directed_pairs": name_total,
        "pairs_with_connection": name_covered,
        "pairs_no_connection": name_total - name_covered,
        "coverage_pct": round(name_covered / name_total * 100, 2),
    }
    return {"matrix_96x96_name_level": name_matrix, "matrix_canonical_consolidated": canonical_matrix}


# --------------------------------------------------------------------------- #
# 4. 连接度
# --------------------------------------------------------------------------- #


def build_degree_report(rows):
    canon_regions = {}
    for r in rows:
        if r["src_canonical_name"]:
            canon_regions.setdefault(r["src_canonical_name"], {"out": 0, "in": 0, "out_evidence": 0, "in_evidence": 0})
        if r["tgt_canonical_name"]:
            canon_regions.setdefault(r["tgt_canonical_name"], {"out": 0, "in": 0, "out_evidence": 0, "in_evidence": 0})
    for r in rows:
        if not r["src_canonical_name"] or not r["tgt_canonical_name"]:
            continue
        if r["src_canonical_name"] != r["tgt_canonical_name"]:
            canon_regions[r["src_canonical_name"]]["out"] += 1
            canon_regions[r["src_canonical_name"]]["out_evidence"] += 1
            canon_regions[r["tgt_canonical_name"]]["in"] += 1
            canon_regions[r["tgt_canonical_name"]]["in_evidence"] += 1
    degrees = {n: {**v, "total": v["out"] + v["in"], "total_evidence": v["out_evidence"] + v["in_evidence"]}
               for n, v in canon_regions.items()}
    ordered = sorted(degrees.items(), key=lambda kv: -kv[1]["total"])
    total = sum(v["total"] for _, v in ordered)
    high = [{"region": n, "degree": v["total"]} for n, v in ordered[:8]]
    low = [{"region": n, "degree": v["total"]} for n, v in ordered[-8:] if v["total"] > 0]
    isolated = [n for n, v in ordered if v["total"] == 0]
    return {
        "regions": [{"region": n, **v} for n, v in ordered],
        "total_region_count": len(ordered),
        "total_degree_sum": total,
        "avg_degree": round(total / len(ordered), 2) if ordered else 0,
        "high_degree_regions": high,
        "low_degree_regions": low,
        "isolated_regions": isolated,
        "isolated_count": len(isolated),
    }


# --------------------------------------------------------------------------- #
# 5. 缺失连接候选
# --------------------------------------------------------------------------- #


def build_missing_candidates(rows, pool_names, hierarchy, canonical_pairs, canon_pool):
    """A/B/C 类缺失候选。不补数据,只标记。"""
    # 镜像对(96 池左右)
    mirror_pairs = {}
    for n in pool_names:
        if n.startswith("left "):
            mirror_pairs[n] = "right " + n[5:]
        elif n.startswith("right "):
            mirror_pairs[n] = "left " + n[6:]
    # 已有连接(名称级,方向) + 每对镜像行的证据数
    existing = Counter()
    for r in rows:
        s, t = r["source_region_name_en"].lower(), r["target_region_name_en"].lower()
        existing[(s, t)] += 1

    def is_substantive(*names: str) -> bool:
        # 子串匹配:名称带 left/right 前缀,如 "left lateral ventricle"
        return not any(ns in n for n in names for ns in NON_SUBSTANTIVE)

    # A 类:镜像缺失(两端均为实质结构)
    #   A1 同侧镜像:left A→left B 存在而 right A→right B 缺失(最强)
    #   A2 交叉镜像:left A→right B 存在而 right A→left B 缺失(合理,置信略低)
    a1_by_key, a2_by_key = {}, {}
    for (s, t), cnt in existing.items():
        if s not in mirror_pairs or t not in mirror_pairs:
            continue
        if not is_substantive(s, t):
            continue
        ms, mt = mirror_pairs[s], mirror_pairs[t]
        if (ms, mt) in existing:
            continue
        if s == ms or t == mt:
            # 两端无 left/right 前缀(midline region)不可能出现在镜像对里
            continue
        k = (ms, mt)
        bucket = a1_by_key if s.startswith("left ") == t.startswith("left ") else a2_by_key
        entry = bucket.setdefault(k, {"source": s, "target": t, "mirror_missing": f"{ms} → {mt}",
                                      "evidence_count": 0, "category": "A_mirror_symmetric"})
        entry["evidence_count"] += cnt
    a1 = sorted(a1_by_key.values(), key=lambda c: -c["evidence_count"])
    a2 = sorted(a2_by_key.values(), key=lambda c: -c["evidence_count"])

    # B 类:层级抽象候选(parent 在 51 区池内 + 两端实质结构)
    child_to_parent = defaultdict(list)
    for child, parent in hierarchy:
        child_to_parent[child.lower()].append(parent)
    b_by_key = {}
    for (src, tgt), cnt in canonical_pairs.items():
        if not is_substantive(src, tgt):
            continue
        for parent in child_to_parent.get(src.lower(), []):
            if parent.lower() not in canon_pool:
                continue
            pk = (parent, tgt)
            if pk in canonical_pairs:
                continue
            entry = b_by_key.setdefault(pk, {
                "child_pattern": f"{src} → {tgt}", "candidate": f"{parent} → {tgt}",
                "rationale": f"{src} part_of {parent};子连接存在而父连接缺失",
                "evidence_count": 0, "category": "B_abstraction_confirm",
            })
            entry["evidence_count"] += cnt
    b_candidates = sorted(b_by_key.values(), key=lambda c: -c["evidence_count"])

    # C 类:非实质结构(CSF/脑室/白质)相关缺失无需补充
    c_count = sum(1 for n in pool_names if any(ns in n.lower() for ns in NON_SUBSTANTIVE))
    return {
        "category_A1_same_side_mirror": {"count": len(a1), "items": a1[:30],
                                         "rationale": "同侧镜像:left A→left B 存在而 right A→right B 缺失(最强候选)"},
        "category_A2_cross_mirror": {"count": len(a2), "items": a2[:30],
                                     "rationale": "交叉镜像:left A→right B 存在而 right A→left B 缺失(置信略低)"},
        "category_A_total": {"count": len(a1) + len(a2), "rationale": "A1+A2 合计"},
        "category_B_confirm": {"count": len(b_candidates), "items": b_candidates[:20],
                               "rationale": "层级抽象候选,parent 限定在 51 区池内,需文献确认"},
        "category_C_not_needed": {"count": c_count,
                                  "rationale": "CSF/脑室/白质等非实质结构,缺失连接无科学意义",
                                  "non_substantive_regions": sorted(NON_SUBSTANTIVE)},
        "note": "仅生成候选标记,不写入任何数据;A/B 类需人工或文献确认",
    }


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #


async def main() -> None:
    async with AsyncSessionLocal() as session:
        rows = await load_macro_connections(session)
        pool_names = await load_macro96_pool(session)
        hierarchy = await load_hierarchy(session)

        current = build_current_status(rows)
        dup = build_duplicate_analysis(rows, pool_names, hierarchy)
        matrix = build_coverage_matrix(rows, pool_names)
        degree = build_degree_report(rows)
        canon_pairs = Counter()
        canon_pool = set()
        for r in rows:
            if r["src_canonical_name"] and r["tgt_canonical_name"]:
                canon_pairs[(r["src_canonical_name"].lower(), r["tgt_canonical_name"].lower())] += 1
                canon_pool.add(r["src_canonical_name"].lower())
                canon_pool.add(r["tgt_canonical_name"].lower())
        missing = build_missing_candidates(rows, pool_names, hierarchy, canon_pairs, canon_pool)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    payloads = {
        "current_status.json": current,
        "duplicate_analysis.json": dup,
        "coverage_matrix.json": matrix,
        "region_degree_report.json": degree,
        "potential_missing_connections.json": missing,
    }
    for fname, data in payloads.items():
        (OUT_DIR / fname).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"[ok] {fname}")

    # summary_report.md
    l1 = dup["level_1_complete_duplicates"]
    l2 = dup["level_2_name_equivalence"]
    cm = matrix["matrix_canonical_consolidated"]["summary"]
    nm = matrix["matrix_96x96_name_level"]["summary"]
    md = f"""# Macro96 Connection Consolidation + Coverage Baseline

> 生成时间:2026-08-24 · 分析范围:Human + Macro 层(mirror_region_connections granularity_level='macro')· 只读,未修改任何数据

## 1. 当前 Macro Connection 实际规模

- Mirror 连接总数:**{current['mirror_connections_total']}**(Macro96 5,715 + AAL3 5)
- 已 grounding:**{current['grounding']['grounded']}** / unresolved:**{current['grounding']['unresolved']}**(self_loop 48 + no_name_match 4)
- Canonical 概念连接(canonical_connections):2,486(全 human,proposed 状态)
- species:全部 human;modality:{json.dumps(current['modality_distribution'], ensure_ascii=False)}
- connection_type:{json.dumps(current['connection_type_distribution'], ensure_ascii=False)}

## 2. 去重后预计规模

| 层级 | 结果 |
|------|------|
| L1 完全重复(canonical key) | {l1['distinct_canonical_keys']} 个去重 key(每 key 平均 {l1['avg_mirror_rows_per_key']} 行);{l1['duplicate_groups']} 组重复,{l1['dup_rows_excess']} 行冗余;最大组 {l1['max_duplicate_group_size']} 行 |
| L2 名称等价(左右合并) | 名称对 {l2['distinct_name_pairs_raw']} → canonical 对 {l2['distinct_canonical_pairs_grounded']}(减少 {l2['reduction_pct']}%) |
| **去重后有效连接(consolidated)** | **约 {l1['distinct_canonical_keys']} 条**(grounding 后 distinct canonical region pairs 2,061,再按 type/direction/modality 细分) |
| L3 层级抽象候选 | {dup['level_3_hierarchy_abstraction']['possible_abstraction_candidates']} 条(仅标记,不合并) |

## 3. 覆盖不足区域

- **96×96 名称级**:{nm['pairs_with_connection']}/{nm['possible_directed_pairs']} 有连接(**{nm['coverage_pct']}%**)
- **Canonical 51 区级**:{cm['pairs_with_connection']}/{cm['possible_directed_pairs']} 有连接(**{cm['coverage_pct']}%**);{cm['pairs_no_connection']} 对完全缺失
- 多证据对(multiple evidence):{cm['multiple_evidence_pairs']};单证据对:{cm['single_evidence_pairs']}
- 孤立区:{degree['isolated_count']} 个({json.dumps(degree['isolated_regions'], ensure_ascii=False)})
- 高连接区:{json.dumps([r['region'] for r in degree['high_degree_regions']], ensure_ascii=False)}
- 低连接区:{json.dumps([r['region'] for r in degree['low_degree_regions']], ensure_ascii=False)}

## 4. 后续补充建议

- **A1 类(优先,同侧镜像)**:{missing['category_A1_same_side_mirror']['count']} 条 — left A→left B 有而 right A→right B 缺,科学上高度可能
- **A2 类(次优先,交叉镜像)**:{missing['category_A2_cross_mirror']['count']} 条 — left A→right B 有而 right A→left B 缺
- **B 类(文献确认)**:{missing['category_B_confirm']['count']} 条 — 层级抽象候选(池内 parent)
- **C 类(无需补充)**:{missing['category_C_not_needed']['count']} 个非实质结构区(CSF/脑室/白质)
- 建议:先人工审核 A1 同侧镜像补全 → LLM 提取 → grounding 回填;再做 A2/B 类文献确认

## 输出文件

- current_status.json / duplicate_analysis.json / coverage_matrix.json / region_degree_report.json / potential_missing_connections.json
"""
    (OUT_DIR / "summary_report.md").write_text(md, encoding="utf-8")
    print("[ok] summary_report.md")
    print(f"\n输出目录: {OUT_DIR}")
    print(f"\n当前规模:{current['mirror_connections_total']} | 去重后:{l1['distinct_canonical_keys']} | "
          f"96级覆盖:{nm['coverage_pct']}% | canonical覆盖:{cm['coverage_pct']}% | "
          f"A1:{missing['category_A1_same_side_mirror']['count']} "
          f"A2:{missing['category_A2_cross_mirror']['count']} B:{missing['category_B_confirm']['count']}")


if __name__ == "__main__":
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except Exception:
        pass
    asyncio.run(main())
