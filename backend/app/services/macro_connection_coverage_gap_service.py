"""Macro Connection Coverage Gap Analysis V1 — 核心逻辑(纯函数,只读分析)。

基于 2485 条 verified Final Canonical Connection,重新分析 Macro96 连接覆盖,
确定下一阶段补缺范围。本模块不创建连接、不修改 Final KG、不做 CN2 inference。

数据语义:
* Macro96 池 = AAL3 96 区(left 44 + right 44 + midline 8)→ bilateral 概念 52 个。
* canonical/final 层是 bilateral 合并粒度;mirror 层保留 left/right 前缀命名。
* 对称性分析必须用 mirror 层(含左右信息);coverage/degree 用 final 层(已验证)。
"""

from __future__ import annotations

import re
from collections import defaultdict

# ---- 区域归一化 ----

def normalize_region_name(name: str | None) -> str:
    """'Left-Amygdala'/'left amygdala'/'Amygdala' → 'amygdala'(bilateral 概念键)。

    同时处理空格与连字符前缀(AAL3 两形式都存在:'left amygdala' / 'Left-Amygdala')。
    """
    if not name:
        return ""
    n = re.sub(r"^(left|right)[\s-]+", "", name.strip().lower())
    n = n.replace("-", " ")
    return " ".join(n.split())


def parse_side(name: str | None) -> tuple[str, str]:
    """解析左右侧:('left x'/'left-x' → ('x', 'L');无前缀 → ('x', 'M'))。"""
    if not name:
        return "", "M"
    s = name.strip()
    low = s.lower()
    if low.startswith(("left ", "left-")):
        return normalize_region_name(s), "L"
    if low.startswith(("right ", "right-")):
        return normalize_region_name(s), "R"
    return normalize_region_name(s), "M"


# ---- 1. Coverage Matrix ----

def build_coverage_matrix(
    pool: list[str],
    connections: list[dict],
) -> dict:
    """Macro96 bilateral 池 × 全对覆盖矩阵。

    connections: {src_name, tgt_name, evidence_count, connection_type}(final 层,
    bilateral 概念名)。返回 52×52 全对覆盖统计 + 摘要。
    """
    pool_sorted = sorted(pool)
    pair_keys = {(s, t) for s in pool_sorted for t in pool_sorted if s < t}
    per_pair: dict[tuple[str, str], dict] = {}

    def _pair(s: str, t: str) -> tuple[str, str]:
        # 无向对:固定字母序,双向连接合并为同一 region pair
        return (s, t) if s < t else (t, s)

    for c in connections:
        s, t = normalize_region_name(c.get("src_name")), normalize_region_name(c.get("tgt_name"))
        if s == t or s not in pool or t not in pool:
            continue
        p = _pair(s, t)
        entry = per_pair.setdefault(p, {
            "region_pair": p, "connection_count": 0, "evidence_count": 0,
            "connection_types": defaultdict(int),
        })
        entry["connection_count"] += 1
        entry["evidence_count"] += int(c.get("evidence_count") or 0)
        entry["connection_types"][c.get("connection_type") or "unknown"] += 1

    # 覆盖行/列统计
    covered = {p[0] for p in per_pair} | {p[1] for p in per_pair}
    matrix_rows = []
    for r in pool_sorted:
        pairs = {p for p in per_pair if r in p}
        matrix_rows.append({
            "region": r,
            "covered_pairs": len(pairs),
            "coverage_pct": round(len(pairs) / (len(pool_sorted) - 1) * 100, 2),
        })

    pairs_out = [dict(e, connection_types=dict(e["connection_types"]))
                 for e in sorted(per_pair.values(), key=lambda e: -e["connection_count"])]
    return {
        "pool_size": len(pool_sorted),
        "total_pairs": len(pair_keys),
        "covered_pairs": len(per_pair),
        "coverage_pct": round(len(per_pair) / len(pair_keys) * 100, 2),
        "covered_region_count": len(covered),
        "uncovered_regions": sorted(set(pool_sorted) - covered),
        "pair_detail": pairs_out,
        "region_rows": matrix_rows,
    }


# ---- 2. Region Degree ----

def compute_region_degree(
    pool: list[str],
    connections: list[dict],
) -> dict:
    """每 region 的 incoming / outgoing / total / structural / functional degree。"""
    incoming: dict[str, int] = defaultdict(int)
    outgoing: dict[str, int] = defaultdict(int)
    structural: dict[str, int] = defaultdict(int)
    functional: dict[str, int] = defaultdict(int)

    for c in connections:
        s = normalize_region_name(c.get("src_name"))
        t = normalize_region_name(c.get("tgt_name"))
        if s == t or s not in pool or t not in pool:
            continue
        outgoing[s] += 1
        incoming[t] += 1
        ctype = c.get("connection_type") or "unknown"
        if ctype == "structural":
            structural[s] += 1
            structural[t] += 1
        elif ctype == "functional":
            functional[s] += 1
            functional[t] += 1

    degrees = []
    for r in sorted(pool):
        deg_in, deg_out = incoming[r], outgoing[r]
        degrees.append({
            "region": r,
            "incoming_degree": deg_in,
            "outgoing_degree": deg_out,
            "total_degree": deg_in + deg_out,
            "structural_degree": structural[r],
            "functional_degree": functional[r],
        })

    totals = [d["total_degree"] for d in degrees]
    mean = sum(totals) / len(totals) if totals else 0.0
    sd = (sum((t - mean) ** 2 for t in totals) / len(totals)) ** 0.5 if totals else 0.0
    high_thr = mean + sd  # 高连接:> mean + 1σ
    low_thr = mean - sd   # 低连接:< mean - 1σ(含 0)

    for d in degrees:
        t = d["total_degree"]
        if t > high_thr:
            d["classification"] = "high_connectivity"
        elif t < low_thr:
            d["classification"] = "low_connectivity"
        else:
            d["classification"] = "normal"
        d["potential_missing"] = t == 0

    return {
        "region_count": len(degrees),
        "mean_total_degree": round(mean, 2),
        "high_threshold": round(high_thr, 2),
        "low_threshold": round(low_thr, 2),
        "high_connectivity_regions": [d["region"] for d in degrees
                                      if d["classification"] == "high_connectivity"],
        "low_connectivity_regions": [d["region"] for d in degrees
                                     if d["classification"] == "low_connectivity"],
        "zero_degree_regions": [d["region"] for d in degrees if d["total_degree"] == 0],
        "regions": degrees,
    }


# ---- 3. 双侧对称性分析(mirror 层) ----

def analyze_symmetry(
    pool: list[str],
    mirror_connections: list[dict],
) -> dict:
    """mirror 层左右侧对称性缺口检测。

    mirror_connections: {src_name, tgt_name, connection_type}(left/right 前缀)。
    对池内 bilateral 对 (X, Y),解析 4 种镜像组合:
      ll = left-X → left-Y;  rr = right-X → right-Y;
      lr = left-X → right-Y; rl = right-X → left-Y。
    分类(只生成候选):
      A1 高度可信镜像缺失:ll 存在而 rr 缺失(或反之)——双侧解剖对称是强先验
      A2 可能镜像缺失:一侧(源或目标)整体无连接,另一侧有
      B  需文献确认:ll 与 rr 都存在但 connection_type 不一致
    """
    pool_set = set(pool)
    per_pair: dict[tuple[str, str], dict[str, set[str]]] = defaultdict(
        lambda: {"ll": set(), "rr": set(), "lr": set(), "rl": set()})
    side_participation: dict[str, set[str]] = defaultdict(set)  # region → 参与的侧

    for c in mirror_connections:
        s_raw, t_raw = c.get("src_name"), c.get("tgt_name")
        s, s_side = parse_side(s_raw)
        t, t_side = parse_side(t_raw)
        if s == t or s not in pool_set or t not in pool_set:
            continue
        if s_side == "M" or t_side == "M":
            continue  # midline 区域无对称语义
        key = (s, t)
        combo = s_side.lower() + t_side.lower()
        per_pair[key][combo].add(c.get("connection_type") or "unknown")
        side_participation[s].add(s_side)
        side_participation[t].add(t_side)

    a1, a2, b = [], [], []
    for (x, y), combos in sorted(per_pair.items()):
        ll, rr = combos["ll"], combos["rr"]
        lr, rl = combos["lr"], combos["rl"]
        # A1:同侧镜像缺失(pair 粒度,双侧解剖对称是强先验)
        if ll and not rr:
            a1.append({"region_pair": (x, y), "missing_side": "right",
                       "existing": {"left_to_left": sorted(ll)},
                       "reason": "left X -> left Y exists, right X -> right Y missing"})
        elif rr and not ll:
            a1.append({"region_pair": (x, y), "missing_side": "left",
                       "existing": {"right_to_right": sorted(rr)},
                       "reason": "right X -> right Y exists, left X -> left Y missing"})
        # B:两侧都存在但类型不一致(需文献确认)
        if ll and rr and (ll != rr):
            b.append({"region_pair": (x, y),
                      "left_types": sorted(ll), "right_types": sorted(rr),
                      "reason": "mirror connections exist but types differ"})
    # A2:region 粒度 — 一侧整体无任何连接,另一侧有(可能镜像缺失)
    for region, sides in sorted(side_participation.items()):
        if "L" in sides and "R" not in sides:
            a2.append({"region": region, "missing_side": "right",
                       "existing_side": "left",
                       "reason": f"{region} has left-side connections, right side entirely missing"})
        elif "R" in sides and "L" not in sides:
            a2.append({"region": region, "missing_side": "left",
                       "existing_side": "right",
                       "reason": f"{region} has right-side connections, left side entirely missing"})

    return {
        "A1_high_confidence_missing": sorted(a1, key=lambda c: c["region_pair"]),
        "A2_possible_missing": sorted(a2, key=lambda c: c["region"]),
        "B_requires_literature": sorted(b, key=lambda c: c["region_pair"]),
        "counts": {"A1": len(a1), "A2": len(a2), "B": len(b)},
    }


# ---- 4. 功能合理性分析 ----

def find_functional_gap_candidates(
    pool: list[str],
    final_connections: list[dict],
    functions: list[dict],
) -> list[dict]:
    """功能高度相关区域但 final 层连接缺失 → 候选。

    functions: {region_name, function_term}(mirror 层,macro)。按 bilateral 概念聚合
    功能集合;池内区域对共享 ≥1 功能词且 final 层无连接 → 候选。
    """
    pool_set = set(pool)
    existing = set()
    for c in final_connections:
        s, t = normalize_region_name(c.get("src_name")), normalize_region_name(c.get("tgt_name"))
        if s != t and s in pool_set and t in pool_set:
            existing.add((s, t)); existing.add((t, s))

    func_by_region: dict[str, set[str]] = defaultdict(set)
    for f in functions:
        r = normalize_region_name(f.get("region_name"))
        if r in pool_set and f.get("function_term"):
            func_by_region[r].add(str(f.get("function_term")).lower())

    candidates = []
    regions = sorted(func_by_region)
    for i, x in enumerate(regions):
        for y in regions[i + 1:]:
            if (x, y) in existing:
                continue
            shared = func_by_region[x] & func_by_region[y]
            if not shared:
                continue
            candidates.append({
                "region_pair": (x, y),
                "shared_functions": sorted(shared),
                "x_functions": sorted(func_by_region[x]),
                "y_functions": sorted(func_by_region[y]),
                "final_connection_exists": False,
            })
    candidates.sort(key=lambda c: (-len(c["shared_functions"]), c["region_pair"]))
    return candidates


# ---- 5. 汇总候选 ----

def build_supplementation_candidates(
    matrix: dict,
    degree: dict,
    symmetry: dict,
    functional: list[dict],
) -> dict:
    """汇总全部补缺候选:未覆盖区域 / 零度区域 / A1+A2 对称缺失 / 功能候选。"""
    candidates = []
    # 1) 完全未覆盖区域(无任何 final 连接)
    for r in matrix["uncovered_regions"]:
        candidates.append({"kind": "uncovered_region", "region": r,
                           "priority": "high",
                           "reason": "region has no final connection at all"})
    # 2) 零度区域(degree=0,与 1 重合但来自 degree 视角)
    for r in degree["zero_degree_regions"]:
        if r not in matrix["uncovered_regions"]:
            candidates.append({"kind": "zero_degree_region", "region": r,
                               "priority": "high",
                               "reason": "total degree 0"})
    # 3) 对称性 A1(高度可信)
    for c in symmetry["A1_high_confidence_missing"]:
        candidates.append({"kind": "symmetry_A1", "region_pair": c["region_pair"],
                           "priority": "high", "detail": c["reason"],
                           "existing": c.get("existing")})
    # 4) 对称性 A2(可能缺失)
    for c in symmetry["A2_possible_missing"]:
        candidates.append({"kind": "symmetry_A2", "region_pair": c["region_pair"],
                           "priority": "medium", "detail": c["reason"],
                           "existing": c.get("existing")})
    # 5) 功能候选
    for c in functional:
        candidates.append({"kind": "functional_gap", "region_pair": c["region_pair"],
                           "priority": "low", "detail": "functionally related, no connection",
                           "shared_functions": c["shared_functions"]})
    by_kind: dict[str, int] = {}
    for c in candidates:
        by_kind[c["kind"]] = by_kind.get(c["kind"], 0) + 1
    return {
        "total_candidates": len(candidates),
        "by_kind": dict(sorted(by_kind.items())),
        "candidates": candidates,
    }
