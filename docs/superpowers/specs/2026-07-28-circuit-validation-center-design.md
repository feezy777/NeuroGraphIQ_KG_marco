# 全粒度回路验证中心 — 设计文档

> **状态**: 待审批
> **日期**: 2026-07-28
> **范围**: 所有粒度（molecular_attr, macro, meso, sub_connectivity, fine_cyto）全部 Mirror KG 对象类型

---

## 1. 架构概览

```
Mirror KG 对象 (全粒度/全类型) + Molecular Circuit Candidates
  │
  ├─→ Phase 1: 确定性规则校验 (12 条规则)
  │     ├─ 通过 → Phase 2
  │     └─ 硬失败 → 拒绝 / 标记 blocked
  │
  ├─→ Phase 2: 双模型盲审 (Reviewer A + Reviewer B 并行)
  │     Reviewer A: 神经解剖学焦点
  │     Reviewer B: 功能/证据焦点
  │     ├─ 一致通过 → Phase 3
  │     ├─ 冲突 → 高优先级人工审核队列
  │     └─ 低证据 → 标记待补充
  │
  ├─→ Phase 3: 自动裁决 (规则引擎对比 Reviewer A/B 输出)
  │     基于: 一致性 / 置信度差值 / 证据等级
  │
  └─→ Phase 4: 人工审核 → Promotion (复用现有 mirror_review + mirror_promotion)
```

### 验证层级

| 层级 | 对象 | 触发方式 |
|---|---|---|
| **步骤级** | mirror_circuit_steps | 每个步骤独立校验 |
| **回路级** | mirror_region_circuits + mirror_molecular_circuit_candidates | 回路整体校验 |
| **运行级** | extraction run | 聚合报告 (pass rate, agreement rate, etc.) |

---

## 2. 确定性规则 (12 条)

### 硬失败 (Hard Failures — 阻塞)

| # | 规则标识 `rule_code` | 检查逻辑 |
|---|---|---|
| H1 | `REGION_IDENTITY` | 每个 node 的 region_id 必须在对应粒度的候选区或正式区表中存在 |
| H2 | `EDGE_EXISTENCE` | 每条 edge 的 edge_id 必须在原始图谱数据中真实存在 |
| H3 | `DIRECTION_CORRECT` | edge.source == 原始记录.source AND edge.target == 原始记录.target |
| H4 | `STEP_CONTINUITY` | step[i].target == step[i+1].source，断链即拒绝 |
| H5 | `CLOSED_LOOP` | 若标记 closed_loop=true，last.target 必须 == first.source |
| H6 | `PROVENANCE_COMPLETE` | resource_id → batch_id → llm_run_id 链条不可断裂 |
| H7 | `GRANULARITY_HOMOGENEITY` | 对象内所有节点同粒度 |

### 警告 (Warnings — 不阻塞)

| # | 规则标识 `rule_code` | 检查逻辑 |
|---|---|---|
| W1 | `TOPOLOGY_TYPE_VALID` | topology_type 在已知枚举中 |
| W2 | `CANONICAL_KEY_DUPLICATE` | canonical_key 去重 |
| W3 | `FIELD_COMPLETENESS` | name_en, name_cn, confidence, evidence_text 非空 |
| W4 | `IDEMPOTENCY` | 同一 canonical_key 重复写入时合并 (取高 confidence) |
| W5 | `LABEL_QUALITY` | 名称不含占位符 ("Step N", "Unknown", "R4 to R17" 等) |

**返回**: `validation_result_json` — `[{rule_code, severity, status, message}]`

---

## 3. 双模型盲审

### Reviewer A: 神经解剖学焦点

```
系统提示: 你是神经解剖学专家。只基于以下区域和连接数据给出判断，不推理功能。

输入:
- 回路拓扑 (nodes + edges): 包含区域名称、层信息、坐标
- 原始 evidence_text
- 区域映射 (candidate_id → formal_region_name)

输出 (JSON):
{
  "decision": "support" | "reject" | "uncertain",
  "confidence": 0.0-1.0,
  "anatomical_assessment": {
    "plausibility": "high" | "moderate" | "low",
    "region_role_correctness": [{step_index, role, assessment, reason}],
    "projection_direction_valid": [{edge_index, valid: bool, reason}],
    "naming_quality": "appropriate" | "needs_revision" | "incorrect",
    "suggested_name": "if naming_quality != appropriate"
  },
  "concerns": ["specific concern 1", "specific concern 2"],
  "recommendation": "accept_as_is" | "accept_with_name_change" | "reject"
}
```

### Reviewer B: 功能/证据焦点

```
系统提示: 你是神经科学功能专家。只基于证据和已知功能文献判断，不重复解剖分析。

输入:
- 回路拓扑 (nodes + edges)
- 原始 evidence_text
- functional_module 标签 (如有)

输出 (JSON):
{
  "decision": "support" | "reject" | "uncertain",
  "confidence": 0.0-1.0,
  "functional_assessment": {
    "coherence": "high" | "moderate" | "low",
    "evidence_support": "strong" | "moderate" | "weak" | "none",
    "overclaiming_detected": bool,
    "overclaiming_details": "if detected",
    "module_assignment": "correct" | "incorrect" | "uncertain",
    "confidence_calibration": "appropriate" | "overconfident" | "underconfident"
  },
  "concerns": ["specific concern 1"],
  "recommendation": "accept_as_is" | "accept_with_lower_confidence" | "reject"
}
```

**关键约束:**
- 两个 Reviewer 不能看到彼此的输出
- 不能添加、删除、重排、重定向回路步骤
- 并行调用，独立计费
- 每个 Reviewer 的结果存储到 `mirror_dual_review_results`

---

## 4. 自动裁决规则

| 条件 | 裁决结果 | 动作 |
|---|---|---|
| A.support + B.support + |confidence_diff| < 0.3 | **一致通过** | 标记 `adjudication: consensus_supported`，进入人工审核队列 (普通优先级) |
| A.support + B.support + |confidence_diff| ≥ 0.3 | **置信度分歧** | 标记 `adjudication: confidence_divergence`，进入人工审核 (中优先级) |
| A.reject AND B.reject | **一致拒绝** | 标记 `adjudication: consensus_rejected`，不回收到人工审核，直接标记为 rejected |
| A.reject XOR B.reject | **模型冲突** | 标记 `adjudication: model_conflict`，进入人工审核 (高优先级) |
| A.uncertain OR B.uncertain | **不确定** | 标记 `adjudication: insufficient_information`，进入人工审核 (中优先级) |
| 任一 confidence < 0.4 | **低证据** | 标记 `adjudication: low_evidence`，进入人工审核 (中优先级)，建议补充数据 |

**初始阶段不自动晋升** — 即使双模型均通过，也必须经过人工审核。

---

## 5. 数据模型

### 新表: `mirror_circuit_validation_runs`

```sql
CREATE TABLE mirror_circuit_validation_runs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  granularity_level TEXT NOT NULL,
  source_atlas TEXT,
  target_types TEXT[] NOT NULL DEFAULT '{}',  -- ['circuit','circuit_step']
  scope_json JSONB NOT NULL DEFAULT '{}',     -- {circuit_ids:[], step_ids:[], batch_ids:[]}
  
  -- Phase 1: rule validation
  rule_validation_status TEXT NOT NULL DEFAULT 'pending',  -- pending/running/completed/failed
  rule_total_count INTEGER DEFAULT 0,
  rule_passed_count INTEGER DEFAULT 0,
  rule_failed_count INTEGER DEFAULT 0,
  rule_warning_count INTEGER DEFAULT 0,
  rule_blocked_count INTEGER DEFAULT 0,
  rule_hard_failure_count INTEGER DEFAULT 0,
  
  -- Phase 2: dual review
  dual_review_status TEXT NOT NULL DEFAULT 'pending',  -- pending/running/completed/failed
  dual_review_total_count INTEGER DEFAULT 0,
  dual_review_agreement_count INTEGER DEFAULT 0,    -- both support
  dual_review_conflict_count INTEGER DEFAULT 0,     -- one support one reject
  dual_review_rejection_count INTEGER DEFAULT 0,    -- both reject
  dual_review_uncertain_count INTEGER DEFAULT 0,
  dual_review_low_evidence_count INTEGER DEFAULT 0,
  
  -- Phase 3: adjudication
  adjudication_status TEXT NOT NULL DEFAULT 'pending',
  
  -- Models used for review
  reviewer_a_provider TEXT NOT NULL DEFAULT 'deepseek',
  reviewer_a_model TEXT NOT NULL DEFAULT 'deepseek-chat',
  reviewer_b_provider TEXT NOT NULL DEFAULT 'kimi',
  reviewer_b_model TEXT NOT NULL DEFAULT 'kimi',
  
  -- Overall
  status TEXT NOT NULL DEFAULT 'created',  -- created/running/completed/partially_completed/failed/cancelled
  dry_run BOOLEAN DEFAULT FALSE,
  error_message TEXT,
  started_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

### 新表: `mirror_circuit_validation_results`

```sql
CREATE TABLE mirror_circuit_validation_results (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id UUID NOT NULL REFERENCES mirror_circuit_validation_runs(id) ON DELETE CASCADE,
  target_type TEXT NOT NULL,      -- 'circuit' | 'circuit_step' | 'molecular_candidate'
  target_id UUID NOT NULL,
  object_label TEXT,               -- human-readable label
  
  -- Phase 1 results
  rule_validation_result_json JSONB NOT NULL DEFAULT '[]',  -- [{rule_code, severity, status, message}]
  rule_overall_status TEXT,         -- 'passed' | 'warning' | 'failed' | 'blocked'
  rule_blocked BOOLEAN DEFAULT FALSE,
  
  -- Phase 2 results
  reviewer_a_decision TEXT,         -- 'support' | 'reject' | 'uncertain'
  reviewer_a_confidence DOUBLE PRECISION,
  reviewer_a_payload_json JSONB,
  reviewer_b_decision TEXT,         -- 'support' | 'reject' | 'uncertain'
  reviewer_b_confidence DOUBLE PRECISION,
  reviewer_b_payload_json JSONB,
  
  -- Phase 3: adjudication
  adjudication_status TEXT,         -- 'consensus_supported' | 'consensus_rejected' | 'confidence_divergence' | 'model_conflict' | 'insufficient_information' | 'low_evidence'
  adjudication_confidence_diff DOUBLE PRECISION,
  adjudication_summary TEXT,
  recommended_review_priority TEXT,  -- 'normal' | 'high' | 'urgent'
  
  -- Link to mirror review
  mirror_review_record_id UUID,    -- FK to mirror_human_review_records after human review
  
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

### 现有表复用

| 表 | 用途 |
|---|---|
| `mirror_rule_validation_runs` + `mirror_rule_validation_results` | 已有确定性规则校验，Phase 1 用 |
| `mirror_human_review_records` | 已有审核记录，Phase 4 用 |
| `mirror_promotion_runs` + `mirror_promotion_records` | 已有晋升管道，Phase 4 用 |
| `mirror_dual_model_verification_results` | 已有双模型验证结果，Phase 2 参考 (不直接复用) |

---

## 6. API 端点

### 新端点

| Method | Path | 说明 |
|---|---|---|
| **POST** | `/api/validation/circuit/runs` | 创建验证运行 (scope: circuit_ids, step_ids, batch_ids) |
| **POST** | `/api/validation/circuit/runs/{id}/start` | 启动验证流水线 (规则 → 双模型 → 裁决) |
| **GET** | `/api/validation/circuit/runs` | 分页列出验证运行 |
| **GET** | `/api/validation/circuit/runs/{id}` | 运行详情 + 统计 |
| **GET** | `/api/validation/circuit/runs/{id}/results` | 分页列出验证结果 |
| **GET** | `/api/validation/circuit/runs/{id}/progress` | 实时进度查询 |
| **POST** | `/api/validation/circuit/runs/{id}/cancel` | 取消运行 |
| **GET** | `/api/validation/circuit/queue` | 获取待验证对象队列 (聚合 mirror review queue + molecular candidates) |

### 复用端点

| Method | Path | 说明 |
|---|---|---|
| **POST** | `/api/mirror-kg/validation/run` | 执行确定性规则校验 |
| **POST** | `/api/mirror-kg/review/action` | 执行人工审核操作 |
| **POST** | `/api/mirror-kg/promotion/run` | 执行晋升 |
| **GET** | `/api/mirror-kg/dual-model-verification/runs` | 已有双模型验证运行列表 |

---

## 7. 状态转换

### 验证对象状态机

```
                    ┌─────────┐
                    │ pending │ (初始状态)
                    └────┬────┘
                         │ 执行规则校验
                    ┌────▼────┐
                    │ rule_   │
               ┌────┤ checked ├────┐
               │    └─────────┘    │
          硬失败             通过/警告
               │                  │
          ┌────▼────┐      ┌─────▼──────┐
          │ blocked │      │ dual_review │
          └─────────┘      │ _pending    │
                           └─────┬──────┘
                                 │ Reviewer A + B 并行
                           ┌─────▼──────┐
                           │ adjudicated│
                           └─────┬──────┘
                                 │
              ┌──────────────────┼──────────────────┐
              │                  │                  │
         consensus_        model_conflict    insufficient_
         supported         confidence_div    low_evidence
              │                  │                  │
              ▼                  ▼                  ▼
         human_review      human_review      human_review
         (normal)          (high)            (medium)
              │                  │                  │
              └──────────────────┼──────────────────┘
                                 │
                          ┌──────▼──────┐
                          │ approved /  │
                          │ rejected    │
                          └──────┬──────┘
                                 │ approved
                          ┌──────▼──────┐
                          │ promoted_to │
                          │ _final      │
                          └─────────────┘
```

### 验证运行状态

```
created → running → completed / partially_completed / failed / cancelled
```

---

## 8. 前端 UI 组件计划

### 文件结构

```
frontend/src/pages/validation-center/
├── ValidationCenterPage.tsx          # 入口 (重写)
├── ValidationWorkbench.tsx           # 统一工作台 (新建)
├── panels/
│   ├── ValidationOverviewPanel.tsx    # 总览仪表盘 (新建)
│   ├── ValidationRulePanel.tsx        # 规则校验面板 (新建)
│   ├── ValidationDualReviewPanel.tsx  # 双模型盲审面板 (新建)
│   ├── ValidationAdjudicationPanel.tsx # 自动裁决面板 (新建)
│   ├── ValidationHumanReviewPanel.tsx # 人工审核面板 (新建)
│   └── ValidationPromotionPanel.tsx   # 晋升面板 (现有, 改造)
├── components/
│   ├── ValidationStatsBar.tsx         # 统计栏 (新建)
│   ├── ValidationRunProgress.tsx      # 运行进度条 (新建)
│   ├── DualReviewComparison.tsx       # Reviewer A/B 对比视图 (新建)
│   ├── AdjudicationBadge.tsx          # 裁决结果标记 (新建)
│   ├── CircuitStepViewer.tsx          # 回路步骤查看器 (新建)
│   ├── EvidenceViewer.tsx             # 证据/溯源查看器 (新建)
│   └── PromotionConfirmDialog.tsx     # 晋升确认弹窗 (新建)
└── hooks/
    ├── useValidationRun.ts            # 验证运行状态 hook (新建)
    └── useValidationQueue.ts          # 验证队列 hook (新建)
```

### 总览仪表盘 (ValidationOverviewPanel)

```
┌─────────────────────────────────────────────────┐
│  [统计卡片行]                                     │
│  待校验 234 │ 规则通过 189 │ 双模型一致 145 │ 待审核 67 │ 已晋升 98 │
├─────────────────────────────────────────────────┤
│  [最近验证运行列表]                               │
│  run #42 | rule ✓ | dual 85% agree | 3 conflicts │
│  run #41 | rule ✓ | dual 92% agree | 1 conflict  │
├─────────────────────────────────────────────────┤
│  [快速操作]                                      │
│  [新建验证运行]  [查看所有运行]  [进入审核队列]      │
└─────────────────────────────────────────────────┘
```

### 规则校验面板 (ValidationRulePanel)

```
┌─────────────────────────────────────────────────┐
│  [运行选择: ▼ run #42]  [查看: ▼ 全部/阻塞/通过]   │
├─────────────────────────────────────────────────┤
│  ☐ 对象名             类型   结果  阻塞  警告  详情  │
│  ☑ 杏仁核回路         回路   ✓     0    2    👁   │
│  ☐ 视觉投射           连接   🚫    3    1    👁   │
│  ☐ 前额叶控制         回路   ⚠     0    4    👁   │
├─────────────────────────────────────────────────┤
│  点击 👁 → 展开规则详情面板                         │
│  ┌─────────────────────────────────────────────┐ │
│  │ H1 REGION_IDENTITY   ✓ 通过                  │ │
│  │ H2 EDGE_EXISTENCE    🚫 失败: edge_id X not found│
│  │ H4 STEP_CONTINUITY   ⚠ 警告: step 3→4 弱连接  │ │
│  └─────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────┘
```

### 双模型盲审面板 (ValidationDualReviewPanel)

```
┌─────────────────────────────────────────────────┐
│  对象: 杏仁核情绪回路  [Reviewer A] [Reviewer B] │
├─────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐              │
│  │ DeepSeek     │  │ Kimi         │              │
│  │ Decision: ✓  │  │ Decision: ✓  │              │
│  │ Conf: 0.82   │  │ Conf: 0.75   │              │
│  │──────────────│  │──────────────│              │
│  │ 解剖评估:     │  │ 功能评估:     │              │
│  │ Plaus: high  │  │ Coher: high  │              │
│  │ Role ✓       │  │ Evidence:    │              │
│  │ Direction ✓  │  │  moderate    │              │
│  │ Name: good   │  │ Overclaim: ✗ │              │
│  │ Concerns:    │  │ Module: ✓    │              │
│  │  - 跨物种推断 │  │ Concerns:    │              │
│  │              │  │  - 证据有限   │              │
│  └──────────────┘  └──────────────┘              │
├─────────────────────────────────────────────────┤
│  裁决: 🤝 一致通过 (Δconf = 0.07) → 人工审核      │
│  [查看裁决详情]                                   │
└─────────────────────────────────────────────────┘
```

---

## 9. 实现阶段

### Phase 1: 后端核心 (Week 1)
- 创建 `mirror_circuit_validation` 模型 + 迁移
- 创建 `mirror_circuit_validation_service.py` (Phase 1-3 编排)
- 创建 `mirror_dual_review_service.py` (双模型并行调用 + 裁决)
- 创建 `app/routers/validation_circuit.py` (API 端点)
- 扩展 `unified_tasks.py` 注册 `circuit_validation` 任务类型
- 测试: 规则校验 12 条、双模型并行、裁决逻辑

### Phase 2: 前端工作台 (Week 2)
- 重写 `ValidationCenterPage.tsx` — 单页工作台布局
- 创建 `ValidationOverviewPanel.tsx` — 仪表盘
- 创建 `ValidationRulePanel.tsx` — 规则校验面板
- 创建 `ValidationDualReviewPanel.tsx` — 双模型对比
- 创建 `DualReviewComparison.tsx` — 并排 Reviewer A/B
- 创建 `ValidationRunProgress.tsx` — 进度组件
- 接入 API、i18n、CSS

### Phase 3: 集成 + 测试 (Week 3)
- 分子候选池桥接到 review queue
- 晋升确认弹窗 + 事务安全
- E2E 测试: 完整流水线
- 运行级指标报告

---

## 10. 文件清单 (实现)

### 后端新建
```
backend/app/models/mirror_circuit_validation.py
backend/app/schemas/mirror_circuit_validation.py
backend/app/services/mirror_circuit_validation_service.py
backend/app/services/mirror_dual_review_service.py
backend/app/routers/validation_circuit.py
backend/app/routers/validation_dual_review.py
backend/migrations/20260728_circuit_validation.sql
backend/tests/test_circuit_validation.py
backend/tests/test_dual_review.py
```

### 后端修改
```
backend/app/main.py                     # 注册新 router
backend/app/routers/unified_tasks.py    # 注册 circuit_validation 任务类型
backend/app/routers/mirror_review.py    # 扩展 queue 过滤器支持 molecular candidates
```

### 前端新建
```
frontend/src/pages/validation-center/ValidationWorkbench.tsx
frontend/src/pages/validation-center/panels/ValidationOverviewPanel.tsx
frontend/src/pages/validation-center/panels/ValidationRulePanel.tsx
frontend/src/pages/validation-center/panels/ValidationDualReviewPanel.tsx
frontend/src/pages/validation-center/panels/ValidationAdjudicationPanel.tsx
frontend/src/pages/validation-center/panels/ValidationHumanReviewPanel.tsx
frontend/src/pages/validation-center/components/ValidationStatsBar.tsx
frontend/src/pages/validation-center/components/ValidationRunProgress.tsx
frontend/src/pages/validation-center/components/DualReviewComparison.tsx
frontend/src/pages/validation-center/components/AdjudicationBadge.tsx
frontend/src/pages/validation-center/components/CircuitStepViewer.tsx
frontend/src/pages/validation-center/components/EvidenceViewer.tsx
frontend/src/pages/validation-center/components/PromotionConfirmDialog.tsx
frontend/src/pages/validation-center/hooks/useValidationRun.ts
frontend/src/pages/validation-center/hooks/useValidationQueue.ts
frontend/src/pages/validation-center/validationCenterTypes.ts  # 扩展
frontend/src/api/endpoints.ts                                    # 添加新端点
frontend/src/i18n.ts                                             # 添加翻译
frontend/src/styles.css                                          # 添加样式
```

### 前端修改
```
frontend/src/pages/validation-center/ValidationCenterPage.tsx   # 重写
frontend/src/pages/validation-center/ValidationCenterTabBar.tsx # 调整 Tab
frontend/src/pages/validation-center/panels/ValidationMirrorPanel.tsx # 改造
```

---

## 自检

- ✅ 无 TBD/TODO
- ✅ 规则、模型、API、UI 全部定义
- ✅ 状态机完整
- ✅ 复用现有基础设施 (review, promotion, validation)
- ✅ 三个验证层级 (step/circuit/run)
- ✅ 所有粒度覆盖
- ✅ 分子候选池桥接方案

---

*请审阅此设计文档。审批后进入 writing-plans 阶段生成实现计划。*
