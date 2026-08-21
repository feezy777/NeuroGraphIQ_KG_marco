# Task 2 Report: `mirror_live_display_name_parts` 中英双名解析

**Status:** DONE_WITH_CONCERNS

## What Was Implemented

New pure function `mirror_live_display_name_parts(target_type: str, get) -> tuple[str | None, str | None]` in
`backend/app/services/paper_evidence_service.py` (inserted after `mirror_live_display_name`, now at line 730).
Returns `(cn, en)` per `target_type` (`connection`/`projection`/`circuit`/`circuit_step`/`circuit_function`/`region_function`/`projection_function`);
each language part is independently `None` when missing; unknown type returns `(None, None)`.
Reuses existing helpers `_pick_cn_en` / `_clean_text`. Pure function, no DB access.

New test file `backend/tests/test_paper_evidence_display_parts.py` (11 tests, verbatim from the brief).

## TDD Evidence

**RED** — `cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_paper_evidence_display_parts.py -q`:
```
ImportError: cannot import name 'mirror_live_display_name_parts' from 'app.services.paper_evidence_service'
1 error in 0.11s
```
Expected: function did not exist yet.

**GREEN** — same command:
```
...........                                                              [100%]
11 passed in 0.17s
```

**Regression check** — `./.venv/Scripts/python.exe -m pytest tests/test_paper_evidence.py -q` → `17 passed`.

## Files Changed / Committed

- `backend/app/services/paper_evidence_service.py` (add `mirror_live_display_name_parts`)
- `backend/tests/test_paper_evidence_display_parts.py` (new, 11 tests)

Commit: `d441709e48a2fa63b3301ab90b0bdf6ea892f472` — `feat(evidence): mirror_live_display_name_parts cn/en pair resolver`
(on branch `codex/ontology-evidence`, staged only the two files named by the brief).

## Concerns

1. **Brief had an internal inconsistency (verbatim code vs verbatim test).** The brief's implementation block used
   `_pick_cn_en(get, "source_region_name_cn", "source_region_name_en")` for the connection cn part, which falls back to
   English when Chinese is missing. That directly contradicts the brief's own interface contract ("中文缺失仅英文")
   and fails its own test `test_connection_cn_missing_keeps_en` (10 passed / 1 failed on first run).
   Per TDD, the test is the executable spec: I changed the connection/projection branch to use Chinese-only columns
   (`_clean_text(get("source_region_name_cn"))` / `target_region_name_cn`) for the cn part. All 11 brief tests pass.
   Everything else matches the brief verbatim.

2. **Commit swept in pre-existing uncommitted WIP in `paper_evidence_service.py`.** Before this task, the working tree
   already contained ~2400 lines of uncommitted changes in that file (the `mirror_live_display_name` /
   `mirror_live_confidence` / `_derive_work_status` / `list_paper_evidence_tasks` rework etc. — the live-display
   infrastructure my function depends on; none of it exists in parent commits df7dda0/d1f94e3). The brief's Step 5
   `git add` of the whole file necessarily included that WIP, so commit d441709 contains it (2490 lines changed for the
   service file, ~40 of which are mine). The committed tree is green (11 + 17 tests pass). If the parent wants
   different attribution, the commit can be amended; note my function cannot be isolated cleanly because it depends on
   the same uncommitted `_pick_cn_en`/`_clean_text` helpers.

## Review Fix (⚠️ item)

Reviewer requested the `region_function` branch be consistent with the per-language None contract. Applied:

- `region_cn` now uses `_clean_text(get("region_name_cn"))` (no `_pick_cn_en` English fallback);
  `en` now returns `None` when the region en name is missing (removed the `(term or None)` term-only fallback).
- Added 3 tests: `test_region_function_cn_missing_keeps_en_only`, `test_region_function_en_missing_keeps_cn_only`,
  `test_region_function_no_region_names`.

**GREEN:** `cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_paper_evidence_display_parts.py -q` →
`14 passed in 0.18s`

Amended commit (only the two task files staged): `712da82` — `fix(evidence): region_function cn/en strict per-language None contract`
(replaces d441709; branch `codex/ontology-evidence`).
