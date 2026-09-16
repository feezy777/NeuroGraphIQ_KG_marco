"""Discovery View continuation — a second pass over the SAME question.

What continuation is
--------------------
A continuation is a NEW, INDEPENDENT run for the same (seed, discovery_view)
pair, whose prompt additionally carries what earlier passes of that same view
already found, so the model is asked to look for what was MISSED rather than to
re-answer the same question.

It is deliberately none of these:
  * not a retry      — the earlier run is untouched and still terminal
  * not a resume     — there is no partial state to resume; round 1 completed
  * not an overwrite — each round keeps its own run and its own candidates

Round 1 -> Run A1, Round 2 -> Run A2: two rows, two candidate sets. Nothing is
merged, deleted or canonicalized here; the rounds are additive by construction,
and resolving whether two rounds found "the same" circuit is a LATER, read-only
judgement that this module does not make.

Where the exclusion context comes from
--------------------------------------
The caller supplies ONE thing: the id of a previous run of this view. The
already-discovered circuits are then read from the AUTHORITATIVE candidate rows
of EVERY completed run of this seed+view — never from the request. A client
cannot submit its own exclusion list, and a later round cannot be built from
only its immediate predecessor: a Round 4 must see rounds 1-3, because a
circuit first found in round 1 and not repeated since is still discovered.

Naming, and why normalization is prompt-only
--------------------------------------------
Two rounds regularly describe one circuit with two spellings. For the PROMPT it
is wasteful to list near-identical names, so names are compared after a
deliberately blunt normalization (trim, collapse whitespace, casefold). That
comparison never touches storage: the candidate rows keep the exact name the
model produced, and no row is merged or deleted because a second row normalized
to the same string.

This module only READS. Creating the run, calling the model and persisting the
candidates all belong to the execution and persistence services.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

#: The route a continuation may continue. A LITERATURE_DISCOVERY run is not a
#: discovery view and can never be a continuation source.
LLM_DISCOVERY = "LLM_DISCOVERY"

#: The only run status that can be continued: a run still QUEUED or RUNNING has
#: not produced a result to build on, and a FAILED run produced nothing at all.
CONTINUABLE_STATUS = "COMPLETED"

_WHITESPACE = re.compile(r"\s+")


def normalize_circuit_name(name: str) -> str:
    """The blunt equality key used for prompt context. Never for storage.

    Trim, collapse internal whitespace, casefold. Deliberately NO stemming and
    NO synonym handling: "Trisynaptic loop (…)" and "Hippocampal trisynaptic
    circuit" stay distinct here, and deciding whether they are one circuit is a
    scientific judgement this module does not make.
    """
    return _WHITESPACE.sub(" ", (name or "").strip()).casefold()


# ===========================================================================
# typed errors — the router maps these; none carries SQL or DB internals
# ===========================================================================
class ContinuationError(Exception):
    """Base for a continuation request that cannot be honoured."""

    code = "CONTINUATION_REJECTED"


class ContinuationRunNotFound(ContinuationError):
    code = "CONTINUATION_RUN_NOT_FOUND"

    def __init__(self, run_id: str) -> None:
        super().__init__(f"continuation run '{run_id}' not found")
        self.run_id = run_id


class ContinuationRunWrongSeed(ContinuationError):
    """Cross-seed continuation: the previous run answered a DIFFERENT region."""

    code = "CONTINUATION_RUN_WRONG_SEED"

    def __init__(self, message: str) -> None:
        super().__init__(message)


class ContinuationRunWrongView(ContinuationError):
    """The previous run asked a different question. Its circuits are not this
    view's circuits, so continuing from it would poison the exclusion context."""

    code = "CONTINUATION_RUN_WRONG_VIEW"

    def __init__(self, message: str) -> None:
        super().__init__(message)


class ContinuationRunNotCompleted(ContinuationError):
    code = "CONTINUATION_RUN_NOT_COMPLETED"

    def __init__(self, message: str) -> None:
        super().__init__(message)


@dataclass(frozen=True)
class AlreadyDiscovered:
    """What earlier passes of this view found, plus the round this run is.

    ``names`` is the PROMPT context: deduplicated by normalized name, in a
    stable order. ``raw_count`` is how many circuit ROWS exist — the honest
    number, since deduplication for the prompt must not be mistaken for a
    finding about the data.
    """

    names: tuple[str, ...]
    raw_count: int
    rounds_present: tuple[int, ...]
    next_round: int


# ===========================================================================
# SQL (module constants — never built from caller input)
# ===========================================================================
#: Resolves the run being continued AND the seed it belongs to, so "not found",
#: "wrong seed" and "wrong route" are answered without a second round trip.
_SCOPE_SQL = text(
    """
    SELECT r.run_id, r.status, r.discovery_type, r.query_strategy_version,
           r.provenance_json ->> 'continuation_round' AS continuation_round,
           e.entity_id AS seed_entity_id
    FROM knowledge_discovery_runs r
    JOIN brain_regions b ON b.entity_pk = r.seed_region_pk
    JOIN kg_entities e ON e.entity_pk = b.entity_pk
    WHERE r.run_id = :run_id
    """
)

#: Every completed run of this seed on THIS view — the whole chain, not just the
#: run named by the caller. Ordered by creation so the prompt context is stable.
_CHAIN_SQL = text(
    """
    SELECT r.run_id,
           r.provenance_json ->> 'continuation_round' AS continuation_round
    FROM knowledge_discovery_runs r
    JOIN brain_regions b ON b.entity_pk = r.seed_region_pk
    JOIN kg_entities e ON e.entity_pk = b.entity_pk
    WHERE e.entity_id = :entity_id
      AND r.discovery_type = :discovery_type
      AND r.status = :status
      AND r.query_strategy_version = :strategy
    ORDER BY r.created_at, r.run_id
    """
)

#: The circuits those runs produced. Names only: the prompt needs a compact
#: exclusion list, not the raw payloads.
_CIRCUIT_SQL = text(
    """
    SELECT dc.name, dc.local_id
    FROM discovery_candidates dc
    WHERE dc.candidate_type = 'circuit'
      AND dc.discovery_run_pk IN (
        SELECT r.run_pk
        FROM knowledge_discovery_runs r
        JOIN brain_regions b ON b.entity_pk = r.seed_region_pk
        JOIN kg_entities e ON e.entity_pk = b.entity_pk
        WHERE e.entity_id = :entity_id
          AND r.discovery_type = :discovery_type
          AND r.status = :status
          AND r.query_strategy_version = :strategy
      )
    ORDER BY dc.candidate_id
    """
)


async def _scope(session: AsyncSession, run_id: str):
    return (await session.execute(_SCOPE_SQL, {"run_id": run_id})).mappings().one_or_none()


async def validate_continuation(
    session: AsyncSession,
    *,
    from_run_id: str,
    entity_id: str,
    discovery_view: str,
    strategy: str,
) -> None:
    """Refuse a continuation whose source run cannot honestly be continued.

    Every rule exists to protect the SAME thing: the exclusion context must be
    circuits this view genuinely found for THIS region. A source from another
    seed, another route or another view would put the wrong names in front of
    the model, and a source that never completed would contribute none.
    """
    scope = await _scope(session, from_run_id)
    if scope is None:
        raise ContinuationRunNotFound(from_run_id)
    if scope["seed_entity_id"] != entity_id:
        raise ContinuationRunWrongSeed(
            f"continuation run '{from_run_id}' belongs to BrainRegion "
            f"'{scope['seed_entity_id']}', not '{entity_id}'"
        )
    if scope["discovery_type"] != LLM_DISCOVERY:
        raise ContinuationRunWrongView(
            f"continuation run '{from_run_id}' is {scope['discovery_type']}, "
            f"not {LLM_DISCOVERY}"
        )
    if scope["status"] != CONTINUABLE_STATUS:
        raise ContinuationRunNotCompleted(
            f"continuation run '{from_run_id}' is {scope['status']}; only a "
            f"{CONTINUABLE_STATUS} run has a result to continue from"
        )
    if scope["query_strategy_version"] != strategy:
        raise ContinuationRunWrongView(
            f"continuation run '{from_run_id}' ran strategy "
            f"'{scope['query_strategy_version']}', not '{strategy}'"
        )


async def collect_already_discovered(
    session: AsyncSession,
    *,
    entity_id: str,
    strategy: str,
) -> AlreadyDiscovered:
    """Accumulate every circuit this seed+view has found across ALL its rounds.

    Read after validation, and read from the candidate rows themselves: the
    caller's request carries no list, so the context cannot be steered. Raw
    rows are counted as they are; only the PROMPT list is deduplicated.
    """
    chain = (
        await session.execute(
            _CHAIN_SQL,
            {
                "entity_id": entity_id,
                "discovery_type": LLM_DISCOVERY,
                "status": CONTINUABLE_STATUS,
                "strategy": strategy,
            },
        )
    ).mappings().all()

    rounds = sorted(
        {
            int(row["continuation_round"])
            for row in chain
            if row["continuation_round"] is not None
        }
    )
    # A completed run with no recorded round IS round 1 — the first pass of a
    # view. Deriving it here is what keeps the number server-owned.
    highest = max(rounds) if rounds else 1

    rows = (
        await session.execute(
            _CIRCUIT_SQL,
            {
                "entity_id": entity_id,
                "discovery_type": LLM_DISCOVERY,
                "status": CONTINUABLE_STATUS,
                "strategy": strategy,
            },
        )
    ).mappings().all()

    seen: set[str] = set()
    names: list[str] = []
    for row in rows:
        name = (row["name"] or "").strip()
        if not name:
            continue
        key = normalize_circuit_name(name)
        if key in seen:
            continue
        seen.add(key)
        names.append(name)

    return AlreadyDiscovered(
        names=tuple(names),
        raw_count=len(rows),
        rounds_present=tuple(rounds) if rounds else (1,),
        next_round=highest + 1,
    )
