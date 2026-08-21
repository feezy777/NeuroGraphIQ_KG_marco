# Task 11 Report: 创建对话框消息 + 左栏 Claim 面板 + 页面测试更新

## Status: DONE

## What changed (per brief, verbatim)

1. `frontend/src/pages/evidence-center/components/CreateBatchTaskDialog.tsx`
   - Success message: `setMessage(\`任务已创建（${r.target_count} 个对象）\`)` → `setMessage(\`任务已创建（${r.task_ids?.length ?? r.target_count} 个对象任务）\`)`.
   - Uses Task 8's extended return type (`task_ids: string[]` already present in `createPaperEvidenceBatch` signature in `api/endpoints.ts` line 5737).

2. `frontend/src/pages/evidence-center/EvidenceCenterPage.tsx`
   - Removed `import { TaskPendingQueue } from './components/TaskPendingQueue'` (component file kept, no longer referenced by the page).
   - tasks-module left-column branch replaced `TaskPendingQueue` with a fragment: empty-state hint `evidence-left-hint` ("点击任务卡片查看验证事实", shown when `candidateClaim` is null) + `ClaimSummaryPanel` fed from `candidateClaim`.
   - review/promotion branch (ObjectQueue) untouched.

3. `frontend/src/pages/evidence-center/EvidenceCenterPage.test.tsx`
   - `TASK_FIXTURE` extended with `target_id`, `display_name_cn/en`, `display_confidence`, `display_name_source`, `display_confidence_source`, `work_status`, `item_counts`, `capabilities` (matches `PaperEvidenceTask` type from T8).
   - Replaced 「tasks 布局」test with the new Claim-panel + empty-hint + right-panel test.
   - Replaced 「中栏对象点击」test with the task-card click → candidates navigation test (`evidence-task-card-ta` → hash contains `module=candidates`, `task_id=ta`, `target_id=r1-r2`).
   - 「tasks 三栏常显」test untouched; its `getAllByText('R1→R2')` assertion now passes via the card title (`objectCardTitle` dedupes cn===en → renders exactly 'R1→R2').

## Verification

- `cd frontend && npx vitest run src/pages/evidence-center/EvidenceCenterPage.test.tsx src/pages/evidence-center/modules/EvidenceTasksModule.test.tsx`
  - Result: **2 test files passed, 32 tests passed** (Duration ~1.5s).
- `npx tsc --noEmit` (whole frontend): exit 0, no type errors.
- `EvidencePromotionModule.test.tsx` (known unrelated intermittent failure) not touched, not run.

## Files changed (commit 4150b42)

- frontend/src/pages/evidence-center/components/CreateBatchTaskDialog.tsx
- frontend/src/pages/evidence-center/EvidenceCenterPage.tsx
- frontend/src/pages/evidence-center/EvidenceCenterPage.test.tsx

Commit: `4150b42 feat(evidence-ui): tasks left column Claim panel; batch dialog counts object tasks`
Verified via `git show --stat` that the commit contains only these 3 files (94 insertions, 35 deletions). Pre-existing unrelated working-tree modifications were not staged.

## Concerns

- `evidence-left-hint` has no CSS rule yet (grep found no matches). It renders as plain unstyled text inside `.evidence-left`; tests only assert testid/text, and the brief did not request styling. Flag if visual styling is wanted in a follow-up.
- Brief 代码块本身全部逐字匹配(94-96 行分支、TASK_FIXTURE 插入点),但提交 diff 除 brief 点名改动外,还捎带了工作树中会话前已有的未提交 WIP——详见下方「Diff 披露(审查补)」。原「no deviations」表述不准确,以本节为准。

## Diff 披露(审查补)

控制器已核实:以下 4 处超出 brief 的 diff 均为会话开始前工作树中即已存在的未提交 WIP(位于本任务点名的两个页面文件内,brief 的行号即针对该文件状态编写),因整文件 `git add` 被捎带进提交,非本任务新增改动:

1. `TaskItemsRefreshProvider` 包装(`EvidenceCenterPage.tsx`):会话开始前工作树即已存在(`useEvidenceTaskItems` 依赖其 version 刷新),被整文件提交捎带。
2. `EvidenceCenterPage.test.tsx` 晋升模块断言 `.evidence-promotion` → `.evidence-review` + 文案正则变更:既有未提交的测试修正(晋升模块空态文案在先前会话已改),被捎带。
3. mock 工厂重构 + `resolvePaperEvidenceTaskItem` 默认 mock:既有未提交改动,新「任务卡点击跳转」用例也依赖该 mock。
4. 「tasks 三栏常显」的 `current_confidence: 0.4 → 0.2`:既有未提交的对齐 tweak(与 fixture 的 `display_confidence` 0.2 一致)。

结论:无需代码变更,提交内容保留。
