"""Circuit semantic novelty assessor — scope, contract, and read-only-ness.

The assessor answers one number ("how many of this round's circuits are new?"),
and that number is intended to become a stopping signal. So these tests are
mostly about what may NOT inflate or deflate it: a run from another seed or
another view, a FAILED run, the target run compared against itself, a missing
verdict silently padded, a match claim pointing at nothing.

No database and no provider: the session is scripted and the provider is a stub,
so every assertion is about the contract rather than about whether Postgres or
DeepSeek happened to agree.
"""
from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime, timezone
from typing import Any
from unittest.mock import patch

import pytest

from app.prompts.llm_circuit_novelty_prompt import build_novelty_prompt
from app.schemas.circuit_novelty import (
    NOVELTY_CLASSES,
    NOVELTY_CLASSES_COUNTING_AS_NEW,
    CircuitNoveltyAssessment,
    ModelNoveltyResponse,
    semantic_new_count_of,
)
from app.services import llm_circuit_novelty_service as nov

SEED = "NGIQ-BR-00001605"
SEED_PK = 4242
VIEW = "NAMED_CLASSIC_CIRCUITS"
STRATEGY = "G4HR1/NAMED_CLASSIC_CIRCUITS"
RUN = "07c31f2e-063d-4f20-9c22-ed6fda8ab5b9"
PRIOR_RUN = "873fd051-7261-48c4-8ccb-417242b6a85e"
T0 = datetime(2026, 9, 16, 22, 47, 47, tzinfo=timezone.utc)


class _Result:
    def __init__(self, rows=None):
        self._rows = list(rows or [])

    def mappings(self):
        return self

    def one_or_none(self):
        return self._rows[0] if self._rows else None

    def all(self):
        return self._rows


class _Session:
    """Answers the three statements this service issues, and nothing else.

    Records every statement so a test can assert that the assessor only ever
    reads.
    """

    def __init__(self, *, scope=None, prior=None, target=None):
        self.scope = scope
        self.prior = list(prior or [])
        self.target = list(target or [])
        self.statements: list[tuple[str, dict[str, Any]]] = []

    async def execute(self, stmt, params=None):
        sql = " ".join(str(stmt).split())
        self.statements.append((sql, dict(params or {})))
        if "(:target_created_at, :target_run_id)" in sql:
            return _Result(self.prior)
        if "r.run_id = :target_run_id" in sql:
            return _Result(self.target)
        if "r.run_id = :run_id" in sql:
            return _Result([self.scope] if self.scope else [])
        raise AssertionError(f"unexpected SQL: {sql}")

    @property
    def sql(self) -> list[str]:
        return [s for s, _ in self.statements]


def _scope(**over) -> dict[str, Any]:
    row = {
        "run_id": RUN,
        "status": "COMPLETED",
        "discovery_type": "LLM_DISCOVERY",
        "query_strategy_version": STRATEGY,
        "created_at": T0,
        "seed_entity_id": SEED,
    }
    row.update(over)
    return row


def _row(candidate_id: str, name: str, run_id: str = PRIOR_RUN, **over) -> dict[str, Any]:
    row = {
        "candidate_id": candidate_id,
        "local_id": f"circuit_{candidate_id[-1]}",
        "name": name,
        "run_id": run_id,
        "description": f"{name} described.",
        "rationale": f"{name} rationale.",
        "topology_hint": "LOOP",
        "region_refs": json.dumps(["SEED", "region_1"]),
        "connection_refs": json.dumps(["connection_1"]),
        "function_refs": [],
    }
    row.update(over)
    return row


def _resolve(session, **over):
    kwargs = dict(run_id=RUN)
    kwargs.update(over)
    return asyncio.run(nov.resolve_assessable_run(session, **kwargs))


def _assess(session, resp=None, **over):
    kwargs = dict(run_id=RUN)
    kwargs.update(over)
    with patch.object(nov, "get_llm_provider", lambda _name: _StubProvider(resp)):
        return asyncio.run(nov.assess_circuit_novelty(session, **kwargs))


class _StubProvider:
    """A provider that returns one canned reply and reports the frozen model."""

    def __init__(self, resp):
        self._resp = resp
        self.calls: list[dict[str, Any]] = []

    async def complete_json(self, **kwargs):
        self.calls.append(kwargs)
        return self._resp


class _Resp:
    def __init__(self, raw_text=None, parsed_json=None, transport_ok=True,
                 model="deepseek-flash", error_message=None):
        self.raw_text = raw_text
        self.parsed_json = parsed_json
        self.transport_ok = transport_ok
        self.model = model
        self.error_message = error_message


def _reply(*verdicts: dict[str, Any]) -> _Resp:
    return _Resp(parsed_json=None, raw_text=json.dumps({"verdicts": list(verdicts)}))


def _v(candidate_id: str, klass: str, matched: str | None = None, reason="because"):
    return {
        "candidate_id": candidate_id,
        "novelty_class": klass,
        "matched_prior_candidate_id": matched,
        "short_reason": reason,
    }


# ===========================================================================
# comparison scope
# ===========================================================================
def test_scope_is_the_same_seed_and_the_same_view_only():
    session = _Session(scope=_scope(), prior=[_row("DC-00000001", "X")], target=[])
    asyncio.run(nov.collect_prior_circuits(
        session, scope=asyncio.run(nov.resolve_assessable_run(session, run_id=RUN))
    ))
    sql, params = session.statements[-1]
    assert params["entity_id"] == SEED
    assert params["strategy"] == STRATEGY
    assert "e.entity_id = :entity_id" in sql
    assert "r.query_strategy_version = :strategy" in sql


def test_failed_runs_are_excluded_by_the_status_predicate():
    session = _Session(scope=_scope(), prior=[], target=[])
    scope = asyncio.run(nov.resolve_assessable_run(session, run_id=RUN))
    asyncio.run(nov.collect_prior_circuits(session, scope=scope))
    sql, params = session.statements[-1]
    assert params["status"] == "COMPLETED"
    assert "r.status = :status" in sql


def test_the_target_run_is_excluded_from_its_own_prior_pool():
    """`earlier` is expressed in SQL, so a run can never be its own prior art."""
    session = _Session(scope=_scope(), prior=[], target=[])
    scope = asyncio.run(nov.resolve_assessable_run(session, run_id=RUN))
    asyncio.run(nov.collect_prior_circuits(session, scope=scope))
    sql, params = session.statements[-1]
    assert "(r.created_at, r.run_id) < (:target_created_at, :target_run_id)" in sql
    assert params["target_run_id"] == RUN
    assert params["target_created_at"] == T0


def test_only_circuit_candidates_are_collected():
    session = _Session(scope=_scope(), prior=[], target=[])
    scope = asyncio.run(nov.resolve_assessable_run(session, run_id=RUN))
    asyncio.run(nov.collect_prior_circuits(session, scope=scope))
    assert session.statements[-1][1]["candidate_type"] == "circuit"
    asyncio.run(nov.collect_target_circuits(session, scope=scope))
    assert session.statements[-1][1]["candidate_type"] == "circuit"


def test_every_previous_completed_round_contributes():
    """The pool spans ALL earlier runs, not just the immediate predecessor."""
    prior = [
        _row("DC-00000001", "A", run_id="run-1"),
        _row("DC-00000002", "B", run_id="run-2"),
        _row("DC-00000003", "C", run_id="run-3"),
    ]
    session = _Session(scope=_scope(), prior=prior, target=[])
    pool = asyncio.run(nov.collect_prior_circuits(
        session, scope=asyncio.run(nov.resolve_assessable_run(session, run_id=RUN))
    ))
    assert len(pool.circuits) == 3
    assert pool.run_count == 3


def test_priority_context_is_carried_not_just_the_name():
    session = _Session(scope=_scope(), prior=[], target=[])
    scope = asyncio.run(nov.resolve_assessable_run(session, run_id=RUN))
    asyncio.run(nov.collect_prior_circuits(session, scope=scope))
    sql = session.statements[-1][0]
    for field in ("description", "rationale", "topology_hint",
                  "region_refs", "connection_refs", "function_refs"):
        assert f"'{field}'" in sql, field


def test_confidence_is_never_collected():
    """It is not novelty evidence, so it is not even read."""
    session = _Session(scope=_scope(), prior=[], target=[])
    scope = asyncio.run(nov.resolve_assessable_run(session, run_id=RUN))
    asyncio.run(nov.collect_prior_circuits(session, scope=scope))
    asyncio.run(nov.collect_target_circuits(session, scope=scope))
    assert all("confidence" not in s for s in session.sql)


# ===========================================================================
# run eligibility
# ===========================================================================
def test_a_missing_run_is_refused():
    with pytest.raises(nov.NoveltyRunNotFound):
        _resolve(_Session(scope=None))


def test_a_failed_run_is_refused():
    with pytest.raises(nov.NoveltyRunNotAssessable) as exc:
        _resolve(_Session(scope=_scope(status="FAILED")))
    assert exc.value.code == "NOVELTY_RUN_NOT_ASSESSABLE"


def test_a_literature_run_is_refused():
    with pytest.raises(nov.NoveltyRunNotAssessable):
        _resolve(_Session(scope=_scope(discovery_type="LITERATURE_DISCOVERY")))


def test_the_strategy_identifier_yields_the_view():
    scope = _resolve(_Session(scope=_scope()))
    assert scope.discovery_view == VIEW


def test_a_foreign_strategy_yields_no_view_rather_than_a_guess():
    scope = _resolve(_Session(scope=_scope(query_strategy_version="SOMETHING_ELSE")))
    assert scope.discovery_view is None


# ===========================================================================
# the four classes
# ===========================================================================
def _one_target(cid="DC-00000010"):
    return [_row(cid, "Target circuit", run_id=RUN)]


def test_new_is_counted():
    session = _Session(scope=_scope(), prior=[_row("DC-00000001", "Old")],
                       target=_one_target())
    result = _assess(session, _reply(_v("DC-00000010", "NEW")))
    assert result.NEW_count == 1
    assert result.semantic_new_count == 1
    assert result.verdicts[0].matched_prior_candidate_id is None


def test_alias_is_not_counted_and_names_what_it_matches():
    session = _Session(scope=_scope(), prior=[_row("DC-00000001", "Old")],
                       target=_one_target())
    result = _assess(session, _reply(_v("DC-00000010", "ALIAS", "DC-00000001")))
    assert result.ALIAS_count == 1
    assert result.semantic_new_count == 0
    assert result.verdicts[0].matched_prior_candidate_id == "DC-00000001"
    # The run id comes from the stored prior row, not from the model.
    assert result.verdicts[0].matched_prior_run_id == PRIOR_RUN


def test_reformulation_is_not_counted():
    session = _Session(scope=_scope(), prior=[_row("DC-00000001", "Old")],
                       target=_one_target())
    result = _assess(session, _reply(_v("DC-00000010", "REFORMULATION", "DC-00000001")))
    assert result.REFORMULATION_count == 1
    assert result.semantic_new_count == 0


def test_borderline_COUNTS_as_novelty():
    """The asymmetry that makes this recall-first rather than deduplication."""
    session = _Session(scope=_scope(), prior=[_row("DC-00000001", "Old")],
                       target=_one_target())
    result = _assess(session, _reply(_v("DC-00000010", "BORDERLINE")))
    assert result.BORDERLINE_count == 1
    assert result.semantic_new_count == 1
    assert result.verdicts[0].counts_as_new


def test_borderline_may_name_a_match_without_it_changing_the_count():
    session = _Session(scope=_scope(), prior=[_row("DC-00000001", "Old")],
                       target=_one_target())
    result = _assess(session, _reply(_v("DC-00000010", "BORDERLINE", "DC-00000001")))
    assert result.semantic_new_count == 1
    assert result.verdicts[0].matched_prior_candidate_id == "DC-00000001"


def test_semantic_new_count_is_EXACTLY_new_plus_borderline():
    session = _Session(
        scope=_scope(),
        prior=[_row("DC-00000001", "A"), _row("DC-00000002", "B")],
        target=[_row(f"DC-0000001{i}", f"T{i}", run_id=RUN) for i in range(4)],
    )
    result = _assess(session, _reply(
        _v("DC-00000010", "NEW"),
        _v("DC-00000011", "ALIAS", "DC-00000001"),
        _v("DC-00000012", "REFORMULATION", "DC-00000002"),
        _v("DC-00000013", "BORDERLINE"),
    ))
    assert (result.NEW_count, result.ALIAS_count) == (1, 1)
    assert (result.REFORMULATION_count, result.BORDERLINE_count) == (1, 1)
    assert result.semantic_new_count == 2
    assert result.semantic_new_count == semantic_new_count_of(result.verdicts)


def test_the_counting_rule_is_exactly_new_plus_borderline():
    assert set(NOVELTY_CLASSES_COUNTING_AS_NEW) == {"NEW", "BORDERLINE"}
    assert set(NOVELTY_CLASSES) == {"NEW", "ALIAS", "REFORMULATION", "BORDERLINE"}


# ===========================================================================
# the reply must be complete and internally consistent
# ===========================================================================
def test_a_MISSING_verdict_is_refused_not_padded():
    session = _Session(
        scope=_scope(), prior=[],
        target=[_row("DC-00000010", "T1", run_id=RUN), _row("DC-00000011", "T2", run_id=RUN)],
    )
    with pytest.raises(nov.NoveltyAssessmentIncomplete):
        _assess(session, _reply(_v("DC-00000010", "NEW")))


def test_a_DUPLICATE_verdict_is_refused():
    session = _Session(scope=_scope(), prior=[], target=_one_target())
    with pytest.raises(nov.NoveltyAssessmentIncomplete):
        _assess(session, _reply(_v("DC-00000010", "NEW"), _v("DC-00000010", "NEW")))


def test_an_unknown_candidate_id_is_refused():
    session = _Session(scope=_scope(), prior=[], target=_one_target())
    with pytest.raises(nov.NoveltyAssessmentInvalid):
        _assess(session, _reply(_v("DC-99999999", "NEW")))


def test_ALIAS_without_a_match_is_refused():
    session = _Session(scope=_scope(), prior=[_row("DC-00000001", "Old")],
                       target=_one_target())
    with pytest.raises(nov.NoveltyAssessmentInvalid):
        _assess(session, _reply(_v("DC-00000010", "ALIAS", None)))


def test_REFORMULATION_matching_something_that_is_not_prior_is_refused():
    session = _Session(scope=_scope(), prior=[_row("DC-00000001", "Old")],
                       target=_one_target())
    with pytest.raises(nov.NoveltyAssessmentInvalid):
        _assess(session, _reply(_v("DC-00000010", "REFORMULATION", "DC-00000077")))


def test_NEW_that_claims_a_match_is_refused():
    session = _Session(scope=_scope(), prior=[_row("DC-00000001", "Old")],
                       target=_one_target())
    with pytest.raises(nov.NoveltyAssessmentInvalid):
        _assess(session, _reply(_v("DC-00000010", "NEW", "DC-00000001")))


def test_an_invalid_class_is_refused():
    session = _Session(scope=_scope(), prior=[], target=_one_target())
    with pytest.raises(nov.NoveltyAssessmentInvalid):
        _assess(session, _reply(_v("DC-00000010", "PROBABLY_NEW")))


def test_a_non_json_reply_is_refused():
    session = _Session(scope=_scope(), prior=[], target=_one_target())
    with pytest.raises(nov.NoveltyAssessmentInvalid):
        _assess(session, _Resp(raw_text="I think most of them are new."))


def test_a_run_with_no_circuits_is_a_zero_and_costs_no_provider_call():
    session = _Session(scope=_scope(), prior=[_row("DC-00000001", "Old")], target=[])
    constructed: list[_StubProvider] = []

    def _factory(_name):
        p = _StubProvider(None)
        constructed.append(p)
        return p

    with patch.object(nov, "get_llm_provider", _factory):
        result = asyncio.run(nov.assess_circuit_novelty(session, run_id=RUN))
    assert result.raw_circuit_count == 0
    assert result.semantic_new_count == 0
    # Never even constructed: "nothing to assess" must not cost a model call.
    assert constructed == []


# ===========================================================================
# the assessment object cannot contradict itself
# ===========================================================================
def test_the_summary_cannot_disagree_with_its_own_verdicts():
    from app.schemas.circuit_novelty import CircuitNoveltyVerdict

    verdict = CircuitNoveltyVerdict(
        candidate_id="DC-1", name="X", novelty_class="NEW", short_reason="r"
    )
    base = dict(
        target_run_id=RUN, seed_entity_id=SEED, strategy_identifier=STRATEGY,
        raw_circuit_count=1, prior_circuit_count=0, prior_run_count=0,
        NEW_count=1, ALIAS_count=0, REFORMULATION_count=0, BORDERLINE_count=0,
        semantic_new_count=1, verdicts=[verdict],
    )
    assert CircuitNoveltyAssessment(**base).semantic_new_count == 1
    for broken in ({"semantic_new_count": 0}, {"NEW_count": 0},
                   {"raw_circuit_count": 99}):
        with pytest.raises(Exception):
            CircuitNoveltyAssessment(**{**base, **broken})


# ===========================================================================
# recall-first guard + policy
# ===========================================================================
def test_the_prompt_tells_the_model_to_prefer_borderline_when_unsure():
    from app.prompts.llm_circuit_novelty_prompt import SYSTEM_PROMPT

    assert "WHEN IN DOUBT, CHOOSE BORDERLINE" in SYSTEM_PROMPT
    assert "NEW or an ALIAS" in SYSTEM_PROMPT
    assert "NEW or a REFORMULATION" in SYSTEM_PROMPT


def test_the_prompt_renders_the_vocabulary_from_the_contract():
    from app.prompts import llm_circuit_novelty_prompt as prompt_mod

    target = (nov.AssessableCircuit(
        candidate_id="DC-1", run_id=RUN, local_id="circuit_1", name="T",
        description="d", rationale="r", topology_hint="LOOP",
        region_refs=("SEED",), connection_refs=(), function_refs=(),
    ),)
    prompt = build_novelty_prompt(
        target=target, prior=(), seed_entity_id=SEED, discovery_view=VIEW
    )
    assert set(prompt_mod.NOVELTY_CLASSES) == set(NOVELTY_CLASSES)
    for value in NOVELTY_CLASSES:
        assert value in prompt["system_prompt"], value
    assert VIEW in prompt["user_prompt"]


def test_confidence_is_NOT_sent_to_the_model():
    target = (nov.AssessableCircuit(
        candidate_id="DC-1", run_id=RUN, local_id="circuit_1", name="T",
        description="d", rationale="r", topology_hint="LOOP",
        region_refs=("SEED",), connection_refs=(), function_refs=(),
    ),)
    prompt = build_novelty_prompt(
        target=target, prior=target, seed_entity_id=SEED, discovery_view=VIEW
    )
    assert "confidence" not in prompt["user_prompt"]
    assert "confidence" not in prompt["system_prompt"]


def test_the_model_is_the_frozen_deepseek_flash():
    from app.llm_model_policy import DEEPSEEK_MODEL

    session = _Session(scope=_scope(), prior=[], target=_one_target())
    stub = _StubProvider(_reply(_v("DC-00000010", "NEW")))
    with patch.object(nov, "get_llm_provider", lambda _name: stub):
        asyncio.run(nov.assess_circuit_novelty(session, run_id=RUN))
    assert stub.calls[0]["model"] == "deepseek-flash"
    assert DEEPSEEK_MODEL == "deepseek-flash"


def test_a_model_policy_violation_is_refused():
    session = _Session(scope=_scope(), prior=[], target=_one_target())
    resp = _reply(_v("DC-00000010", "NEW"))
    resp.model = "deepseek-v4-pro"
    with pytest.raises(nov.NoveltyProviderError):
        _assess(session, resp)


def test_a_transport_failure_is_refused():
    session = _Session(scope=_scope(), prior=[], target=_one_target())
    with pytest.raises(nov.NoveltyProviderError):
        _assess(session, _Resp(raw_text="", transport_ok=False,
                               error_message="connection reset"))


# ===========================================================================
# read-only: no writes, no merges, no deletes, no status changes
# ===========================================================================
def test_every_statement_the_assessor_issues_is_a_SELECT():
    session = _Session(
        scope=_scope(), prior=[_row("DC-00000001", "Old")], target=_one_target()
    )
    _assess(session, _reply(_v("DC-00000010", "ALIAS", "DC-00000001")))
    assert session.sql, "the assessor must have read something"
    # Word boundaries, not substrings: `created_at` is not a CREATE.
    banned = re.compile(
        r"\b(INSERT|UPDATE|DELETE|MERGE|ALTER|DROP|TRUNCATE|CREATE|GRANT|"
        r"UPSERT|ON\s+CONFLICT)\b",
        re.IGNORECASE,
    )
    for sql in session.sql:
        assert sql.upper().startswith("SELECT"), sql
        assert not banned.search(sql), sql


def test_the_assessment_returns_no_write_summary():
    """Nothing in the result describes a mutation, because none is possible."""
    session = _Session(scope=_scope(), prior=[_row("DC-00000001", "Old")],
                       target=_one_target())
    result = _assess(session, _reply(_v("DC-00000010", "ALIAS", "DC-00000001")))
    dumped = result.model_dump()
    for word in ("merged", "deleted", "rejected", "status", "written",
                 "created", "updated"):
        assert word not in dumped, word


def test_an_ALIAS_verdict_does_not_change_the_candidate_in_any_way():
    """The class is an annotation. The circuit is still returned, with its own
    name and local id, exactly as stored."""
    session = _Session(scope=_scope(), prior=[_row("DC-00000001", "Old")],
                       target=_one_target())
    result = _assess(session, _reply(_v("DC-00000010", "ALIAS", "DC-00000001")))
    assert len(result.verdicts) == 1
    assert result.verdicts[0].name == "Target circuit"
    assert result.verdicts[0].candidate_id == "DC-00000010"
    assert result.raw_circuit_count == 1


def test_unknown_extra_keys_in_the_reply_do_not_destroy_the_assessment():
    """Deliberately unlike the discovery contract: a stray key here would only
    throw away a count over candidates that are already stored."""
    session = _Session(scope=_scope(), prior=[], target=_one_target())
    reply = _reply({**_v("DC-00000010", "NEW"), "invented_field": None,
                    "note": "the model added this"})
    result = _assess(session, reply)
    assert result.semantic_new_count == 1


def test_the_response_model_accepts_extras_but_requires_the_known_fields():
    assert ModelNoveltyResponse.model_config["extra"] == "ignore"
    with pytest.raises(Exception):
        ModelNoveltyResponse.model_validate({"verdicts": [{"novelty_class": "NEW"}]})


# ===========================================================================
# reply shape — found by live validation against Round 5
# ===========================================================================
# The first live run reported "23 of 23 circuits were not assessed" against a
# reply that in fact contained all 23 verdicts. Two shape bugs, one cause: the
# assessor trusted `response.parsed_json` — the provider's JSON extraction, which
# takes the FIRST object it finds — instead of what the model actually emitted.
# For a `{"verdicts":[...]}` document the first object is the first VERDICT, so a
# complete answer arrived as a single verdict and looked like an empty one.
def test_raw_text_is_authoritative_over_a_misleading_parsed_json():
    """The exact live failure, pinned."""
    verdicts = [_v("DC-00000010", "NEW"), _v("DC-00000011", "BORDERLINE")]
    session = _Session(
        scope=_scope(), prior=[],
        target=[_row("DC-00000010", "T1", run_id=RUN),
                _row("DC-00000011", "T2", run_id=RUN)],
    )
    resp = _Resp(
        raw_text=json.dumps({"verdicts": verdicts}),
        # What the provider's extractor returns: the first inner object.
        parsed_json=verdicts[0],
    )
    result = _assess(session, resp)
    assert result.raw_circuit_count == 2
    assert result.semantic_new_count == 2


def test_a_reply_with_no_text_at_all_is_refused_before_parsing():
    """There is no `parsed_json` fallback to get wrong: an empty reply is an
    empty reply."""
    session = _Session(scope=_scope(), prior=[], target=_one_target())
    with pytest.raises(nov.NoveltyProviderError):
        _assess(session, _Resp(raw_text="   ", parsed_json={"verdicts": [_v("DC-00000010", "NEW")]}))


def test_a_bare_ARRAY_of_verdicts_is_the_same_answer_as_the_wrapper():
    """The model sometimes drops the envelope. That is a style difference, not a
    different answer, and refusing it would discard a valid assessment."""
    session = _Session(
        scope=_scope(), prior=[],
        target=[_row("DC-00000010", "T1", run_id=RUN),
                _row("DC-00000011", "T2", run_id=RUN)],
    )
    result = _assess(session, _Resp(raw_text=json.dumps(
        [_v("DC-00000010", "NEW"), _v("DC-00000011", "BORDERLINE")]
    )))
    assert result.NEW_count == 1
    assert result.semantic_new_count == 2


def test_a_reply_with_NO_verdicts_is_not_reported_as_a_partial_one():
    """An unjudged-everything reply is a shape problem; a missing-three reply is
    a coverage problem. Conflating them sends a reader hunting for the wrong
    thing."""
    session = _Session(scope=_scope(), prior=[], target=_one_target())
    with pytest.raises(nov.NoveltyAssessmentInvalid) as exc:
        _assess(session, _Resp(raw_text=json.dumps({"summary": "all new I think"})))
    assert "carried no verdicts" in str(exc.value)


def test_prompt_and_parser_agree_that_the_envelope_is_optional():
    from app.prompts.llm_circuit_novelty_prompt import SYSTEM_PROMPT

    assert '"verdicts"' in SYSTEM_PROMPT  # the asked-for shape
