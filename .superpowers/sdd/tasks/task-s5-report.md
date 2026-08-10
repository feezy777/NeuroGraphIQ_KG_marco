# Task S5 Report: 佐证任务右栏 Task Summary + 论文库全宽确认 + 视觉收尾

**Status:** DONE
**Date:** 2026-08-10
**Commit:** `feat(evidence-center): 佐证任务右栏摘要 + 论文库全宽 + 视觉收尾`

## 1. 佐证任务右栏 Task Summary

按 S3 reviewDecision / S4 promotionImpact 同模式(Context 推送 → RightPanel 渲染)实现:

- **新建 `frontend/src/pages/evidence-center/components/TaskSummary.tsx`**
  - `TaskSummaryData`: 选中任务的 id/name/targetType/mode/granularity/status/reviewStatus/total/processed/awaitingReview/failed/createdAt
  - `TaskSummaryActions`: `{ onCreateBatch, onRefresh }` 回调接口(对话框与列表刷新都归模块所有,经 Context 暴露)
  - UI: 任务名 + 类型 chip + 预处理/审核状态 chips → 处理进度堆叠计数条(已处理绿/待审琥珀/失败红,宽度=占比)+ 四格计数(已处理/待审/失败/总数)→ subtle divider → 任务信息(模式/粒度/创建时间,UTC 格式化避免时区漂移)→ 操作 [开始人工处理(primary)] [创建批量预处理] [刷新]
- **`EvidenceCenterContext.tsx`**: 新增 `taskSummary/setTaskSummary`(数据)与 `taskSummaryActions/setTaskSummaryActions`(模块注册的操作回调,默认 no-op)
- **`RightPanel.tsx`**: `module === 'tasks'` 渲染 TaskSummary,`onStartReview` → `openTask(taskSummary.id)`(跳候选模块,URL 带 task_id)
- **`EvidenceTasksModule.tsx`**:
  - 任务行可点击选中(`data-testid="evidence-task-row-<id>"` + `evidence-task-row-selected` 高亮)
  - 选中任务 → `useMemo` 转 TaskSummaryData → effect 推送 Context;卸载时清空
  - URL 携带 `task_id` 时自动选中该任务(从候选/审核模块返回任务列表时摘要仍在)
  - 注册 `taskSummaryActions`(稳定引用:loadTasks 已是 useCallback([]),handleCreateBatch 同样稳定)
  - 状态标签/色调用法抽取到新建 `components/taskStatus.ts`(TASK_STATUS_LABELS/TASK_REVIEW_LABELS/taskStatusTone/taskReviewTone),模块与 TaskSummary 共用,消除重复
  - 行内按钮点击冒泡会同时选中行,语义无害

## 2. 论文库全宽确认

- S1 已实现 `evidence-center-layout-full`(grid 1fr,隐藏左右栏);主区不再受 `minmax(620px,1fr)` 限制
- 本轮微调:`.evidence-center-layout-full .evidence-main { max-width: 1280px; margin: 0 auto; }` 限制可读行长;`.paper-module` 搜索条/列表/分页在 jsdom 与 build 均正常
- 回归:EvidenceCenterPage.test 'papers 模块例外' 扩展断言 `.paper-module` + `.paper-search-bar` + 空态渲染

## 3. 视觉收尾(§17)

- 三栏骨架 `.evidence-left/.evidence-main/.evidence-right` 去掉 `border`/`box-shadow`(页面灰底 `--bg:#f2f3f5` + 白底栏 + 14px gap 即分隔),符合"减少灰色 border,用 spacing 分隔"
- 新增 `.evidence-section-divider`(1px, opacity .6)用于右栏 section 间轻分隔
- Primary 按钮收敛核对:tasks=开始人工处理 / candidates=进入人工审核 / review=审核通过 / promotion=确认晋升,每模块仅当前步骤主操作带 btn-primary(论文库主操作=搜索)
- section 标题层级核对:h3(15px)仅用于模块级 toolbar 标题(tasks/论文库),子区块统一 h4,与 candidates/review/promotion 一致

## 4. 测试(TDD)

- RED:先写测试(5 个新用例),确认右栏仍为占位(5 failed)
- GREEN:实现后 `evidence-center` 全部 132 passed
- 新增用例(EvidenceTasksModule.test.tsx):
  1. 未选中任务时右栏显示引导提示
  2. 选中任务后右栏显示进度计数条(0%/100%/0%)、计数、状态 chips、模式/粒度/创建时间,行高亮
  3. TaskSummary [开始人工处理] 跳候选模块(URL task_id)
  4. TaskSummary [创建批量预处理] 打开模块对话框、[刷新] 重新加载列表
  5. URL 携带 task_id 自动选中并显示摘要
- 期间修复:RightPanel 重构时误删 `state` 解构导致 candidates 分支 `ReferenceError: state is not defined`(修复后回归通过)

## 5. 验证

- `npx vitest run src/pages/evidence-center/` → 15 files, 132 passed
- 全量 `npx vitest run` → 18 files, 146 passed
- `npm run build` → 0 TypeScript errors, built (chunk size warning 为既有,非本轮引入)

## 6. Files Changed

- Modify: `frontend/src/pages/evidence-center/modules/EvidenceTasksModule.tsx`
- Modify: `frontend/src/pages/evidence-center/components/RightPanel.tsx`
- Modify: `frontend/src/pages/evidence-center/EvidenceCenterContext.tsx`
- Modify: `frontend/src/styles.css`
- New: `frontend/src/pages/evidence-center/components/TaskSummary.tsx`
- New: `frontend/src/pages/evidence-center/components/taskStatus.ts`
- Test: `frontend/src/pages/evidence-center/modules/EvidenceTasksModule.test.tsx`
- Test: `frontend/src/pages/evidence-center/EvidenceCenterPage.test.tsx`

## Fix: V2-S5 Review Finding — 佐证任务模块 Primary 按钮收敛

- Commit: `8ffb8c3` — `fix(evidence-center): 佐证任务模块 Primary 按钮收敛(仅右栏开始人工处理)`
- `EvidenceTasksModule.tsx` L56 每行「开始人工处理」: 去掉 `btn-primary`(保留 `btn btn-xs`)
- `EvidenceTasksModule.tsx` L163 工具栏「创建批量预处理」: 去掉 `btn-primary`(保留 `btn btn-sm`)
- TaskSummary.tsx L109「开始人工处理」保持 `btn btn-sm btn-primary`(当前步骤主操作,右栏)
- 全模块 grep 复查: 无其他 `btn-primary`;同目录其余 btn-primary(PaperLibraryModule 搜索、ReviewerDecisionPanel 审核通过、PromotionImpact 晋升等)均属各自模块当前步骤主操作,保留
- 验证: 定向测试 12 passed;全量 `npx vitest run` 18 files / 146 tests passed;`npx tsc --noEmit` 0 错误
