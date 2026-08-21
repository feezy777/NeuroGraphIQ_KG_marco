# Final Review Fix Report

Commit: `67da6d765f0c36d8de4697386025d4900db0a9e1` — fix(evidence-center): 晋升后标记任务项完成 + 返回候选时同步落盘草稿

## Finding 1 (Critical): 晋升后任务项未标记完成

`frontend/src/pages/evidence-center/modules/EvidencePromotionModule.tsx`

- `handlePromote` 现在捕获 `attachPaperEvidence` 响应 `resp`，在清理草稿/更新 queue 后，若 `state.taskId && queueEntry?.taskItemId` 则调用 `completePaperEvidenceTaskItem(state.taskId, queueEntry.taskItemId, resp.evidence_id)`（import 自 `../../../api/endpoints`），失败静默 catch，不阻断主流程——与旧 Modal（`EvidenceReviewModal` 的 `taskIdRef.current && current.taskItemId` 条件）一致。
- queueEntry 复用模块现有查找方式：`queue.find(q => q.target_type === targetType && q.target_id === targetId)`。
- 新增依赖 `state.taskId` 到 `handlePromote` 的 useCallback deps。

## Finding 2 (Important): 审核草稿 500ms 丢稿窗口

`frontend/src/pages/evidence-center/modules/EvidenceReviewModule.tsx`

- 提取 `persistDraft()`（useCallback：`targetId` 存在且 `passages.length > 0` 时写 sessionStorage），debounce effect 改用它。
- `handleBack`（返回证据候选）在 `openTarget(...,'candidates')` 之前同步调用 `persistDraft()`，最后 500ms 内的编辑立即落盘。
- 增加卸载 flush：`persistDraftRef`（每渲染同步最新 callback）+ 空依赖 effect cleanup 调用 `persistDraftRef.current()`——切模块（模块条件渲染卸载）也不丢稿。

## Tests

- `EvidencePromotionModule.test.tsx`：mock 新增 `completePaperEvidenceTaskItem`；新增 `QueueSeeder`（queue 带 taskItemId）。新增 2 用例：
  - 晋升成功 → 调用 `completePaperEvidenceTaskItem('t1', 'item-1', 'ev-new')`；且标记接口 reject 时主流程仍完成（列表刷新 + 成功消息 + 草稿清除）。
  - URL 无 `task_id` → 不调用。
- `EvidenceReviewModule.test.tsx`：新增 1 用例——修改备注后立即点击「返回证据候选」（不等待 500ms debounce），断言 sessionStorage 已含最新备注。

## Verification

- 定向：`npx vitest run src/pages/evidence-center/modules/EvidencePromotionModule.test.tsx src/pages/evidence-center/modules/EvidenceReviewModule.test.tsx` → 2 files, 17 tests passed
- 全量：`npx vitest run` → 10 files, 65 tests passed
- `npx tsc --noEmit` → 0 errors
