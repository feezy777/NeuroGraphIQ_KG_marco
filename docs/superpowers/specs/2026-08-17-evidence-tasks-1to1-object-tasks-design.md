# 佐证任务中心:任务-对象一对一 + 对象命名设计

- **日期**: 2026-08-17
- **状态**: 设计已与用户逐项确认(层次/标题格式/存量迁移/左栏/中栏范围/点击行为)
- **分支**: `codex/ontology-evidence`
- **目标**: 佐证任务中心的任务卡片按知识对象命名(连接/回路中英文名+置信度),且一个佐证任务 = 一个对象(后端数据模型真正一对一)

---

## 1. 背景与问题

现状(截至 fb32474):

1. `paper_evidence_tasks` 是批量任务(1 任务 = 最多 200/500 个对象),对象在 `paper_evidence_task_items` 中;中栏一卡 = 一个批量任务,标题统一「连接验证任务 · N 个对象」,看不到具体对象。
2. 任务 `name` 为内部自动名时(如「重新评分 · s7b-acc-…」)直接抢占卡片标题。
3. 旧任务 `total_items` 列未维护,出现「0 个对象」却显示「待验证 1」的口径混乱。
4. 存量 item 快照 label 大量为 UUID 占位、current_confidence 为 NULL(物化流程硬编码,见 2026-08-14 排查报告 §2)。

用户诉求:

- 卡片按知识对象命名:中文为主 + 英文括号,置信度副行大字。
- 一个连接验证任务 = 一个任务,只有一个对象(后端真正一对一,非仅展示层)。
- 点击卡片跳转到证据佐证页(module=candidates),与数据中心「论文佐证」入口完全一致。
- 存量多对象任务一次性拆分迁移;中栏全部状态都显示;左栏为 Claim 面板。

## 2. 目标

1. **后端一对一**:批量创建时每个对象生成一个独立任务(1 任务 = 1 对象 = 1 item);存量任务拆分迁移。
2. **对象命名**:任务卡片标题 = 对象中英文名 + 置信度,数据来自镜像行实时解析,快照兜底。
3. **点击直达**:整卡点击跳转 `#/validation-center?tab=paper_evidence&module=candidates&task_id=X&target_type=T&target_id=I`,与数据中心入口一致。

## 3. 非目标

- 不改 EvidenceCandidatesModule / EvidenceReviewModule / EvidencePromotionModule 的内容(仅跳转入口)。
- 不改 pause/resume/cancel/retry/reopen/items 系端点语义。
- 不做队列轮询、不做分页 UI(沿用 limit 200)。
- 不覆盖 `_derive_work_status` 状态推导(1 item 计数桶自然退化,无需改)。

## 4. 数据模型与迁移

### 4.1 任务行即对象

- `paper_evidence_tasks` 新增 `target_id UUID NULL`(迁移 SQL,兼容旧行;新建任务必填)。
- **一对一不变量**:每个任务恰好 1 个 `paper_evidence_task_items` 行,item 的 `target_id` = 任务的 `target_id`。
- 状态机全部复用:`work_status` 由该 item 单状态桶推导(0/1 退化);pause/resume/cancel/retry/reopen 天然对象级。
- 先例:rescore 流程已存在 single_object 单对象任务创建路径(`paper_evidence_service.py` `rollback_review_for_rescore`,约 6377 行),本次将批量任务统一为同一形态。

### 4.2 创建批量预处理 = 一次生成 N 个对象任务

`create_batch_task` 改为:

1. 圈选对象(现有 scope 逻辑与 busy 去重不变)。
2. 每个对象插入 1 个任务行(`target_id`、`total_items=1`)+ 1 个 item 行(实时 label/current_confidence 快照,复用 `_batch_scope_label`/`mirror_live_*`)。
3. 逐任务调度后台执行(`execute_paper_evidence_batch_background`,处理自己唯一对象)。
4. 响应 `{task_ids, target_count, skipped_active_targets, auto_started}`(保留 `task_id`=第一个,兼容旧调用方)。

新路径 item 创建即写入真实快照,不再依赖 `_materialize_page`(其硬编码 UUID/None 的问题不再触发)。

### 4.3 存量拆分迁移

一次性脚本 `backend/scripts/migrate_evidence_tasks_1to1.py`,幂等,按旧任务逐个事务提交:

1. 对每个「item 数 ≠ 1 或 item.target_id ≠ 任务.target_id」的旧任务,每个 item 生成一个新任务行:复制 scope/mode/max_papers_per_object/config/name 等配置,`target_id` = item 的 target_id,`total_items=1`,状态取旧任务状态。
2. `UPDATE paper_evidence_task_items SET task_id = 新任务` 把 item 挂过去。
3. 旧任务行 `status='cancelled'` + summary 打 `{"migrated_to": [新任务 ids]}` 标记(保留审计)。
4. 回填:item 的 label 为空或 UUID、current_confidence 为 NULL 的,从镜像行实时取(复用 `_batch_scope_label`)。

中断可重跑:已拆任务(带 migrated_to 标记)跳过;旧行拆完才标 cancelled。

### 4.4 命名策略

- 任务行 `name` 降级为「用户自定义备注」:**不再作为卡片标题**,有值时作卡片第三行小字显示。
- 卡片标题 = 镜像行实时名称,后端返回 `display_name_cn`、`display_name_en`、`display_confidence` 三字段。
- 兜底链:镜像行缺失 → item 快照 label(非 UUID)→「类型中文 #短ID」;置信度缺失 → 「未评分」。
- 后端新增 `mirror_live_display_name_parts(target_type, get) -> (cn, en) | None`(现 `mirror_live_display_name` 拆出双值版本,原函数保留供 item 列表兼容),`display_confidence` 复用 `mirror_live_confidence`。

## 5. 后端接口

| 端点 | 改动 |
|---|---|
| `POST /evidence/batch` | §4.2:N 个对象任务;响应加 `task_ids`(保留 `task_id` 兼容) |
| `GET /evidence/batch` | 每任务新增 `target_id`、`display_name_cn`、`display_name_en`、`display_confidence` + 来源标记;按 target_type 批量 JOIN 7 张镜像表(复用 item 列表 live 解析,无 N+1) |
| `GET /evidence/batch/{task_id}` | 同上补 display 字段 |
| pause/resume/cancel/retry-failed | 语义不变 |
| items 系端点 | 不变 |
| `/api/tasks/runs`(统一任务) | `_paper_evidence` label 改为对象显示名 |
| 迁移脚本 | `backend/scripts/migrate_evidence_tasks_1to1.py`(§4.3) |

worker:`execute_paper_evidence_batch_background(task_id)` 处理唯一 item,代码不变。

## 6. 前端(证据中心·佐证任务)

### 6.1 中栏任务卡(重写 TaskCard)

```
┌─────────────────────────────────────────┐
│ 杏仁核 → 海马 (Amygdala → Hippocampus)   │  ← 标题:中文 (英文),缺一侧自动省略
│ 连接 · 置信度 35%          ⬤ 待验证      │  ← 副行:类型中文 + 置信度大字 + 状态徽章
│ (name 备注第三行小字)        [继续验证]   │
└─────────────────────────────────────────┘
```

- **整卡点击 → 跳转证据佐证页**,与数据中心入口一致:`#/validation-center?tab=paper_evidence&module=candidates&task_id=X&target_type=T&target_id=I`,同时写 `INITIAL_QUEUE_KEY` 队列快照(`MirrorKgPanel.tsx:282-290` 同款)。
- 卡片按钮(stopPropagation):暂停/继续任务/重试失败项保留;「查看进度/查看结果」改为同上跳转。
- 排序:处理中 → 已暂停 → 待验证(置信度升序)→ 已完成(置信度升序)→ 失败;已取消不显示;「空任务」状态随一对一模型消亡。
- 筛选 chips 移到中栏工具栏:全部 / 连接 / 回路 / 功能(映射沿用 PRD V4 R4:回路=circuit/circuit_step/circuit_function,连接=connection/projection,功能=region_function/projection_function)。
- 任务 `name` 非空时第三行小字显示,不替换标题。

### 6.2 中栏不再就地嵌入工作区

- 删除 `targetResolved → 嵌入 EvidenceCandidatesModule` 分支(点击即跳走)。
- 深链 URL(`module=tasks&target_*`)兼容:解析后直接跳 candidates。
- `EvidenceTasksModule` 保留:工具栏 + 卡片网格 + 创建对话框 + 确认对话框。

### 6.3 左/右栏

- 左栏:Claim 面板保持现状(`ClaimSummaryPanel`),未选中对象时显示「点击任务卡片查看验证事实」空态。
- 右栏:已处理数据面板不变(一对一后每个已完成任务自然对应一条)。

### 6.4 前端类型与清理

- `PaperEvidenceTask` 增 `target_id`、`display_name_cn`、`display_name_en`、`display_confidence`(含来源标记)。
- `taskTitle` 的「N 个对象」分支废弃,`taskStatus.ts` 改用对象名拼接工具。
- `useEvidenceTaskItems` 保留供右栏/队列取数,其中面向中栏的全局多任务合并逻辑不再使用。

## 7. 错误处理

| 场景 | 行为 |
|---|---|
| 创建时对象全部 busy | 400「所有匹配对象已有活动佐证任务」,前端提示 |
| 部分对象 busy | 跳过并返回 `skipped_active_targets`;前端消息「已创建 N 个对象任务,跳过 M 个」 |
| 圈选 0 对象 | 400「无匹配对象」(现状) |
| 迁移重复执行/中断 | 幂等、逐任务事务、重跑续接(§4.3) |
| 镜像行被删除 | 标题回退快照 label →「类型中文 #短ID」;置信度「未评分」 |
| 卡片跳转目标无效 | candidates 模块现有 resolve 校验兜底(与数据中心入口行为一致) |
| 创建后后台执行失败 | 任务 failed,卡片「重试失败项」(端点不变) |
| 单行 display 解析异常 | 该任务回退兜底链,不影响列表整体返回 |

## 8. 测试计划

- **后端 pytest**:
  - `create_batch_task`:N 对象 → N 任务 × 1 item;target_id 落任务行;item 快照为实时值(非 UUID)。
  - `list_paper_evidence_tasks`:7 种 target_type 中英名+置信度解析(中文优先);镜像行缺失回退。
  - 迁移脚本:拆分、幂等、旧任务 cancelled+migrated_to、item 挂接、审计保留。
  - busy 三路径(全部 busy / 部分 busy / 0 对象)。
  - unified tasks label 变化。
- **前端 vitest**:
  - TaskCard 标题拼接(中英/单语/兜底)、name 备注、置信度格式(0 / 0.356 / null)。
  - 点击构造 hash 与数据中心入口一致(含 INITIAL_QUEUE_KEY);按钮不触发跳转。
  - 排序(状态组 + 置信度升序)、筛选 chips。
  - EvidenceCenterPage 布局断言更新。
- **验收**:后端 pytest 全绿;前端 `npm run build` 0 错误;迁移后页面卡片为对象名;点击跳转与数据中心一致。

## 9. 文件改动清单

| 文件 | 改动 |
|---|---|
| `backend/migrations/20260817_evidence_tasks_target_id.sql` | 新增 `target_id` 列(沿用日期命名惯例) |
| `backend/app/services/paper_evidence_service.py` | create_batch_task 一对一化;list_paper_evidence_tasks/get_batch_task 补 display 字段;新增 `mirror_live_display_name_parts` 中英双值解析 |
| `backend/app/routers/ontology.py` | POST /evidence/batch 响应与调度适配 |
| `backend/app/routers/unified_tasks.py` | `_paper_evidence` label 改对象名 |
| `backend/scripts/migrate_evidence_tasks_1to1.py` | 新增迁移脚本(§4.3) |
| `frontend/src/api/endpoints.ts` | PaperEvidenceTask 类型 + create 响应类型 |
| `frontend/src/pages/evidence-center/modules/EvidenceTasksModule.tsx` | 重写卡片(标题/跳转/排序/筛选),删除就地嵌入分支 |
| `frontend/src/pages/evidence-center/components/taskStatus.ts` | 对象名拼接工具,废弃「N 个对象」分支 |
| `frontend/src/pages/evidence-center/components/useEvidenceTaskItems.ts` | 保留供右栏/队列;移除中栏全局合并用法 |
| `frontend/src/pages/evidence-center/modules/EvidenceTasksModule.test.tsx` 等 | 测试更新(§8) |
| `frontend/src/styles.css` | 卡片标题/置信度/备注样式微调 |

## 10. 用户确认记录

- 「一个任务 = 一个对象」落**后端数据模型**(真正一对一)。
- 卡片标题:**中文为主 + 英文括号**,置信度副行大字。
- 存量多对象任务:**一次性拆分迁移**。
- 左栏:**改 Claim 面板**(选中对象后显示验证事实)。
- 中栏范围:**全部状态都显示**(处理中/待验证/已完成/失败)。
- 点击卡片:**跳转证据佐证页**(module=candidates),与数据中心入口一模一样。
