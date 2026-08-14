# 佐证任务页面重设计（PRD + 设计）· V2 修订

- **日期**: 2026-08-14（V2 修订;V1 于 2026-08-13 初版后按用户反馈重设计）
- **状态**: V2 已与用户逐项确认（结构/队列范围/取数方式/点击行为）
- **分支**: `codex/ontology-evidence`
- **V1 遗留**: V1 的提交 57d7831..dfd8755 已包含可复用的基础设施（见 §5 复用清单）

---

## 1. 背景与问题（V2 修订动机）

V1 实现为「两页结构」：任务列表全宽页 → 点击进详情页（左任务列表 + 主区候选工作区 + 右栏队列）。用户验收时反馈与预期不符：

1. 列表页隐藏左右栏 → 看不到置信度队列，只见任务卡片，感知「没按置信度筛选」；
2. 预期是**复用证据佐证（证据候选）的三栏结构**——队列常驻右栏，而非藏在详情页里。

V2 重设计为**单页三栏**：中栏任务卡片 ⇄ 对象卡片 ⇄ 就地嵌入候选工作区；右栏置信度队列**常驻**（未选任务时是跨任务全局队列）。

## 2. 目标

1. **单页三栏**：左栏验证事实（Claim），中栏任务/对象卡片与就地证据工作区，右栏常驻置信度队列。
2. **全局队列**：未选任务时，右栏展示所有进行中任务的未完成对象（置信度升序优先级）；选中任务后过滤为该任务。
3. **就地处理**：点队列项/对象卡片 → 中栏就地嵌入现有证据候选工作区（复用 EvidenceCandidatesModule，不离开本页）。
4. **筛选与回退**：回路/连接/功能筛选、已完成折叠区两步回退重审（沿用 V1 已交付能力）。

## 3. 非目标

- 不改动 EvidenceCandidatesModule / EvidenceReviewModule / EvidencePromotionModule 的内容（仅嵌入复用）。
- 不改动 ValidationWorkbench 与验证中心其他 tab（工作树既有未提交改动保留原样）。
- 后端无改动（V1 的 reopen 端点已交付）。
- 不做队列轮询、不做对象卡片分页。

## 4. 需求明细

### R1 页面骨架（单页三栏,始终显示）

- 佐证任务页始终三栏（**移除 V1 的全宽列表视图与详情页切换**）：
  - 左栏 = Claim 面板（`ClaimSummaryPanel`,选中对象时由嵌入候选模块推送显示;未选中时占位提示）。
  - 中栏 = 三态内容（见 R2）。
  - 右栏 = 常驻 `TaskItemQueue`（见 R3）。
- 移除 `TaskListPanel` 左栏任务列表组件（任务列表由中栏卡片承担）。

### R2 中栏三态

**态 ① 任务卡片网格**（无 taskId）：
- 复用 V1 的 TaskCard:名称/目标类型/状态徽章（进行中高亮）/已处理 X/总数 Y/待审核 Z（警示色）/失败数（>0 才显示）/创建时间;排序 = 进行中 → 有等待审核 → 其他,同组创建时间倒序。
- 当前选中任务卡片高亮（选中态样式）。
- 空态 + 创建 CTA;工具栏:「创建批量预处理」「刷新」。

**态 ② 任务对象卡片**（有 taskId,未选中对象）：
- 该任务全部 items 渲染为卡片（复用 evidence-conn-card 样式）:名称/类型/置信度大字/状态 chip;排序 = 未完成优先 + 置信度升序,已完成/失败排后。
- 点击任一对象卡片 → 态 ③（打开该对象工作区）。
- 工具栏:显示「← 任务列表」返回按钮（closeTask）+ 任务名 + 进度摘要。

**态 ③ 就地证据工作区**（有 taskId + target 解析）：
- 中栏渲染嵌入的 `EvidenceCandidatesModule`（不改其代码）。
- 保留 V1 的 `targetResolved` 门控（URL target 必须解析为本任务某个 item 才挂载候选组件,防其「target 不符则回写 module=candidates」副作用切走页面）。
- 全部完成且无 target 时:中栏显示「全部处理完成」空态（失败数 >0 时文案区分,同 V1 终审修复）。

**选中任务自动选中**:进入态 ② 时（点任务卡片或深链带 task_id）,自动 `openTarget(该任务未完成对象中置信度最低, 'tasks')` → 直接进入态 ③。该任务全部完成时不自动选中,停留在态 ②。

### R3 右栏常驻队列（V1 组件扩展）

- **全局模式**（无 taskId）:并行拉取所有**进行中**（pending/running/paused）任务的 items（每任务 `limit 100`）,合并去重后按置信度升序（null 最前）展示;条目卡片附加所属任务名徽章（区分来源）。
- **任务模式**（有 taskId）:只拉该任务 items,行为同 V1。
- 两种模式共享:回路/连接/功能筛选 chips（带计数,只作用待处理区）、未完成集合过滤、>100 条截断提示、已完成折叠区（updated_at 倒序 + 两步确认回退重审 + 失败提示）、加载失败错误+重试、陈旧响应守卫（latestTaskIdRef 模式,V1 终审修复保留）。
- 点击队列项 → `openTarget(type, id, 'tasks')`,中栏切态 ③,队列项高亮当前对象。

### R4 筛选分组映射（沿用 V1）

| 分组 | target_type |
|---|---|
| 回路 | circuit, circuit_step, circuit_function |
| 连接 | connection, projection |
| 功能 | region_function, projection_function |
| 其他类型 | 仅「全部」下可见 |

### R5 导航与 URL

- 未选任务:`#/validation-center?tab=paper_evidence` 或 `#/evidence-center?module=tasks`。
- 选中任务/对象:`…&task_id=X&target_type=T&target_id=I`（复用现有参数与 parse/buildEvidenceUrl;buildEvidenceUrl 省略默认 module=tasks 属预期,测试不检查该字符串）。
- `openTask` = 选中任务（清 target,module 'tasks'）;`closeTask` = 回任务卡片网格（清 taskId+target）;`openTarget(type, id, 'tasks')` = 态 ③。
- 自动选中 effect:deps 不含 state.targetType/targetId（V1 终审修复:防回退重审后点击被旧快照抢回）。

### R6 刷新时机

- 进入页面、切换任务/对象时;手动「刷新」按钮（队列与中栏各自）;回退成功后队列自动刷新。不做轮询。

### R7 回退重新审查（沿用 V1 已交付）

- 后端 `POST /api/ontology/evidence/batch/{task_id}/items/{item_id}/reopen`（已完成）;前端两步确认回退（已完成）。

## 5. 文件改动清单（V2 增量）

**复用（V1 已提交,不重做）**:`taskItemQueueUtils.ts(+test)`、`taskStatus.ts` 排序工具、reopen 后端端点、`reopenPaperEvidenceTaskItem` wrapper、已完成区回退逻辑、`closeTask`、reopen 相关后端测试。

| 文件 | 改动 |
|---|---|
| `modules/EvidenceTasksModule.tsx` | 重写:中栏三态（任务卡 ⇄ 对象卡 ⇄ 嵌入工作区）+ 自动选中 + 返回按钮 |
| `components/TaskItemQueue.tsx` | 扩展:全局模式（并行拉取进行中任务 items 合并）+ 任务过滤 + 任务名徽章 |
| `components/TaskListPanel.tsx` | **删除**（被中栏卡片取代） |
| `EvidenceCenterPage.tsx` | 移除 tasks 全宽条件（`isTasksList`）;左栏 tasks 分支 TaskListPanel → ClaimSummaryPanel |
| `modules/EvidenceTasksModule.test.tsx` | 重写（三态行为用例） |
| `components/TaskItemQueue.test.tsx` | 追加全局模式/任务过滤用例 |
| `EvidenceCenterPage.test.tsx` | 更新 tasks 布局断言（三栏常显） |
| `styles.css` | 追加:对象卡片选中态/任务名徽章/中栏返回条样式 |

**不碰**:候选/审核/晋升模块、ValidationWorkbench、验证中心其他 tab、后端。

## 6. 边界与错误处理（V1 全部保留 + 新增）

| 场景 | 行为 |
|---|---|
| 全局队列部分任务 items 拉取失败 | 失败的任务跳过,队列展示其余;全部失败时错误+重试 |
| 队列 > 100 条（每任务截断） | 提示「仅显示前 100 条（按优先级截断）」 |
| 选中任务全部完成 | 中栏态 ②,不自动选中;右栏该任务过滤后空态「全部处理完成」+ 已完成区可回退 |
| 置信度 null | 排最前 + 显示「—」 |
| 回退非 completed / 接口失败 | 后端 400 / 前端错误提示、队列不变（V1 已交付） |
| 切换任务时 items 乱序返回 | 陈旧响应守卫丢弃（V1 终审修复,队列与中栏都保留） |

## 7. 测试计划

`EvidenceTasksModule.test.tsx` 重写:
1. 无 taskId:任务卡片网格渲染 + 进行中置顶排序 + 空态 CTA + 加载失败重试（沿用 V1 用例）
2. 点任务卡片 → 中栏态 ②③:对象卡片渲染（未完成优先+置信度升序）+ 自动选中置信度最低对象（URL 带 target）
3. 选中任务全部完成 → 不自动选中（URL 无 target）,中栏空态
4. 点对象卡片 → 态 ③（targetResolved 门控挂载候选组件）
5. 「← 任务列表」→ 回任务卡片网格（URL 无 task_id）

`TaskItemQueue.test.tsx` 追加:
6. 全局模式:未选任务时并行拉取进行中任务 items、合并置信度升序、条目带任务名徽章
7. 任务模式:选中任务后只拉该任务 items（沿用现有用例）
8. 单任务 items 拉取失败不影响其他任务（跳过并展示其余）

`EvidenceCenterPage.test.tsx`:tasks 三栏常显断言（左栏 Claim 面板、右栏队列）。

## 8. 验收标准

- 佐证任务相关前端测试全绿;其他模块既有失败测试保持原状（基线不变）。
- `npx tsc --noEmit` 0 错误;`npm run build` 通过。
- 后端 pytest 52 passed（reopen 相关保持）。
- 手动走查:进入页即见右栏全局置信度队列 → 点任务 → 中栏对象+自动打开最低置信度工作区 → 筛选三组 → 回退重审 → 返回任务列表。
