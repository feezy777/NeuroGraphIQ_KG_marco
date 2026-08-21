# 第七步 A 设计：审核通过 → 回退 → 重新评分 → 重新进入流程（只读设计审计）

> 状态：设计审计（2026-08-14）。本轮零代码/数据库/迁移/测试/配置改动。
> 前置：第六步 review↔task item 稳定关联已验收。

## 0. 审计确认的关键事实（只读核实）

### 0.1 review 数据模型（paper_evidence_reviews，实测 pg 元数据）
- 无 `revision`/`parent`/`superseded`/`invalidated`/`rollback_*` 任何可复用版本字段；唯一近似字段是 `draft_revision`（草稿乐观锁，语义不同）。
- `review_status` / `promotion_status`：varchar NOT NULL，**无 CHECK 约束**；`paper_id` 有 FK；`task_id`/`task_item_id` 无 FK 约束（仅 `idx_reviews_task` 普通索引，无 `task_item_id` 索引）。
- 晋升关联：`evidence_id`（指向 mirror_evidence_records）+ `promoted_at/by`。
- 审计：`ontology_change_logs`（action_type/entity_type/entity_id/before/after/operator/reason）— 已有 `EVIDENCE_REVIEW_CREATED/APPROVED/REJECTED/PROMOTED/RETURNED` 事件。

### 0.2 回答「二」的 8 问
1. **可变记录还是不可变快照**：事实上的**混合体**——build 时冻结 claim/coverage/置信度快照（不可变部分），但 `review_status`/`promotion_status` 在 approve/reject/promote/return 中反复改写，且 `return_review` 会把已 approved 的 review 的 review_status 改回 `awaiting_review`。评分本身（reviewer_confidence 等）自创建后不再被修改。
2. **approve/reject/promote 修改哪些字段**：approve → `review_status=approved`、`promotion_status=awaiting_promotion`、`approved_at`、`updated_at`（+同事务完成 task item）；reject → `review_status=rejected`、`rejected_at`、`updated_at`（+完成 item）；promote → `promotion_status=promoted`、`evidence_id`、`promoted_at/by`、`updated_at`（+写 mirror_evidence_records/passages、confidence_adjustment_logs、目标行 confidence/evidence_text）。
3. **同一 task item 可以有多少条终态 review**：无约束——多条。第六步防重只挡非终态；`reopen_batch_item` 把 item 放回 awaiting_review 后 build 会生成第二条终态 review。**迁移版本化时不能假设唯一**。
4. **如何判断「最新/当前有效 review」**：无后端字段。前端 TaskProcessedPanel 用 `pickPrimary`（按 approved_at/rejected_at/reviewed_at/created_at 取最新终态，否则最新）。后端无此概念。
5. **数据库约束/索引是否限制版本化**：不限制。reviews 表无 partial unique index；item 的 `uq_task_item_target`（task+target 唯一）与 `uq_evidence_task_item_active_target`（全局 active 唯一）只约束 item 创建，不影响 review。
6. **review_status 是否有 CHECK/枚举**：无 CHECK、无 PG 枚举。新增值不触发约束错误（但设计上**避免新增状态值**，用列而非状态）。
7. **增加新状态是否需要迁移**：本设计**不新增 review_status 值**（用 `superseded_at` 等列表达），因此零状态迁移；新增列本身需要一条 idempotent 迁移（035）。
8. **前端能否按 review_id 加载详情**：`endpoints.getEvidenceReview(id)` 已定义但**无任何使用点**。审核工作区 EvidenceReviewModule 完全由 target（URL target_type/target_id + task_item_id）驱动，从 sessionStorage 草稿/任务 item draft 恢复；无 review_id 驱动的入口。TaskProcessedPanel 卡片点击走 `openTaskTarget`（对象级）。**第七步需新增“按 review_id 打开只读历史”与“回退后导航”能力**。

### 0.3 重新评分真实前端工作流（回答「三」）
1. **评分何时生成**：build review 时一次性生成。EvidenceReviewModule 修改草稿 → 点击「审核通过/驳回」→ `buildReview` 一次写入（reviewer_direction/evidence_level/confidence/note/快照）。**不存在“在已有 review 上修改评分”的路径**；`return_review` 只改状态不改评分。
2. **reviewer_confidence 何时写入**：build 创建时写入，之后不可变。
3. **重新进入工作区后应该做什么**：**重新 build review**（编辑草稿后走现有 buildReview 链路）。第六步已实现：旧终态 review 不参与防重，item 回 `awaiting_review` 后 build 生成新 review（`test_terminal_review_does_not_block_new_build_after_item_reopen` 已验证此最小路径可行）。
4. **能否加载指定 review_id**：见 0.2-8，不能。
5. **回退时立即建新 review 是否被第六步防重挡**：如果旧 review 处于终态（approved/rejected），防重不挡（只挡非终态）。但若回退接口把新 review 建成 `draft/awaiting_review`，则后续用户在工作区点「审核通过」再 build 一条 → 被防重 409 挡住。**这正是方案 A 的关键缺陷**。
6. **若不立即建 review，后续 build 如何知道是旧版的新版本**：需要在持久锚点（task item）上保存 pending rescore 上下文（source_review_id + revision_no），build_review 读该上下文并挂链。见 §6。
7. **对现有 UI 改动最小且语义最安全的方式**：**方案 B**（回退事件 + 重开 item + build 时挂链）。见 §4。

## 1. 当前 review/评分工作流（确认版）

```
任务/数据中心 → openTaskTarget(taskId, type, id, itemId) → URL 稳定参数
  → EvidenceCandidatesModule(候选/草稿) → 进入人工审核
    → EvidenceReviewModule(按 target+task_item 恢复草稿, ReviewerDecisionPanel)
      → buildReview(一次性冻结评分+快照; task_id/task_item_id 强制关联)
        → approve → review approved/current, item completed(同事务)
        → promote → evidence 生效, review.evidence_id 关联
          右栏已处理: 卡片=最新终态 review + 关联类型 + 时间 + 历史数量
          旧 reopen(任务项重开) 仅对无终态 review 的 completed 项开放
```

## 2. promotion rollback 真实事务边界（回答「五」）

`rollback_evidence`（paper_evidence_service.py:1405）：
1. 输入主体：**`evidence_id`**（mirror_evidence_records.id），不是 review_id。router `POST /evidence/{evidence_id}/rollback`，`require_role("reviewer")`。
2. 定位正式证据：由 promote_review 写回的 `review.evidence_id` 关联；对 review 回退需先读该字段。
3. 修改的表/状态：
   - `mirror_evidence_records`：`verification_status='invalidated'`、`invalidated_by/at`、`invalidation_reason=reason`（**不物理删除**）。
   - `confidence_adjustment_logs`（applied → `rolled_back` + rolled_back_by/at/reason）。
   - 目标行（mirror_region_connections 等）：`confidence = max(其余 applied 日志, log.before_confidence)`，`evidence_text = rebuild_evidence_text(...)`。
   - `ontology_change_logs`（EVIDENCE_ROLLBACK）+ `evidence_validation_records`（EV_PAPER_EVIDENCE_INVALIDATED，含 paper 快照）。
4. 是否物理删除：**否**，全部逻辑失效+留痕（invalidated 记录保留）。
5. 是否保留 invalidated 记录：是。
6. 是否自己 commit：**否**——只 `session.flush()`，commit 由 router 调用方执行（成功 commit，异常 rollback）。
7. **能否作为同一事务的内部步骤调用**：能。其实现纯 ORM + 审计，无 commit，可被 review 回退事务直接复用（建议在实施时拆出 `_invalidate_evidence_inplace(session, evidence_id, reason, operator)` 内部函数，端点继续包 commit）。
8. 撤销成功但重开失败能否整体回滚：**能**——同 session 未 commit，任一异常 → router rollback → 全无副作用。
9. 是否涉及 PG 之外系统：**不涉及**。无搜索索引/图库/缓存/文件写入；DeepSeek/Europe PMC 只在检索期调用，回退不触发。
10. 外部系统策略：不适用。
11. promotion_status 回退后：**保持 `promoted` 不变**。它是历史事实（该版本确实晋升过）；“证据已撤销”由 mirror_evidence_records.verification_status='invalidated' 表达；“不再是当前版本”由 reviews.superseded_at 表达。改 promotion_status 会破坏既有晋升列表过滤与审计语义。
12. 旧 review 的 approved 事实：**保留**（review_status 保持 approved；approved_at 不动）。

## 3. A/B/C 方案比较（回答「四」）

| 维度 | A 回退时立即建新 draft review | B 回退事件+重开 item，build 时挂链 | C 新建单对象任务/attempt |
|---|---|---|---|
| 现有审核 UI 兼容 | 差：UI 无“按 review_id 打开 draft”能力；draft 状态机不存在（review_status='draft' 无写入路径） | **好**：完全复用现有 build→approve/promote 链路 | 中：复用任务链路，但多一个任务卡 |
| linked review | 需要为 draft 补 claim 快照/草稿回填，改动大 | **原生**：item 就是锚点 | 过度设计：弃用原 item |
| standalone/legacy | 无锚点，draft 无处挂 | standalone 无锚点 → 需补建锚点（可复用 C 的子集） | **适合** standalone |
| 已晋升证据撤销 | 同 B | 同 B | 同 B |
| 审计完整性 | 好 | **最好**（回退事件独立成审计行） | 好 |
| 并发/幂等 | draft 建两次 → 防重 409 | review 行锁串行化，重复 → 409 | 任务创建需幂等键 |
| 迁移复杂度 | 同 B | 同 B | 同 B + 任务来源字段 |
| 立即重进工作区 | 是（但要新 UI） | 是（回退即重开 item，导航到对象） | 是（新任务） |
| 同 target 多任务歧义 | 无改善 | linked 无歧义（item 锁死）；legacy 按第六步 resolve 规则 | 新任务反而增加同 target 多任务 |
| 版本历史可读性 | 链挂 review 上，好 | **链挂 review 上，好** | 链分散在任务间，差 |
| 第六步防重交互 | 新 draft 会挡住后续 build（关键缺陷） | 无冲突（新 review 只在 build 时产生） | 无冲突 |

**推荐**：
- **linked review：方案 B**。
- **standalone review：方案 C 变体（单对象任务）**——standalone 无 task_item 锚点，“重新进入任务中心”的唯一安全路径是新建单对象任务；任务用 `filter_snapshot` 记录 `{"rescore_of": review_id}`（零新列），新 review 照常挂 supersedes 链。
- **legacy ambiguous（多候选/0 候选）review：禁止回退**——只读历史（capability=false + block_reason）；唯一匹配（复用第六步 resolve 语义，不改写旧 review 行）时按 linked B 路径执行。

## 4. 数据模型（回答「六」，最小完整版）

新增迁移 `035_review_rescore_versioning.sql`（idempotent）：

```sql
ALTER TABLE paper_evidence_reviews
  ADD COLUMN IF NOT EXISTS revision_no INT NOT NULL DEFAULT 1,
  ADD COLUMN IF NOT EXISTS supersedes_review_id UUID
      REFERENCES paper_evidence_reviews(id),
  ADD COLUMN IF NOT EXISTS superseded_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS superseded_by VARCHAR(64),
  ADD COLUMN IF NOT EXISTS rollback_reason TEXT;
CREATE INDEX IF NOT EXISTS idx_reviews_supersedes
  ON paper_evidence_reviews(supersedes_review_id);
CREATE INDEX IF NOT EXISTS idx_reviews_task_item
  ON paper_evidence_reviews(task_item_id);

ALTER TABLE paper_evidence_task_items
  ADD COLUMN IF NOT EXISTS rescore_source_review_id UUID,
  ADD COLUMN IF NOT EXISTS rescore_revision_no INT;
```

逐字段裁定：
- `revision_no`：加。任务中心「第 N 次评分」显示 + 防并发误读。
- `supersedes_review_id`：加，方向 = **新 review 指向旧 review（子→父）**。旧行是历史事实尽量不改；新行创建时已知父；父指针可用简单递归/逐跳查询串链。
- `is_current`：**不加**。current = 版本链上 `superseded_at IS NULL` 且为链尾的行；并发安全靠回退事务对 review 行 `FOR UPDATE`（第二个并发回退看到 superseded_at 非空 → 409），不需要布尔+partial unique index 状态机。
- `superseded_at/superseded_by`：加（旧行）。
- `rollback_reason`：加在 **review 行**（superseded 行上）——回退原因属于该版本的终结事件，历史卡直接展示无需 join 审计；审计表同时写入（双重留存，审计表是权威流水）。
- `rescore_status`：**不加**。重评中间态 = task item.status='awaiting_review' + item.rescore_source_review_id/revision_no；放弃重评表现为「悬空链」（旧版已 superseded、无后继），UI 标「回退后未完成重评」，item 继续留在待处理队列可随时接续。
- `source_review_id`（review 表）：**不加**，supersedes_review_id 已表达。
- task 表：**不加列**，standalone 重评任务用 `filter_snapshot={"rescore_of": review_id}` + `name` 带「重新评分」。
- 独立 `review_events` 表：**不加**，ontology_change_logs 已具备事件流水能力（新增 action_type `EVIDENCE_REVIEW_SUPERSEDED`）。
- 旧数据兼容：全表默认 revision_no=1、superseded 空；同 item 多条终态旧 review 不会使迁移失败（无唯一约束）；「当前」对无链旧数据回落第六步 pickPrimary 规则。**禁止**自动为旧数据建链。

## 5. 状态机（回答「七」）

### linked approved（未晋升）
初始：review approved/current、item completed、promotion=not_ready|awaiting_promotion
回退（事务内）：review 加 superseded_at/by+rollback_reason（**review_status 仍 approved**）；item → awaiting_review + rescore_source_review_id=旧id、rescore_revision_no=2（保留 label/置信度快照，清 reviewed_at/by）
重评：工作区 build → 新 review（revision_no=2，supersedes_review_id=旧id，初始 status=awaiting_review 或 rejected）→ 清 item.rescore 上下文
新 approve → 新行即 current；item completed（第六步逻辑）
新 reject → 链尾=rejected（current），流程结束；rejected 重评本阶段不扩展
中途放弃 → 悬空链：无 current，item 停留 awaiting_review，UI「回退后未完成重评」，重新进入工作区即可 build

### linked promoted
初始：review approved/current、item completed、promotion=promoted、evidence active
回退（同一事务）：锁 review → 读 review.evidence_id → `_invalidate_evidence_inplace`（evidence invalidated + 置信度回算 + 审计）→ supersede review → item 重开 + rescore 上下文 → 审计 → commit；任一失败全量回滚（不出现“回退成功但证据仍生效”）
promotion_status 保持 promoted；旧 approved 事实保留

### standalone approved/promoted
回退：锁 review → 撤销 evidence（如 promoted）→ supersede review → **新建单对象任务**（scope=single_object，target_ids=[target_id]，name=「重新评分·{对象名}」，filter_snapshot={"rescore_of": review_id}）→ materialize 1 个 item(awaiting_review) + item.rescore 上下文 → 导航新任务新 item。**不猜测旧任务**。

### legacy ambiguous
- 唯一匹配 item（复用 resolve 语义，**不改写旧 review 行**）：按 linked 路径回退。
- 0 或多匹配：**禁止回退**（can_rollback_rescore=false，block_reason=NO_TASK_ITEM/AMBIGUOUS_TASK_ITEM），仅只读历史；治理手段为管理员手工关联（不在本阶段实现）。
- orphan（task/item 指向不存在）：只读历史。

通用规则：
- 只能回退**当前终态**版本（superseded_at IS NULL 且 review_status='approved'）；已 superseded 再回退 → 409；**不允许历史版本分叉**。
- rejected 回退不扩展（本阶段）。

## 6. API 契约（回答「八」）

`POST /api/ontology/evidence/reviews/{review_id}/rollback-for-rescore`
- body：`{"reason": "必填, min 2", "idempotency_key": "可选, 客户端生成, 记入审计 after_data"}`
- 响应 200：
```json
{ "source_review_id":"…", "new_review_id":null,
  "task_id":"…", "task_item_id":"…", "target_type":"…", "target_id":"…",
  "revision_no":2,
  "promotion_rollback":"not_needed|completed",
  "navigation":{"module":"tasks","task_id":"…","task_item_id":"…","target_type":"…","target_id":"…"} }
```
- 权限：`require_role("reviewer")`。
- 可回退：review_status='approved' 且 superseded_at IS NULL（promoted/未 promoted 均可）；否则 409 `REVIEW_CONFLICT`/code=REVIEW_NOT_ROLLBACKABLE。
- 错误码：404 `REVIEW_NOT_FOUND`；409 `REVIEW_ALREADY_SUPERSEDED`（重复点击/已被他人回退——**重复请求返回 409 而非原结果**，避免误以为二次生效）；400 `ROLLBACK_REASON_REQUIRED`；409 `AMBIGUOUS_TASK_ITEM`/`NO_TASK_ITEM`（legacy）；502 `PROMOTION_ROLLBACK_FAILED`（证据撤销失败，整体回滚后返回）。
- 并发锁：review 行 `SELECT … FOR UPDATE`；promoted 时证据撤销在同一事务（rollback_evidence 内部函数化复用）。
- linked 与 standalone 同端点，内部按 `task_item_id` 分流（standalone → 建单对象任务）。
- 只读能力：`GET /evidence/reviews/{id}` 与 list items 增补 `can_rollback_rescore: bool` + `rollback_block_reason: string|null`（后端推导：状态/是否 superseded/关联唯一性）。

## 7. 前端交互（回答「九」）

- TaskProcessedPanel 已审核卡：仅 `can_rollback_rescore===true` 显示「回退并重新评分」（替代现有 hint 文案；capability=false 且原因=未开放时保留现有 hint）。
- 确认弹窗：对象名、当前结论、评分、是否已晋升、回退影响（证据失效/对象重回待验证）、必填原因、确认按钮 + loading 防重复提交。
- 成功：`refresh()`（任务/items/reviews/左右栏）→ 按 navigation `openTaskTarget(task_id, type, id, item_id)` → URL 稳定参数齐全 → 工作区提示「正在进行第 N 次评分」（revision_no）。
- 历史审核：卡片历史数量点击 → 只读抽屉（revision_no、结论、评分、时间、回退原因），不可编辑。
- 失败反馈：403 无权限 / 409 已被他人回退或状态变化（自动刷新并提示）/ 撤销失败明确错误保持原状 / 网络错误通用提示。
- promotion 模块现有「回滚」（纯证据撤销）保持不变；两个入口文案区分，避免冒充。

## 8. 历史数据 capability（回答「十」）

| 类型 | 可直接回退 | 处理 |
|---|---|---|
| linked（task_item_id 有效） | 是 | B 路径 |
| task-only 唯一匹配 item | 是 | resolve 后按 linked（不改旧行） |
| task-only 0/多匹配 | 否 | block=NO_TASK_ITEM/AMBIGUOUS_TASK_ITEM，只读历史 |
| standalone | 是 | C 变体：新单对象任务 |
| orphan | 否 | block=ORPHAN_TASK_CONTEXT，只读历史 |

禁止 target 自动选任意旧任务（延续第六步规则）。

## 9. 测试数据库安全核查（回答「十一」，全部只读核实）

1. 当前连接：`.env DATABASE_URL=…/neurographiq_kg_v3_mvp1_e2e`；运行时 /api/health `database.name=neurographiq_kg_v3_mvp1_e2e` ✓ 隔离 E2E 库。
2. 业务库未受影响：枚举本机 PostgreSQL 全部 10 个数据库，**仅 e2e 库存在 paper_evidence_reviews 表**（0 行）——业务库（v2/Workbench/KG_V3/wb/candidate 等）从未创建该表，旧测试文件的全表 DELETE 不可能伤及业务数据。**阻断项解除**。
3. 测试连库保障：目前仅靠 .env（无代码断言）——**不足**。
4. 现有测试无 DB 名断言。
5. 无条件清表清理：现仅剩 2 处按 id 删除测试自建 review（安全）；git 历史 `-S` 检索无危险模式提交记录。
6. 全仓危险模式：无 TRUNCATE/无条件 DELETE；migrations 仅 1 条注释掉的 DROP TABLE。
7. **第七步 B 需加硬保护**：conftest.py autouse fixture 断言 `settings.postgres_db` 以 `_e2e` 结尾，否则写测试全部 skip/fail；后台 batch 服务同理加启动断言。

## 10. 实施步骤拆分（第七步 B 草案）

1. 迁移 035（§4）+ conftest DB 名硬保护。
2. 后端 service：`rollback_review_for_rescore`（锁→校验→证据撤销内部化→supersede→item 重开+上下文→审计→单 commit）；`build_review` 挂链（读 item.rescore 上下文，校验一致，写 supersedes/revision_no，成功即清上下文）；`get/list_review` capability 字段；standalone 单对象任务创建（复用 materialize）。
3. router：rollback-for-rescore 端点 + 结构化错误映射。
4. 前端：TaskProcessedPanel 按钮/弹窗/导航/提示/只读历史抽屉；promotion 模块文案区分。
5. 测试矩阵（§11）+ 运行时只读验收。

## 11. 测试矩阵（第七步 B 验收用）

后端：linked approved 回退（item 重开+上下文+不建新 review）；linked promoted 回退（证据 invalidated+置信度回算+同事务）；事务中途失败整体回滚（证据撤销后 item 重开失败 → 全无副作用）；重复回退 409；已 superseded 409；无原因 400；并发回退（两请求串行，一个 409）；新 build 挂链（revision_no=2、supersedes 正确、上下文清空）；上下文不一致（客户端带错 source_review_id）拒绝；standalone 回退建新任务（filter_snapshot 来源、item 就绪）；legacy 唯一/0/多匹配三分支；capability 字段正确性；旧数据（无链）不迁移不报错。
前端：capability 才显示按钮；弹窗内容与必填原因；防重复提交；成功刷新+导航（URL 稳定参数）+「第 N 次评分」提示；历史抽屉只读；409 已回退反馈；standalone 导航新任务。

## 12. 阻断项

- **无阻断项**。测试库清空事件已确认只影响 E2E 库（业务库无此表）；实施期需补 conftest DB 名硬保护（已列入步骤 1）。

## 13. 结论

**可以进入第七步 B 实施**（按 §10/§11 执行；linked 用方案 B、standalone 用单对象任务、legacy 按唯一性分流；数据模型为 §4 五列+两 item 列，不加 is_current/事件表/新状态）。

---

## 附:第七步 B 实施记录(2026-08-14,保留上方设计依据原文)

- **迁移**:实际编号 `044_review_rescore_versioning.sql`(当时最大编号为 043),已在 e2e 库应用并验证(5 review 列 + 2 索引 + 2 item 列 + FK 就位)。项目无 downgrade 惯例,遵循现有规范不提供。
- **实施偏差**:
  1. `supersedes_review_id` 子→父(与设计一致);回退事务行锁 + 状态校验,重复/并发 → 409 `REVIEW_ALREADY_SUPERSEDED`。
  2. 权限:沿用 `require_role("reviewer")`(403 code=FORBIDDEN,现有惯例,未引入 PERMISSION_DENIED 新码)。
  3. standalone 重评任务 `scope='single_object'`、`filter_snapshot={"rescore_of": ...}`、item 置信度快照取自 target 行。
  4. `build_review` 挂链:后端从 item 的 rescore 上下文取 source(不信任客户端),校验 source 已 superseded/target 一致/仍为链尾(禁分叉),INSERT 同事务清上下文。
  5. capability/effective_promotion_status 为后端派生(`active|rolled_back|not_promoted`),前端不自行判断。
  6. PG 约束:LEFT JOIN 与 FOR UPDATE 不兼容(已拆分查询);同任务同 target 多 item 被 `uq_task_item_target` 阻止(歧义分支以 mock 单测)。
- **测试**:后端 `test_paper_evidence_rescore.py` 20 项全绿;conftest 增加 session 级 E2E 库硬门禁(连接后 `SELECT current_database()` 非 `_e2e` 结尾立即终止,连接失败保守终止)。
- **运行时验收**:`scripts/s7b_runtime_acceptance.py`(唯一前缀 fixture,全部通过:linked approved/promoted 回退、evidence invalidated+置信度 0.7→0.5 回算、重复 409、standalone 单对象任务、版本链 [(1,False),(2,True)]);真实 HTTP 实测 POST rollback(200)/重复(409)/空原因(400)/GET 详情+capability/GET history 全部符合契约。
- **遗留**:前端 14 个失败为第3~5步陈旧测试(与 S7B 无关);后端全量 12 个失败为先前改动遗留(S7B 无新增失败)。
