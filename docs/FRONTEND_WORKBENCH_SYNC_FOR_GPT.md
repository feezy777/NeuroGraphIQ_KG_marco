# NeuroGraphIQ Workbench — 前端架构与页面功能同步说明 (2026-08-25)

> 给 GPT 的工作台前端上下文同步文档。基于当前代码库实际状态生成，可直接作为继续开发前端的输入。
>
> **运行环境**：
> - Frontend dev: http://localhost:5173 (Vite, 运行中)
> - Backend API: http://127.0.0.1:8002 (FastAPI, 运行中) — Vite 通过 `/api` 代理转发到 8002
> - 版本号: v3.2.9-mvp1 (顶栏显示)

---

## 1. 技术栈

| 项 | 值 |
|----|----|
| 框架 | React 18.3 + TypeScript 5.6 |
| 构建 | Vite 6 (`npm run dev` / `npm run build` = `tsc -b && vite build`) |
| 路由 | **手写 hash 路由**（无 react-router）— `App.tsx` 的 `ROUTES` 表 + `location.hash` 监听 |
| 状态 | React Context + 自定义 hooks；**无** redux/zustand/react-query |
| 数据获取 | 手写 fetch 封装 `src/api/client.ts`（getJson/postJson/putJson/patchJson/deleteJson/uploadForm）+ `useData` hook |
| 轮询 | `useBackgroundTasks` hook（任务中心统一轮询，3s/15s 动态间隔，visibility 感知） |
| 样式 | 全局单文件 `src/styles.css`（CSS 变量设计令牌），无 Tailwind / CSS Modules |
| 图标 | lucide-react |
| 图可视化 | d3 (ForceGraph, 力导向图)、@xyflow/react (GraphExplorer, React Flow 12)、@dagrejs/dagre (树布局)、three.js (Brain3D) |
| 国际化 | 自研 i18n：`src/i18n.ts`（zh-CN / en-US 双语 key 表，5000+ 行）, `I18nProvider` + `useI18n().t(key)` |
| 测试 | Vitest + Testing Library、Playwright (e2e) |
| 文件大小 | 374 个 src 文件；`api/endpoints.ts` 6553 行（API 全封装）、`styles.css` 14612 行、`i18n.ts` 5067 行 |

---

## 2. 目录结构

```
frontend/src/
├── main.tsx                  # 入口，挂 <App/> 于 #root，引 styles.css
├── App.tsx                   # Hash 路由注册表 + 4 层 Provider 嵌套 + 旧路由重定向
├── styles.css                # 全局设计系统（CSS 变量令牌，见 §6）
├── i18n.ts / i18n-context.tsx / i18n-context-core.ts   # 自研 i18n
├── api/
│   ├── client.ts             # fetch 封装: getJson/postJson/putJson/patchJson/deleteJson/uploadForm + ApiError + 错误日志桥接
│   ├── endpoints.ts          # ★全部 API 函数的唯一封装点（6553 行，含 TS 类型定义）
│   ├── ontologyApi.ts        # Ontology 树/图专用 API
│   ├── ontologyGraph.ts      # GraphExplorer 图数据 API + 测试
│   ├── ontologyQueryApi.ts   # 规则 NL 查询 API
│   └── payloadUtils.ts
├── config/granularity.ts     # 资源粒度配置（macro/meso/micro/molecular/term 表单预置）
├── hooks/
│   ├── useData.ts            # 通用 fetch hook {data, loading, error, reload}
│   ├── useSessionIds.ts      # sessionStorage 'ngiq_pipeline_ids' 流水线 id 追踪
│   ├── useGlobalGranularity.tsx  # 全局粒度上下文（URL hash granularity_level 同步）
│   └── useBackgroundTasks.ts # 任务中心轮询 hook（3s/15s）
├── logging/                  # Workbench 底部日志控制台（localStorage 持久化 + window error 捕获）
├── layout/WorkbenchLayout.tsx # 顶栏 + 侧边栏 + 主区 + 底部日志控制台
├── components/               # 全局复用组件（见 §5）
│   ├── brain-3d/             # three.js 3D 脑区视图
│   ├── import-batches/       # 批次管理弹窗组（Clone/Edit/Delete/Create/Rollback/RunHistory…）
│   └── pipeline/             # 流水线筛选横幅/阶段数据操作
├── pages/                    # 按业务域组织（见 §7）
│   ├── DashboardPage / ResourcesPage / FilesPage / ImportBatchesPage / ImportPipelinePage
│   ├── LlmExtractionPage + llm-extraction/（复合工作流 + 字段补全）
│   ├── MirrorKgPage / MirrorValidationTab
│   ├── data-center/（数据中心）+ legacy redirect
│   ├── evidence-center/（证据中心）+ validation-center/（校验中心）
│   ├── ontology-center/（本体中心: browser/detail/governance/query）
│   ├── symptom-query/（症状查询图谱）、GraphExplorerPage、Brain3DPage
│   ├── BackgroundTaskCenter / SettingsPage / FinalRegionsPage
├── services/taskRegistry.ts   # 后台任务注册表
└── utils/                    # piplineNavigation（hash query 工具）、parser 兼容层等
```

---

## 3. 路由系统（App.tsx）

`window.location.hash` 驱动，注册表 `ROUTES: Record<string, ComponentType>`：

| Hash 路径 | 页面 | 备注 |
|-----------|------|------|
| `/` | DashboardPage | |
| `/resources` | ResourcesPage | 资源登记 |
| `/files` | FilesPage | 文件管理 |
| `/import-batches` | ImportBatchesPage | 批次管理（含「导入流程」Tab） |
| `/import-pipeline` | ImportPipelinePage | 导入流水线（时间线视图，截断到 Candidate） |
| `/data-center` | DataCenterPage | 数据中心 |
| `/evidence-center` | **EvidenceCenterRedirect** | 旧路由 → 重定向到 `#/validation-center?tab=paper_evidence` |
| `/ontology-center` | OntologyCenterPage | 本体中心 |
| `/llm-extraction` | LlmExtractionPage | LLM 提取（主 main-llm-data-first 布局） |
| `/mirror-kg` | MirrorKgPage | Mirror KG 浏览 |
| `/task-center` | BackgroundTaskCenterPage | 后台任务中心 |
| `/graph-explorer` | GraphExplorerPage | Canonical KG 图探索 |
| `/brain-3d` | Brain3DPage | 3D 脑区视图（lazy 加载） |
| `/symptom-query` | SymptomQueryPage | 症状→回路图谱查询 |
| `/validation-center` | ValidationCenterPage | 规则校验/双模型/证据 |
| `/settings` | SettingsPage | 设置 |

**旧路由重定向**（LEGACY_REDIRECTS → `/data-center?tab=...`）：
`/raw-aal3` → rawTab=aal3；`/raw-macro96` → rawTab=macro96；`/candidates`、`/raw-aal3-labels`、`/raw-macro96-rows`、`/candidate-regions` 同理。

**跨页 URL 状态约定**：通过 hash query 传参（如 `?tab=raw&rawTab=aal3&batch_id=...`），工具函数 `readHashQueryParams` / `buildHashUrl`（`utils/pipelineNavigation.ts`）；`useGlobalGranularity` 将 `granularity_level` 写入 hash（`history.replaceState` 防刷）。

**Provider 嵌套顺序**（App.tsx）：
`I18nProvider → TaskDetailModalProvider → WorkbenchLogProvider → GranularityProvider → WorkbenchLayout → Suspense(Page)`。

---

## 4. 数据访问层约定

- **全部 API 调用封装在 `src/api/endpoints.ts`**（6553 行），页面按函数名导入，不直接写 URL。每个函数返回类型都定义了（MirrorRegion 等接口型别在同一文件）。
- fetch 封装 `client.ts`：非 2xx 抛 `ApiError(status, message, meta)`；错误自动写入 Workbench 底部日志（health poll 5xx 静默）；`buildApiUrl` 供下载/预览 URL 使用。
- 组件数据获取惯例：`useData(fetchFn, deps)` → `{ data, loading, error, reload }`，无缓存无重试（简单可靠）。
- 后台任务统一轮询：任务中心与顶栏 Dropdown 共用 `useBackgroundTasks()` → `listUnifiedTasks({limit:100})`，有活跃任务 3s、否则 15s，tab 隐藏暂停；`fetchTaskDetail` 按 task.type 分派详情端点。

### API 面（endpoints.ts 中所有 `/api/*` 路径前缀）

| 域 | 前缀 | 主要内容 |
|----|------|---------|
| 基础 | `/api/health`, `/api/system/restart`, `/api/database/status·databases·switch·validate` | 健康/系统/数据库运行时切换 |
| 资源文件 | `/api/resources`, `/api/resources/options`, `/api/files/options` | 资源 CRUD、预览、下载、回收站 |
| 导入批次 | `/api/import-batches`, `/api/import-batches/options` | 批次全生命周期 + pipeline overview |
| 原始解析 | `/api/raw-parsing/options·aal3-labels·macro96-rows` | RAW 行展示 |
| 候选 | `/api/candidates`, `/api/candidates/pools·replace·brain-regions·options` | 候选生成/池管理 |
| 连接池 | `/api/connection-pools*` | |
| 规则校验 | `/api/rule-validation/run·runs·results·options` | |
| 人工审核 | `/api/human-review/pending·records·options` | |
| 晋升 | `/api/promotion/records·options` | 遗留晋升 |
| 正式区 | `/api/final-regions`, `/api/final-regions/options·summary` | |
| LLM 提取 | `/api/llm-extraction/*` | runs/items/options/providers/task-types/prompt-templates/field-completion(相关 6 个)/circuit-extraction/molecular-circuit/composite-workflows(run/start/runs/steps/cancel/pause/resume/retry)/same-granularity-{connections,functions,circuits}/circuit-to-{steps,functions}/circuit-steps-to-projections/projection-to-functions/projections-to-circuits |
| Mirror KG | `/api/mirror-kg/connections·functions·circuits·triples·circuit-steps·projection-functions·circuit-functions·circuit-projection-memberships·evidence` | CRUD + `triples/consolidate` |
| Mirror 校验/评审/晋升 | `/api/mirror-kg/validation/run·runs·results`, `/api/mirror-kg/review/queue·action·records·target-types`, `/api/mirror-kg/promotion/preview·run·runs·records·candidates` | |
| 双模型 | `/api/mirror-kg/dual-model-verification/run·runs·results`, `/api/mirror-kg/circuit-projection-cross-validation/run·runs·results` | |
| Final KG/宏观 | `/api/final-kg/connections·functions·circuits·triples`, `/api/final-macro-clinical/promotion/*`, `/api/final-macro-clinical/browser/search·graph`, `/api/final-macro-clinical/export/run·list` | |
| 本体治理 | `/api/ontology/terms·vocabularies·vocabularies/usage·coverage·alignment/candidates(+batch-accept-exact·stats)·audit/run·runs·change-logs·enum-anomalies(+replace)·governance/{dashboard,issues,role,ungrounded-records}·groundings/{run,manual,batch-by-text,skip}·terms/duplicates·terms/batch-activate·regions/alignment` | |
| 证据-论文 | `/api/ontology/evidence/{search,list,attach,attach-preview,extract,extract-selected,extraction-runs,queue,translate,translate-batch,audit,batch(+preview),papers,stats,review-queue,reviews,passage/validate-selection,adjustments}` | |
| Canonical KG | `/api/canonical-regions(+roots·by-level·ancestors·children·parent·multiscale)·canonical-connections·canonical-circuits(·regions·connections·functions)` | GraphExplorer 数据 |
| 多尺度 | `/api/multiscale/atlas-regions·atlas-mappings·cell-types·molecular-entities·region-cell-alignments·region-molecular-alignments` | |
| 任务 | `/api/tasks/runs` | 统一后台任务 |
| 设置 | `/api/settings/options·runtime·api-providers/deepseek/test` | |
| 工作区 | `/api/workspace-files*` | |
| 校验 | `/api/validation/circuit/runs...` | 新建电路校验 |
| Ontology 前端专用 API | `ontologyApi.ts` / `ontologyGraph.ts` / `ontologyQueryApi.ts`（含 `/api/ontology-query` 规则查询） | |

> 注：完整函数清单与 TS 类型在 `endpoints.ts` 中（480+ export const），修改或新增端点必须在其内完成并对齐后端路由；任意页面不得绕开此文件裸写 fetch。

---

## 5. 全局复用组件（src/components/）

| 组件 | 功能 |
|------|------|
| DataTable | 通用斑马纹表格（条纹/选中态/操作列） |
| StatusBadge | 状态徽章（语义色） |
| KeyValuePanel | 键值明细面板 |
| ActionButton / FormPanel / Notice / States / PageHeader | 表单/提示/空态/页头 |
| SessionIdsPanel | 显示当前流水线 session ids |
| GranularitySwitcher | 顶栏粒度切换（macro/meso/subregion/cyto/molecular） |
| ForceGraph | d3 力导向图 |
| TaskCenterDropdown | 顶栏任务中心下拉（查看/跳转证据工作台 openEvidenceWorkbench） |
| TaskDetailModal | 全局任务详情弹窗（Provider + useTaskDetailModal） |
| BottomLogConsole | 底部日志控制台（折叠/展开/过滤/清空，localStorage） |
| CancelConfirmDialog / ConfirmDialog / CopyButton / ModelBadge | 确认/复制/模型徽章 |
| brain-3d/* | three.js 脑区 3D + 详情面板 + 未放置列表 |
| import-batches/* | 批次编辑/克隆/安全删除/绑定文件/回滚预览/运行历史 |
| pipeline/* | 流水线筛选横幅/阶段数据操作/阶段数据预览 Drawer |

---

## 6. 设计系统（styles.css 令牌）

```css
:root {
  --sidebar-w: 220px; --topbar-h: 52px;
  --log-console-height-collapsed: 44px; --log-console-height-expanded: 320px;
  --bg: #f2f3f5; --sidebar-bg: #001529;
  --sidebar-text: rgba(255,255,255,0.65); --sidebar-active-bg: rgba(22,119,255,0.25); --sidebar-active-text: #4096ff;
  --white: #ffffff; --border: #e5e6e8; --text: #1d2129; --text-muted: #86909c;
  --primary: #1677ff; --primary-hover: #4096ff; --primary-active: #0958d9;
  --success: #52c41a; --warning: #faad14; --danger: #ff4d4f;
  --radius: 6px; --radius-md: 8px; --card-radius: 10px;
  --shadow: 0 1px 2px rgba(0,0,0,.06); --shadow-md: 0 4px 12px rgba(0,0,0,.08); --shadow-lg: 0 8px 24px rgba(0,0,0,.12);
  --table-stripe: #fafbfc; --table-hover: #e8f4ff; --table-selected: #e6f4ff;
  /* Evidence Center 视觉令牌 */
  --main-padding-y: 22px; --bg-soft: #f8fafc; --info-bg: #eff6ff;
  --success-bg: #dcfce7; --success-fg: #15803d; --warning-bg: #fef3c7; --warning-fg: #b45309;
  --danger-bg: #fff1f0; --muted-bg: #f1f5f9; --evidence-bg: #f5f7fa;
  --progress-ok: #34c77b; --progress-warn: #f2b13b; --progress-bad: #f2685f;
  --font-mono: Consolas/Menlo/Courier New
}
```

- 布局：`.layout` grid（topbar 52px + 侧栏 220px）；`.main` overflow-y auto；`main-data-center`/`main-brain-3d` 为 flex 列 + overflow hidden 并给底部日志栏留 padding。
- 页面结构惯例：`.page-header`（标题+描述+右侧动作）、`.card`（白卡）、`.table` 斑马纹。
- 卡片/表格/徽章语义色统一走上面令牌；新增页面应复用 class（`styles.css` 已是 14.6k 行的全局约定——不要新建样式体系）。

---

## 7. 页面功能清单

### 7.1 顶层页面

#### DashboardPage (`#/`, 363 行)
系统仪表盘。卡片式：后端状态卡、当前数据库卡、数据库切换卡、4 组统计卡（Final Regions / Resources / Import Batches / Candidates）、「📚 论文证据库」卡（条件渲染）、SessionIdsPanel、快捷链接。
- 操作：刷新；重启后端（danger + ConfirmDialog，确认后 2.5s 等待 + 每 1.5s 轮询 `/api/health` 40s 直到恢复）；数据库下拉（`schema_status==='mvp1_ready'` 且非当前库才可切换，带确认）；Swagger 链接；「前往论文证据中心」「查看论文库」。
- API：`/api/health`、`/api/database/status`、`/api/database/databases`、`POST /api/database/switch`、`POST /api/system/restart`、`/api/final-regions/summary`、`/api/resources`(limit 1)、`/api/import-batches`(limit 1)、`/api/candidates/brain-regions/status-summary`、`/api/ontology/evidence/stats`（Promise.all 并发）。

#### ResourcesPage (`#/resources`, 1068 行)
图谱资源（Atlas Resource）管理。按粒度 Tab（macro/meso/micro/molecular/term，含计数徽章）+ 粒度信息卡 + Macro 预设区（AAL3/Macro96 卡）+ 内联资源表单 + 详情卡 + 筛选 DataTable。
- 操作：新建/编辑/查看/归档/恢复/销毁式删除（`ResourceDestructiveDeleteModal`，支持 purge-then-recreate）；粒度 Tab 切换写 localStorage；表单字段含 granularity_family「推荐/高级」切换（create 时 granularity_level 锁定）；预设动作 useExistingActiveResource / restoreOrPurge / purgeThenRecreate / goUploadBrainVolumeList(→`#/files`)。
- API：`/api/resources/options`、CRUD `/api/resources`、`/api/resources/{id}`、`DELETE`(归档)、`POST .../restore`。重复资源码 422 走 `utils/duplicateResourceError` 拆解展示依赖计数。

#### FilesPage (`#/files`, 1968 行)
文件管理，双模式 Tab（资源文件 / 工作区文件，localStorage `ngiq_files_mode`）。上传面板 + 资源选择器 + 列表 DataTable + 右侧粘性预览窗格（preview/metadata/intermediate/raw 子 Tab）+ 工作区 Attach-to-Resource 对话框 + 重复文件提示卡。
- 操作：上传（按扩展名自动建议分类：.xml→label_table、brain volume xlsx→spreadsheet 等）；预览/下载/停用/恢复；生成/重新生成中间态（normalize）、查看 intermediate artifact 各渲染器；工作区归档/附加到资源。
- API：`/api/files/options`、`/api/resources/{id}/files`、文件详情/preview/download/intermediate/intermediate/runs/intermediate/preview、`POST /api/files/{id}/normalize`、PATCH/DELETE/restore、`POST /api/resources/{resourceId}/files`(FormData)、`/api/workspace-files*`（含 attach-to-resource）。

#### ImportBatchesPage (`#/import-batches`, 1034 行)
批次管理（导入流程已并入）。左列表 + 右详情：详情 Tabs overview/pipeline(导入流程时间线+操作+治理链路)/files/events/raw。
- 操作：CreateBatchModal（选资源/文件、batch_type/parser_key、绑定角色）；queue/start/edit/cancel（按状态经 `batchEditPermissions` 控制可编辑性）；Pipeline Tab：队列/启动/解析 Macro96/解析 AAL3/生成候选脑区；治理链路跳转 rule-validation/human-review/promotions/data-center(mirror/final)。
- API：`/api/import-batches*`（列表/options/详情/events/PATCH/cancel/queue/start/parse-aal3/parse-macro96/generate-candidates/generate-macro96-candidates）。`filterWorkbenchBatches` 过滤 cancelled。

#### ImportPipelinePage (`#/import-pipeline`, 9 行) / MirrorKgPage (`#/mirror-kg`, 9 行)
纯重定向页：分别跳 `#/import-batches` 与 `#/data-center?tab=mirror`（防旧书签 404）。

#### SettingsPage (`#/settings`, 344 行)
设置页：Tab `language` / `api` / `basic`。
- 语言下拉（zh-CN/en-US）；API：enabled/baseUrl/default_model（deepseek-v4-pro/v4-flash 等）/api_key(密码框不回填,placeholder 显示掩码)/timeout_seconds(5–120)/max_batch_size(1–20)/「保存时清除 API Key」；「测试连接」显示 OK · model · latency ms；basic：default_page_size/max_page_size/show_debug_panels。
- API：`/api/settings/options`、`/api/settings/runtime`(GET/PATCH)、`POST /api/settings/api-providers/deepseek/test`。

#### BackgroundTaskCenter (`#/task-center`, 496 行, BackgroundTaskCenterPage)
后台任务中心：6 类任务统一管理（composite_workflow/field_completion/circuit_extraction/circuit_connection_extraction/molecular_circuit/paper_evidence）。
- 8 状态统计条（全部/进行中/排队中/已暂停/已完成/部分失败/失败/已取消）+ 左侧筛选侧栏（状态/任务类型/时间/排序）+ 卡片列表 + 详情 Drawer。
- 操作：「新建论文佐证任务」「取消选中 (n)」「全选排队 (n)」批量操作；卡片上「详情」「打开佐证工作台」(paper_evidence 类 → evidence-center candidates)、「暂停」「继续」「重试失败项」「取消」（按状态与 taskDef.canPause 条件渲染）。
- API：`/api/tasks/runs`（useBackgroundTasks 3s/15s 轮询）；详情/取消/暂停/恢复/重试按类型分派（field-completion/composite-workflows/circuit-extraction/circuit-connection-extraction/molecular-circuit/ontology-evidence batch 各端点）。类型定义集中 `services/taskRegistry`。

#### GraphExplorerPage (`#/graph-explorer`, 240 行)
图谱探索，双视图 Tab：`legacy`（旧 d3 力导向图，直接 fetch `/api/kg/graph/data`，绕过 endpoints.ts——legacy 遗留）+ `canonical`（Canonical KG：侧栏 + React Flow 画布 + Inspector，源码在 pages/graph-explorer/ 子目录 ~6 文件）。视图状态写 URL（`?view=legacy|canonical`）。
- canonical API：`getFinalGraph`（`/api/final-macro-clinical/browser/graph`，center_type/center_id/depth/source_atlas/granularity_level/include_functions/include_evidence/include_triples/limit=200），mirror 源列表，`listRegionCandidates` 定位等。

#### Brain3DPage (`#/brain-3d`, 147 行, lazy)
3D 脑图（Macro96）：先加载空间数据展示表格（已定位节点：名称/MNI 坐标/状态），「进入3D视图」后渲 Three.js 主视图 + 右侧详情面板 + 未定位区域列表（manual_review/unmapped 两类原因）。
- 无后端 API：读 `public/brain_3d/major96/*.json` 静态文件（`lib/brain-spatial/` 模块级缓存）；3D 节点点击选中查看详情。硬编码中文，无 i18n。

#### FinalRegionsPage (`#/final-regions`, 222 行)
⚠️ **孤儿页面**：`App.tsx` ROUTES 无此路径、全仓库无 import（Dashboard 的 `#/final-regions` 链接会落回 DashboardPage）。功能设计：Final 脑区列表(搜索/laterality/granularity_level/status 筛选) + 详情（基本信息 + 溯源自证卡 + 晋升记录卡）。API：`/api/final-regions`、`/api/final-regions/{id}/provenance`。

#### MirrorValidationTab.tsx (477 行)
⚠️ **孤儿组件**：未被任何入口 import——`LlmExtractionPage.tsx` 内有一份本地副本在 governance-gate 中实际使用，本文件为遗留版本。功能：Mirror 校验运行表单（10 目标类型复选、core/macro/signal 分组、dry-run、apply-status-update、limit）+ 运行记录/结果表。API：`/api/mirror-kg/validation/run·runs·results`。

#### DataCenterPage (`#/data-center`, 166 行壳体)
数据中心统一入口，7 Tab：**overview**（计数总览）、**raw**（子 Tab aal3/macro96）、**candidates**、**mirror**（子 Tab connections/functions/circuits/triples）、**macro**（circuit_steps/projection_functions/memberships/circuit_functions/cross_validation/dual_model）、**final**（circuit/circuit_step/projection/projection_function/membership/region_function/circuit_function/triple）、**exports**。状态全写 URL hash 双向同步；mirror→macro 定向跳转（`onJumpToMacro`）。计数由 `useDataCenterCounts` 并发 19 个计数请求（Promise.allSettled + 10s 超时兜底，失败降级 0）。

#### LegacyDataCenterRedirect (24 行)
旧路由兜底组件：挂载即跳目标 hash，附提示 + 手动「前往数据中心」按钮。

#### ValidationCenterPage (`#/validation-center`, 30 行壳体)
渲染 `ValidationWorkbench`（子目录实现），透传 granularity；左上「返回上一页」箭头（`window.history.back()`）。工作台内部功能见 §7.3。

### 7.2 数据中心 (data-center/) + 本体中心 (ontology-center/) 模块

#### DataCenterPage 结构（Tab 定义 `dataCenterTypes.ts`）
`DATA_CENTER_TABS = ['overview','raw','candidates','mirror','macro','final','exports']`；导航状态 `{tab, rawTab, mirrorTab, macroTab, finalTab, batchId, resourceId, sourceAtlas, granularityLevel}` 全部编码进 hash（parse/write 双向同步 + hashchange 监听）；全局粒度来自 `useGlobalGranularity`；计数经 `useDataCenterCounts`（19 端点并行 + 10s 超时 + Promise.allSettled）。

| Tab | 面板 | 内容 |
|-----|------|------|
| overview | DataCenterOverview | 流水线阶段卡(Raw→候选→Mirror→Final) + 需要关注 + 论文佐证统计 + 快速入口 |
| raw | RawDataPanel (aal3/macro96) | 内嵌 RawAal3Page / RawMacro96Page |
| candidates | CandidateRegionsPanel | 内嵌 CandidatesPage |
| mirror | MirrorKgPanel | 子 tab connections/functions/circuits/triples；connections→[projection, projection_function]、functions→[region_function]、circuits→[circuit, circuit_step]、triples→[triple] |
| macro | MacroClinicalDataPanel | 子 tab circuit_steps/projection_functions/memberships/circuit_functions/cross_validation/dual_model |
| final | FinalKgDataPanel | 只读 8 子 tab: circuit/circuit_step/projection/projection_function/membership/region_function/circuit_function/triple |
| exports | ExportPackagesPanel | 导出清单 → 文件表 → 下载 |

**核心列/抽屉组件**：
- `FormalObjectTableSection`：选择引擎（页选/全选 filtered + 浮层操作条 FAB：AI 补全/校验/删除/论文佐证）+ `ConfidenceFilterPopover`（置信度区间 + includeNull）+ 服务端分页（无则回退 `useDataCenterPagination` 客户端分页，select-all-filtered 时 onFetchAll limit 5000）。
- `FormalObjectDetailDrawer`：逐字段可编辑（保存/删除）、`PaperEvidenceColumn` 内嵌、AI 补全入口、查看原数据跳转。
- `FormalAlignmentCard` 系列：mirror 表→formal DB 映射（使用 `formalFieldMappings.ts`：10 类 FormalObjectType 列映射 + getFieldValue/computeMissingFields/computeCompleteness）。
- `MissingFieldsBadge`（"完整"/"缺失 N"）、`DataObjectDetailDrawer`（通用只读抽屉）、`DataCenterTableRegion`/`DataCenterPagination`（50/100/200/全部）。

**AI 字段补全（核心特色）**：
- `FieldCompletionModal`：4 步向导（选对象→Provider/Model（deepseek-chat/v4-flash/v4-pro/reasoner、kimi moonshot-v1-*）→补全范围 missing_only/selected_fields/all_enrichable_fields →覆盖策略 fill_missing_only/overwrite_with_review/suggest_only → Dry Run（费用/调用估算）→ 执行（异步 run_id，取消，后台运行）。
- `MultiTargetFieldCompletionModal`（Circuit Bundle）：circuit+circuit_step+circuit_function 分组状态机 pending→running→executed，execRef 游标逐组执行，60s 无 run_id 超时兜底。
- `FieldCompletionStatsCards`：进度/模型调用/更新/建议/跳过/失败/费用估算。
- **Overlay patch 模式**：补全结果 `applied_overlay` → `extractOverlayPatchFromItems` → `mergeOverlayPatches` → 行 `__fieldCompletionOverlay`，`getFieldValue` 优先读 overlay，不刷新表格即显示新值 + "overlay" 徽章。
- 轮询：setInterval 2000ms poll `getFieldCompletionRun`，mountedRef/notifiedRef/onCompletedRef 防重。
- 错误归一化：`MIRROR_CIRCUIT_FUNCTIONS_NOT_INITIALIZED`(503) → 迁移提示；`classifyFieldCompletionError` 映射 404/501/422/503 为友好 i18n。

**论文佐证（Paper Evidence）**：`PaperEvidenceColumn`（单对象：检索→AI 提取段落→翻译→挂接→撤销）+ `PaperEvidencePanel`（独立简化版）。检索分功能/存在性模式；提取段落做来源校验；翻译逐段；会话级 handoff：sessionStorage `evidence-center.initial-queue` + 跳 `#/validation-center?tab=paper_evidence`。

**数据库 API**：`/api/mirror-kg/{connections,functions,circuits,triples,circuit-steps,projection-functions,circuit-functions,circuit-projection-memberships,cross-validation/results,dual-model-verification/results}`、`/api/final-macro-clinical/objects/{targetType}[{finalId}]`、`/api/final-macro-clinical/export/*`、`/api/llm-extraction/field-completion/{run,runs,related-targets,prompt-templates}`、`/api/ontology/evidence/{search,attach,list,extract,translate,rollback,batch,stats,target}`、`/api/connection-pools*`（projection 加入连接池）。

#### OntologyCenterPage（本体中心，3 主 tab：browser / query / governance）

- **browser → OntologyBrowser**（三栏，类 BioPortal）：顶栏 `OntologyScaleSelector`（compact 尺度透镜：macro/clinical/meso/subregion/fine/cyto/molecular，写回 hash `oc_scale`）。
  - 左栏 Explorer：搜索（≥2 字符、300ms 防抖、6 类实体并行搜索、分组结果）+ 非搜索态 `OntologyTree`（懒加载 + childrenCache/expandedIds ref 镜像防连点竞态 + 叶子探测 + 级联自动展开 whole_brain/macro/clinical + 「展开到研究层级」迭代扫描 30ms/5s 超时/20 轮 + "(n)" 计数徽章）。
  - 中栏 `EntityDetailPanel`：按 entityType 5 种布局（region breadcrumb+Children+External Atlas+Molecules+知识关系 / connection Source→Target / circuit 拓扑/连接/功能 / function 层级 / cell_type·molecule 跨层 overview）。
  - 右栏 `RelationExplorer`：Tabs All/Connections/Circuits/Functions + 计数 badge（1280px 折叠）；关系数据单次拉取共享（中栏+右栏共用，`relationsReloadKey` 重试）。
  - 详情行点击/Entity 卡/「Open in Graph」跳图谱；hash 深度链接 `tab=browser&entity_type=...&entity=...`（Browser 挂载只消费一次）。
- **query → OntologyQueryPage**（`OntologyQueryDashboard` 无实现文件，仅残留测试；真实页面为 OntologyQueryPage）：
  - 左 `QueryInput`（示例问题、最近查询 localStorage `ngiq.ontology-query.recent` 5 条、Ctrl/Cmd+Enter 提交）；中列：`QueryEmptyState`（initial/unresolved 候选 chips/空+后端 warning）→ `QuerySummaryCard`（Entity/Intent/Results/Confidence 指标）→ `AIExplanationCard`（幻觉 warning + Key Points）→ `EvidenceSummary`（结构/功能/不确定 统计条）→ `QueryResultTable`（结构结果/证据链/相关回路 3 tab，置信度排序）；右栏 `RightContextPanel`：`EntityContextCard` + `SourceListCard`（来源分组占比）+ Quick Actions。
  - API：`POST /api/ontology-query/explain`（`postOntologyQuery` `/api/ontology-query` 存在但未用）。
- **governance → OntologyGovernance**（子 tab functions/regions/relations）：
  - `GovernanceOverview`：6 统计卡（锚定率/待审核/未锚定/待对齐/枚举异常/最近审计）+「运行确定性锚定」「运行本体审计」。
  - functions：`TermsTable`（proposed/all、搜索、多选批量激活、激活/弃用/合并/同义词/详情）+ `UngroundedView`（推荐/人工锚定/创建 proposed/暂不处理）+ `DuplicatesView`（合并建议只读）。
  - regions：`RegionCandidates`（pending/accepted/rejected 三态、批量接受 exact（admin））；connections/circuits：`EntityView` 只读分布；relations：词汇表注册表（按 vocab_type 分组）/枚举异常（按域查询 + admin 批量替换）/变更日志。
  - 弹窗组件：`GovernanceModal`、`TermDetailDrawer`、`MergeDialog`（getMergePreview 预览）、`DeprecateDialog`（迁移或仅禁引用）、`SynonymDialog`。
  - **角色控制**：`getOntologyRole` → viewer/reviewer/ontology_admin；viewer 无操作按钮。
- **API**：canonical (`/api/canonical-regions/roots|{id}/parent|ancestors|children|connections|circuits|functions|candidates|multiscale`、`/api/canonical-connections`、`/api/canonical-circuits`)、terms (`/api/ontology/terms*` + activate/deprecate/merge/synonyms/duplicates/batch-activate + `/api/ontology/hierarchy/terms/{id}/parents|children`)、multiscale (`/api/multiscale/*`)、governance (`/api/ontology/governance/{dashboard,role,ungrounded-records,entity-summary}`、`/api/ontology/groundings/{run,manual,skip}`、`/api/ontology/audit/run`、`/api/ontology/vocabularies/usage`、`/api/ontology/enum-anomalies(+replace)`、`/api/ontology/alignment/candidates(+stats/batch-accept-exact)`、`/api/ontology/change-logs`）。
- **模式**：组件只依赖 `ontologyApi.ts` adapter（getTreeChildren/getEntityDetail/getRelations/searchEntities/getRegionResearchView），内部按 entityType 分发；不存在的 API 关系组返回 `unavailable: true`（显示「后端 API 待接入」，不造假数据）；AbortController 全面取消 + mountedRef 防未挂载 setState；粒度透镜用 `GRANULARITY_LEVEL_ORDER`（whole_brain=0…molecular=9）只过滤显示深度，level 不参与父子判定。

#### data-center 孤儿/备用组件（事实核对）
`EvidenceReviewModal`（兼容壳，打开即跳 `#/validation-center`）、`FieldCompletionPlaceholderModal`、`DataCenterSummaryCards`、`CircuitFunctionPromotionPreviewSection`、`PromptWorkbenchSection` 均无正式调用点（保留复用）。

### 7.3 证据中心 (evidence-center/) + 验证中心 (validation-center/)

#### 部署形态（重要）
`App.tsx` 中 `/evidence-center` → `EvidenceCenterRedirect`（useEffect 重定向 `#/validation-center?tab=paper_evidence`）。**实际宿主是验证中心 embedded 模式**。`EvidenceCenterPage` 支持 standalone / embedded（`tab=paper_evidence` 时 URL 参数才被解析）。

#### 证据中心：论文佐证五阶段工作台
服务「佐证任务 → 论文库 → 证据候选 → 人工审核 → 证据晋升」流程（StepPills 五步：确认对象→查找论文→找到原文→人工审核→确认晋升）。三栏布局（左 aside / 中 main / 右 aside），tasks/papers 模块隐藏左右栏。

- 上下文：`EvidenceCenterProvider`（状态 `{module, taskId, taskItemId, targetType, targetId, paperId}` ↔ URL hash 双向同步，`buildEmbeddedUrl`/`buildEvidenceUrl`；`navigateToEvidenceCandidates()` 做 sessionStorage 队列交接）+ `TaskItemsRefreshProvider`（version 计数，审核后 refresh 全量重取）。
- URL 解析/构建集中于 `evidenceCenterUrl.ts`（`INITIAL_QUEUE_KEY='evidence-center.initial-queue'`）。
- 五模块（`EVIDENCE_MODULES=['tasks','papers','candidates','review','promotion']`）：
  - **tasks `EvidenceTasksModule`**：任务筛选 pills（全部/连接/回路/功能）+ 任务卡（「继续验证/查看结果」才跳转、暂停/恢复/重试失败项）+「创建批量预处理」`CreateBatchTaskDialog`（任务名/对象类型/模式（功能|存在性）/目标范围（勾选对象|低置信）/Confidence<阈值/每对象最多论文/limit/仅 OA/止于强支持，打开即 debounce 300ms scope 预览）。
  - **papers `PaperLibraryModule`**：论文库搜索（标题/期刊/PMID/DOI）+ 仅 OA/年份/已解析全文 + 分页 + `PaperDetailDrawer`（摘要 + 按 section 分组的全文段落 + 关联对象 chips）。
  - **candidates `EvidenceCandidatesModule`**（核心，1125 行）：`getEvidenceTarget` 400 "target not found" 专用面板；自动检索（无候选用系统推荐词）+ 手动检索 + 过滤 + 全选提取（`createPaperEvidenceExtractionRun` 并行 + 1s 轮询 + 取消/仅重试失败）；`PassageEvidenceCard` 片段卡（未核验禁用/证据等级/佐证组件勾选/翻译/重新截取后端校验/语义置信度）；勾选片段写 sessionStorage 草稿 `evidence-center.review-draft.{targetId}`；状态条 + 「进入人工审核(N)」。
  - **review `EvidenceReviewModule`**：草稿恢复；350ms debounce 置信度预览（`attachPaperEvidencePreview`）；`ReviewerDecisionPanel`（AI 初判 + Coverage；人工方向 supports/partial/contradicts/mixed/not_found + 置信度滑块 0–0.85 + Note + 置信度影响格 Current/Reviewer/Rule/Maximum/Final + 「驳回证据」「审核通过」）；`CoveragePanel`（组件 ✓/✕/○ + 冲突警告）；`useTaskItemResolution` 门控（未解析完成禁用审核）；`commitReviewStatus`（buildReview 权威 + sessionStorage 兼容）；通过/驳回后自动下一条 + 「返回上一条」；重审先 `reopenPaperEvidenceTaskItem`；`ReviewHistoryDrawer` / `RollbackRescoreDialog`（幂等键 crypto.randomUUID，409 提示）。
  - **promotion `EvidencePromotionModule`**：待晋升列表（`listEvidenceReviews` approved+awaiting_promotion，失败回退 sessionStorage）+ `PromotionImpact`（人工方向/置信度变化/新增 Evidence/Passages + sticky 按钮）+ `PromotionDialog`（「确认入库」/被拦截时「强制入库(跳过验证)」）+ 确认入库 → 队列 completed → `completePaperEvidenceTaskItem` 回写 → 自动下一条（1500ms）+「退回审核」（`returnReview`）+ 证据详情/回滚（`rollbackPaperEvidence` 必填原因）。
- **API**（`/api/ontology/evidence/*`）：`target/{type}/{id}`、`search`、`extract-selected`、`extraction-runs(+/{id}/cancel|retry-failed)`、`attach-preview`、`translate(-batch)`、`passage/validate-selection`、`reviews(+/{id}/approve|reject|rollback-for-rescore|history|promote|return)`、`list`、`{id}/rollback`、`batch(+/{id}/items,items/resolve,items/{itemId}/reviewed|reopen,batch/{id}/pause|resume|retry-failed,batch/items/{itemId}/draft,batch/preview)`、`papers(+/{id})`。
- **模式要点**：URL 参数即状态（可深链）；大量中文注释引用需求章节（三.3–9、S6、S7B）；前端公式镜像后端 confidence_rules（supports cap 0.85/partial cap 0.75）但最终以 attach-preview 服务端结果优先；`ClaimPanel/ConfidencePreview/TaskSummary(组件本体)` 为已弃用遗留。

#### 验证中心
`ValidationCenterPage`（30 行壳）→ `ValidationWorkbench` → `<EvidenceCenterPage embedded/>`。
⚠️ 目录中其余组件（`ValidationStatsBar/DualReviewComparison/QualityScoreBadge/CircuitDetailDrawer/RepairModal/EnhancementModal/RuleValidationTab/CandidateCircuitTable/CircuitSelector/DualReviewPanel/HumanReviewPanel/PaperEvidenceReviewPanel/PromotionPanel`）**均为历史遗留死代码**（无任何路由/页面引用，裸 fetch `/api/validation/circuit/*` + 2s 轮询 + SafeApiResponse 容错）。新增功能请勿复用，其中有用的是 `validationCenterTypes.ts` 的类型模型与 `/api/validation/circuit/*` 后端能力（RepairModal 的 DeepSeek 诊断/修正/重新验证、数据增强 Tier1+Tier2、双模型重试等视觉稿功能，接线时可参考其 API 形状）。

### 7.4 LLM 提取 (llm-extraction/) + 症状查询 (symptom-query/)

#### LlmExtractionPage（`src/pages/LlmExtractionPage.tsx`，**6626 行四大页**）
Data-First 流水线。顶级 Tab：`candidates 候选 / mirror 抽取 / runs 运行 / items 条目 / macroClinical / finalLinks / fieldCompletions 字段补全`（+ legacy hash tab：finalPromotion/finalBrowser/finalExport/promotion/validation/review 等以 alias 兼容）。只写 mirror 层，绝不写 final/kg。
- 候选源切换：🧠脑区 / 🔗连接 / 🔄回路；`QuickExtractionCards` 快捷卡（脑区功能/连接提取/回路+步骤+功能；回路模式另有「多连接提取」「主连接对提取」）。
- 提取池：`useCandidatePool` / `useConnectionPool`；`PoolExtractionModal`（3361 行，4 步向导）：①池成员勾选+分包计划（每包脑区数 5–50 / Shuffle 轮数 / pairs_per_pack 1–500 默认 30）②LLM 配置（Provider deepseek/kimi、Model preset、Temperature、Max Tokens、并发 1–8、skip_existing、预算上限）③任务目标+提示词模板绑定+补充要求 ④Dry Run 预览（费用/调用估算，前后端包数不一致则禁止）→「开始正式提取」。
- 运行：`compositeExtractionRunner` 核心编排器（**优先 `startCompositeWorkflow` + 1.2s 轮询 `getCompositeWorkflowRun`；404 回退同步 `/run`；再无前端 fallback 编排**）；`ExtractionProgressPanel`（进度条/包统计/tokens/费用/pause/resume/cancel/后台运行/重试失败包/DryRun 明细）；`ExtractionResultModal`（provider 审计网格、pack 故障诊断 raw preview、workflow events、circuit bundle 一键补全）；`ExtractionRunFloatingWidget`（可拖动悬浮窗，位置 sessionStorage）；单步模式 `ExtractionRunModal`（BATCH_SIZE=20 前端分批串行）。
- 结果浏览：`MirrorExtractionPanel`（mirror 4 子表 connections/functions/circuits/triples + JSON 抽屉）；`ExtractionResultPanel`（items 卡视图，11 类 `EXTRACTION_TYPE_CONFIGS`）；`FieldCompletionTab`（目标切换 connection/circuit/circuit_bundle + ModelSelector + 2s 轮询）。
- Macro Clinical：6 张 `MacroPipelineCard`（CircuitToSteps / CircuitStepsToProjections / ProjectionToFunctions / ProjectionsToCircuits / CrossValidation / DualModel）+ `useMacroClinicalPipelineProgress`（7 计数 → 6 步）。
- 治理 Tab：`MirrorValidationTab`（10 目标类型复选 ✓ 本文件内有工作副本）、`MirrorReviewTab`（审核队列/动作）、`MirrorPromotionTab`（preview→run）、`FinalMacroClinicalPromotionTab`、`FinalKgBrowserTab`、`FinalKgExportTab`。
- `workflow/`：`WorkflowNextStep/WorkflowProgressBar/WorkflowStageRail/useWorkflowProgress`（5 stage 全局进度，17 API 计数并发）。
- **API 面**（均在 `/api/llm-extraction/*`，见 §4 表）：candidates/pools、connection-pools、runs/items/options/providers/task-types、field-completion（run/runs/related-targets/prompt-templates）、circuit-extraction、circuit-connection-extraction、molecular-circuit（start/progress/取消/暂停/恢复）、prompt-templates、same-granularity-{connections,functions,circuits}、circuit-to-{steps,functions}、circuit-steps-to-projections、projection-to-functions、projections-to-circuits、composite-workflows（start/run/runs/{id}/cancel·pause·resume·retry-failed）。
- **模式**：全程轮询无 SSE；`mergeMonotonicCounter` 防进度回退；workflow events → `emitWorkbenchLog` 日志桥接（去重）；sessionStorage：`ngiq_pipeline_ids`（scope）、`llm.extractionWidgetPos`、`llm.dismissedWorkflowRunIds`、`pendingCircuitFunctionExtractionCircuitIds`、`connPoolFieldCompletionIds`。

#### SymptomQueryPage（`#/symptom-query`，369 行 + SymptomCircuitGraph 424 行 + ClinicalReportModal 513 行）
症状驱动的神经回路查询：AI 对话收集中 → 总结确认 → 标准化功能分析 → 检索回路 → 可视化图谱 → 临床报告。
- Phase 状态机 `idle→chatting→summarizing→analyzing→results`；模式 focused/exploratory；顺序 await analyze→expand→search→graph（`analysisRunRef` 防新覆盖旧）。
- `SymptomCircuitGraph`：**纯 SVG 手绘力导向图（非 d3）**——确定性初始坐标（按 id hash，左右半球分带）、节点拖拽、平移缩放、双击聚焦、关系类型下拉/置信度 slider/脑区搜索/显示模式（全部|步骤聚焦|脑区聚焦）、背景连接开关（≥200 上限裁剪）、回路步骤面包屑、图例；可见性计算纯函数 `computeSymptomGraphVisibility`。
- `ClinicalReportModal`：4 阶段动画进度 + Markdown→HTML 自研行式解析 + 图谱 PNG 捕获（SVG clone→canvas）插入正文 + 下载 PDF（`POST /api/symptom-query/report/pdf`，graph_image base64）+ 打印。
- **API**：`POST /api/symptom-query/{conversation,analyze,expand,search,graph,report,circuit-describe,report/pdf}`。
- 模式：无轮询无 SSE，全离线前段图渲染；进度动画为客户端模拟。

### 7.5 共享组件核对（src/components/，实际清单）

| 组件 | 功能要点 |
|------|---------|
| DataTable | 通用表格 columns/rows/loading/error/empty/total/getKey/onRowClick/getRowClassName；footer 总记录数。几乎所有列表页使用 |
| StatusBadge | 状态→色彩映射（succeeded 绿/failed 红/pending 黄/running 蓝/cancelled 灰/llm 系列彩）+ 中文 label |
| KeyValuePanel / ActionButton / FormPanel / Notice / States / PageHeader | 常规 UI 基建；PageHeader 默认 readonly=true 显示🔒「只读」徽章 |
| SessionIdsPanel | 流水线 session ids 展示/复制/清空 |
| GranularitySwitcher | 顶栏粒度切换（读写 useGlobalGranularity） |
| ForceGraph | d3 力导向图：预跑 300 tick 一次布局提交、20 万边上限、拖拽缩放 tooltip、高亮集合二次更新；导出 NODE_COLOR/EDGE_DASH/LegendItem |
| TaskCenterDropdown / TaskDetailModal(+Provider) | 顶栏任务铃铛 + 全局详情弹窗（field_completion→FieldCompletionStatsCards，composite→ExtractionProgressPanel）；`fetchTaskDetail` 分派 |
| CancelConfirmDialog / ConfirmDialog / CopyButton / ModelBadge | 确认/复制/模型徽章（deepseek-chat=V3、v4-pro=V4P、reasoner=R1、moonshot=Kimi 色系） |
| BottomLogConsole | 底部日志控制台（过滤 all/error/warning/info/request、复制、清空、高度写回 CSS var） |
| ResourceDestructiveDeleteModal | 资源销毁删除（预览依赖计数 + operator/reason 双验证 + thenRecreate） |
| brain-3d/* | three.js 3D 视图 + 详情面板 + 未放置列表 |
| import-batches/* | BatchCloneDialog/BatchEditModal/BatchFileBindingsEditor/BatchSafeDeleteDialog/BatchShortId/CreateBatchModal/RollbackPreviewModal/RunHistoryPanel |
| pipeline/* | PipelineFilterBanner/PipelineStageDataActions/StageDataPreviewDrawer |

> ⚠️ `ModelSelector` 实际位于 `llm-extraction/components/ModelSelector.tsx`，不在共享 components 下。`ProgressPanel`（旧 pack 进度条 133 行）与 `ExtractionProgressPanel`（新版 545 行）是两个不同组件，新接入用后者。

---

## 8. 关键约束（前端开发须知）

1. **不引入 react-router**：继续用 hash 路由注册表 + `readHashQueryParams`/`buildHashUrl` 传参（`from_pipeline=1` 标识流水线跳转）。
2. **不改写 API URL**：所有端点走 `endpoints.ts`；新端点先确认后端存在。
3. **状态尽量本地**：页内 useState；跨页用 URL hash query（可分享/可书签）；跨页 session 用 `useSessionIds`（sessionStorage）。
4. **i18n 所有文案**：中文/英文 key 写进 `i18n.ts`，组件内用 `t('key')`。
5. **图表**：ForceGraph(d3) / xyflow / dagre / three 已装；新增图可视化优先复用现有组件。
6. **测试**：组件测试用 Vitest（`*.test.tsx` 相邻放置），关键页已有测试；`npm test` 运行。
7. **构建验证**：`npm run build`（tsc -b + vite build）必须 0 错误。
8. **数据治理边界**：前端只是展示/审查工具——LLM 提取结果进 Mirror KG，人工审核后晋升 Final；前端不得提供绕过审查直写 final 的入口。
