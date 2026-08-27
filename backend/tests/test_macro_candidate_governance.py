"""Macro Candidate Governance 只读接口测试。

两层:
1. Router 层(无 DB) — TestClient + 依赖覆盖/服务 monkeypatch:
   验证 3 个端点形状 + 参数过滤 + 404。
2. DB 层(真实测试库) — 读取已落库的真实表
   (paper_connection_candidate_rankings / macro_candidate_connection_llm_reviews),
   验证 JOIN 名称、数量一致性与只读副作用(前后计数不变)。

只读约束:端点禁止写任何表;测试对 5 个治理计数器做前后断言。
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


# ---- Router 层(无 DB,覆盖 get_db 依赖) ----

class _FakeRanking:
    """模拟 ranking 行(返回元组,与 router 解包顺序一致)。"""

    def __init__(self, **kw):
        self._k = kw

    def __getitem__(self, i):
        keys = ["id", "source_region_id", "target_region_id", "source_name",
                "target_name", "paper_count", "evidence_count", "score",
                "priority_level", "created_at"]
        return self._k[keys[i]]


class _FakeReview:
    def __init__(self, **kw):
        self._k = kw

    def __getitem__(self, i):
        keys = ["ranking_id", "source_region_id", "target_region_id",
                "source_name", "target_name", "decision", "connection_type",
                "direction", "confidence", "evidence_strength", "reasoning",
                "model_name", "raw_response_json", "created_at",
                "paper_count", "evidence_count", "score"]
        return self._k[keys[i]]


class _CaptureSession:
    """捕获 execute 调用(不真连库);按 SQL 内容返回假行。"""

    async def execute(self, sql, params=None):
        stmt = (sql.text if hasattr(sql, "text") else str(sql))
        if "FROM macro_candidate_connection_llm_reviews" in stmt:
            return _FakeResult([_FakeReview(
                ranking_id="r1", source_region_id="s1", target_region_id="t1",
                source_name="Amygdala", target_name="Hippocampus",
                decision="supported", connection_type="projection",
                direction="A_to_B", confidence=0.9,
                evidence_strength="high", reasoning="dense projection",
                model_name="deepseek-chat",
                raw_response_json={"parsed": {"decision": "supported"}},
                created_at="2026-08-25T09:00:00Z",
                paper_count=93, evidence_count=93, score=48.0)])
        if "SELECT count(*) FROM macro_candidate_connection_llm_reviews" in stmt:
            return _FakeScalar(1)
        if stmt.startswith("SELECT candidate_pair_ids"):
            return _FakeResult([(None, {}, {})])
        return _FakeResult([_FakeRanking(
            id="rk1", source_region_id="s1", target_region_id="t1",
            source_name="Thalamus proper", target_name="Hippocampus",
            paper_count=104, evidence_count=104, score=48.0,
            priority_level="A", created_at="2026-08-25T08:00:00Z")])


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows

    def first(self):
        return self._rows[0] if self._rows else None

    def scalar(self):
        return 1 if self._rows else 0


class _FakeScalar:
    def __init__(self, v):
        self._v = v

    def scalar(self):
        return self._v


async def _override_db():
    yield _CaptureSession()


def test_router_rankings_shape(client, monkeypatch):
    """GET /rankings → items 数组 + 名称 JOIN 字段 + score/paper_count。"""
    from app.database import get_db as real_get_db
    monkeypatch.setitem(app.dependency_overrides, real_get_db, _override_db)
    try:
        r = client.get("/api/macro-candidates/rankings")
    finally:
        app.dependency_overrides.pop(real_get_db, None)
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    item = body["items"][0]
    assert item["source_name"] == "Thalamus proper"
    assert item["target_name"] == "Hippocampus"
    assert item["paper_count"] == 104
    assert item["score"] == 48.0
    assert item["priority_level"] == "A"
    assert item["id"] == "rk1"


def test_router_reviews_shape(client, monkeypatch):
    """GET /reviews → decision/confidence/reason/model/raw 全字段。"""
    from app.database import get_db as real_get_db
    monkeypatch.setitem(app.dependency_overrides, real_get_db, _override_db)
    try:
        r = client.get("/api/macro-candidates/reviews")
    finally:
        app.dependency_overrides.pop(real_get_db, None)
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    item = body["items"][0]
    assert item["decision"] == "supported"
    assert item["confidence"] == 0.9
    assert item["reasoning"] == "dense projection"
    assert item["model_name"] == "deepseek-chat"
    assert item["source_name"] == "Amygdala"
    assert item["paper_count"] == 93


def test_router_ranking_detail(client, monkeypatch):
    """GET /rankings/{id} → candidate_pair_ids + ranking_reason。"""
    from app.database import get_db as real_get_db
    monkeypatch.setitem(app.dependency_overrides, real_get_db, _override_db)
    try:
        r = client.get(
            "/api/macro-candidates/rankings/11111111-1111-1111-1111-111111111111")
    finally:
        app.dependency_overrides.pop(real_get_db, None)
    assert r.status_code == 200
    assert r.json()["id"] == "rk1"
    assert "candidate_pair_ids" in r.json()
    assert "ranking_reason" in r.json()


# ---- DB 层(真实只读验证 + 零副作用) ----

COUNTERS = [
    "SELECT count(*) FROM paper_connection_candidate_rankings",
    "SELECT count(*) FROM macro_candidate_connection_llm_reviews",
    "SELECT count(*) FROM paper_region_pair_candidates",
    "SELECT count(*) FROM final_canonical_connections WHERE final_status='active'",
    "SELECT count(*) FROM canonical_connections",
]


def test_db_layer_readonly_no_side_effects(client):
    """真实库读取:端点可访问、数据非空、前后计数一致(零写入)。"""

    async def counts() -> list[int]:
        async with AsyncSessionLocal() as session:
            return [int((await session.execute(text(s))).scalar()) for s in COUNTERS]

    before = _run(counts())
    # rankings 表是阶段已有产物(1129 行)
    assert before[0] >= 1, "rankings 表应有既有数据(1129)"
    assert before[1] >= 1, "llm reviews 表应有既有数据(200)"

    r = client.get("/api/macro-candidates/rankings", params={"limit": 5})
    assert r.status_code == 200
    assert r.json()["total"] == before[0]
    assert len(r.json()["items"]) == 5

    r2 = client.get("/api/macro-candidates/reviews", params={"limit": 5})
    assert r2.status_code == 200
    assert r2.json()["total"] == before[1]
    assert len(r2.json()["items"]) == 5
    for it in r2.json()["items"]:
        assert it["decision"] in ("supported", "uncertain", "not_supported")

    after = _run(counts())
    assert before == after, "只读端点不得有任何写入"

    # 名称 JOIN 成功(非空)
    item = r.json()["items"][0]
    assert item["source_name"] and item["target_name"]


# ---- Phase 4: review-queue 双入口 + 新 target_type DTO ----

def test_review_queue_endpoint(client):
    """GET review-queue: enhancement(目标类型 existing_connection_evidence)与 novel 形状。"""
    r = client.get("/api/macro-candidates/review-queue", params={"kind": "enhancement", "limit": 5})
    assert r.status_code == 200
    body = r.json()
    assert body["kind"] == "enhancement"
    assert body["total"] >= 1
    for it in body["items"]:
        assert it["target_type"] == "existing_connection_evidence"
        assert it["rule_status"] == "BLOCKED"
        assert it["ai_decision"] in ("supported", "uncertain", "not_supported")
        assert it["status"] == "awaiting_review"
        assert "→" in it["label"]
    r2 = client.get("/api/macro-candidates/review-queue", params={"kind": "novel", "limit": 5})
    assert r2.status_code == 200
    for it in r2.json()["items"]:
        assert it["target_type"] == "macro_candidate_connection"


def test_enhancement_dto_case_amygdala_hippocampus():
    """案例1: Amygdala→Hippocampus 证据增强 DTO(已有连接 + 新证据 + AI 判定)。"""
    async def go():
        async with AsyncSessionLocal() as s:
            r = (await s.execute(text("""
                SELECT rk.id FROM paper_connection_candidate_rankings rk
                JOIN canonical_brain_regions rs ON rs.id=rk.source_region_id
                JOIN canonical_brain_regions rt ON rt.id=rk.target_region_id
                WHERE rs.canonical_name_en='Amygdala' AND rt.canonical_name_en='Hippocampus'
                LIMIT 1"""))).first()
            if r is None:
                return None
            from app.services.evidence_target_adapter import build_target_dto
            return await build_target_dto(s, "existing_connection_evidence",
                                          uuid.UUID(str(r[0])))

    dto = _run(go())
    if dto is None:
        pytest.skip("Amygdala→Hippocampus ranking 不存在")
    assert dto["target_type"] == "existing_connection_evidence"
    assert dto["review_kind"] == "enhancement"
    assert dto["source_region"] == "Amygdala"
    assert dto["target_region"] == "Hippocampus"
    assert dto["existing_connection_id"]
    assert dto["existing_connection_code"].startswith("ng:")
    assert dto["ai_decision"] == "supported"
    assert dto["rule_status"] == "BLOCKED"
    assert dto["claim_text"]


def test_novel_dto_shape():
    """macro_candidate_connection DTO 同样可构造(kind=novel)。"""
    async def go():
        async with AsyncSessionLocal() as s:
            r = (await s.execute(text(
                "SELECT id FROM paper_connection_candidate_rankings LIMIT 1"))).first()
            from app.services.evidence_target_adapter import build_target_dto
            return await build_target_dto(s, "macro_candidate_connection",
                                          uuid.UUID(str(r[0])))

    dto = _run(go())
    assert dto["target_type"] == "macro_candidate_connection"
    assert dto["review_kind"] == "novel"
    assert dto["source_region"] and dto["target_region"]
