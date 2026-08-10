# Task S2 Report: 证据候选三栏重构 + 论文证据视图分离

**Status:** DONE — 104/104 tests pass, `npm run build` green.

## What Was Done

### 1. 左队列移除
- `EvidenceCandidatesModule.tsx` 不再渲染自己的左队列（`candidates-queue` 删除），队列由页面级 `<ObjectQueue>`（EvidenceCenterPage 左栏）渲染 — 模块只渲染中栏内容。
- 模块内 `ITEM_STATUS_LABEL` / `PREPROCESS_HINTS` 等队列专用代码删除。

### 2. Claim 区重排 — 新建 `components/ClaimView.tsx`
- 「当前需要验证的事实」+ Claim 单行突出（左强调条）+ Component Chips（`COMPONENT_LABEL` 标签 + statement 值，紧凑排布，optional chip 弱化）。
- 候选模块改用它；`ClaimPanel` 保留给 Review/Promotion 模块。

### 3. 搜索区三层（保留现逻辑，重排视觉 + section 标题）
- 第一层「查找相关论文」:Query 输入 + [重新搜索] + [恢复系统推荐] + Query Terms Chips（来自 DTO source/target/relation/function_context）。
- 第二层「检索过滤」:仅 OA（客户端过滤 is_open_access）/ 佐证模式（auto/existence/function，透传 search+extract）/ 年份（客户端过滤）/ [恢复排除]。
- 第三层「批量操作」:[全选] + [提取所选论文(N)]。
- 搜索入口仍按原逻辑仅任务为空（manualTarget）时出现。

### 4. PaperCard 信息分层 — `components/PaperCard.tsx` 新增 `CandidatePaperCard`
- 第一行标题粗体 / 第二行 作者·Journal·Year / 第三行匹配信息（matchScore% + matchReason，仅搜索结果显示）/ 第四行标签（PMID/DOI/摘要/OA 全文）/ 操作行（[查看详情]→PaperDetailDrawer / [加入提取] checkbox（仅未提取搜索结果）/ [排除此候选] / 提取后：AI 判断 + 覆盖度 + 片段 N + 已核验 N + [查看证据候选] + [重新提取]）。
- 原论文库 `PaperCard` 保留不动（PaperLibraryModule 不受影响）。

### 5. 论文↔证据视图分离 — 新建 `components/PaperEvidenceView.tsx`
- 顶部 `← 返回论文列表`；Paper Summary（标题/期刊/PMID/DOI）；Claim Coverage 组件表（每个 claim_component 一行 ✓/○，右下角 Coverage N/M，基于 computeTmpCoverage 只计已核验片段）；候选佐证原文 = PassageEvidenceCard 列表（readOnly 模式复用）。
- `PassageEvidenceCard` 新增 `readOnly` prop（隐藏翻译/证据等级/组件勾选编辑控件），并在 readOnly 顶部行加「详细信息」折叠按钮；details 内展示 paragraph_id/paragraph_index/source_locator/校验方式。

### 6. 右栏 CandidateSummary — 新建 `components/CandidateSummary.tsx`
- 当前 Claim / 找到论文 N / AI 提取论文 N / 已核验片段 N / Coverage / 模型判断 / [进入人工审核]（openTarget review）。
- **禁止项**：无 Reviewer Confidence/Direction 输入、无 attach 控件。
- 接入方式：EvidenceCenterContext 增加 `candidateSummary` + `setCandidateSummary`（模块计算后推送，卸载时清空）；`RightPanel` 在 candidates 模块渲染 `<CandidateSummary>`（最小改动，其余模块仍占位标题）。
- 草稿链路：PaperEvidenceView 中勾选已核验片段 → 模块自动写入 `evidence-center.review-draft.<targetId>`（与旧格式一致），右栏 [进入人工审核] 仅导航，Review 模块照常恢复草稿。

### 7. granularity 兑现
- `QueueEntry` 增加可选 `granularity?: string | null`；模块 DTO 加载后按 target 填充队列条目（带引用相等 guard 防循环）；`EvidenceCenterPage` 将 `current?.granularity` 传给 ContextBar。
- 注：brief 说 itemToQueueEntry 时填充，但 `PaperEvidenceTaskItem` 无 granularity 字段，实际从 `getEvidenceTarget` DTO 填充（等效结果，测试覆盖）。

### 8. styles.css
- 新增 `.evidence-claim-*`、`.evidence-search-*`（三层）、`.paper-card-*` 分层、`.evidence-paper-view`、`.evidence-candidate-summary` 样式（192 行，仅本次改动）。

## Tests (TDD: RED → GREEN)
- 新建 `PaperEvidenceView.test.tsx`（7 用例）：返回按钮、Paper Summary、Coverage 表 ✓/○ + N/M、readOnly 复用（无编辑控件）、checkbox 禁用逻辑、reason/semantic confidence 低层级、详细信息折叠。
- 新建 `CandidateSummary.test.tsx`（5 用例）：统计渲染、空态、进入人工审核回调、禁止 Reviewer/attach 控件。
- 扩展 `EvidenceCandidatesModule.test.tsx`（14 用例）：左队列不再自渲染、Claim chips、PaperCard 分层、证据视图切换+返回、勾选自动写草稿、排除、重新提取、搜索三层+Query Terms、重新搜索 query_override、恢复系统推荐、批量全选+提取、OA/年份过滤、initial-queue 恢复消息。
- 扩展 `EvidenceCenterPage.test.tsx`（17 用例）：右栏 candidates 渲染 CandidateSummary + 进入人工审核跳转、右栏无 Reviewer 控件、granularity 显示在 ContextBar、initial-queue 条目渲染页面级左栏。
- 结果：evidence-center 90/90，全量 104/104，`npm run build` 通过。

## 期间修复的 Bug
- 候选模块 `claimComponents = dto?.claim_components ?? []` 每次渲染新引用 → summary useMemo → setCandidateSummary → context 更新 → 重渲染 → 无限循环（vitest 挂起）。已 useMemo 稳定化。
- Context `setQueue` 是普通函数（非 Dispatch updater），granularity effect 改用「先 map 再比对引用、有变更才 setQueue」。

## Files Changed
- M `frontend/src/pages/evidence-center/modules/EvidenceCandidatesModule.tsx`（大改）
- M `frontend/src/pages/evidence-center/components/PaperCard.tsx`（新增 CandidatePaperCard）
- M `frontend/src/pages/evidence-center/components/PassageEvidenceCard.tsx`（readOnly + 详细信息折叠）
- M `frontend/src/pages/evidence-center/components/RightPanel.tsx`（candidates → CandidateSummary）
- M `frontend/src/pages/evidence-center/components/types.ts`（QueueEntry.granularity）
- M `frontend/src/pages/evidence-center/EvidenceCenterContext.tsx`（candidateSummary）
- M `frontend/src/pages/evidence-center/EvidenceCenterPage.tsx`（ContextBar granularity）
- A `frontend/src/pages/evidence-center/components/ClaimView.tsx`
- A `frontend/src/pages/evidence-center/components/CandidateSummary.tsx`
- A `frontend/src/pages/evidence-center/components/PaperEvidenceView.tsx`
- A `frontend/src/pages/evidence-center/components/CandidateSummary.test.tsx`
- A `frontend/src/pages/evidence-center/components/PaperEvidenceView.test.tsx`
- M `frontend/src/pages/evidence-center/modules/EvidenceCandidatesModule.test.tsx`
- M `frontend/src/pages/evidence-center/EvidenceCenterPage.test.tsx`
- M `frontend/src/styles.css`

## Commit
`feat(evidence-center): 证据候选三栏重构 + 论文证据视图分离`
