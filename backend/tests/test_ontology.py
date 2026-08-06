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
    def __init__(self, rows):
        self._rows = rows

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


def test_merge_term_moves_groundings_and_deletes_source():
    source = OntologyTerm(id=uuid.uuid4(), term_code="ng:func:a", canonical_term_en="a", status="proposed")
    target = OntologyTerm(id=uuid.uuid4(), term_code="ng:func:b", canonical_term_en="b", status="active")
    src_syn = OntologyTermSynonym(id=uuid.uuid4(), term_id=source.id, synonym_text="a-syn", lang="en", match_type="synonym")
    session = SessionStub(
        execute_results=[FakeResult([src_syn]), FakeResult([]), FakeResult([]), FakeResult([]), FakeResult([]), FakeResult([])],
        get_map={(OntologyTerm, source.id): source, (OntologyTerm, target.id): target},
    )

    result = asyncio.run(svc.merge_term(session, source.id, target.id))

    assert result is target
    assert source in session.deleted


def test_run_deterministic_grounding_batch_counts():
    term = OntologyTerm(id=uuid.uuid4(), term_code="ng:func:memory", canonical_term_en="memory", status="active")
    row_grounded = MirrorCircuitFunctionStub(id=uuid.uuid4(), function_term_en="memory")
    row_ungrounded = MirrorCircuitFunctionStub(id=uuid.uuid4(), function_term_en="weird phrase")
    session = SessionStub(
        execute_results=[
            FakeResult([term]),  # active terms
            FakeResult([]),  # synonyms
            FakeResult([row_grounded, row_ungrounded]),  # rows to process
            FakeResult([]),  # delete existing groundings
        ]
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
    session = SessionStub(
        execute_results=[FakeResult([term]), FakeResult([]), FakeResult([])],
        get_map={(MirrorCircuitFunctionModel, row.id): row},
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


from app.models.mirror_macro_clinical import MirrorCircuitFunction as MirrorCircuitFunctionModel
