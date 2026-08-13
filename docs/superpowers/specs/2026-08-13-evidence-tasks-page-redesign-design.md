# 佐证任务页面重设计（PRD + 设计）

- **日期**: 2026-08-13
- **状态**: 已与用户逐节确认（页面结构 / 任务范围 / 队列范围 / 点击行为 / 既有改动处理 / 方案路线 A）
- **分支**: `codex/ontology-evidence`

---

## 1. 背景与问题

证据中心「佐证任务」模块当前只展示任务级列表（状态分组 + 行内操作），任务与其下每个知识对象（连接/回路/功能）的验证进度脱节：用户看不到「哪个对象置信度最低、最需要先处理」，也没有一个以任务为中心的处理工作台。

工作树中今早有一次未完成的半成品重构（左栏任务列表 + 中栏连接卡片），方向与用户新描述不符，**放弃该方向**，按本 PRD 重做，仅限佐证任务相关文件。

## 2. 目标

1. **任务列表视图**：中间展示全部证据佐证任务卡片（基本信息），进行中优先排序。
2. **任务详情视图**：点击任务卡片进入该任务的证据佐证页面 —— 主区就地嵌入证据候选工作区，右侧按置信度优先级（升序，低置信度最优先）展示待处理对象队列。
3. **筛选**：队列可按 回路 / 连接 / 功能 三组筛选。
4. **闭环**：对象处理完成后从队列消失，切回任务详情时自动刷新。
5. **回退重审**：右侧队列同时展示已完成对象，可一键回退到待审核、重新审查。

## 3. 非目标（明确不做）

- 不改动证据候选 / 人工审核 / 证据晋升模块的内容（仅嵌入复用，不修改）。
- 不改动 ValidationWorkbench 与验证中心其他 tab（工作树中既有未提交改动保留原样，不修、不还原）。
- 后端仅新增一个回退端点（见 R7），其余后端逻辑不动。
- 不做队列轮询、不做任务内分页（>200 条时截断提示）。

## 4. 需求明细

### R1 任务列表视图（无 taskId 时）

- 页面全宽布局（隐藏左右栏，同论文库模式），中间 = 任务卡片网格（响应式 2–3 列）。
- 工具栏保留：「创建批量预处理」「刷新」。
- 卡片基本信息：任务名（`name || target_type`）、目标类型徽章、状态徽章（进行中高亮）、进度「已处理 X / 总数 Y」、待审核 Z（>0 警示色）、失败数（>0 才显示）、创建时间。
- 排序：**进行中（pending/running/paused）→ 有等待审核（awaiting_review_items>0）→ 其他**，同组内创建时间倒序。
- 空态：暂无任务 + 创建 CTA；点击卡片 → 进入详情视图。

### R2 任务详情视图（有 taskId 时）

三栏布局（复用现有三栏壳）：

- **左栏** = `TaskListPanel`（保留现有组件；当前任务高亮；顶部加「← 任务列表」返回按钮；点击其他任务直接切换）。
- **主区** = 嵌入现有 `EvidenceCandidatesModule` 组件（不改动其代码）。
- **右栏** = 新建 `TaskItemQueue`（替换现有 tasks 分支的 TaskSummary）：顶部任务名 + 未完成计数 + 刷新按钮；筛选 chips「全部 / 回路 / 连接 / 功能」；队列条目列表。
- 主区上方紧凑详情条：任务名 + 状态 + 进度摘要（已处理/总数/待审）。

### R3 右侧队列（TaskItemQueue）—— 两区结构

右栏 = 任务名 + 未完成计数 + 刷新按钮 + **「待处理」区** + **「已完成」折叠区**。

**待处理区**：
- 数据源：`listPaperEvidenceTaskItems(taskId, { limit: 200 })`。
- 未完成集合 = `pending, searching, fetching, retrieving, extracting, verifying, awaiting_review`；排除 completed/skipped/failed/cancelled。
- 排序：`current_confidence` 升序；**null 置信度排最前**；同置信度按 label 稳定排序（localeCompare）。
- 筛选 chips（全部/回路/连接/功能）只作用于待处理区。
- 条目卡片：对象名称（`label || target_id`）、类型徽章、置信度大字（`toFixed(2)`，null → 「—」）、状态 chip、AI 方向（`model_direction`）、「未找到有效证据」（`preprocess_outcome === 'no_evidence_found'`）、当前选中对象高亮。
- 点击条目 → `openTarget(target_type, target_id, 'tasks')`，module 保持 tasks，主区加载该对象证据候选。
- 空态：待处理为空且已完成也为空 → 「全部处理完成」；仅待处理为空 → 该区显示「全部处理完成」小字，已完成区照常展示。
- >200 条时队列底部提示「仅显示前 200 条（按优先级截断）」。

**已完成区**（可折叠，默认折叠）：
- 数据 = `status === 'completed'` 的 items（skipped/failed 不进入两区，failed 沿用既有 retry-failed 机制）。
- 排序：按 `updated_at` 倒序（最近完成的在前）。
- 条目卡片：对象名称、类型徽章、置信度、状态 chip（已完成）。
- 每条带「回退重新审查」按钮 → 二次确认 → 调用回退端点（R7）→ 成功后刷新队列，该对象回到待处理区（按置信度重新排序）。失败显示错误提示，不改动队列。

### R4 筛选分组映射

| 分组 | target_type |
|---|---|
| 回路 | circuit, circuit_step, circuit_function |
| 连接 | connection, projection |
| 功能 | region_function, projection_function |
| 其他类型 | 仅「全部」下可见 |

### R5 导航与 URL

- 列表：`#/evidence-center?module=tasks`
- 详情：`#/evidence-center?module=tasks&task_id=X&target_type=T&target_id=I`（复用现有参数与 parse/buildEvidenceUrl，支持深链）。
- 点击任务卡片 → `openTask(id)`，其语义改为「进入 tasks 详情」：`apply({ taskId, targetType: null, targetId: null, module: 'tasks' })`。其当前唯一调用点（RightPanel TaskSummary「开始人工处理」按钮）随右栏替换而消失，BackgroundTaskCenter 使用自己的导航函数，不受影响。
- 返回列表 → 新增 `closeTask()`：`apply({ taskId: null, targetType: null, targetId: null })`。
- **进入详情自动选中队列首位**：items 加载完成后，若 `state.targetType/targetId` 不在本任务未完成 items 中，则 `openTarget(首位.type, 首位.id, 'tasks')`。该行为同时抵消嵌入的候选组件「target 与 URL 不符时回写 `openTarget(..., 'candidates')`」把 module 切走的副作用。

### R6 刷新时机

- 进入详情视图时；从审核/晋升模块切回佐证任务时（hashchange 重进详情自然触发）；手动「刷新」按钮。不做轮询。

### R7 回退重新审查（后端新增端点）

- **端点**：`POST /api/ontology/evidence/batch/{task_id}/items/{item_id}/reopen`，权限 `require_role("reviewer")`，ValueError → 400（INVALID_REQUEST）。模式对齐既有 `/items/{item_id}/reviewed` 端点。
- **服务**：`reopen_batch_item(session, task_id, item_id)`：
  - 守卫：item 必须存在且 `status='completed'`，否则 `ValueError("item is not completed")`。
  - `UPDATE paper_evidence_task_items SET status='awaiting_review', reviewed_by=NULL, reviewed_at=NULL, evidence_id=NULL, updated_at=now() WHERE task_id=... AND id=... AND status='completed'`。
  - 随后 `_update_task_totals` + `_update_task_review_status`（与 complete 流程对称）。
  - 返回 `{task_id, item_id, status: 'awaiting_review'}`。
- **语义边界**：仅回退 item 状态；已写入的 `paper_evidence` 记录不撤销（留痕），重新审核晋升时按现有流程产生新记录。
- **前端**：`endpoints.ts` 新增 `reopenPaperEvidenceTaskItem(taskId, itemId)`。

## 5. 文件改动清单（严格限定）

| 文件 | 改动 |
|---|---|
| `frontend/src/pages/evidence-center/modules/EvidenceTasksModule.tsx` | 重写：双视图（列表 ⇄ 详情）+ 自动选中首位；移除向 Context 注册 taskSummary/taskSummaryActions 的旧逻辑（右栏不再渲染 TaskSummary） |
| `frontend/src/pages/evidence-center/components/TaskItemQueue.tsx` | 新建：右栏队列 + 筛选 |
| `frontend/src/pages/evidence-center/components/TaskListPanel.tsx` | 顶部加「← 任务列表」返回按钮 |
| `frontend/src/pages/evidence-center/EvidenceCenterPage.tsx` | 全宽条件扩展（tasks 无 taskId）；tasks 详情三栏壳不变 |
| `frontend/src/pages/evidence-center/components/RightPanel.tsx` | 仅 tasks 分支：TaskSummary → TaskItemQueue |
| `frontend/src/pages/evidence-center/EvidenceCenterContext.tsx` | `openTask` module 改 'tasks'；新增 `closeTask` |
| `frontend/src/styles.css` | 任务卡片网格 + 队列样式（沿用 evidence-* 视觉语言） |
| `frontend/src/pages/evidence-center/modules/EvidenceTasksModule.test.tsx` | 重写（见 §7） |
| `frontend/src/pages/evidence-center/EvidenceCenterPage.test.tsx` | 仅更新 tasks 布局断言 |
| `frontend/src/api/endpoints.ts` | 新增 `reopenPaperEvidenceTaskItem` |
| `backend/app/services/paper_evidence_service.py` | 新增 `reopen_batch_item`（对称 complete_batch_item_reviewed） |
| `backend/app/routers/ontology.py` | 新增 `/evidence/batch/{task_id}/items/{item_id}/reopen` 端点 |
| `backend/tests/test_paper_evidence*.py` | 新增回退端点测试（成功/非 completed 拒绝/不存在 item） |

**不碰**：`EvidenceCandidatesModule` / `EvidenceReviewModule` / `EvidencePromotionModule` / `ValidationWorkbench` / 验证中心其他 tab / 后端。

## 6. 边界与错误处理

| 场景 | 行为 |
|---|---|
| items 接口失败 | 队列区错误 + 重试按钮，主区不受影响 |
| 任务 items 全部完成 | 队列空态「全部处理完成」 |
| 筛选后无匹配 | 「该类型下暂无待处理对象」 |
| 任务已完成/失败 | 仍可进详情查看（队列通常为空） |
| 队列 > 200 条 | 按优先级排序后截断 + 提示 |
| 置信度 null | 排最前 + 显示「—」 |
| 任务列表加载失败 | 错误 + 重试（沿用现有模式） |
| 回退非 completed item | 后端 400 INVALID_REQUEST，前端提示错误 |
| 回退接口失败 | 队列不变，显示错误提示 |
| 回退成功后队列刷新 | 对象回到待处理区按置信度重排，已完成区移除该条 |

## 7. 测试计划

`EvidenceTasksModule.test.tsx` 重写（RTL + mock endpoints，行为导向）：

1. 列表视图渲染任务卡片（名称/类型/进度/待审），进行中任务排最前
2. 空任务列表 → 空态 + 创建 CTA
3. 点击卡片 → 详情视图：items 拉取、队列渲染、自动选中首位（openTarget 以 tasks 调用）
4. 队列排序：置信度升序、null 最前
5. 筛选：回路（含 circuit_function）/连接/功能 分组过滤正确
6. 点击队列项 → openTarget(type, id, 'tasks')，URL module 保持 tasks
7. 全部完成 → 待处理区空态「全部处理完成」+ 已完成区展示
8. items 失败 → 错误 + 重试
9. 返回列表 → 回到卡片网格
10. 已完成区：折叠/展开、按完成时间倒序、点击「回退重新审查」→ 二次确认 → 调 reopen 接口 → 队列刷新、对象回到待处理区
11. 回退失败（接口报错）→ 错误提示、队列不变

后端测试（`backend/tests/test_paper_evidence*.py`）：

- `reopen` 成功：completed → awaiting_review，reviewed_at/reviewed_by/evidence_id 清空，task totals 与 review_status 更新
- `reopen` 非 completed item → ValueError → 400
- `reopen` 不存在的 item → 400

`EvidenceCenterPage.test.tsx`：仅更新 tasks 布局断言（列表全宽 / 详情右栏为队列）；其他模块断言不动。

## 8. 验收标准

- 佐证任务相关前端测试全绿；其他模块既有的 17 个失败测试保持原状（本次范围外，不新增不修复）。
- 后端 `pytest tests/test_paper_evidence*.py` 全绿（含新增 reopen 测试）。
- `npx tsc --noEmit` 0 错误；`npm run build` 通过。
- 手动走查：创建/进入任务 → 队列按置信度排序 → 筛选三组 → 点对象进工作区 → 处理 → 返回列表；已完成区回退 → 对象回到待处理区。
