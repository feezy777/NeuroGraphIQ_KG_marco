# Task 1 Report: 后端 Paper Library 只读 API

## Status: DONE_WITH_CONCERNS

## What I implemented

Two read-only service functions appended at the END of `backend/app/services/paper_evidence_service.py` (existing functions untouched):

- `list_papers(session, *, search, oa, year, has_fulltext, page, page_size) -> dict` — paginated list over `paper_sources` with optional ILIKE search (title/journal/pmid/doi) and `is_oa` / `publication_year` / `fulltext_available` filters; per-paper `paragraph_count` (from `paper_passages`) and `evidence_count` (from `mirror_evidence_records`) subqueries; ordered `fetched_at DESC NULLS LAST`. Returns `{"items": [...], "total": int}`.
- `get_paper_detail(session, paper_id: uuid.UUID) -> dict` — paper metadata (+`metadata_json`), all paragraphs ordered by `paragraph_index`, and linked evidence targets (`evidence_target_type`/`evidence_target_id`) from `mirror_evidence_records` filtered to `verification_status IN ('human_verified','ai_extracted')`. Raises `ValueError("paper not found")` when the paper doesn't exist.

Two router endpoints in `backend/app/routers/ontology.py`, inserted in the `/evidence/...` section immediately BEFORE `@router.get("/evidence/stats")` (existing endpoints untouched):

- `GET /api/ontology/evidence/papers` — query params `search`, `oa`, `year`, `has_fulltext`, `page` (ge=1), `page_size` (ge=1, le=100); delegates to `pes.list_papers`.
- `GET /api/ontology/evidence/papers/{paper_id}` — `uuid.UUID` path param; maps `ValueError` from the service to `HTTPException(400, {"code": "INVALID_REQUEST", "message": ...})`.

New test file `backend/tests/test_paper_library_api.py` (verbatim from the brief): inserts a `paper_sources` row + one `paper_passages` row, asserts list/detail behavior, cleans up in `finally`; plus a TestClient smoke test on the list endpoint.

## TDD Evidence

**RED** — `cd backend && .venv/Scripts/python.exe -m pytest tests/test_paper_library_api.py -q`:

```
FAILED tests/test_paper_library_api.py::test_list_papers_returns_cached_sources
FAILED tests/test_paper_library_api.py::test_paper_library_endpoints - assert...
2 failed, 2 warnings in 1.34s
```
(Failure: `list_papers` attribute doesn't exist; endpoint returns 404 since route not registered.)

**GREEN** — same command after implementation:

```
2 passed, 2 warnings in 1.16s
```

**Regression check** — related existing suites still pass:
`pytest tests/test_paper_evidence_v4.py tests/test_paper_evidence_api.py -q` → `13 passed`.

## Files changed (committed)

- `backend/app/services/paper_evidence_service.py` (+~128 lines, appended at EOF)
- `backend/app/routers/ontology.py` (+~32 lines, before `/evidence/stats`)
- `backend/tests/test_paper_library_api.py` (new, 72 lines)

Commit: `1cc5bb0` — `feat(evidence): Paper Library 只读 API(list/detail)` — 3 files changed, 718 insertions(+), 61 deletions(-).

## Self-review findings

- **Completeness**: all interfaces from the brief implemented exactly as specified; router registered before `/evidence/stats`; service imports (`AsyncSession`, `text`, `uuid`) were already present, no import changes needed.
- **Correctness**: verified against real test DB (INSERT/RETURNING pattern works; `paper_sources`/`paper_passages`/`mirror_evidence_records` columns referenced by the SQL all exist). Count query reuses the same `params` dict including `lim`/`off` — safe, SQLAlchemy `text()` ignores extra params; GREEN test proves it.
- **YAGNI**: nothing beyond the brief (no extra filters, no response schemas — brief called for plain dict returns).
- **Error handling**: detail endpoint converts `ValueError` → 400 with `INVALID_REQUEST` code, per brief.
- **Minor spec-vs-code note**: brief's interface text describes `targets` items as `{evidence_target_type, evidence_target_id}`, but the brief's own code emits `{target_type, target_id}` — I followed the brief's code (authoritative). Frontend should consume `target_type`/`target_id`.

## Concerns

1. **Commit contains pre-existing uncommitted work (main concern).** Both modified files had ~590 lines of other uncommitted evidence work (similarity tiering, batch Phase C/D state machine, paper ranking) in the working tree before I started. The brief's Step 6 and the orchestration context explicitly sanctioned `git add` of these exact three paths, and my changes are the final hunks of each file (verified via hunk-header analysis), so I committed the whole files per instructions. The commit therefore includes more than Task 1's additions. If the orchestrator wants attribution-precise history, it should `git reset --soft HEAD~1` and re-stage only the last hunks; otherwise the pre-existing work is now permanently attributed to this commit. All tests (mine + related suites) pass with the pre-existing work present, so nothing is broken.
2. Detail endpoint returns 400 for a nonexistent paper id rather than 404 — matches the brief's code exactly; flagged in case frontend expects 404 semantics.
3. `paper_library_list` endpoint has no `_auth` dependency guard (read-only, consistent with `/evidence/stats` which also has none).
