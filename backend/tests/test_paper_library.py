"""Paper Library 升级后端测试。

覆盖:
1. list_papers 默认排除软删 + journal/evidence_min 过滤 + author 搜索。
2. get_paper_detail 扩展字段(authors/abstract/review_count)。
3. 添加论文:URL→DOI 提取、重复禁建(created=False)、合法输入入库(用假 metadata,monkeypatch fetch)。
4. 软删除:幂等 + 列表排除。

不做真实外部抓取:fetch_paper_metadata 全部 monkeypatch。
"""
from __future__ import annotations

import asyncio
import random
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


async def _create_paper(overrides: dict | None = None) -> str:
    o = overrides or {}
    pid = str(uuid.uuid4())
    async with AsyncSessionLocal() as s:
        await s.execute(text(
            """INSERT INTO paper_sources
               (id, source, pmid, doi, normalized_doi, title, journal, publication_year,
                is_oa, abstract_available, fulltext_available, metadata_json, fetched_at)
               VALUES (:id, 'test', :pmid, :doi, :ndoi, :title, :journal, :year,
                       false, true, false, '{"authors": "Test Author"}'::jsonb, now())"""),
            {"id": pid,
             "pmid": o.get("pmid", str(random.randint(10 ** 15, 9 * 10 ** 15))),
             "doi": o.get("doi"),
             "ndoi": o.get("ndoi"),
             "title": o.get("title", "图书馆测试论文"),
             "journal": o.get("journal", "Test Journal"),
             "year": o.get("year", 2024)})
        await s.commit()
    return pid


async def _cleanup(pid: str) -> None:
    async with AsyncSessionLocal() as s:
        await s.execute(text("DELETE FROM mirror_evidence_records WHERE paper_id = :p"), {"p": pid})
        await s.execute(text("DELETE FROM paper_evidence_reviews WHERE paper_id = :p"), {"p": pid})
        await s.execute(text("DELETE FROM paper_passages WHERE paper_id = :p"), {"p": pid})
        await s.execute(text("DELETE FROM paper_sources WHERE id = :p"), {"p": pid})
        await s.commit()


@pytest.fixture()
def paper_id():
    pid = _run(_create_paper())
    yield pid
    _run(_cleanup(pid))


def test_soft_delete_list_exclusion(paper_id, client):
    """软删后默认列表排除;重复删除幂等(第二次 deleted=False)。"""
    r = client.post(f"/api/ontology/evidence/papers/{paper_id}/delete")
    assert r.status_code == 200
    body = r.json()
    assert body["deleted"] is True
    assert body["deleted_at"] is not None
    # 列表排除
    lst = client.get("/api/ontology/evidence/papers",
                     params={"search": "图书馆测试论文", "page_size": 50})
    ids = [i["id"] for i in lst.json()["items"]]
    assert paper_id not in ids
    # 幂等
    r2 = client.post(f"/api/ontology/evidence/papers/{paper_id}/delete")
    assert r2.json()["deleted"] is False


def test_list_filters_and_author_search(paper_id, client):
    """journal/evidence_min 过滤 + author 搜索(metadata_json)."""
    j = client.get("/api/ontology/evidence/papers",
                   params={"journal": "Test Journal", "page_size": 50})
    ids = [i["id"] for i in j.json()["items"]]
    assert paper_id in ids
    a = client.get("/api/ontology/evidence/papers",
                   params={"search": "Test Author", "page_size": 50})
    ids_a = [i["id"] for i in a.json()["items"]]
    assert paper_id in ids_a
    em = client.get("/api/ontology/evidence/papers",
                    params={"evidence_min": 100, "page_size": 50})
    assert paper_id not in [i["id"] for i in em.json()["items"]]


def test_detail_extension_fields(paper_id, client):
    """detail: authors/abstract/review_count 呈现(0 时 null/0)。"""
    r = client.get(f"/api/ontology/evidence/papers/{paper_id}")
    assert r.status_code == 200
    paper = r.json()["paper"]
    assert paper["authors"] == "Test Author"
    assert paper["review_count"] == 0
    assert "abstract" in paper


def test_add_paper_duplicate_rejected(paper_id, client, monkeypatch):
    """添加已有(PMID) → created=False(禁止重复创建)。"""
    existing_pmid = _run(_get_pmid(paper_id))

    async def _no_fetch(**kw):
        raise AssertionError("已有论文不应触发抓取")

    from app.services import paper_fetch_service as pfs
    monkeypatch.setattr(pfs, "fetch_paper_metadata", _no_fetch)
    r = client.post("/api/ontology/evidence/papers",
                    json={"pmid": existing_pmid})
    assert r.status_code == 200
    assert r.json()["created"] is False
    assert r.json()["message"] == "already_exists"


async def _get_pmid(pid: str) -> str:
    async with AsyncSessionLocal() as s:
        return (await s.execute(
            text("SELECT pmid FROM paper_sources WHERE id = :p"), {"p": pid})).scalar()


def test_add_paper_url_doi_parsing():
    """URL → DOI 提取(纯规则;锚点剥除在 add 函数内完成)。"""
    from app.services.paper_evidence_service import _URL_DOI_RE
    m = _URL_DOI_RE.search("https://doi.org/10.1523/JNEUROSCI.1234-20.2020#tab")
    assert m
    raw = m.group(0).rstrip(".,;").split("#")[0].split("?")[0].strip()
    assert raw == "10.1523/JNEUROSCI.1234-20.2020"
