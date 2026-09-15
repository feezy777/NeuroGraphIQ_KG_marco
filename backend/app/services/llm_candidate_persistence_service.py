"""LLM Discovery P0-1 — persist the candidates one LLM Discovery run proposed.

    validated LlmDiscoveryResponse (already parsed)
      -> projection (type / local_id / name / payload / confidence)
      -> ONE idempotent multi-row INSERT into discovery_candidates
      -> bounded persistence summary

Why the projection exists: ``payload_json`` keeps the typed candidate verbatim,
but a row whose only columns were run + jsonb would be unlistable. ``name`` and
``confidence`` are lifted out for that reason alone — never recomputed.

Frozen boundaries (phase brief §1 / §10 / §12):

  * A candidate is a PROPOSAL. This module writes to the Knowledge Production
    staging table and nothing else: no kg_entities row, no canonical
    connection / circuit / function, no evidence, no knowledge_assertion.
  * It does NOT call a provider, build a prompt, parse raw model text,
    canonicalize a name, judge scientific truth, or touch literature. The Phase
    3A parser is the only structural authority; re-validating here would give
    the contract two opinions.
  * Run-local references stay inside the payload. They point at sibling
    proposals that may never be accepted, so a canonical FK would assert a
    resolution that has not happened.
  * ``source_hints`` produce NO rows, and no table is created for them.
  * No secrets, no raw response text, no reasoning content, no prompt.

Atomicity (§12): every candidate of ONE response is written by ONE INSERT, so
PostgreSQL's statement atomicity is the guarantee — no window exists in which a
circuit persisted and the function that followed it did not.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Iterator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import TextClause

from app.schemas.llm_discovery import (
    CircuitCandidate,
    ConnectionCandidate,
    FunctionCandidate,
    LlmDiscoveryResponse,
    RegionCandidate,
)

logger = logging.getLogger(__name__)

#: The candidate_type vocabulary. Mirrors ck_dc_candidate_type (gate7b_016) and
#: the four arrays of LlmDiscoveryResponse. Deliberately no 'literature' or
#: 'evidence' type: those are not discovery candidates.
TYPE_REGION = "region"
TYPE_CONNECTION = "connection"
TYPE_CIRCUIT = "circuit"
TYPE_FUNCTION = "function"

CANDIDATE_TYPES: tuple[str, ...] = (
    TYPE_REGION,
    TYPE_CONNECTION,
    TYPE_CIRCUIT,
    TYPE_FUNCTION,
)

#: The only status this phase writes. Mirrors ck_dc_status.
STATUS_PROPOSED = "proposed"

_INSERT_SQL_HEAD = (
    "INSERT INTO discovery_candidates"
    " (discovery_run_pk, seed_region_pk, candidate_type, local_id, name,"
    "  payload_json, confidence, status)"
    " VALUES "
)
#: Idempotency lives in the database, not in a read-then-write pre-check: two
#: concurrent writers replaying the same response would both pass a pre-check and
#: both insert. The unique index is the final authority, and this clause makes
#: the loser of that race a no-op instead of an error.
_INSERT_SQL_TAIL = (
    " ON CONFLICT (discovery_run_pk, candidate_type, local_id) DO NOTHING"
    " RETURNING candidate_type"
)


@dataclass(frozen=True)
class CandidatePersistenceSummary:
    """What one persistence call did. Bounded: counts only, never payloads.

    ``by_type`` is a per-type breakdown of ``total`` — created AND
    already-present alike, since both are rows the caller just caused to exist.
    It is not a second measure of ``created``, and no internal key appears here.
    """

    created: int
    existing: int
    total: int
    by_type: dict[str, int]


def candidate_name(candidate_type: str, candidate: Any) -> str:
    """The human-readable list label for one typed candidate (§8).

    Projected from fields the candidate ALREADY carries. Nothing is resolved: a
    connection label shows its run-local refs rather than looking up what they
    might canonically be — at this point they are proposals with no referent.
    """
    if candidate_type in (TYPE_REGION, TYPE_CIRCUIT):
        return candidate.name
    if candidate_type == TYPE_FUNCTION:
        return candidate.label
    if candidate_type == TYPE_CONNECTION:
        return (
            f"{candidate.source_ref} -> {candidate.target_ref}"
            f" [{candidate.connection_type}]"
        )
    # Fail closed: an unknown type is a vocabulary drift, and inventing a label
    # for it would hide that behind a plausible-looking row.
    raise ValueError(f"unknown candidate_type: {candidate_type!r}")


def _typed_candidates(
    data: LlmDiscoveryResponse,
) -> Iterator[tuple[str, RegionCandidate | ConnectionCandidate | CircuitCandidate | FunctionCandidate]]:
    """Every candidate in the response, in a deterministic order.

    ``source_hints`` and ``warnings`` are deliberately absent: neither is one.
    """
    for candidate in data.regions:
        yield TYPE_REGION, candidate
    for candidate in data.connections:
        yield TYPE_CONNECTION, candidate
    for candidate in data.circuits:
        yield TYPE_CIRCUIT, candidate
    for candidate in data.functions:
        yield TYPE_FUNCTION, candidate


def _insert_statement(count: int) -> TextClause:
    """One statement for the whole response, one param set per candidate.

    Built from module constants only. The VALUES slots are indexed bind
    parameters, so no value the model produced is ever interpolated into SQL.
    """
    placeholders = ", ".join(
        f"(:run_pk, :seed_pk, :type_{i}, :local_id_{i}, :name_{i},"
        f" CAST(:payload_{i} AS jsonb), :confidence_{i}, :status)"
        for i in range(count)
    )
    return text(_INSERT_SQL_HEAD + placeholders + _INSERT_SQL_TAIL)


async def persist_discovery_candidates(
    session: AsyncSession,
    *,
    discovery_run_pk: int,
    seed_region_pk: int,
    data: LlmDiscoveryResponse,
) -> CandidatePersistenceSummary:
    """Persist every candidate of ONE validated response. Idempotent per run.

    ``discovery_run_pk`` and ``seed_region_pk`` are INTERNAL keys and are never
    returned. The caller derives both from the same run row, so the seed
    recorded on a candidate cannot disagree with the run that produced it.

    Re-persisting the same response for the same run reports ``existing``; the
    same local label in a DIFFERENT run is a new row, because those are two
    independent proposals. A zero-candidate response is not an error and issues
    no SQL at all.

    On failure the session is rolled back and the exception propagates, leaving
    the caller a usable session so it can still finish the run.
    """
    rows = [
        (
            candidate_type,
            candidate.local_id,
            candidate_name(candidate_type, candidate),
            # The typed candidate, verbatim. mode="json" so the payload is data
            # rather than a Python repr that happens to look like JSON.
            candidate.model_dump(mode="json"),
            candidate.confidence,
        )
        for candidate_type, candidate in _typed_candidates(data)
    ]

    by_type: dict[str, int] = {t: 0 for t in CANDIDATE_TYPES}
    for candidate_type, *_ in rows:
        by_type[candidate_type] += 1

    if not rows:
        return CandidatePersistenceSummary(created=0, existing=0, total=0, by_type=by_type)

    params: dict[str, Any] = {
        "run_pk": discovery_run_pk,
        "seed_pk": seed_region_pk,
        "status": STATUS_PROPOSED,
    }
    for index, (candidate_type, local_id, name, payload, confidence) in enumerate(rows):
        params[f"type_{index}"] = candidate_type
        params[f"local_id_{index}"] = local_id
        params[f"name_{index}"] = name
        params[f"payload_{index}"] = json.dumps(payload, ensure_ascii=False)
        params[f"confidence_{index}"] = confidence

    try:
        result = await session.execute(_insert_statement(len(rows)), params)
        # RETURNING yields only the rows the INSERT actually created; a row the
        # ON CONFLICT clause skipped is absent, which is how "existing" is
        # counted without a second query.
        created = len(result.scalars().all())
        await session.commit()
    except Exception:
        await session.rollback()
        logger.exception(
            "[llm-candidates] persistence failed run_pk=%s candidates=%s",
            discovery_run_pk,
            len(rows),
        )
        raise

    summary = CandidatePersistenceSummary(
        created=created, existing=len(rows) - created, total=len(rows), by_type=by_type
    )
    logger.info(
        "[llm-candidates] persisted run_pk=%s created=%s existing=%s by_type=%s",
        discovery_run_pk,
        summary.created,
        summary.existing,
        summary.by_type,
    )
    return summary
