# Task 3 Report: EvidenceCenterContext + URL 纯函数

Status: DONE

## Implemented

Three files created under `frontend/src/pages/evidence-center/`:

1. **`evidenceCenterUrl.test.ts`** — test file (brief Step 1, transcribed verbatim):
   - parses module/task/target/paper from hash
   - defaults module to `tasks` when absent
   - buildEvidenceUrl ↔ parseEvidenceUrl round-trip

2. **`evidenceCenterUrl.ts`** — URL pure functions (brief Step 3, transcribed verbatim):
   - `interface EvidenceCenterState { module, taskId, targetType, targetId, paperId }`
   - `parseEvidenceUrl(hash)` — strips `#`, splits `?`, validates path `/evidence-center`, whitelists module against `['tasks','papers','candidates','review','promotion']`, falls back to `tasks`
   - `buildEvidenceUrl(state)` — returns `#/evidence-center?...` omitting empty/`tasks` params
   - imports `ModuleKey` type-only from `./EvidenceCenterContext` (circular import is type-only, erased at runtime — safe)

3. **`EvidenceCenterContext.tsx`** — unified Context (brief Step 5, transcribed verbatim):
   - `export type ModuleKey = 'tasks' | 'papers' | 'candidates' | 'review' | 'promotion'`
   - `EvidenceCenterProvider` — state initialized from `window.location.hash`, synced on `hashchange`, `apply()` writes back via `window.location.hash` (with no-op guard), queue state
   - API: `{ state, queue, setQueue, gotoModule, openTask, openTarget, selectPaper }` via `useEvidenceCenter()` (throws outside provider)
   - consumes `QueueEntry` from `./components/types` (Task 2, already committed in 498d59e)

## TDD Evidence

- **RED** (14:57:30): `npx vitest run src/pages/evidence-center/evidenceCenterUrl.test.ts` → `Test Files 1 failed (1)` — import of nonexistent `./evidenceCenterUrl` failed to resolve
- **GREEN** (14:57:36): same command → `Test Files 1 passed (1) / Tests 3 passed (3)`

## Verification

- Targeted: 3/3 passed (after Context file added too)
- Full suite: `npx vitest run` → **4 files / 34 tests passed**, no regressions
- `npx tsc --noEmit` → clean (Context compiles against `components/types.ts` QueueEntry)

## Commit

- `5d6f3ac feat(evidence-center): URL 解析/构建 + 统一 Context`
- Exactly 3 files staged via explicit paths (workspace has many unrelated uncommitted changes — none included): 109 insertions

## Self-Review

- Code transcribed exactly from brief (diff-free); test assertions match brief Step 1
- Circular import `evidenceCenterUrl → EvidenceCenterContext` is `import type` only — runtime graph is acyclic, verified by passing vitest + tsc
- Round-trip test 3 covers non-default module; default `tasks` + nulls case covered by test 2
- `apply()` guard (`window.location.hash !== url`) prevents redundant hash writes
- Per brief, only the URL pure functions have tests; the Context component has no dedicated test (matches brief design)

## Concerns

- None blocking. Minor note: `window` access in `EvidenceCenterProvider` initial state makes it browser-only (fine for this Vite SPA; would need guarding if ever SSR'd).
- Brief Step 6 suggested `git add frontend/src/pages/evidence-center` (whole dir); I staged only the 3 new files per explicit task instruction — the directory otherwise contained no uncommitted files, so no divergence in effect.

Report path: `.superpowers/sdd/tasks/task-3-report.md`
