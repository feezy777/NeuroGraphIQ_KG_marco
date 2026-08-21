# Evidence Center 前端勘察报告

> 勘察时间:2026-08-11 · 只读勘察,未修改任何文件
> 勘察范围:`frontend/src/`(Evidence Center 全链路)
> 结论前置:**tsc --noEmit 通过(EXIT 0)**;`frontend/dist`(2026-08-11 13:44 构建,晚于全部 src 修改 13:02–13:17)已包含 ClaimView 代码 → `ClaimView is not defined` 为 dev-server HMR 陈旧问题,非代码问题(详见 §8)。

---

## 1. 页面结构

### 1.1 `pages/evidence-center/` 完整文件树

```
pages/evidence-center/
├── EvidenceCenterPage.tsx         — 页面入口(Header + Body,三栏骨架)
├── EvidenceCenterContext.tsx      — Context Provider(URL 状态/队列/进度/各模块右栏推送状态)
├── EvidenceCenterHeader.tsx       — 顶部五模块导航胶囊(20 行)
├── EvidenceCenterPage.test.tsx    — 页面级测试(320 行)
├── evidenceCenterUrl.ts           — URL state(module/task_id/target_type/target_id/paper_id)解析与构建
├── evidenceCenterUrl.test.ts
├── components/                    — 21 个组件 + 7 个工具/类型文件(见 §4.2)
└── modules/                       — 5 个模块 + 各自 test(见 §5)
```

### 1.2 `EvidenceCenterPage.tsx` 结构(130 行)

```
EvidenceCenterPage (119-128)
└── EvidenceCenterProvider                    ← Context 包裹全页
    └── div.evidence-center (122)
        ├── EvidenceCenterHeader moduleTitles={MODULE_TITLE}   ← 五模块胶囊导航(123)
        └── EvidenceCenterBody (32-117)
            ├── ContextBar (63-75)             ← 对象/任务/进度信息条(14 props,见 §4.2)
            ├── StepPills module+progress (76) ← 五步流程胶囊
            ├── div.evidence-center-layout (77)
            │   ├── aside.evidence-left (78-100)   ← 左栏
            │   ├── main.evidence-main (101-108)   ← 中栏
            │   └── aside.evidence-right (109-113) ← 右栏
```

**左栏模块切换逻辑**(EvidenceCenterPage.tsx:78-100):
- `isPapers`(`state.module === 'papers'`)时整个三栏变单栏:`evidence-center-layout-full`,左/右栏 `display:none`,中栏 `max-width:1280px` 居中(77 行)
- `module === 'candidates'` → 左栏渲染 **ClaimView**(82-86 行,数据来自 `candidateClaim` context 推送)
- 其余模块(tasks/review/promotion)→ 左栏渲染 **ObjectQueue**(88-97 行);队列项点击 `openTarget(targetType, targetId, module)`,`review`/`promotion` 模块内切换留在当前模块,否则回 `candidates`(91-96 行)

**中栏**(101-108 行):顶部 `evidence-module-hint`(MODULE_HINT 常量,24-30 行)+ 按 `state.module` 条件渲染 5 个模块组件。

**右栏**(109-113 行):`RightPanel module={state.module}`(组件内部分支,见 §5.3)。

**URL 驱动**:所有状态由 `window.location.hash` 驱动(EvidenceCenterContext.tsx:62,79-83 行 hashchange 监听;apply() 84-92 行写回 URL),支持深链/刷新恢复。

---

## 2. 布局尺寸实测

### 2.1 系统布局(styles.css :root 1-41 行 + Layout 54-133 行)

| 变量 | 值 | 位置 |
|---|---|---|
| `--sidebar-w` | **220px** | styles.css:2 |
| `--topbar-h` | **52px** | styles.css:3 |
| `--log-console-height-collapsed` | 44px | styles.css:4 |
| `--log-console-height-expanded` | 320px | styles.css:5 |
| `--main-padding-y` | 22px(.main 垂直内边距,高度计算引用) | styles.css:31 |
| `.main` padding | `var(--main-padding-y) 24px` | styles.css:113-118 |
| `.layout` grid | `grid-template-rows: var(--topbar-h) 1fr; grid-template-columns: var(--sidebar-w) 1fr; height:100vh; overflow:hidden` | styles.css:55-61 |
| `.sidebar` | 深蓝 `#001529`,`height: calc(100vh - var(--topbar-h))`,sticky | styles.css:80-87 |
| `.main-data-center/.main-brain-3d` 特例 | overflow:hidden + padding 16px 20px + log-console 补偿 | styles.css:119-133 |

### 2.2 evidence-center 布局(styles.css:11392-11437)

```
.evidence-center            height: calc(100vh - var(--topbar-h) - var(--log-console-actual-height, 44px) - 2 * var(--main-padding-y));
                            即 100vh - 52 - 44 - 44 = 100vh - 140px;flex column;gap 12px (11392-11398)
.evidence-center-header     padding 8px 14px;白底卡片 (11399-11410)
.evidence-center-layout     flex:1;min-height:0;grid-template-columns: 230px minmax(620px, 1fr) 370px;gap 14px (11411-11417)
.evidence-center-layout-full grid-template-columns:1fr;左右栏隐藏;main max-width 1280px 居中 (11418-11422)
.evidence-left/.evidence-main/.evidence-right
                            白底、1px var(--border) 边框、radius var(--card-radius)、padding 12px 14px、
                            overflow-y:auto、min-height/min-width 0 (11424-11434)
.evidence-main              额外 flex column gap 12px (11435)
```

**实测合计**:三栏 = 左 230 + 中 minmax(620, 1fr) + 右 370 + 2×14 gap = 最小 1248px 视口才不横向压缩;整体可用高度 100vh-140px。

### 2.3 `App.tsx`(91 行)

- `WorkbenchLayout` 包 `Suspense` + `Page`(81-85 行);路由表 ROUTES 27-44 行,**`/evidence-center` → EvidenceCenterPage 为 Eager 静态导入**(App.tsx:19,34),仅 Brain3DPage lazy(25 行)
- LEGACY_REDIRECTS(47-54 行):raw-aal3/raw-macro96/candidates 等旧路径 → data-center
- hash 路由:`getPath()` 57-59 行 + hashchange 64-68 行

---

## 3. 主题 token(styles.css :root,1-41 行)

### 色板
| 组 | token |
|---|---|
| 主色 | `--primary #1677ff`、`--primary-hover #4096ff`、`--primary-active #0958d9` |
| 语义 | `--success #52c41a`、`--warning #faad14`、`--danger #ff4d4f` |
| 文字 | `--text #1d2129`、`--text-muted #86909c` |
| 底色 | `--bg #f2f3f5`、`--bg-soft #f8fafc`、`--white #ffffff`、`--muted-bg #f1f5f9` |
| 证据中心扩展 | `--selected-bg #eef6ff`、`--info-bg #eff6ff`、`--success-bg #dcfce7`/`--success-fg #15803d`、`--warning-bg #fef3c7`/`--warning-fg #b45309`、`--danger-bg #fff1f0` |
| 侧边栏 | `--sidebar-bg #001529`、`--sidebar-text rgba(255,255,255,.65)`、`--sidebar-active-bg rgba(22,119,255,.25)`、`--sidebar-active-text #4096ff` |

### 间距/圆角/阴影/字体
- 圆角:`--radius 6px`、`--radius-md 8px`、`--card-radius 10px`(21,24-25,29 行)
- 阴影:`--shadow 0 1px 2px rgba(0,0,0,.06)`、`--shadow-md 0 4px 12px rgba(0,0,0,.08)`、`--shadow-lg 0 8px 24px rgba(0,0,0,.12)`(23-25 行)
- 表格:`--table-stripe #fafbfc`、`--table-hover #e8f4ff`、`--table-selected #e6f4ff`(26-28 行)
- 字体:body `-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; 14px/1.5`(styles.css:44-50);`--font-mono` 无 :root 定义,全部走 `var(--font-mono, monospace)` 回退(styles.css:735 等 7 处)
- 第二处 `:root`(5970-5978 行):Governance Dashboard 专用 `--gov-*` 7 个色,与 Evidence Center 无关

---

## 4. 组件清单

### 4.1 `components/`(共享,22 项 + 3 子目录)

| 组件 | props 一句话 |
|---|---|
| ActionButton.tsx | `{ variant?, size?, loading?, disabled?, children, onClick }` 通用按钮封装 |
| BottomLogConsole.tsx | 底部日志控制台(无 props,读 WorkbenchLogContext) |
| CancelConfirmDialog.tsx | `{ task: BgTask; onClose }` 取消后台任务确认 |
| ConfirmDialog.tsx | `{ open, title, message?, children?, onConfirm, onCancel, confirmLabel?, danger?, loading? }` 通用确认弹窗(EvidenceDetailDrawer 使用) |
| CopyButton.tsx | `{ value, label?, title?, ariaLabel? }` 复制按钮 |
| DataTable.tsx | `DataTable<T>({ columns: Column<T>[], rows, ... })` 泛型表格(Column 含 render/key) |
| ForceGraph.tsx | 力导向图(图谱页用) |
| FormPanel.tsx | `{ title, defaultOpen?, children }` 可折叠表单面板 |
| GranularitySwitcher.tsx | 粒度切换器(无 props,读 useGlobalGranularity) |
| KeyValuePanel.tsx | `{ entries: KVEntry[] }` 键值展示面板 |
| ModelBadge.tsx | `{ provider, modelName }` 模型徽章 |
| Notice.tsx | `{ notice: NoticeState, onClose, autoDismissMs? }` 通知条 |
| PageHeader.tsx | `{ title, description?, actions?, readonly? }` 页头 |
| ResourceDestructiveDeleteModal.tsx | 资源破坏性删除确认 |
| SessionIdsPanel.tsx | 会话 ID 面板(无 props) |
| States.tsx | `LoadingState({text?})` / `ErrorState({error})` / `EmptyState({text?})` — 通用三态 |
| StatusBadge.tsx | `{ status: string }` 状态徽章 |
| TaskCenterDropdown.tsx | `{ onViewAll, onViewTask, onOpenEvidenceWorkbench }` 任务中心下拉 |
| TaskDetailModal.tsx | 任务详情模态(useTaskDetailModal hook) |
| brain-3d/ import-batches/ pipeline/ | 各自领域子组件目录 |

### 4.2 `evidence-center/components/`(21 组件 + 7 工具,props 一句话)

| 组件 | props 一句话 | 行数 |
|---|---|---|
| **ContextBar** | `{ targetLabel, targetType, granularity, confidence, evidenceCount, taskName, queueIndex, queueTotal, taskStatus, onBackToDataCenter, onRefresh }` 顶部信息条 | 64 |
| **StepPills** | `{ module, progress }` 五步流程胶囊(deriveStep 纯函数导出) | 41 |
| **ObjectQueue** | `{ queue, currentIndex, onSelect, showStats? }` 左/右栏队列(统计+只看未处理+状态徽章) | 85 |
| **RightPanel** | `{ module }` 右栏插槽:按 module 分发 TaskSummary/ObjectQueue/ReviewerDecisionPanel/PromotionImpact | 101 |
| **ClaimView** | `{ claimText, components, targetType }` 候选模块左栏事实卡(chips 可折叠) | 49 |
| **ClaimPanel** | `{ claimText, components, confidence, evidenceCount, targetType, granularity }` 中栏事实卡(review/promotion 用) | 34 |
| **CoveragePanel** | `{ coverage: CoverageSummary, direction }` Claim 覆盖情况面板 | 40 |
| **CandidateStatsBar** | `{ stats: CandidateStats, onEnterReview }` 中栏统计条(候选模块) | 78 |
| **PaperCard** | `{ paper: EvidencePaperItem, onOpen }` 论文库卡片 | 163 |
| **CandidatePaperCard**(同文件) | `{ paper: CandidatePaperData, selected, onToggleSelected, onOpenDetail, onExclude, onReExtract, onViewEvidence, reExtracting }` 候选模块分层论文卡 | 同 163 |
| **PaperDetailDrawer** | `{ paperId, onClose }` 论文详情右滑抽屉(摘要/分节段落/关联对象) | 177 |
| **PaperEvidenceView** | `{ paper, components, passages, selectedHashes, onTogglePassage, onBack }` 论文↔证据视图(readOnly PassageEvidenceCard 列表) | 102 |
| **PassageEvidenceCard** | `{ passage, components, selected, translation, onToggleSelect, onLevelChange, onComponentToggle, onTranslationChange, onTranslate, onCopy, onShowContext, showContext, onReselect?, readOnly? }` 证据片段卡(校验徽章/翻译/等级/组件勾选/重截取) | 146 |
| **ConfidencePreview** | `{ preview: AttachPreviewResponse }` 置信度预览(current→final+公式+cap+block_reasons) | 23 |
| **ReviewerDecisionPanel** | `{ direction, modelDirection, onDirectionChange, evidenceLevel, onEvidenceLevelChange, confidence, onConfidenceChange, note, onNoteChange, selectedCount, preview, previewBusy, coverage?, currentConfidence?, reviewStatus?, onApprove?, onReject? }` 人工审核右栏 | 185 |
| **PromotionDialog** | `{ open, targetLabel, claimText, paper, passages, components, direction, preview, busy, onConfirm, onClose }` 晋升确认弹窗 | 62 |
| **PromotionImpact** | `{ direction, currentConfidence, reviewerConfidence, preview?, previewBusy?, evidenceNewCount, passagesNewCount, statusLabel?, canPromote?, onReturnToReview?, onPromote? }` 晋升影响右栏 | 106 |
| **EvidenceDetailDrawer** | `{ open, evidence: PaperEvidenceItem, onClose, onRollback }` 已晋升证据详情抽屉(含回滚 ConfirmDialog) | 169 |
| **CreateBatchTaskDialog** | `{ open, granularity, onClose, onCreated, selectedIds? }` 创建批量预处理弹窗(scope 预览 300ms debounce) | 132 |
| **TaskSummary** | `{ data: TaskSummaryData, onStartReview, onCreateBatch, onRefresh }` 任务摘要右栏 | 121 |
| **TaskSummaryData/TaskSummaryActions** | 纯类型,经 Context 推送(同文件) | 同 121 |

工具/类型文件:`types.ts`(145 行,方向/等级/队列状态/组件标签全套)、`taskStatus.ts`、`ReviewStatusStore.ts`(68 行,localStorage 审核状态)、`candidatePassages.ts`、`claimCoverage.ts`(computeTmpCoverage/aggregateTmpDirection)、`confidenceImpact.ts`(clampConfidence/computeConfidenceImpact)。

> 注:任务清单里提到的 `SearchSection` 不存在 — 检索区 UI 内联在 `EvidenceCandidatesModule.tsx:566-681`。

---

## 5. 五模块现状

### 5.1 EvidenceTasksModule(208 行,中栏)
- **区块**:toolbar(标题+刷新/创建批量预处理)→ loading/error/empty → 6 个状态分组(STATUS_GROUPS 16-23 行:待处理/预处理中/待人工审核/已审核/已完成/失败)→ TaskRow 行组件(名称/统计/双 chip/操作)→ CreateBatchTaskDialog(200-205 行)
- **右栏**:选中任务 → `setTaskSummary` Context 推送(126-127 行)+ `setTaskSummaryActions`(131-137 行)→ RightPanel 渲染 TaskSummary
- **左栏**:ObjectQueue(页面级)

### 5.2 PaperLibraryModule(165 行,中栏)
- **区块**:toolbar → 搜索表单(标题/期刊/PMID/DOI + OA/年份/全文过滤,93-118 行)→ 卡片列表 PaperCard(20 页分页,138-158 行)→ PaperDetailDrawer(160-162 行)
- **左右栏**:`isPapers` 时三栏全隐藏,单栏全宽(EvidenceCenterPage.tsx:77)

### 5.3 EvidenceCandidatesModule(763 行,最重)
- **中栏结构**(520-761 行):message → 证据视图态(PaperEvidenceView + CandidateStatsBar,539-563 行)| 列表态:检索区(三层:查找论文/过滤/批量,596-681 行;有结果时折叠为单条摘要条 569-595 行)→ CandidateStatsBar(684-689 行)→ 候选论文列表(691-753 行,搜索未提取卡 + 任务已提取卡 + 手动提取卡)→ PaperDetailDrawer(757 行)
- **左栏**:ClaimView(经 `setCandidateClaim` Context 推送,227-238 行;卸载清空 240 行)
- **右栏**:ObjectQueue(RightPanel.tsx:51-62 行,queueIndex 独立计算 30-34 行)
- **数据流**:loadItems 141-161 行 → 队列同步 URL 188-194 行 → StepPills 进度推导 200-209 行 → DTO 220-224 行 → auto-draft 跨论文累计写 sessionStorage 464-496 行 → stats 推导 499-516 行;sessionStorage initial-queue 交接 268-295 行

### 5.4 EvidenceReviewModule(417 行)
- **中栏**:toolbar(返回候选/保存草稿,347-353 行)→ ClaimPanel(355-362 行)→ 当前论文(364-369 行)→ PassageEvidenceCard 列表(379-408 行,全编辑态)→ CoveragePanel(411-413 行)
- **右栏**:ReviewerDecisionPanel(经 `setReviewDecision` 推送 301-330 行;无目标时 RightPanel 显示占位 69-74 行)
- **左栏**:ObjectQueue
- 草稿双写:sessionStorage(`evidence-center.review-draft.` 前缀)500ms debounce 200-204 行 + 卸载同步 207-213 行;审核≠晋升:只写 ReviewStatusStore(279-288 行)

### 5.5 EvidencePromotionModule(516 行)
- **中栏**:三组列表 — 待晋升(pendingGroup 332-420 行,ReviewStatusStore review_approved 记录;选中后渲染 ClaimPanel+论文+CoveragePanel+Reviewer 决策卡 362-413 行)→ 已晋升(439-463 行,listPaperEvidence)→ 已失效(465-489 行)→ PromotionDialog(491-505 行)→ EvidenceDetailDrawer(507-512 行)
- **右栏**:PromotionImpact(经 `setPromotionImpact` 推送 306-327 行;无草稿时 RightPanel 占位 84-91 行)
- **左栏**:ObjectQueue;晋升成功推进 progress.promoted(244 行)+ queue 状态置 completed(246-248 行)+ 标记 task item 完成(250-259 行)

---

## 6. ClaimView 与 ClaimPanel 现状

| | ClaimView(components/ClaimView.tsx:12-49) | ClaimPanel(components/ClaimPanel.tsx:13-34) |
|---|---|---|
| props | `{ claimText, components, targetType }` | `{ claimText, components, confidence, evidenceCount, targetType, granularity }` |
| 容器 | `.evidence-claim`(左栏窄卡) | `.ew-section.ew-claim-panel`(中栏宽卡) |
| chips | `.evidence-claim-chip` 横向 flex-wrap,**可折叠**(`chipsCollapsed` state + btn.btn-xs toggle,19-28 行;隐藏后仅显示 claim 单行) | `.ew-component-chip` 纵向列表(必选/辅助上下文 em 标记,24-30 行),不可折叠 |
| 附加信息 | 仅 targetType 徽章 | 置信度 + 已有论文证据数 meta 行(18-22 行) |
| 使用方 | 仅 EvidenceCenterPage.tsx:82(候选模块左栏) | EvidenceReviewModule.tsx:355 + EvidencePromotionModule.tsx:364(中栏) |

两组件同源(COMPONENT_LABEL 共享),但视觉体系分属 `evidence-*` 与 `ew-*` 两套命名。

---

## 7. 关键样式现状(`.evidence-center-*` 主要类,styles.css 11390-12339)

- **三栏骨架**:`.evidence-center`(11392)/`-header`(11399)/`-layout`(11411,230/620+/370)/`-layout-full`(11418)/`.evidence-left,.main,.right`(11424)/`.evidence-module-hint`(11437)
- **导航**:`.evidence-module-nav`(11440)/`-btn`(11441,胶囊,active 实底主色+阴影 11454-11460)
- **ContextBar**:`.evidence-context-bar`(11463)/`-object`(11474)/`-chip`(11476)/`-task`(11486)/`-progress`(11487,左边线分隔)/`-actions`(11495)
- **Stepper**:`.evidence-step-pills`(11498)/`-pill`(11499)/`-num`(11511)/`.done`(11523)/`.active`(11525,实底主色)
- **队列**:`.evidence-queue`(11529)/`-head/-title/-count/-stats/-filter/-list/-item(11537,active 左侧强调条 11549)/-status-{info,warn,ok,bad,muted}(11563-11567)/-empty(11569)/-item-hint(11573)`
- **Claim**:`.evidence-claim`(11573)/`-head`(11583)/`-text`(11586)/`-chips`(11596)/`-chip`(11597,optional 变体 11610);左栏缩排版 11613-11618
- **任务模块**:`.evidence-task-module/-toolbar/-groups/-group(11626,标题前色条 11635)/-row(11646)/-chip-{ok,bad,warn,info,muted}(11682-11686)/-loading/-error/-empty(11690,虚线空态卡)`
- **任务摘要/统计**:`.evidence-task-summary`(11701)/`.evidence-progress-bar`(11706,分段色条 ok/warn/bad 11714-11717)/`.evidence-summary-stats`(11722)/`-stat`(11728)/`.evidence-section-divider`(11741)
- **论文模块**:`.paper-module/-toolbar/-search-bar(11747)/-card(11770)/-badge-{oa,avail,muted}(11793-11795)/-pagination/-empty(11800)`
- **候选模块**:`.evidence-candidates`(11811)/`-main`(11812)/`-papers`(11813)/`-empty`(11816,虚线空态)/`.evidence-search`(11827)/`-collapsed`(11859 折叠条)/`.evidence-stats-bar`(11889)/`-stats-item/-label/-value/-model/-direction/-actions`(11900-11914)
- **证据视图**:`.evidence-paper-view/-back/-summary/-coverage(11976)/-coverage-table(11987)/-passages(12001)`
- **审核模块**:`.evidence-review`(12005)/`-toolbar`(12007)/`-paper`(12009)
- **晋升模块**:`.evidence-promotion`(12104)/`-group`(12105)/`-card`(12135)/`-paper`(12144)/`-decision`(12155)/`-row`(12183)/`-row-invalidated`(12197)/`-empty`(12207)/`-impact`(12220)/`-row-selected`(12216)
- **详情抽屉**:`.evidence-detail-*`(12238-12292)/`.evidence-drawer-overlay`(12295)/`.evidence-drawer`(12305,右侧滑出)/`-head/-title/-close/-body`(12315-12339)
- **`ew-*` 体系**(11307-11381 等):`.ew-meta/-ok/-bad/-warn`(11307,11316-11318 语义色)/`.ew-section`(11310)/`.ew-field`(11312)/`.ew-preview`(11314)/`.ew-passage`(11322)/`-en/-zh/-context`(11338-11342)/`.ew-claim-panel`(11347)/`.ew-component-chip`(11361)/`.ew-coverage-*`(11378-11381)/`.ew-ai-section`(12028)/`.ew-divider`(12048)/`.ew-impact-grid`(12059)/`.ew-dir-chip`(12085)/`.ew-sticky-actions`(12073)/`.ew-promo-field`(12222)
- **空态**:无统一 Empty 组件 — `.evidence-task-empty`(11690)/`.evidence-candidates-empty`(11816)/`.evidence-promotion-empty`(12207)/`.evidence-queue-empty`(11569)/`.paper-empty`(11800)五处各自复刻「虚线边框白卡」样式(均 padding 20-40px、虚线 border、text-muted 居中);共享组件目录有 `States.tsx: EmptyState` 但 evidence-center 未使用

---

## 8. ClaimView is not defined 线索(结论:运行时 HMR 陈旧,代码/构建均正常)

**证据链:**

1. **编译期正常**:`npx tsc --noEmit` 通过(EXIT 0)
2. **文件存在且导出正确**:`components/ClaimView.tsx:12` `export function ClaimView({ claimText, components, targetType }: Props)`,49 行,仅依赖 `./types`(无循环依赖)
3. **静态 Eager 导入**:EvidenceCenterPage.tsx:5 `import { ClaimView } from './components/ClaimView'`,使用点 82 行;App.tsx:19 Eager 导入 EvidenceCenterPage(全站仅 Brain3DPage lazy,App.tsx:25)→ 无懒加载/条件加载路径
4. **产物正确**:`frontend/dist` 构建于 2026-08-11 13:44(晚于全部 src 修改:ClaimView.tsx 13:02、EvidenceCenterPage.tsx 13:17);dist 主包 `index-BZEycL_m.js` 含 `evidence-claim`、`当前需要验证的事实`、`收起组件`、`candidateClaim` 全部字符串 → ClaimView 代码完整打进产物
5. **git 干净**:evidence-center 目录无未提交修改;ClaimView.tsx 由提交 `02a9e96 feat(evidence-center): 证据候选三栏重构` 引入(ClaimPanel 由更早的 `498d59e` 迁移引入)— 即 ClaimView 是「新 import + 新导出」的跨提交改动
6. **测试正常**:EvidenceCenterPage.test.tsx:259 页面级测试断言「candidates 左栏渲染 ClaimView」且不 mock 该组件(仅 mock `../../api/endpoints` 6-20 行)

**判定**:Vite dev 模式下,浏览器标签页持有的是三栏重构(02a9e96)之前的陈旧模块图 — 旧版 EvidenceCenterPage 模块(或其依赖图中该 import 位置的绑定)引用了重构后才诞生的 `ClaimView` 导出,模块图失效后未触发完整页面刷新,运行时出现 ReferenceError。此现象典型触发场景:git checkout 大改(而非编辑器单文件保存)时 Vite watcher 传播不全,或长时间挂起的标签页。**修复手段**:硬刷新(清缓存)/重启 `npm run dev`,与代码无关。生产 dist 已验证无此问题。

---

## 9. 通用组件体系(现成可复用)

### 按钮
- `.btn`(styles.css:204-218,高 32px 白底边框)+ 变体 `.btn-primary`(10175)/`.btn-danger`(776,10177)/`.btn-text`(9485)/`.btn-sm`(28px,10179)/`.btn-xs`(24px,10180)/`:disabled`(10181)

### 表单
- `.filter-input`/`.filter-select`(188-200,evidence-center 主力)+ `.form-input`/`.form-select`/`.form-textarea`(376-388)+ `.filter-label`(201)/`.form-label/.form-hint/.form-error`(375,388-389)+ `.form-row/.form-field`(373-374)

### 卡片/面板
- `.card`(141)/`.card-title`(142)/`.ontology-card*`(11144-11153,ont 中心体系:header/title/sub/grid/item/label/value/pct)+ `.ontology-modal-overlay/-modal/-header/-body/-actions`(PromotionDialog/CreateBatchTaskDialog 复用)+ `.ontology-detail-row`(行式键值,PromotionDialog 使用)+ `.ontology-page-message`(11193,evidence-center 复用为 message 条)+ `.ontology-empty`(11194)

### 表格
- 原生 `table` 体系(222-226:thead sticky、th #f7f8fa)+ `.table-wrap`(222)+ 共享 DataTable.tsx(泛型列渲染)

### 状态/徽章/空态
- `.status-badge` 相关(StatusBadge.tsx)+ `.evidence-task-chip-*`/`.evidence-queue-status-*`/`.evidence-context-chip`/`.paper-badge-*` 语义色胶囊体系
- 共享 States.tsx(LoadingState/ErrorState/EmptyState)存在但 evidence-center 未接入;空态均为各文件本地 `.evidence-*-empty` 虚线卡

### 弹窗/抽屉
- 共享 ConfirmDialog.tsx(open/title/message/children/confirmLabel/danger/loading)
- 本地 `.evidence-drawer-overlay` + `.evidence-drawer`(12305 起,右侧滑出 宽 480px 级别)两处抽屉(PaperDetailDrawer/EvidenceDetailDrawer)+ `.ontology-modal-overlay` 弹窗(PromotionDialog/CreateBatchTaskDialog)
