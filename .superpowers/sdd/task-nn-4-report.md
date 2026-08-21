# Task 4 Report: build_search_query negative 参数 + 自动反向检索

**Status:** DONE_WITH_CONCERNS (review fixes applied and amended)
**Commit:** `3913507` — feat(evidence): negative search on no-result — auto second round distinguishes evidence_negated vs no_evidence
**Branch:** `codex/ontology-evidence` (unchanged)

## What Was Done

1. **Adapter (`backend/app/services/evidence_target_adapter.py`)** — `build_search_query` gains `negative: bool = False` keyword param. When `negative=True`, `negative_terms` (["no projection", "does not connect", "absence of connection", "not connected", "no connection"]) are appended to the term list in both `mode == "existence"` and the default branch (for connection/projection the `_CONNECTION_EVIDENCE_TERMS` are still appended before the negative terms). Token assembly unchanged — negation phrases get wrapped as `ABSTRACT:"no projection"` via the existing token loop, exactly as the brief specified.
2. **Service (`backend/app/services/paper_evidence_service.py`)** — `_process_batch_item_v2` no-result path: after the existing wide_query second-round block and before the final `if not papers:` no-evidence path, a negative-oriented second round runs:
   - `build_search_query(..., mode=mode, abstract_only=False, negative=True)`, searched under `sem_search` with `limit=max(10, max_papers * 3)`, guarded by `negative_query != query`; on hits `query = negative_query`.
   - `query_is_negative = query.startswith("no projection") or "does not connect" in query` recorded after query finalization (query is not yet defined at the function top, so the record point is right after the negative-search block — semantically equivalent to the brief's intent).
   - Outcome assignment now: `"evidence_negated" if query_is_negative and verified_any else "evidence_found" if verified_any else "no_evidence_found"` — distinguishes「证据否定」from「无证据」.
3. **Test (`backend/tests/test_evidence_target_adapter.py`, new)** — brief's two tests; the `__import__("unittest.mock")` shorthand was replaced with the equivalent `from unittest.mock import AsyncMock, patch` (brief explicitly permits this).

## TDD Evidence

**RED** — `./.venv/Scripts/python.exe -m pytest tests/test_evidence_target_adapter.py -q`:

```
>           q = _run(eta.build_search_query(None, "connection", uuid.uuid4(), mode="existence", negative=True))
E           TypeError: build_search_query() got an unexpected keyword argument 'negative'
FAILED tests/test_evidence_target_adapter.py::test_negative_query_contains_negation_terms
1 failed, 1 passed in 0.25s
```
(Failure exactly as predicted: `TypeError: build_search_query() got an unexpected keyword argument 'negative'`; the positive-variant test passed even before the change.)

**GREEN (adapter)** — same command after implementation:

```
..                                                                       [100%]
2 passed in 0.10s
```

**Regression (brief's runner)** — `./.venv/Scripts/python.exe -m pytest tests/test_evidence_target_adapter.py tests/test_paper_evidence_batch.py tests/test_paper_evidence_batch_phase4.py -q`:

```
...................                                                      [100%]
19 passed in 14.37s
```

**Post-commit re-run:** `19 passed in 16.13s`

**Bonus adjacency check** — `tests/test_paper_evidence_batch_scale.py tests/test_paper_evidence_m2.py`:

```
20 passed, 4 warnings in 4.62s
```
(4 warnings are pre-existing ResourceWarnings, unrelated to this change.)

## Review Fixes (coordinator-flagged defect, amended into `3913507`)

**Defect:** the 5 negation phrases were AND-joined (`" AND ".join(tokens)`), so a single paper would need to contain ALL of "no projection", "does not connect", "absence of connection", "not connected", "no connection" simultaneously — impossible in practice, so `evidence_negated` could never fire (silent no-op). The `query.startswith("no projection")` check was also dead code (query strings start with `ABSTRACT:"..."`).

**Fix 1 (adapter, OR-group):** removed the `negative_terms` list from both term-construction branches; the negation phrases are now appended to `tokens` after the term loop as a single OR-group:
`(ABSTRACT:"no projection" OR ABSTRACT:"does not connect" OR ABSTRACT:"absence of connection" OR ABSTRACT:"not connected" OR ABSTRACT:"no connection")` — any single phrase hitting matches. Verified no leftover `negative_terms` reference.

**Fix 2 (service, boolean flag):** replaced the string-matching `query_is_negative = query.startswith(...)` line with a plain boolean: `query_is_negative = False` declared at the initial query assignment, set `True` only when the negative round hits (`query = negative_query; query_is_negative = True`). The `evidence_negated` outcome guard (`query_is_negative and verified_any`) is unchanged.

**Fix 3 (flow test):** added `TestBatchStateMachine::test_negative_round_marks_evidence_negated` in `tests/test_paper_evidence_batch.py` (new helper `_read_item_model_direction`). It mocks the actual v2-path symbols: `build_search_query` side_effect `["pos q", "pos q", "neg q"]` (initial / wide-identical-skip / negative), `_search_with_retry` side_effect `[[], [_paper()]]` (positive round empty, negative round hit), `build_retrieval_context`, `semantic_filter_papers`, `_verify_paper_with_retry`, `pfs.fetch_oa_fulltext_xml`, `_extract_from_paper_with_retry` (verified contradicts passage). Asserts item `preprocess_outcome == "evidence_negated"` and `model_direction == "contradicts"` after a real-DB batch loop run.

**Defect-guard proof:** temporarily breaking the flag (`pass` instead of `query_is_negative = True`) makes the new test FAIL with AssertionError on the outcome assert; restored → passes. The test genuinely guards the fix.

**Post-fix verification:**

```
pytest tests/test_evidence_target_adapter.py tests/test_paper_evidence_batch.py tests/test_paper_evidence_batch_phase4.py -q
20 passed in 13.98s   (then 12.66s on final run — 19 prior + 1 new)
```

## Files Committed (brief-named set + the fix's test file)

- `backend/app/services/evidence_target_adapter.py`
- `backend/app/services/paper_evidence_service.py`
- `backend/tests/test_evidence_target_adapter.py` (new)
- `backend/tests/test_paper_evidence_batch.py` (Fix 3 test — 4th file required by the review fix; commit amended with the same message)

## Concerns

1. **Adapter file carried pre-existing uncommitted changes into the commit.** `evidence_target_adapter.py` was already modified in the working tree before this task started (a prior-task refactor of `build_search_query`/`build_target_dto` — cn-name metadata, circuit_context resolution, token dedup). Per the caller's instruction to `git add` the brief-named files as whole files, the commit includes that pre-existing work (150 insertions total vs ~15 from this task). If those changes belonged to another task's commit, they should be split out or the parent orchestrator should confirm they belong together.
2. **`query_is_negative` placement** — resolved by review Fix 2: the flag is now a plain boolean declared at the initial query assignment and set `True` only on negative-round hit; the brief's "在函数开头记录" intent is satisfied exactly (no string matching).
3. **`evidence_negated` outcome path** — resolved by review Fix 3: `TestBatchStateMachine::test_negative_round_marks_evidence_negated` covers the full flow (real DB batch loop, mocked search/extraction) and was proven to fail when the flag logic is broken.
4. **OR-group shape note.** The negative round now queries `ABSTRACT:"BLA" AND ABSTRACT:"IL" AND (ABSTRACT:"no projection" OR ...)`; Europe PMC interprets the OR-group as a single required clause, so any one negation phrase suffices. The negation phrases are ABSTRACT-scoped even though the negative round passes `abstract_only=False` — the coordinator's prescribed group uses `ABSTRACT:` prefixes verbatim; BODY variants could be added later if recall is insufficient.
