"""Centralized validation state machine — single source of truth for status values and transitions."""

from __future__ import annotations

from typing import Any


class RuleValidationStatus:
    NOT_STARTED = "not_started"
    QUEUED = "queued"
    RUNNING = "running"
    PASSED = "passed"
    WARNING = "warning"
    BLOCKED = "blocked"
    FAILED = "failed"
    CANCELLED = "cancelled"


class BlockerAnalysisStatus:
    NOT_STARTED = "not_started"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    PARSE_FAILED = "parse_failed"
    PROVIDER_FAILED = "provider_failed"
    CANCELLED = "cancelled"


class CorrectionStatus:
    NONE = "none"
    PROPOSED = "proposed"
    DETERMINISTIC_REJECTED = "deterministic_rejected"
    PENDING_HUMAN = "pending_human"
    APPROVED = "approved"
    REJECTED = "rejected"
    APPLIED = "applied_to_effective_view"


class RevalidationStatus:
    NOT_STARTED = "not_started"
    QUEUED = "queued"
    RUNNING = "running"
    PASSED = "passed"
    WARNING = "warning"
    BLOCKED = "blocked"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ReviewerStatus:
    NOT_STARTED = "not_started"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    PARSE_FAILED = "parse_failed"
    PROVIDER_FAILED = "provider_failed"
    CANCELLED = "cancelled"


class AdjudicationStatus:
    NOT_STARTED = "not_started"
    READY_FOR_HUMAN_REVIEW = "ready_for_human_review"
    REVIEWER_DISAGREEMENT = "reviewer_disagreement"
    LOW_EVIDENCE = "low_evidence"
    RULE_REJECTED = "rule_rejected"
    MODEL_REJECTED = "model_rejected"
    REVIEWER_FAILED = "reviewer_failed"
    TOPOLOGY_ONLY = "topology_only"
    DUPLICATE_CANDIDATE = "duplicate_candidate"


class HumanReviewStatus:
    NOT_STARTED = "not_started"
    PENDING = "pending"
    APPROVED = "approved"
    MODIFIED_APPROVED = "modified_approved"
    RETAINED = "retained"
    REJECTED = "rejected"
    RETURNED = "returned"
    TOPOLOGY_ONLY = "topology_only"
    MERGED_DUPLICATE = "merged_duplicate"


class PromotionStatus:
    NOT_STARTED = "not_started"
    PREVIEW_READY = "preview_ready"
    BLOCKED = "blocked"
    DRY_RUN_PASSED = "dry_run_passed"
    DRY_RUN_FAILED = "dry_run_failed"
    PROMOTED = "promoted"
    ROLLED_BACK = "rolled_back"
    FAILED = "failed"


# ── Stage-specific rule severity ──────────────────────────────────────────
RULE_SEVERITY_POLICY: dict[str, dict[str, Any]] = {
    "REGION_IDENTITY": {"validation": "hard_fail", "blocks_dual_review": True, "blocks_promotion": True},
    "EDGE_EXISTENCE": {"validation": "hard_fail", "blocks_dual_review": True, "blocks_promotion": True},
    "DIRECTION_CORRECT": {"validation": "hard_fail", "blocks_dual_review": True, "blocks_promotion": True},
    "STEP_CONTINUITY": {"validation": "hard_fail", "blocks_dual_review": True, "blocks_promotion": True},
    "CLOSED_LOOP": {"validation": "hard_fail", "blocks_dual_review": True, "blocks_promotion": True, "note": "hard fail only when closed_loop=true and path is not closed"},
    "GRANULARITY_HOMOGENEITY": {"validation": "hard_fail", "blocks_dual_review": True, "blocks_promotion": True},
    "PROVENANCE_COMPLETE": {"validation": "warning", "blocks_dual_review": False, "blocks_promotion": True, "note": "promotion blocked if provenance still missing"},
    "TOPOLOGY_TYPE_VALID": {"validation": "warning", "blocks_dual_review": False, "blocks_promotion": False},
    "CANONICAL_KEY_DUPLICATE": {"validation": "warning", "blocks_dual_review": False, "blocks_promotion": True, "note": "promotion blocked until duplicate resolved"},
    "FIELD_COMPLETENESS": {"validation": "warning", "blocks_dual_review": False, "blocks_promotion": False},
    "LABEL_QUALITY": {"validation": "warning", "blocks_dual_review": False, "blocks_promotion": False},
    "PREDICATE_VALIDITY": {"validation": "warning", "blocks_dual_review": False, "blocks_promotion": True, "note": "hard fail for unknown predicate, warning for alias"},
}


def get_rule_severity(rule_code: str) -> dict[str, Any]:
    """Return severity policy for a given rule code."""
    return RULE_SEVERITY_POLICY.get(rule_code, {"validation": "warning", "blocks_dual_review": False, "blocks_promotion": False})


def can_enter_dual_review(rule_results: list[dict]) -> bool:
    """Check if a circuit's rule results allow dual review."""
    for r in rule_results:
        policy = get_rule_severity(r.get("rule_code", ""))
        if policy["blocks_dual_review"] and r.get("status") in ("blocked", "failed"):
            return False
    return True


def can_enter_promotion(rule_results: list[dict]) -> bool:
    """Check if a circuit's rule results allow promotion.

    Hard-fail rules always block promotion when in blocked/failed status.
    Warning rules block promotion only when their note explicitly says so
    (e.g. PROVENANCE_COMPLETE, CANONICAL_KEY_DUPLICATE).
    """
    for r in rule_results:
        policy = get_rule_severity(r.get("rule_code", ""))
        if not policy["blocks_promotion"]:
            continue
        if r.get("status") not in ("blocked", "failed", "warning"):
            continue
        # Hard-fail rules always block promotion on bad status
        if policy.get("validation") == "hard_fail":
            return False
        # Warning rules only block when note explicitly says so
        note = policy.get("note", "")
        if "promotion blocked" in note:
            return False
    return True
