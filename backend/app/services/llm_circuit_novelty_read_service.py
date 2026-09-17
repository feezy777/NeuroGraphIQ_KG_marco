"""Reading stored circuit novelty assessments.

Read-only, and structurally so: this module imports no provider, no model policy
and no settings, so it does not merely promise it never calls an LLM — it has no
way to. A GET costs nothing and cannot become a paid operation by accident.

Four reads:
  * one assessment by its public id, with every verdict
  * the latest assessment of one discovery run
  * the verdicts of one assessment
  * the counts of one assessment, without loading its verdicts

Internal keys never leave here. The tables store a verdict as a RELATIONSHIP
between candidate rows — ``candidate_pk``, ``matched_prior_candidate_pk`` — and
a caller receives the public ``candidate_id`` instead, so no client can grow a
dependency on a row number that is not part of any contract.
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.circuit_novelty import (
    PersistedNoveltyAssessment,
    PersistedNoveltyVerdict,
    NoveltySummary,
)


class NoveltyAssessmentNotFound(Exception):
    """No stored assessment carries that public id."""

    code = "NOVELTY_ASSESSMENT_NOT_FOUND"

    def __init__(self, assessment_id: str) -> None:
        super().__init__(f"novelty assessment '{assessment_id}' not found")
        self.assessment_id = assessment_id


#: The parent row, with the seed's public id resolved. `discovery_view` is
#: stored, so it is read rather than re-derived from the strategy identifier —
#: what the row SAYS is the scope it was made under.
_ASSESSMENT_SQL = text(
    """
    SELECT a.assessment_pk, a.assessment_id, a.discovery_view,
           a.query_strategy_version, a.provider, a.model_name,
           a.assessor_prompt_key, a.assessor_prompt_version,
           a.raw_circuit_count, a.new_count, a.alias_count,
           a.reformulation_count, a.borderline_count, a.semantic_new_count,
           a.prior_completed_run_count, a.prior_circuit_count,
           a.created_at,
           r.run_id AS target_run_id,
           e.entity_id AS seed_entity_id
    FROM discovery_circuit_novelty_assessments a
    JOIN knowledge_discovery_runs r ON r.run_pk = a.target_run_pk
    JOIN kg_entities e ON e.entity_pk = a.seed_region_pk
    WHERE a.assessment_id = :assessment_id
    """
)

#: The latest assessment of one run. `created_at DESC` rather than "the only
#: one": the idempotency key includes the prompt version and the model, so a run
#: assessed under a bumped prompt legitimately has more than one row.
_LATEST_FOR_RUN_SQL = text(
    """
    SELECT a.assessment_id
    FROM discovery_circuit_novelty_assessments a
    JOIN knowledge_discovery_runs r ON r.run_pk = a.target_run_pk
    WHERE r.run_id = :run_id
    ORDER BY a.created_at DESC, a.assessment_pk DESC
    LIMIT 1
    """
)

#: Verdicts with both candidate ids resolved, in the target run's own circuit
#: order so the list reads the way the run's circuits were stored.
_VERDICTS_SQL = text(
    """
    SELECT dc.candidate_id, dc.local_id, dc.name,
           v.novelty_class, v.short_reason,
           m.candidate_id AS matched_candidate_id,
           mr.run_id      AS matched_run_id
    FROM discovery_circuit_novelty_verdicts v
    JOIN discovery_candidates dc ON dc.candidate_pk = v.candidate_pk
    LEFT JOIN discovery_candidates m ON m.candidate_pk = v.matched_prior_candidate_pk
    LEFT JOIN knowledge_discovery_runs mr ON mr.run_pk = m.discovery_run_pk
    WHERE v.assessment_pk = :assessment_pk
    ORDER BY v.candidate_pk
    """
)


async def _parent_row(session: AsyncSession, assessment_id: str):
    return (
        await session.execute(_ASSESSMENT_SQL, {"assessment_id": assessment_id})
    ).mappings().one_or_none()


async def latest_assessment_id_for_run(
    session: AsyncSession, *, run_id: str
) -> str | None:
    """The public id of the newest assessment of `run_id`, or None."""
    row = (
        await session.execute(_LATEST_FOR_RUN_SQL, {"run_id": run_id})
    ).scalars().first()
    return str(row) if row is not None else None


async def list_novelty_verdicts(
    session: AsyncSession, *, assessment_id: str
) -> list[PersistedNoveltyVerdict]:
    """Every verdict of one assessment, in the target run's circuit order."""
    parent = await _parent_row(session, assessment_id)
    if parent is None:
        raise NoveltyAssessmentNotFound(assessment_id)
    rows = (
        await session.execute(
            _VERDICTS_SQL, {"assessment_pk": parent["assessment_pk"]}
        )
    ).mappings().all()
    return [
        PersistedNoveltyVerdict(
            candidate_id=r["candidate_id"],
            local_id=r["local_id"],
            name=r["name"],
            novelty_class=r["novelty_class"],
            matched_prior_candidate_id=r["matched_candidate_id"],
            matched_prior_run_id=(
                str(r["matched_run_id"]) if r["matched_run_id"] else None
            ),
            short_reason=r["short_reason"],
        )
        for r in rows
    ]


async def get_novelty_summary(
    session: AsyncSession, *, assessment_id: str
) -> NoveltySummary:
    """One assessment's counts, without loading its verdicts."""
    parent = await _parent_row(session, assessment_id)
    if parent is None:
        raise NoveltyAssessmentNotFound(assessment_id)
    return NoveltySummary(**_summary_kwargs(parent))


async def get_novelty_assessment(
    session: AsyncSession, *, assessment_id: str
) -> PersistedNoveltyAssessment:
    """One assessment and every verdict it holds."""
    parent = await _parent_row(session, assessment_id)
    if parent is None:
        raise NoveltyAssessmentNotFound(assessment_id)
    verdicts = await list_novelty_verdicts(session, assessment_id=assessment_id)
    return PersistedNoveltyAssessment(
        **_summary_kwargs(parent), verdicts=verdicts
    )


async def get_latest_novelty_assessment(
    session: AsyncSession, *, run_id: str
) -> PersistedNoveltyAssessment | None:
    """The newest assessment of one discovery run, or None if it has none.

    None is not an error: a run that has never been assessed is the normal state
    of every run before its first POST.
    """
    assessment_id = await latest_assessment_id_for_run(session, run_id=run_id)
    if assessment_id is None:
        return None
    return await get_novelty_assessment(session, assessment_id=assessment_id)


def _summary_kwargs(row) -> dict:
    return {
        "assessment_id": row["assessment_id"],
        "target_run_id": str(row["target_run_id"]),
        "seed_entity_id": row["seed_entity_id"],
        "discovery_view": row["discovery_view"],
        "query_strategy_version": row["query_strategy_version"],
        "provider": row["provider"],
        "model_name": row["model_name"],
        "assessor_prompt_key": row["assessor_prompt_key"],
        "assessor_prompt_version": row["assessor_prompt_version"],
        "raw_circuit_count": row["raw_circuit_count"],
        "NEW_count": row["new_count"],
        "ALIAS_count": row["alias_count"],
        "REFORMULATION_count": row["reformulation_count"],
        "BORDERLINE_count": row["borderline_count"],
        "semantic_new_count": row["semantic_new_count"],
        "prior_completed_run_count": row["prior_completed_run_count"],
        "prior_circuit_count": row["prior_circuit_count"],
        "created_at": row["created_at"],
    }


__all__ = [
    "NoveltyAssessmentNotFound",
    "get_latest_novelty_assessment",
    "get_novelty_assessment",
    "get_novelty_summary",
    "latest_assessment_id_for_run",
    "list_novelty_verdicts",
]
