"""Schema contract tests for parallel paper-evidence extraction runs."""

from __future__ import annotations

import asyncio
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError
from sqlalchemy.dialects import postgresql

from app.models import PaperEvidenceExtractionItem, PaperEvidenceExtractionRun
from app.schemas.paper_evidence_extraction import PaperEvidenceExtractionRunRequest
from app.services.paper_evidence_extraction_run_service import create_run, get_run_detail


MIGRATION_PATH = (
    Path(__file__).parent.parent
    / "migrations"
    / "20260812_paper_evidence_extraction_runs.sql"
)


def _python_default(model: type, column_name: str):
    default = model.__table__.c[column_name].default
    assert default is not None
    return default.arg


def _canonical_type(type_name: str) -> str:
    aliases = {
        "INT": "INTEGER",
        "TIMESTAMPTZ": "TIMESTAMP WITH TIME ZONE",
    }
    normalized = " ".join(type_name.upper().split())
    return aliases.get(normalized, normalized)


def _canonical_default(value):
    if value is None:
        return None
    if isinstance(value, uuid.UUID):
        return "generated_uuid"
    if isinstance(value, dict):
        return value
    if not isinstance(value, str):
        return value

    normalized = value.strip().lower()
    if normalized == "gen_random_uuid()":
        return "generated_uuid"
    if normalized == "now()":
        return "now"
    if normalized == "'{}'::jsonb":
        return {}
    if normalized in {"true", "false"}:
        return normalized == "true"
    if re.fullmatch(r"-?\d+", normalized):
        return int(normalized)
    if normalized.startswith("'") and normalized.endswith("'"):
        return normalized[1:-1]
    return normalized


def _orm_column_contract(model: type) -> dict[str, dict[str, object]]:
    contract = {}
    dialect = postgresql.dialect()
    for column in model.__table__.c:
        default = None
        if column.server_default is not None:
            default = str(column.server_default.arg.compile(dialect=dialect))
        elif column.default is not None:
            value = column.default.arg
            if callable(value):
                value = value(None)
            default = value
        contract[column.name] = {
            "type": _canonical_type(column.type.compile(dialect=dialect)),
            "nullable": column.nullable,
            "default": _canonical_default(default),
        }
    return contract


def _migration_column_contract(
    sql: str, table_name: str
) -> dict[str, dict[str, object]]:
    match = re.search(
        rf"CREATE TABLE IF NOT EXISTS {re.escape(table_name)}\s*\((.*?)\n\);",
        sql,
        flags=re.IGNORECASE | re.DOTALL,
    )
    assert match is not None, f"missing CREATE TABLE for {table_name}"

    contract = {}
    for raw_line in match.group(1).splitlines():
        declaration = raw_line.strip().rstrip(",")
        if not declaration or declaration.upper().startswith("CONSTRAINT "):
            continue
        name, type_name, *_ = declaration.split(maxsplit=2)
        upper_declaration = declaration.upper()
        default_match = re.search(r"\bDEFAULT\s+(\S+)", declaration, re.IGNORECASE)
        contract[name] = {
            "type": _canonical_type(type_name),
            "nullable": (
                "NOT NULL" not in upper_declaration
                and "PRIMARY KEY" not in upper_declaration
            ),
            "default": _canonical_default(
                default_match.group(1) if default_match else None
            ),
        }
    return contract


def test_run_model_columns_and_defaults():
    table = PaperEvidenceExtractionRun.__table__

    assert table.name == "paper_evidence_extraction_runs"
    assert set(table.c.keys()) == {
        "id",
        "target_type",
        "target_id",
        "mode",
        "status",
        "total_items",
        "completed_items",
        "evidence_hit_items",
        "no_evidence_items",
        "failed_items",
        "requested_concurrency",
        "active_concurrency",
        "cancel_requested",
        "request_json",
        "created_at",
        "updated_at",
        "started_at",
        "finished_at",
    }
    assert _python_default(PaperEvidenceExtractionRun, "mode") == "function"
    assert _python_default(PaperEvidenceExtractionRun, "status") == "queued"
    for column_name in (
        "total_items",
        "completed_items",
        "evidence_hit_items",
        "no_evidence_items",
        "failed_items",
        "active_concurrency",
    ):
        assert _python_default(PaperEvidenceExtractionRun, column_name) == 0
    assert _python_default(PaperEvidenceExtractionRun, "requested_concurrency") == 4
    assert _python_default(PaperEvidenceExtractionRun, "cancel_requested") is False
    assert _python_default(PaperEvidenceExtractionRun, "request_json")(None) == {}
    assert table.c.started_at.nullable
    assert table.c.finished_at.nullable


def test_item_model_columns_defaults_and_constraints():
    table = PaperEvidenceExtractionItem.__table__

    assert table.name == "paper_evidence_extraction_items"
    assert set(table.c.keys()) == {
        "id",
        "run_id",
        "item_index",
        "pmid",
        "pmcid",
        "doi",
        "title",
        "paper_json",
        "status",
        "progress_percent",
        "attempt_count",
        "result_json",
        "error_code",
        "error_message",
        "stage_timings_json",
        "started_at",
        "finished_at",
        "updated_at",
    }
    assert _python_default(PaperEvidenceExtractionItem, "paper_json")(None) == {}
    assert _python_default(PaperEvidenceExtractionItem, "status") == "queued"
    assert _python_default(PaperEvidenceExtractionItem, "progress_percent") == 0
    assert _python_default(PaperEvidenceExtractionItem, "attempt_count") == 0
    assert _python_default(PaperEvidenceExtractionItem, "stage_timings_json")(None) == {}
    assert table.c.result_json.nullable

    foreign_key = next(iter(table.c.run_id.foreign_keys))
    assert foreign_key.target_fullname == "paper_evidence_extraction_runs.id"
    assert foreign_key.ondelete == "CASCADE"
    assert any(
        constraint.name == "uq_paper_evidence_extraction_items_run_index"
        and {column.name for column in constraint.columns} == {"run_id", "item_index"}
        for constraint in table.constraints
    )
    assert {
        (index.name, tuple(column.name for column in index.columns))
        for index in table.indexes
    } >= {
        ("idx_paper_evidence_extraction_items_run_index", ("run_id", "item_index")),
        ("idx_paper_evidence_extraction_items_run_status", ("run_id", "status")),
    }


def test_run_status_index_registered_in_metadata():
    indexes = PaperEvidenceExtractionRun.__table__.indexes
    assert any(
        index.name == "idx_paper_evidence_extraction_runs_status"
        and tuple(column.name for column in index.columns) == ("status",)
        for index in indexes
    )


def test_migration_is_idempotent_and_matches_metadata():
    sql = MIGRATION_PATH.read_text(encoding="utf-8")
    normalized = " ".join(sql.lower().split())

    assert normalized.count("create table if not exists") == 2
    assert normalized.count("create index if not exists") >= 3
    assert "paper_evidence_extraction_runs" in normalized
    assert "paper_evidence_extraction_items" in normalized
    assert "references paper_evidence_extraction_runs(id) on delete cascade" in normalized
    assert "unique (run_id, item_index)" in normalized
    for default_fragment in (
        "mode varchar(16) not null default 'function'",
        "status varchar(32) not null default 'queued'",
        "requested_concurrency int not null default 4",
        "cancel_requested boolean not null default false",
        "request_json jsonb not null default '{}'::jsonb",
        "paper_json jsonb not null default '{}'::jsonb",
        "stage_timings_json jsonb not null default '{}'::jsonb",
    ):
        assert default_fragment in normalized

    for model in (PaperEvidenceExtractionRun, PaperEvidenceExtractionItem):
        assert _migration_column_contract(
            sql, model.__tablename__
        ) == _orm_column_contract(
            model
        )


def test_run_request_validates_defaults_and_limits():
    request = PaperEvidenceExtractionRunRequest(
        target_type="region_function",
        target_id=uuid.uuid4(),
        papers=[{"pmid": "123"}],
    )

    assert request.mode == "function"
    assert request.concurrency == 4
    assert request.only_oa is False
    assert request.stop_after_strong_support is False

    for invalid in (
        {"papers": []},
        {"papers": [{"pmid": str(i)} for i in range(21)]},
        {"papers": [{"pmid": "123"}], "mode": "unsupported"},
        {"papers": [{"pmid": "123"}], "concurrency": 0},
        {"papers": [{"pmid": "123"}], "concurrency": 7},
    ):
        with pytest.raises(ValidationError):
            PaperEvidenceExtractionRunRequest(
                target_type="region_function",
                target_id=uuid.uuid4(),
                **invalid,
            )


def test_create_run_inserts_ordered_queued_items_in_one_commit():
    session = MagicMock()
    session.add_all = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock(side_effect=RuntimeError("refresh should not run"))
    session.rollback = AsyncMock()
    request = PaperEvidenceExtractionRunRequest(
        target_type="region_function",
        target_id=uuid.uuid4(),
        papers=[
            {"pmid": "111", "title": "First", "abstract": "A"},
            {"doi": "10.1/second", "pmcid": "PMC2", "title": "Second"},
        ],
        only_oa=True,
        stop_after_strong_support=True,
        mode="existence",
        concurrency=2,
    )

    response = asyncio.run(create_run(session, request))

    run = session.add.call_args.args[0]
    items = session.add_all.call_args.args[0]
    assert isinstance(run, PaperEvidenceExtractionRun)
    assert response.run_id == run.id
    assert response.status == "queued"
    assert response.total_items == 2
    assert run.total_items == 2
    assert run.requested_concurrency == 2
    assert run.request_json == request.model_dump(mode="json")
    assert "api_key" not in run.request_json
    assert [item.item_index for item in items] == [0, 1]
    assert [item.status for item in items] == ["queued", "queued"]
    assert [item.paper_json["title"] for item in items] == ["First", "Second"]
    assert items[0].pmid == "111"
    assert items[1].pmcid == "PMC2"
    session.commit.assert_awaited_once()
    session.flush.assert_awaited_once()
    session.refresh.assert_not_awaited()
    session.rollback.assert_not_awaited()


def test_create_run_rolls_back_and_reraises_commit_failure():
    session = MagicMock()
    session.add_all = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock(side_effect=RuntimeError("commit failed"))
    session.refresh = AsyncMock()
    session.rollback = AsyncMock()
    request = PaperEvidenceExtractionRunRequest(
        target_type="region_function",
        target_id=uuid.uuid4(),
        papers=[{"pmid": "111"}],
    )

    with pytest.raises(RuntimeError, match="^commit failed$"):
        asyncio.run(create_run(session, request))

    session.rollback.assert_awaited_once()
    session.refresh.assert_not_awaited()


def test_get_run_detail_orders_items_and_aggregates_progress():
    now = datetime.now(timezone.utc)
    run_id = uuid.uuid4()
    run = PaperEvidenceExtractionRun(
        id=run_id,
        target_type="region_function",
        target_id=uuid.uuid4(),
        mode="function",
        status="running",
        total_items=2,
        completed_items=1,
        evidence_hit_items=1,
        no_evidence_items=0,
        failed_items=0,
        requested_concurrency=4,
        active_concurrency=1,
        cancel_requested=False,
        request_json={},
        created_at=now,
        updated_at=now,
    )
    later = PaperEvidenceExtractionItem(
        id=uuid.uuid4(),
        run_id=run_id,
        item_index=1,
        paper_json={"pmid": "2"},
        status="running",
        progress_percent=50,
        attempt_count=1,
        stage_timings_json={"retrieval_ms": 20},
        updated_at=now,
    )
    first = PaperEvidenceExtractionItem(
        id=uuid.uuid4(),
        run_id=run_id,
        item_index=0,
        paper_json={"pmid": "1"},
        status="completed",
        progress_percent=100,
        attempt_count=1,
        result_json={"direction": "supports"},
        stage_timings_json={},
        updated_at=now,
    )
    scalars = MagicMock()
    scalars.all.return_value = [later, first]
    execute_result = MagicMock()
    execute_result.scalars.return_value = scalars
    session = MagicMock()
    session.get = AsyncMock(return_value=run)
    session.execute = AsyncMock(return_value=execute_result)

    detail = asyncio.run(get_run_detail(session, run_id))

    assert [item.item_index for item in detail.items] == [0, 1]
    assert detail.progress_percent == 75.0
    assert detail.items[0].result_json == {"direction": "supports"}
    assert detail.items[1].stage_timings_json == {"retrieval_ms": 20}


@pytest.mark.parametrize(
    "terminal_status",
    ["completed", "partially_failed", "failed", "cancelled"],
)
def test_terminal_run_progress_is_100_and_unknown_run_raises(terminal_status):
    now = datetime.now(timezone.utc)
    run_id = uuid.uuid4()
    run = PaperEvidenceExtractionRun(
        id=run_id,
        target_type="region_function",
        target_id=uuid.uuid4(),
        mode="function",
        status=terminal_status,
        total_items=1,
        completed_items=0,
        evidence_hit_items=0,
        no_evidence_items=0,
        failed_items=1,
        requested_concurrency=1,
        active_concurrency=0,
        cancel_requested=False,
        request_json={},
        created_at=now,
        updated_at=now,
    )
    item = PaperEvidenceExtractionItem(
        id=uuid.uuid4(),
        run_id=run_id,
        item_index=0,
        paper_json={},
        status="failed",
        progress_percent=25,
        attempt_count=1,
        stage_timings_json={},
        updated_at=now,
    )
    scalars = MagicMock()
    scalars.all.return_value = [item]
    execute_result = MagicMock()
    execute_result.scalars.return_value = scalars
    session = MagicMock()
    session.get = AsyncMock(return_value=run)
    session.execute = AsyncMock(return_value=execute_result)

    detail = asyncio.run(get_run_detail(session, run_id))
    assert detail.progress_percent == 100.0

    session.get.return_value = None
    with pytest.raises(ValueError, match="^extraction run not found$"):
        asyncio.run(get_run_detail(session, uuid.uuid4()))


def test_execute_run_bounds_concurrency_and_isolates_failures(monkeypatch):
    from types import SimpleNamespace

    from app.services import paper_evidence_extraction_run_service as svc

    run_id = uuid.uuid4()
    item_ids = [uuid.uuid4() for _ in range(20)]
    now = datetime.now(timezone.utc)
    run = PaperEvidenceExtractionRun(
        id=run_id,
        target_type="region_function",
        target_id=uuid.uuid4(),
        mode="function",
        status="queued",
        total_items=20,
        completed_items=0,
        evidence_hit_items=0,
        no_evidence_items=0,
        failed_items=0,
        requested_concurrency=4,
        active_concurrency=0,
        cancel_requested=False,
        request_json={
            "target_type": "region_function",
            "target_id": str(uuid.uuid4()),
            "papers": [{"pmid": str(i)} for i in range(20)],
            "only_oa": False,
            "stop_after_strong_support": False,
            "mode": "function",
            "concurrency": 4,
        },
        created_at=now,
        updated_at=now,
    )
    items = [
        PaperEvidenceExtractionItem(
            id=item_id,
            run_id=run_id,
            item_index=idx,
            paper_json={"pmid": str(idx)},
            status="queued",
            progress_percent=0,
            attempt_count=0,
            stage_timings_json={},
            updated_at=now,
        )
        for idx, item_id in enumerate(item_ids)
    ]
    fail_id = item_ids[7]
    active = 0
    max_active = 0
    lock = asyncio.Lock()

    async def fake_extract_item(*, item_id, sem_paper, stop_event, **kwargs):
        nonlocal active, max_active
        async with sem_paper:
            async with lock:
                active += 1
                max_active = max(max_active, active)
            await asyncio.sleep(0.02)
            async with lock:
                active -= 1
            item = next(i for i in items if i.id == item_id)
            if item_id == fail_id:
                item.status = "failed"
                item.progress_percent = 100
                item.error_code = "INJECTED"
            else:
                item.status = "completed"
                item.progress_percent = 100
                item.result_json = {
                    "passages": [],
                    "coverage_summary": {"overall_direction": "supports"},
                }
            item.finished_at = datetime.now(timezone.utc)

    class _Session:
        async def get(self, model, pk):
            if model is PaperEvidenceExtractionRun and pk == run_id:
                return run
            if model is PaperEvidenceExtractionItem:
                return next((i for i in items if i.id == pk), None)
            return None

        async def execute(self, stmt):
            result = MagicMock()
            scalars = MagicMock()
            scalars.all.return_value = list(items)
            result.scalars.return_value = scalars
            return result

        async def commit(self):
            return None

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

    monkeypatch.setattr("app.database.AsyncSessionLocal", _Session)
    monkeypatch.setattr(
        svc.pes,
        "build_retrieval_context",
        AsyncMock(return_value={"claim_text": "c", "claim_components": []}),
    )
    monkeypatch.setattr(
        svc,
        "get_settings",
        lambda: SimpleNamespace(
            paper_extraction_worker_concurrency=4,
            paper_extraction_fetch_concurrency=6,
            paper_extraction_llm_concurrency=4,
        ),
    )

    asyncio.run(svc.execute_run(run_id, extract_item=fake_extract_item))

    assert max_active == 4
    assert sum(1 for i in items if i.status == "completed") == 19
    assert sum(1 for i in items if i.status == "failed") == 1


def test_cancel_run_marks_queued_items_and_keeps_completed():
    from app.services import paper_evidence_extraction_run_service as svc

    now = datetime.now(timezone.utc)
    run_id = uuid.uuid4()
    run = PaperEvidenceExtractionRun(
        id=run_id,
        target_type="region_function",
        target_id=uuid.uuid4(),
        mode="function",
        status="running",
        total_items=2,
        completed_items=1,
        evidence_hit_items=1,
        no_evidence_items=0,
        failed_items=0,
        requested_concurrency=4,
        active_concurrency=0,
        cancel_requested=False,
        request_json={},
        created_at=now,
        updated_at=now,
    )
    done = PaperEvidenceExtractionItem(
        id=uuid.uuid4(),
        run_id=run_id,
        item_index=0,
        paper_json={"pmid": "1"},
        status="completed",
        progress_percent=100,
        attempt_count=1,
        result_json={"ok": True},
        stage_timings_json={},
        updated_at=now,
    )
    queued = PaperEvidenceExtractionItem(
        id=uuid.uuid4(),
        run_id=run_id,
        item_index=1,
        paper_json={"pmid": "2"},
        status="queued",
        progress_percent=0,
        attempt_count=0,
        stage_timings_json={},
        updated_at=now,
    )
    items = [done, queued]
    scalars = MagicMock()
    scalars.all.return_value = items
    execute_result = MagicMock()
    execute_result.scalars.return_value = scalars
    session = MagicMock()
    session.get = AsyncMock(return_value=run)
    session.execute = AsyncMock(return_value=execute_result)
    session.commit = AsyncMock()

    detail = asyncio.run(svc.cancel_run(session, run_id))
    assert run.cancel_requested is True
    assert queued.status == "cancelled"
    assert done.status == "completed"
    assert done.result_json == {"ok": True}
    assert detail.items[1].status == "cancelled"


def test_extraction_run_api_create_get_cancel_retry(monkeypatch):
    from types import SimpleNamespace

    from fastapi.testclient import TestClient

    from app.main import app
    from app.schemas.paper_evidence_extraction import (
        PaperEvidenceExtractionItemDetail,
        PaperEvidenceExtractionRunDetail,
        PaperEvidenceExtractionStartResponse,
    )
    from app.services import paper_evidence_extraction_run_service as svc

    run_id = uuid.uuid4()
    target_id = uuid.uuid4()
    now = datetime.now(timezone.utc)
    started = PaperEvidenceExtractionStartResponse(
        run_id=run_id,
        status="queued",
        total_items=1,
        requested_concurrency=4,
        created_at=now,
    )
    detail = PaperEvidenceExtractionRunDetail(
        id=run_id,
        target_type="region_function",
        target_id=target_id,
        mode="function",
        status="completed",
        total_items=1,
        completed_items=1,
        evidence_hit_items=0,
        no_evidence_items=0,
        failed_items=1,
        requested_concurrency=4,
        active_concurrency=0,
        cancel_requested=False,
        created_at=now,
        updated_at=now,
        started_at=now,
        finished_at=now,
        progress_percent=100.0,
        items=[
            PaperEvidenceExtractionItemDetail(
                id=uuid.uuid4(),
                run_id=run_id,
                item_index=0,
                pmid="1",
                paper_json={"pmid": "1"},
                status="failed",
                progress_percent=100,
                attempt_count=1,
                stage_timings_json={},
                updated_at=now,
            )
        ],
    )

    monkeypatch.setattr(
        "app.routers.ontology.get_settings",
        lambda: SimpleNamespace(ontology_role="reviewer"),
    )
    monkeypatch.setattr(svc, "create_run", AsyncMock(return_value=started))
    monkeypatch.setattr(svc, "execute_run_background", AsyncMock())
    monkeypatch.setattr(svc, "get_run_detail", AsyncMock(return_value=detail))
    monkeypatch.setattr(svc, "cancel_run", AsyncMock(return_value=detail))
    monkeypatch.setattr(
        svc,
        "retry_failed_items",
        AsyncMock(return_value={"run_id": str(run_id), "retried": 1, "status": "queued"}),
    )

    client = TestClient(app, raise_server_exceptions=False)
    create = client.post(
        "/api/ontology/evidence/extraction-runs",
        json={
            "target_type": "region_function",
            "target_id": str(target_id),
            "papers": [{"pmid": "1"}],
        },
    )
    assert create.status_code == 202, create.text
    assert create.json()["run_id"] == str(run_id)

    got = client.get(f"/api/ontology/evidence/extraction-runs/{run_id}")
    assert got.status_code == 200
    assert got.json()["failed_items"] == 1

    cancel = client.post(f"/api/ontology/evidence/extraction-runs/{run_id}/cancel")
    assert cancel.status_code == 200

    retry = client.post(f"/api/ontology/evidence/extraction-runs/{run_id}/retry-failed")
    assert retry.status_code == 200
    assert retry.json()["retried"] == 1
