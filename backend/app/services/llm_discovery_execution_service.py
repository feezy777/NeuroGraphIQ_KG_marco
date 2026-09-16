"""Phase 3B — LLM Discovery EXECUTION.

The chain this module implements, and nothing beyond it:

    BrainRegion seed -> create LLM_DISCOVERY run -> QUEUED -> RUNNING
    -> Phase 3A prompt -> DeepSeek provider -> newline-free raw text
    -> Phase 3A parser -> validated typed candidates
    -> persist those candidates (P0-1)
    -> RUNNING -> COMPLETED / FAILED

Frozen boundaries (phase brief §4 / §10 / §11 / §16 / §20):

  * SYNCHRONOUS. No Celery, no Redis, no BackgroundTasks, no scheduler, no
    retry daemon. One request performs one attempt and returns its result.
  * NO RUN-SIDE WRITE PATH. Only the run's lifecycle transitions are written,
    and only through the Phase 2B lifecycle service — never a raw INSERT/UPDATE.
  * NO KNOWLEDGE. Nothing here creates a connection / circuit / function /
    evidence / assertion. Candidates go to the Knowledge Production PROPOSAL
    staging table (``discovery_candidates``) and nowhere else.
  * CANDIDATES BEFORE COMPLETION. Persistence runs BEFORE the completion
    transition, so a COMPLETED/CANDIDATES_FOUND run always has its proposals
    stored; a persistence failure ends the run FAILED.
  * NO PROVIDER-SIDE SCHEMA ENFORCEMENT IS ASSUMED. ``response_schema`` is not
    passed: the DeepSeek provider only sets ``response_format=json_object``,
    which shapes the output but does not enforce this contract. The Phase 3A
    parser is the single structural authority.
  * NO SPECIES FABRICATION. ``species_context`` is required by the contract and
    is checked by the parser; this layer never fills it in, so a model that
    omits it FAILS rather than being silently defaulted.
"""
from __future__ import annotations

import hashlib
import logging

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm_model_policy import effective_deepseek_model
from app.prompts.llm_discovery_prompt import (
    PROMPT_KEY,
    PROMPT_VERSION,
    build_llm_discovery_prompt,
)
from app.schemas.knowledge_production import DiscoveryRunItem
from app.schemas.llm_discovery import SCHEMA_VERSION, LlmDiscoveryResponse
from app.schemas.llm_discovery_execution import (
    LlmDiscoveryExecutionMetrics,
    LlmDiscoveryExecutionResult,
)
from app.services import knowledge_discovery_run_lifecycle_service as lifecycle
from app.services import llm_candidate_persistence_service as candidate_persistence
from app.services import llm_discovery_readiness_service as readiness
from app.services.llm_discovery_parser import parse_llm_discovery_response
from app.services.llm_discovery_seed_service import build_discovery_input
from app.services.llm_providers.base import ProviderNotConfiguredError
from app.services.llm_providers.factory import get_llm_provider
from app.services.settings_service import get_deepseek_runtime_config

logger = logging.getLogger(__name__)

#: The business layer selects the PROVIDER and nothing else. The model is
#: decided by ``app.llm_model_policy`` at the provider call site (§3), so no
#: model name is written here.
PROVIDER_NAME = "deepseek"

DISCOVERY_TYPE_LLM = "LLM_DISCOVERY"

# Execution failure codes (§13 / §14). Reused vocabulary — no new framework.
ERR_PROVIDER_TIMEOUT = "LLM_PROVIDER_TIMEOUT"
ERR_PROVIDER_AUTH = "LLM_PROVIDER_AUTH_ERROR"
ERR_PROVIDER_ERROR = "LLM_PROVIDER_ERROR"
ERR_EMPTY_RESPONSE = "LLM_EMPTY_RESPONSE"
ERR_PARSE_FAILED = "LLM_DISCOVERY_PARSE_FAILED"
#: The model produced usable candidates and they could not be stored. The
#: DISCOVERY succeeded and the PERSISTENCE did not — conflating the two would
#: make a storage defect look like a model defect.
ERR_CANDIDATE_PERSISTENCE_FAILED = "LLM_CANDIDATE_PERSISTENCE_FAILED"

#: error_message is an OPERATIONAL summary. A response never goes here, so the
#: cap is a backstop against a long parser complaint, not a budget to spend.
_ERROR_MESSAGE_MAX = 500

#: `response_payload` carries a structured status_code for HTTP failures, but a
#: transport-level timeout never produces one. This narrow textual fallback is
#: the only way to tell the two apart, and it inspects the PROVIDER's own
#: classification, not the model's output.
_TIMEOUT_MARKERS = ("timeout", "timed out")


class LlmDiscoveryExecutionError(Exception):
    """An execution failure whose run has ALREADY been marked FAILED.

    The router maps this onto the HTTP error contract; ``run_id`` identifies
    the failed run so a caller can inspect it.
    """

    def __init__(self, code: str, message: str, *, run_id: str | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.run_id = run_id


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def classify_provider_exception(exc: BaseException) -> tuple[str, str]:
    """Map a raised provider-layer exception onto the frozen error codes.

    Messages are deliberately generic: an exception string can carry a URL, a
    stack fragment or worse, and none of that belongs on a run row.
    """
    if isinstance(exc, ProviderNotConfiguredError):
        # "no API key configured" IS an authentication problem from the
        # caller's point of view: the provider cannot be used as deployed.
        return ERR_PROVIDER_AUTH, "the DeepSeek provider is not configured"
    if isinstance(exc, httpx.TimeoutException):
        return ERR_PROVIDER_TIMEOUT, "the DeepSeek request timed out"
    if isinstance(exc, httpx.HTTPError):
        return ERR_PROVIDER_ERROR, "the DeepSeek request failed"
    return ERR_PROVIDER_ERROR, f"unexpected provider failure ({type(exc).__name__})"


def classify_transport_failure(response: object) -> tuple[str, str]:
    """Classify a provider result that came back with ``transport_ok=False``.

    Status codes are read from the structured ``response_payload`` the provider
    fills in — not guessed from prose.
    """
    payload = getattr(response, "response_payload", None) or {}
    status = payload.get("status_code")
    if status in (401, 403):
        return ERR_PROVIDER_AUTH, f"DeepSeek rejected the credentials (HTTP {status})"
    if status in (408, 504):
        return ERR_PROVIDER_TIMEOUT, f"DeepSeek timed out (HTTP {status})"
    if status is not None:
        return ERR_PROVIDER_ERROR, f"DeepSeek returned HTTP {status}"
    detail = (getattr(response, "error_message", None) or "").lower()
    if any(marker in detail for marker in _TIMEOUT_MARKERS):
        return ERR_PROVIDER_TIMEOUT, "the DeepSeek request timed out"
    return ERR_PROVIDER_ERROR, "the DeepSeek request failed"


def resolve_outcome(data: LlmDiscoveryResponse) -> str:
    """Map a parsed response onto the run's scientific outcome (§12).

    Only the four candidate arrays decide this. ``source_hints`` are unverified
    leads, not candidates, so a response carrying nothing but source hints
    reports NO_CANDIDATES_FOUND — and LLM Discovery can never report
    NO_EVIDENCE_FOUND, because it is not an evidence-search route.
    """
    total = (
        len(data.regions)
        + len(data.connections)
        + len(data.functions)
        + len(data.circuits)
    )
    return "CANDIDATES_FOUND" if total else "NO_CANDIDATES_FOUND"


def _candidate_counts(data: LlmDiscoveryResponse) -> dict[str, int]:
    return {
        "regions": len(data.regions),
        "connections": len(data.connections),
        "functions": len(data.functions),
        "circuits": len(data.circuits),
        "source_hints": len(data.source_hints),
    }


async def _abort(
    session: AsyncSession, run_id: str, code: str, message: str
) -> LlmDiscoveryExecutionError:
    """Move the run to FAILED, then hand back the error to raise (§11).

    A run must never be left permanently RUNNING, and the lifecycle service is
    the only sanctioned way to end it. If that transition itself fails we cannot
    repair it here — but we record it loudly rather than hide it, and the
    original failure still surfaces to the caller.
    """
    try:
        await lifecycle.fail_discovery_run(
            session, run_id, error_code=code, error_message=message[:_ERROR_MESSAGE_MAX]
        )
    except Exception:  # noqa: BLE001
        logger.exception("[llm-discovery] could not mark run FAILED run_id=%s", run_id)
    logger.warning("[llm-discovery] run failed run_id=%s error_code=%s", run_id, code)
    return LlmDiscoveryExecutionError(code, message, run_id=run_id)


def _log_success(run: DiscoveryRunItem, metrics: LlmDiscoveryExecutionMetrics) -> None:
    """One structured success line: ids, model, latency, counts, warnings (§25).

    Never logged: API keys, auth headers, the full prompt, the full response.
    """
    logger.info(
        "[llm-discovery] run completed run_id=%s seed_entity_id=%s provider=%s"
        " effective_model=%s prompt=%s@%s max_tokens=%s finish_reason=%s"
        " latency_ms=%s outcome=%s counts=%s warnings=%s",
        run.run_id,
        run.seed_entity_id,
        metrics.provider,
        metrics.effective_model,
        PROMPT_KEY,
        PROMPT_VERSION,
        metrics.max_tokens,
        metrics.finish_reason,
        metrics.latency_ms,
        run.outcome,
        metrics.candidate_counts,
        metrics.warning_count,
    )


#: The run's OWN internal keys. Reading seed_region_pk back from the run (rather
#: than re-resolving entity_id) means a candidate records the seed the RUN is
#: anchored to, and the two cannot disagree.
_RUN_KEYS_SQL = text(
    """
    SELECT run_pk, seed_region_pk
    FROM knowledge_discovery_runs
    WHERE run_id = :run_id
    """
)


async def _resolve_run_keys(session: AsyncSession, run_id: str) -> tuple[int, int] | None:
    """``(run_pk, seed_region_pk)`` for a run this module just created. SELECT only.

    INTERNAL keys: handed to the persistence layer, never returned to a caller.

    None means "candidate persistence cannot proceed" — the row is missing OR
    the read failed. Both are one failure to the caller, so they share the
    existing code path rather than growing a second vocabulary. On a failed read
    the session is rolled back first, because a failed statement aborts the
    transaction and the run could then not even be ended; a rollback failure is
    logged, never raised.
    """
    try:
        row = (
            await session.execute(_RUN_KEYS_SQL, {"run_id": run_id})
        ).mappings().one_or_none()
    except Exception:  # noqa: BLE001 - classified by the caller as a prep failure
        logger.exception("[llm-discovery] could not read run keys run_id=%s", run_id)
        try:
            await session.rollback()
        except Exception:  # noqa: BLE001
            logger.exception("[llm-discovery] session rollback failed")
        return None
    if row is None:
        return None
    return int(row["run_pk"]), int(row["seed_region_pk"])


async def execute_llm_discovery(
    session: AsyncSession, *, entity_id: str
) -> LlmDiscoveryExecutionResult:
    """Run one synchronous LLM Discovery for a BrainRegion seed.

    On success the parsed candidates are persisted BEFORE the run is declared
    COMPLETED, so a COMPLETED/CANDIDATES_FOUND run always has its proposals
    stored.

    Raises ``LlmDiscoveryDatabaseNotReady`` before anything happens at all when
    the database lacks the candidate staging shape, ``DiscoveryRunNotFound``
    (unknown seed), ``DiscoveryRunConflict`` (an active run already exists) or
    ``LlmDiscoveryExecutionError`` (the run was created, started and then
    FAILED).
    """
    # 0. THE DATABASE MUST BE ABLE TO STORE THE RESULT (P0-4C.1). This is the
    #    first thing that happens, before the seed is read, before a run row
    #    exists and before any model is called: the candidate staging table is
    #    written LAST, so without this check a database lacking it produces a
    #    paid provider call and a permanent FAILED run instead of an answer.
    #    Raising here costs nothing at all — no run, no request, no parse, no
    #    storage attempt.
    await readiness.require_llm_discovery_database_readiness(session)

    # 1. The seed must exist and be usable BEFORE a run is created, so an
    #    unusable seed cannot leave an orphaned FAILED run behind.
    seed = await build_discovery_input(session, entity_id)
    if seed is None:
        raise lifecycle.DiscoveryRunNotFound(entity_id, what="BrainRegion")

    # 2. TRUSTED INTERNAL CALLER. The client supplies only the entity id; the
    #    provenance below is written by the layer that knows what will run. The
    #    model comes from the global policy — never a literal repeated here.
    effective_model = effective_deepseek_model(None)
    run = await lifecycle.create_discovery_run(
        session,
        entity_id=entity_id,
        discovery_type=DISCOVERY_TYPE_LLM,
        provider=PROVIDER_NAME,
        model_name=effective_model,
        prompt_key=PROMPT_KEY,
        prompt_version=PROMPT_VERSION,
    )
    run = await lifecycle.start_discovery_run(session, run.run_id)

    # 3. Build the FROZEN Phase 3A prompt. Nothing is re-written here: the
    #    prompt module is the only author of its text.
    prompt = build_llm_discovery_prompt(seed)
    config = get_deepseek_runtime_config()

    try:
        provider = get_llm_provider(PROVIDER_NAME)
        response = await provider.complete_json(
            model=effective_model,
            system_prompt=prompt["system_prompt"],
            user_prompt=prompt["user_prompt"],
            temperature=config.temperature,
            max_tokens=config.max_tokens,
            timeout_seconds=config.timeout_seconds,
            # The reasoning profile is stated explicitly rather than inherited
            # from the server, so the budget is spent as a DECISION. It comes
            # from the one runtime authority; nothing is re-typed here.
            thinking_enabled=config.thinking_enabled,
            reasoning_effort=config.reasoning_effort,
        )
    except Exception as exc:  # noqa: BLE001 - classified, then re-raised typed
        code, message = classify_provider_exception(exc)
        raise await _abort(session, run.run_id, code, message) from None

    if not response.transport_ok:
        code, message = classify_transport_failure(response)
        raise await _abort(session, run.run_id, code, message)

    # 4. `content` is the answer; `reasoning_content` is never promoted to it
    #    (see the provider). A response with no content — including one the
    #    provider could only salvage as a raw body dump — is EMPTY, never
    #    parsed: feeding a dump into the parser would let it pass as a result.
    if not (response.raw_text or "").strip() or response.response_payload.get(
        "fallback_raw_response_used"
    ):
        # A reasoning model that exhausts its token budget before emitting an
        # answer is the common cause, and it is operationally different from a
        # model that simply said nothing: the fix is a larger budget, not a
        # different prompt. The code stays in the frozen vocabulary either way.
        detail = (
            " the model exhausted its token budget before producing an answer"
            if response.finish_reason == "length"
            else ""
        )
        raise await _abort(
            session,
            run.run_id,
            ERR_EMPTY_RESPONSE,
            "the model returned no content to parse" + detail,
        )

    # 5. The run records the model that ACTUALLY ran. The provider normalizes,
    #    so a disagreement here means the policy was bypassed somewhere, and
    #    that must fail loudly rather than be recorded as if it were normal.
    if response.model != effective_model:
        raise await _abort(
            session,
            run.run_id,
            ERR_PROVIDER_ERROR,
            f"model policy violation: requested {effective_model},"
            f" the provider reported {response.model}",
        )

    # 6. The Phase 3A parser is the ONLY structural authority (§19).
    parsed = parse_llm_discovery_response(
        response.raw_text, seed_entity_id=seed.seed_entity_id
    )
    if not parsed.ok or parsed.data is None:
        raise await _abort(
            session,
            run.run_id,
            ERR_PARSE_FAILED,
            f"the model response did not satisfy the discovery contract: {parsed.error}",
        )

    data = parsed.data

    # 7. PERSIST BEFORE COMPLETING (P0-1). A run must never read
    #    COMPLETED/CANDIDATES_FOUND while its candidates are only in memory: the
    #    response is gone once the request ends, so storing first is what makes
    #    "completed" a promise the data can keep. Zero candidates is NOT an
    #    error — "the model proposed nothing" is a scientific answer.
    run_keys = await _resolve_run_keys(session, run.run_id)
    if run_keys is None:
        # Persistence PREPARATION failed (the read raised, or the run's own row
        # vanished) — not a client error. Fail closed rather than guess a seed,
        # and report it as the same failure the storage step would report.
        raise await _abort(
            session,
            run.run_id,
            ERR_CANDIDATE_PERSISTENCE_FAILED,
            "the run's own identity could not be read back",
        )
    try:
        summary = await candidate_persistence.persist_discovery_candidates(
            session,
            discovery_run_pk=run_keys[0],
            seed_region_pk=run_keys[1],
            data=data,
        )
    except Exception:  # noqa: BLE001 - every storage defect ends the run
        # The persistence layer rolled its own transaction back, so the session
        # is usable and the run can still be ended. The message stays bounded:
        # exception text can carry SQL or a stack fragment, and neither belongs
        # on a run row.
        raise await _abort(
            session,
            run.run_id,
            ERR_CANDIDATE_PERSISTENCE_FAILED,
            "the discovery candidates could not be persisted",
        ) from None

    # Keyed by run_id (which the persistence layer's own log does not have), so
    # "which run stored how many" is answerable from the execution log alone.
    logger.info(
        "[llm-discovery] candidates persisted run_id=%s created=%s existing=%s by_type=%s",
        run.run_id, summary.created, summary.existing, summary.by_type,
    )

    run = await lifecycle.complete_discovery_run(
        session, run.run_id, resolve_outcome(data)
    )

    metrics = LlmDiscoveryExecutionMetrics(
        provider=response.provider,
        effective_model=response.model,
        prompt_key=PROMPT_KEY,
        prompt_version=PROMPT_VERSION,
        schema_version=SCHEMA_VERSION,
        max_tokens=config.max_tokens,
        finish_reason=response.finish_reason,
        thinking_enabled=config.thinking_enabled,
        reasoning_effort=config.reasoning_effort,
        latency_ms=response.latency_ms,
        prompt_tokens=response.usage.prompt_tokens,
        completion_tokens=response.usage.completion_tokens,
        total_tokens=response.usage.total_tokens,
        reasoning_tokens=response.usage.reasoning_tokens,
        prompt_sha256=_sha256(prompt["system_prompt"] + "\n" + prompt["user_prompt"]),
        response_sha256=_sha256(response.raw_text),
        warning_count=len(parsed.validation_warnings),
        candidate_counts=_candidate_counts(data),
    )
    _log_success(run, metrics)

    return LlmDiscoveryExecutionResult(
        run=run,
        result=data,
        validation_warnings=parsed.validation_warnings,
        metrics=metrics,
    )
