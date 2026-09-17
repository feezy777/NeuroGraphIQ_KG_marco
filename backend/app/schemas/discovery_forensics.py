"""Bounded provider-response forensics for ONE Discovery run.

Why this exists
---------------
A live Round-21 Discovery attempt failed with an envelope-shape parse error, and
the response that caused it was gone the moment the request ended: the run kept
its ``error_code`` and a 500-character ``error_message`` and nothing else. The
failure could not be diagnosed from the database — it had to be reconstructed
from a log file, and the question "did the model actually emit a bare region, or
did the extractor hand us one?" remains unanswerable to this day.

That is ``DISCOVERY_FAILED_RAW_RESPONSE_AUDIT_GAP``. This record closes it.

What it is NOT
--------------
It is not a raw-response archive. The preview is bounded, it is for debugging,
and it never becomes a second candidate store: no request payload, no header, no
credential and no environment value is ever part of it. Provider response
content and provider response metadata only.

The record is deliberately provider-agnostic and free of any service import, so
both the execution service (which fills it) and the lifecycle service (which
writes it) can depend on it without a cycle.
"""
from __future__ import annotations

from dataclasses import dataclass

#: The storage columns this record owns, in write order. It lives beside the
#: record so that a field added to one cannot be silently forgotten by the other
#: — the constructor and the UPDATE are driven from this one tuple.
FORENSIC_COLUMN_NAMES: tuple[str, ...] = (
    "response_sha256",
    "raw_response_preview",
    "finish_reason",
    "prompt_tokens",
    "completion_tokens",
    "total_tokens",
    "provider_latency_ms",
    "fallback_raw_response_used",
)

#: Data characters of the response kept for forensics. The storage CHECK allows
#: 2048, which is this plus the longest truncation marker the shared preview
#: helper appends, so the helper is used unchanged and storage still refuses
#: anything unbounded.
#:
#: It is a CHARACTER bound on a debugging preview — quite unlike a token budget,
#: which is a runtime setting read from the settings authority at the provider
#: call site. The two are deliberately not co-located: a number that bounds a
#: preview has no business living next to the code that decides how much the
#: model may generate.
RAW_RESPONSE_PREVIEW_MAX_CHARS = 2000


@dataclass(frozen=True)
class DiscoveryResponseForensics:
    """What the provider returned, reduced to what an operator can act on.

    ``None`` means "there is nothing truthful to record", never "unknown but
    guessable". In particular ``response_sha256`` is NULL — not the hash of an
    empty string — when the provider produced no content at all, because "the
    model said nothing" and "the model said the empty string" are different
    facts and only one of them happened.

    ``response_sha256`` is always taken over the COMPLETE raw text; the preview
    is a bounded prefix of it. Two failures with the same hash had byte-identical
    responses even when their previews are indistinguishable, which is exactly
    the case a preview alone cannot settle.
    """

    response_sha256: str | None = None
    raw_response_preview: str | None = None
    finish_reason: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    provider_latency_ms: int | None = None
    fallback_raw_response_used: bool | None = None
