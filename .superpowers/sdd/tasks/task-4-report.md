# Task 4 Report: 路由/侧边栏/页面壳与模块导航

**Status: Implemented ✅ (TDD RED → GREEN, all green)**

## TDD

- **RED**: Wrote `EvidenceCenterPage.test.tsx` (2 tests from brief) → ran `npx vitest run src/pages/evidence-center/EvidenceCenterPage.test.tsx` → FAIL (module `./EvidenceCenterPage` transform error, 0 tests ran) ✓
- **GREEN**: Implemented page shell + Header + placeholder module + route/sidebar/i18n wiring → targeted test **2 passed** ✓

## Files

**Created:**
- `frontend/src/pages/evidence-center/EvidenceCenterPage.tsx` — page shell (`EvidenceCenterProvider` wrapper + Header + Body with `MODULE_TITLE`/`MODULE_HINT`; named export + default export; `tasks` module rendered, others stubbed until Task 6-9)
- `frontend/src/pages/evidence-center/EvidenceCenterHeader.tsx` — five module nav buttons (`tasks/papers/candidates/review/promotion`, active class via `state.module`) + 返回数据中心 button (`#/data-center`)
- `frontend/src/pages/evidence-center/modules/EvidenceTasksModule.tsx` — **placeholder** `佐证任务模块(建设中)` (T5 will replace with real implementation, per task instructions)
- `frontend/src/pages/evidence-center/EvidenceCenterPage.test.tsx` — 2 tests exactly per brief

**Modified:**
- `frontend/src/App.tsx` — `ROUTES` + `'/evidence-center': EvidenceCenterPage` (+ import)
- `frontend/src/layout/WorkbenchLayout.tsx` — NAV_ITEMS + `{ path: '/evidence-center', labelKey: 'nav.evidenceCenter', icon: FileText }` (icon already imported)
- `frontend/src/i18n.ts` — `nav.evidenceCenter`: zh `论文证据中心` + en `Evidence Center` (en section exists; kept consistent)

## Verification

- Targeted test: `npx vitest run src/pages/evidence-center/EvidenceCenterPage.test.tsx` → **2 passed**
- Full suite: `npx vitest run` → **5 files / 36 tests passed**
- Build: `npm run build` → **built in 2.35s** (only pre-existing chunk-size warning, unrelated)
- Pre-existing `evidenceCenterUrl.test.ts` (Task 3) still passes

## Commit

`feat(evidence-center): 路由/侧边栏/页面壳/模块导航` — exactly 7 files staged (3 modified + 4 new), 98 insertions, no unrelated working-tree changes included. Worktree has many unrelated uncommitted changes which were left untouched.

## Self-review

- Consumes Task 3 context exactly (`useEvidenceCenter`, `ModuleKey`, `gotoModule`); no API mismatch — TypeScript + build confirm
- Test asserts URL sync (`module=papers`) + content-area hint swap + 返回数据中心 redirect — all exercised
- No console.log, no mutation, small focused files, hooks used per rules
- Dual named/default export satisfies both the test (`{ EvidenceCenterPage }`) and brief's 默认导出 requirement

## Concerns

- Evidence center page has no CSS classes defined in `styles.css` yet (`.evidence-center-*`, `.evidence-module-*` are unstyled, falling back to default button/browser styles). Not in brief scope; suggest a dedicated styling task (Task 5+ or follow-up) so the nav buttons look consistent with the medical-blue design system.
- `FileText` icon is reused for both 文件管理 and 论文证据中心 sidebar entries (brief explicitly suggested `FileText`); can swap to a distinct icon (e.g. `Library`, `Newspaper`) later if desired.
- en i18n section lacks `nav.ontologyCenter`/`nav.validationCenter` (pre-existing gap); added `nav.evidenceCenter` to en anyway since it exists and is correct.
