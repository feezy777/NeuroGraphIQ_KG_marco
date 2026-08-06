"""Ontology service unit tests (deterministic, no DB, no network)."""

from __future__ import annotations

import asyncio
import uuid

from app.models.ontology import (
    OntologyTerm,
    OntologyTermGrounding,
    OntologyTermSynonym,
)
from app.services import ontology_service as svc


class FakeResult:
    def __init__(self, rows, rowcount=0):
        self._rows = rows
        self.rowcount = rowcount

    def scalars(self):
        return self

    def all(self):
        return self._rows

    def scalar_one(self):
        if not self._rows:
            raise ValueError("no rows")
        return self._rows[0]

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None

    def scalar(self):
        return self._rows[0] if self._rows else None


class SessionStub:
    def __init__(self, execute_results=None, get_map=None):
        self._results = list(execute_results or [])
        self._get_map = get_map or {}
        self.added = []
        self.deleted = []

    async def execute(self, *args, **kwargs):
        if self._results:
            return self._results.pop(0)
        return FakeResult([])

    async def get(self, model, pk):
        return self._get_map.get((model, pk))

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        pass

    async def delete(self, obj):
        self.deleted.append(obj)


def test_normalize_term_key():
    assert svc.normalize_term_key("  Working-Memory  ") == "working memory"
    assert svc.normalize_term_key("MEMORY") == "memory"
    assert svc.normalize_term_key("  ") == ""


def test_term_code_slug():
    assert svc._term_code("Working Memory", "function") == "ng:func:working_memory"
    assert svc._term_code("attention", "function").startswith("ng:func:")


def test_index_lookup_uses_normalized_key():
    term_id = uuid.uuid4()
    index = {"working memory": term_id}
    assert svc._index_lookup(index, "Working-Memory") == term_id
    assert svc._index_lookup(index, "attention") is None


def test_propose_term_returns_existing_active_term():
    existing = OntologyTerm(
        id=uuid.uuid4(),
        term_code="ng:func:memory",
        canonical_term_en="memory",
        status="active",
    )
    session = SessionStub(execute_results=[FakeResult([existing])])

    async def run():
        return await svc.propose_term(
            session,
            canonical_term_en="  MEMORY  ",
            created_by="llm",
        )

    result = asyncio.run(run())

    assert result is existing
    assert session.added == []


def test_propose_term_creates_proposed_when_unknown():
    session = SessionStub(execute_results=[FakeResult([])])

    async def run():
        return await svc.propose_term(
            session,
            canonical_term_en="novel function",
            created_by="llm",
        )

    result = asyncio.run(run())

    assert result.status == "proposed"
    assert result.term_code == "ng:func:novel_function"
    assert result.created_by == "llm"


def test_activate_term():
    term = OntologyTerm(id=uuid.uuid4(), term_code="ng:func:memory", canonical_term_en="memory", status="proposed")
    session = SessionStub(get_map={(OntologyTerm, term.id): term})

    result = asyncio.run(svc.activate_term(session, term.id))

    assert result.status == "active"


def test_deprecate_term():
    term = OntologyTerm(id=uuid.uuid4(), term_code="ng:func:memory", canonical_term_en="memory", status="active")
    session = SessionStub(get_map={(OntologyTerm, term.id): term})

    result = asyncio.run(svc.deprecate_term(session, term.id))

    assert result.status == "deprecated"


def test_merge_term_soft_merges_source_and_audits():
    source = OntologyTerm(id=uuid.uuid4(), term_code="ng:func:a", canonical_term_en="a", status="proposed")
    target = OntologyTerm(id=uuid.uuid4(), term_code="ng:func:b", canonical_term_en="b", status="active")
    src_syn = OntologyTermSynonym(id=uuid.uuid4(), term_id=source.id, synonym_text="a-syn", lang="en", match_type="synonym")
    session = SessionStub(
        execute_results=[
            FakeResult([source, target]),  # row locks (fixed id order)
            FakeResult([src_syn]),  # source synonyms
            FakeResult([]),  # target synonyms
            FakeResult([]),  # source external mappings
            FakeResult([]),  # target external mappings
            FakeResult([], rowcount=1),  # synonyms update
            FakeResult([], rowcount=1),  # external mappings update
            FakeResult([], rowcount=2),  # groundings update
            FakeResult([], rowcount=5),  # business rows update x3
            FakeResult([], rowcount=0),
            FakeResult([], rowcount=0),
        ],
    )

    result = asyncio.run(svc.merge_term(session, source.id, target.id))

    assert result is target
    assert source.status == "merged"
    assert source.replaced_by_term_id == target.id
    assert source not in session.deleted
    assert any(getattr(obj, "action_type", None) == "term.merge" for obj in session.added)


def test_merge_term_idempotent():
    source = OntologyTerm(
        id=uuid.uuid4(), term_code="ng:func:a", canonical_term_en="a",
        status="merged", replaced_by_term_id=None,
    )
    target = OntologyTerm(id=uuid.uuid4(), term_code="ng:func:b", canonical_term_en="b", status="active")
    source.replaced_by_term_id = target.id
    session = SessionStub(execute_results=[FakeResult([source, target])])

    result = asyncio.run(svc.merge_term(session, source.id, target.id))

    assert result is target
    assert source.status == "merged"
    assert session.added == []


def test_merge_term_drops_conflicting_synonym():
    source = OntologyTerm(id=uuid.uuid4(), term_code="ng:func:a", canonical_term_en="a", status="proposed")
    target = OntologyTerm(id=uuid.uuid4(), term_code="ng:func:b", canonical_term_en="b", status="active")
    src_syn = OntologyTermSynonym(id=uuid.uuid4(), term_id=source.id, synonym_text="same", lang="en", match_type="synonym")
    tgt_syn = OntologyTermSynonym(id=uuid.uuid4(), term_id=target.id, synonym_text="same", lang="en", match_type="synonym")
    session = SessionStub(
        execute_results=[
            FakeResult([source, target]),
            FakeResult([src_syn]),
            FakeResult([tgt_syn]),
            FakeResult([]),
            FakeResult([]),
            FakeResult([], rowcount=0),
            FakeResult([], rowcount=0),
            FakeResult([], rowcount=0),
            FakeResult([], rowcount=0),
            FakeResult([], rowcount=0),
            FakeResult([], rowcount=0),
        ],
    )

    asyncio.run(svc.merge_term(session, source.id, target.id))

    assert src_syn in session.deleted


def test_run_deterministic_grounding_batch_counts():
    term = OntologyTerm(id=uuid.uuid4(), term_code="ng:func:memory", canonical_term_en="memory", status="active")
    row_grounded = MirrorCircuitFunctionStub(id=uuid.uuid4(), function_term_en="memory")
    row_ungrounded = MirrorCircuitFunctionStub(id=uuid.uuid4(), function_term_en="weird phrase")
    g1 = OntologyTermGrounding(id=uuid.uuid4(), target_type="circuit_function", target_id=row_grounded.id, term_id=term.id, grounded_by="deterministic", confidence=1.0)
    g2 = OntologyTermGrounding(id=uuid.uuid4(), target_type="circuit_function", target_id=row_ungrounded.id, term_id=None, grounded_by="ungrounded")
    session = SessionStub(
        execute_results=[
            FakeResult([term]),  # active terms
            FakeResult([]),  # synonyms
            FakeResult([row_grounded, row_ungrounded]),  # rows to process
            FakeResult([]),  # existing grounding row 1 (none)
            FakeResult([g1.id]),  # upsert row 1
            FakeResult([]),  # existing grounding row 2 (none)
            FakeResult([g2.id]),  # upsert row 2
        ],
        get_map={
            (OntologyTermGrounding, g1.id): g1,
            (OntologyTermGrounding, g2.id): g2,
        },
    )

    result = asyncio.run(svc.run_deterministic_grounding_batch(session, "circuit_function", limit=10))

    assert result["processed"] == 2
    assert result["grounded"] == 1
    assert result["ungrounded"] == 1
    assert row_grounded.term_id == term.id
    assert row_ungrounded.term_id is None


class MirrorCircuitFunctionStub:
    def __init__(self, id, function_term_en, function_term_cn=None):
        self.id = id
        self.function_term_en = function_term_en
        self.function_term_cn = function_term_cn
        self.term_id = None


def test_ground_deterministic_single():
    term = OntologyTerm(id=uuid.uuid4(), term_code="ng:func:memory", canonical_term_en="memory", status="active")
    row = MirrorCircuitFunctionStub(id=uuid.uuid4(), function_term_en="MEMORY")
    g = OntologyTermGrounding(id=uuid.uuid4(), target_type="circuit_function", target_id=row.id, term_id=term.id, grounded_by="deterministic", confidence=1.0)
    session = SessionStub(
        execute_results=[
            FakeResult([term]),  # active terms
            FakeResult([]),  # synonyms
            FakeResult([]),  # existing grounding (none)
            FakeResult([g.id]),  # upsert
        ],
        get_map={
            (MirrorCircuitFunctionModel, row.id): row,
            (OntologyTermGrounding, g.id): g,
        },
    )

    async def run():
        return await svc.ground_deterministic(
            session,
            target_type="circuit_function",
            target_id=row.id,
            term_text="memory",
        )

    grounding = asyncio.run(run())

    assert grounding.grounded_by == "deterministic"
    assert grounding.term_id == term.id
    assert row.term_id == term.id


def test_auto_grounding_does_not_overwrite_manual():
    existing = OntologyTermGrounding(
        id=uuid.uuid4(), target_type="circuit_function", target_id=uuid.uuid4(),
        term_id=uuid.uuid4(), grounded_by="manual",
    )
    session = SessionStub(execute_results=[FakeResult([existing])])

    async def run():
        return await svc._upsert_grounding(
            session,
            target_type="circuit_function",
            target_id=existing.target_id,
            term_id=None,
            grounded_by="deterministic",
            confidence=None,
            created_by="system",
        )

    result = asyncio.run(run())

    assert result is existing
    assert result.grounded_by == "manual"
    assert session.added == []


from app.models.mirror_macro_clinical import MirrorCircuitFunction as MirrorCircuitFunctionModel
