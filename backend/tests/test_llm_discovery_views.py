"""G4 Discovery View contract (§3–§7) — vocabulary, prompt composition, identity.

The contract has three promises, and each is asserted here directly:

  1. The vocabulary is FROZEN. Four views, no fifth, and no free-text focus: a
     caller names a view, and an unknown name is refused rather than absorbed.
  2. The four views share ONE prompt contract and differ only in scientific
     focus — so a change to the JSON schema cannot reach one view and miss
     another, and a change to one view's science cannot alter another's.
  3. A view is written onto the run it produced, in a shape a reader can resolve
     back to the view without knowing the encoding.

No database and no provider is touched by this file: these are the guarantees
that must hold before any run exists.
"""
from __future__ import annotations

import pytest

from app.llm_discovery_views import (
    CIRCUIT_BOUNDARY_RULE,
    DISCOVERY_VIEWS,
    GENERAL_DISCOVERY,
    RECALL_FIRST_RULE,
    STRATEGY_FAMILY,
    STRATEGY_VERSION,
    VIEW_SPECS,
    InvalidDiscoveryView,
    is_discovery_view,
    resolve_discovery_view,
    strategy_identifier,
    view_of_strategy_identifier,
    view_provenance,
)
from app.prompts.llm_discovery_prompt import PROMPT_KEY, PROMPT_VERSION, SYSTEM_PROMPT
from app.prompts.llm_discovery_views import build_view_instruction, build_view_prompt
from app.schemas.llm_discovery import LlmDiscoveryInput

SEED = LlmDiscoveryInput(
    seed_entity_id="NGIQ-BR-00001605",
    seed_name_en="CA3 (Hippocampus) left",
    seed_granularity_level="G4_MICROSTRUCTURAL_FINE",
    seed_hemisphere="left",
    species_taxon_id="9606",
)


# ===========================================================================
# §19.1 — the four view enums are exact
# ===========================================================================
def test_1_the_view_vocabulary_is_exactly_the_four_frozen_views():
    assert DISCOVERY_VIEWS == (
        "NAMED_CLASSIC_CIRCUITS",
        "LOCAL_INTRINSIC_CIRCUITS",
        "AFFERENT_CIRCUITS",
        "EFFERENT_CIRCUITS",
    )
    # No E/F/G slipped in, and every declared view has a spec.
    assert set(VIEW_SPECS) == set(DISCOVERY_VIEWS)
    for view, spec in VIEW_SPECS.items():
        assert spec.view == view
        assert spec.goal and spec.focus and spec.must_not


def test_1b_the_vocabulary_module_holds_no_model_and_no_prompt_text():
    """§17 — a view selects a QUESTION, never a model, and never its own prompt."""
    from pathlib import Path

    import app.llm_discovery_views as module

    source = Path(module.__file__).read_text(encoding="utf-8")
    for forbidden in ("deepseek", "kimi", "moonshot", "gpt", "claude",
                      "max_tokens", "temperature", "reasoning_effort"):
        assert forbidden not in source.lower(), forbidden


# ===========================================================================
# §19.2 — an invalid view is rejected
# ===========================================================================
#: Blank input is NOT here: silence means legacy (test_2b), and only a NAMED
#: view can be wrong. These are all names the server does not implement.
@pytest.mark.parametrize(
    "bad",
    ["named_classic_circuits", "NAMED_CLASSIC", "FUNCTION_ASSOCIATED",
     "NEUROMODULATORY", "ALIAS_HISTORICAL", "AFFERENT", "circuits", "'; DROP TABLE"],
)
def test_2_an_unknown_view_is_refused_never_absorbed(bad):
    with pytest.raises(InvalidDiscoveryView) as excinfo:
        resolve_discovery_view(bad)
    assert excinfo.value.code == "INVALID_DISCOVERY_VIEW"
    assert excinfo.value.value == bad.strip()


def test_2b_only_the_absent_body_and_the_explicit_general_sentinel_mean_legacy():
    """§8 — silence is legacy; a near-miss name is an ERROR, not a fallback."""
    assert resolve_discovery_view(None) is None
    assert resolve_discovery_view("") is None
    assert resolve_discovery_view("  ") is None
    assert resolve_discovery_view(GENERAL_DISCOVERY) is None
    # A view-shaped string that is not a view must NOT quietly become legacy.
    with pytest.raises(InvalidDiscoveryView):
        resolve_discovery_view("GENERAL_DISCOVERY_V2")
    assert is_discovery_view(GENERAL_DISCOVERY) is False


# ===========================================================================
# §19.5 / §19.6 — distinct scientific focus, shared scientific boundary
# ===========================================================================
def test_5_each_view_builds_a_distinct_scientific_focus():
    instructions = {v: build_view_instruction(v) for v in DISCOVERY_VIEWS}
    # Pairwise distinct: no two views produce the same instruction.
    assert len(set(instructions.values())) == len(DISCOVERY_VIEWS)
    # Each names its own view, so a transcript can be attributed to one view.
    for view, text in instructions.items():
        assert view in text
        # ...and not any OTHER view's id by accident.
        for other in DISCOVERY_VIEWS:
            if other != view:
                assert other not in text


@pytest.mark.parametrize(
    ("view", "required", "forbidden"),
    [
        ("NAMED_CLASSIC_CIRCUITS", ("named", "established", "classic"),
         ("recurrent circuit", "autoassociative")),
        ("LOCAL_INTRINSIC_CIRCUITS", ("local", "intrinsic", "recurrent"),
         ("upstream region",)),
        ("AFFERENT_CIRCUITS", ("input", "receiv"), ("downstream region",)),
        ("EFFERENT_CIRCUITS", ("output", "origin"), ("upstream region",)),
    ],
)
def test_5b_the_focus_says_what_it_is_for(view, required, forbidden):
    text = build_view_instruction(view).lower()
    for word in required:
        assert word in text, f"{view} must emphasise {word!r}"
    for word in forbidden:
        assert word not in text, f"{view} must not lean on {word!r}"


@pytest.mark.parametrize("view", DISCOVERY_VIEWS)
def test_6_every_view_keeps_the_circuit_scientific_boundary(view):
    text = build_view_instruction(view)
    # The hard rule is present in EVERY view, not just the ones that invite it.
    assert CIRCUIT_BOUNDARY_RULE in text
    assert RECALL_FIRST_RULE in text
    lowered = text.lower()
    assert "projection" in lowered and "not a circuit" in lowered
    assert "do not" in lowered
    # Recall may not be bought by weakening what a circuit is.
    assert "confidence" in lowered


@pytest.mark.parametrize("view", DISCOVERY_VIEWS)
def test_6b_the_view_block_never_restates_the_shared_contract(view):
    """§6 — the schema/local-id/species contract stays in ONE place."""
    block = build_view_instruction(view)
    for shared in ("schema_version", "local_id", "species_context", "source_hints",
                   "topology_hint", "region_refs"):
        assert shared not in block, f"{shared} belongs to the shared prompt"


def test_5c_each_view_carries_its_own_prohibitions():
    for view, spec in VIEW_SPECS.items():
        block = build_view_instruction(view)
        for prohibition in spec.must_not:
            assert prohibition in block, (view, prohibition)


# ===========================================================================
# §6 — composition, not duplication
# ===========================================================================
def test_7_a_view_prompt_extends_the_frozen_prompt_without_changing_it():
    base = build_view_prompt(SEED, None)
    assert base["system_prompt"] == SYSTEM_PROMPT, "legacy must be byte-identical"
    assert base["prompt_key"] == PROMPT_KEY
    assert base["prompt_version"] == PROMPT_VERSION

    for view in DISCOVERY_VIEWS:
        p = build_view_prompt(SEED, view)
        # The frozen prompt is still there, unmodified, as a prefix.
        assert p["system_prompt"].startswith(SYSTEM_PROMPT.rstrip())
        assert build_view_instruction(view) in p["system_prompt"]
        # Identity is shared: four views are one prompt contract.
        assert p["prompt_key"] == PROMPT_KEY
        assert p["prompt_version"] == PROMPT_VERSION
        # The USER side is the world, and the world does not change per view.
        assert p["user_prompt"] == base["user_prompt"]


def test_7b_the_view_block_is_the_only_difference_between_two_views():
    a = build_view_prompt(SEED, "AFFERENT_CIRCUITS")
    b = build_view_prompt(SEED, "EFFERENT_CIRCUITS")
    assert a["user_prompt"] == b["user_prompt"]
    assert a["prompt_key"] == b["prompt_key"]
    assert a["prompt_version"] == b["prompt_version"]
    assert a["system_prompt"] != b["system_prompt"]


def test_7c_an_unknown_view_cannot_be_composed():
    with pytest.raises(InvalidDiscoveryView):
        build_view_instruction("NOT_A_VIEW")
    with pytest.raises(InvalidDiscoveryView):
        build_view_prompt(SEED, "NOT_A_VIEW")


# ===========================================================================
# §19.10 — the run can be read back to its view
# ===========================================================================
def test_10_the_stored_strategy_identifier_resolves_back_to_its_view():
    for view in DISCOVERY_VIEWS:
        identifier = strategy_identifier(view)
        assert identifier == f"{STRATEGY_VERSION}/{view}"
        assert view_of_strategy_identifier(identifier) == view


@pytest.mark.parametrize(
    "foreign",
    [None, "", "LLM_DISCOVERY_SINGLE_PASS_V1",
     "BRAIN_REGION_LITERATURE_MVP_V1",
     f"{STRATEGY_VERSION}/NOT_A_VIEW", f"{STRATEGY_VERSION}/", "SOMETHING/AFFERENT_CIRCUITS"],
)
def test_10b_a_foreign_or_malformed_identifier_is_not_a_view(foreign):
    """An unreadable provenance must yield None, never a guess."""
    assert view_of_strategy_identifier(foreign) is None


def test_10c_the_structured_provenance_names_the_view_and_its_family():
    for view in DISCOVERY_VIEWS:
        prov = view_provenance(view)
        assert prov == {
            "discovery_view": view,
            "strategy_family": STRATEGY_FAMILY,
            "strategy_version": STRATEGY_VERSION,
        }


def test_10d_a_legacy_run_records_no_view_at_all():
    """§8 — absence is absence: no empty provenance pretending to be a view run."""
    assert view_provenance(None) is None
