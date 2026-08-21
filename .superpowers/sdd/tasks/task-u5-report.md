# Task U5 报告:样式 token 收敛 + 空态统一 + 字体层级

> 提交:`d067a97 style(evidence-center): token 收敛与空态统一`(分支 codex/ontology-evidence)
> 范围:`frontend/src/styles.css` + evidence-center 10 个组件/测试;后端与功能逻辑零改动

---

## 1. Token 收敛(styles.css :root)

| 项 | 处理 |
|---|---|
| `--font-mono` 缺失 | 补 `--font-mono: 'Consolas', 'Menlo', 'Courier New', monospace`;全文件 12 处 `var(--font-mono, monospace)` 回退收敛为 `var(--font-mono)`;`code` 元素同步改用 token |
| `--selected-bg #eef6ff` vs `--info-bg #eff6ff` | 近同(仅 1 个 hex 位差)已合并:删除 `--selected-bg`,4 处使用(evidence-context-badge / evidence-queue-item-active / evidence-task-row-selected / evidence-promotion-row-selected)改为 `var(--info-bg)` |
| 进度条硬编码色 | `.evidence-progress-{ok,warn,bad}` 的 `#34c77b/#f2b13b/#f2685f` 收敛为 `--success/--warning/--danger` |
| 间距节奏 8/12/16/20 | evidence 区离调值收敛:gap 14→12(任务分组、任务统计)与 14→16(paper-card);gap 18→16(stats-bar);卡片 padding `12px 14px`→`12px 16px`(三栏、任务组、检索区、论文摘要/覆盖、晋升组、抽屉 meta);`10px 14px`→`12px 16px`(ContextBar、候选论文卡);抽屉头 `14px 18px`→`16px 20px`、抽屉体 `16px 18px 24px`→`16px 20px 24px`;队列项左内边距 14→12 |
| 细粒度间距 | chips/badges/行内 padding(6-10px)保留紧凑档(行/徽章/字段属内联级,不适用区块节奏)——已在下方"取舍说明"记录 |
| 按钮高度 | `.btn` 32px ✓、模块导航 34px ✓(均在 32-36 区间);`.btn-sm` 28 / `.btn-xs` 24 保留为紧凑档(全站共用,不在本任务范围) |
| Input/Select 高度 | `.filter-input/.filter-select` 32px 与 `.form-input` 32px 已一致;evidence 区检索框/下拉全部走 `filter-input/filter-select`(PaperSearchPanel、PaperSearchFilters、CreateBatchTaskDialog、EvidenceDetailDrawer),无需改动 |

## 2. 字体层级

- evidence 区实测已符合视觉稿层级:模块标题 15(任务/论文库/审核 toolbar h3、候选论文头 h4、论文标题、抽屉标题)、正文 13-14(claim、行内 strong、段落)、辅助 12/11(meta、hint、徽章)。
- 收敛 1 处越级:`dc-evidence-stat strong` 18px→16px(与 `evidence-stats-value`、`evidence-summary-stat dd` 的 16px 展示数字档对齐,消除"大量 18px+")。
- `evidence-summary-stat dd` / `evidence-stats-value` 16px 为数字展示档,保留。

## 3. 空态统一(5+1 处复刻 → EmptyState 组件)

`EmptyState`(U3 建立)新增 props:`compact`(紧凑变体)、`testId`、`actionTestId`(保持既有测试锚点,默认 `evidence-empty` 不变)。

替换清单(全部删除各自复刻的虚线卡 div):

| 位置 | 原类 | 现 | 形态 |
|---|---|---|---|
| EvidenceTasksModule | `.evidence-task-empty` | EmptyState(Inbox 图标) | 全量 |
| PaperLibraryModule | `.paper-empty` | EmptyState(FileSearch 图标) | 全量 |
| EvidenceCandidatesModule(无目标) | `.evidence-candidates-empty` | EmptyState(MousePointerClick) | 全量 |
| EvidenceReviewModule(无目标) | `.evidence-candidates-empty` | EmptyState(MousePointerClick) | 全量 |
| EvidenceReviewModule(无草稿片段) | `.evidence-candidates-empty` | EmptyState compact | 内联 |
| EvidencePromotionModule(无目标) | `.evidence-promotion-empty` | EmptyState(MousePointerClick) | 全量 |
| EvidencePromotionModule(待晋升/无草稿/已晋升/已失效 4 处) | `.evidence-promotion-empty` | EmptyState compact | 内联 |
| PaperEvidenceView(无候选片段) | `.evidence-candidates-empty` | EmptyState compact | 内联 |
| ObjectQueue(左栏队列) | `.evidence-queue-empty` | EmptyState compact | 内联 |
| EvidenceQueuePanel(右栏队列) | `.evidence-queue-panel-empty*`(📥 自绘) | EmptyState(Inbox 图标 + 查看全部对象按钮) | 全量 |

- 新增 CSS 变体 `.evidence-empty-compact`(padding 14px 12px、透明底、32px 图标、13px 标题)用于窄栏/组内内联场景;`.evidence-queue-panel .evidence-empty { margin-top: auto }` 保留右栏空态吸底语义。
- 删除死类 CSS:`.evidence-task-empty`、`.paper-empty`、`.evidence-candidates-empty`、`.evidence-promotion-empty`、`.evidence-queue-empty`、`.evidence-queue-panel-empty*`、`.evidence-queue-panel-view-all`。
- 保留 `.evidence-module-hint`(EvidenceTasksModule:157 仍使用)与 `.evidence-candidates-hint`(PaperCandidateList 仍使用)。

## 4. 清理

- 删除旧版重复 `.btn` 块(styles.css:204-219,被 10157 行「Button system」逐属性完全覆盖的死类)。
- 合并重复规则:`.evidence-task-loading` + `.paper-loading`(完全相同)→ 组选择器;`.evidence-task-error` + `.paper-error` → 组选择器。
- 死类扫描(evidence 区 150+ 类 × tsx 引用):`evidence-claim-text/-chips/-chip` 已在上轮删除(当前无定义无引用);`evidence-queue-status-*`/`evidence-task-chip-*` 为模板字符串动态使用,保留。
- 勘察报告 §2.2 的 `.evidence-center-layout` gap 14px 已在上轮收敛为 12px(勘察快照滞后),本轮无需处理。

## 5. 测试与构建

- `npx vitest run`:27 文件 / 238 测试全过(evidence-center 224 项在内)
- `npx tsc --noEmit`:EXIT 0
- `npm run build`:通过(500kB chunk 警告为既有问题,与本轮无关)
- 测试适配 1 处:EvidenceQueuePanel.test 的 `.evidence-queue-panel-empty-icon` 断言改为 `.evidence-empty-icon svg`(组件已统一为 lucide Inbox,行为断言不变)

## 6. 取舍说明(有意保留项)

- `.btn-sm` 28px / `.btn-xs` 24px:全站共用紧凑档,非 evidence 区专属,本轮不动(主按钮 32px 已达标)。
- 行内级间距(6-10px:徽章/行/chips/字段)保留紧凑档,不做 8/12 化——节奏统一面向区块级间距。
- `.evidence-empty-title` 14px / compact 13px:空态属状态提示而非模块标题,保持在正文-辅助区间。
- 证据区外(其它页面 60+ 处 `12px 14px`)不在本轮范围,未触碰。

## 7. 风险与后续

- 无功能逻辑改动;所有类名替换均为纯视觉,测试全绿。
- 后续若需全站统一(非 evidence 区的 14px/18px),建议单独一轮全局 token 迁移。

## 8. U5 复审修复(2026-08-11)

### 修复项:进度条三色恢复(commit f8da35f)

- **发现**:`.evidence-progress-{ok,warn,bad}` 在 d067a97(token 收敛)被从自定义柔和色 `#34c77b/#f2b13b/#f2685f` 换成 Ant Design 鲜艳 token(`--success #52c41a / --warning #faad14 / --danger #ff4d4f`),绿/红视觉差异明显,brief 未要求此改动。
- **修复**:在 `:root` 新增命名 token `--progress-ok: #34c77b; --progress-warn: #f2b13b; --progress-bad: #f2685f`(带设计稿注释),样式改为引用 token——既恢复原设计意图,又保持 token 化。
- **验证**:`npx vitest run` 27 文件 / 238 测试全过;`npx tsc --noEmit` EXIT 0;`npm run build` 通过。类名仅用于 `TaskSummary.tsx`(不持色),无其它引用。
