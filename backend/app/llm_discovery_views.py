"""Frozen Discovery View vocabulary — the one authority for WHICH question a run asks.

Why this module exists
----------------------
`llm_model_policy` answers *which model*; this answers *which question*. A
Discovery View is a server-owned search focus: it changes what the model is
asked to look for, and nothing else. The caller may name a view and may name
nothing else — not the prompt, not the model, not the version.

The window is deliberately narrow. Exactly four views exist, they are frozen
here, and there is no route that accepts a view the module does not declare.
A free-text "focus" would be a client-authored prompt wearing a parameter's
clothes, and it would make two runs with the same recorded view incomparable.

What a view is NOT
------------------
A view is not a different prompt. The frozen `knowledge_production.llm_discovery`
contract — its JSON schema, its local-id contract, its species contract and its
circuit structure rules — is shared by every view and is not restated here. A
view contributes ONE thing: a scientific focus block appended to the system
prompt. Four copies of a 441-line prompt would be four things to keep in step.

Scientific boundaries are NOT view-specific
-------------------------------------------
``RECALL_FIRST_RULE`` and ``CIRCUIT_BOUNDARY_RULE`` are common to all four views
and are therefore stated once, here, rather than repeated per view. Recall is
raised by asking for more distinct concepts — never by lowering the bar for what
counts as one. ``confidence`` continues to mean *model discovery confidence*: it
is not evidence quality and not a probability that the circuit is real.

This module imports nothing (no httpx, no SQLAlchemy), so schemas, services and
the prompt layer can all share the vocabulary without pulling a transport into
their import graph.
"""
from __future__ import annotations

from dataclasses import dataclass

#: The DEFAULT a caller gets by saying nothing. It is NOT a fifth scientific
#: view: it means "the frozen single-pass behaviour", unchanged since P0-4B, and
#: a run that carries it records no view at all. Keeping it distinct is what
#: stops the legacy button from silently becoming one of A/B/C/D.
GENERAL_DISCOVERY = "GENERAL_DISCOVERY"

#: The four views this pilot may run, in run order. Frozen: adding E/F/G is a
#: deliberate change to this tuple, not a value a caller can invent.
DISCOVERY_VIEWS: tuple[str, ...] = (
    "NAMED_CLASSIC_CIRCUITS",
    "LOCAL_INTRINSIC_CIRCUITS",
    "AFFERENT_CIRCUITS",
    "EFFERENT_CIRCUITS",
)

#: Written to ``knowledge_discovery_runs.query_strategy_version`` as
#: ``"<STRATEGY_VERSION>/<VIEW>"``. The version alone would not identify the
#: view, and the view alone would lose which strategy produced it; the run read
#: DTO already exposes this column, so both facts stay readable with no schema
#: change and no migration.
#:
#: WIDTH IS A HARD CONSTRAINT, not a style preference. That column is
#: ``character varying(32)`` and is NOT being widened, so the identifier must fit
#: inside it — the first live run failed with `StringDataRightTruncation` because
#: a 44-character prefix made every view's identifier too long. Hence the compact
#: ``G4HR1`` form: it is a durable version tag for the G4 high-recall strategy, and
#: ``G4HR1/LOCAL_INTRINSIC_CIRCUITS`` is the longest identifier this vocabulary can
#: produce at 30 characters. The full, human-readable strategy semantics live in
#: ``provenance_json`` (an unbounded jsonb column), which is why shortening this
#: token loses no information. See ``query_strategy_version_width_ok`` and its
#: test: expanding this prefix or a view name past the column width must fail
#: loudly rather than at runtime.
STRATEGY_VERSION = "G4HR1"

#: ``query_strategy_version`` is ``character varying(32)``. Mirrored here so the
#: vocabulary can prove its own output fits, instead of discovering it in
#: production.
QUERY_STRATEGY_VERSION_MAX_LENGTH = 32

#: The family a view run belongs to. A second family (a different granularity
#: policy, say) would be a second value here, not a rewrite of the first.
STRATEGY_FAMILY = "G4_HIGH_RECALL_V1"

_SEPARATOR = "/"


class InvalidDiscoveryView(ValueError):
    """The caller named a view this server does not implement.

    A REQUEST fault, not a discovery one: nothing was read, no run exists and no
    model was called. Callers map it to 422 with code ``INVALID_DISCOVERY_VIEW``.
    """

    code = "INVALID_DISCOVERY_VIEW"

    def __init__(self, value: str) -> None:
        super().__init__(
            f"unknown discovery_view '{value}'; expected one of "
            + ", ".join(DISCOVERY_VIEWS)
        )
        self.value = value


@dataclass(frozen=True)
class DiscoveryViewSpec:
    """One view's scientific identity, as prose the model reads.

    ``goal`` is what the view is FOR — it is quoted in the docstring of the run
    that used it. ``focus`` is the instruction the model receives. ``must_not``
    lists the specific over-reach this view is most likely to commit, stated as
    prohibitions because "prefer X" does not stop a model from also doing Y.
    """

    view: str
    goal: str
    focus: str
    must_not: tuple[str, ...]


#: The Recall-First rule (§5). One statement, shared by all four views: it is a
#: property of this pilot, not of any single search focus.
RECALL_FIRST_RULE = """\
RECALL-FIRST SEARCH (this overrides any instinct to be conservative):
  * Enumerate as many PLAUSIBLE DISTINCT circuit concepts as you can justify.
    A short list is a failure of this task, not a sign of rigour.
  * Preserve ALTERNATIVE concepts that compete with each other. If two schools
    describe the same anatomy differently, return BOTH rather than choosing.
  * Include alternative terminology where it is genuinely used (a synonym, an
    eponym, a translation). An alias is a second candidate, not a duplicate to
    be resolved here.
  * Do NOT merge concepts merely because they share regions or overlap.
  * Do NOT collapse different granularities into one item.
  * Do NOT deduplicate. An unresolved duplicate is cheap; a destroyed
    distinction is not. Resolution happens in review, not in discovery.
"""

#: The hard scientific boundary (§5), also shared. Recall raises the NUMBER of
#: candidates; it never lowers what a candidate must BE. Without this paragraph
#: "high recall" degrades into "call every projection a circuit".
CIRCUIT_BOUNDARY_RULE = """\
WHAT COUNTS AS A CIRCUIT (unchanged by the recall instruction above):
  * Projection != Connection != Pathway != Circuit. These are four different
    claims and must not be promoted into one another.
  * A single projection is NOT a circuit. A single tract is NOT a circuit. An
    isolated pathway is NOT a circuit.
  * A circuit must carry enough structure to be a circuit: multiple components
    with a defined arrangement (a chain, a loop, a recurrent arrangement, a
    convergence, or a named multi-synapse organisation).
  * Returning MORE items never licenses returning WEAKER ones. If the only
    honest answer for an item is "one connection", it is a connection — put it
    in `connections`, not in `circuits`.
  * `confidence` means the model's DISCOVERY confidence (how sure you are this
    circuit concept is correctly identified and correctly attributed to the
    seed). It is NOT evidence quality and NOT the probability that the circuit
    is scientifically true.
"""


VIEW_SPECS: dict[str, DiscoveryViewSpec] = {
    "NAMED_CLASSIC_CIRCUITS": DiscoveryViewSpec(
        view="NAMED_CLASSIC_CIRCUITS",
        goal=(
            "circuits that carry an established NAME in the literature and in "
            "which this seed is a genuine component"
        ),
        focus="""\
SEARCH FOCUS — NAMED / CLASSIC CIRCUITS.

Look for circuits that are NAMED or otherwise ESTABLISHED in the neuroscience
literature as a circuit, loop or network circuit, and in which the seed is a
genuine component (not merely adjacent to it).

  * Prefer concepts a specialist would recognise by name or by a standard
    description: classical circuit concepts, eponymous loops, textbook circuits,
    canonical network motifs of this region.
  * The seed must be a REAL component of the circuit you return — an origin, a
    relay, a target or a recurring member. "This circuit exists near the seed"
    is not enough.
  * Return MULTIPLE distinct named circuit concepts when more than one applies.
    Different named circuits that share the seed are different candidates.
""",
        must_not=(
            "a single projection, tract or isolated pathway dressed up as a "
            "named circuit",
            "a circuit the seed merely sits near, rather than belongs to",
            "inventing a plausible-sounding name for an unnamed structure",
        ),
    ),
    "LOCAL_INTRINSIC_CIRCUITS": DiscoveryViewSpec(
        view="LOCAL_INTRINSIC_CIRCUITS",
        goal="local, fine-grained intrinsic circuits that belong to this seed itself",
        focus="""\
SEARCH FOCUS — LOCAL / INTRINSIC CIRCUITS.

Look for circuits that are INTERNAL to the seed's own level of granularity: the
seed's local microcircuitry and its own recurrent organisation.

  * Recurrent circuits, intrinsic loops, local microcircuits, autoassociative
    arrangements, local excitatory/inhibitory circuit architecture, local
    feed-forward and feed-back motifs — as long as they are a property of THIS
    structure at THIS granularity.
  * The circuit's components should be at or below the seed's granularity.
    Naming the seed's parent structure as a component is a granularity error.
  * Return multiple distinct local circuit concepts when the region supports
    more than one. Competing descriptions of the same local architecture are
    distinct candidates at this stage.
""",
        must_not=(
            "copying in every parent-level circuit simply because the seed "
            "belongs to that larger structure",
            "treating the seed's membership in a bigger structure as a local "
            "intrinsic circuit",
            "a single local projection treated as a local circuit",
        ),
    ),
    "AFFERENT_CIRCUITS": DiscoveryViewSpec(
        view="AFFERENT_CIRCUITS",
        goal=(
            "whole circuits in which this seed is a key receiving, relay or "
            "input target node"
        ),
        focus="""\
SEARCH FOCUS — AFFERENT CIRCUITS (the seed as an INPUT / RELAY target).

Look for complete circuits in which the seed is a KEY RECEIVING NODE, a relay,
or an input target — circuits that exist in order to deliver something INTO this
structure and do more than that.

  * The shape to look for is: upstream region(s) -> [relay] -> seed -> onward
    circuit structure. The seed is on the receiving side of the circuit.
  * The circuit must contain ENOUGH STRUCTURE to be a circuit — an upstream
    arrangement, a relay, or an onward continuation. A single incoming
    connection is not a circuit.
  * Return multiple distinct afferent circuits when the seed receives from more
    than one organised system. Distinct sources with distinct arrangements are
    distinct candidates.
""",
        must_not=(
            "creating a circuit merely because some region A projects to the "
            "seed (A -> seed is one projection, not a circuit)",
            "an incoming connection with no further structure",
            "describing the seed's own local microcircuitry, which is a "
            "different view",
        ),
    ),
    "EFFERENT_CIRCUITS": DiscoveryViewSpec(
        view="EFFERENT_CIRCUITS",
        goal=(
            "whole circuits in which this seed is a key output, origin or "
            "upstream component"
        ),
        focus="""\
SEARCH FOCUS — EFFERENT CIRCUITS (the seed as an OUTPUT / ORIGIN node).

Look for complete circuits in which the seed is a KEY OUTPUT NODE, an origin, or
an upstream component — circuits that begin here and go somewhere with structure.

  * The shape to look for is: seed -> downstream region(s) -> onward circuit
    structure. The seed is on the sending side of the circuit.
  * The circuit must contain ENOUGH STRUCTURE to be a circuit — a downstream
    arrangement, a relay, or a return path. A single outgoing connection is not
    a circuit.
  * Return multiple distinct efferent circuits when the seed drives more than
    one organised system. Distinct targets with distinct arrangements are
    distinct candidates.
""",
        must_not=(
            "treating seed -> B as a circuit (that is one projection)",
            "an outgoing connection with no further structure",
            "describing the seed's own local microcircuitry, which is a "
            "different view",
        ),
    ),
}


def is_discovery_view(value: str) -> bool:
    """True when ``value`` is one of the four frozen views."""
    return value in DISCOVERY_VIEWS


def resolve_discovery_view(value: str | None) -> str | None:
    """Validate a caller-supplied view. ``None``/empty means the legacy path.

    Returns the view id, or ``None`` for the unchanged single-pass behaviour.
    ``GENERAL_DISCOVERY`` is accepted as an explicit spelling of that same
    default, so a caller may state "no view" rather than imply it by silence.

    Raises InvalidDiscoveryView for anything else — including a view-shaped
    string that is not one of the four, which must never fall through to the
    default and quietly run a different search than the caller asked for.
    """
    if value is None:
        return None
    text = value.strip()
    if not text or text == GENERAL_DISCOVERY:
        return None
    if not is_discovery_view(text):
        raise InvalidDiscoveryView(text)
    return text


def strategy_identifier(view: str) -> str:
    """The value written to ``query_strategy_version`` for a view run."""
    return f"{STRATEGY_VERSION}{_SEPARATOR}{view}"


def query_strategy_version_width_ok(identifier: str) -> bool:
    """True when this identifier fits the ``varchar(32)`` column it is stored in.

    Exposed so the vocabulary can be checked against its own storage limit in a
    test, rather than against a comment: the identifier that overflowed the
    column was produced by this very function, and nothing in the code said so.
    """
    return len(identifier) <= QUERY_STRATEGY_VERSION_MAX_LENGTH


def view_of_strategy_identifier(identifier: str | None) -> str | None:
    """The view a stored ``query_strategy_version`` names, or None.

    The inverse of :func:`strategy_identifier`, so a reader never has to know
    the separator. A value from another strategy family, or a malformed one,
    yields None rather than a guess — an unreadable provenance is not a view.
    """
    if not identifier or not identifier.startswith(STRATEGY_VERSION + _SEPARATOR):
        return None
    view = identifier[len(STRATEGY_VERSION) + len(_SEPARATOR):]
    return view if is_discovery_view(view) else None


def view_provenance(view: str | None) -> dict[str, str] | None:
    """The structured provenance written to ``provenance_json``, or None.

    None for the legacy path so the column is left exactly as it was: a run with
    no view must not acquire an empty provenance object that makes it look like
    a view run whose view went missing.
    """
    if view is None:
        return None
    return {
        "discovery_view": view,
        "strategy_family": STRATEGY_FAMILY,
        "strategy_version": STRATEGY_VERSION,
    }
