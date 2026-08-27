"""Macro Connection Human Review + Promotion V1 — 核心逻辑(纯函数)。

治理闭环:Validation → Human Review → Active Canonical → Final Canonical (Final KG)。

* Review Queue:从 validation REVIEW_REQUIRED 结果构建待审队列,
  展示 canonical / source-target region / type / evidence / provenance / failed rules。
* Promotion 资格(守卫):仅
    - validation PASS,或
    - REVIEW_REQUIRED 且最新 review action == approved
  可进入 Final;rejected / needs_more_evidence / 未审 / FAIL 一律不可。
* Final 行:复制 canonical 事实(保留 evidence_summary / provenance_json /
  evidence_reference),附带 validation_run_id / review_record_id 溯源。

不执行:CN2 inference、外部数据导入。不删除 mirror / cluster。
"""

from __future__ import annotations

from typing import Any

VALID_ACTIONS = frozenset({"approved", "rejected", "needs_more_evidence"})
PROMOTION_KEY = "macro_connection_promotion_v1"

# ---- Review Queue ----

def build_review_queue(
    review_items: list[dict],
    region_names: dict[str, dict],
) -> list[dict]:
    """构造 Review Queue 展示项(每项含决策前的完整上下文)。

    review_items 元素(canonical 视角):
      canonical_connection_id / connection_code / source_region_id / target_region_id /
      connection_type / directionality_policy / evidence_count / evidence_summary /
      provenance_json / confidence_statistics / failed_rules / validation_run_id /
      validation_status

    返回按 validation_status + failed 规则排序的队列(人工逐个处理)。
    """
    queue = []
    for item in review_items:
        src = region_names.get(item.get("source_region_id")) or {}
        tgt = region_names.get(item.get("target_region_id")) or {}
        queue.append({
            "canonical_connection_id": item["canonical_connection_id"],
            "connection_code": item.get("connection_code"),
            "source_region": {
                "region_id": item.get("source_region_id"),
                "name_en": src.get("canonical_name_en") or src.get("name_en"),
                "name_cn": src.get("canonical_name_cn") or src.get("name_cn"),
            },
            "target_region": {
                "region_id": item.get("target_region_id"),
                "name_en": tgt.get("canonical_name_en") or tgt.get("name_en"),
                "name_cn": tgt.get("canonical_name_cn") or tgt.get("name_cn"),
            },
            "connection_type": item.get("connection_type"),
            "directionality_policy": item.get("directionality_policy"),
            "evidence_count": item.get("evidence_count"),
            "evidence_summary": item.get("evidence_summary") or {},
            "provenance_json": item.get("provenance_json") or {},
            "confidence_statistics": item.get("confidence_statistics") or {},
            "validation_status": item.get("validation_status"),
            "validation_run_id": item.get("validation_run_id"),
            "failed_rules": item.get("failed_rules") or [],
        })
    # 无 failed_rules 的排前面(结构类问题更明确),再按证据数升序
    queue.sort(key=lambda q: (0 if q["failed_rules"] else 1, q["evidence_count"] or 0))
    return queue


def latest_review_decision(
    reviews: list[dict],
    canonical_id: str,
) -> dict | None:
    """取该 canonical 最新一条 review(按 created_at 降序)。"""
    rows = [r for r in reviews if r["canonical_connection_id"] == canonical_id]
    if not rows:
        return None
    return max(rows, key=lambda r: r["created_at"])


def check_promotion_eligibility(
    validation_status: str,
    review: dict | None,
) -> tuple[bool, str]:
    """Promotion 资格守卫(纯判定)。

    返回 (eligible, reason):
    * PASS                                     → (True,  "validation_pass")
    * REVIEW_REQUIRED + approved               → (True,  "review_approved")
    * REVIEW_REQUIRED + rejected               → (False, "review_rejected")
    * REVIEW_REQUIRED + needs_more_evidence    → (False, "needs_more_evidence")
    * REVIEW_REQUIRED + 未审                   → (False, "review_pending")
    * FAIL                                     → (False, "validation_fail")
    """
    if validation_status == "PASS":
        return True, "validation_pass"
    if validation_status == "FAIL":
        return False, "validation_fail"
    if validation_status is None:
        # 未验证 connection 禁止进入 Final(即使有 review 记录)
        return False, "validation_missing"
    # REVIEW_REQUIRED
    if review is None:
        return False, "review_pending"
    action = review.get("action")
    if action == "approved":
        return True, "review_approved"
    if action == "rejected":
        return False, "review_rejected"
    return False, "needs_more_evidence"


def final_connection_from_canonical(
    canonical: dict,
    validation_run_id: str | None,
    review_record_id: str | None,
) -> dict:
    """构造 Final Canonical Connection 行(保留 provenance / evidence / reference)。"""
    return {
        "canonical_connection_id": canonical["id"],
        "connection_code": canonical.get("connection_code"),
        "source_region_id": canonical.get("source_region_id"),
        "target_region_id": canonical.get("target_region_id"),
        "connection_type": canonical.get("connection_type"),
        "directionality_policy": canonical.get("directionality_policy"),
        "species": canonical.get("species"),
        "granularity_level": canonical.get("granularity_level"),
        "confidence": canonical.get("confidence"),
        "evidence_summary": canonical.get("evidence_summary") or {},
        "provenance_json": canonical.get("provenance_json") or {},
        "assertion_type": canonical.get("assertion_type") or "reported_fact",
        "source_type": canonical.get("source_type") or "unknown",
        "generation_method": canonical.get("generation_method") or "unknown",
        "evidence_reference": canonical.get("evidence_reference") or [],
        "validation_run_id": validation_run_id,
        "review_record_id": review_record_id,
        "final_status": "active",
    }


def summarize_promotion(records: list[dict]) -> dict:
    """Promotion 结果统计:{total, promoted, skipped_duplicate, skipped_ineligible,
    rejected, by_reason:{...}}。"""
    counts = {"promoted": 0, "skipped_duplicate": 0, "skipped_ineligible": 0, "rejected": 0}
    reasons: dict[str, int] = {}
    for r in records:
        status = r["status"]
        counts[status] = counts.get(status, 0) + 1
        reason = (r.get("promotion_reason") or r.get("reason")
                  or r.get("message") or "unknown")
        reasons[reason] = reasons.get(reason, 0) + 1
    return {
        "total": len(records),
        "promoted": counts["promoted"],
        "skipped_duplicate": counts["skipped_duplicate"],
        "skipped_ineligible": counts["skipped_ineligible"],
        "rejected": counts["rejected"],
        "by_reason": dict(sorted(reasons.items(), key=lambda kv: -kv[1])),
    }


def summarize_final(final_rows: list[dict], total_connections: int) -> dict:
    """Final Connection 统计:{active, deprecated, coverage, evidence_coverage,...}。"""
    active = sum(1 for f in final_rows if f["final_status"] == "active")

    def _has_evidence(f: dict[str, Any]) -> bool:
        es = f.get("evidence_summary") or {}
        return (es.get("evidence_count") or 0) > 0 or bool(f.get("evidence_reference"))

    with_evidence = sum(1 for f in final_rows if _has_evidence(f))
    return {
        "active": active,
        "deprecated": sum(1 for f in final_rows if f["final_status"] == "deprecated"),
        "superseded": sum(1 for f in final_rows if f["final_status"] == "superseded"),
        "total_canonical": total_connections,
        "coverage_pct": round(active / total_connections * 100, 2) if total_connections else 0.0,
        "evidence_coverage": round(with_evidence / max(active, 1) * 100, 2),
        "with_evidence": with_evidence,
        "granularity_distribution": _count_by(final_rows, "granularity_level"),
        "type_distribution": _count_by(final_rows, "connection_type"),
    }


def _count_by(rows: list[dict], key: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for r in rows:
        out[r.get(key) or "unknown"] = out.get(r.get(key) or "unknown", 0) + 1
    return dict(sorted(out.items()))
