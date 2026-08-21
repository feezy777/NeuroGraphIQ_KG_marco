# Task 1 Report: 语义分块函数 (build_semantic_windows)

## Status: DONE_WITH_CONCERNS

## TDD Evidence

### RED (Step 2)
Command: `cd backend && ./.venv/Scripts/python.exe -m pytest tests/test_paragraph_retrieval.py -q -k semantic`

Output (tail):
```
_____________________________ ERROR collecting tests/test_paragraph_retrieval.py ______________
ImportError while importing test module 'D:\...\backend\tests\test_paragraph_retrieval.py'.
E   ImportError: cannot import name 'build_semantic_windows' from 'app.services.paragraph_retrieval' (D:\...\backend\app\services\paragraph_retrieval.py)
=========================== short test summary info ===========================
ERROR tests/test_paragraph_retrieval.py
!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
1 error in 0.10s
```
Expected RED confirmed: ImportError `cannot import name 'build_semantic_windows'`.

### First GREEN attempt (brief code verbatim) — 1 FAIL
Command: `.\.venv\Scripts\python.exe -m pytest tests/test_paragraph_retrieval.py -q`

Output: `1 failed, 3 passed in 0.14s`
- FAILED: `test_merges_short_paragraphs_into_blocks`
- `assert 2 == 1` — brief's implementation (seal when `current_len + length > target_chars`) split 3×300-char paragraphs (900 chars total) into 2 blocks, but the brief's own test expects 1 block of 3 paragraphs.

### Deviation from verbatim brief (documented)
The brief's implementation condition `if current and current_len + length > target_chars and current_len >= 1` contradicts the brief's test `test_merges_short_paragraphs_into_blocks` (3×300=900 chars > target 800 must still merge into ONE block). The docstring in the brief ("段落到 target_chars 上限即封块") supports soft-cap semantics: a block is sealed only once it has already reached `target_chars`.

Minimal change applied (all other code verbatim):
```python
if current and current_len >= target_chars:   # was: current_len + length > target_chars and current_len >= 1
```
Note: the `current_len >= 1` guard became redundant (`current` truthy implies ≥1 paragraph).

### GREEN (Step 4)
Command: `.\.venv\Scripts\python.exe -m pytest tests/test_paragraph_retrieval.py -q`
Output: `4 passed in 0.10s`

Regression check (related existing suite):
Command: `.\.venv\Scripts\python.exe -m pytest tests/test_paper_retrieval_phase2.py tests/test_paragraph_retrieval.py -q`
Output: `20 passed in 0.28s`

## Commit
- SHA: `ee66b85` — `feat(evidence): build_semantic_windows — paragraph blocks for LLM semantic recall`
- Staged files (exactly the two brief-named files):
  - `backend/app/services/paragraph_retrieval.py` (M)
  - `backend/tests/test_paragraph_retrieval.py` (A, new — file did not exist before; created with module docstring header + `from app.services.paragraph_retrieval import build_semantic_windows` + 4 tests verbatim from brief)

## Concerns
1. **Brief internal inconsistency (main)**: the brief's verbatim implementation fails its own verbatim test `test_merges_short_paragraphs_into_blocks` (2 blocks vs expected 1). I made the smallest deviation to reconcile (see above) so all 4 tests pass per Step 4's "全部通过". If the intended behavior was instead a hard cap (seal as soon as the next paragraph would exceed 800 chars), the test needs updating instead — Task 2 should be checked against the chosen soft-cap semantics (block may exceed target_chars by up to one paragraph; single oversized paragraphs stand alone).
2. Test `test_split_long_text_into_multiple_blocks` only asserts `len(blocks) >= 2` and pid order — loose but as specified.
3. `ordered.sort` is stable (Python sort), so abstract paragraphs keep relative order among themselves; order within a block is preserved.

## Files
- `D:\Tool\Coding\IDE\PyCharm\NeuroGraphIQ_KG_V3_1\backend\app\services\paragraph_retrieval.py`
- `D:\Tool\Coding\IDE\PyCharm\NeuroGraphIQ_KG_V3_1\backend\tests\test_paragraph_retrieval.py`
