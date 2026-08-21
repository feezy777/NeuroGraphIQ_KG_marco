# 验证中心—佐证任务 第二轮定向排查报告（只读，2026-08-14）

> 方法：全仓库 grep + 运行中后端真实 API 请求 + 只读 SQL（SELECT，无 UPDATE/INSERT/DELETE）+ 前端状态机代码推导（本环境无浏览器，DOM/控制台项标注为「无法验证」）。所有结论带文件行号或实测数据。

---

## 1. confidence=0.0 语义结论

### 1.1 写入来源（全仓库）

| 位置 | 行为 | 证据 |
|---|---|---|
| `mirror_region_connections.confidence` 列定义 | `NUMERIC` **可空、无 DEFAULT** → 未传即 NULL | `backend/migrations/022_mirror_kg_schema.sql:30`；模型 `backend/app/models/mirror_kg.py:73` 同 |
| LLM 回路连接提取创建行 | `confidence=confidence`（LLM 判定值，可为 None） | `backend/app/services/llm_circuit_connection_extraction_service.py:150-163` |
| mirror 服务创建/合并 | payload 透传；合并比较用 `or 0.0`（**仅比较，不落库**） | `backend/app/services/mirror_kg_service.py:344-360` |
| 字段补全（canonical resolver） | **主动写 0.0**：resolver 未解析成功时 `confidence=0.0`；`float(resolution.get("confidence") or 0.0)` 把缺失转 0.0 后**写入 mirror 行** | `backend/app/services/canonical_region_resolver.py:152,424`；`backend/app/services/field_completion_execution.py:128,137,146,655` |
| `paper_evidence_task_items.current_confidence` | **当前运行代码（工作树）在物化流程中硬编码 `conf=None` 插入**（见 §2）；HEAD 版只在创建时快照镜像行 confidence（2667/5062）；全流程无 UPDATE | `paper_evidence_service.py:_materialize_page` 插入段；grep 证实 |
| `PaperEvidenceTaskItem.confidence`（论文级） | 预处理期间 LLM 方向置信度（2445/2469/2835 写 `confidence=:conf`） | `paper_evidence_service.py:2445,2469,2835` |
| review 评分 | `reviewer_confidence: float ge=0 le=1`（schema 强制 ≥0）| `backend/app/schemas/ontology.py:364` |
| 晋升/审核/回退 | 审核 approve/promote 只更新 reviews 表；回退（rollback_evidence）把证据记录置 invalidated，**均不改置信度字段** | `paper_evidence_service.py:5604,5693,1270` |

### 1.2 数据库统计（只读，按镜像表分组）

| 表 | 总数 | NULL | =0 | 0<x<0.5 | ≥0.5 |
|---|---|---|---|---|---|
| mirror_region_connections | 70029 | **100** | **109** | 63175 | 6645 |
| mirror_region_circuits | 53562 | 0 | 10 | 49364 | 4188 |
| mirror_region_functions | 142 | 0 | 0 | 14 | 128 |
| mirror_projection_functions | 13341 | 0 | 4 | 12976 | 361 |
| mirror_circuit_functions | 100627 | 0 | 0 | 85395 | 15232 |
| mirror_circuit_steps | 103880 | 4 | 0 | 87346 | 16530 |

**confidence=0 样本（connections）**：8/8 条均带 `uncertainty_reason`（如 "Atypical projection; low confidence."、"Very low likelihood; included for completeness."、"No evidence."），`mirror_status=llm_suggested`、`review_status=pending`、`granularity_level=molecular_attr`、`source_atlas=Allen_HBA_2012`、`updated_at` 均为 2026-07-21。

### 1.3 结论（逐条回答）

1. **DB 默认值 = NULL**（可空无 DEFAULT）。已确认。
2. 创建 mirror 行未传 confidence → **保存 NULL**。已确认（DDL + 100 条 NULL 实证）。
3. 主动写 0.0 的代码：canonical resolver 未解析兜底（`canonical_region_resolver.py:152/424`）、字段补全默认 0.0（`field_completion_execution.py:128`）。已确认。
4. null→0.0 转换：`float(x.get("confidence") or 0.0)`（field_completion 137/146）→ **落库**；`float(existing.confidence or 0)`（连接竞争比较 171、合并 344+）→ 仅比较。已确认。
5. 0.0 参与低置信筛选：`_resolve_scope_ids_low_confidence` SQL 为 `WHERE confidence < :thr ORDER BY confidence ASC`（`paper_evidence_service.py:4791-4808`）→ **0.0 入选且排最前；NULL 被排除**。已确认。
6. 三个概念（未评分/无证据/明确低置信）**存在**：未评分=confidence NULL；无证据=连接级 `uncertainty_reason`（如 "No evidence."）或对象级 `preprocess_outcome='no_evidence_found'`；明确低置信=confidence 0.0 + uncertainty_reason。已确认。
7. 区分字段：mirror_region_connections 有 `uncertainty_reason` 文本列（`022_mirror_kg_schema.sql:31`）——**是当前唯一可区分 0.0 语义的字段**（resolver 写入的 0.0 不带该字段）。已确认。
8. `confidence_lt` 对 null/0 的实际处理：null 被 SQL 排除（不当作低置信）；0 被选中。已确认。

**最终判断（已确认为主）**：`0.0` 在 mirror_region_connections 上 = **LLM 明确判定的低置信度**（有 uncertainty_reason 佐证），不是未评分缺省；未评分以 **NULL** 表达。但字段补全/resolver 也会落 0.0（语义=未解析兜底），两者值上无法区分，只能靠 uncertainty_reason 有无。

---

## 2. 名称/置信度生命周期（target 4bd7092b-… 实测）

时间轴（全部来自只读 SQL + 运行中后端）：

1. **2026-07-14 11:22** mirror 行创建（Allen_HBA_2012，molecular_attr，llm_suggested）。
2. **2026-07-21 19:57** mirror 行更新：此时已有真实名称 `Somatosensory areas, layer 4 / Primary somatosensory area, nose, layer 1`、`confidence=0`、`uncertainty_reason="Atypical projection; low confidence."`。
3. **2026-08-07 17:13** 任务 00e4bf49 创建，task item 同时创建——**label 存的是 UUID 字符串、current_confidence=NULL**。

**根因（已确认，比第一轮更精确）**：不是"快照过期"，而是**当前运行中的后端（工作树版本）的物化流程根本不查镜像行**：

- 路由创建任务后调度 `materialize_task_items_background`（`backend/app/routers/ontology.py:1002-1004`）。
- `_materialize_page` 插入 items 时 **硬编码 `"lbl": str(oid), "conf": None`**（`backend/app/services/paper_evidence_service.py` `_materialize_page` 的 INSERT 段：`SELECT CAST(:tid AS uuid), CAST(:tt AS varchar), t.id, CAST(:lbl AS varchar), :conf, 'pending'`，参数 `{"lbl": str(oid), "conf": None}`）。
- 实测：DB 中 117 条 label==target_id、2 条真实 label；115 条 item 的 current_confidence 全部 NULL。
- 镜像行在任务创建**之前**就已有名称和置信度——代码没有读取它们。

**补充确认**：任务创建同时进行的 `_batch_scope_label` 路径（HEAD 逻辑，2666 插入段）对**新建任务仍然有效**（会取到真实名称）——但运行中的 morning 版本创建任务本身只插 `(task_id, target_type, target_id)`（2339-2372 的旧 create 版本被文件后部同名函数覆盖，且 items 实际由物化流程插入）。**结论：存量 117 条 UUID 是物化流程硬编码 lbl 造成的；修复需改物化插入或回填。**

---

## 3. 数据读取方案比较（A 回填快照 / B 实时关联 / C 并存）

| 维度 | A 修改存量快照 | B 列表实时 JOIN mirror | **C 快照+live 并存（推荐）** |
|---|---|---|---|
| 审计可追溯 | 差：历史值被覆盖 | 中：需另行保留快照 | **好：label/current_confidence 保持不动，live_* 新增** |
| 存量修复 | 需要一次性回填端点 | 自动（每次读取即最新） | 自动（live 字段）+ 可选回填 |
| 性能 | 无额外成本 | 每任务一次批量 JOIN（7 张表按 target_type 分表关联，无 N+1） | 同 B，+ 2 个字段 |
| N+1 风险 | 无 | 批量 JOIN 无 N+1 | 无 |
| 数据删除兜底 | 快照仍在（优点） | 行删除后 live 为空 → 前端回退快照/中文兜底 | **最好：live 缺失回退快照，再回退「类型中文#短ID」** |
| 前后端兼容 | 无协议变化 | 响应加字段，兼容 | 响应加字段，兼容 |
| 实现复杂度 | 低（端点+脚本） | 中（list_batch_items 按 7 类型 JOIN） | 中（B + 前端切换两行） |

**推荐 C**：列表接口为每个 item 附 `live_display_name`（镜像行实时名称拼接）与 `live_confidence`（镜像行实时置信度，0 原样返回）；前端展示优先 live、缺失回退快照 label、再回退中文兜底。回填（A）可作为一次性存量治理单独做，非必选。

---

## 4. 点击问题复现矩阵（运行时 API + 状态机推导；无浏览器，DOM/控制台项无法验证）

前置事实（代码确认）：
- **嵌入模式（验证中心）下 `apply()` 不写 URL**（`EvidenceCenterContext.tsx:139-149`：`if (!embedded) { window.location.hash = url }`）→ 页面内任何点击**不改变 URL**，刷新后 `parseEmbeddedUrl` 重置回 `module='tasks', taskId=null` → **选中对象/任务状态刷新即丢失**。
- 非嵌入（`#/evidence-center`）下 URL 会同步（module=tasks 为默认省略）。

| # | 入口 | 数据类 | 点击前 URL | 点击后 URL | getEvidenceTarget | 页面模块 | 根因判定 |
|---|---|---|---|---|---|---|---|
| 1 | 左栏待处理卡 | 镜像行存在（4bd7092b） | `#/validation-center?tab=paper_evidence` | **不变**（嵌入不写 URL） | 200，完整 DTO（真实名+conf 0.0） | tasks 模块 targetResolved→候选工作区（state 内正确） | ✅ 进入工作区；但刷新丢失状态 |
| 2 | 左栏待处理卡 | 镜像行缺失（0ad8173b） | 同上 | 不变 | **HTTP 400 `target not found`**（实测） | 工作区 DTO=null 空态 | ⚠️「没进去」= 请求失败+静默空态 |
| 3 | 右栏已处理卡 | 有 review、行存在（1910140e） | 同上 | 不变 | 200（右丘脑本体·右壳核） | 候选工作区 ✓ | ✅ 正常 |
| 4 | 中栏任务卡 | 任意任务 | 同上 | 不变 | 不触发（仅 openTask 清 target） | 中栏任务卡选中态+左栏过滤 | ✅ 正常；刷新丢失选中 |
| 5 | 数据中心「论文佐证」 | selected 行 | `#/data-center` | `#/validation-center?tab=paper_evidence&module=candidates&task_id=&target_*`（`MirrorKgPanel.tsx:287-292`） | 200/400 视行而定 | **candidates 模块**（非佐证任务页） | ✅ 符合既定产品方向 |

**「没有跳转」的最终判定**：最可能 = ②③⑤ 的组合——嵌入模式 URL 无变化（看起来像没跳转）+ 镜像行缺失时 400→静默空态（真的没进去）+ 数据中心入口落在 candidates 模块。已确认。

---

## 5. review—task 关联链路

1. 创建方：审核模块 `EvidenceReviewModule.tsx:341-356` 调 `buildReview`，**payload 里带 `task_id` 与 `task_item_id`**（`task_id: state.taskId ?? null`、`task_item_id: taskItem?.taskItemId ?? null`；queue 条目确有 taskItemId，`EvidenceCandidatesModule.tsx:141`）。
2. 后端 schema 支持两字段（`EvidenceReviewBuildRequest`，`backend/app/schemas/ontology.py:356-357`）。
3. 实测 15/15 条 review 的 task_id/task_item_id 为 **NULL** —— 因为当时 `state.taskId` 为 null（数据中心 handoff 写 `{items, taskId: null}`，`MirrorKgPanel.tsx:281`）且未从队列找到条目 → **前端有字段可传，但运行时值为 null**。已确认。
4. 模型/迁移支持两列（reviews 表 task_id/task_item_id 可空）。
5. item 仍 awaiting_review 而 review 已 approved/promoted：**approve_review/promote_review 只更新 reviews 表**（`paper_evidence_service.py:5604/5693`，UPDATE 仅 reviews），从不更新 task item；唯一的 item 完成路径是晋升模块前端调 `completePaperEvidenceTaskItem`（仅在 state.taskId 存在时触发）。已确认。
6. 审核完成后是否应同步 task item：现状否（断点明确）。
7. 右栏关联方式：**临时关联**（`TaskProcessedPanel.tsx` 按 `target_type|target_id` 建 Map），无正式外键；reviews 表虽有 task_item_id 列但未使用。已确认。
8. 同 target 多版本：实测 1910140e 有 1 个 task item + **2 条 review**（approved/awaiting_promotion → approved/promoted，08-13 先后创建）；同 target 多任务多 item 也普遍（DB 分组查询证实）。已确认。
9. 仅按 target_type+target_id 回退 → **会歧义**：无法确定回退哪个任务版本、哪次审核。需以 review id（或 task_item_id 补链）为回退主体。已确认。

---

## 6. 回退能力差距（「审核通过后回退并重新评分」）

现有能力盘点：

| 能力 | 现状 | 证据 |
|---|---|---|
| reopen task item | 仅 `status='completed'` 的 item → awaiting_review；清 reviewed_* 与 evidence_id；**不支持 awaiting_review、不碰 review** | `paper_evidence_service.py:3925-3950` |
| retry failed | 任务级重试失败 items | `retry_failed_batch_items:3649` |
| review 状态变更 | approve(5604)/reject(1391 路由)；reject 后 review_status=rejected | 同上 |
| promotion rollback | `rollback_evidence`（证据记录→invalidated，留痕） | `paper_evidence_service.py:1270-1332` |
| rescore | 无独立接口；只能重新 build review（新行） | `build_review` 每次 INSERT 新行 |
| 版本/历史 | review 多行并存但**无版本链/无 active 标记**；无覆盖删除 | reviews 表结构 + 实测 2 行同 target |

**结论**：现有 reopen **不能**安全支撑「审核通过后回退并重新评分」：
- 对已 promoted 的对象，reopen 直接 400（item 是 awaiting_review）。
- 回退主体错位：应围绕 review（保留旧行、新建重评行），而非 item 状态。
- 缺失清单（不设计迁移/接口，仅列出）：(1) review 级「回退重评」操作（旧 review 置 superseded/保留，新 review 重开）；(2) review 与 task_item 的稳定关联（补 task_item_id）；(3) 版本排序（created_at 已有，缺 active/current 标记语义）；(4) 重评入口能复用旧 claim/候选快照。

---

## 7. 分页与数量一致性

1. 左栏「全部 N」「回路/连接/功能计数」= **已加载子集的过滤计数**（`TaskPendingQueue.tsx` chips 用 `unfinished.filter(...)` 计数），**不是后端真实总数**。已确认。
2. items 响应**无 total 字段**（`list_batch_items` 只返回 items，实测响应也无 total）；无 offset/page/cursor 前端使用。已确认。
3. 服务端 `ORDER BY created_at LIMIT 50 默认`（`ontology.py:1109`、`list_batch_items` 3834-3839），前端取 100 → 实测任务 00e4bf49 共 115 条全未完成 → **漏 15 条（created_at 最新 15 条）**。
4. 「仅显示前 100 条(按优先级截断)」提示**语义不成立**：服务端按创建时间截断，前端才按置信度排序 → 被截掉的是最新对象，可能与置信度优先级无关。
5. 无按任务分项的聚合端点可复用；`paper_evidence_stats`（router 1207）只按 target_types 汇总。
6. 多任务全局：每任务各自 limit 100，合计截断。
7. 遗漏对象是否可能恰为最低置信度：**可能**（截断与置信度无关；当前全 null 无感，回填后即暴露）。已确认（推导）。

---

## 8. 下一步可实施范围（一个提交，不含代码）

建议单次提交（前后端 + 测试）：
1. **后端 `list_batch_items` 增强**：批量 JOIN 各镜像表（按 target_type 分表），返回 `live_display_name`/`live_confidence`（0 原样）+ `total`；**不改快照列**。
2. **后端 `_materialize_page` 修复**：插入时按 `_batch_scope_label` 逻辑解析 label/current_confidence（不再硬编码 UUID/None）——防新增数据继续坏。
3. **前端**：左栏/右栏/中栏展示优先 live 字段、回退快照、再回退中文兜底；筛选计数旁标注「已加载 N / 总 M」；「前 100 条」提示改为真实语义。
4. **任务卡状态主操作**（产品方向 #3）：进行中→继续验证（进入该任务）/部分失败→重试失败/已完成→查看审核;接线 pause/retry-failed。
5. **嵌入模式 URL 同步**：`apply()` 在 embedded 下也写 URL（保留 tab 参数）→ 刷新可恢复任务/对象选中（修复 §4 刷新丢失）。
6. **测试**：后端 items live 字段（行存在/缺失/0 置信度）+ total；前端回填展示、计数一致性、嵌入 URL 同步；既有 240+52 全绿。

独立后续（第二提交起）：review 级回退重评（§6 缺口）、存量回填端点、review-task_item 补链。

---

## 9. 仍需用户决定的问题（无法由代码/数据验证解决）

1. **回退重评的对象主体**：按「review 行」（保留旧行新建重评）还是「task item」（状态回退）？两者并存时需要定义优先级与 UI 入口。
2. **左栏未评分（confidence NULL）对象的处理**：产品方向说「未评分不能自动等同低置信」，但当前排序把 null 排最前——是保留现状（null 最前提示未评分）还是把未评分单独分组/排除？
3. **任务卡「继续验证」的落地视图**：进入该任务的对象列表（左栏过滤）还是直接打开最低置信度对象的工作区？
4. **「前 100 条」截断的产品期望**：改为服务端按置信度排序+分页（需要后端改动），还是接受按创建时间截断并明确提示？

---

## 附：只读性自检

- 本轮未修改任何仓库文件（代码/配置/迁移/测试）。
- DB 仅执行 SELECT（统计、样本、时间线、关联查询），无 UPDATE/INSERT/DELETE。
- 运行中后端仅被 GET 请求（未触发任何写操作端点）。
- `git diff --stat` 见下（应与上一轮结束时一致）。
