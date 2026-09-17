"""High-recall multi-view discovery orchestration — request and read contract.

What the orchestrator does
--------------------------
Runs the four Discovery Views in a frozen order, automatically:

    A NAMED_CLASSIC_CIRCUITS → B LOCAL_INTRINSIC_CIRCUITS
    → C AFFERENT_CIRCUITS → D EFFERENT_CIRCUITS → COMPLETED

keeping each View alive while it still produces SEMANTIC NOVELTY, and moving on
once two consecutive successful rounds produce none.

What it deliberately is not
---------------------------
Not Canonicalization. It merges nothing across Views, resolves no identity,
promotes nothing and changes no candidate's status. A, B, C and D are
independent search strategies and their circuits stay independent Raw
Candidates — a circuit found under two Views is expected, not a defect.

Confidence plays no part in any decision here. A 0.20-confidence circuit that
the novelty assessor calls NEW or BORDERLINE keeps a View alive exactly as a
0.95 one would.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.llm_discovery_views import DISCOVERY_VIEWS

#: Our own constructed output: strict, because none of it is model-authored.
_STRICT = ConfigDict(extra="forbid")

#: The View order is the SERVER's. A client cannot reorder it, skip a View or
#: add one — that would change what "saturated" means without changing anything
#: visible in the request. It is the frozen vocabulary itself, in its own order,
#: so the two can never disagree.
VIEW_ORDER: tuple[str, ...] = DISCOVERY_VIEWS

#: Orchestration-level lifecycle. There is deliberately NO global SATURATED:
#: saturation is a property of ONE View, and with four Views a global flag would
#: be false the moment the loop moved on.
OrchestrationStatus = Literal[
    "READY", "RUNNING", "PAUSED_BY_BUDGET", "BLOCKED", "COMPLETED"
]
ORCHESTRATION_STATUSES: tuple[str, ...] = (
    "READY", "RUNNING", "PAUSED_BY_BUDGET", "BLOCKED", "COMPLETED"
)

#: Per-View lifecycle.
#:
#: No per-View PAUSED, deliberately: a budget pause stops the ORCHESTRATION
#: mid-View, and that View is still RUNNING. Recording the same fact in two
#: places is how two records start disagreeing.
ViewStatus = Literal[
    "PENDING", "RUNNING", "SATURATED_BY_ZERO_NOVELTY", "BLOCKED", "COMPLETE"
]
VIEW_STATUSES: tuple[str, ...] = (
    "PENDING", "RUNNING", "SATURATED_BY_ZERO_NOVELTY", "BLOCKED", "COMPLETE"
)

#: A View is finished being searched when this many CONSECUTIVE successful
#: rounds produced no semantic novelty. The first zero is not enough: the
#: assessor is stochastic, so one zero is a measurement and two are a pattern.
ZERO_STREAK_TO_SATURATE = 2

#: Safety envelope for ONE execution's NEW Discovery provider calls. This is a
#: cost guard, NOT a scientific parameter: exhausting it pauses, and a pause is
#: never saturation.
DEFAULT_DISCOVERY_CALL_BUDGET = 10
MIN_DISCOVERY_CALL_BUDGET = 1
MAX_DISCOVERY_CALL_BUDGET = 20


class OrchestrationStartRequest(BaseModel):
    """The whole client-side surface of an orchestration.

    Deliberately absent: View order, model, prompt, novelty thresholds,
    confidence thresholds, zero-streak rule. Every one of those is a server-owned
    policy, and a request field for any of them would let a caller change what
    the system means without changing anything it can see.
    """

    model_config = _STRICT

    max_new_discovery_calls: int = Field(
        default=DEFAULT_DISCOVERY_CALL_BUDGET,
        ge=MIN_DISCOVERY_CALL_BUDGET,
        le=MAX_DISCOVERY_CALL_BUDGET,
        description=(
            "Maximum NEW Discovery provider calls for this execution. A safety "
            "budget, not a saturation signal: exhausting it pauses the "
            "orchestration, which stays resumable."
        ),
    )


class OrchestrationViewStateRead(BaseModel):
    """One View's control state."""

    model_config = _STRICT

    discovery_view: str
    position: int
    status: ViewStatus
    zero_streak: int
    latest_successful_run_id: str | None = None
    latest_novelty_assessment_id: str | None = None
    successful_round_count: int
    failed_attempt_count: int
    semantic_new_count: int | None = None
    stop_reason: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None

    @model_validator(mode="after")
    def _saturation_means_two_zeros(self) -> "OrchestrationViewStateRead":
        # The same rule the table's CHECK holds, restated where a reader will
        # meet it: a View claiming saturation with a streak below two would mean
        # the loop stopped for a reason nobody recorded.
        if self.status == "SATURATED_BY_ZERO_NOVELTY" and self.zero_streak < 2:
            raise ValueError(
                f"view '{self.discovery_view}' is SATURATED_BY_ZERO_NOVELTY with "
                f"zero_streak {self.zero_streak}; saturation requires "
                f"{ZERO_STREAK_TO_SATURATE} consecutive zero-novelty rounds"
            )
        return self


class OrchestrationRead(BaseModel):
    """One orchestration, its Views in order, and its cost ledger."""

    model_config = _STRICT

    orchestration_id: str
    seed_entity_id: str
    strategy_family: str
    strategy_version: str
    status: OrchestrationStatus
    current_view: str | None = None
    zero_streak: int

    discovery_call_budget: int
    discovery_calls_used: int
    novelty_calls_used: int

    stop_reason: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None

    views: list[OrchestrationViewStateRead] = Field(default_factory=list)

    @model_validator(mode="after")
    def _budget_is_within_the_frozen_envelope(self) -> "OrchestrationRead":
        if not (
            MIN_DISCOVERY_CALL_BUDGET
            <= self.discovery_call_budget
            <= MAX_DISCOVERY_CALL_BUDGET
        ):
            raise ValueError(
                f"discovery_call_budget {self.discovery_call_budget} is outside "
                f"{MIN_DISCOVERY_CALL_BUDGET}..{MAX_DISCOVERY_CALL_BUDGET}"
            )
        return self

    @property
    def provider_calls_total(self) -> int:
        """Discovery + novelty. The honest total, never just the paid part."""
        return self.discovery_calls_used + self.novelty_calls_used
