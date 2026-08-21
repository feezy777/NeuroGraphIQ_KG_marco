# Task U3 Report: 中栏搜索面板组件化拆分

> 状态:✅ 完成 · 提交 `4fbaf06`(分支 codex/ontology-evidence)
> 全量验证:vitest 228/228 通过(27 文件)、`npx tsc --noEmit` EXIT 0、`npm run build` 通过

## 交付内容

### 新建 7 个组件(`frontend/src/pages/evidence-center/components/`)

| 组件 | 规格落地 |
|---|---|
| `EmptyState.tsx` | props `{ icon?, title, description?, actionLabel?, onAction? }`;统一虚线白卡空态(图标圆底 + 标题 + 说明 + 按钮) |
| `PaperSearchPanel.tsx` | 「查找相关论文」+ 大搜索框(推荐 placeholder)+ [重新搜索][恢复系统推荐] 同行;Query Chips 浅蓝圆角 + ×清空(可换行);**保留折叠行为**——`collapsed` 时渲染折叠条(Query 摘要 + 重新搜索/展开检索/提取所选论文(N)),filters/batchActions 为插槽仅展开态渲染 |
| `PaperSearchFilters.tsx` | 「检索过滤」+ ☐仅OA / 证据模式[自动▼] / 年份[2020▼ 下拉] / [恢复默认](重置仅OA/模式/年份)+ [恢复排除](无排除时禁用);导出 `EvidenceMode` 类型 |
| `PaperBatchActions.tsx` | 「批量操作」+ ☐全选(可勾回取消)+ [提取所选论文(N)](N=0 禁用)+ [收起检索](有结果时) |
| `PaperStatusSummary.tsx` | 浅蓝状态条(min-height 48px):找到论文 / AI提取 / 已核验 / Coverage N/M / 模型判断(加粗)+ 右侧 [进入人工审核](零勾选禁用);**替换并删除 CandidateStatsBar.tsx**(git 识别为 rename,全部 testid 保留,页面级测试零改动) |
| `PaperCandidateList.tsx` | 「候选论文(N)」+ 空态用 EmptyState(文档+放大镜 FileSearch 图标 / 暂无候选论文 / 说明 / [调整检索条件])+ 底部轻提示「勾选论文后可批量操作;被排除的论文可通过「恢复排除」找回。」;有排除时列表头出现 [恢复排除(N)];非手动检索场景显示任务候选文案(无按钮) |
| `PaperCandidateCard.tsx` | 四行层级:①标题粗体 ②作者·Journal·Year ③匹配度/理由 ④PMID·DOI·摘要·OA 徽章;底部操作行:☐加入提取 / [查看详情] / [排除此候选];提取后结果行改视觉稿规格:**AI判断：X / Coverage N/M(coverage_summary supported/required)/ 已核验片段 N**(独立行,不挤操作行)+ [查看证据候选] + [重新提取] |

### 接线与保留逻辑

- `EvidenceCandidatesModule.tsx` 中栏(原 566-753 行内联检索区/统计条/候选列表)替换为上述组件组合;全部 state/逻辑保留:searchQuery/manualResults/candidates/selectedHashes/折叠状态/提取/排除/证据视图切换/auto-draft/统计推导/StepPills 推进。
- 新增 `clearedTerms` state 支持 Chip × 清空(仅展示层);恢复系统推荐与切换目标时重置。
- `PaperCard.tsx` 移出 CandidatePaperCard/CandidatePaperData(仅保留论文库 PaperCard,该模块测试不受影响)。
- 行为增强(不改变功能逻辑):全选由"只选不全清"按钮改为可回勾的 checkbox;年份由文本输入改为下拉(不限/2018-2026)。

### 样式(`styles.css`)

- `.evidence-query-term` 浅蓝 Chip + `.evidence-query-term-clear` 圆形 × 按钮
- `.evidence-stats-bar` 浅蓝底(remove 白底阴影)+ min-height 48px;`.evidence-stats-assessment` 加粗;direction chip 白底描边
- 新增 `.evidence-empty*`(统一空态)、`.evidence-candidates-hint`(轻提示)、`.paper-card-result-badge-ai`
- `.evidence-candidates-papers-head` 对齐改 center(容纳恢复按钮);年份下拉宽度 118px

## 测试

- 7 个新组件测试文件,39 例:展开/折叠态渲染、chips 清空、busy 禁用、全选勾回、N=0 禁用、空态(两场景)、卡四行层级、结果行格式、恢复排除禁用/启用等
- `EvidenceCandidatesModule.test.tsx` 更新(佐证模式→证据模式、年份 select、AI判断/Coverage/已核验片段文案、☐全选 checkbox)+ 新增 3 条链路:chip ×清空→恢复系统推荐、[恢复默认]重置过滤、空态(暂无候选论文/调整检索条件/轻提示/恢复排除找回)
- 全量回归:**228 通过(27 文件)**,含 EvidenceCenterPage.test(页面级 stats-bar/进入人工审核链路零改动通过)

## 说明 / 关注点

1. 「恢复排除」保留在过滤行(原逻辑,无排除时禁用)而非删除——视觉稿的 [恢复默认] 与空态提示中的「恢复排除」功能不同,两者并存:恢复默认=重置过滤条件;恢复排除=找回被排除论文。
2. 年份控件从文本输入改为下拉(视觉稿 [如2020▼]);过滤语义不变(年份下限)。
3. 卡片结果行按视觉稿删除了「片段 N」徽章(信息仍在证据视图可见)。
4. 后端零改动;仅 git add 本任务相关 18 个文件。

## U3-Fix(2026-08-11): 删除 PaperSearchPanel 未使用 onCollapse prop(commit 5f3818f)

- 发现:`PaperSearchPanel.tsx` 声明并解构 `onCollapse` 但组件体从不使用;`EvidenceCandidatesModule.tsx`(约 606 行)仍传 `onCollapse={() => setSearchExpanded(false)}`。
- 修复:
  1. `PaperSearchPanel.tsx` — 删除 `onCollapse` 类型声明与解构(共 2 行)。
  2. `EvidenceCandidatesModule.tsx` — 删除传给 `PaperSearchPanel` 的 `onCollapse` 传参(仅 606 行那一处;635 行为 `PaperBatchActions` 的 `onCollapse`,该组件体内真实使用,保留)。
  3. `PaperSearchPanel.test.tsx` — 同步删除默认 props 中的 `onCollapse: vi.fn()`(无相关断言)。
- 验证:
  - `npx vitest run src/pages/evidence-center/` → 24 files / 214 tests 全绿
  - `npx vitest run`(全量)→ 27 files / 228 tests 全绿
  - `npx tsc --noEmit` → 0 错误
