"""Compose the frozen discovery prompt with a Discovery View's search focus (§6).

The base prompt is NOT copied, parameterised or forked. ``build_llm_discovery_prompt``
stays the single author of the schema, the local-id contract, the species
contract and the circuit structure rules; this module appends a scientific focus
to its system side and returns the same four keys unchanged.

    base system_prompt            (frozen, untouched)
      + RECALL_FIRST_RULE         (shared by all four views)
      + CIRCUIT_BOUNDARY_RULE     (shared by all four views)
      + <view>.focus              (the only part that differs)
      + <view>.must_not           (the over-reach this view invites)

Composition rather than four prompts means a change to the JSON contract reaches
every view at once, and a change to one view's science cannot silently alter
another's. The user prompt carries the seed and is identical across views — two
views differ ONLY in what they are asked to look for, never in what they are
told about the world.

The legacy path (no view) returns the base prompt byte-for-byte, so the existing
single-pass run is provably unaffected.
"""
from __future__ import annotations

from app.llm_discovery_views import (
    CIRCUIT_BOUNDARY_RULE,
    RECALL_FIRST_RULE,
    VIEW_SPECS,
    InvalidDiscoveryView,
)
from app.prompts.llm_discovery_prompt import build_llm_discovery_prompt
from app.schemas.llm_discovery import LlmDiscoveryInput

#: Marker so a reader (and a test) can find where the frozen prompt ends.
_VIEW_BLOCK_HEADER = "DISCOVERY VIEW — SEARCH FOCUS"


def build_view_instruction(discovery_view: str) -> str:
    """The system-prompt block for one view. Pure function.

    Raises InvalidDiscoveryView for an unknown view: this is the second and last
    place that decides what a view may be, and it must not accept a string the
    vocabulary module would reject.
    """
    spec = VIEW_SPECS.get(discovery_view)
    if spec is None:
        raise InvalidDiscoveryView(discovery_view)

    prohibitions = "\n".join(f"  * Do NOT return {item}." for item in spec.must_not)
    return (
        f"{_VIEW_BLOCK_HEADER}: {spec.view}\n"
        f"Scientific goal: {spec.goal}.\n\n"
        f"{RECALL_FIRST_RULE}\n"
        f"{CIRCUIT_BOUNDARY_RULE}\n"
        f"{spec.focus}\n"
        f"SPECIFIC TO THIS VIEW — do not:\n{prohibitions}\n"
    )


def build_view_prompt(seed: LlmDiscoveryInput, discovery_view: str | None) -> dict[str, str]:
    """The prompt parts for one run, with the view focus when there is one.

    ``None`` returns the frozen prompt unchanged — the legacy single-pass
    contract, byte-for-byte, which is what keeps the old entry point working.
    """
    prompt = build_llm_discovery_prompt(seed)
    if discovery_view is None:
        return prompt
    return {
        **prompt,
        "system_prompt": (
            prompt["system_prompt"].rstrip() + "\n\n" + build_view_instruction(discovery_view)
        ),
    }
