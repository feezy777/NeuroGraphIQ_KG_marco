# 验证中心—佐证任务 数据链路审计（只读分析，2026-08-14）

> 本报告所有结论均引用仓库具体代码位置；实测数据来自本地运行中的后端（127.0.0.1:8002）。已确认/待确认逐条标注。

---

## 1. 完整数据流（创建 → 展示 → 点击）

### 1.1 创建任务

1. 入口：数据中心 Mirror KG 面板「论文佐证」按钮 → `onPaperEvidence(rows)`（`frontend/src/pages/data-center/MirrorKgPanel.tsx:270-294`）：把选中行映射为 `EvidenceQueueHandoffItem`（`target_type`=映射类型或 `'connection'`，`target_id = String(r.id)` 即镜像表行 ID），写入 `sessionStorage['evidence-center.initial-queue']`，然后跳转 `#/validation-center?tab=paper_evidence&module=candidates&target_type=…&target_id=…`。
2. 佐证任务页工具栏「创建批量预处理」→ `CreateBatchTaskDialog`（`frontend/src/pages/evidence-center/components/CreateBatchTaskDialog.tsx:49-78`）→ `createPaperEvidenceBatch(body)`（`frontend/src/api/endpoints.ts:5673-5690`）→ `POST /api/ontology/evidence/batch`（`backend/app/routers/ontology.py:975`）。
   - body 字段：`target_type, scope(selected|low_confidence), mode, max_papers_per_object, limit, name, granularity_level, only_oa, confidence_lt, stop_after_strong_support, target_ids, filter_snapshot`。
3. 后端 `create_batch_task`（`backend/app/services/paper_evidence_service.py:2575-2685`）：
   - `_resolve_scope_ids`（2562-2590 附近）按 scope 从镜像表（`TARGET_MODELS`，见 `evidence_target_adapter.py:30-38`：connection/projection→`mirror_region_connections`，circuit→`mirror_region_circuits`，等）取行 ID；`selected` 直接使用前端传入的 target_ids。
   - 对每个 target 调 `_batch_scope_label`（2575-2595）生成 **label + confidence 快照**：`_name_parts`（586-604）从镜像行取名称字段（connection：`source_region_name_en · target_region_name_en · connection_type`；circuit：`circuit_name · circuit_type`；等），**名称字段缺失时回退 `target_id`（UUID）**；`conf = float(row.confidence) if row.confidence is not None else None`。
   - `INSERT paper_evidence_tasks`（status=`pending`/`paused`）+ `INSERT paper_evidence_task_items (task_id, target_type, target_id, label, current_confidence, status='pending')`（2667-2685）。
4. 后台循环 `execute_paper_evidence_batch_background` 处理对象（搜索/检索/LLM 验证），结束时任务级 status 由对象状态统计推导：`partially_failed`/`failed`/`completed`（3490-3512）；但**对象级 `current_confidence` 全程无 UPDATE**（全文件仅 INSERT 处写 2667/5062，grep 证实）。

### 1.2 页面展示

1. 路由：侧栏「验证中心」→ `#/validation-center`（`frontend/src/layout/WorkbenchLayout.tsx:32`）；`App.tsx:40/48`：`/evidence-center` → `EvidenceCenterRedirect`（19-23，重定向到 `#/validation-center?tab=paper_evidence`），`/validation-center` → `ValidationCenterPage` → `ValidationWorkbench` → `<EvidenceCenterPage embedded />`。
2. 嵌入 provider 解析 URL（`EvidenceCenterContext.tsx:83-97`）：要求 `tab=paper_evidence`，否则回退默认 `module='tasks', taskId=null`。
3. 共享取数 hook `useEvidenceTaskItems`（`components/useEvidenceTaskItems.ts`）：
   - 1 次 `listPaperEvidenceTasks({limit:200})`（任务列表）+ 对每个「非取消且有对象」任务并行 `listPaperEvidenceTaskItems(id,{limit:100})`（N+1 并行，实测 7 个任务）。
   - 任务模式（有 taskId）只拉该任务 items；含陈旧响应守卫。
4. 三栏渲染（`EvidenceCenterPage.tsx:88-128` + `modules/EvidenceTasksModule.tsx` + `components/TaskPendingQueue.tsx` + `components/TaskProcessedPanel.tsx`）：
   - 左栏 `TaskPendingQueue`：未完成对象，`current_confidence` 升序、null 最前（`taskItemQueueUtils.ts:sortByConfidenceAsc`，`ca == null` 判定——0 值安全）；筛选 chips。
   - 中栏 `EvidenceTasksModule`：任务卡片（V5 统一状态 `deriveTaskWorkStatus`，由对象状态推导：进行中/待审核/部分失败/已完成，见 `taskStatus.ts`）；选中对象（targetResolved）时就地嵌入 `EvidenceCandidatesModule`。
   - 右栏 `TaskProcessedPanel`：终态对象 + `listEvidenceReviews({page_size:200})` 关联出的已审核/已晋升对象（名称取自 review 的 `claim_components_snapshot` 的 source/target_region name_cn，`TaskProcessedPanel.tsx:reviewTargetLabel`）。
   - 名称兜底：`itemDisplayLabel`（`taskStatus.ts`）——label 缺失或为裸 UUID 时显示「类型中文 #短ID」。

### 1.3 点击跳转

1. 左/右点击对象：`handleOpen(item)` → 全局模式先 `openTask(item.__taskId)` 再 `openTarget(type,id,'tasks')`（`TaskPendingQueue.tsx` / `TaskProcessedPanel.tsx`）。`openTask` 清 target 并置 module='tasks'，`openTarget` 再设 target（`EvidenceCenterContext.tsx:158-172`；两次 apply 同事件批处理，最终 state 含 taskId+target；`buildEvidenceUrl` 省略默认 module=tasks，`evidenceCenterUrl.ts:28-37`）。
2. 中栏 `targetResolved` 门控（`EvidenceTasksModule.tsx`）：URL target 必须命中当前 items 才挂载候选组件，防止候选组件的 URL 同步副作用（`EvidenceCandidatesModule.tsx:282-288`，`openTarget(...,'candidates')`）把模块切走。
3. 候选工作区 DTO：`getEvidenceTarget`（`endpoints.ts`）→ `GET /evidence/target/{target_type}/{target_id}` → `build_target_dto`（`evidence_target_adapter.py:284-330`）。**镜像行不存在时抛 `ValueError("target not found")`（293-294）** → 前端 `EvidenceCandidatesModule.tsx:305-318` `.catch(() => setDto(null))` → 工作区显示空态/占位。
4. 数据中心直达：`navigateToEvidenceCandidates`（`evidenceCenterUrl.ts:54-70`）写 initial-queue + 跳 `module=candidates`，落在候选模块（不是佐证任务页）；候选模块读 initial-queue 恢复队列（`EvidenceCandidatesModule.tsx` 内 `INITIAL_QUEUE_KEY`）。

---

## 2. 文件清单

**前端（佐证任务页）**
- `frontend/src/pages/evidence-center/EvidenceCenterContext.tsx` — URL 状态/导航（openTask/openTarget/closeTask/gotoModule/parseEmbeddedUrl）
- `frontend/src/pages/evidence-center/evidenceCenterUrl.ts` — parse/buildEvidenceUrl、navigateToEvidenceCandidates、INITIAL_QUEUE_KEY
- `frontend/src/pages/evidence-center/EvidenceCenterPage.tsx` — 三栏骨架/左右栏分支/ContextBar（37-50 另拉任务列表 limit 50）
- `frontend/src/pages/evidence-center/modules/EvidenceTasksModule.tsx` — 中栏任务卡（统一状态）+ targetResolved 门控 + 嵌入候选组件
- `frontend/src/pages/evidence-center/components/useEvidenceTaskItems.ts` — 共享取数 hook（全局 N+1 并行/任务模式/陈旧守卫）
- `frontend/src/pages/evidence-center/components/TaskPendingQueue.tsx` — 左栏待处理队列
- `frontend/src/pages/evidence-center/components/TaskProcessedPanel.tsx` — 右栏已处理（终态+审核记录）
- `frontend/src/pages/evidence-center/components/taskStatus.ts` — 状态标签/音色、taskDisplayName、deriveTaskWorkStatus、itemDisplayLabel
- `frontend/src/pages/evidence-center/components/taskItemQueueUtils.ts` — 未完成集合/置信度排序/类型分组
- `frontend/src/pages/evidence-center/modules/EvidenceCandidatesModule.tsx` — 候选工作区（本次只读，未改）
- `frontend/src/api/endpoints.ts` — 全部 API wrapper 与类型（5595-5720、5838-5910）

**后端**
- `backend/app/routers/ontology.py` — /evidence/batch 系端点（创建 975/列表 1008/pause 1043/resume 1055/cancel 1070/retry-failed 1082/任务详情 1098/items 1109/reopen 1119/reviews 1349-1391）
- `backend/app/services/paper_evidence_service.py` — create_batch_task、_batch_scope_label、_name_parts、_resolve_scope_ids、list_batch_items、执行循环、pause/resume/cancel/retry_failed/reopen、_update_task_totals/_update_task_review_status
- `backend/app/services/evidence_target_adapter.py` — TARGET_MODELS（30-38）、build_target_dto（284-330）、claim 构建
- `backend/app/models/mirror_kg.py` — MirrorRegionConnection（33-）、MirrorRegionCircuit、MirrorRegionFunction 等（confidence 列均 `Numeric nullable`）

---

## 3. 当前接口响应示例（实测，2026-08-14）

**任务列表** `GET /api/ontology/evidence/batch?limit=20`
```json
{"id":"00e4bf49-…","target_type":"connection","scope":"selected","mode":"function",
 "status":"completed","total_items":115,"processed_items":0,"awaiting_review_items":109,
 "name":null,"granularity_level":"macro","summary":{"counts":{"awaiting_review":109,"pending":6}}}
```
> 注意：任务 status=completed 但 109 个对象 awaiting_review——任务级状态与对象状态脱节。

**对象列表** `GET /api/ontology/evidence/batch/00e4bf49-…/items?limit=200`（实测 115 条）
```json
{"id":"01445d48-…","target_type":"connection","target_id":"4bd7092b-…","status":"awaiting_review",
 "label":"4bd7092b-f65b-49c8-81f7-ebf8d896c152","current_confidence":null,"confidence":null,"pmid":null,
 "updated_at":"2026-08-12T13:03:53…"}
```
> 115/115 条 label==target_id（UUID）；current_confidence 非空 0/115；为 0 的 0 条。

**目标 DTO** `GET /api/ontology/evidence/target/connection/4bd7092b-…`（同一对象！）
```json
{"granularity":"molecular_attr","display_name":"Somatosensory areas, layer 4 · Primary somatosensory area, nose, layer 1 · projection",
 "source_region":"Somatosensory areas, layer 4","source_region_cn":"体感区，第4层","current_confidence":0.0,
 "claim_text":"Somatosensory areas, layer 4 到 … 存在投射连接（方向性：directed）。",…}
```
> 镜像行现在存在、有真实名称、confidence=0.0——与对象快照（UUID/None）完全脱节。

**审核记录** `GET /api/ontology/evidence/reviews?page_size=5`
```json
{"id":"9aaacd5e-…","target_type":"projection","target_id":"1910140e-…","task_id":null,"task_item_id":null,
 "review_status":"approved","promotion_status":"promoted",
 "claim_text_snapshot":"right thalamus proper 到 right putamen 存在投射连接…",
 "claim_components_snapshot":[{"component_type":"source_region","metadata":{"name_cn":"右丘脑本体",…}},{…target_region…右壳核}]}
```
> 已审核/已晋升对象与任务对象无 task_item 关联；任务对象状态仍 awaiting_review（实测投影任务的 items 为 awaiting_review）。

---

## 4. 问题根因

### P1 连接/投射/回路显示数据库 ID（已确认）
- **根因（已确认）**：`label` 是创建任务时的**快照**。`_batch_scope_label`（`paper_evidence_service.py:2575-2595`）在创建时查镜像行拼名称；`_name_parts`（586-604）名称字段缺失时 parts 为空 → 回退 `target_id`（2595 行 `label = " · ".join(parts[:3]) if parts else target_id`）。实测 115/115 条快照为 UUID，而同一 target_id 的实时 DTO 已有真实名称 → 快照过期。
- **待确认**：创建时镜像行是否已存在（若存在则名称字段当时为 NULL，后续被镜像富集步骤补写；若不存在则创建时查无此行）。

### P2 置信度显示「—」/值不正确（已确认，另有待确认点）
- **根因（已确认）**：`current_confidence` 仅在创建时 INSERT 快照（`paper_evidence_service.py:2667、5062`），预处理/审核全程**无 UPDATE**（grep 证实）；创建时镜像行 confidence 为 NULL → 快照 NULL → 永远「—」。实测 0/115 有值。
- **显示层无 0-as-falsy 缺陷（已确认）**：前端排序用 `ca == null` 判定（`taskItemQueueUtils.ts`），卡片显示用 `conf != null ? conf.toFixed(2) : '—'`（`TaskPendingQueue.tsx`）；全 evidence-center 无 `confidence ||`/`conf ||` 模式（grep 证实）。若回填 confidence=0.0，会正确显示「0.00」。
- **待确认**：镜像行 confidence=0.0（实测 DTO）是真实低置信还是「未评分缺省 0」；若为缺省值，回填时应区分。

### P3 点击对象/任务后没有进入正确页面（部分确认）
- 3a（已确认链路存在）：数据中心入口落到 `module=candidates`（`MirrorKgPanel.tsx:287-292`、`evidenceCenterUrl.ts:54-70`），进入的是候选模块，不是佐证任务页——符合「数据中心点一条数据进入论文佐证」的业务预期，但与「验证中心管理任务」是两个入口。
- 3b（已确认）：佐证任务页点击对象后，候选组件 `getEvidenceTarget` 对无镜像行的 target 抛 `ValueError("target not found")`（`evidence_target_adapter.py:293-294`），前端 catch 后 `setDto(null)`（`EvidenceCandidatesModule.tsx:305-318`）→ 工作区空态，看起来「没进去」。
- 3c（已确认）：全局队列点击先 `openTask` 再 `openTarget`，顺序与批处理语义正确（`EvidenceCenterContext.tsx:158-172`）。
- **待确认**：用户实际遇到的是 3a、3b 还是 URL 未带 `tab=paper_evidence` 导致的默认回退（`parseEmbeddedUrl` 要求 tab 参数，`EvidenceCenterContext.tsx:83-97`）。

### P4 不同任务状态操作不明确（已确认）
- 前端 pause/resume/cancel/retry-failed wrapper 存在（`endpoints.ts:5701-5708`）但**佐证任务页三组件零使用**（grep 证实）；中栏任务卡仅「点击选中任务」一个动作（`EvidenceTasksModule.tsx`）。
- 后端操作守卫：pause 仅 pending/running（`paper_evidence_service.py:3560-3572`）；resume（3584）；cancel（3616）；retry-failed（3649）；对象 reopen 仅 completed（3925+）。
- **状态枚举不一致（已确认）**：后端任务状态含 `partially_failed`（3490-3512）与 `cancelled`，前端 `TASK_STATUS_LABELS`（`taskStatus.ts`）只有 pending/running/paused/completed/failed → 未知状态裸显；V5 的 `deriveTaskWorkStatus` 已绕开任务级 status，改由对象状态推导统一状态。

### P5 N+1 / 命名不一致 / fallback 缺陷（审计结论）
- N+1：全局取数 1 次任务列表 + 每任务 1 次 items（`useEvidenceTaskItems.ts`，并行、≤200 任务，实测 7 次）——受控的 N+1，无聚合端点；`EvidenceCenterPage.tsx:37-50` 另有一次 limit 50 的任务列表拉取（仅 ContextBar 任务名用，非嵌入模式）。右栏再加 1 次 reviews（page_size 200）。
- 命名不一致（已确认）：对象同时有 `confidence`（论文级 LLM 方向置信度，list_batch_items r[8]）与 `current_confidence`（对象快照 r[13]）；前端类型 `PaperEvidenceTaskItem` 两者并存（`endpoints.ts:5595-5642`）；DTO 只用 `current_confidence`（adapter:302）。易误用。
- 分页语义（已确认）：items 服务端 `ORDER BY created_at LIMIT 50 默认`（`ontology.py:1109-1115`、`list_batch_items` 3834-3839），前端取 100 且按置信度排序——「仅显示前 100 条(按优先级截断)」的提示语义不成立（服务端按创建时间截断，非置信度）。
- `value || fallback` 0 值审计：**未发现** confidence 相关的 `||` 缺陷；`itemDisplayLabel` 用 `item.label &&`、`taskDisplayName` 用 `t.name ||`（字符串字段，无 0 值风险）。

---

## 5. 最小改动方案（待确认后实施）

| # | 改动 | 文件 | 影响 |
|---|---|---|---|
| M1 | 后端新增批量回填端点 `POST /evidence/batch/{task_id}/items/resolve-labels`：按 target_id 重查镜像表回写 `label`+`current_confidence`（含 0.0），`_batch_scope_label` 逻辑复用；一次性修复存量 + 可在创建时直接调用 | `paper_evidence_service.py`、`ontology.py`、测试 | P1/P2 |
| M2 | 预处理完成分支回写 `current_confidence`（对象通过验证后镜像行置信度快照进 item） | `paper_evidence_service.py`（_process_batch_item 完成分支） | P2 |
| M3 | 中栏任务卡按统一状态提供操作：进行中→暂停 / 部分失败→重试失败 / 待审核→查看 / 已完成→查看；接线既有 pause/resume/retry-failed 端点 | `EvidenceTasksModule.tsx`、测试 | P4 |
| M4 | `build_target_dto` 查无行时返回可辨识错误信息（前端候选组件显示明确提示而非静默空态）；或前端在 targetResolved 前先探测 DTO | `evidence_target_adapter.py` 或 `EvidenceTasksModule.tsx` | P3b |
| M5 | 统一入口：数据中心「论文佐证」与验证中心同用佐证任务页（或在佐证任务页保留 module=candidates 兼容）——需业务确认 | 路由层 | P3a |

## 6. 建议数据契约（草案）

```jsonc
// GET /evidence/batch/{task_id}/items 增强
{ "items": [ {
    "id": "…", "task_id": "…", "target_type": "connection", "target_id": "…",
    "status": "awaiting_review",            // 枚举: pending|searching|fetching|retrieving|extracting|verifying|awaiting_review|completed|skipped|failed|cancelled
    "label": "体感区第4层 · 鼻区第1层 · 投射",  // 已解析业务名(实时或回填)
    "label_source": "mirror_snapshot|mirror_live|review_claim|fallback", // 名称来源
    "current_confidence": 0.0,              // 数值 0..1,允许 0,允许 null=未评分(显式区分)
    "confidence_snapshot_at": "…",          // 快照时间,过期可判断
    "task_work_status": "awaiting",         // 统一状态(进行中/待审核/部分失败/已完成),由对象推导
    "total": 115                            // 列表总数,支持真分页
} ], "total": 115 }
```
任务级：`status` 与派生 `work_status` 并存；名称/置信度以 `label_source` 标注出处，前端据此决定是否显示兜底样式。

## 7. 需要执行的测试

**后端（pytest）**
- 回填端点：有行/无行/名称字段为空/confidence=0.0/confidence=NULL 五分支；回填后 item 与任务统计不变；幂等。
- 预处理完成回写 current_confidence（含 0.0）。
- retry-failed / reopen 守卫回归（既有 52 测试保持）。
**前端（vitest）**
- 回填后列表显示真实名称与「0.00」；label_source=fallback 时显示「类型中文 #短ID」。
- 任务卡各统一状态的操作按钮（暂停/重试/查看）及点击后的 URL。
- 点击链路端到端：全局队列点对象 → task_id+target 入 URL → 中栏工作区；镜像行缺失时显示明确错误提示。
- 既有 240 用例全绿（15 个其他模块基线不变）。

---

## 待确认清单（请用户确认后进入修改）

1. 创建任务时镜像行是否已存在（决定 M1 是否需要处理「创建时行缺失」场景）。
2. confidence=0.0 的语义（真实低置信 vs 未评分缺省）。
3. 数据中心入口应落在「佐证任务页」还是维持「候选模块」（P3a）。
4. M3 任务卡操作按钮的具体形态（每状态一个主操作 vs 详情内操作）。
