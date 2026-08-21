# Task 10 Report: 数据中心入口切换 + EvidenceReviewModal 兼容壳 + 五模块接入

## Status: ✅ 完成

## 提交(3 个逻辑提交,分支 codex/ontology-evidence)

1. `d46b132` refactor(evidence): EvidenceReviewModal 改为跳转兼容壳 + 数据中心交接 helper
2. `37190f9` feat(evidence): 数据中心入口切换为 Evidence Center 跳转
3. `ce6d457` feat(evidence-center): 五模块全部接入 EvidenceCenterPage + 候选模块 initial-queue 恢复

## 改动内容

### 1. EvidenceReviewModal → 兼容壳(`frontend/src/pages/data-center/EvidenceReviewModal.tsx`)
- 删除全部工作台业务逻辑(约 1100 行:队列/检索/提取/审核/attach/草稿/翻译/预览等)及其 import
- props 不变 `{open, onClose, initialItems?, initialTaskId?}`,open 时:
  - initialItems 有值 → 写 `sessionStorage['evidence-center.initial-queue'] = {items, taskId}`
  - `window.location.hash = buildEvidenceUrl({module:'candidates', taskId, targetType: first?.target_type, targetId: first?.target_id, paperId: null})`
  - 调用 onClose,return null

### 2. 共享交接 helper(`frontend/src/pages/evidence-center/evidenceCenterUrl.ts`)
- 新增 `INITIAL_QUEUE_KEY`、`EvidenceQueueHandoffItem`、`navigateToEvidenceCandidates({items?, taskId?})`
- 兼容壳与三个调用点共用,避免重复逻辑

### 3. 入口切换(调用点不再渲染 Modal,直接跳转)
- `BackgroundTaskCenter.tsx`:删除 `workbenchTaskId` 状态与 `<EvidenceReviewModal/>`;`onOpenWorkbench`/`onCreated` 改为 `navigateToEvidenceCandidates({taskId})`
- `MirrorKgPanel.tsx`:删除 reviewOpen/reviewItems 状态与 Modal;`onPaperEvidence` 改为 `navigateToEvidenceCandidates({items})`
- `MacroClinicalDataPanel.tsx`:同上,`handlePaperEvidence` 改为交接跳转

### 4. 五模块接线(`EvidenceCenterPage.tsx`)
- Body 渲染 tasks/papers/candidates/review/promotion 全部五个模块(替换原 tasks-only 占位)

### 5. 候选模块 initial-queue 恢复(`EvidenceCandidatesModule.tsx`)
- 挂载时(无 taskId)读 `evidence-center.initial-queue`,一次性消费(读完 remove),填充 queue(status=pending, evidenceCount=0)并提示「已从数据中心恢复 N 个待处理对象」
- 注意:恢复 effect 必须声明在「切换目标重置」effect 之后(该 effect 会 setMessage(null)),依赖 effect 声明顺序,已加注释说明

### 6. 测试改造
- `EvidenceReviewModal.test.tsx` 重写为壳行为测试(7 个):跳转 hash 含 /evidence-center + module=candidates、initial-queue 写入、target/task 参数透传、onClose 调用、无 items 不写 storage、open=false 无副作用、渲染为空
- `evidenceCenterUrl.test.ts`:新增 navigateToEvidenceCandidates 两个测试
- `EvidenceCenterPage.test.tsx`:新增五模块接线 it.each(按 module 切换渲染对应模块根节点 + 空态文案)
- `EvidenceCandidatesModule.test.tsx`:新增 initial-queue 一次性恢复测试(队列渲染 + storage 消费后清除)
- 原 24 个业务测试删除(由 T5-T9 模块测试承接);noNativeDialogs.test 仍通过(壳无原生弹窗)

## 验证

- `npx vitest run`:10 个文件 62 个测试全绿
- `npm run build`:通过(仅既有 chunk 体积 warning)
- `npx tsc --noEmit`:0 错误

## Concerns / 备注

1. **旧工作台草稿不迁移**:旧 Modal 的 `neurographiq.evidenceWorkbench.queue.v1`(localStorage)与新模块的 `evidence-center.review-draft.<targetId>`(sessionStorage)模型不同,旧 UI 进行中的草稿不会被新模块恢复。新流程以 URL task_id + 服务端 task items + sessionStorage 草稿为准。
2. **task items 条数**:旧 Modal 按 limit=200 加载批量任务,candidates 模块按 limit=100 —— 队列上限略降,不影响流程。
3. 恢复 effect 的顺序依赖已注释说明;若后续重构该模块需保持「恢复 effect 最后声明」。
4. 调用点中 MacroClinicalDataPanel 的文件原本有大量空行(历史遗留),本次仅做最小 diff,未顺手格式化。

## 相关文件

- frontend/src/pages/data-center/EvidenceReviewModal.tsx(+ 测试)
- frontend/src/pages/evidence-center/evidenceCenterUrl.ts(+ 测试)
- frontend/src/pages/evidence-center/EvidenceCenterPage.tsx(+ 测试)
- frontend/src/pages/evidence-center/modules/EvidenceCandidatesModule.tsx(+ 测试)
- frontend/src/pages/BackgroundTaskCenter.tsx
- frontend/src/pages/data-center/MirrorKgPanel.tsx
- frontend/src/pages/data-center/MacroClinicalDataPanel.tsx
- frontend/src/pages/evidence-center/components/candidatePassages.ts(仅注释更新)

## 复审修复(2026-08-10,Important 项)

**WorkbenchLayout 佐证工作台入口改为直接跳转** — commit `a57c446`

- `frontend/src/layout/WorkbenchLayout.tsx`:删除 `EvidenceReviewModal` import、`workbenchTaskId` state 与 Modal JSX 渲染;`onOpenEvidenceWorkbench` handler 改为 `navigateToEvidenceCandidates({ taskId })`(共享 helper,直接 hash 跳转 candidates 模块);同时移除不再使用的 `useState` import
- 至此全库不再有调用点渲染 `EvidenceReviewModal`(仅保留兼容壳文件 + 壳行为测试),TaskCenterDropdown 按钮/文案不变
- 验证:`npx vitest run` 10 文件 62 测试全绿(含 evidenceCenterUrl/壳/noNativeDialogs 覆盖);`npx tsc --noEmit` 0 错误
