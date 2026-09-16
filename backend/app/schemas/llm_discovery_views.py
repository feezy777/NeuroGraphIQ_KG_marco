"""Request contract for a view-scoped LLM Discovery run (§7).

One field. A caller may name a VIEW; it may not name a prompt, a system
instruction, a model, a provider, a prompt version or a schema version. Those
belong to the server, and the way to keep them there is to make them
unrepresentable rather than merely undocumented.

``extra="forbid"`` is that guarantee, not a style choice: a request carrying
``{"discovery_view": "...", "model": "deepseek-reasoner"}`` is REJECTED with 422
instead of being accepted with the extra key ignored. An ignored key is worse
than a rejected one — the caller believes it took effect, and provenance would
then record a model the server never used.

The schema deliberately does not enumerate the view values: that vocabulary is
frozen in ``app.llm_discovery_views``, and a second copy here (a ``Literal`` or
an ``Enum``) would be a second authority that could drift from it. An unknown
view is therefore rejected by the service with code ``INVALID_DISCOVERY_VIEW``.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class LlmDiscoveryViewExecuteRequest(BaseModel):
    """The body of a discovery execute request. Omit it entirely for legacy.

    ``None`` — an absent body, an empty body, or an explicit null — means the
    frozen single-pass behaviour. It does NOT mean "pick a view for me": the old
    entry point must stay semantically distinguishable from a view run.
    """

    model_config = ConfigDict(extra="forbid")

    discovery_view: str | None = None

    #: Continue an EARLIER run of this same view: the new run is told what that
    #: view already found, so it looks for omissions instead of re-answering.
    #:
    #: Only the run's ID travels. The already-discovered circuits are read
    #: server-side from the authoritative candidate rows of every completed run
    #: of this seed+view — a client cannot supply, extend or trim that list, and
    #: `extra="forbid"` makes an attempt a 422 rather than a silent no-op. The
    #: round number is likewise derived by the server, never requested.
    continuation_from_run_id: str | None = None
