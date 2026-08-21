"""Persistence and bounded parallel execution for paper-evidence extraction runs."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.paper_evidence_extraction import (
    PaperEvidenceExtractionItem,
    PaperEvidenceExtractionRun,
)
from app.schemas.paper_evidence_extraction import (
    PaperEvidenceExtractionItemDetail,
    PaperEvidenceExtractionRunDetail,
    PaperEvidenceExtractionRunRequest,
    PaperEvidenceExtractionStartResponse,
)
from app.services import paper_evidence_service as pes

logger = logging.getLogger(__name__)

_TERMINAL_RUN_STATUSES = {"completed", "partially_failed", "failed", "cancelled"}
_TERMINAL_ITEM_STATUSES = {"completed", "no_evidence", "failed", "cancelled"}
_IN_FLIGHT_ITEM_STATUSES = {
    "fetching",
    "parsing",
    "retrieving",
    "locating",
    "judging",
    "verifying",
}
_ACTIVE_ITEM_STATUSES = {"queued", *_IN_FLIGHT_ITEM_STATUSES}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _progress_percent(
    run: PaperEvidenceExtractionRun,
    items: list[PaperEvidenceExtractionItem],
) -> float:
    if run.total_items > 0 and run.status in _TERMINAL_RUN_STATUSES:
        return 100.0
    if not items:
        return 0.0
    progress = sum(min(100, max(0, item.progress_percent)) for item in items)
    return round(progress / len(items), 2)


def _run_detail(
    run: PaperEvidenceExtractionRun,
    items: list[PaperEvidenceExtractionItem],
) -> PaperEvidenceExtractionRunDetail:
    ordered_items = sorted(items, key=lambda item: item.item_index)
    return PaperEvidenceExtractionRunDetail(
        id=run.id,
        target_type=run.target_type,
        target_id=run.target_id,
        mode=run.mode,
        status=run.status,
        total_items=run.total_items,
        completed_items=run.completed_items,
        evidence_hit_items=run.evidence_hit_items,
        no_evidence_items=run.no_evidence_items,
        failed_items=run.failed_items,
        requested_concurrency=run.requested_concurrency,
        active_concurrency=run.active_concurrency,
        cancel_requested=run.cancel_requested,
        created_at=run.created_at,
        updated_at=run.updated_at,
        started_at=run.started_at,
        finished_at=run.finished_at,
        items=[
            PaperEvidenceExtractionItemDetail.model_validate(item)
            for item in ordered_items
        ],
        progress_percent=_progress_percent(run, ordered_items),
    )


def _recompute_counters(
    run: PaperEvidenceExtractionRun,
    items: list[PaperEvidenceExtractionItem],
) -> None:
    evidence_hit = sum(1 for item in items if item.status == "completed")
    no_evidence = sum(1 for item in items if item.status == "no_evidence")
    failed = sum(1 for item in items if item.status == "failed")
    cancelled = sum(1 for item in items if item.status == "cancelled")
    run.evidence_hit_items = evidence_hit
    run.no_evidence_items = no_evidence
    run.failed_items = failed
    run.completed_items = evidence_hit + no_evidence + failed + cancelled
    run.active_concurrency = sum(
        1 for item in items if item.status in _IN_FLIGHT_ITEM_STATUSES
    )


def _finalize_run_status(
    run: PaperEvidenceExtractionRun,
    items: list[PaperEvidenceExtractionItem],
) -> None:
    if any(item.status in _ACTIVE_ITEM_STATUSES for item in items):
        return
    hits = run.evidence_hit_items + run.no_evidence_items
    if run.failed_items and hits:
        run.status = "partially_failed"
    elif run.failed_items:
        run.status = "failed"
    elif hits == 0 and any(item.status == "cancelled" for item in items):
        run.status = "cancelled"
    else:
        run.status = "completed"
    run.active_concurrency = 0
    run.finished_at = _now()
    run.updated_at = run.finished_at


async def create_run(
    session: AsyncSession,
    request: PaperEvidenceExtractionRunRequest,
) -> PaperEvidenceExtractionStartResponse:
    now = _now()
    run_id = uuid.uuid4()
    request_json = request.model_dump(mode="json")
    run = PaperEvidenceExtractionRun(
        id=run_id,
        target_type=request.target_type,
        target_id=request.target_id,
        mode=request.mode,
        status="queued",
        total_items=len(request.papers),
        completed_items=0,
        evidence_hit_items=0,
        no_evidence_items=0,
        failed_items=0,
        requested_concurrency=request.concurrency,
        active_concurrency=0,
        cancel_requested=False,
        request_json=request_json,
        created_at=now,
        updated_at=now,
    )
    items = [
        PaperEvidenceExtractionItem(
            id=uuid.uuid4(),
            run_id=run_id,
            item_index=item_index,
            pmid=paper.pmid or None,
            pmcid=paper.pmcid,
            doi=paper.doi,
            title=paper.title,
            paper_json=paper.model_dump(mode="json"),
            status="queued",
            progress_percent=0,
            attempt_count=0,
            stage_timings_json={},
            updated_at=now,
        )
        for item_index, paper in enumerate(request.papers)
    ]
    session.add(run)
    await session.flush()  # ensure run row exists before inserting items (asyncpg FK)
    session.add_all(items)
    try:
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    return PaperEvidenceExtractionStartResponse(
        run_id=run.id,
        status=run.status,
        total_items=run.total_items,
        requested_concurrency=run.requested_concurrency,
        created_at=run.created_at,
    )


async def get_run_detail(
    session: AsyncSession,
    run_id: uuid.UUID,
) -> PaperEvidenceExtractionRunDetail:
    run = await session.get(PaperEvidenceExtractionRun, run_id)
    if run is None:
        raise ValueError("extraction run not found")

    result = await session.execute(
        select(PaperEvidenceExtractionItem)
        .where(PaperEvidenceExtractionItem.run_id == run_id)
        .order_by(PaperEvidenceExtractionItem.item_index)
    )
    items = list(result.scalars().all())
    return _run_detail(run, items)


async def cancel_run(
    session: AsyncSession,
    run_id: uuid.UUID,
) -> PaperEvidenceExtractionRunDetail:
    run = await session.get(PaperEvidenceExtractionRun, run_id)
    if run is None:
        raise ValueError("extraction run not found")
    if run.status in _TERMINAL_RUN_STATUSES:
        return await get_run_detail(session, run_id)

    now = _now()
    run.cancel_requested = True
    run.updated_at = now
    result = await session.execute(
        select(PaperEvidenceExtractionItem).where(
            PaperEvidenceExtractionItem.run_id == run_id
        )
    )
    items = list(result.scalars().all())
    for item in items:
        if item.status == "queued":
            item.status = "cancelled"
            item.progress_percent = 100
            item.finished_at = now
            item.updated_at = now
            item.error_code = item.error_code or "CANCELLED"
            item.error_message = item.error_message or "cancelled before start"
    _recompute_counters(run, items)
    if not any(item.status in _ACTIVE_ITEM_STATUSES for item in items):
        _finalize_run_status(run, items)
    await session.commit()
    return await get_run_detail(session, run_id)


async def retry_failed_items(
    session: AsyncSession,
    run_id: uuid.UUID,
) -> dict[str, Any]:
    run = await session.get(PaperEvidenceExtractionRun, run_id)
    if run is None:
        raise ValueError("extraction run not found")
    if run.status not in _TERMINAL_RUN_STATUSES and run.status != "running":
        # Allow retry only when the run finished (or still has failed rows after
        # a partial finish). Reject mid-flight retries that race the workers.
        if run.status not in {"completed", "partially_failed", "failed", "cancelled"}:
            raise ValueError("extraction run is not retryable in its current state")

    result = await session.execute(
        select(PaperEvidenceExtractionItem).where(
            PaperEvidenceExtractionItem.run_id == run_id
        )
    )
    items = list(result.scalars().all())
    now = _now()
    retried = 0
    for item in items:
        if item.status != "failed":
            continue
        item.status = "queued"
        item.progress_percent = 0
        item.error_code = None
        item.error_message = None
        item.result_json = None
        item.stage_timings_json = {}
        item.started_at = None
        item.finished_at = None
        item.updated_at = now
        retried += 1

    if retried == 0:
        await session.commit()
        return {"run_id": str(run_id), "retried": 0, "status": run.status}

    run.cancel_requested = False
    run.status = "queued"
    run.finished_at = None
    run.updated_at = now
    _recompute_counters(run, items)
    await session.commit()
    return {"run_id": str(run_id), "retried": retried, "status": run.status}


async def recover_interrupted_runs(session: AsyncSession) -> list[uuid.UUID]:
    """Reset in-flight items to queued and return run ids that should resume."""
    result = await session.execute(
        select(PaperEvidenceExtractionRun).where(
            PaperEvidenceExtractionRun.status.in_(["queued", "running"]),
            PaperEvidenceExtractionRun.cancel_requested.is_(False),
        )
    )
    runs = list(result.scalars().all())
    resume_ids: list[uuid.UUID] = []
    now = _now()
    for run in runs:
        items_result = await session.execute(
            select(PaperEvidenceExtractionItem).where(
                PaperEvidenceExtractionItem.run_id == run.id
            )
        )
        items = list(items_result.scalars().all())
        changed = False
        for item in items:
            if item.status in _IN_FLIGHT_ITEM_STATUSES:
                item.status = "queued"
                item.progress_percent = 0
                item.updated_at = now
                item.started_at = None
                changed = True
        if any(item.status == "queued" for item in items):
            run.status = "queued"
            run.active_concurrency = 0
            run.finished_at = None
            run.updated_at = now
            _recompute_counters(run, items)
            resume_ids.append(run.id)
        elif changed:
            _recompute_counters(run, items)
            _finalize_run_status(run, items)
    await session.commit()
    return resume_ids


async def _load_items(
    session: AsyncSession, run_id: uuid.UUID
) -> list[PaperEvidenceExtractionItem]:
    result = await session.execute(
        select(PaperEvidenceExtractionItem)
        .where(PaperEvidenceExtractionItem.run_id == run_id)
        .order_by(PaperEvidenceExtractionItem.item_index)
    )
    return list(result.scalars().all())


async def _set_item_stage(
    item_id: uuid.UUID,
    stage: str,
    *,
    timings: dict[str, Any] | None = None,
) -> bool:
    """Persist a stage update. Returns False if the item is already terminal."""
    from app.database import AsyncSessionLocal

    if AsyncSessionLocal is None:
        return False
    progress = pes.STAGE_PROGRESS.get(stage)  # type: ignore[arg-type]
    if progress is None:
        return True
    async with AsyncSessionLocal() as session:
        item = await session.get(PaperEvidenceExtractionItem, item_id)
        if item is None:
            return False
        if item.status in _TERMINAL_ITEM_STATUSES:
            return False
        now = _now()
        if item.started_at is None and stage != "queued":
            item.started_at = now
        item.status = stage
        item.progress_percent = progress
        if timings is not None:
            merged = dict(item.stage_timings_json or {})
            merged.update(timings)
            item.stage_timings_json = merged
        item.updated_at = now
        run = await session.get(PaperEvidenceExtractionRun, item.run_id)
        if run is not None:
            items = await _load_items(session, item.run_id)
            _recompute_counters(run, items)
            run.updated_at = now
        await session.commit()
        return True


async def _finalize_item(
    item_id: uuid.UUID,
    *,
    status: str,
    candidate: dict[str, Any] | None,
    error_code: str | None = None,
    error_message: str | None = None,
    stage_timings: dict[str, Any] | None = None,
) -> None:
    from app.database import AsyncSessionLocal

    if AsyncSessionLocal is None:
        return
    async with AsyncSessionLocal() as session:
        item = await session.get(PaperEvidenceExtractionItem, item_id)
        if item is None:
            return
        now = _now()
        item.status = status
        item.progress_percent = 100
        item.result_json = candidate
        item.error_code = error_code
        item.error_message = error_message
        if stage_timings:
            merged = dict(item.stage_timings_json or {})
            merged.update(stage_timings)
            item.stage_timings_json = merged
        item.finished_at = now
        item.updated_at = now
        if item.started_at is None:
            item.started_at = now

        run = await session.get(PaperEvidenceExtractionRun, item.run_id)
        items = await _load_items(session, item.run_id)
        if run is not None:
            _recompute_counters(run, items)
            if not any(i.status in _ACTIVE_ITEM_STATUSES for i in items):
                _finalize_run_status(run, items)
            else:
                run.status = "running"
                run.updated_at = now
        await session.commit()


async def _process_item(
    *,
    run_id: uuid.UUID,
    item_id: uuid.UUID,
    context: dict[str, Any],
    only_oa: bool,
    mode: str,
    sem_paper: asyncio.Semaphore,
    sem_fetch: asyncio.Semaphore,
    sem_deepseek: asyncio.Semaphore,
    stop_event: asyncio.Event,
) -> None:
    from app.database import AsyncSessionLocal

    async with sem_paper:
        if AsyncSessionLocal is None:
            return

        async with AsyncSessionLocal() as gate:
            run = await gate.get(PaperEvidenceExtractionRun, run_id)
            item = await gate.get(PaperEvidenceExtractionItem, item_id)
            if run is None or item is None:
                return
            if run.cancel_requested or stop_event.is_set() or item.status != "queued":
                if item.status == "queued":
                    item.status = "cancelled"
                    item.progress_percent = 100
                    item.finished_at = _now()
                    item.updated_at = item.finished_at
                    item.error_code = "CANCELLED"
                    item.error_message = "cancelled before start"
                    items = await _load_items(gate, run_id)
                    _recompute_counters(run, items)
                    if not any(i.status in _ACTIVE_ITEM_STATUSES for i in items):
                        _finalize_run_status(run, items)
                    await gate.commit()
                return
            item.attempt_count = int(item.attempt_count or 0) + 1
            item.started_at = _now()
            item.updated_at = item.started_at
            item.status = "fetching"
            item.progress_percent = pes.STAGE_PROGRESS["fetching"]
            run.status = "running"
            run.updated_at = item.started_at
            if run.started_at is None:
                run.started_at = item.started_at
            await gate.commit()
            paper = dict(item.paper_json or {})
            if item.pmid and not paper.get("pmid"):
                paper["pmid"] = item.pmid
            if item.doi and not paper.get("doi"):
                paper["doi"] = item.doi
            if item.pmcid and not paper.get("pmcid"):
                paper["pmcid"] = item.pmcid

        stage_started = time.monotonic()
        last_stage = "fetching"
        timings: dict[str, Any] = {}

        async def on_stage(stage: str) -> None:
            nonlocal last_stage, stage_started
            now_mono = time.monotonic()
            elapsed_ms = int((now_mono - stage_started) * 1000)
            timings[f"{last_stage}_ms"] = timings.get(f"{last_stage}_ms", 0) + elapsed_ms
            stage_started = now_mono
            last_stage = stage
            if stop_event.is_set():
                return
            await _set_item_stage(item_id, stage, timings={f"{stage}_entered_at": _now().isoformat()})

        try:
            async with AsyncSessionLocal() as session:
                envelope = await pes.extract_candidate_for_paper(
                    session,
                    context=context,
                    paper=paper,
                    only_oa=only_oa,
                    sem_fetch=sem_fetch,
                    sem_deepseek=sem_deepseek,
                    mode=mode,
                    on_stage=on_stage,
                )
            status = envelope.get("status") or "failed"
            candidate = envelope.get("candidate") or {}
            error_code = candidate.get("error_code")
            error_message = candidate.get("error_message") or envelope.get("reason")
            timings[f"{last_stage}_ms"] = timings.get(f"{last_stage}_ms", 0) + int(
                (time.monotonic() - stage_started) * 1000
            )
            await _finalize_item(
                item_id,
                status=status if status in _TERMINAL_ITEM_STATUSES else "failed",
                candidate=candidate,
                error_code=error_code,
                error_message=error_message,
                stage_timings=timings,
            )

            coverage = candidate.get("coverage_summary") or {}
            if (
                status == "completed"
                and coverage.get("overall_direction") == "supports"
                and coverage.get("full_claim_supported")
            ):
                # stop_after_strong_support is enforced by the caller via stop_event.
                pass
            return
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "paper evidence extraction item failed run_id=%s item_id=%s",
                run_id,
                item_id,
            )
            timings[f"{last_stage}_ms"] = timings.get(f"{last_stage}_ms", 0) + int(
                (time.monotonic() - stage_started) * 1000
            )
            await _finalize_item(
                item_id,
                status="failed",
                candidate={
                    **paper,
                    "error_code": "EXTRACTION_WORKER_ERROR",
                    "error_message": str(exc)[:500],
                    "passages": [],
                },
                error_code="EXTRACTION_WORKER_ERROR",
                error_message=str(exc)[:500],
                stage_timings=timings,
            )


async def execute_run(
    run_id: uuid.UUID,
    *,
    extract_item=_process_item,
) -> None:
    """Execute a queued extraction run with bounded paper concurrency."""
    from app.database import AsyncSessionLocal

    if AsyncSessionLocal is None:
        return

    settings = get_settings()
    async with AsyncSessionLocal() as session:
        run = await session.get(PaperEvidenceExtractionRun, run_id)
        if run is None:
            return
        if run.cancel_requested and run.status in _TERMINAL_RUN_STATUSES:
            return
        request = run.request_json or {}
        only_oa = bool(request.get("only_oa", False))
        stop_after = bool(request.get("stop_after_strong_support", False))
        mode = str(request.get("mode") or run.mode or "function")
        items = await _load_items(session, run_id)
        queued = [item for item in items if item.status == "queued"]
        if not queued:
            _recompute_counters(run, items)
            if not any(i.status in _ACTIVE_ITEM_STATUSES for i in items):
                _finalize_run_status(run, items)
            await session.commit()
            return

        try:
            context = await pes.build_retrieval_context(
                session, run.target_type, run.target_id, mode=mode
            )
        except Exception as exc:  # noqa: BLE001
            now = _now()
            for item in queued:
                item.status = "failed"
                item.progress_percent = 100
                item.error_code = "CONTEXT_BUILD_FAILED"
                item.error_message = str(exc)[:500]
                item.finished_at = now
                item.updated_at = now
            _recompute_counters(run, items)
            _finalize_run_status(run, items)
            await session.commit()
            return

        run.status = "running"
        run.started_at = run.started_at or _now()
        run.updated_at = run.started_at
        await session.commit()
        requested = max(1, int(run.requested_concurrency or 1))
        configured = max(1, int(settings.paper_extraction_worker_concurrency))
        worker_n = min(requested, configured, len(queued))
        fetch_n = max(1, int(settings.paper_extraction_fetch_concurrency))
        llm_n = max(1, int(settings.paper_extraction_llm_concurrency))
        item_ids = [item.id for item in queued]

    sem_paper = asyncio.Semaphore(worker_n)
    sem_fetch = asyncio.Semaphore(fetch_n)
    sem_deepseek = asyncio.Semaphore(llm_n)
    stop_event = asyncio.Event()

    async def _runner(item_id: uuid.UUID) -> None:
        await extract_item(
            run_id=run_id,
            item_id=item_id,
            context=context,
            only_oa=only_oa,
            mode=mode,
            sem_paper=sem_paper,
            sem_fetch=sem_fetch,
            sem_deepseek=sem_deepseek,
            stop_event=stop_event,
        )
        if stop_after:
            async with AsyncSessionLocal() as check:
                item = await check.get(PaperEvidenceExtractionItem, item_id)
                if item is None:
                    return
                candidate = item.result_json or {}
                coverage = candidate.get("coverage_summary") or {}
                if (
                    item.status == "completed"
                    and coverage.get("overall_direction") == "supports"
                    and coverage.get("full_claim_supported")
                ):
                    stop_event.set()
                    run_row = await check.get(PaperEvidenceExtractionRun, run_id)
                    remaining = await _load_items(check, run_id)
                    now = _now()
                    for rem in remaining:
                        if rem.status == "queued":
                            rem.status = "cancelled"
                            rem.progress_percent = 100
                            rem.finished_at = now
                            rem.updated_at = now
                            rem.error_code = "STOP_AFTER_STRONG_SUPPORT"
                            rem.error_message = "stopped after strong support"
                    if run_row is not None:
                        _recompute_counters(run_row, remaining)
                        if not any(i.status in _ACTIVE_ITEM_STATUSES for i in remaining):
                            _finalize_run_status(run_row, remaining)
                    await check.commit()

    results = await asyncio.gather(
        *[_runner(item_id) for item_id in item_ids],
        return_exceptions=True,
    )
    for result in results:
        if isinstance(result, Exception):
            logger.exception(
                "paper evidence extraction worker crashed run_id=%s",
                run_id,
                exc_info=result,
            )

    async with AsyncSessionLocal() as session:
        run = await session.get(PaperEvidenceExtractionRun, run_id)
        if run is None:
            return
        items = await _load_items(session, run_id)
        _recompute_counters(run, items)
        if not any(i.status in _ACTIVE_ITEM_STATUSES for i in items):
            _finalize_run_status(run, items)
        else:
            run.status = "running"
            run.updated_at = _now()
        await session.commit()


async def execute_run_background(run_id: uuid.UUID | str) -> None:
    rid = run_id if isinstance(run_id, uuid.UUID) else uuid.UUID(str(run_id))
    try:
        await execute_run(rid)
    except Exception:  # noqa: BLE001
        logger.exception("paper evidence extraction run failed run_id=%s", rid)
