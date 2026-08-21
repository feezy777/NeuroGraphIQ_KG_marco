### Task 1: 后端 Paper Library 只读 API

**Files:**
- Modify: `backend/app/services/paper_evidence_service.py`(文件尾追加两个函数)
- Modify: `backend/app/routers/ontology.py`(追加两个端点)
- Test: `backend/tests/test_paper_library_api.py`(新建)

**Interfaces:**
- Produces:
  - `async def list_papers(session, *, search: str = "", oa: bool | None = None, year: int | None = None, has_fulltext: bool | None = None, page: int = 1, page_size: int = 20) -> dict` → `{"items": [{id, pmid, pmcid, doi, title, journal, publication_year, is_oa, abstract_available, fulltext_available, paragraph_count, evidence_count}], "total": int}`
  - `async def get_paper_detail(session, paper_id: uuid.UUID) -> dict` → `{"paper": {...}, "paragraphs": [{paragraph_id, section_title, paragraph_index, passage_text, source_scope}], "evidence_count": int, "targets": [{evidence_target_type, evidence_target_id}]}`
  - Router: `GET /api/ontology/evidence/papers`、`GET /api/ontology/evidence/papers/{paper_id}`

- [ ] **Step 1: 写失败测试**

`backend/tests/test_paper_library_api.py`:
```python
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
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_paper_library_api.py -q`
Expected: FAIL(`list_papers` 不存在)

- [ ] **Step 3: 实现 service 函数**(paper_evidence_service.py 文件尾追加)

```python
async def list_papers(
    session: AsyncSession,
    *,
    search: str = "",
    oa: bool | None = None,
    year: int | None = None,
    has_fulltext: bool | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    """Paper Library: paginated read-only list over paper_sources."""
    where = ["1=1"]
    params: dict = {}
    if search:
        where.append("(title ILIKE :q OR journal ILIKE :q OR pmid ILIKE :q OR doi ILIKE :q)")
        params["q"] = f"%{search}%"
    if oa is not None:
        where.append("is_oa = :oa")
        params["oa"] = oa
    if year is not None:
        where.append("publication_year = :yr")
        params["yr"] = year
    if has_fulltext is not None:
        where.append("fulltext_available = :ft")
        params["ft"] = has_fulltext
    clause = " AND ".join(where)
    params["lim"] = page_size
    params["off"] = (max(1, page) - 1) * page_size
    rows = (
        await session.execute(
            text(
                f"SELECT ps.id, ps.pmid, ps.pmcid, ps.doi, ps.title, ps.journal, "
                f"ps.publication_year, ps.is_oa, ps.abstract_available, ps.fulltext_available, "
                f"(SELECT COUNT(*) FROM paper_passages pp WHERE pp.paper_id = ps.id) AS paragraph_count, "
                f"(SELECT COUNT(*) FROM mirror_evidence_records er WHERE er.paper_id = ps.id) AS evidence_count "
                f"FROM paper_sources ps WHERE {clause} ORDER BY ps.fetched_at DESC NULLS LAST "
                f"LIMIT :lim OFFSET :off"
            ),
            params,
        )
    ).all()
    total = (
        await session.execute(text(f"SELECT COUNT(*) FROM paper_sources WHERE {clause}"), params)
    ).scalar_one()
    return {
        "items": [
            {
                "id": str(r[0]),
                "pmid": r[1],
                "pmcid": r[2],
                "doi": r[3],
                "title": r[4],
                "journal": r[5],
                "publication_year": r[6],
                "is_oa": bool(r[7]),
                "abstract_available": bool(r[8]),
                "fulltext_available": bool(r[9]),
                "paragraph_count": int(r[10] or 0),
                "evidence_count": int(r[11] or 0),
            }
            for r in rows
        ],
        "total": int(total),
    }


async def get_paper_detail(session: AsyncSession, paper_id: uuid.UUID) -> dict:
    """Paper Library detail: metadata + paragraphs + linked evidence targets."""
    row = (
        await session.execute(
            text(
                "SELECT id, source, pmid, pmcid, doi, title, journal, publication_year, "
                "is_oa, abstract_available, fulltext_available, metadata_json "
                "FROM paper_sources WHERE id = :pid"
            ),
            {"pid": paper_id},
        )
    ).first()
    if row is None:
        raise ValueError("paper not found")
    paragraphs = (
        await session.execute(
            text(
                "SELECT paragraph_id, section_title, paragraph_index, passage_text, source_scope "
                "FROM paper_passages WHERE paper_id = :pid ORDER BY paragraph_index"
            ),
            {"pid": paper_id},
        )
    ).all()
    evidence = (
        await session.execute(
            text(
                "SELECT evidence_target_type, evidence_target_id FROM mirror_evidence_records "
                "WHERE paper_id = :pid AND verification_status IN ('human_verified','ai_extracted')"
            ),
            {"pid": paper_id},
        )
    ).all()
    return {
        "paper": {
            "id": str(row[0]),
            "source": row[1],
            "pmid": row[2],
            "pmcid": row[3],
            "doi": row[4],
            "title": row[5],
            "journal": row[6],
            "publication_year": row[7],
            "is_oa": bool(row[8]),
            "abstract_available": bool(row[9]),
            "fulltext_available": bool(row[10]),
            "metadata_json": row[11],
        },
        "paragraphs": [
            {
                "paragraph_id": p[0],
                "section_title": p[1],
                "paragraph_index": p[2],
                "passage_text": p[3],
                "source_scope": p[4],
            }
            for p in paragraphs
        ],
        "evidence_count": len(evidence),
        "targets": [{"target_type": t[0], "target_id": str(t[1])} for t in evidence],
    }
```

- [ ] **Step 4: 实现 router 端点**(ontology.py,`/evidence/papers` 段,放在 `@router.get("/evidence/stats")` 之前)

```python
@router.get("/evidence/papers")
async def paper_library_list(
    search: str | None = Query(default=None),
    oa: bool | None = Query(default=None),
    year: int | None = Query(default=None),
    has_fulltext: bool | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_db),
):
    return await pes.list_papers(
        session,
        search=search or "",
        oa=oa,
        year=year,
        has_fulltext=has_fulltext,
        page=page,
        page_size=page_size,
    )


@router.get("/evidence/papers/{paper_id}")
async def paper_library_detail(
    paper_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
):
    try:
        return await pes.get_paper_detail(session, paper_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"code": "INVALID_REQUEST", "message": str(exc)})
```

- [ ] **Step 5: 运行测试确认通过**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_paper_library_api.py -q`
Expected: PASS(2 passed)

- [ ] **Step 6: 提交**

```bash
git add backend/app/services/paper_evidence_service.py backend/app/routers/ontology.py backend/tests/test_paper_library_api.py
git commit -m "feat(evidence): Paper Library 只读 API(list/detail)"
```

---

