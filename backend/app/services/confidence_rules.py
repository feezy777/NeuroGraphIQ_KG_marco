"""Deterministic confidence adjustment rules for paper evidence (Phase B).

Rules are versioned (formula_version). The reviewer-confirmed confidence is
authoritative; DeepSeek confidence is never applied directly.
"""

from __future__ import annotations

from dataclasses import dataclass

FORMULA_VERSION = "paper_evidence_v1"
SUPPORT_CAP = 0.85
PARTIAL_CAP = 0.75


@dataclass
class AdjustmentResult:
    final_confidence: float | None
    adjustment_status: str  # applied | pending | none
    formula_version: str
    apply: bool
    reason: str


def compute_adjustment(
    *,
    direction: str,
    current_confidence: float | None,
    reviewer_confidence: float,
) -> AdjustmentResult:
    current = current_confidence if current_confidence is not None else 0.0
    reviewer = max(0.0, min(1.0, float(reviewer_confidence)))
    if direction == "supports":
        if reviewer >= current:
            final = min(SUPPORT_CAP, reviewer)
            return AdjustmentResult(
                final_confidence=final,
                adjustment_status="applied",
                formula_version=FORMULA_VERSION,
                apply=True,
                reason=f"supports: min({SUPPORT_CAP}, max(current, reviewer))",
            )
        # weak / indirect evidence (reviewer below current) must not raise confidence
        return AdjustmentResult(
            final_confidence=current,
            adjustment_status="no_change_weak_evidence",
            formula_version=FORMULA_VERSION,
            apply=False,
            reason="weak evidence: reviewer confidence below current; confidence unchanged",
        )
    if direction == "partial":
        if reviewer >= current:
            final = min(PARTIAL_CAP, reviewer)
            return AdjustmentResult(
                final_confidence=final,
                adjustment_status="applied",
                formula_version=FORMULA_VERSION,
                apply=True,
                reason=f"partial: min({PARTIAL_CAP}, max(current, reviewer))",
            )
        return AdjustmentResult(
            final_confidence=current,
            adjustment_status="no_change_weak_evidence",
            formula_version=FORMULA_VERSION,
            apply=False,
            reason="weak evidence: reviewer confidence below current; confidence unchanged",
        )
    if direction in ("contradicts", "mixed"):
        return AdjustmentResult(
            final_confidence=current,
            adjustment_status="pending",
            formula_version=FORMULA_VERSION,
            apply=False,
            reason=f"{direction}: no automatic change; pending human review",
        )
    raise ValueError("not_found evidence cannot be stored as paper evidence")
