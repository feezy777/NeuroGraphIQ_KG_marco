"""Phase P0-3A — the Candidate Review domain contract.

No database, no HTTP, no fixtures: the contract is a pure module, so these tests
are pure too. What they protect is not behaviour but MEANING — the vocabulary,
the transition graph, and above all the conflations that must stay impossible.
"""
from __future__ import annotations

import ast
import dataclasses
import inspect
import re
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]

from app.services import llm_candidate_review_contract as contract  # noqa: E402

MIGRATION = BACKEND / "migrations" / "gate7b_016_discovery_candidates.sql"

#: Words that belong to OTHER vocabularies. A candidate status must never be one
#: of them, and the module must never export one un-namespaced.
CANONICAL_RECORD_STATUSES = ("active", "deprecated", "merged")
CANONICAL_REVIEW_STATUSES = ("pending", "approved", "uncertain", "needs_revision")


# ===========================================================================
# A / B — the two frozen vocabularies
# ===========================================================================
def test_A_candidate_status_vocabulary_is_exactly_the_frozen_four():
    assert contract.CANDIDATE_STATUSES == ("proposed", "accepted", "rejected", "deferred")
    assert [s.value for s in contract.CandidateStatus] == list(contract.CANDIDATE_STATUSES)


def test_B_review_decision_vocabulary_is_exactly_three():
    assert contract.CANDIDATE_REVIEW_DECISIONS == ("ACCEPT", "REJECT", "DEFER")
    assert "REOPEN" not in contract.CANDIDATE_REVIEW_DECISIONS


# ===========================================================================
# C / D / E — one decision, one status, no aliasing
# ===========================================================================
@pytest.mark.parametrize(
    "decision,expected",
    [
        ("ACCEPT", "accepted"),
        ("REJECT", "rejected"),
        ("DEFER", "deferred"),
        (contract.CandidateReviewDecision.ACCEPT, "accepted"),
        (contract.CandidateReviewDecision.REJECT, "rejected"),
        (contract.CandidateReviewDecision.DEFER, "deferred"),
    ],
)
def test_C_D_E_each_decision_maps_to_exactly_one_status(decision, expected):
    assert contract.review_decision_to_status(decision).value == expected


def test_every_decision_maps_to_a_DIFFERENT_status():
    """If two decisions collapsed onto one status, the third status would be
    unreachable — the vocabulary would be decorative."""
    produced = {contract.review_decision_to_status(d) for d in contract.CANDIDATE_REVIEW_DECISIONS}
    assert len(produced) == len(contract.CANDIDATE_REVIEW_DECISIONS)
    assert produced == {
        contract.CandidateStatus.ACCEPTED,
        contract.CandidateStatus.REJECTED,
        contract.CandidateStatus.DEFERRED,
    }


def test_proposed_is_the_ENTRY_state_and_no_decision_ever_produces_it():
    """A decision moves a proposal OUT of ``proposed``; nothing moves it back in
    except re-opening a deferral. If a decision could produce ``proposed``, the
    review queue could be fed a status that means "nobody has looked yet"."""
    produced = {contract.review_decision_to_status(d) for d in contract.CANDIDATE_REVIEW_DECISIONS}
    assert contract.CandidateStatus.PROPOSED not in produced

    revivers = [
        current for current in contract.CANDIDATE_STATUSES
        if contract.can_transition_candidate_status(current, "proposed")
    ]
    assert revivers == ["deferred"], revivers


def test_an_unknown_decision_fails_closed():
    with pytest.raises(ValueError):
        contract.review_decision_to_status("REOPEN")
    with pytest.raises(ValueError):
        contract.review_decision_to_status("approve")


# ===========================================================================
# F / G / H — the transition graph
# ===========================================================================
def test_F_proposed_may_go_to_any_of_the_three_decisions():
    assert contract.allowed_transitions_from("proposed") == {
        contract.CandidateStatus.ACCEPTED,
        contract.CandidateStatus.REJECTED,
        contract.CandidateStatus.DEFERRED,
    }
    assert contract.can_transition_candidate_status("proposed", "accepted")
    assert contract.can_transition_candidate_status("proposed", "rejected")
    assert contract.can_transition_candidate_status("proposed", "deferred")


def test_G_deferred_reopens_to_proposed_and_to_nothing_else():
    """Re-opening is a TRANSITION, not an invented REOPEN decision: the repo has
    no reopen action in any review vocabulary, so none is invented here. A
    deferred item goes back through review rather than being decided directly,
    because its lacking context is exactly what deferral recorded."""
    assert contract.allowed_transitions_from("deferred") == {contract.CandidateStatus.PROPOSED}
    assert contract.can_transition_candidate_status("deferred", "proposed")
    assert not contract.can_transition_candidate_status("deferred", "accepted")
    assert not contract.can_transition_candidate_status("deferred", "rejected")


def test_H_rejected_is_TERMINAL():
    assert contract.is_terminal_candidate_status("rejected")
    assert contract.allowed_transitions_from("rejected") == frozenset()
    for target in contract.CANDIDATE_STATUSES:
        assert not contract.can_transition_candidate_status("rejected", target), target


def test_the_semantic_table_and_the_transition_graph_cannot_drift_apart():
    """`terminal_for_review` is a CLAIM about the transition graph, so it is
    checked AGAINST the graph instead of being trusted.

    Without this, the two could disagree — the semantics table saying a status is
    terminal while the graph still has an edge out of it — and every consumer
    would read a different truth depending on which function it happened to call.
    That is exactly the internal contradiction a future edit could introduce one
    status at a time.
    """
    observed: dict[str, bool] = {}
    for status in contract.CandidateStatus:
        terminal = contract.semantics_for(status).terminal_for_review
        assert terminal == (len(contract.allowed_transitions_from(status)) == 0), status
        # The public predicate must agree with the table it reads from.
        assert contract.is_terminal_candidate_status(status) == terminal, status
        observed[status.value] = terminal

    # The frozen truth, stated so a change to ANY of the four is visible.
    assert observed == {
        "proposed": False,
        "accepted": True,
        "rejected": True,
        "deferred": False,
    }


# ===========================================================================
# I / J / K / L — the next gate after each status
# ===========================================================================
def test_I_accepted_hands_off_to_resolution_canonicalization():
    assert contract.next_candidate_gate("accepted") == contract.CANDIDATE_GATE_RESOLUTION_CANONICALIZATION
    assert contract.semantics_for("accepted").enters_resolution is True


def test_I2_accepted_is_terminal_for_REVIEW_and_not_terminal_for_the_workflow():
    """The sharpest distinction this contract draws.

    ``accepted`` is TERMINAL FOR CANDIDATE REVIEW — no further review transition
    exists — while the overall Knowledge Production workflow continues into
    Resolution. A regression that gave ``accepted`` an outgoing edge (say back to
    ``deferred``) would leave ``terminal_for_review`` True while the graph said
    otherwise: the contract would contradict itself, silently. The four
    assertions below are what make that state unconstructible.
    """
    assert contract.is_terminal_candidate_status("accepted")
    assert contract.allowed_transitions_from("accepted") == frozenset()
    for target in contract.CANDIDATE_STATUSES:
        assert not contract.can_transition_candidate_status("accepted", target), target
    # A self-transition is not a legal transition either.
    assert not contract.can_transition_candidate_status("accepted", "accepted")

    assert contract.next_candidate_gate("accepted") == (
        contract.CANDIDATE_GATE_RESOLUTION_CANONICALIZATION
    )
    assert contract.semantics_for("accepted").enters_resolution is True
    assert contract.semantics_for("accepted").terminal_for_review is True

    # ...and "terminal for review" is not "terminal for the workflow": the gate
    # is a handoff, not a stop.
    assert contract.next_candidate_gate("accepted") != contract.CANDIDATE_GATE_TERMINAL


def test_J_K_proposed_and_deferred_both_gate_back_into_candidate_review():
    assert contract.next_candidate_gate("proposed") == contract.CANDIDATE_GATE_CANDIDATE_REVIEW
    assert contract.next_candidate_gate("deferred") == contract.CANDIDATE_GATE_CANDIDATE_REVIEW
    assert contract.semantics_for("proposed").enters_resolution is False
    assert contract.semantics_for("deferred").enters_resolution is False


def test_L_rejected_gate_is_terminal():
    assert contract.next_candidate_gate("rejected") == contract.CANDIDATE_GATE_TERMINAL


def test_a_gate_is_never_a_candidate_status():
    """The whole point of naming gates separately: a gate says what happens NEXT
    and must never be written into the status column."""
    for gate in contract.CANDIDATE_GATES:
        assert gate not in contract.CANDIDATE_STATUSES, gate
        assert gate.upper() == gate, "gates are loud on purpose, statuses are lowercase"


# ===========================================================================
# M — accepted means ONE thing, and not the seven things it is confused with
# ===========================================================================
def test_M_accepted_is_not_canonical_promoted_validated_or_evidence_backed():
    semantics = contract.semantics_for("accepted")
    assert semantics.implies_canonical_knowledge is False
    assert semantics.implies_validated is False
    assert semantics.implies_evidence_backed is False


def test_M2_no_status_at_all_claims_canonical_validated_or_evidence_backed():
    for status in contract.CandidateStatus:
        semantics = contract.semantics_for(status)
        assert semantics.implies_canonical_knowledge is False, status
        assert semantics.implies_validated is False, status
        assert semantics.implies_evidence_backed is False, status


@pytest.mark.parametrize(
    "forbidden",
    ["active", "promoted", "approved", "canonicalized", "validated", "resolved",
     "merged", "supported", "canonical", "final"],
)
def test_M3_forbidden_conflations_are_rejected_as_statuses(forbidden):
    assert forbidden not in contract.CANDIDATE_STATUSES
    with pytest.raises(ValueError):
        contract.CandidateStatus(forbidden)

    # And no transition may name one, from ANY status.
    for current in contract.CANDIDATE_STATUSES:
        assert not contract.can_transition_candidate_status(current, forbidden), current
    for current in ("accepted", "rejected"):
        assert not contract.can_transition_candidate_status(current, "active")
        assert not contract.can_transition_candidate_status(current, "promoted")


# ===========================================================================
# N — the canonical vocabulary stays on the canonical side
# ===========================================================================
def _module_source() -> str:
    return Path(contract.__file__).read_text(encoding="utf-8")


def _code_only() -> str:
    """Docstrings and comments removed: the prose names the forbidden words on
    purpose (to forbid them), so scanning raw source would match the guardrail."""
    src = _module_source()
    doc_lines: set[int] = set()
    for node in ast.walk(ast.parse(src)):
        if (isinstance(node, ast.Expr)
                and isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, str)):
            doc_lines.update(range(node.lineno, (node.end_lineno or node.lineno) + 1))
    kept = []
    for i, line in enumerate(src.splitlines(), start=1):
        if i in doc_lines or line.strip().startswith("#"):
            continue
        kept.append(line.split("#", 1)[0])
    return "\n".join(kept)


def test_N_the_canonical_lifecycle_vocabulary_is_not_reused_here():
    code = _code_only()
    for word in CANONICAL_RECORD_STATUSES + CANONICAL_REVIEW_STATUSES:
        assert f'"{word}"' not in code, word
        assert f"'{word}'" not in code, word

    # ...and none of them is a member of this module's vocabulary.
    for word in CANONICAL_RECORD_STATUSES + CANONICAL_REVIEW_STATUSES:
        assert word not in contract.CANDIDATE_STATUSES, word


def test_N2_no_bare_un_namespaced_vocabulary_constant_exists():
    """`proposed` is spelled identically in both domains. The defence is that this
    module exposes NO bare constant for it — only ``CandidateStatus.PROPOSED``."""
    for bare in ("PROPOSED", "ACCEPTED", "REJECTED", "DEFERRED",
                 "ACCEPT", "REJECT", "DEFER",
                 "ACTIVE", "PENDING", "APPROVED", "DEPRECATED", "MERGED"):
        assert not hasattr(contract, bare), bare


def test_N3_the_two_proposed_values_are_different_domains():
    """The collision itself, asserted rather than merely documented.

    Candidate ``proposed`` lives on discovery_candidates.status and means "no
    review decision yet". Canonical ``proposed`` lives on kg_entities.record_status
    and means "a canonical row that is not yet accepted". This module only owns
    the first, and must not be usable to interpret the second.
    """
    assert contract.CandidateStatus.PROPOSED.value == "proposed"
    # The canonical domain's `proposed` is NOT among this module's review statuses
    # in any other role: the module names no canonical column at all.
    assert "kg_entities" not in _code_only()
    assert "record_status" not in _code_only()
    assert "review_status" not in _code_only()


# ===========================================================================
# O / P / Q — purity
# ===========================================================================
def _imports() -> set[str]:
    mods: set[str] = set()
    for node in ast.walk(ast.parse(_module_source())):
        if isinstance(node, ast.Import):
            mods.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            mods.add(node.module or "")
    return mods


def test_O_P_Q_the_contract_imports_nothing_but_the_standard_library():
    """No database (O), no FastAPI (P), no Literature/Evidence/any app service (Q).
    A contract that could reach a session or an HTTP layer would stop being a
    contract."""
    mods = _imports()
    assert mods <= {"__future__", "dataclasses", "enum", "typing", "collections.abc"}, mods
    for module in mods:
        assert not module.startswith("app."), module
    for forbidden in ("sqlalchemy", "fastapi", "psycopg", "networkx", "httpx",
                      "pydantic", "literature", "evidence", "publication"):
        assert not any(forbidden in m for m in mods), forbidden


# ===========================================================================
# R — pure, deterministic, side-effect free
# ===========================================================================
def test_R_the_query_functions_are_deterministic():
    for status in contract.CANDIDATE_STATUSES:
        assert contract.allowed_transitions_from(status) == contract.allowed_transitions_from(status)
        assert contract.next_candidate_gate(status) == contract.next_candidate_gate(status)
        assert contract.is_terminal_candidate_status(status) is contract.is_terminal_candidate_status(status)
        assert contract.semantics_for(status) == contract.semantics_for(status)
    for decision in contract.CANDIDATE_REVIEW_DECISIONS:
        assert contract.review_decision_to_status(decision) is contract.review_decision_to_status(decision)


def test_R2_calling_them_mutates_nothing():
    before = {s: frozenset(contract.allowed_transitions_from(s)) for s in contract.CANDIDATE_STATUSES}
    for s in contract.CANDIDATE_STATUSES:
        contract.allowed_transitions_from(s)
        contract.can_transition_candidate_status(s, "accepted")
        contract.next_candidate_gate(s)
    after = {s: frozenset(contract.allowed_transitions_from(s)) for s in contract.CANDIDATE_STATUSES}
    assert before == after

    assert isinstance(contract.allowed_transitions_from("proposed"), frozenset)
    assert all(isinstance(v, frozenset) for v in
               [contract.allowed_transitions_from(s) for s in contract.CANDIDATE_STATUSES])


def test_R3_the_semantics_records_are_immutable_and_the_functions_are_sync():
    semantics = contract.semantics_for("accepted")
    assert dataclasses.is_dataclass(semantics)
    with pytest.raises(dataclasses.FrozenInstanceError):
        semantics.enters_resolution = False  # type: ignore[misc]

    for fn in (contract.review_decision_to_status, contract.allowed_transitions_from,
               contract.can_transition_candidate_status, contract.is_terminal_candidate_status,
               contract.next_candidate_gate, contract.semantics_for):
        assert not inspect.iscoroutinefunction(fn), fn.__name__


# ===========================================================================
# S — the migration is the storage authority, and the two must agree
# ===========================================================================
def test_S_the_contract_vocabulary_equals_the_gate7b_016_check():
    """Two-way alignment: parse the values out of the migration's CHECK and
    compare. If either side gains or loses a value, this fails."""
    sql = MIGRATION.read_text(encoding="utf-8")
    match = re.search(r"ck_dc_status CHECK \(\s*status IN \(([^)]+)\)", sql)
    assert match, "the ck_dc_status CHECK was not found — has the migration changed?"

    from_sql = tuple(re.findall(r"'([a-z_]+)'", match.group(1)))
    assert from_sql == contract.CANDIDATE_STATUSES
    assert set(from_sql) == {"proposed", "accepted", "rejected", "deferred"}


def test_S2_the_migration_declares_the_candidate_status_column_and_nothing_else():
    """A second status-like column on the candidate table would create a second
    authority for the same question."""
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "status             VARCHAR(16) NOT NULL DEFAULT 'proposed'" in sql
    assert sql.count("CHECK (") >= 4
