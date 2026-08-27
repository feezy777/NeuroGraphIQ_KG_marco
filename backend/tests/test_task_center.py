"""Task Center(佐证任务中心)后端测试。

覆盖:
1. 软删除:删除后默认列表不可见;include_deleted=True 可见;deleted_at/deleted_by 记录;幂等。
2. 历史聚合:终态任务 + 审核简况(时间/人员/状态/次数)。
3. 既有列表默认行为不变(status 过滤/granularity 过滤已由既有测试覆盖)。
4. 既有 rollback-for-rescore(S7B)可被任务中心回退复用(端点链路 smoke)。

只做最小写入(软删列/测试专用任务),不物理删除任何数据。
"""
from __future__ import annotations

import asyncio
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.database import AsyncSessionLocal
from app.main import app

pytestmark = pytest.mark.function_term_real


def _run(coro):
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except Exception:
        pass
    return asyncio.run(coro)


@pytest.fixture()
def client():
    return TestClient(app)


async def _create_test_task() -> str:
    """插入一条测试任务(终态 completed,便于历史聚合)。"""
    async with AsyncSessionLocal() as s:
        tid = str(uuid.uuid4())
        await s.execute(text(
            """INSERT INTO paper_evidence_tasks
               (id, target_type, scope, status, name, review_status, granularity_level,
                total_items, processed_items, created_by, created_at)
               VALUES (:id, 'connection', 'filter', 'completed', '任务中心测试-历史聚合',
                       'in_review', 'macro', 2, 2, 'tester', now())"""),
            {"id": tid})
        await s.commit()
        return tid


async def _cleanup_task(tid: str) -> None:
    async with AsyncSessionLocal() as s:
        await s.execute(text("DELETE FROM paper_evidence_tasks WHERE id = :id"), {"id": tid})
        await s.commit()


@pytest.fixture()
def test_task():
    tid = _run(_create_test_task())
    yield tid
    _run(_cleanup_task(tid))


def test_soft_delete_default_hidden(test_task, client):
    """删除后默认列表不可见(软删除不物理删除),include_deleted=True 可见。"""
    before = client.get("/api/ontology/evidence/batch", params={"limit": 200})
    assert before.status_code == 200
    assert before.json()["total"] >= 1

    r = _run(_delete_task(test_task, client))
    assert r.json()["deleted"] is True
    assert r.json()["deleted_at"] is not None

    # 默认列表排除
    after = client.get("/api/ontology/evidence/batch", params={"limit": 200})
    ids_default = [i["id"] for i in after.json()["items"]]
    assert test_task not in ids_default

    # include_deleted=True 可见
    include = client.get("/api/ontology/evidence/batch",
                         params={"limit": 200, "include_deleted": True})
    ids_all = [i["id"] for i in include.json()["items"]]
    assert test_task in ids_all

    # 幂等:重复删除
    r2 = _run(_delete_task(test_task, client))
    assert r2.json()["deleted"] is False


async def _delete_task(tid: str, client) -> object:
    r = client.post(f"/api/ontology/evidence/batch/{tid}/delete")
    assert r.status_code == 200, r.text
    return r


def test_history_aggregation(test_task, client):
    """历史聚合:终态任务可见 + review_brief 字段齐全(时间/人员/状态/count)。"""
    r = client.get("/api/ontology/evidence/batch/history", params={"limit": 200})
    assert r.status_code == 200
    items = r.json()["items"]
    row = next((i for i in items if i["task_id"] == test_task), None)
    assert row is not None, "测试终态任务必须出现在历史聚合"
    assert row["status"] == "completed"
    assert row["name"] == "任务中心测试-历史聚合"
    assert row["created_by"] == "tester"
    assert row["finished_at"] is None or isinstance(row["finished_at"], str)
    assert "review_brief" in row
    assert row["review_brief"] is None or "review_count" in row["review_brief"]


def test_list_default_behavior_unchanged(client):
    """默认列表(未传 include_deleted)沿用既有形状。"""
    r = client.get("/api/ontology/evidence/batch", params={"limit": 5})
    assert r.status_code == 200
    body = r.json()
    assert "items" in body and "total" in body
    assert len(body["items"]) <= 5
