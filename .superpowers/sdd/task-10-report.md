# Task 10 Report: EvidenceTasksModule 重写(对象级任务卡+跳转+排序+筛选)+ 测试重写

## Status: DONE_WITH_CONCERNS (1 documented deviation from verbatim brief)

## What was implemented

1. **Test rewrite** (`frontend/src/pages/evidence-center/modules/EvidenceTasksModule.test.tsx`): replaced wholesale with the brief's verbatim code (9 tests: 对象级命名 3、整卡跳转+initial-queue 快照、按钮 stopPropagation、排序、筛选 chips、继续验证直达、重试确认弹窗). One assertion deviation — see Concerns.
2. **Component rewrite** (`frontend/src/pages/evidence-center/modules/EvidenceTasksModule.tsx`): replaced wholesale with the brief's verbatim code. Object-level task cards (`objectCardTitle` = 中文 (英文) / 兜底「类型中文 #短ID」), full-card click → `navigateToEvidenceCandidates` (writes `evidence-center.initial-queue` sessionStorage + jumps `#/validation-center?tab=paper_evidence&module=candidates&task_id=…&target_*`), buttons `stopPropagation`, status-group sort (处理中→已暂停→待验证→已完成→部分失败→失败;组内置信度升序 null 最前), type filter chips, removed `useEvidenceCenter`/`openTask`/inline `EvidenceCandidatesModule` embedding.

## TDD evidence

- **RED** (old component + new test): `npx vitest run src/pages/evidence-center/modules/EvidenceTasksModule.test.tsx` → `Test Files 1 failed (1) / Tests 7 failed | 2 passed (9)`. Failures confirmed the expected mode: old component renders stats rows instead of object display names; card click still went through `openTask` (hash stayed `#/evidence-center?module=tasks`).
- **GREEN** (new component): same command → `Tests 9 passed (9)` after the single test-assertion fix below.
- **Type check**: `npx tsc --noEmit -p tsconfig.json` → exit 0.
- **Regression check**: `EvidenceTasksModule.test.tsx` + `EvidenceCenterPage.test.tsx` → `Test Files 2 passed (2) / Tests 31 passed (31)`. (`EvidencePromotionModule.test.tsx` known-flaky, not run, per task notes.)

## Files changed (committed)

- `frontend/src/pages/evidence-center/modules/EvidenceTasksModule.tsx` (rewritten, brief verbatim)
- `frontend/src/pages/evidence-center/modules/EvidenceTasksModule.test.tsx` (rewritten, brief verbatim except 1 assertion, see below)

## Commit

- `d3392e7` feat(evidence-ui): object-named task cards with jump-to-candidates navigation (2 files changed, 401 insertions, 160 deletions — only the two brief-named files staged; unrelated pre-existing working-tree changes left untouched)

## Concerns (root cause outside brief code — fixed in-scope)

The brief's verbatim test `待验证任务「继续验证」:有 target_id 直接跳转,不查 items` asserts `listPaperEvidenceTaskItems` was **never** called. That can never pass: `useEvidenceTaskItems` (shared hook, delivered in T8/T9) itself calls `listPaperEvidenceTaskItems(t.id, { limit: 100, sort: 'confidence' })` twice in this scenario —
1. on mount (global-mode pre-fetch for every non-cancelled task with `total_items > 0`), and
2. after the click, because `navigateToEvidenceCandidates` changes the hash → `EvidenceCenterProvider`'s `hashchange` listener (`EvidenceCenterContext.tsx` lines 130-136) updates `state.taskId` to `'t1'` → the hook re-fetches in task mode.

Suppressing those calls would require changing the shared hook/provider, which `TaskPendingQueue`/`TaskProcessedPanel` depend on (regression), and would add files outside the brief's named scope. The minimal in-scope fix was one assertion in the test, matching the project's own existing convention (old suite asserted on call signatures, not zero calls):

```typescript
expect(vi.mocked(endpoints.listPaperEvidenceTaskItems)).not.toHaveBeenCalledWith(
  't1', { status: 'awaiting_review', limit: 1, sort: 'confidence' },
)
```

This preserves the test's intent (the 「继续验证」 handler does not fire the fallback awaiting-review query when `target_id` exists) while tolerating the shared hook's own `{ limit, sort }`-signature fetches. All other brief code (makeTask fixture fields, sort assertion order, sessionStorage assertions) is verbatim.

## Verification notes

- Dependency exports verified before starting: `taskStatus.ts` exports `objectCardTitle`/`formatConfidencePercent`/`TARGET_TYPE_LABELS`/`WORK_STATUS_LABELS`/`workStatusTone`; `evidenceCenterUrl.ts` exports `navigateToEvidenceCandidates({ items, taskId })` writing `evidence-center.initial-queue`; `PaperEvidenceTask` in `api/endpoints.ts` includes `target_id`/`display_name_cn`/`display_name_en`/`display_confidence`/`work_status`/`item_counts`/`capabilities`.

## Review fix (Important, plan-mandated) — keyboard event guard

Reviewer found: card `onKeyDown` (Enter/Space → onJump) did not check `e.target`, so keydown events from inner action buttons bubbled to the card and triggered navigation — keyboard Enter on 暂停/继续验证/重试 would jump the card in addition to the action. Fixed:

1. `EvidenceTasksModule.tsx` TaskCard `onKeyDown` now guards `if (e.target !== e.currentTarget) return` before the Enter/Space handling.
2. Added regression test `键盘 Enter 触发在按钮上时不冒泡触发整卡跳转` (Enter on 暂停 button → no jump; Enter on card itself → jump) per reviewer's verbatim code.

Results: `npx vitest run src/pages/evidence-center/modules/EvidenceTasksModule.test.tsx` → `Tests 10 passed (10)`; `npx tsc --noEmit -p tsconfig.json` → exit 0.

## Commit (amended)

- `git commit --amend` on the same two files (component + test). Final SHA reported in task completion message.
