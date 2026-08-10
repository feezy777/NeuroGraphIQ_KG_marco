"""Paper Library 只读 API 测试(基于真实 DB)。"""
from __future__ import annotations

import asyncio
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.database import AsyncSessionLocal
from app.main import app
from app.services import paper_evidence_service as pes


def _run(coro):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def test_list_papers_returns_cached_sources():
    async def case():
        async with AsyncSessionLocal() as s:
            # 需要至少一条 paper_sources;插入一条测试数据
            pid = (
                await s.execute(
                    text(
                        "INSERT INTO paper_sources (id, source, pmid, doi, normalized_doi, title, journal, "
                        "publication_year, is_oa, abstract_available, fulltext_available) "
                        "VALUES (:id, 'europepmc', '99990001', '10.1/lib1', '10.1/lib1', 'Library Test Paper', "
                        "'Test J', 2026, true, true, false) RETURNING id"
                    ),
                    {"id": uuid.uuid4()},
                )
            ).scalar_one()
            # 关联一段段落
            await s.execute(
                text(
                    "INSERT INTO paper_passages (id, paper_id, source_scope, paragraph_id, paragraph_index, "
                    "passage_text, text_hash) VALUES (:id, :pid, 'abstract', 'abstract_p001', 0, 'Some abstract.', :h)"
                ),
                {"id": uuid.uuid4(), "pid": pid, "h": pes.passage_hash("Some abstract.")},
            )
            await s.commit()
            try:
                result = await pes.list_papers(s, search="Library Test", page=1, page_size=10)
                assert result["total"] >= 1
                hit = next((i for i in result["items"] if i["pmid"] == "99990001"), None)
                assert hit is not None
                assert hit["paragraph_count"] == 1
                assert hit["abstract_available"] is True
                detail = await pes.get_paper_detail(s, pid)
                assert detail["paper"]["pmid"] == "99990001"
                assert len(detail["paragraphs"]) == 1
                assert detail["paragraphs"][0]["paragraph_id"] == "abstract_p001"
            finally:
                await s.execute(text("DELETE FROM paper_passages WHERE paper_id=:pid"), {"pid": pid})
                await s.execute(text("DELETE FROM paper_sources WHERE id=:pid"), {"pid": pid})
                await s.commit()

    _run(case())


def test_paper_library_endpoints():
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/api/ontology/evidence/papers", params={"page_size": 5})
    assert resp.status_code == 200
    body = resp.json()
    assert "items" in body and "total" in body
