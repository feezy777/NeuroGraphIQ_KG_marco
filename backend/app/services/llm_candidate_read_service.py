"""Phase P0-2A — read-only access to persisted LLM Discovery candidates.

The read side of what Phase P0-1 made writable:

    Discovery Run (LLM_DISCOVERY)
      -> discovery_candidates        (region / connection / circuit / function)

Tables read (SELECT only):

    discovery_candidates        the persisted proposals
    knowledge_discovery_runs    run identity, route and chronology
    brain_regions               seed resolution
    kg_entities                 public identity (entity_id)

This module is STRICTLY READ-ONLY: SELECT only, never a write, never a commit.
Writing belongs to ``llm_candidate_persistence_service`` (P0-1), which is the
only author of a candidate row; this layer only reads back what that one stored.

Boundaries:
  * A candidate is a PROPOSAL. Nothing here canonicalizes it, resolves its
    run-local references, or joins it to a canonical region / connection /
    circuit / function. ``payload`` is returned exactly as persisted.
  * LLM_DISCOVERY only. A LITERATURE_DISCOVERY run is deliberately NOT readable
    as an LLM run: the two discovery channels are independent, and quietly
    returning literature rows here would erase that boundary.
  * No legacy ``candidate_*`` / ``mirror_*`` table is read, and
    ``provenance_json`` is never treated as candidate storage.
  * No LLM call, no provider client, no literature search: this layer reads what
    an execution already produced and never performs one.

The read DTOs and the domain errors live HERE rather than in the shared
Knowledge Production schema module: this phase must stay independently
reviewable, and a read layer that cannot express "wrong discovery type" would
have to report it as "empty", which is a different fact.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Mapping

from pydantic import BaseModel, ConfigDict
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# Imported, never restated. The candidate-type vocabulary belongs to the writer
# and the DB CHECK; and `resolve_hemisphere` is the CONTRACT's one definition of
# how laterality resolves, so a copy here could disagree with the schema that
# validated the payload it is being applied to.
from app.schemas.llm_discovery import resolve_hemisphere
from app.services.llm_candidate_persistence_service import TYPE_REGION

#: The route this read service serves. Not a general discovery-type vocabulary:
#: a candidate read is an LLM Discovery read.
LLM_DISCOVERY = "LLM_DISCOVERY"


# ===========================================================================
# domain errors — the caller maps these onto its own HTTP contract (§7)
# ===========================================================================
# Named distinctly from ``knowledge_discovery_run_lifecycle_service``'s errors
# on purpose: "this run does not exist" and "this run is not an LLM run" are
# read-side facts here, and reusing the write-side exception would invite a
# caller to catch a failure it does not actually handle.
class DiscoveryCandidateReadError(Exception):
    """Base for a candidate read failure. Never carries SQL or DB internals."""


class DiscoveryCandidateRunNotFound(DiscoveryCandidateReadError):
    """No Discovery Run with that public id — including a malformed one."""

    def __init__(self, run_id: str) -> None:
        super().__init__(f"Discovery Run '{run_id}' not found")
        self.run_id = run_id


class DiscoveryCandidateSeedNotFound(DiscoveryCandidateReadError):
    """No BrainRegion with that public entity_id."""

    def __init__(self, entity_id: str) -> None:
        super().__init__(f"BrainRegion '{entity_id}' not found")
        self.entity_id = entity_id


class DiscoveryCandidateRunNotLlm(DiscoveryCandidateReadError):
    """The run exists but is not an LLM_DISCOVERY run (§4).

    Explicit, not empty: a LITERATURE_DISCOVERY run has no LLM candidates to
    show, and reporting "no candidates" would state something false about it.
    """

    def __init__(self, run_id: str, discovery_type: str) -> None:
        super().__init__(
            f"Discovery Run '{run_id}' is {discovery_type}, not {LLM_DISCOVERY}"
        )
        self.run_id = run_id
        self.discovery_type = discovery_type


# ===========================================================================
# read DTO — public fields only (§5)
# ===========================================================================
class DiscoveryCandidateReadItem(BaseModel):
    """One persisted candidate, as a reader may see it.

    Internal keys are deliberately absent: ``candidate_pk`` /
    ``discovery_run_pk`` / ``seed_region_pk`` are storage details, and the
    public API is candidate_id / run_id / entity_id based.

    ``candidate_type`` and ``status`` stay ``str`` rather than a Literal: their
    vocabulary is owned by the database CHECK and the P0-1 writer, and a third
    copy here would be a second authority that could drift from both.
    """

    model_config = ConfigDict(extra="forbid")

    candidate_id: str
    run_id: str
    seed_entity_id: str
    candidate_type: str
    local_id: str
    name: str
    #: The persisted parsed typed candidate, verbatim. Never reconstructed from
    #: the normalized columns and never canonicalized. For a region this carries
    #: `hemisphere_context` exactly as the model stated it — the RAW claim, kept
    #: readable so a reader can tell "stated LEFT" from "resolved to LEFT".
    payload: dict[str, Any]
    #: The region's laterality as an ABSOLUTE side, or None when it does not
    #: apply. Two things it deliberately is NOT:
    #:
    #:   * not a second copy of `hemisphere_context`. A relative value
    #:     (IPSILATERAL_TO_SEED) is a real answer, and collapsing it into the
    #:     side it happens to resolve to today would lose the relationship the
    #:     model actually claimed — and silently change meaning if the seed's
    #:     own side is ever corrected.
    #:   * not present on a connection, circuit or function. Their laterality
    #:     FOLLOWS from the regions they reference; a connection between two
    #:     UNSPECIFIED endpoints is not a left-left connection, and defaulting
    #:     one is how an unknown becomes a false claim.
    #:
    #: Derived on read, never stored: it is a pure function of the seed's side
    #: and the stated context, so persisting it would create a second copy that
    #: can disagree with the first.
    resolved_hemisphere: str | None = None
    confidence: float | None = None
    status: str
    created_at: datetime
    updated_at: datetime


# ===========================================================================
# SQL (module constants — never built from caller input)
# ===========================================================================
# Resolves the run AND its route AND its seed's public id in one statement, so a
# run-scoped read can answer "absent" / "wrong route" / "which seed" without a
# second round trip.
_RUN_SCOPE_SQL = text(
    """
    SELECT r.run_pk, r.discovery_type, e.entity_id AS seed_entity_id,
           b.hemisphere AS seed_hemisphere
    FROM knowledge_discovery_runs r
    JOIN brain_regions b ON b.entity_pk = r.seed_region_pk
    JOIN kg_entities e ON e.entity_pk = b.entity_pk
    WHERE r.run_id = :run_id
    """
)

_SEED_SCOPE_SQL = text(
    """
    SELECT b.entity_pk, e.entity_id, b.hemisphere AS seed_hemisphere
    FROM brain_regions b
    JOIN kg_entities e ON e.entity_pk = b.entity_pk
    WHERE e.entity_id = :entity_id
    """
)

#: One shared projection. ``run_id`` is selected so a seed-scoped row can name
#: the run it belongs to without a per-row lookup.
_CANDIDATE_COLUMNS = """
    c.candidate_id,
    c.candidate_type,
    c.local_id,
    c.name,
    c.payload_json,
    c.confidence,
    c.status,
    c.created_at,
    c.updated_at,
    r.run_id
"""

#: No discovery_type filter here: the route was already verified by
#: _RUN_SCOPE_SQL, and re-filtering would turn an explicit rejection into a
#: silent empty page.
_FOR_RUN_SQL = text(
    "SELECT " + _CANDIDATE_COLUMNS
    + " FROM discovery_candidates c"
    " JOIN knowledge_discovery_runs r ON r.run_pk = c.discovery_run_pk"
    " WHERE c.discovery_run_pk = :run_pk"
    " ORDER BY c.candidate_type, c.local_id"
)

#: Scoped by the CANDIDATE's own seed_region_pk, which P0-1 guarantees equals
#: its run's seed. The discovery_type filter is what keeps the two discovery
#: channels independent: a literature run under the same seed contributes
#: nothing here. run_id breaks created_at ties so the order is deterministic.
_FOR_SEED_SQL = text(
    "SELECT " + _CANDIDATE_COLUMNS
    + " FROM discovery_candidates c"
    " JOIN knowledge_discovery_runs r ON r.run_pk = c.discovery_run_pk"
    " WHERE c.seed_region_pk = :seed_pk"
    "   AND r.discovery_type = :discovery_type"
    " ORDER BY r.created_at DESC, r.run_id, c.candidate_type, c.local_id"
)


def _resolved_hemisphere(
    candidate_type: str, payload: Mapping[str, Any], seed_hemisphere: str | None
) -> str | None:
    """The candidate's absolute laterality, or None where it does not apply.

    Only a REGION states a laterality, so only a region resolves: the other
    three types return None rather than a resolved side, because none of them
    ever stated one. A payload with no `hemisphere_context` — every LEGACY row,
    and any row whose model answered UNSPECIFIED — resolves to UNSPECIFIED
    unless the seed's own side makes a relative value decidable.
    """
    if candidate_type != TYPE_REGION:
        return None
    # The legacy free-text `hemisphere` key is deliberately NOT read here: its
    # wording ("left", "LEFT", "bilateral") is what the closed vocabulary
    # replaced, and reinterpreting it at read time would be a silent backfill of
    # data this contract cannot vouch for. It stays visible in `payload` for
    # anyone who wants to read what was actually written. `resolve_hemisphere`
    # is total, so an absent or malformed context resolves to UNSPECIFIED rather
    # than defaulting to a side.
    return resolve_hemisphere(seed_hemisphere, payload.get("hemisphere_context"))


def _row_to_item(
    row: Mapping[str, Any],
    seed_entity_id: str,
    seed_hemisphere: str | None = None,
) -> DiscoveryCandidateReadItem:
    """Map one joined row to the public DTO. Pure function (unit-testable).

    ``seed_hemisphere`` defaults to None so a caller that has no seed side still
    gets correct rows: an unresolvable relative context stays UNSPECIFIED.
    """
    return DiscoveryCandidateReadItem(
        candidate_id=row["candidate_id"],
        run_id=str(row["run_id"]),
        seed_entity_id=seed_entity_id,
        candidate_type=row["candidate_type"],
        local_id=row["local_id"],
        name=row["name"],
        payload=row["payload_json"],
        resolved_hemisphere=_resolved_hemisphere(
            row["candidate_type"], row["payload_json"], seed_hemisphere
        ),
        confidence=row["confidence"],
        status=row["status"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _is_uuid(value: str) -> bool:
    """A malformed run_id cannot identify any run, so it must not reach SQL.

    Without this the uuid column comparison raises a database DataError, which
    is a 500 for what is really "no such run".
    """
    try:
        uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        return False
    return True


async def list_candidates_for_run(
    session: AsyncSession, *, run_id: str
) -> list[DiscoveryCandidateReadItem]:
    """Every candidate persisted for ONE LLM Discovery run. SELECT only.

    Ordering is deterministic: ``candidate_type`` then ``local_id`` (which is
    unique within a run, so the order is total).

    Raises DiscoveryCandidateRunNotFound for an unknown or malformed run_id, and
    DiscoveryCandidateRunNotLlm when the run exists on another route. A known
    LLM run with no candidates returns an empty list — that is a fact about the
    run, not an error.

    Two statements, both bounded by one run: the route check, then the rows.
    """
    if not _is_uuid(run_id):
        raise DiscoveryCandidateRunNotFound(run_id)

    scope = (
        await session.execute(_RUN_SCOPE_SQL, {"run_id": run_id})
    ).mappings().one_or_none()
    if scope is None:
        raise DiscoveryCandidateRunNotFound(run_id)
    if scope["discovery_type"] != LLM_DISCOVERY:
        raise DiscoveryCandidateRunNotLlm(run_id, scope["discovery_type"])

    rows = (
        await session.execute(_FOR_RUN_SQL, {"run_pk": scope["run_pk"]})
    ).mappings().all()
    return [
        _row_to_item(row, scope["seed_entity_id"], scope["seed_hemisphere"])
        for row in rows
    ]


async def list_candidates_for_seed(
    session: AsyncSession, *, entity_id: str
) -> list[DiscoveryCandidateReadItem]:
    """Every LLM candidate proposed around ONE BrainRegion seed. SELECT only.

    Spans all LLM_DISCOVERY runs of that seed. Ordering preserves run
    chronology: newest run first, then ``candidate_type`` then ``local_id``.

    Raises DiscoveryCandidateSeedNotFound when the BrainRegion itself does not
    exist — "no such region" and "no candidates yet" are different facts and
    must not both look like an empty list.

    Two statements, neither of them per-candidate.
    """
    scope = (
        await session.execute(_SEED_SCOPE_SQL, {"entity_id": entity_id})
    ).mappings().one_or_none()
    if scope is None:
        raise DiscoveryCandidateSeedNotFound(entity_id)

    rows = (
        await session.execute(
            _FOR_SEED_SQL,
            {"seed_pk": scope["entity_pk"], "discovery_type": LLM_DISCOVERY},
        )
    ).mappings().all()
    return [
        _row_to_item(row, scope["entity_id"], scope["seed_hemisphere"])
        for row in rows
    ]
