"""Circuit semantic novelty assessor.

Answers ONE question after a Discovery run completes: of the circuits it found,
how many are genuinely new relative to everything earlier runs of the same
(seed, discovery_view) already found?

Read-only, and structurally so: every statement this module issues is a SELECT.
It writes no row, changes no status, merges nothing and deletes nothing. A
candidate the assessor calls an ALIAS stays exactly where it is, with exactly
the payload the model produced — the class is a diagnostic annotation over
stored proposals, not a decision about them.

Scope of the comparison
-----------------------
Same seed, same discovery view, earlier runs only, completed runs only:

  * same seed          — circuits found for Left Hippocampus say nothing about
                         CA3; comparing across seeds would manufacture novelty
                         and destroy it in equal measure.
  * same view          — each view asks a different question, so its circuits
                         are not each other's prior art.
  * earlier only       — "prior" means what was already known when THIS run
                         ran. A later run cannot make an earlier one less novel.
  * completed only     — a FAILED run persisted nothing, so it contributes
                         nothing. It also must not: a failed attempt is not
                         evidence that a concept was already found.
  * never itself       — the target run is excluded from its own prior pool.

Judgement
---------
One DeepSeek call, model fixed by ``app.llm_model_policy`` (``deepseek-flash``).
Discovery confidence is NOT sent to the model and NOT used as novelty evidence;
the surest way to keep a number out of a judgement is not to supply it.

What the assessor will not do
-----------------------------
It will not accept a partial answer. A response that misses a target circuit, or
returns one twice, is rejected rather than padded — inventing a class for a
circuit the model never judged would put a number into ``semantic_new_count``
that no model ever assigned, and that count is intended to become a stopping
signal. A structurally incomplete answer FAILS.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm_discovery_views import view_of_strategy_identifier
from app.llm_model_policy import DEEPSEEK_PROVIDER, effective_deepseek_model
from app.prompts.llm_circuit_novelty_prompt import build_novelty_prompt
from app.schemas.circuit_novelty import (
    NOVELTY_CLASSES_REQUIRING_A_MATCH,
    CircuitNoveltyAssessment,
    CircuitNoveltyVerdict,
    ModelNoveltyResponse,
    semantic_new_count_of,
)
from app.services.llm_providers.factory import get_llm_provider
from app.services.settings_service import get_deepseek_runtime_config

#: The only route assessable. A LITERATURE_DISCOVERY run has no circuits.
LLM_DISCOVERY = "LLM_DISCOVERY"

#: Only a completed run has circuits to assess.
ASSESSABLE_STATUS = "COMPLETED"

CANDIDATE_TYPE_CIRCUIT = "circuit"


# ===========================================================================
# typed errors — the caller maps these; none carries SQL or DB internals
# ===========================================================================
class NoveltyAssessmentError(Exception):
    """Base for a novelty assessment that cannot be produced."""

    code = "NOVELTY_ASSESSMENT_ERROR"


class NoveltyRunNotFound(NoveltyAssessmentError):
    code = "NOVELTY_RUN_NOT_FOUND"

    def __init__(self, run_id: str) -> None:
        super().__init__(f"discovery run '{run_id}' not found")
        self.run_id = run_id


class NoveltyRunNotAssessable(NoveltyAssessmentError):
    """Wrong route, or a run that never completed."""

    def __init__(self, message: str, code: str) -> None:
        super().__init__(message)
        self.code = code


class NoveltyProviderError(NoveltyAssessmentError):
    code = "NOVELTY_PROVIDER_ERROR"

    def __init__(self, message: str) -> None:
        super().__init__(message)


class NoveltyAssessmentIncomplete(NoveltyAssessmentError):
    """The model did not return exactly one verdict per target circuit."""

    code = "NOVELTY_ASSESSMENT_INCOMPLETE"

    def __init__(self, message: str) -> None:
        super().__init__(message)


class NoveltyAssessmentInvalid(NoveltyAssessmentError):
    """A verdict contradicts itself — typically a match claim that names
    nothing, or a NEW that claims to match."""

    code = "NOVELTY_ASSESSMENT_INVALID"

    def __init__(self, message: str) -> None:
        super().__init__(message)


# ===========================================================================
# one circuit, as the assessor needs it
# ===========================================================================
@dataclass(frozen=True)
class AssessableCircuit:
    """A circuit candidate with enough context to judge meaning.

    Confidence is deliberately absent: it is not novelty evidence, so there is
    nowhere here to read it from even by accident.
    """

    candidate_id: str
    run_id: str
    local_id: str
    name: str
    description: str | None
    rationale: str | None
    topology_hint: str | None
    region_refs: tuple[str, ...]
    connection_refs: tuple[str, ...]
    function_refs: tuple[str, ...]


@dataclass(frozen=True)
class PriorCircuitPool:
    circuits: tuple[AssessableCircuit, ...]
    run_count: int


# ===========================================================================
# SQL (module constants — never built from caller input). All SELECT.
# ===========================================================================
_RUN_SQL = text(
    """
    SELECT r.run_id, r.status, r.discovery_type, r.query_strategy_version,
           r.created_at, e.entity_id AS seed_entity_id
    FROM knowledge_discovery_runs r
    JOIN brain_regions b ON b.entity_pk = r.seed_region_pk
    JOIN kg_entities e ON e.entity_pk = b.entity_pk
    WHERE r.run_id = :run_id
    """
)

#: Circuits of earlier completed runs of the same seed and view.
#:
#: The row comparison `(created_at, run_id) < (target_created_at, target_run_id)`
#: is what makes "earlier" precise and stable: created_at alone could tie, and
#: run_id alone is not chronological.
_PRIOR_SQL = text(
    """
    SELECT dc.candidate_id, dc.local_id, dc.name, r.run_id,
           dc.payload_json ->> 'description'   AS description,
           dc.payload_json ->> 'rationale'     AS rationale,
           dc.payload_json ->> 'topology_hint' AS topology_hint,
           dc.payload_json -> 'region_refs'     AS region_refs,
           dc.payload_json -> 'connection_refs' AS connection_refs,
           dc.payload_json -> 'function_refs'   AS function_refs
    FROM discovery_candidates dc
    JOIN knowledge_discovery_runs r ON r.run_pk = dc.discovery_run_pk
    JOIN brain_regions b ON b.entity_pk = r.seed_region_pk
    JOIN kg_entities e ON e.entity_pk = b.entity_pk
    WHERE e.entity_id = :entity_id
      AND r.discovery_type = :discovery_type
      AND r.status = :status
      AND r.query_strategy_version = :strategy
      AND dc.candidate_type = :candidate_type
      AND (r.created_at, r.run_id) < (:target_created_at, :target_run_id)
    ORDER BY r.created_at, r.run_id, dc.candidate_id
    """
)

#: Circuits of the run being assessed. A run is never its own prior art.
_TARGET_SQL = text(
    """
    SELECT dc.candidate_id, dc.local_id, dc.name, r.run_id,
           dc.payload_json ->> 'description'   AS description,
           dc.payload_json ->> 'rationale'     AS rationale,
           dc.payload_json ->> 'topology_hint' AS topology_hint,
           dc.payload_json -> 'region_refs'     AS region_refs,
           dc.payload_json -> 'connection_refs' AS connection_refs,
           dc.payload_json -> 'function_refs'   AS function_refs
    FROM discovery_candidates dc
    JOIN knowledge_discovery_runs r ON r.run_pk = dc.discovery_run_pk
    WHERE r.run_id = :target_run_id
      AND dc.candidate_type = :candidate_type
    ORDER BY dc.candidate_id
    """
)


def _as_tuple(value: Any) -> tuple[str, ...]:
    """A jsonb array from the driver, as a tuple of str. Anything else is empty
    — a malformed ref list is not a reason to fail an assessment."""
    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(str(v) for v in value)


def _circuit_from_row(row: Any) -> AssessableCircuit:
    return AssessableCircuit(
        candidate_id=row["candidate_id"],
        run_id=str(row["run_id"]),
        local_id=row["local_id"],
        name=row["name"],
        description=row["description"],
        rationale=row["rationale"],
        topology_hint=row["topology_hint"],
        region_refs=_as_tuple(row["region_refs"]),
        connection_refs=_as_tuple(row["connection_refs"]),
        function_refs=_as_tuple(row["function_refs"]),
    )


# ===========================================================================
# collection (read-only)
# ===========================================================================
@dataclass(frozen=True)
class _RunScope:
    run_id: str
    seed_entity_id: str
    strategy: str
    discovery_view: str | None
    created_at: datetime


async def resolve_assessable_run(session: AsyncSession, *, run_id: str) -> _RunScope:
    """The run being assessed, or a typed refusal.

    A run that never completed has no result to assess; a run from another route
    has no circuits at all. Both are refused here rather than producing a
    meaningless zero.
    """
    row = (
        await session.execute(_RUN_SQL, {"run_id": run_id})
    ).mappings().one_or_none()
    if row is None:
        raise NoveltyRunNotFound(run_id)
    if row["discovery_type"] != LLM_DISCOVERY:
        raise NoveltyRunNotAssessable(
            f"run '{run_id}' is {row['discovery_type']}, not {LLM_DISCOVERY}",
            "NOVELTY_RUN_NOT_ASSESSABLE",
        )
    if row["status"] != ASSESSABLE_STATUS:
        raise NoveltyRunNotAssessable(
            f"run '{run_id}' is {row['status']}; only a {ASSESSABLE_STATUS} run "
            f"has circuits to assess",
            "NOVELTY_RUN_NOT_ASSESSABLE",
        )
    strategy = row["query_strategy_version"]
    return _RunScope(
        run_id=str(row["run_id"]),
        seed_entity_id=row["seed_entity_id"],
        strategy=strategy,
        discovery_view=view_of_strategy_identifier(strategy),
        created_at=row["created_at"],
    )


async def collect_prior_circuits(
    session: AsyncSession, *, scope: _RunScope
) -> PriorCircuitPool:
    """Every circuit the earlier completed runs of this seed+view produced."""
    rows = (
        await session.execute(
            _PRIOR_SQL,
            {
                "entity_id": scope.seed_entity_id,
                "discovery_type": LLM_DISCOVERY,
                "status": ASSESSABLE_STATUS,
                "strategy": scope.strategy,
                "candidate_type": CANDIDATE_TYPE_CIRCUIT,
                "target_created_at": scope.created_at,
                "target_run_id": scope.run_id,
            },
        )
    ).mappings().all()
    circuits = tuple(_circuit_from_row(r) for r in rows)
    return PriorCircuitPool(
        circuits=circuits,
        run_count=len({c.run_id for c in circuits}),
    )


async def collect_target_circuits(
    session: AsyncSession, *, scope: _RunScope
) -> tuple[AssessableCircuit, ...]:
    """The circuits of the run being assessed."""
    rows = (
        await session.execute(
            _TARGET_SQL,
            {
                "target_run_id": scope.run_id,
                "candidate_type": CANDIDATE_TYPE_CIRCUIT,
            },
        )
    ).mappings().all()
    return tuple(_circuit_from_row(r) for r in rows)


# ===========================================================================
# parse + validate the model's verdicts
# ===========================================================================
def parse_novelty_assessment(
    raw: Any,
    *,
    scope: _RunScope,
    target: tuple[AssessableCircuit, ...],
    prior: PriorCircuitPool,
) -> CircuitNoveltyAssessment:
    """Turn one provider reply into a validated assessment.

    The model supplies a class and (sometimes) a match. Everything else — the
    circuit's name, its local id, the matched candidate's run — is read back
    from the stored rows, so a verdict cannot smuggle in a circuit or a run that
    does not exist.
    """
    payload = raw
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except (TypeError, ValueError) as exc:
            raise NoveltyAssessmentInvalid(
                f"the model reply is not valid JSON: {exc}"
            ) from None

    # A bare array of verdicts is accepted as the same answer as the requested
    # wrapper. The model sometimes drops the envelope, and which of the two
    # shapes carries the verdicts says nothing about what the verdicts mean —
    # refusing a list for not being an object would be enforcing a style rule
    # against a reply that answered the question.
    if isinstance(payload, list):
        payload = {"verdicts": payload}

    try:
        response = ModelNoveltyResponse.model_validate(payload)
    except Exception as exc:  # pydantic ValidationError
        raise NoveltyAssessmentInvalid(
            f"the model reply does not match the verdict contract: {exc}"
        ) from None

    if not response.verdicts:
        # Distinct from a PARTIAL answer: nothing was judged at all, which is a
        # shape problem, not a coverage one. Saying "0 of 23 assessed" here
        # would send a reader looking for the missing 23.
        raise NoveltyAssessmentInvalid(
            f"the model reply carried no verdicts (expected one for each of "
            f"{len(target)} circuits); its top-level keys were "
            f"{sorted(payload) if isinstance(payload, dict) else type(payload).__name__}"
        )

    by_target = {c.candidate_id: c for c in target}
    prior_by_id = {c.candidate_id: c for c in prior.circuits}

    seen: dict[str, Any] = {}
    for verdict in response.verdicts:
        cid = verdict.candidate_id
        if cid not in by_target:
            raise NoveltyAssessmentInvalid(
                f"verdict names candidate '{cid}', which is not a circuit of "
                f"run '{scope.run_id}'"
            )
        if cid in seen:
            raise NoveltyAssessmentIncomplete(
                f"candidate '{cid}' was assessed more than once"
            )
        seen[cid] = verdict
        _check_match(verdict, prior_by_id)

    missing = [c.candidate_id for c in target if c.candidate_id not in seen]
    if missing:
        raise NoveltyAssessmentIncomplete(
            f"{len(missing)} of {len(target)} circuits were not assessed "
            f"(e.g. {', '.join(missing[:3])}); a partial answer is refused "
            f"rather than padded with an invented class"
        )

    verdicts: list[CircuitNoveltyVerdict] = []
    for circuit in target:
        raw_verdict = seen[circuit.candidate_id]
        matched_id = raw_verdict.matched_prior_candidate_id
        matched = prior_by_id.get(matched_id) if matched_id else None
        verdicts.append(
            CircuitNoveltyVerdict(
                candidate_id=circuit.candidate_id,
                local_id=circuit.local_id,
                name=circuit.name,
                novelty_class=raw_verdict.novelty_class,
                matched_prior_candidate_id=matched_id,
                # From the stored prior row, never from the model.
                matched_prior_run_id=matched.run_id if matched else None,
                short_reason=raw_verdict.short_reason,
            )
        )

    return CircuitNoveltyAssessment(
        target_run_id=scope.run_id,
        seed_entity_id=scope.seed_entity_id,
        discovery_view=scope.discovery_view,
        strategy_identifier=scope.strategy,
        raw_circuit_count=len(verdicts),
        prior_circuit_count=len(prior.circuits),
        prior_run_count=prior.run_count,
        NEW_count=sum(1 for v in verdicts if v.novelty_class == "NEW"),
        ALIAS_count=sum(1 for v in verdicts if v.novelty_class == "ALIAS"),
        REFORMULATION_count=sum(
            1 for v in verdicts if v.novelty_class == "REFORMULATION"
        ),
        BORDERLINE_count=sum(
            1 for v in verdicts if v.novelty_class == "BORDERLINE"
        ),
        semantic_new_count=semantic_new_count_of(verdicts),
        verdicts=verdicts,
    )


def _check_match(verdict: Any, prior_by_id: dict[str, AssessableCircuit]) -> None:
    """A claim about the past must point at something that exists."""
    klass = verdict.novelty_class
    matched = verdict.matched_prior_candidate_id
    if klass in NOVELTY_CLASSES_REQUIRING_A_MATCH:
        if not matched:
            raise NoveltyAssessmentInvalid(
                f"candidate '{verdict.candidate_id}' is {klass} but names no "
                f"earlier circuit to match"
            )
        if matched not in prior_by_id:
            raise NoveltyAssessmentInvalid(
                f"candidate '{verdict.candidate_id}' matches '{matched}', which "
                f"is not in the prior pool"
            )
    elif klass == "NEW" and matched:
        raise NoveltyAssessmentInvalid(
            f"candidate '{verdict.candidate_id}' is NEW but claims to match "
            f"'{matched}'"
        )
    elif matched and matched not in prior_by_id:
        raise NoveltyAssessmentInvalid(
            f"candidate '{verdict.candidate_id}' matches '{matched}', which is "
            f"not in the prior pool"
        )


# ===========================================================================
# the assessment
# ===========================================================================
async def assess_circuit_novelty(
    session: AsyncSession, *, run_id: str
) -> CircuitNoveltyAssessment:
    """Assess one completed discovery run. Reads; writes nothing.

    One provider call. No retry, no loop, no follow-up round — deciding what to
    do with the number is a later feature with its own design.
    """
    scope = await resolve_assessable_run(session, run_id=run_id)
    prior = await collect_prior_circuits(session, scope=scope)
    target = await collect_target_circuits(session, scope=scope)

    # A run with no circuits still has a well-defined answer — nothing to
    # assess, zero novelty — and must not cost a provider call to say so.
    if not target:
        return CircuitNoveltyAssessment(
            target_run_id=scope.run_id,
            seed_entity_id=scope.seed_entity_id,
            discovery_view=scope.discovery_view,
            strategy_identifier=scope.strategy,
            raw_circuit_count=0,
            prior_circuit_count=len(prior.circuits),
            prior_run_count=prior.run_count,
            NEW_count=0,
            ALIAS_count=0,
            REFORMULATION_count=0,
            BORDERLINE_count=0,
            semantic_new_count=0,
            verdicts=[],
        )

    prompt = build_novelty_prompt(
        target=target,
        prior=prior.circuits,
        seed_entity_id=scope.seed_entity_id,
        discovery_view=scope.discovery_view,
    )
    config = get_deepseek_runtime_config()

    try:
        provider = get_llm_provider(DEEPSEEK_PROVIDER)
        response = await provider.complete_json(
            model=effective_deepseek_model(None),
            system_prompt=prompt["system_prompt"],
            user_prompt=prompt["user_prompt"],
            temperature=config.temperature,
            max_tokens=config.max_tokens,
            timeout_seconds=config.timeout_seconds,
        )
    except Exception as exc:  # noqa: BLE001 — re-raised as a typed error
        raise NoveltyProviderError(
            f"the novelty comparison could not be completed: {exc}"
        ) from None

    if not response.transport_ok:
        raise NoveltyProviderError(
            f"the novelty comparison failed in transport: "
            f"{response.error_message or 'no detail reported'}"
        )
    if not (response.raw_text or "").strip():
        raise NoveltyProviderError("the model returned no content to parse")

    # The provider normalizes the model name, so a disagreement here means the
    # frozen policy was bypassed somewhere.
    if response.model != effective_deepseek_model(None):
        raise NoveltyProviderError(
            f"model policy violation: expected {effective_deepseek_model(None)}, "
            f"the provider reported {response.model}"
        )

    return parse_novelty_assessment(
        # `raw_text`, NOT `parsed_json`. The provider's JSON extraction takes the
        # first object it finds; for this reply — a {"verdicts": [...]} document
        # — that is the FIRST VERDICT rather than the document, so trusting it
        # turned a complete 23-verdict answer into "23 of 23 not assessed".
        # The discovery parser is handed `raw_text` for the same reason, and the
        # empty-text guard above already rules out the one case a fallback
        # would have covered, so there is no fallback to get wrong.
        response.raw_text,
        scope=scope,
        target=target,
        prior=prior,
    )


__all__ = [
    "AssessableCircuit",
    "PriorCircuitPool",
    "NoveltyAssessmentError",
    "NoveltyAssessmentIncomplete",
    "NoveltyAssessmentInvalid",
    "NoveltyProviderError",
    "NoveltyRunNotAssessable",
    "NoveltyRunNotFound",
    "assess_circuit_novelty",
    "collect_prior_circuits",
    "collect_target_circuits",
    "parse_novelty_assessment",
    "resolve_assessable_run",
]
