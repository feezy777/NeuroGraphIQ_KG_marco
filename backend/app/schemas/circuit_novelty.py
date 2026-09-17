"""Circuit semantic novelty — the OUTPUT CONTRACT of the novelty assessor.

What this is
------------
After ONE successful Discovery run, decide for each of its Circuit candidates
whether it is genuinely new relative to every EARLIER completed run of the same
(seed, discovery_view). It answers a question about a COUNT:

    how many new circuit concepts did this round actually add?

What this is NOT
----------------
Not validation, not canonicalization, not deduplication and not a review
decision. It writes nothing, merges nothing, deletes nothing and changes no
candidate status. Discovery stays RECALL FIRST: every structurally valid Raw
Candidate stays stored exactly as the model produced it, whatever this layer
concludes about it.

The four classes
----------------
    NEW             a meaningfully distinct Circuit concept
    ALIAS           the same Circuit concept under another established name
    REFORMULATION   the same underlying concept expressed differently
    BORDERLINE      possibly distinct, on insufficient basis to collapse

and the asymmetry that makes this RECALL-FIRST rather than deduplication::

    semantic_new_count = NEW + BORDERLINE

ALIAS and REFORMULATION are the only classes that assert "we already had this",
so they are the only ones that must name what they match. Everything else
counts as novelty, and a case too close to call counts as novelty. The cost of
missing a genuinely new circuit is a prematurely stopped View; the cost of
carrying an extra Raw Candidate is one more row for a later, evidence-backed
layer to judge. Those costs are not symmetric, so neither is this rule.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

#: Our own constructed output: strict, because nothing here is model-authored.
_STRICT = ConfigDict(extra="forbid")

#: The model's verdict payload. Deliberately NOT extra="forbid".
#:
#: The discovery contract rejects an unknown key because an unexpected field
#: there is drift in the KNOWLEDGE contract. This is different in kind: a
#: verdict is our own diagnostic annotation over candidates that are already
#: stored, so a stray key cannot corrupt anything — it would only throw away a
#: count. Live model output added an unknown key to a strict contract twice
#: (a null `relation_note`, then a `RECURRENT` topology), and both times a whole
#: response died for it. The known fields below are still required and still
#: validated; only unrecognised extras are ignored.
_LENIENT = ConfigDict(extra="ignore")

NoveltyClass = Literal["NEW", "ALIAS", "REFORMULATION", "BORDERLINE"]
NOVELTY_CLASSES: tuple[str, ...] = ("NEW", "ALIAS", "REFORMULATION", "BORDERLINE")

#: Classes that count toward semantic novelty. See the module docstring.
NOVELTY_CLASSES_COUNTING_AS_NEW: tuple[str, ...] = ("NEW", "BORDERLINE")

#: The classes that make a claim about the PAST ("this was already found"), and
#: therefore must name the earlier candidate they are claiming to match.
NOVELTY_CLASSES_REQUIRING_A_MATCH: tuple[str, ...] = ("ALIAS", "REFORMULATION")


class ModelNoveltyVerdict(BaseModel):
    """One verdict as the MODEL returned it, before cross-checking."""

    model_config = _LENIENT

    candidate_id: str
    novelty_class: NoveltyClass
    #: Null unless the class claims a match. The assessor verifies that a
    #: non-null id exists in the prior pool and that a null one is allowed by
    #: the class — a claim about the past must point at something real.
    matched_prior_candidate_id: str | None = None
    short_reason: str


class ModelNoveltyResponse(BaseModel):
    """The model's whole reply: one verdict per Circuit in the target run."""

    model_config = _LENIENT

    verdicts: list[ModelNoveltyVerdict] = Field(default_factory=list)


class CircuitNoveltyVerdict(BaseModel):
    """One assessed Circuit. `matched_prior_run_id` is filled in by the
    assessor from the prior candidate's own run — the model is never asked for
    it, so a run id here cannot be invented."""

    model_config = _STRICT

    candidate_id: str
    local_id: str | None = None
    name: str
    novelty_class: NoveltyClass
    matched_prior_candidate_id: str | None = None
    matched_prior_run_id: str | None = None
    short_reason: str

    @property
    def counts_as_new(self) -> bool:
        return self.novelty_class in NOVELTY_CLASSES_COUNTING_AS_NEW


class CircuitNoveltyAssessment(BaseModel):
    """The assessor's result for one target run. Read-only by construction."""

    model_config = _STRICT

    target_run_id: str
    seed_entity_id: str
    #: Derived from the stored strategy identifier; None when it is not one this
    #: build can read (a foreign family), which is reported rather than guessed.
    discovery_view: str | None = None
    strategy_identifier: str

    raw_circuit_count: int
    prior_circuit_count: int
    prior_run_count: int

    NEW_count: int
    ALIAS_count: int
    REFORMULATION_count: int
    BORDERLINE_count: int
    #: NEW + BORDERLINE. Recomputed from `verdicts` and checked below, so the
    #: headline number can never disagree with the rows under it.
    semantic_new_count: int

    verdicts: list[CircuitNoveltyVerdict]

    @model_validator(mode="after")
    def _headline_numbers_match_the_verdicts(self) -> "CircuitNoveltyAssessment":
        if self.raw_circuit_count != len(self.verdicts):
            raise ValueError(
                f"raw_circuit_count {self.raw_circuit_count} != "
                f"{len(self.verdicts)} verdicts"
            )
        tallies = {
            name: sum(1 for v in self.verdicts if v.novelty_class == name)
            for name in NOVELTY_CLASSES
        }
        for name, counted in tallies.items():
            declared = getattr(self, f"{name}_count")
            if declared != counted:
                raise ValueError(f"{name}_count {declared} != {counted} verdicts")
        expected = tallies["NEW"] + tallies["BORDERLINE"]
        if self.semantic_new_count != expected:
            raise ValueError(
                f"semantic_new_count {self.semantic_new_count} != NEW+BORDERLINE "
                f"({expected})"
            )
        return self


def semantic_new_count_of(verdicts: list[CircuitNoveltyVerdict]) -> int:
    """NEW + BORDERLINE. The one place the RECALL-FIRST rule is applied."""
    return sum(1 for v in verdicts if v.counts_as_new)


# ===========================================================================
# Persisted form — what a stored assessment looks like on the way out
# ===========================================================================
# The tables hold INTERNAL keys (candidate_pk, run_pk) because a verdict is a
# relational claim. A caller gets PUBLIC ids only: an internal key is never
# returned, so a client cannot grow a dependency on a row number that is not
# part of any contract.
class PersistedNoveltyVerdict(BaseModel):
    """One stored verdict, with the ids a caller may actually use."""

    model_config = _STRICT

    candidate_id: str
    local_id: str | None = None
    name: str
    novelty_class: NoveltyClass
    matched_prior_candidate_id: str | None = None
    #: The matched circuit's run. Read from the matched candidate's own row, so
    #: it cannot disagree with it — the same guarantee the live assessor gives.
    matched_prior_run_id: str | None = None
    short_reason: str

    @property
    def counts_as_new(self) -> bool:
        return self.novelty_class in NOVELTY_CLASSES_COUNTING_AS_NEW


class NoveltySummary(BaseModel):
    """The stored counts of one assessment, without loading its verdicts.

    Carries the same arithmetic guard as the full assessment but NOT the
    "counts equal the verdict rows" check, which needs the rows themselves.
    """

    model_config = _STRICT

    assessment_id: str
    target_run_id: str
    seed_entity_id: str
    discovery_view: str
    query_strategy_version: str
    provider: str
    model_name: str
    assessor_prompt_key: str
    assessor_prompt_version: str
    raw_circuit_count: int
    NEW_count: int
    ALIAS_count: int
    REFORMULATION_count: int
    BORDERLINE_count: int
    semantic_new_count: int
    prior_completed_run_count: int
    prior_circuit_count: int
    created_at: datetime

    @model_validator(mode="after")
    def _arithmetic_holds(self) -> "NoveltySummary":
        if self.raw_circuit_count != (
            self.NEW_count + self.ALIAS_count
            + self.REFORMULATION_count + self.BORDERLINE_count
        ):
            raise ValueError("class counts do not sum to raw_circuit_count")
        if self.semantic_new_count != self.NEW_count + self.BORDERLINE_count:
            raise ValueError("semantic_new_count != NEW + BORDERLINE")
        return self


class PersistedNoveltyAssessment(NoveltySummary):
    """A stored assessment and every verdict it holds."""

    verdicts: list[PersistedNoveltyVerdict]

    @model_validator(mode="after")
    def _counts_match_the_verdicts(self) -> "PersistedNoveltyAssessment":
        if self.raw_circuit_count != len(self.verdicts):
            raise ValueError(
                f"stored raw_circuit_count {self.raw_circuit_count} != "
                f"{len(self.verdicts)} stored verdicts"
            )
        for name in NOVELTY_CLASSES:
            counted = sum(1 for v in self.verdicts if v.novelty_class == name)
            declared = getattr(self, f"{name}_count")
            if declared != counted:
                raise ValueError(
                    f"stored {name}_count {declared} != {counted} verdicts"
                )
        return self
