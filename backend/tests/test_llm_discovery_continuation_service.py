"""Discovery View continuation — validation, exclusion context, round derivation.

The exclusion context is the whole point of a continuation, so these tests are
mostly about what may NOT feed it: a run from another seed, another route, another
view, or one that never completed. Each of those would put names in front of the
model that this view did not find for this region.

No database and no provider: the session is scripted, so every assertion is about
the contract rather than about whether Postgres happened to agree.
"""
from __future__ import annotations

import asyncio

import pytest

from app.services import llm_discovery_continuation_service as cont

SEED = "NGIQ-BR-00001605"
OTHER_SEED = "NGIQ-BR-00001169"
VIEW = "NAMED_CLASSIC_CIRCUITS"
STRATEGY = "G4HR1/NAMED_CLASSIC_CIRCUITS"
RUN = "8cd2e18a-d4c8-4e90-8324-97fcfb8dd0b3"


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
    """Answers the three statements this service issues, and nothing else."""

    def __init__(self, *, scope=None, chain=None, circuits=None):
        self.scope = scope
        self.chain = list(chain or [])
        self.circuits = list(circuits or [])
        self.statements: list[str] = []

    async def execute(self, stmt, params=None):
        sql = " ".join(str(stmt).split())
        self.statements.append(sql)
        if "r.run_id = :run_id" in sql:
            return _Result([self.scope] if self.scope else [])
        if "ORDER BY r.created_at, r.run_id" in sql:
            return _Result(self.chain)
        if "dc.candidate_type = 'circuit'" in sql:
            return _Result(self.circuits)
        raise AssertionError(f"unexpected SQL: {sql}")


def _scope(**over):
    row = {
        "run_id": RUN,
        "status": "COMPLETED",
        "discovery_type": "LLM_DISCOVERY",
        "query_strategy_version": STRATEGY,
        "continuation_round": None,
        "seed_entity_id": SEED,
    }
    row.update(over)
    return row


def _validate(session, **over):
    kwargs = dict(from_run_id=RUN, entity_id=SEED, discovery_view=VIEW, strategy=STRATEGY)
    kwargs.update(over)
    return asyncio.run(cont.validate_continuation(session, **kwargs))


def _collect(session, **over):
    kwargs = dict(entity_id=SEED, strategy=STRATEGY)
    kwargs.update(over)
    return asyncio.run(cont.collect_already_discovered(session, **kwargs))


# ===========================================================================
# §16.5-8 — what may NOT be continued
# ===========================================================================
def test_a_missing_source_run_is_not_found():
    with pytest.raises(cont.ContinuationRunNotFound) as e:
        _validate(_Session(scope=None))
    assert e.value.code == "CONTINUATION_RUN_NOT_FOUND"
    assert e.value.run_id == RUN


def test_cross_seed_continuation_is_rejected():
    """A continuation answers THIS region. Another seed's circuits are not this
    region's omissions, and using them would corrupt the exclusion context."""
    with pytest.raises(cont.ContinuationRunWrongSeed) as e:
        _validate(_Session(scope=_scope(seed_entity_id=OTHER_SEED)))
    assert e.value.code == "CONTINUATION_RUN_WRONG_SEED"
    assert OTHER_SEED in str(e.value)


def test_cross_view_continuation_is_rejected():
    """AFFERENT circuits may not seed a NAMED_CLASSIC continuation."""
    with pytest.raises(cont.ContinuationRunWrongView) as e:
        _validate(_Session(scope=_scope(query_strategy_version="G4HR1/AFFERENT_CIRCUITS")))
    assert e.value.code == "CONTINUATION_RUN_WRONG_VIEW"
    assert "AFFERENT_CIRCUITS" in str(e.value)


@pytest.mark.parametrize("status", ["QUEUED", "RUNNING", "FAILED", "CANCELLED"])
def test_an_incomplete_source_run_is_rejected(status):
    with pytest.raises(cont.ContinuationRunNotCompleted) as e:
        _validate(_Session(scope=_scope(status=status)))
    assert e.value.code == "CONTINUATION_RUN_NOT_COMPLETED"
    assert status in str(e.value)


def test_a_literature_run_is_not_a_continuation_source():
    with pytest.raises(cont.ContinuationRunWrongView) as e:
        _validate(_Session(scope=_scope(discovery_type="LITERATURE_DISCOVERY")))
    assert e.value.code == "CONTINUATION_RUN_WRONG_VIEW"


def test_a_legitimate_source_run_is_accepted():
    _validate(_Session(scope=_scope()))  # does not raise


def test_every_rejection_names_no_sql_and_no_database_internals():
    for scope in (None, _scope(seed_entity_id=OTHER_SEED), _scope(status="FAILED"),
                  _scope(discovery_type="LITERATURE_DISCOVERY")):
        with pytest.raises(cont.ContinuationError) as e:
            _validate(_Session(scope=scope))
        for forbidden in ("SELECT", "run_pk", "seed_region_pk", "Traceback", "psycopg"):
            assert forbidden not in str(e.value), forbidden


# ===========================================================================
# §16.9/11/12/13 — the exclusion context
# ===========================================================================
def _circuits(*names):
    return [{"name": n, "local_id": f"circuit_{i}"} for i, n in enumerate(names, 1)]


def test_the_context_lists_what_the_rows_actually_hold():
    s = _Session(circuits=_circuits("Papez circuit", "Entorhinal-hippocampal loop"))
    got = _collect(s)
    assert got.names == ("Papez circuit", "Entorhinal-hippocampal loop")
    assert got.raw_count == 2


def test_normalized_duplicates_collapse_ONLY_in_the_prompt_list():
    """The prompt gets a compact list; the count stays the honest row count."""
    s = _Session(circuits=_circuits(
        "Hippocampal trisynaptic circuit",
        "  hippocampal   TRISYNaptic circuit ",   # same after normalization
        "Papez circuit",
    ))
    got = _collect(s)
    assert got.names == ("Hippocampal trisynaptic circuit", "Papez circuit")
    assert got.raw_count == 3, "three ROWS exist; only the prompt list is deduplicated"


def test_the_first_spelling_encountered_is_the_one_kept():
    s = _Session(circuits=_circuits("Papez Circuit", "papez circuit"))
    assert _collect(s).names == ("Papez Circuit",)


def test_similar_but_distinct_concepts_are_NOT_collapsed():
    """Blunt normalization by design: it must not decide two circuits are one."""
    s = _Session(circuits=_circuits(
        "Hippocampal trisynaptic circuit",
        "Trisynaptic loop (perforant path-mossy fiber-Schaffer collateral circuit)",
        "CA3 autoassociative recurrent network",
    ))
    assert _collect(s).raw_count == 3
    assert len(_collect(s).names) == 3


def test_blank_names_never_enter_the_context():
    s = _Session(circuits=_circuits("Papez circuit", "", "   "))
    got = _collect(s)
    assert got.names == ("Papez circuit",)
    assert got.raw_count == 3, "a blank row still exists and is still counted"


def test_the_context_reads_the_WHOLE_chain_not_one_run():
    """§6 — a round-4 continuation must see rounds 1-3.

    The service asks for every COMPLETED run of this seed+view, so a circuit
    found in round 1 and never repeated is still excluded from round 4.
    """
    s = _Session(chain=[{"run_id": "r1", "continuation_round": None},
                        {"run_id": "r2", "continuation_round": "2"}],
                 circuits=_circuits("from round 1", "from round 2"))
    got = _collect(s)
    assert set(got.names) == {"from round 1", "from round 2"}
    chain_sql = next(x for x in s.statements if "ORDER BY r.created_at" in x)
    # The chain query is scoped by seed+route+status+STRATEGY — not by run id.
    assert "e.entity_id = :entity_id" in chain_sql
    assert "r.query_strategy_version = :strategy" in chain_sql
    assert "r.run_id = :run_id" not in chain_sql


# ===========================================================================
# §16.14/15 — the round number is derived, never requested
# ===========================================================================
def test_a_first_continuation_is_round_two():
    s = _Session(chain=[{"run_id": "r1", "continuation_round": None}], circuits=[])
    assert _collect(s).next_round == 2


def test_a_third_round_is_derived_from_the_chain():
    s = _Session(chain=[{"run_id": "r1", "continuation_round": None},
                        {"run_id": "r2", "continuation_round": "2"}], circuits=[])
    got = _collect(s)
    assert got.next_round == 3
    assert got.rounds_present == (2,)


def test_the_round_advances_past_a_gap():
    """Rounds are derived from the MAX present, not from how many there are."""
    s = _Session(chain=[{"run_id": "r1", "continuation_round": None},
                        {"run_id": "r5", "continuation_round": "5"}], circuits=[])
    assert _collect(s).next_round == 6


def test_normalize_is_blunt_and_stable():
    assert cont.normalize_circuit_name("  A   B  ") == "a b"
    assert cont.normalize_circuit_name("A\nB") == "a b"
    assert cont.normalize_circuit_name("") == ""
    assert cont.normalize_circuit_name("Papez Circuit") == cont.normalize_circuit_name("papez  circuit")


def test_the_service_only_ever_SELECTs():
    """A continuation reads; it never writes, merges or deletes."""
    s = _Session(chain=[{"run_id": "r1", "continuation_round": None}],
                 circuits=_circuits("A"))
    _collect(s)
    assert s.statements
    for sql in s.statements:
        assert sql.split(" ", 1)[0].upper() == "SELECT", sql
        for forbidden in ("INSERT", "UPDATE", "DELETE", "FOR UPDATE"):
            assert forbidden not in sql, sql
