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
from app.services.llm_discovery_continuation_service import normalize_circuit_name

#: Marker so a reader (and a test) can find where the frozen prompt ends.
_VIEW_BLOCK_HEADER = "DISCOVERY VIEW — SEARCH FOCUS"

#: Marker for the continuation block, appended after the view block.
_CONTINUATION_HEADER = "CONTINUATION PASS — FIND WHAT WAS MISSED"

#: Bound on the historical exclusion list, per View.
#:
#: Listing EVERY historical name made the model perform an exhaustive
#: set-difference against a list that grows without bound. At 431 names one A
#: round spent its entire 65 536-token output budget on reasoning and emitted no
#: content at all — the failure was in the reasoning, not in the context window.
#:
#: Recall First does not ask a continuation for perfect global deduplication:
#: overlap is resolved by novelty assessment and, later, by canonicalization.
#: A representative subset therefore loses nothing that matters, and the full
#: history stays in the database, where every downstream reader still sees it.
_EXCLUSION_MAX = 120
#: Of the bound: the most recent names, plus an evenly spread sample of older
#: ones. Recency matters because the newest rounds are the ones the next round
#: is most likely to repeat; the sample preserves coverage of the deep history.
_EXCLUSION_RECENT = 80
_EXCLUSION_SAMPLED = 40


def _evenly_spaced(items: list[str], count: int) -> list[str]:
    """``count`` names spread evenly across ``items``, deterministically.

    Integer arithmetic and no randomness, so the same history produces the same
    exclusion list on every round and in every process. Index 0 is always
    included: the point of sampling is COVERAGE, so the oldest history must be
    represented rather than dropped for being old.
    """
    total = len(items)
    if count >= total:
        return list(items)
    return [items[(index * total) // count] for index in range(count)]


def bounded_exclusion_names(names: tuple[str, ...]) -> tuple[tuple[str, ...], int]:
    """Return ``(shown, total)`` for one View's historical circuit names.

    ``total`` is the number of DISTINCT names this View has produced — what the
    prompt reports as already discovered, never the size of the subset shown.
    It is not the same number as the run's ``already_discovered_circuit_count``,
    which counts candidate ROWS and is written elsewhere, unchanged.

    Uniqueness uses the frozen prompt-only normalization, so two spellings of
    one circuit occupy one slot in the bound rather than two.
    """
    ordered: list[str] = []
    seen: set[str] = set()
    for name in names:
        key = normalize_circuit_name(name)
        if not key or key in seen:
            continue
        seen.add(key)
        ordered.append(name)

    total = len(ordered)
    if total <= _EXCLUSION_MAX:
        return tuple(ordered), total

    recent = ordered[-_EXCLUSION_RECENT:]
    older = ordered[:-_EXCLUSION_RECENT]
    sampled = _evenly_spaced(older, _EXCLUSION_SAMPLED)
    # Sampled first, then recent: the block reads oldest-representative to
    # newest, which is also the order the history itself arrived in.
    return tuple(sampled + recent), total


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

    The list is also BOUNDED — see ``bounded_exclusion_names``. The block says
    so out loud, because a model that believes it is looking at the whole
    history will spend its reasoning trying to prove novelty against history it
    cannot see, which is exactly the round that produced no answer at all.
    """
    shown, total = bounded_exclusion_names(already)
    listed = "\n".join(f"  * {name}" for name in shown) or "  * (none recorded)"
    if total > len(shown):
        history_line = (
            f"{total} circuit candidates have already been discovered for this "
            f"region and this discovery view.\n"
            f"The {len(shown)} names below are REPRESENTATIVE, not exhaustive: the "
            f"most recent, plus an evenly spread sample of the older ones.\n"
        )
    else:
        history_line = (
            f"{total} circuit candidates have already been discovered for this "
            f"region and this discovery view. All of them are listed below.\n"
        )
    return (
        f"{_CONTINUATION_HEADER}\n"
        "You are performing a continuation discovery pass. Earlier passes asked "
        "this same question about this same brain region.\n\n"
        f"{history_line}\n"
        f"{listed}\n\n"
        "Your task is to find ADDITIONAL DISTINCT circuit concepts.\n"
        "  * Prioritise concepts NOT represented by the names above.\n"
        "  * Do NOT try to prove novelty against history that is not shown. Some\n"
        "    overlap with the OLDER history is expected and acceptable — novelty\n"
        "    assessment and canonical review resolve overlap downstream, not\n"
        "    here. Spending reasoning to rule out candidates you cannot see is a\n"
        "    wasted round.\n"
        "  * Do still avoid obvious duplication with the names ABOVE: restating\n"
        "    one of them is not a new discovery.\n"
        "  * Search the less obvious places: less prominent concepts, alternative\n"
        "    literature traditions and historical descriptions, and circuit\n"
        "    contexts that cross functional systems (development, pathology,\n"
        "    plasticity, comparative anatomy) where a circuit has a genuinely\n"
        "    distinct usage.\n"
        "  * Alternative names may still be returned, when they plausibly\n"
        "    represent a scientifically distinct usage or genuinely unresolved\n"
        "    terminology.\n\n"
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
