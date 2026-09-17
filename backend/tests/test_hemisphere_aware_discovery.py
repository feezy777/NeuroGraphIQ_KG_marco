"""Hemisphere-Aware Discovery V1 — the laterality contract.

Why each piece is worth a test rather than a comment:

  * the resolution TABLE. Laterality is part of a region's identity — `CA3 left
    -> CA1 left` and `CA3 left -> CA1 right` are different scientific claims —
    so a resolution that drifts silently changes what an already-stored
    candidate means.
  * that a side is never INFERRED from the seed. The defect being fixed is a
    guessed side, and the cheapest way to reintroduce it is a convenience
    default in the resolver.
  * that LEGACY payloads stay READABLE and are not reinterpreted. The CA3
    dataset is legacy baseline data by decision, not by accident.
  * that the PROMPT states the rules the contract depends on. A closed
    vocabulary only helps if the model is told the vocabulary, and "never infer
    a side from the seed" is not enforceable by any validator.

Scope of this module: the focused tests this contract change asked for, plus
the connection-endpoint and live-CA3 cases §11/§15 describe. The full suite is
not run from here.

The contract version bump also made every fixture that hard-coded
`schema_version: "1.0"` or the retired free-text `hemisphere` key stale. That
migration is TEST-ONLY and is complete: new fixtures use `hemisphere_context`,
and the one place the legacy key still appears is test_22, which is about
reading data that was already stored — never about producing it.
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

if sys.platform == "win32":  # psycopg async cannot use the Proactor loop
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

BACKEND = Path(__file__).resolve().parents[1]
E2E_DB = os.environ.get("TEST_E2E_DB", "neurographiq_human_brain_v1_e2e")

#: The two seeds the CA3 pools are split across. Named here because §12's claim
#: — pools stay seed-specific — is only meaningful against seeds whose sides
#: actually differ.
LEFT_SEED = "NGIQ-BR-00001605"
RIGHT_SEED = "NGIQ-BR-00001604"

#: §8's table, restated as DATA in the test rather than read from the code under
#: test. A table copied from the implementation cannot detect the implementation
#: changing; these two dicts are the specification.
LEFT_SEED_TABLE = {
    "LEFT": "LEFT",
    "RIGHT": "RIGHT",
    "BILATERAL": "BILATERAL",
    "MIDLINE": "MIDLINE",
    "IPSILATERAL_TO_SEED": "LEFT",
    "CONTRALATERAL_TO_SEED": "RIGHT",
    "UNSPECIFIED": "UNSPECIFIED",
}
RIGHT_SEED_TABLE = {
    "LEFT": "LEFT",
    "RIGHT": "RIGHT",
    "BILATERAL": "BILATERAL",
    "MIDLINE": "MIDLINE",
    "IPSILATERAL_TO_SEED": "RIGHT",
    "CONTRALATERAL_TO_SEED": "LEFT",
    "UNSPECIFIED": "UNSPECIFIED",
}


def _schema():
    from app.schemas import llm_discovery

    return llm_discovery


def _prompt():
    from app.prompts import llm_discovery_prompt

    return llm_discovery_prompt


def _read_service():
    from app.services import llm_candidate_read_service

    return llm_candidate_read_service


def _region(**over: Any) -> dict[str, Any]:
    body: dict[str, Any] = {"local_id": "region_1", "name": "CA1 field of the hippocampus"}
    body.update(over)
    return body


def _row(**over: Any) -> dict[str, Any]:
    """One joined read row, shaped as the shared SQL projection returns it."""
    now = datetime(2026, 9, 17, tzinfo=timezone.utc)
    row: dict[str, Any] = {
        "candidate_id": "NGIQ-DC-00000001",
        "candidate_type": "region",
        "local_id": "region_1",
        "name": "CA1 field of the hippocampus",
        "payload_json": _region(confidence=0.7),
        "confidence": 0.7,
        "status": "PROPOSED",
        "created_at": now,
        "updated_at": now,
        "run_id": uuid.UUID("11111111-2222-3333-4444-555555555555"),
    }
    row.update(over)
    return row


def _seed(**over: Any):
    from app.schemas.llm_discovery import LlmDiscoveryInput

    body: dict[str, Any] = {
        "seed_entity_id": LEFT_SEED,
        "seed_name_en": "CA3 field of the hippocampus",
        "seed_name_zh": "海马 CA3 区",
        "seed_granularity_level": "subregion",
        "seed_hemisphere": "left",
        "species_taxon_id": "9606",
    }
    body.update(over)
    return LlmDiscoveryInput.model_validate(body)


def _flat(text: str) -> str:
    return " ".join(text.split())


# ===========================================================================
# 1-5. The contract: vocabulary, strictness, and where the field lives
# ===========================================================================
def test_01_hemisphere_context_defaults_to_unspecified_and_legacy_stays_readable():
    """Absent means UNSPECIFIED — stated, not repaired into a side."""
    s = _schema()

    parsed = s.RegionCandidate.model_validate(_region())
    assert parsed.hemisphere_context == "UNSPECIFIED"

    # A LEGACY region: every field the old contract had, and no new one. It must
    # still validate, because a historical payload that cannot be read is data
    # loss even when nothing writes it back.
    legacy = {
        "local_id": "region_2",
        "name": "Subiculum",
        "name_en": "Subiculum",
        "name_zh": "下托",
        "confidence": 0.55,
        "species_taxon_id": "9606",
        "relation_to_seed": "AFFERENT",
        "rationale": "Principal output target of CA3.",
    }
    assert s.RegionCandidate.model_validate(legacy).hemisphere_context == "UNSPECIFIED"

    # And through the WHOLE response contract, which is what a run validates.
    data = s.LlmDiscoveryResponse.model_validate(
        {
            "schema_version": s.SCHEMA_VERSION,
            "seed_entity_id": LEFT_SEED,
            "regions": [legacy],
        }
    )
    assert data.regions[0].hemisphere_context == "UNSPECIFIED"


def test_02_every_closed_vocabulary_value_is_accepted_and_the_mirror_tuple_matches():
    """The Literal and its `tuple` mirror are one vocabulary, not two.

    The module's convention elsewhere (REGION_RELATIONS_TO_SEED and friends) is
    a `Literal` plus a tuple restatement, and a restatement that drifts is worse
    than no restatement.
    """
    s = _schema()
    assert s.HEMISPHERE_CONTEXTS == (
        "LEFT",
        "RIGHT",
        "BILATERAL",
        "MIDLINE",
        "IPSILATERAL_TO_SEED",
        "CONTRALATERAL_TO_SEED",
        "UNSPECIFIED",
    )
    from typing import get_args

    assert tuple(get_args(s.HemisphereContext)) == s.HEMISPHERE_CONTEXTS

    for value in s.HEMISPHERE_CONTEXTS:
        parsed = s.RegionCandidate.model_validate(_region(hemisphere_context=value))
        assert parsed.hemisphere_context == value


def test_03_unknown_hemisphere_values_remain_invalid():
    """A near-miss is a REJECTION, not a coerce-to-UNSPECIFIED.

    The live values this vocabulary replaced were exactly the near-misses below.
    Normalising them would have been the smaller diff and the wrong one: it
    would accept an answer the model did not actually give in the vocabulary it
    was asked for, with no way to tell afterwards.
    """
    s = _schema()
    for bad in ("left", "Left", "LEFTISH", "", "SEED_SIDE", "BOTH", "UNKNOWN", "NONE", "L"):
        with pytest.raises(ValidationError):
            s.RegionCandidate.model_validate(_region(hemisphere_context=bad))


def test_04_strictness_was_not_relaxed():
    """The new field is a CONTRACT, not a tolerance."""
    s = _schema()
    for model in (
        s.RegionCandidate,
        s.ConnectionCandidate,
        s.FunctionCandidate,
        s.CircuitCandidate,
        s.LlmDiscoveryResponse,
    ):
        assert model.model_config["extra"] == "forbid", model.__name__

    with pytest.raises(ValidationError):
        s.RegionCandidate.model_validate(_region(invented_field="carries meaning"))

    # The RETIRED free-text field is gone, not tolerated alongside the new one.
    # Two laterality fields would leave a reader choosing between them.
    with pytest.raises(ValidationError):
        s.RegionCandidate.model_validate(_region(hemisphere="left"))


def test_05_laterality_belongs_to_region_candidates_only():
    """§5/§11 — a connection, circuit or function states NO side of its own.

    Its side is a consequence of the regions it references. A laterality field
    on a function would also invite "left memory" as a term, which is not a
    function — it is a function plus a structure.
    """
    s = _schema()
    for model in (s.ConnectionCandidate, s.FunctionCandidate, s.CircuitCandidate):
        assert "hemisphere_context" not in model.model_fields, model.__name__
        assert "resolved_hemisphere" not in model.model_fields, model.__name__

    species_unknown = {"scope": "UNKNOWN", "taxon_ids": []}
    with pytest.raises(ValidationError):
        s.FunctionCandidate.model_validate(
            {
                "local_id": "function_1",
                "label": "Pattern separation",
                "confidence": 0.5,
                "species_context": species_unknown,
                "hemisphere_context": "LEFT",
            }
        )
    with pytest.raises(ValidationError):
        s.CircuitCandidate.model_validate(
            {
                "local_id": "circuit_1",
                "name": "Trisynaptic circuit",
                "confidence": 0.5,
                "species_context": species_unknown,
                "region_refs": ["SEED", "region_1"],
                "hemisphere_context": "LEFT",
            }
        )


# ===========================================================================
# 6-9. The resolver: pure, total, and never inventive
# ===========================================================================
def test_06_left_seed_resolution_table():
    """§8, exactly. A relative value resolves AGAINST the seed's own side."""
    s = _schema()
    for context, expected in LEFT_SEED_TABLE.items():
        assert s.resolve_hemisphere("left", context) == expected, context


def test_07_right_seed_resolution_table():
    """The mirror. Only the two relative values move."""
    s = _schema()
    for context, expected in RIGHT_SEED_TABLE.items():
        assert s.resolve_hemisphere("right", context) == expected, context


def test_08_resolution_never_invents_a_side():
    """The failure mode this whole contract exists to prevent.

    An unresolvable RELATIVE value says UNSPECIFIED. It does not fall back to
    the seed's side (that is the guessed side), and it does not fall back to
    LEFT (that is the historical default that made "left" meaningless). An
    ABSOLUTE value needs no seed and is returned even when the seed has none.
    """
    s = _schema()
    for unknown_seed in (None, "", "   ", "unknown", "bilateral", "midline", "?"):
        assert s.resolve_hemisphere(unknown_seed, "IPSILATERAL_TO_SEED") == "UNSPECIFIED"
        assert s.resolve_hemisphere(unknown_seed, "CONTRALATERAL_TO_SEED") == "UNSPECIFIED"
        assert s.resolve_hemisphere(unknown_seed, "UNSPECIFIED") == "UNSPECIFIED"
        # Absolute claims do not depend on the seed, so they survive its absence.
        assert s.resolve_hemisphere(unknown_seed, "LEFT") == "LEFT"
        assert s.resolve_hemisphere(unknown_seed, "BILATERAL") == "BILATERAL"

    # BILATERAL / MIDLINE are not "a side", so a relative value against them
    # cannot be resolved either.
    for non_lateral_seed in ("bilateral", "midline_unpaired"):
        assert s.resolve_hemisphere(non_lateral_seed, "CONTRALATERAL_TO_SEED") == "UNSPECIFIED"


def test_09_resolution_is_pure_deterministic_and_total():
    """No model call, no I/O, no state — and no input mutated.

    Determinism is the reason this is application logic: an LLM asked to derive
    it again could disagree with itself between rounds and silently change what
    an already-stored candidate means.
    """
    s = _schema()

    # The canonical vocabulary is lowercase ("left"/"right"), the contract's is
    # uppercase; the boundary is normalised here rather than at every caller.
    for seed_spelling in ("left", "LEFT", " Left ", "LeFt"):
        assert s.resolve_hemisphere(seed_spelling, "IPSILATERAL_TO_SEED") == "LEFT"

    for context_spelling in ("ipsilateral_to_seed", " IPSILATERAL_TO_SEED ", "Ipsilateral_To_Seed"):
        assert s.resolve_hemisphere("left", context_spelling) == "LEFT"

    # An absent context is UNSPECIFIED, not an error: legacy payloads reach here.
    assert s.resolve_hemisphere("left", None) == "UNSPECIFIED"
    assert s.resolve_hemisphere("left", "") == "UNSPECIFIED"

    # Total: no input raises, including nonsense that no validator would admit.
    for junk in ("sideways", "L", 3, "LEFT;RIGHT"):
        assert s.resolve_hemisphere("left", junk) == "UNSPECIFIED"

    # Deterministic and side-effect free.
    first = s.resolve_hemisphere("left", "CONTRALATERAL_TO_SEED")
    assert first == s.resolve_hemisphere("left", "CONTRALATERAL_TO_SEED") == "RIGHT"

    # A resolved absolute value is stable under a second pass: the output
    # vocabulary is a subset of the input vocabulary on purpose, so a resolved
    # side can be fed back in without changing meaning.
    assert s.resolve_hemisphere("right", first) == first


# ===========================================================================
# 10-13. The prompt: the rules a validator cannot enforce
# ===========================================================================
def test_10_prompt_states_what_the_seed_IS():
    """§6 — identity, not just a label.

    A model that reads `seed_entity_id` as a label can still reason about the
    hippocampus as a CATEGORY, which is how a bilateral claim gets made about a
    region that was named on one side.
    """
    text = _flat(_prompt().build_user_prompt(_seed()))

    assert f"SEED is exactly this canonical BrainRegion: {LEFT_SEED}" in text
    assert "CA3 field of the hippocampus" in text
    assert "Its granularity is subregion" in text
    assert "Its hemisphere is left." in text
    # The constraint that keeps the seed's side from becoming evidence.
    assert "belongs to the SEED alone" in text


def test_11_prompt_states_the_vocabulary_and_the_no_inference_rule():
    """§7 — the rule is stated in both directions, because only one is obvious.

    "Do not infer left" is easy to obey; "do not infer bilateral" is the one a
    model does by default when it does not know which side was meant.
    """
    system = _flat(_prompt().SYSTEM_PROMPT)

    # Pinned as rule 8, because the seed identity note points the model at
    # "rule 8" by name. Renumbering must fail here rather than leave the prompt
    # cross-referencing the wrong rule.
    assert "8. LATERALITY" in system
    for value in _schema().HEMISPHERE_CONTEXTS:
        assert value in system, value
    assert "NEVER infer a side from the seed" in system
    assert "does NOT make the structures you propose left" in system
    assert "UNSPECIFIED: that is a complete answer, not a missing one" in system
    # Relative values are preferred when the relationship is what is known, and
    # must not be converted into an absolute side.
    assert "Do not convert it into LEFT or RIGHT" in system
    # The containment rule, stated where the model writes a circuit.
    assert "A connection, circuit or function does NOT carry a laterality" in system


def test_12_field_reference_offers_the_enum_and_no_longer_a_free_string():
    """The reference is rendered FROM the contract, so this proves the contract
    is what the model is shown — including the default that makes the field
    omissible without being optional in meaning."""
    definitions = _prompt().build_field_definitions()

    assert (
        "  hemisphere_context: "
        "enum(LEFT|RIGHT|BILATERAL|MIDLINE|IPSILATERAL_TO_SEED|"
        "CONTRALATERAL_TO_SEED|UNSPECIFIED)  default=UNSPECIFIED" in definitions
    )
    # The retired free-text field is not offered anywhere in section B.
    assert "\n  hemisphere:" not in definitions
    # And not on a type that must not have it.
    functions = definitions.split("FunctionCandidate")[1].split("CircuitCandidate")[0]
    assert "hemisphere" not in functions


def test_13_prompt_degrades_honestly_when_the_seed_has_no_side():
    """A seed with no stated side cannot resolve a relative value, and the
    prompt says so instead of leaving the model to assume one."""
    text = _flat(_prompt().build_user_prompt(_seed(seed_hemisphere=None)))

    assert "Its hemisphere is not stated" in text
    assert "no relative laterality can be resolved" in text
    assert "otherwise UNSPECIFIED" in text
    assert "belongs to the SEED alone" not in text


# ===========================================================================
# 14. The contract version, recorded in-band
# ===========================================================================
def test_14_the_contract_version_was_incremented_and_old_responses_are_refused():
    """§16 — the version is ENFORCED, not documented.

    A stored payload is never revalidated, so raising the version costs nothing
    historical; what it buys is that a model answering an older contract is
    refused in-band instead of being read as if it had answered this one.
    """
    s = _schema()
    assert s.SCHEMA_VERSION == "1.1"
    assert s.HEMISPHERE_AWARE_CONTRACT == "hemisphere-aware-v1"

    body = {"seed_entity_id": LEFT_SEED, "regions": [_region()]}
    with pytest.raises(ValidationError, match="unsupported schema_version '1.0'"):
        s.LlmDiscoveryResponse.model_validate({**body, "schema_version": "1.0"})

    assert (
        s.LlmDiscoveryResponse.model_validate(
            {**body, "schema_version": s.SCHEMA_VERSION}
        ).schema_version
        == s.SCHEMA_VERSION
    )

    # The run row records the contract that produced it from the ONE constant,
    # so the stored provenance cannot name a version the response did not have.
    from app.services import llm_discovery_execution_service as execution

    assert execution.SCHEMA_VERSION == s.SCHEMA_VERSION


# ===========================================================================
# 15-17. The read projection
# ===========================================================================
def test_15_read_projection_carries_the_stated_context_and_the_resolved_side():
    """§15 — BOTH values, because they answer different questions.

    `hemisphere_context` is the claim; `resolved_hemisphere` is what it means
    against this seed. A relative claim collapsed into its resolution would lose
    the relationship the model actually asserted.
    """
    read = _read_service()
    item = read._row_to_item(
        _row(payload_json=_region(hemisphere_context="CONTRALATERAL_TO_SEED")),
        LEFT_SEED,
        "left",
    )
    assert item.payload["hemisphere_context"] == "CONTRALATERAL_TO_SEED"
    assert item.resolved_hemisphere == "RIGHT"

    # The public list envelope passes this DTO through unchanged, so the field
    # reaches the API without a second schema that could drop it.
    from app.routers.llm_discovery_candidates import LlmCandidateListResponse

    assert (
        LlmCandidateListResponse.model_fields["items"].annotation
        == list[read.DiscoveryCandidateReadItem]
    )


def test_16_non_region_candidates_have_no_resolved_side():
    """§10 — UNSPECIFIED endpoints do NOT become a left-left connection.

    A connection states no laterality and neither may the read layer: inventing
    one would turn an unknown into a claim, which is the same failure as
    inferring a side from the seed.
    """
    read = _read_service()
    payload = {
        "local_id": "connection_1",
        "source_ref": "region_1",
        "target_ref": "SEED",
        "connection_type": "PROJECTION",
        "confidence": 0.5,
        "species_context": {"scope": "UNKNOWN", "taxon_ids": []},
    }
    for candidate_type in ("connection", "circuit", "function"):
        item = read._row_to_item(
            _row(candidate_type=candidate_type, local_id="x_1", payload_json=payload),
            LEFT_SEED,
            "left",
        )
        assert item.resolved_hemisphere is None, candidate_type


def test_17_legacy_free_text_laterality_is_neither_reinterpreted_nor_backfilled():
    """§13 — historical candidates are baseline data, not work in progress.

    The legacy wording stays visible verbatim in `payload`, and it is NOT
    promoted into the closed vocabulary at read time. Mapping "left" -> LEFT
    would look harmless and would be a backfill: it would put a claim in the new
    field that no model ever made in that vocabulary.
    """
    read = _read_service()
    for legacy_word in ("left", "LEFT", "right", "bilateral"):
        payload = _region(hemisphere=legacy_word, confidence=0.4)
        for seed_side in ("left", "right", None):
            item = read._row_to_item(_row(payload_json=payload), LEFT_SEED, seed_side)
            assert item.resolved_hemisphere == "UNSPECIFIED", (legacy_word, seed_side)
        # Verbatim, and unchanged: the original wording is still readable.
        assert item.payload["hemisphere"] == legacy_word
        assert "hemisphere_context" not in item.payload


# ===========================================================================
# 18. Seed-specificity, against the real seed pair
# ===========================================================================
def _dsn() -> str:
    cfg: dict[str, str] = {}
    env = BACKEND / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                cfg[k.strip()] = v.strip().strip('"').strip("'")
    return "postgresql+psycopg://%s:%s@%s:%s/%s" % (
        cfg.get("POSTGRES_USER"),
        cfg.get("POSTGRES_PASSWORD"),
        cfg.get("POSTGRES_HOST", "127.0.0.1"),
        cfg.get("POSTGRES_PORT", "5432"),
        E2E_DB,
    )


async def _laterality_is_seed_specific() -> None:
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.pool import NullPool

    read = _read_service()
    engine = create_async_engine(_dsn(), poolclass=NullPool)
    try:
        connection = await engine.connect()
    except Exception as exc:  # pragma: no cover - environment dependent
        pytest.skip(f"isolated test database unavailable: {type(exc).__name__}")

    transaction = await connection.begin()
    db = AsyncSession(bind=connection, join_transaction_mode="create_savepoint")
    try:
        if (
            await connection.execute(
                text("SELECT to_regclass('public.discovery_candidates')")
            )
        ).scalar_one() is None:
            pytest.skip("gate7b_016 not applied to the isolated test database")

        rows = (
            await db.execute(
                text(
                    "SELECT e.entity_id, b.hemisphere FROM brain_regions b"
                    " JOIN kg_entities e ON e.entity_pk = b.entity_pk"
                    " WHERE e.entity_id IN (:l, :r)"
                ),
                {"l": LEFT_SEED, "r": RIGHT_SEED},
            )
        ).all()
        sides = {entity_id: hemisphere for entity_id, hemisphere in rows}
        if sides.get(LEFT_SEED) != "left" or sides.get(RIGHT_SEED) != "right":
            pytest.skip(f"seed pair absent or not opposite in this database: {sides}")

        # §12 — the same claim means opposite things against the two pools.
        assert _schema().resolve_hemisphere(sides[LEFT_SEED], "CONTRALATERAL_TO_SEED") == "RIGHT"
        assert _schema().resolve_hemisphere(sides[RIGHT_SEED], "CONTRALATERAL_TO_SEED") == "LEFT"

        # The projection takes the side from the ROW's own seed, so a page read
        # for one seed can never be resolved against the other.
        items = await read.list_candidates_for_seed(db, entity_id=LEFT_SEED)
        assert items, "the left seed has no candidates to project"
        regions = [i for i in items if i.candidate_type == "region"]
        assert regions, "the left seed has no region candidates to project"
        for item in regions:
            assert item.resolved_hemisphere == _schema().resolve_hemisphere(
                "left", item.payload.get("hemisphere_context")
            )
            # No legacy row leaks a side it never stated in this vocabulary.
            if "hemisphere_context" not in item.payload:
                assert item.resolved_hemisphere == "UNSPECIFIED"
                assert "hemisphere" in item.payload
    finally:
        await db.close()
        await transaction.rollback()
        await connection.close()
        await engine.dispose()


def test_18_laterality_is_seed_specific_and_the_real_seeds_are_opposite():
    """The earlier tests prove the mapping; this proves it is WIRED to the seed.

    A resolver that is correct but handed a constant, or a page resolved against
    the wrong seed, passes every pure test above and still mislabels data.
    """
    asyncio.run(_laterality_is_seed_specific())


# ===========================================================================
# 19-20. Connection endpoints (§11) and the live CA3 concepts (§15)
# ===========================================================================
def _regions(*specs: tuple[str, str]) -> dict[str, Any]:
    """local_id -> RegionCandidate, keyed the way the resolver looks them up."""
    s = _schema()
    return {
        local_id: s.RegionCandidate.model_validate(
            _region(local_id=local_id, name="CA1 field of the hippocampus",
                    hemisphere_context=context)
        )
        for local_id, context in specs
    }


def test_19_connection_endpoints_inherit_their_sides_and_never_collapse():
    """§11, both examples: one seed, two connections, two different claims.

    `Left CA3 -> CA1(ipsilateral)` and `Left CA3 -> CA1(contralateral)` are not
    the same connection, and the ONLY thing distinguishing them here is the
    context on the region each one points at.
    """
    s = _schema()
    ipsi = _regions(("region_1", "IPSILATERAL_TO_SEED"))
    contra = _regions(("region_2", "CONTRALATERAL_TO_SEED"))

    assert s.resolve_connection_sides("left", "SEED", "region_1", ipsi) == ("LEFT", "LEFT")
    assert s.resolve_connection_sides("left", "SEED", "region_2", contra) == ("LEFT", "RIGHT")
    # The same two refs against the opposite seed swap, and that is correct:
    # the relative claim is preserved, not the side it happened to mean.
    assert s.resolve_connection_sides("right", "SEED", "region_1", ipsi) == ("RIGHT", "RIGHT")
    assert s.resolve_connection_sides("right", "SEED", "region_2", contra) == ("RIGHT", "LEFT")

    # Direction is semantic for a DIRECTED connection, so the tuple is ordered.
    assert s.resolve_connection_sides("left", "region_1", "SEED", ipsi) == ("LEFT", "LEFT")


def test_20_unspecified_endpoints_stay_unspecified_and_are_never_inherited():
    """§11 last line — the connection case of §8's rule.

    An UNSPECIFIED endpoint must not borrow the seed's side. If it did,
    `Left CA3 -> CA1` (no laterality stated) would be stored as a left-left
    claim, which is precisely the manufactured fact this contract exists to
    prevent — and it would be manufactured on the connection, where the region
    layer can no longer correct it.
    """
    s = _schema()
    bare = _regions(("region_1", "UNSPECIFIED"))
    assert s.resolve_connection_sides("left", "SEED", "region_1", bare) == (
        "LEFT", "UNSPECIFIED",
    )
    assert s.resolve_connection_sides("left", "region_1", "region_9", bare) == (
        "UNSPECIFIED", "UNSPECIFIED",
    )
    # A seed with no side of its own cannot resolve its own endpoint either.
    assert s.resolve_connection_sides(None, "SEED", "region_1", bare) == (
        "UNSPECIFIED", "UNSPECIFIED",
    )


#: §15's three live CA3 concepts, typed the way the contract now requires. The
#: prose stays in `rationale` where a human reads it; the laterality moves into
#: the one field a machine reads.
_CA3_SEED = "NGIQ-BR-00001605"          # CA3 (Hippocampus) left


def _ca3_concepts() -> dict[str, Any]:
    return {
        "schema_version": _schema().SCHEMA_VERSION,
        "seed_entity_id": _CA3_SEED,
        "summary": "CA3 laterality concepts from the live pool.",
        "regions": [
            {   # "Contralateral CA3 commissural circuit"
                "local_id": "region_1", "name": "CA3 (Hippocampus)",
                "hemisphere_context": "CONTRALATERAL_TO_SEED",
                "relation_to_seed": "RECIPROCAL",
                "rationale": "Contralateral CA3 via commissural fibres.",
            },
            {   # "Bilateral entorhinal convergence ... ipsilateral plus crossed
                # perforant path" — ONE concept, TWO participating regions. The
                # pool keeps both sides by keeping two region candidates that
                # share a name and differ only in context; a BILATERAL value on
                # one of them would collapse the two paths into one.
                "local_id": "region_2", "name": "Entorhinal cortex",
                "hemisphere_context": "IPSILATERAL_TO_SEED",
                "relation_to_seed": "AFFERENT",
                "rationale": "Ipsilateral perforant path.",
            },
            {
                "local_id": "region_3", "name": "Entorhinal cortex",
                "hemisphere_context": "CONTRALATERAL_TO_SEED",
                "relation_to_seed": "AFFERENT",
                "rationale": "Crossed perforant path.",
            },
            {   # "Ipsilateral longitudinal associational circuit"
                "local_id": "region_4", "name": "CA3 (Hippocampus)",
                "hemisphere_context": "IPSILATERAL_TO_SEED",
                "relation_to_seed": "CIRCUIT_MEMBER",
                "rationale": "Same-side associational fibres.",
            },
        ],
        "connections": [
            {"local_id": "connection_1", "confidence": 0.6,
             "species_context": {"scope": "NON_HUMAN", "taxon_ids": [10116]},
             "source_ref": "SEED", "target_ref": "region_1",
             "connection_type": "PROJECTION", "directionality": "DIRECTED"},
            {"local_id": "connection_2", "confidence": 0.6,
             "species_context": {"scope": "NON_HUMAN", "taxon_ids": [10116]},
             "source_ref": "region_2", "target_ref": "SEED",
             "connection_type": "PROJECTION", "directionality": "DIRECTED"},
            {"local_id": "connection_3", "confidence": 0.6,
             "species_context": {"scope": "NON_HUMAN", "taxon_ids": [10116]},
             "source_ref": "region_3", "target_ref": "SEED",
             "connection_type": "PROJECTION", "directionality": "DIRECTED"},
        ],
        "circuits": [
            {"local_id": "circuit_1", "confidence": 0.6,
             "species_context": {"scope": "NON_HUMAN", "taxon_ids": [10116]},
             "name": "Contralateral CA3 commissural circuit",
             "region_refs": ["SEED", "region_1"],
             "connection_refs": ["connection_1"], "function_refs": [],
             "topology_hint": "RECIPROCAL"},
            {"local_id": "circuit_2", "confidence": 0.6,
             "species_context": {"scope": "NON_HUMAN", "taxon_ids": [10116]},
             "name": "Bilateral entorhinal convergence circuit onto CA3",
             "region_refs": ["SEED", "region_2", "region_3"],
             "connection_refs": ["connection_2", "connection_3"],
             "function_refs": [], "topology_hint": "CONVERGENT"},
        ],
        "functions": [
            {"local_id": "function_1", "confidence": 0.5,
             "species_context": {"scope": "UNKNOWN", "taxon_ids": []},
             "label": "pattern completion",
             "related_region_refs": ["region_1"], "related_circuit_refs": ["circuit_1"]},
        ],
        "source_hints": [], "warnings": [],
    }


def test_21_the_live_ca3_concepts_parse_and_keep_their_bilateral_structure():
    """§15 — the prose these candidates already carry, in typed form.

    Two entorhinal regions share a NAME and differ only in hemisphere_context.
    That is the whole point: if the pair collapsed, the "ipsilateral plus
    crossed" structure would be gone and nothing downstream could tell a
    bilateral convergence from a one-sided one.
    """
    s = _schema()
    from app.services.llm_discovery_parser import parse_llm_discovery_response

    data = _ca3_concepts()
    parsed = parse_llm_discovery_response(data, seed_entity_id=_CA3_SEED)
    assert parsed.ok, parsed.error
    response = parsed.data

    entorhinal = [r for r in response.regions if r.name == "Entorhinal cortex"]
    assert len(entorhinal) == 2, "both perforant paths must survive as regions"
    assert {r.hemisphere_context for r in entorhinal} == {
        "IPSILATERAL_TO_SEED", "CONTRALATERAL_TO_SEED",
    }
    # Same name, different claim: this is the distinction that would have been
    # lost under a name-keyed pool.
    assert len({r.local_id for r in entorhinal}) == 2

    by_id = {r.local_id: r for r in response.regions}
    convergence = next(c for c in response.circuits if "Bilateral" in c.name)
    assert convergence.region_refs == ["SEED", "region_2", "region_3"]
    sides = [
        s.resolve_hemisphere("left", by_id[ref].hemisphere_context)
        for ref in convergence.region_refs
        if ref != "SEED"
    ]
    assert sides == ["LEFT", "RIGHT"], "the crossed path must not become left"

    # And the resolver reaches the same answer through a connection endpoint.
    assert s.resolve_connection_sides("left", "region_3", "SEED", by_id) == (
        "RIGHT", "LEFT",
    )

    # §12 — laterality is NOT pushed into the function vocabulary.
    assert [f.label for f in response.functions] == ["pattern completion"]


# ===========================================================================
# 22. Backward compatibility, at the boundary it is actually claimed
# ===========================================================================
#: A region payload as schema 1.0 actually wrote it: the free-text `hemisphere`
#: key, no `hemisphere_context`. This is data that EXISTS, not a hypothetical:
#: 353 of the 1,113 region candidates in the isolated database carry that key
#: (290 "left", 47 "LEFT", 15 "right", 1 "bilateral") and the other 760 carry
#: none at all — which is itself the argument for a field whose default is a
#: stated UNSPECIFIED rather than an absent string.
_LEGACY_V1_REGION = {
    "local_id": "region_1",
    "confidence": 0.72,
    "name": "CA1 field of the hippocampus",
    "name_en": "CA1",
    "name_zh": "CA1 区",
    "hemisphere": "left",
    "species_taxon_id": "9606",
    "relation_to_seed": "AFFERENT",
    "rationale": "Receives the seed's principal output.",
}


def test_22_a_stored_v1_payload_is_readable_but_is_still_refused_as_new_input():
    """§14 — the two halves of the backward-compatibility claim, kept apart.

    READ side: a stored v1.0 payload predates this contract and cannot be
    refused, because refusing it would be data loss over a field that was
    correct when it was written. It reads as UNSPECIFIED — the laterality it
    used to carry is NOT promoted into the new field, because "left" written as
    free text is not the same claim as LEFT in a closed vocabulary, and quietly
    converting it would be a backfill dressed up as a migration.

    WRITE side: the same region body is REFUSED as a new response, at the
    CURRENT version. Strictness was not relaxed to accommodate history — the
    legacy key is readable where it already exists and rejected where it would
    be newly produced. That separation is the whole guarantee, so it is asserted
    in one place rather than half-proved in two.
    """
    read = _read_service()
    s = _schema()

    # --- READ: a stored v1.0 row survives the projection unchanged ----------
    stored = {
        "schema_version": "1.0",
        "seed_entity_id": LEFT_SEED,
        "summary": "Written before this contract existed.",
        "regions": [_LEGACY_V1_REGION],
    }
    item = read._row_to_item(
        _row(payload_json=stored, name=_LEGACY_V1_REGION["name"]), LEFT_SEED, "left"
    )
    # Verbatim: the original wording is still there to be read by a human, and
    # the payload is not rewritten on read.
    assert item.payload["regions"][0]["hemisphere"] == "left"
    assert item.payload["schema_version"] == "1.0"
    # NOT reinterpreted, and NOT invented from the seed's own side.
    assert "hemisphere_context" not in item.payload["regions"][0]
    assert item.resolved_hemisphere == "UNSPECIFIED"

    # The whole stored payload still round-trips through JSON as data.
    import json

    assert json.loads(json.dumps(stored)) == stored

    # --- WRITE: the same body at the CURRENT version is still refused --------
    from app.services.llm_discovery_parser import parse_llm_discovery_response

    at_current_version = dict(_LEGACY_V1_REGION)
    refused = parse_llm_discovery_response(
        {
            "schema_version": s.SCHEMA_VERSION,   # version is NOT the objection
            "seed_entity_id": LEFT_SEED,
            "regions": [at_current_version],
        },
        seed_entity_id=LEFT_SEED,
    )
    assert not refused.ok, "the retired field must not be accepted on new input"
    assert "hemisphere" in refused.error and "extra_forbidden" in refused.error

    # The stored payload is also refused if it ever arrives as a RESPONSE. Two
    # things are wrong with it there and pydantic reports the field error first,
    # because field validation precedes the `mode="after"` version check — the
    # version pin itself is asserted directly in test_14, against a body that is
    # otherwise valid, so it is not tested through this unrelated failure.
    stale = parse_llm_discovery_response(stored, seed_entity_id=LEFT_SEED)
    assert not stale.ok
    assert "extra_forbidden" in stale.error
