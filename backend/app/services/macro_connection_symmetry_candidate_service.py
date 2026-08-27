"""Macro Connection Symmetry Candidate Generation V1 — 核心逻辑(纯函数)。

针对 Coverage Analysis 的 A1 高可信镜像缺失候选生成 candidate connection:
  已有 Left A → Left B,缺 Right A → Right B(或反之)→ bilateral symmetry candidate。

生成规则(硬约束):
* 仅允许已有连接(mirror 层)作为依据 —— source_connection_id 必填。
* 禁止:LLM 生成、外部数据库、自动进入 Final / canonical active。
* assertion_type = 'candidate',generation_method = 'hemisphere_symmetry_v1'。

治理定位:candidate 是独立的候选层,不进入 canonical_connections(不 active),
不写入 final_canonical_connections。与 canonical 已有连接冲突 → conflict 不生成。
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from app.services.macro_connection_coverage_gap_service import (
    normalize_region_name,
    parse_side,
)

GENERATION_METHOD = "hemisphere_symmetry_v1"
RULE = "hemisphere_symmetry"
ASSERTION_TYPE = "candidate"

# mirror 层连接类型 → canonical 词表(structural/functional/uncertain/association)
TYPE_MAP = {
    "structural_connection": "structural",
    "functional_connectivity": "functional",
    "uncertain_connection": "uncertain",
    "association_connection": "association",
}


def normalize_connection_type(mirror_type: str | None) -> str:
    """mirror 类型归一化到 canonical 词表;未知类型原样保留。"""
    t = (mirror_type or "").strip().lower()
    return TYPE_MAP.get(t, t or "unknown")


def build_region_map(canonical_rows: list[dict]) -> dict[str, str]:
    """canonical 层 bilateral 概念映射:{normalize(name) → region_id}。

    canonical_rows: {id, canonical_name_en, laterality}。仅收 bilateral——
    candidate 与 Final 层同粒度(左右侧信息放 provenance)。
    """
    out: dict[str, str] = {}
    for r in canonical_rows:
        if (r.get("laterality") or "bilateral") != "bilateral":
            continue
        name = normalize_region_name(r.get("canonical_name_en"))
        if name:
            out[name] = r["id"]
    return out


def find_mirror_source(
    a1_item: dict,
    mirror_conns: list[dict],
) -> list[dict]:
    """找 A1 候选的 mirror 源连接(已有 side 的证据)。

    a1_item: {region_pair: [x, y](字母序), missing_side: 'left'|'right',
              existing: {left_to_left: [...types]} 或 {right_to_right: [...]}}
    mirror_conns: {id, src_name, tgt_name, connection_type, directionality,
                   modality, confidence}(mirror 层 macro,原文保留)。

    existing side = missing_side 的对侧。对 (pair, existing_type) 各返回
    第一条方向匹配的 mirror 连接(保持真实方向)。
    """
    x, y = a1_item["region_pair"]
    existing_side = "right" if a1_item["missing_side"] == "left" else "left"
    existing_types = set(
        (a1_item.get("existing") or {})
        .get({"left": "left_to_left", "right": "right_to_right"}[existing_side], []))
    existing_code = "L" if existing_side == "left" else "R"  # parse_side 返回大写缩写

    found: list[dict] = []
    for m in mirror_conns:
        s, s_side = parse_side(m.get("src_name"))
        t, t_side = parse_side(m.get("tgt_name"))
        if s_side != existing_code or t_side != existing_code:
            continue
        # A1 region_pair 是镜像连接的有向序(per_pair key = (src, tgt));
        # 双向都接受(同一对可能有多条方向相反的 mirror 连接),candidate 保留 mirror 原方向
        if (s, t) != (x, y) and (t, s) != (x, y):
            continue
        mtype = m.get("connection_type") or "unknown"
        if mtype not in existing_types:
            continue
        found.append(m)
    return found


def build_candidate(
    mirror_row: dict,
    a1_item: dict,
    region_map: dict[str, str],
) -> dict:
    """由 mirror 源连接推断 bilateral candidate(纯 dict,未落库)。

    方向继承 mirror 源连接(A → B)。region 无法映射到 canonical(池细分概念,
    如 cerebellum exterior / ventral diencephalon)→ region_id 为 None,名称保留,
    待人工映射到宏观概念——缺口信息不丢失。
    """
    x, y = a1_item["region_pair"]
    s, s_side = parse_side(mirror_row.get("src_name"))
    t, t_side = parse_side(mirror_row.get("tgt_name"))
    src_id = region_map.get(s)
    tgt_id = region_map.get(t)
    region_unmapped = not src_id or not tgt_id

    mirror_type = mirror_row.get("connection_type") or "unknown"
    missing_side = a1_item["missing_side"]
    src_side_name = f"{missing_side} {s}"
    tgt_side_name = f"{missing_side} {t}"

    provenance = {
        "rule": RULE,
        "original_side": "right" if s_side == "R" else "left",  # 已有连接的侧别
        "inferred_side": missing_side,                          # 推断候选的侧别(对侧)
        "source_connection": {
            "mirror_connection_id": mirror_row.get("id"),
            "source_region_name": mirror_row.get("src_name"),
            "target_region_name": mirror_row.get("tgt_name"),
            "connection_type": mirror_type,
            "directionality": mirror_row.get("directionality"),
            "modality": mirror_row.get("modality"),
            "confidence": mirror_row.get("confidence"),
        },
        "inferred_candidate": {
            "source_region": src_side_name,  # 推断候选名称(对侧)
            "target_region": tgt_side_name,
            "inferred_side_pair": f"{src_side_name}_to_{tgt_side_name}",
            "connection_type": normalize_connection_type(mirror_type),
        },
        "generation_method": GENERATION_METHOD,
    }
    return {
        "source_region_id": src_id,
        "target_region_id": tgt_id,
        "source_region_name": src_side_name,  # 候选侧别的名称(region 未映射时保留待人工映射)
        "target_region_name": tgt_side_name,
        "connection_type": normalize_connection_type(mirror_type),
        "mirror_connection_type": mirror_type,
        "direction": mirror_row.get("directionality"),
        "modality": mirror_row.get("modality"),
        "source_connection_id": mirror_row.get("id"),
        "generation_method": GENERATION_METHOD,
        "assertion_type": ASSERTION_TYPE,
        "confidence": mirror_row.get("confidence"),
        "provenance_json": provenance,
        "status": "candidate",
        "region_pair": (x, y),
        "missing_side": missing_side,
        "region_unmapped": region_unmapped,
        "suggested_mapping": _suggest_mapping(mirror_row, region_unmapped),
    }


def _suggest_mapping(mirror_row: dict, region_unmapped: bool) -> dict | None:
    """未映射概念的建议映射目标(人工后续决定)。"""
    if not region_unmapped:
        return None
    s, s_side = parse_side(mirror_row.get("src_name"))
    t, t_side = parse_side(mirror_row.get("tgt_name"))
    macro_map = {
        "cerebellum exterior": "Cerebellum",
        "cerebellum white matter": "Cerebellum",
        "ventral diencephalon": "Diencephalon",
    }
    return {
        "unmapped_concepts": [s, t],
        "suggested_macro_targets": sorted({macro_map.get(r, r) for r in (s, t)}),
        "note": "Macro96 池细分概念在 canonical 层无 bilateral 对应;"
                "建议人工映射到宏观概念后再进入 canonical review",
    }


def is_conflict(candidate: dict, existing_canonicals: list[dict]) -> bool:
    """candidate 与 canonical 已有连接冲突?

    canonical 层已存在同 (region pair, connection_type) 且 status 非 deprecated
    → 该连接在 canonical 层已被代表,不需要对称 candidate。
    """
    s, t = candidate["source_region_id"], candidate["target_region_id"]
    ctype = candidate["connection_type"]
    for c in existing_canonicals:
        if c.get("status") == "deprecated":
            continue
        if c.get("connection_type") != ctype:
            continue
        cs, ct = c.get("source_region_id"), c.get("target_region_id")
        if (cs == s and ct == t) or (cs == t and ct == s):
            return True
    return False


def candidate_key(cand: dict) -> tuple:
    """幂等键:region id(未映射时用归一化名称兜底)+ type + mirror 源连接 id。"""
    s = cand.get("source_region_id") or normalize_region_name(cand.get("source_region_name"))
    t = cand.get("target_region_id") or normalize_region_name(cand.get("target_region_name"))
    return (s, t, cand.get("connection_type"), cand.get("source_connection_id"))


def is_duplicate(candidate: dict, existing_candidates: list[dict]) -> bool:
    """与已生成的 candidate 重复?(幂等锚同义,NULL region id 用名称兜底)"""
    key = candidate_key(candidate)
    return any(candidate_key(e) == key for e in existing_candidates)


def plan_generation(
    a1_items: list[dict],
    mirror_conns: list[dict],
    canonical_rows: list[dict],
    existing_canonicals: list[dict],
    existing_candidates: list[dict],
) -> dict:
    """生成规划(纯函数):对全部 A1 候选分类 generated / skipped / conflict / duplicate。

    返回 {generated: [...], skipped: [{pair, reason}], conflict: [{pair, reason}],
          duplicate: [...], by_region_missing: [...], counts: {...}}
    """
    region_map = build_region_map(canonical_rows)
    generated: list[dict] = []
    skipped: list[dict] = []
    conflict: list[dict] = []
    duplicate: list[dict] = []
    seen_keys: set[tuple] = set()  # 本批内去重(同一 A1 多条同 type 源连接)

    for a1 in a1_items:
        x, y = a1["region_pair"]
        sources = find_mirror_source(a1, mirror_conns)
        if not sources:
            skipped.append({"region_pair": (x, y), "reason": "no_mirror_source",
                            "missing_side": a1["missing_side"]})
            continue
        per_type: set[str] = set()
        for m in sources:
            mtype = m.get("connection_type") or "unknown"
            if mtype in per_type:
                continue  # 每 (pair, side, type) 只生成一条
            per_type.add(mtype)
            cand = build_candidate(m, a1, region_map)
            key = candidate_key(cand)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            # 未映射概念(cerebellum exterior / ventral diencephalon 等池细分)
            # 仍生成 candidate(region_id NULL,名称保留),是 A1 与 canonical
            # 未覆盖的交集 —— 真正的补缺目标,不能丢弃
            if not cand["region_unmapped"] and is_conflict(cand, existing_canonicals):
                conflict.append({"region_pair": (x, y), "reason": "canonical_exists",
                                 "connection_type": cand["connection_type"],
                                 "missing_side": a1["missing_side"]})
                continue
            if is_duplicate(cand, existing_candidates):
                duplicate.append({"region_pair": (x, y), "reason": "already_generated",
                                  "connection_type": cand["connection_type"],
                                  "missing_side": a1["missing_side"]})
                continue
            generated.append(cand)

    counts = {
        "a1_total": len(a1_items),
        "generated": len(generated),
        "skipped": len(skipped),
        "conflict": len(conflict),
        "duplicate": len(duplicate),
    }
    skip_reasons: dict[str, int] = {}
    for r in skipped:
        skip_reasons[r["reason"]] = skip_reasons.get(r["reason"], 0) + 1
    return {
        "generated": generated,
        "skipped": skipped,
        "conflict": conflict,
        "duplicate": duplicate,
        "counts": counts,
        "skip_reasons": dict(sorted(skip_reasons.items())),
    }
