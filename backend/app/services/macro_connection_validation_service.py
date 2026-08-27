"""Macro Connection Validation V1 — 核心逻辑(纯函数)。

对 2500 条 Macro Human Canonical Connection 建立第一版验证流程:
* 结构规则:region 存在 / src!=tgt / type 合法 / direction 合法 / species / granularity
* Evidence 规则:lineage 存在 / evidence_count 正确 / provenance 非空 / confidence 存在
* 质量规则:duplicate key 不存在 / canonical 可追溯 mirror

状态映射:
* PASS              全部规则通过
* FAIL              任何结构规则失败(数据不可用,硬失败)
* REVIEW_REQUIRED   结构规则全通过,但 evidence/质量规则有失败(需人工审查)

validator_version = "v1"。只写 validation 表,不修改 canonical_connections
状态,不执行 promotion / Final KG / CN2。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

VALIDATOR_KEY = "macro_connection_validation_v1"
VALIDATOR_VERSION = "v1"

# canonical_connections 词表(与表 CHECK 约束/服务常量对齐)
VALID_CONNECTION_TYPES = frozenset({
    "structural", "functional", "projection", "association", "uncertain",
})
VALID_DIRECTIONS = frozenset({"unspecified", "directed", "bidirectional"})
# canonical 层粒度编码:clinical 即 Macro 池的 canonical 层(granularity=Macro)
VALID_GRANULARITIES = frozenset({"clinical", "macro"})

PASS = "PASS"
FAIL = "FAIL"
REVIEW_REQUIRED = "REVIEW_REQUIRED"

# 规则分类(用于状态映射与报告分组)
STRUCTURAL = "structural"
EVIDENCE = "evidence"
QUALITY = "quality"


@dataclass
class RuleSpec:
    code: str
    category: str
    fail_level: str            # FAIL=硬失败(数据不可用);REVIEW_REQUIRED=需审查
    check: Callable[[dict, dict], str | None]  # 返回 None=通过,否则返回失败消息


# ---- 规则检查函数(canonical: dict, ctx: dict) ----

def _missing_region(canonical: dict, ctx: dict, side: str) -> str | None:
    region_id = canonical.get(f"{side}_region_id")
    if region_id not in ctx["valid_region_ids"]:
        return f"{side} region {region_id} does not exist in canonical_brain_regions"
    return None


def _self_loop(canonical: dict, ctx: dict) -> str | None:
    if canonical["source_region_id"] == canonical["target_region_id"]:
        return "source == target (self-loop)"
    return None


def _type_valid(canonical: dict, ctx: dict) -> str | None:
    if canonical["connection_type"] not in VALID_CONNECTION_TYPES:
        return f"connection_type '{canonical['connection_type']}' not in {sorted(VALID_CONNECTION_TYPES)}"
    return None


def _direction_valid(canonical: dict, ctx: dict) -> str | None:
    if canonical["directionality_policy"] not in VALID_DIRECTIONS:
        return (f"directionality_policy '{canonical['directionality_policy']}' "
                f"not in {sorted(VALID_DIRECTIONS)}")
    return None


def _species_human(canonical: dict, ctx: dict) -> str | None:
    if canonical["species"] != "human":
        return f"species '{canonical['species']}' != human"
    return None


def _granularity_macro(canonical: dict, ctx: dict) -> str | None:
    if canonical["granularity_level"] not in VALID_GRANULARITIES:
        return (f"granularity_level '{canonical['granularity_level']}' not in "
                f"{sorted(VALID_GRANULARITIES)} (clinical = Macro pool canonical layer)")
    return None


def _lineage_exists(canonical: dict, ctx: dict) -> str | None:
    lineage = ctx["lineage_by_canonical"].get(canonical["id"]) or []
    if not lineage:
        return "no canonical_connection_lineage rows"
    return None


def _evidence_count_correct(canonical: dict, ctx: dict) -> str | None:
    lineage = ctx["lineage_by_canonical"].get(canonical["id"]) or []
    expect = sum(l["cluster_size"] for l in lineage)
    actual = canonical["evidence_count"]
    if actual != expect:
        return f"evidence_count {actual} != lineage cluster_size sum {expect}"
    return None


def _provenance_nonempty(canonical: dict, ctx: dict) -> str | None:
    pj = canonical.get("provenance_json")
    if not pj:
        return "provenance_json is empty"
    return None


def _confidence_exists(canonical: dict, ctx: dict) -> str | None:
    cs = canonical.get("confidence_statistics") or {}
    if int(cs.get("count") or 0) <= 0:
        return "confidence_statistics.count == 0"
    return None


def _no_duplicate_key(canonical: dict, ctx: dict) -> str | None:
    key = (canonical["source_region_id"], canonical["target_region_id"],
           canonical["connection_type"])
    if key in ctx["duplicate_keys"]:
        return f"duplicate canonical key (src, tgt, type) among active rows"
    return None


def _traceable_to_mirror(canonical: dict, ctx: dict) -> str | None:
    lineage = ctx["lineage_by_canonical"].get(canonical["id"]) or []
    missing = [mid for l in lineage for mid in l["mirror_connection_ids"]
               if mid not in ctx["valid_mirror_ids"]]
    if missing:
        return f"{len(missing)} mirror_connection_ids unresolved"
    return None


# ---- 规则注册表(声明式,顺序即报告顺序) ----

RULE_SPECS: list[RuleSpec] = [
    RuleSpec("src_region_exists", STRUCTURAL, FAIL, _missing_region),
    RuleSpec("tgt_region_exists", STRUCTURAL, FAIL, _missing_region),
    RuleSpec("src_ne_tgt", STRUCTURAL, FAIL, _self_loop),
    RuleSpec("connection_type_valid", STRUCTURAL, FAIL, _type_valid),
    RuleSpec("direction_valid", STRUCTURAL, FAIL, _direction_valid),
    RuleSpec("species_human", STRUCTURAL, FAIL, _species_human),
    RuleSpec("granularity_macro", STRUCTURAL, FAIL, _granularity_macro),
    RuleSpec("lineage_exists", EVIDENCE, REVIEW_REQUIRED, _lineage_exists),
    RuleSpec("evidence_count_correct", EVIDENCE, REVIEW_REQUIRED, _evidence_count_correct),
    RuleSpec("provenance_json_nonempty", EVIDENCE, REVIEW_REQUIRED, _provenance_nonempty),
    RuleSpec("confidence_exists", EVIDENCE, REVIEW_REQUIRED, _confidence_exists),
    RuleSpec("no_duplicate_key", QUALITY, FAIL, _no_duplicate_key),
    RuleSpec("traceable_to_mirror", QUALITY, REVIEW_REQUIRED, _traceable_to_mirror),
]


def validate_connection(canonical: dict, ctx: dict) -> tuple[str, list[dict]]:
    """单 canonical 验证 → (validation_status, failed_rules)。

    ctx: {valid_region_ids, lineage_by_canonical, duplicate_keys, valid_mirror_ids}
    """
    failed: list[dict] = []
    hard_failed = False
    for spec in RULE_SPECS:
        fn = spec.check
        args = [canonical, ctx]
        # src_region_exists / tgt_region_exists 共用 _missing_region,带 side 参数
        if spec.code == "src_region_exists":
            args = [canonical, ctx, "source"]
        elif spec.code == "tgt_region_exists":
            args = [canonical, ctx, "target"]
        msg = fn(*args)
        if msg is not None:
            failed.append({"rule_code": spec.code, "category": spec.category, "message": msg})
            if spec.fail_level == FAIL:
                hard_failed = True
    if hard_failed:
        return FAIL, failed
    if failed:
        return REVIEW_REQUIRED, failed
    return PASS, []


def build_validation_context(
    valid_region_ids: set[str],
    lineage_by_canonical: dict[str, list[dict]],
    duplicate_keys: set[tuple],
    valid_mirror_ids: set[str],
) -> dict:
    """预计算的全局上下文(全局规则只算一次)。"""
    return {
        "valid_region_ids": valid_region_ids,
        "lineage_by_canonical": lineage_by_canonical,
        "duplicate_keys": duplicate_keys,
        "valid_mirror_ids": valid_mirror_ids,
    }


def summarize_results(results: list[dict]) -> dict:
    """结果统计:{total, pass, fail, review_required, pass_pct, failed_rule_counts}。"""
    total = len(results)
    status_map = {PASS: "pass", FAIL: "fail", REVIEW_REQUIRED: "review_required"}
    counts = {"pass": 0, "fail": 0, "review_required": 0}
    rule_fails: dict[str, int] = {}
    for r in results:
        counts[status_map[r["validation_status"]]] += 1
        for fr in r["failed_rules"]:
            rule_fails[fr["rule_code"]] = rule_fails.get(fr["rule_code"], 0) + 1
    return {
        "total": total,
        "pass": counts["pass"],
        "fail": counts["fail"],
        "review_required": counts["review_required"],
        "pass_pct": round(counts["pass"] / total * 100, 2) if total else 0.0,
        "failed_rule_counts": dict(sorted(rule_fails.items(), key=lambda kv: -kv[1])),
    }
