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

#: Marker for the continuation block, appended after the view block.
_CONTINUATION_HEADER = "CONTINUATION PASS — FIND WHAT WAS MISSED"


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


def build_continuation_block(already: tuple[str, ...]) -> str:
    """The extra system-prompt block for a continuation pass.

    Appended AFTER the view block, so the model still knows which question it is
    asking and under which scientific definition — the continuation narrows the
    SEARCH, it never widens what may be called a circuit.

    The list is deliberately names only, and deliberately deduplicated by a
    blunt normalization: its job is to stop the model re-deriving what earlier
    passes already produced, not to be a scientific inventory. The raw candidate
    rows are untouched by that deduplication.
    """
    listed = "\n".join(f"  * {name}" for name in already) or "  * (none recorded)"
    return (
        f"{_CONTINUATION_HEADER}\n"
        "You are performing a continuation discovery pass. Earlier passes asked "
        "this same question about this same brain region.\n\n"
        "Already discovered for this region and this discovery view:\n"
        f"{listed}\n\n"
        "Your task is to find what those earlier passes MISSED.\n"
        "  * Do NOT merely repeat the items above. A list that restates them is a\n"
        "    failed continuation, however long it is.\n"
        "  * Search specifically for ADDITIONAL DISTINCT circuit concepts that\n"
        "    may have been omitted previously.\n"
        "  * Search the less obvious places: less prominent concepts, alternative\n"
        "    literature traditions and historical descriptions, and circuit\n"
        "    contexts that cross functional systems (development, pathology,\n"
        "    plasticity, comparative anatomy) where a circuit has a genuinely\n"
        "    distinct usage.\n"
        "  * Alternative names may still be returned, but ONLY when they\n"
        "    plausibly represent a scientifically distinct usage or genuinely\n"
        "    unresolved terminology. A pure synonym of an item above is not a new\n"
        "    discovery.\n\n"
        "THE SCIENTIFIC DEFINITION DOES NOT CHANGE. Do not lower the definition of\n"
        "a circuit in order to produce more results. A short continuation that\n"
        "finds nothing new is an honest and acceptable answer; a padded one is\n"
        "not. Projection != Connection != Pathway != Circuit, exactly as stated\n"
        "above.\n"
    )


def build_view_prompt(
    seed: LlmDiscoveryInput,
    discovery_view: str | None,
    already_discovered: tuple[str, ...] | None = None,
) -> dict[str, str]:
    """The prompt parts for one run, with the view focus when there is one.

    ``None`` returns the frozen prompt unchanged — the legacy single-pass
    contract, byte-for-byte, which is what keeps the old entry point working.

    ``already_discovered`` adds the continuation block. It is only meaningful
    with a view (a continuation continues a VIEW), and an empty list is treated
    as no continuation at all: a first pass has nothing to exclude, and emitting
    an empty exclusion list would tell the model something untrue.
    """
    prompt = build_llm_discovery_prompt(seed)
    if discovery_view is None:
        return prompt
    system_prompt = (
        prompt["system_prompt"].rstrip() + "\n\n" + build_view_instruction(discovery_view)
    )
    if already_discovered:
        system_prompt = system_prompt.rstrip() + "\n\n" + build_continuation_block(
            already_discovered
        )
    return {**prompt, "system_prompt": system_prompt}
