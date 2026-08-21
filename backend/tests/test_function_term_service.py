"""P1.3 unified Function term resolver, auto-propose, anchoring & backfill tests.

Covers the 17 acceptance cases from the P1.3 brief: unit tests for the match
ladder / guards (no DB), and DB-backed tests for write-path anchoring, merged
redirect dup-safety, backfill idempotency and Final schema.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest

from app.database import AsyncSessionLocal
from app.models.mirror_kg import (
    MirrorRegionCircuit,
    MirrorRegionConnection,
    MirrorRegionFunction,
)
from app.models.mirror_macro_clinical import (
    MirrorCircuitFunction,
    MirrorProjectionFunction,
)
from app.models.ontology import OntologyTerm, OntologyTermSynonym
from app.schemas.mirror_kg import (
    MirrorPromotionStatus,
    MirrorRegionFunctionCreate,
    MirrorReviewStatus,
    MirrorStatus,
)
from app.schemas.mirror_macro_clinical import (
    MirrorCircuitFunctionCreate,
    MirrorProjectionFunctionCreate,
)
from app.services import function_term_service as fts
from app.services import mirror_kg_service as mks
from app.services import mirror_macro_clinical_service as mmcs

TEST_PREFIX = "p13_test_"

# All P1.3 tests exercise the real resolver / anchoring paths (no AsyncMocks).
pytestmark = pytest.mark.function_term_real


def _run(coro):
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except Exception:
        pass
    return asyncio.run(coro)


# ---------------------------------------------------------------- stubs (unit)


class _FakeResult:
    def __init__(self, rows=None, scalar=None):
        self._rows = list(rows or [])
        self._scalar = scalar

    def scalars(self):
        return self

    def all(self):
        return self._rows

    def scalar_one(self):
        if self._rows:
            return self._rows[0]
        raise ValueError("no rows")

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else self._scalar

    def scalar(self):
        return self._scalar if self._scalar is not None else (self._rows[0] if self._rows else None)


class _SessionStub:
    def __init__(self, get_map=None, execute_results=None):
        self._get_map = get_map or {}
        self._results = list(execute_results or [])
        self.added = []

    async def execute(self, *args, **kwargs):
        if self._results:
            return self._results.pop(0)
        return _FakeResult([])

    async def get(self, model, pk):
        return self._get_map.get((model, pk))

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        pass

    async def commit(self):
        pass


def _term(term_id=None, *, status="active", term_type="function", code=None, name=None, replaced_by=None):
    term = OntologyTerm(
        id=term_id or uuid.uuid4(),
        term_code=code or f"ng:func:{name or 'x'}",
        canonical_term_en=name or "x",
        term_type=term_type,
        status=status,
    )
    if replaced_by:
        term.replaced_by_term_id = replaced_by
    return term


# ---------------------------------------------------------------- unit tests


def test_01_active_canonical_exact_match():
    term = _term(status="active", name="fear extinction", code="ng:func:fear_extinction")
    idx = fts.TermIndex(active_canon={"fear extinction": term.id})
    res = _run(fts.resolve_or_propose_function_term(
        _SessionStub(get_map={(OntologyTerm, term.id): term}),
        "fear_extinction", index=idx,
    ))
    assert res.term_id == term.id
    assert res.state == fts.STATE_GROUNDED_ACTIVE
    assert res.path == ["active_canonical_exact"]


def test_02_active_synonym_exact_match():
    term = _term(status="active", name="fear extinction", code="ng:func:fear_extinction")
    synonym_id = uuid.uuid4()
    idx = fts.TermIndex(active_synonym={"extinction of conditioned fear": term.id})
    res = _run(fts.resolve_or_propose_function_term(
        _SessionStub(get_map={(OntologyTerm, term.id): term}),
        "extinction of conditioned fear", index=idx,
    ))
    assert res.term_id == term.id
    assert res.state == fts.STATE_GROUNDED_ACTIVE
    assert res.path == ["active_synonym_exact"]


def test_03_proposed_canonical_exact_reuse():
    term = _term(status="proposed", name="novel function", code="ng:func:novel_function")
    idx = fts.TermIndex(proposed_canon={"novel function": term.id})
    res = _run(fts.resolve_or_propose_function_term(
        _SessionStub(get_map={(OntologyTerm, term.id): term}),
        "novel function", index=idx,
    ))
    assert res.term_id == term.id
    assert res.state == fts.STATE_GROUNDED_PROPOSED


def test_04_merged_term_resolves_to_canonical():
    canonical = _term(status="active", name="fear extinction", code="ng:func:fear_extinction")
    merged = _term(status="merged", name="fear extinction old", code="ng:func:fear_extinction_old",
                   replaced_by=canonical.id)
    session = _SessionStub(get_map={
        (OntologyTerm, merged.id): merged,
        (OntologyTerm, canonical.id): canonical,
    })
    res = _run(fts.resolve_canonical_function_term(session, merged.id))
    assert res.term_id == canonical.id
    assert res.status == "active"
    assert "merged_redirect" in res.path


def test_05_brain_region_term_rejected():
    region = _term(status="active", term_type="region", name="amygdala", code="ng:region:amygdala")
    session = _SessionStub(get_map={(OntologyTerm, region.id): region})
    res = _run(fts.resolve_canonical_function_term(session, region.id))
    assert res.is_function_term is False
    assert res.state == fts.STATE_INVALID_TYPE


def test_10_auto_propose_creates_proposed_function_term():
    session = _SessionStub(execute_results=[_FakeResult([])])
    res = _run(fts.resolve_or_propose_function_term(
        session, "brand new test function 42", index=fts.TermIndex(),
    ))
    assert res.state == fts.STATE_GROUNDED_PROPOSED
    assert res.status == "proposed"
    assert res.term_code == "ng:func:brand_new_test_function_42"
    assert res.path == ["auto_propose"]
    created = [o for o in session.added if isinstance(o, OntologyTerm)]
    assert len(created) == 1
    assert created[0].term_type == "function"
    assert created[0].status == "proposed"


def test_11_no_semantic_auto_merge():
    # 'fear extinction and emotional regulation' must NOT merge into 'fear extinction'
    target = _term(status="active", name="fear extinction", code="ng:func:fear_extinction")
    idx = fts.TermIndex(active_canon={"fear extinction": target.id})
    session = _SessionStub(
        get_map={(OntologyTerm, target.id): target},
        execute_results=[_FakeResult([])],
    )
    res = _run(fts.resolve_or_propose_function_term(
        session, "fear extinction and emotional regulation", index=idx,
    ))
    assert res.term_id != target.id
    assert res.term_code == "ng:func:fear_extinction_and_emotional_regulation"
    assert res.path == ["auto_propose"]


def test_14_rerun_does_not_create_duplicate_term_code():
    session1 = _SessionStub(execute_results=[_FakeResult([])])
    first = _run(fts.resolve_or_propose_function_term(session1, "p13 unique function 99", index=fts.TermIndex()))
    term = [o for o in session1.added if isinstance(o, OntologyTerm)][0]
    # second run: term_code lookup now finds the existing term
    session2 = _SessionStub(execute_results=[_FakeResult([term])])
    second = _run(fts.resolve_or_propose_function_term(session2, "p13 unique function 99", index=fts.TermIndex()))
    assert second.term_id == first.term_id
    assert second.path == ["term_code_reuse"]
    assert len([o for o in session2.added if isinstance(o, OntologyTerm)]) == 0


# ---------------------------------------------------------------- DB-backed


@pytest.fixture()
def db():
    async def _cleanup():
        async with AsyncSessionLocal() as session:
            for model in (MirrorCircuitFunction, MirrorProjectionFunction, MirrorRegionFunction,
                          MirrorRegionCircuit, MirrorRegionConnection):
                await session.execute(model.__table__.delete().where(
                    model.__table__.c.raw_payload_json["p13_test"].astext.is_not(None)
                ))
            terms = (await session.execute(
                OntologyTerm.__table__.select().where(OntologyTerm.__table__.c.canonical_term_en.like(f"{TEST_PREFIX}%"))
            )).all()
            for t in terms:
                await session.execute(OntologyTermSynonym.__table__.delete().where(
                    OntologyTermSynonym.__table__.c.term_id == t.id
                ))
            await session.execute(
                OntologyTerm.__table__.delete().where(OntologyTerm.__table__.c.canonical_term_en.like(f"{TEST_PREFIX}%"))
            )
            await session.commit()

    yield
    _run(_cleanup())


def _make_region_fn_row(session, *, function_term: str, term_id=None):
    row = MirrorRegionFunction(
        region_candidate_id=None,
        granularity_level="macro_clinical",
        granularity_family="macro",
        source_atlas="test_atlas",
        function_term=function_term,
        function_category="cognitive",
        relation_type="involved_in",
        confidence=0.8,
        mirror_status=MirrorStatus.llm_suggested,
        review_status=MirrorReviewStatus.pending,
        promotion_status=MirrorPromotionStatus.not_promoted,
        raw_payload_json={"p13_test": True},
        term_id=term_id,
    )
    session.add(row)
    return row


def _make_connection_row(session):
    conn = MirrorRegionConnection(
        granularity_level="macro_clinical",
        granularity_family="macro",
        source_atlas="test_atlas",
        connection_type="projection",
        directionality="directed",
        mirror_status=MirrorStatus.llm_suggested,
        review_status=MirrorReviewStatus.pending,
        promotion_status=MirrorPromotionStatus.not_promoted,
        raw_payload_json={"p13_test": True},
    )
    session.add(conn)
    return conn


def _make_circuit_row(session):
    circ = MirrorRegionCircuit(
        granularity_level="macro_clinical",
        granularity_family="macro",
        source_atlas="test_atlas",
        circuit_name="p13 test circuit",
        circuit_type="simple",
        mirror_status=MirrorStatus.llm_suggested,
        review_status=MirrorReviewStatus.pending,
        promotion_status=MirrorPromotionStatus.not_promoted,
        raw_payload_json={"p13_test": True},
    )
    session.add(circ)
    return circ


def _make_active_term(session, name: str) -> OntologyTerm:
    term = OntologyTerm(
        term_code=f"ng:func:{name.replace(' ', '_')}",
        canonical_term_en=name,
        term_type="function",
        status="active",
        created_by="p13_test",
    )
    session.add(term)
    return term


def test_06_relation_text_preserved_on_anchor(db):
    async def _case():
        async with AsyncSessionLocal() as session:
            term = _make_active_term(session, f"{TEST_PREFIX}text kept")
            await session.flush()
            row = _make_region_fn_row(session, function_term=f"{TEST_PREFIX}text kept")
            await session.flush()
            await fts.anchor_function_relation(
                session, target_type="region_function", row=row, created_by="test"
            )
            await session.flush()
            assert row.term_id == term.id
            assert row.function_term == f"{TEST_PREFIX}text kept"
    _run(_case())


def test_07_region_function_write_path_anchors(db):
    async def _case():
        async with AsyncSessionLocal() as session:
            _make_active_term(session, f"{TEST_PREFIX}region fn")
            await session.flush()
            row = await mks.create_mirror_function(session, MirrorRegionFunctionCreate(
                granularity_level="macro_clinical",
                source_atlas="test_atlas",
                function_term=f"{TEST_PREFIX}region fn",
                raw_payload_json={"p13_test": True},
            ))
            assert row.term_id is not None
            assert row.function_term == f"{TEST_PREFIX}region fn"
    _run(_case())


def test_08_projection_function_write_path_anchors(db):
    async def _case():
        async with AsyncSessionLocal() as session:
            _make_active_term(session, f"{TEST_PREFIX}proj fn")
            conn = _make_connection_row(session)
            await session.flush()
            row = await mmcs.create_projection_function(session, MirrorProjectionFunctionCreate(
                projection_id=conn.id,
                granularity_level="macro_clinical",
                granularity_family="macro",
                source_atlas="test_atlas",
                function_term=f"{TEST_PREFIX}proj fn",
                raw_payload_json={"p13_test": True},
            ))
            assert row.term_id is not None
            assert row.function_term == f"{TEST_PREFIX}proj fn"
    _run(_case())


def test_09_circuit_function_write_path_anchors(db):
    async def _case():
        async with AsyncSessionLocal() as session:
            _make_active_term(session, f"{TEST_PREFIX}circ fn")
            circ = _make_circuit_row(session)
            await session.flush()
            row = await mmcs.create_circuit_function(session, MirrorCircuitFunctionCreate(
                circuit_id=circ.id,
                granularity_level="macro_clinical",
                granularity_family="macro",
                source_atlas="test_atlas",
                function_term_en=f"{TEST_PREFIX}circ fn",
                raw_payload_json={"p13_test": True},
            ))
            assert row.term_id is not None
            assert row.function_term_en == f"{TEST_PREFIX}circ fn"
    _run(_case())


def test_12_merged_redirect_dup_safety(db):
    async def _case():
        async with AsyncSessionLocal() as session:
            canonical = _make_active_term(session, f"{TEST_PREFIX}canonical")
            await session.flush()  # canonical.id must exist before linking
            old = OntologyTerm(
                term_code=f"ng:func:{TEST_PREFIX}old",
                canonical_term_en=f"{TEST_PREFIX}old",
                term_type="function",
                status="merged",
                replaced_by_term_id=canonical.id,
                created_by="p13_test",
            )
            session.add(old)
            await session.flush()
            # two relations, same subject+qualifiers: one anchored to merged term, one to canonical
            row_old = _make_region_fn_row(session, function_term=f"{TEST_PREFIX}old text", term_id=old.id)
            row_canon = _make_region_fn_row(session, function_term=f"{TEST_PREFIX}canonical", term_id=canonical.id)
            await session.flush()
            await fts.anchor_function_relation(
                session, target_type="region_function", row=row_old, created_by="test"
            )
            await session.flush()
            # old row must be superseded with duplicate_of audit, canonical row untouched
            assert row_old.mirror_status == MirrorStatus.superseded
            prov = (row_old.raw_payload_json or {}).get("provenance", {})
            assert prov.get("duplicate_of") == str(row_canon.id)
            assert row_canon.term_id == canonical.id
            assert row_canon.mirror_status != MirrorStatus.superseded
    _run(_case())


def test_13_backfill_idempotent(db):
    async def _case():
        async with AsyncSessionLocal() as session:
            term = _make_active_term(session, f"{TEST_PREFIX}backfill")
            await session.flush()
            row = _make_region_fn_row(session, function_term=f"{TEST_PREFIX}backfill")
            await session.flush()
            first = await fts.backfill_function_grounding(
                session, target_type="region_function", batch_size=10, max_batches=1,
                created_by="test",
            )
            await session.flush()
            assert row.term_id == term.id
            assert first["rows_updated"] >= 1
            assert first["proposed_created"] == 0  # matched existing active term

            second = await fts.backfill_function_grounding(
                session, target_type="region_function", batch_size=10, max_batches=2,
                created_by="test",
            )
            assert second["total_scanned"] == 0
    _run(_case())


def test_15_final_tables_have_term_id_column():
    from sqlalchemy import text

    async def _case():
        async with AsyncSessionLocal() as session:
            for table in ("final_region_functions", "final_projection_functions", "final_circuit_functions"):
                rows = (await session.execute(text(
                    "SELECT column_name FROM information_schema.columns "
                    f"WHERE table_name = '{table}' AND column_name = 'term_id'"
                ))).all()
                assert rows, f"{table} missing term_id column"
    _run(_case())


def test_16_legacy_write_path_anchors_via_create(db):
    # llm_to_mirror_service.create_mirror_function_from_llm_item delegates to
    # create_mirror_function; anchoring happens there, so a bare create payload
    # must already carry term_id.
    async def _case():
        async with AsyncSessionLocal() as session:
            _make_active_term(session, f"{TEST_PREFIX}legacy")
            await session.flush()
            row = await mks.create_mirror_function(session, MirrorRegionFunctionCreate(
                granularity_level="macro_clinical",
                source_atlas="test_atlas",
                function_term=f"{TEST_PREFIX}legacy",
                raw_payload_json={"p13_test": True},
            ))
            assert row.term_id is not None
    _run(_case())


def test_17_regression_ontology_service_imports():
    # Ontology center services still importable / callable after rewiring.
    from app.services import ontology_governance_service, ontology_service  # noqa: F401
    assert ontology_service.normalize_term_key("  x  ") == "x"
