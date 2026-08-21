# Paper Evidence Parallel Extraction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Process 20 reviewer-selected papers in a recoverable background run with four-way bounded concurrency and incremental frontend progress, without changing the per-paper evidence algorithm.

**Architecture:** Add persisted run/item records and async endpoints under the existing ontology router. Refactor the existing single-paper body into an isolated worker that opens its own database session; a queue orchestrator runs four workers while retaining the existing locator, judge, and source-verification logic. The evidence-center frontend creates a run, polls once per second, renders per-paper progress, and incrementally merges completed results.

**Tech Stack:** FastAPI, SQLAlchemy async, PostgreSQL JSONB, Pydantic v2, asyncio worker queues, React 18, TypeScript, Vitest, pytest.

**Commit policy:** Do not commit unless the user explicitly requests it.

---

## File Structure

- Create `backend/migrations/20260812_paper_evidence_extraction_runs.sql`: idempotent run/item tables and indexes.
- Create `backend/app/models/paper_evidence_extraction.py`: SQLAlchemy run/item models only.
- Modify `backend/app/models/__init__.py`: register new models.
- Create `backend/app/schemas/paper_evidence_extraction.py`: request, start, run-detail, item-detail schemas.
- Create `backend/app/services/paper_evidence_extraction_run_service.py`: run lifecycle, bounded worker queue, progress aggregation, cancel/retry.
- Modify `backend/app/services/paper_evidence_service.py`: extract an independently callable single-paper operation while preserving existing behavior.
- Modify `backend/app/routers/ontology.py`: create/get/cancel/retry run endpoints.
- Modify `backend/app/config.py`: explicit paper extraction concurrency settings.
- Create `backend/tests/test_paper_evidence_extraction_runs.py`: state machine, concurrency, failure isolation, endpoint tests.
- Modify `backend/tests/test_paper_evidence_api.py`: compatibility regression for synchronous extraction.
- Modify `frontend/src/api/endpoints.ts`: run API contracts.
- Create `frontend/src/pages/evidence-center/components/PaperExtractionProgress.tsx`: progress bar and per-paper statuses.
- Create `frontend/src/pages/evidence-center/components/PaperExtractionProgress.test.tsx`: component tests.
- Modify `frontend/src/pages/evidence-center/modules/EvidenceCandidatesModule.tsx`: create/poll run and incrementally merge results.
- Modify `frontend/src/pages/evidence-center/modules/EvidenceCandidatesModule.test.tsx`: async extraction flow regressions.
- Modify `frontend/src/styles.css`: scoped progress styles only.

### Task 1: Persisted run and item model

**Files:**
- Create: `backend/migrations/20260812_paper_evidence_extraction_runs.sql`
- Create: `backend/app/models/paper_evidence_extraction.py`
- Modify: `backend/app/models/__init__.py`
- Test: `backend/tests/test_paper_evidence_extraction_runs.py`

- [ ] **Step 1: Write the failing model persistence test**

Create a test that inserts one run and two items, reloads them, and asserts the initial counters and item order:

```python
async def test_run_and_items_persist(async_session):
    run = PaperEvidenceExtractionRun(
        target_type="connection",
        target_id=uuid.uuid4(),
        mode="existence",
        status="queued",
        total_items=2,
        requested_concurrency=4,
    )
    async_session.add(run)
    await async_session.flush()
    async_session.add_all([
        PaperEvidenceExtractionItem(run_id=run.id, item_index=0, pmid="1", title="A"),
        PaperEvidenceExtractionItem(run_id=run.id, item_index=1, doi="10.1/b", title="B"),
    ])
    await async_session.commit()
    loaded = await async_session.get(PaperEvidenceExtractionRun, run.id)
    assert loaded.total_items == 2
    assert loaded.completed_items == 0
```

- [ ] **Step 2: Run the test and confirm missing model/table failure**

Run:

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest tests/test_paper_evidence_extraction_runs.py -q -k persist
```

Expected: collection/import failure because the model does not exist.

- [ ] **Step 3: Add idempotent migration**

Create UUID run/item tables with:

```sql
CREATE TABLE IF NOT EXISTS paper_evidence_extraction_runs (
  id UUID PRIMARY KEY,
  target_type VARCHAR(64) NOT NULL,
  target_id UUID NOT NULL,
  mode VARCHAR(16) NOT NULL DEFAULT 'function',
  status VARCHAR(32) NOT NULL DEFAULT 'queued',
  total_items INT NOT NULL DEFAULT 0,
  completed_items INT NOT NULL DEFAULT 0,
  evidence_hit_items INT NOT NULL DEFAULT 0,
  no_evidence_items INT NOT NULL DEFAULT 0,
  failed_items INT NOT NULL DEFAULT 0,
  requested_concurrency INT NOT NULL DEFAULT 4,
  active_concurrency INT NOT NULL DEFAULT 0,
  cancel_requested BOOLEAN NOT NULL DEFAULT FALSE,
  request_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  started_at TIMESTAMPTZ,
  finished_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS paper_evidence_extraction_items (
  id UUID PRIMARY KEY,
  run_id UUID NOT NULL REFERENCES paper_evidence_extraction_runs(id) ON DELETE CASCADE,
  item_index INT NOT NULL,
  pmid VARCHAR(32),
  pmcid VARCHAR(32),
  doi VARCHAR(512),
  title TEXT,
  paper_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  status VARCHAR(32) NOT NULL DEFAULT 'queued',
  progress_percent INT NOT NULL DEFAULT 0,
  attempt_count INT NOT NULL DEFAULT 0,
  result_json JSONB,
  error_code VARCHAR(64),
  error_message TEXT,
  stage_timings_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  started_at TIMESTAMPTZ,
  finished_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(run_id, item_index)
);
```

Add indexes on `(run_id, item_index)`, `(run_id, status)`, and run status.

- [ ] **Step 4: Add focused ORM models and register them**

Use `UUID(as_uuid=True)`, `JSONB`, timezone-aware timestamps, and defaults matching the SQL. Export both models from `app.models`.

- [ ] **Step 5: Apply migration and verify test passes**

Apply the SQL to the configured development database using the repository's existing migration procedure, then run the persistence test. Expected: PASS.

### Task 2: Run schemas and lifecycle creation

**Files:**
- Create: `backend/app/schemas/paper_evidence_extraction.py`
- Create: `backend/app/services/paper_evidence_extraction_run_service.py`
- Test: `backend/tests/test_paper_evidence_extraction_runs.py`

- [ ] **Step 1: Write failing tests for create and read**

Test these invariants:

```python
assert created.status == "queued"
assert created.total_items == len(request.papers)
assert [item.item_index for item in detail.items] == list(range(len(request.papers)))
assert detail.progress_percent == 0
```

- [ ] **Step 2: Define Pydantic contracts**

Define:

```python
class PaperEvidenceExtractionRunRequest(BaseModel):
    target_type: str
    target_id: uuid.UUID
    papers: list[PaperRef] = Field(min_length=1, max_length=20)
    only_oa: bool = False
    stop_after_strong_support: bool = False
    mode: Literal["function", "existence"] = "function"
    concurrency: int = Field(default=4, ge=1, le=6)
```

Add start, item read, and detail responses. Detail computes `progress_percent` from terminal items and per-item stage percentages and includes `items` ordered by `item_index`.

- [ ] **Step 3: Implement run creation**

`create_run(session, request)` must insert the run and one queued item per request paper in one transaction. Store the original paper metadata in `paper_json`; never store credentials or provider secrets.

- [ ] **Step 4: Implement get detail**

Load run and items with deterministic ordering; raise `ValueError("extraction run not found")` for unknown IDs.

- [ ] **Step 5: Run lifecycle tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_paper_evidence_extraction_runs.py -q -k "create or detail"
```

Expected: PASS.

### Task 3: Isolated single-paper worker

**Files:**
- Modify: `backend/app/services/paper_evidence_service.py`
- Create/Modify: `backend/app/services/paper_evidence_extraction_run_service.py`
- Test: `backend/tests/test_paper_evidence_extraction_runs.py`
- Test: `backend/tests/test_paper_evidence_api.py`

- [ ] **Step 1: Write a failing worker parity test**

Mock metadata, fulltext, locator, judge, and source verification. Run the legacy synchronous path and the new worker on the same paper and assert equal candidate payloads for:

```python
("model_direction", "coverage_summary", "passages", "not_found_reason", "evidence_dimension")
```

- [ ] **Step 2: Extract a single-paper operation**

Create an internal function whose inputs are one paper, context, semaphores, and an optional stage callback:

```python
async def extract_candidate_for_paper(
    session: AsyncSession,
    *,
    context: dict,
    paper: dict,
    only_oa: bool,
    sem_fetch: asyncio.Semaphore,
    sem_deepseek: asyncio.Semaphore,
    on_stage: Callable[[str], Awaitable[None]] | None = None,
) -> dict:
    ...
```

Move the current per-paper body without changing prompts, retrieval limits, verification, or result shape. Return an explicit result envelope for non-OA skips and failures instead of silent `continue`.

- [ ] **Step 3: Make legacy multi-paper code call the worker**

Keep semantic filtering and stop-after-strong-support behavior intact. The compatibility endpoint must still return one audit-visible result per submitted paper.

- [ ] **Step 4: Map stages to deterministic percentages**

Use:

```python
STAGE_PROGRESS = {
    "queued": 0,
    "fetching": 10,
    "parsing": 25,
    "retrieving": 40,
    "locating": 55,
    "judging": 75,
    "verifying": 90,
    "completed": 100,
    "no_evidence": 100,
    "failed": 100,
    "cancelled": 100,
}
```

- [ ] **Step 5: Run worker parity and legacy regressions**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_paper_evidence_extraction_runs.py tests/test_paper_evidence_api.py tests/test_paper_evidence_m2.py -q
```

Expected: PASS.

### Task 4: Four-way bounded background executor

**Files:**
- Modify: `backend/app/config.py`
- Modify: `backend/app/services/paper_evidence_extraction_run_service.py`
- Test: `backend/tests/test_paper_evidence_extraction_runs.py`

- [ ] **Step 1: Write failing concurrency and isolation tests**

Instrument a fake worker:

```python
active = 0
max_active = 0

async def fake_worker(...):
    nonlocal active, max_active
    active += 1
    max_active = max(max_active, active)
    await asyncio.sleep(0.01)
    active -= 1
```

For 20 items and concurrency 4, assert `max_active == 4`, all items terminal, and one injected exception increments only `failed_items`.

- [ ] **Step 2: Add settings**

Add:

```python
paper_extraction_worker_concurrency: int = 4
paper_extraction_fetch_concurrency: int = 6
paper_extraction_llm_concurrency: int = 4
paper_extraction_poll_seconds: float = 1.0
```

- [ ] **Step 3: Implement queue executor**

`execute_run_background(run_id)` must:

1. Load run and context.
2. Mark run running.
3. Put queued items into `asyncio.Queue`.
4. Start `min(requested_concurrency, configured_max, queued_count)` workers.
5. Open an independent `AsyncSessionLocal()` inside each item execution.
6. Persist stage changes and timing.
7. Recompute counters after every terminal item.
8. Finalize as completed, partially_failed, failed, or cancelled.

- [ ] **Step 4: Add cancel and retry-failed service methods**

Cancel sets `cancel_requested`, marks queued items cancelled, and leaves completed results untouched. Retry resets only failed items to queued, clears their errors, and creates a new background execution on the same run.

- [ ] **Step 5: Run bounded concurrency tests**

Expected: no shared-session errors, maximum active worker count equals configured concurrency, and failures remain isolated.

### Task 5: Async API endpoints

**Files:**
- Modify: `backend/app/routers/ontology.py`
- Test: `backend/tests/test_paper_evidence_extraction_runs.py`

- [ ] **Step 1: Write failing API tests**

Cover reviewer authorization and:

```python
POST /api/ontology/evidence/extraction-runs              -> 202
GET  /api/ontology/evidence/extraction-runs/{run_id}     -> 200
POST /api/ontology/evidence/extraction-runs/{run_id}/cancel -> 200
POST /api/ontology/evidence/extraction-runs/{run_id}/retry-failed -> 200
```

- [ ] **Step 2: Add create endpoint**

Use `BackgroundTasks`:

```python
run = await run_service.create_run(session, body)
background_tasks.add_task(run_service.execute_run_background, run.id)
return start_response(run)
```

- [ ] **Step 3: Add detail, cancel, and retry endpoints**

Translate service `ValueError` into the repository's existing 400/404 error shape. Retry schedules background execution only when at least one failed item was reset.

- [ ] **Step 4: Run API tests and inspect OpenAPI**

Run the test file and verify generated schemas contain all progress fields.

### Task 6: Frontend API and progress component

**Files:**
- Modify: `frontend/src/api/endpoints.ts`
- Create: `frontend/src/pages/evidence-center/components/PaperExtractionProgress.tsx`
- Create: `frontend/src/pages/evidence-center/components/PaperExtractionProgress.test.tsx`
- Modify: `frontend/src/styles.css`

- [ ] **Step 1: Write failing component tests**

Test:

- progress width for 8/20,
- hit/no-evidence/failed/running counters,
- Chinese stage labels,
- cancel visibility while running,
- retry-failed visibility only for terminal runs with failures.

- [ ] **Step 2: Add API types/functions**

Define `PaperEvidenceExtractionRun`, `PaperEvidenceExtractionItem`, and:

```typescript
createPaperEvidenceExtractionRun(body)
getPaperEvidenceExtractionRun(runId, signal?)
cancelPaperEvidenceExtractionRun(runId)
retryFailedPaperEvidenceExtractionRun(runId)
```

- [ ] **Step 3: Implement focused progress component**

Props:

```typescript
interface Props {
  run: PaperEvidenceExtractionRun
  onCancel: () => void
  onRetryFailed: () => void
}
```

Render one accessible progressbar and a compact paper list. Keep styles under `evidence-extraction-progress-*`.

- [ ] **Step 4: Run component tests**

Run:

```powershell
npx vitest run src/pages/evidence-center/components/PaperExtractionProgress.test.tsx
```

Expected: PASS.

### Task 7: Evidence candidate integration and polling

**Files:**
- Modify: `frontend/src/pages/evidence-center/modules/EvidenceCandidatesModule.tsx`
- Modify: `frontend/src/pages/evidence-center/modules/EvidenceCandidatesModule.test.tsx`

- [ ] **Step 1: Write failing integration tests**

Test that selecting 20 papers calls create once, does not call the legacy synchronous API, polls by `run_id`, shows 4 active papers, and merges a completed item before the run is terminal.

- [ ] **Step 2: Add run state and polling**

Store `activeRunId` per target in session storage:

```typescript
const RUN_KEY = `evidence-center.extraction-run.${targetId}`
```

Poll every 1000 ms while status is nonterminal. Abort the previous poll on target change/unmount.

- [ ] **Step 3: Incrementally merge successful results**

For each item with `status` completed or no_evidence and `result_json`, upsert by stable paper identity. Keep failed papers visible with error status; never duplicate the original search card and result card.

- [ ] **Step 4: Replace busy state with progress panel**

Submitting creates the run and clears submitted selections. The progress panel remains visible through partially_failed completion. Existing review passage selection uses only successful verified passages.

- [ ] **Step 5: Run candidate module tests**

Run targeted async-run tests first, then the full module test. Record any unrelated pre-existing failures separately; do not weaken assertions to hide them.

### Task 8: Recovery, regression, and performance gate

**Files:**
- Modify: `backend/app/main.py`
- Modify: `backend/tests/test_paper_evidence_extraction_runs.py`
- Create: `backend/scripts/benchmark_paper_evidence_extraction.py`

- [ ] **Step 1: Write failing recovery test**

Seed a running run with fetching/judging items, call recovery, and assert nonterminal items return to queued while completed results remain unchanged.

- [ ] **Step 2: Add startup recovery**

At startup, reset interrupted nonterminal items to queued and schedule runs that were queued/running and not cancelled.

- [ ] **Step 3: Add deterministic benchmark script**

The script accepts a target and 20 paper identifiers, runs concurrency 1 and 4 with the same model parameters, and outputs:

- total wall time,
- per-stage latency,
- source-verified passage hashes by paper,
- direction/evidence-level/component differences.

It must not promote or attach evidence.

- [ ] **Step 4: Run backend and frontend verification**

Run:

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest tests/test_paper_evidence_extraction_runs.py tests/test_paper_evidence_api.py tests/test_paper_evidence_m1.py tests/test_paper_evidence_m2.py tests/test_paper_evidence_v4.py -q

cd ..\frontend
npx vitest run src/pages/evidence-center/components/PaperExtractionProgress.test.tsx
npx vitest run src/pages/evidence-center/modules/EvidenceCandidatesModule.test.tsx
npm run build
```

- [ ] **Step 5: Run the real 20-paper performance gate**

Run three cold-cache and three warm-cache trials. Accept only if:

- cold-cache wall time is at most 180 seconds,
- no cross-paper passage identity occurs,
- source-verified passage hashes do not regress against concurrency 1,
- failures do not block other items,
- the frontend reflects each completion within 1 second.
