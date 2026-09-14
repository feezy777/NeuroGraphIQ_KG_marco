"""Phase 3B — LLM Discovery EXECUTION response DTOs.

These DTOs describe one completed execution attempt. They carry the run's
lifecycle record plus the typed, IN-MEMORY discovery result.

What is deliberately absent, and must stay absent (§9 / §15 of the phase brief):

  * the raw model response and any ``reasoning_content`` — the parser's output
    is the answer; the deliberation that preceded it is not;
  * API keys, authorization headers, request bodies, SQL text, constraint
    names, and every database primary key.

``metrics`` is provenance, not content: hashes, counts, latency and token usage
are what make a run auditable without storing what the model said. The response
is NOT persisted anywhere — no candidate table exists and none may be added.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.knowledge_production import DiscoveryRunItem
from app.schemas.llm_discovery import DiscoveryWarning, LlmDiscoveryResponse


class LlmDiscoveryExecutionMetrics(BaseModel):
    """Non-content execution provenance (§15).

    Every field is either a digest, a count, or a measured magnitude. None of
    them can reconstruct the model's answer, and none of them is a secret.
    """

    provider: str
    effective_model: str
    prompt_key: str
    prompt_version: str
    schema_version: str

    #: The budget that was actually REQUESTED. Without it a truncated answer is
    #: indistinguishable from a model that simply had nothing to say.
    max_tokens: int
    #: ``stop`` = the model finished; ``length`` = it ran out of budget. A
    #: truncated run must be read WITH the reasoning profile below: under
    #: thinking mode the reasoning consumes the very same generation budget.
    finish_reason: str | None = None
    thinking_enabled: bool | None = None
    reasoning_effort: str | None = None

    latency_ms: int

    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    #: A COUNT only, and only when the provider reports one. Never the text.
    reasoning_tokens: int | None = None

    #: SHA-256 of the prompt actually sent / the raw text actually received.
    #: Lets a later phase prove which response was parsed without keeping it.
    prompt_sha256: str
    response_sha256: str

    warning_count: int
    #: regions / connections / functions / circuits / source_hints.
    candidate_counts: dict[str, int] = Field(default_factory=dict)


class LlmDiscoveryExecutionResult(BaseModel):
    """The outcome of one synchronous LLM Discovery execution.

    ``run`` is the persisted lifecycle record (COMPLETED, with its outcome).
    ``result`` and ``validation_warnings`` exist only in this response: they are
    candidates awaiting a later, governed phase, never formal knowledge.
    """

    run: DiscoveryRunItem
    result: LlmDiscoveryResponse
    validation_warnings: list[DiscoveryWarning] = Field(default_factory=list)
    metrics: LlmDiscoveryExecutionMetrics
