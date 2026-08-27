"""Macro Connection Priority Classification V2 — 核心逻辑(纯函数,只读分析)。

基于最新 BrainRegion ontology(Macro96 Region Hierarchy Alignment 已完成:
  cerebellum exterior / cerebellum white matter / ventral diencephalon 已纳入
  canonical ontology,child canonical region ↓ part_of ↓ parent canonical),
重新计算 Macro96 Connection 覆盖缺口并建立补充优先级列表。

与 V1(coverage_gap)的差异:
* 3 个池细分概念不再视为"未覆盖缺失"——它们经 hierarchy 已由父概念
  (Cerebellum / Diencephalon)的连接语义覆盖,归 C 类(粒度造成的假缺失)。
* missing pairs 全量三分类:A(高可信,mirror 直接证据)/ B(潜在,需文献)/
  C(ignore:非实质脑区、hierarchy 已覆盖、粒度假缺失)。
* 27 条 A1 hemisphere symmetry candidate 重评估:提升到父概念后检查
  final 层是否已覆盖 → keep(需补充)/ discard(已覆盖)。

数据语义:
* Macro96 池 = AAL3 96 区 → bilateral 概念 52 个(含 3 细分概念)。
* final 层连接端点用 canonical 概念名;mirror 层保留 left/right 前缀。
* 本模块零写入:不创建连接、不 promotion、不改 Final KG、不 CN2 inference。
"""

from __future__ import annotations

import re
from collections import defaultdict

# ---- V1 基线(V1 分析于 2026-08-24,基于旧 ontology:3 细分概念无 canonical 实体) ----
V1_BASELINE: dict = {
    "pool_size": 52,
    "total_pairs": 1326,
    "covered_pairs": 1145,
    "coverage_pct": 86.35,
    "uncovered_regions": ["cerebellum exterior", "cerebellum white matter",
                          "ventral diencephalon"],
    "uncovered_regions_explanation": (
        "Macro96 细分概念在 canonical 层无实体,final 层无连接(连接挂在父概念 "
        "Cerebellum / Diencephalon 上)→ 被计为未覆盖缺失"),
}

# 3 个池细分概念 → 父概念(V2 中 hierarchy 已覆盖)
SUBDIVISION_PARENT: dict[str, str] = {
    "cerebellum exterior": "cerebellum",
    "cerebellum white matter": "cerebellum",
    "ventral diencephalon": "diencephalon",
}
SUBDIVISION_CONCEPTS = tuple(SUBDIVISION_PARENT)

# 非实质脑区(CSF / 脑室):连接无功能意义 → C 类 ignore
NON_SUBSTANTIVE_REGIONS = ("3rd ventricle", "4th ventricle",
                           "lateral ventricle", "csf")


def normalize_region_name(name: str | None) -> str:
    """'Left-Amygdala'/'left amygdala'/'Amygdala' → 'amygdala'(bilateral 键)。

    同时处理空格与连字符前缀(AAL3 两形式都存在)。与 V1 一致。
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


def _pair_key(s: str, t: str) -> tuple[str, str]:
    """无向对:固定字母序(双向连接合并为同一 region pair)。"""
    return (s, t) if s < t else (t, s)


# ---- 1. Coverage Matrix V2 ----

def build_coverage_matrix_v2(
    pool: list[str],
    connections: list[dict],
) -> dict:
    """Macro96 池 × 全对覆盖矩阵(V2:显式 missing_pairs 列表)。

    connections: {src_name, tgt_name, evidence_count, connection_type}(final 层)。
    """
    pool_sorted = sorted(pool)
    pair_keys = {(s, t) for s in pool_sorted for t in pool_sorted if s < t}
    per_pair: dict[tuple[str, str], dict] = {}

    for c in connections:
        s, t = normalize_region_name(c.get("src_name")), normalize_region_name(c.get("tgt_name"))
        if s == t or s not in pool_sorted or t not in pool_sorted:
            continue
        p = _pair_key(s, t)
        entry = per_pair.setdefault(p, {
            "region_pair": p, "connection_count": 0, "evidence_count": 0,
            "connection_types": defaultdict(int),
        })
        entry["connection_count"] += 1
        entry["evidence_count"] += int(c.get("evidence_count") or 0)
        entry["connection_types"][c.get("connection_type") or "unknown"] += 1

    covered = {p[0] for p in per_pair} | {p[1] for p in per_pair}
    matrix_rows = []
    for r in pool_sorted:
        pairs = {p for p in per_pair if r in p}
        matrix_rows.append({
            "region": r,
            "covered_pairs": len(pairs),
            "coverage_pct": round(len(pairs) / (len(pool_sorted) - 1) * 100, 2),
        })

    missing = sorted(pair_keys - set(per_pair))
    pairs_out = [dict(e, connection_types=dict(e["connection_types"]))
                 for e in sorted(per_pair.values(), key=lambda e: -e["connection_count"])]
    return {
        "pool_size": len(pool_sorted),
        "total_pairs": len(pair_keys),
        "covered_pairs": len(per_pair),
        "missing_pairs": [list(p) for p in missing],
        "coverage_pct": round(len(per_pair) / len(pair_keys) * 100, 2),
        "covered_region_count": len(covered),
        "uncovered_regions": sorted(set(pool_sorted) - covered),
        "pair_detail": pairs_out,
        "region_rows": matrix_rows,
    }


def compute_region_degree(
    pool: list[str],
    connections: list[dict],
) -> dict:
    """每 region 的 incoming / outgoing / total / structural / functional degree。

    isolated(degree=0)单独列出 —— V2 中细分概念 isolated 归 C 类。
    """
    incoming: dict[str, int] = defaultdict(int)
    outgoing: dict[str, int] = defaultdict(int)
    structural: dict[str, int] = defaultdict(int)
    functional: dict[str, int] = defaultdict(int)

    for c in connections:
        s, t = normalize_region_name(c.get("src_name")), normalize_region_name(c.get("tgt_name"))
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
    high_thr, low_thr = mean + sd, mean - sd

    for d in degrees:
        t = d["total_degree"]
        if t > high_thr:
            d["classification"] = "high_connectivity"
        elif t < low_thr:
            d["classification"] = "low_connectivity"
        else:
            d["classification"] = "normal"
        d["isolated"] = t == 0

    return {
        "region_count": len(degrees),
        "mean_total_degree": round(mean, 2),
        "high_threshold": round(high_thr, 2),
        "low_threshold": round(low_thr, 2),
        "high_connectivity_regions": [d["region"] for d in degrees
                                      if d["classification"] == "high_connectivity"],
        "low_connectivity_regions": [d["region"] for d in degrees
                                     if d["classification"] == "low_connectivity"],
        "isolated_regions": [d["region"] for d in degrees if d["isolated"]],
        "regions": degrees,
    }


# ---- 2. 缺失对三分类(A/B/C) ----

def _final_pair_set(final_connections: list[dict]) -> set[tuple[str, str]]:
    """final 层无向对集合(full 范围,不限池——父概念不在 Macro96 池内)。"""
    out: set[tuple[str, str]] = set()
    for c in final_connections:
        s, t = normalize_region_name(c.get("src_name")), normalize_region_name(c.get("tgt_name"))
        if s == t or not s or not t:
            continue
        out.add(_pair_key(s, t))
    return out


def _mirror_evidence_for_pairs(
    missing_pairs: list[tuple[str, str]],
    mirror_connections: list[dict],
) -> dict[tuple[str, str], dict]:
    """缺失对 → mirror 层直接证据(侧组合集合 + 类型)。

    mirror_connections: {src_name, tgt_name, connection_type}(left/right 前缀)。
    返回 {pair: {"combos": {...}, "types": set}} — 该 pair 在 mirror 层存在的
    侧组合(ll/lr/rl/rr),有任一组合即 A 类(对称体系已有证据)。
    """
    pool_pairs = set(missing_pairs)
    evidence: dict[tuple[str, str], dict] = defaultdict(
        lambda: {"combos": defaultdict(set), "types": set()})
    for c in mirror_connections:
        s, s_side = parse_side(c.get("src_name"))
        t, t_side = parse_side(c.get("tgt_name"))
        if s == t or s_side == "M" or t_side == "M":
            continue
        p = _pair_key(s, t)
        if p not in pool_pairs:
            continue
        combo = s_side.lower() + t_side.lower()
        evidence[p]["combos"][combo].add(c.get("connection_type") or "unknown")
        evidence[p]["types"].add(c.get("connection_type") or "unknown")
    return evidence


def _common_neighbors(
    pair: tuple[str, str],
    final_connections: list[dict],
    pool: set[str],
) -> list[str]:
    """网络关系佐证:pair 两端的共同连接区域(图论一跳共同邻居)。"""
    adj: dict[str, set[str]] = defaultdict(set)
    for c in final_connections:
        s, t = normalize_region_name(c.get("src_name")), normalize_region_name(c.get("tgt_name"))
        if s == t or s not in pool or t not in pool:
            continue
        adj[s].add(t)
        adj[t].add(s)
    return sorted(adj[pair[0]] & adj[pair[1]])


def _shared_functions(
    pair: tuple[str, str],
    func_by_region: dict[str, set[str]],
) -> list[str]:
    """功能关联佐证:两区域共享功能词。"""
    return sorted(func_by_region.get(pair[0], set()) & func_by_region.get(pair[1], set()))


def classify_missing_pairs(
    missing_pairs: list[tuple[str, str]],
    mirror_connections: list[dict],
    final_connections: list[dict],
    func_by_region: dict[str, set[str]],
) -> dict:
    """缺失对三分类(A 高可信 / B 潜在需文献 / C ignore)。

    判定顺序(C 最优先,保证细分概念与脑室对不误入 A/B):
      C1 粒度假缺失:pair 涉及池细分概念(3 个)且父概念对在 final 层已覆盖——
         child canonical ↓ part_of ↓ parent canonical,连接语义由父概念覆盖,
         粒度造成的假缺失。父概念对未覆盖 → 归 B(真实缺失,父概念粒度)。
      C2 非实质脑区:pair 涉及 ventricle / CSF → 连接无功能意义。
      A  高可信:mirror 层该 pair 存在直接连接证据(任一侧组合)——mirror
         evidence + hemisphere symmetry 体系支持 + final 层缺失(解剖合理为
         池内宏观概念间对,默认成立)。
      B  潜在:其余——无 mirror 直接证据,附功能关联 / 共同邻居佐证,需文献验证。

    返回 {A: [...], B: [...], C: [...], counts: {...}}
    """
    evidence = _mirror_evidence_for_pairs(missing_pairs, mirror_connections)
    pool = {r for p in missing_pairs for r in p}
    final_pairs = _final_pair_set(final_connections)

    a_list, b_list, c_list = [], [], []
    for p in sorted(missing_pairs):
        x, y = p
        # C1:细分概念对 → 父概念对已覆盖才为粒度假缺失
        if x in SUBDIVISION_CONCEPTS or y in SUBDIVISION_CONCEPTS:
            sx = SUBDIVISION_PARENT.get(x, x)
            sy = SUBDIVISION_PARENT.get(y, y)
            # 同一父概念的两个细分之间(如 cerebellum exterior ↔ white matter):
            # 同父内部细分对,非跨概念连接,粒度无意义
            if sx == sy:
                c_list.append({
                    "region_pair": list(p),
                    "class": "C",
                    "reason": "subdivision_same_parent",
                    "detail": (
                        f"{p[0]} 与 {p[1]} 同属父概念 {sx}:同一父概念内部细分对,"
                        "无跨概念连接语义(粒度造成)"),
                    "parent": sx,
                    "parent_pair": [sx, sx],
                })
                continue
            parent_pair = _pair_key(sx, sy)
            if parent_pair in final_pairs:
                sub = x if x in SUBDIVISION_CONCEPTS else y
                other = y if x in SUBDIVISION_CONCEPTS else x
                c_list.append({
                    "region_pair": list(p),
                    "class": "C",
                    "reason": "hierarchy_covered_subdivision",
                    "detail": (
                        f"{sub} ↓ part_of ↓ {SUBDIVISION_PARENT[sub]}:细分概念连接语义"
                        f"由父概念覆盖(父概念对已存在),粒度造成的假缺失"),
                    "parent": SUBDIVISION_PARENT[sub],
                    "parent_pair": list(parent_pair),
                })
                continue
            b_list.append({
                "region_pair": list(p),
                "class": "B",
                "reason": "subdivision_parent_missing",
                "detail": (
                    f"细分概念对 {p[0]}–{p[1]} 的父概念对 {parent_pair} 在 final "
                    "层未覆盖 —— 真实缺失,建议以父概念粒度补充"),
                "parent_pair": list(parent_pair),
            })
            continue
        # C2:非实质脑区(脑室 / CSF)
        if x in NON_SUBSTANTIVE_REGIONS or y in NON_SUBSTANTIVE_REGIONS:
            ns = x if x in NON_SUBSTANTIVE_REGIONS else y
            c_list.append({
                "region_pair": list(p),
                "class": "C",
                "reason": "non_substantive_region",
                "detail": f"{ns} 为非实质脑区(CSF/脑室),连接无功能意义",
            })
            continue
        # A:mirror 层直接证据
        ev = evidence.get(p)
        if ev and any(ev["combos"].values()):
            combos = {k: sorted(v) for k, v in sorted(ev["combos"].items()) if v}
            a_list.append({
                "region_pair": list(p),
                "class": "A",
                "reason": "mirror_evidence_missing_in_final",
                "mirror_combos": combos,
                "mirror_types": sorted(ev["types"]),
                "detail": "mirror 层存在连接证据,hemisphere symmetry 体系支持,"
                          "final 层缺失 → 高可信补充候选",
            })
            continue
        # B:其余(功能关联 / 共同邻居佐证,需文献验证)
        b_entry: dict = {
            "region_pair": list(p),
            "class": "B",
            "reason": "no_mirror_evidence_requires_literature",
            "detail": "无 mirror 直接证据,需文献验证",
        }
        shared = _shared_functions(p, func_by_region)
        neighbors = _common_neighbors(p, final_connections, pool)
        if shared:
            b_entry["shared_functions"] = shared
        if neighbors:
            b_entry["common_neighbors"] = neighbors
        if not shared and not neighbors:
            b_entry["detail"] = ("无 mirror 证据、无功能关联、无共同邻居 —— "
                                 "网络关系合理性存疑,需文献重点验证")
        b_list.append(b_entry)

    counts = {"A": len(a_list), "B": len(b_list), "C": len(c_list),
              "total": len(missing_pairs)}
    return {"A": a_list, "B": b_list, "C": c_list, "counts": counts}


# ---- 3. 27 条 A1 candidate 重评估 ----

def reassess_a1_candidates(
    candidates: list[dict],
    final_connections: list[dict],
    pool: set[str],
) -> list[dict]:
    """重评估 A1 hemisphere symmetry candidates(27 条,已 resolved)。

    每条 candidate:{source_region_name, target_region_name, ...}。
    规则:
      * 概念对中涉及池细分概念 → 提升到父概念(细分概念连接语义归父概念)
      * final 层 (父)概念对已覆盖 → discard(ontology 已覆盖,无需补充)
      * final 层 (父)概念对未覆盖 → keep(仍需补充,推荐父概念粒度)

    pool 参数仅用于过滤候选自身的细分/未知名称;covered 集合必须包含
    final 层全部连接 —— 父概念(Cerebellum / Diencephalon)不在 Macro96 池内,
    若按池过滤会误判父概念对全部未覆盖。

    返回逐条评估:keep/discard + 理由 + 父概念对 + final 覆盖状态。
    """
    covered: set[tuple[str, str]] = set()
    for c in final_connections:
        s, t = normalize_region_name(c.get("src_name")), normalize_region_name(c.get("tgt_name"))
        if s == t or not s or not t:
            continue
        covered.add(_pair_key(s, t))

    out = []
    for c in candidates:
        s = normalize_region_name(c.get("source_region_name"))
        t = normalize_region_name(c.get("target_region_name"))
        s_parent, t_parent = SUBDIVISION_PARENT.get(s, s), SUBDIVISION_PARENT.get(t, t)
        parent_pair = _pair_key(s_parent, t_parent)
        is_covered = parent_pair in covered

        reasons = []
        if s != s_parent:
            reasons.append(f"{s} → 父概念 {s_parent}(hierarchy 已覆盖)")
        if t != t_parent:
            reasons.append(f"{t} → 父概念 {t_parent}(hierarchy 已覆盖)")
        if s == t:
            reasons.append("自环无意义")

        recommendation = "discard" if is_covered or s == t else "keep"
        final_reason = ("ontology_covered" if is_covered
                        else "self_loop" if s == t
                        else "still_missing")
        out.append({
            "candidate_id": c.get("id") or str(c.get("candidate_id", "")),
            "source_region_name": c.get("source_region_name"),
            "target_region_name": c.get("target_region_name"),
            "source_concept": s,
            "target_concept": t,
            "parent_concept_pair": list(parent_pair),
            "parent_substitution": reasons,
            "final_parent_pair_covered": is_covered,
            "recommendation": recommendation,
            "reason": final_reason,
            "suggested_action": (
                "无需补充:父概念对已在 final 层覆盖(粒度缺失由 hierarchy 解析)"
                if recommendation == "discard" and is_covered else
                "丢弃:自环无意义" if recommendation == "discard" else
                "保留:父概念对仍缺失,建议以父概念粒度补充(Macro96 池宏观概念间连接)"),
        })
    return out


# ---- 4. 组合规划 ----

def plan_priority_classification(
    pool: list[str],
    final_connections: list[dict],
    mirror_connections: list[dict],
    func_by_region: dict[str, set[str]],
    a1_candidates: list[dict],
) -> dict:
    """全流程规划(纯函数):coverage V2 + degree + 三分类 + A1 重评估 + 新旧对比。

    func_by_region: {normalize(region): set(function_terms)}
    a1_candidates: [{id, source_region_name, target_region_name, ...}]
    """
    matrix = build_coverage_matrix_v2(pool, final_connections)
    degree = compute_region_degree(pool, final_connections)
    pool_set = set(pool)

    missing_pairs = [tuple(p) for p in matrix["missing_pairs"]]
    classification = classify_missing_pairs(
        missing_pairs, mirror_connections, final_connections, func_by_region)
    reassessment = reassess_a1_candidates(a1_candidates, final_connections, pool_set)

    keep_count = sum(1 for r in reassessment if r["recommendation"] == "keep")
    discard_count = len(reassessment) - keep_count

    # 新旧对比
    delta = {
        "coverage_pct": {
            "v1": V1_BASELINE["coverage_pct"],
            "v2": matrix["coverage_pct"],
            "note": "原始覆盖口径不变(final 层连接未增删);变化在缺失对的解析维度",
        },
        "uncovered_regions": {
            "v1": V1_BASELINE["uncovered_regions"],
            "v2": matrix["uncovered_regions"],
            "note": ("V1 计 3 个细分概念为未覆盖;V2 经 hierarchy 解析后不再视为"
                     "缺失(C 类),uncovered = 0"),
        },
        "missing_pairs": {
            "v1": V1_BASELINE["total_pairs"] - V1_BASELINE["covered_pairs"],
            "v2": len(missing_pairs),
        },
        "supplementation_scope": {
            "v1": "273 候选(V1:uncovered 3 + symmetry_A1 266 + functional 4)",
            "v2": f"A {classification['counts']['A']} + B {classification['counts']['B']}"
                  f"(C {classification['counts']['C']} 无需补充)",
        },
    }

    return {
        "matrix": matrix,
        "degree": degree,
        "classification": classification,
        "reassessment": reassessment,
        "reassessment_counts": {
            "total": len(reassessment),
            "keep": keep_count,
            "discard": discard_count,
            "discard_ontology_covered": sum(
                1 for r in reassessment
                if r["recommendation"] == "discard" and r["reason"] == "ontology_covered"),
        },
        "delta_v1_v2": delta,
    }
