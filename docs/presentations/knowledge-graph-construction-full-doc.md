# NeuroGraphIQ KG V3 — 知识图谱构建过程（完整技术文档）

> 版本：2026-08-03 | 基于仓库实际代码与架构文档撰写

---

## 目录

1. [项目定位与设计目标](#1-项目定位与设计目标)
2. [知识体系架构](#2-知识体系架构)
3. [构建流水线总览](#3-构建流水线总览)
4. [第一阶段：资源导入与原始解析](#4-第一阶段资源导入与原始解析)
5. [第二阶段：候选生成](#5-第二阶段候选生成)
6. [第三阶段：规则校验与数据增强](#6-第三阶段规则校验与数据增强)
7. [第四阶段：LLM 知识提取](#7-第四阶段llm-知识提取)
8. [第五阶段：Mirror KG 治理](#8-第五阶段mirror-kg-治理)
9. [第六阶段：校验中心——三道闸门](#9-第六阶段校验中心三道闸门)
10. [第七阶段：晋升与 Final KG](#10-第七阶段晋升与-final-kg)
11. [知识消费与应用](#11-知识消费与应用)
12. [全链路溯源体系](#12-全链路溯源体系)
13. [技术架构与工程规模](#13-技术架构与工程规模)

---

## 1. 项目定位与设计目标

### 1.1 核心目标

NeuroGraphIQ KG V3 旨在构建**多粒度脑区知识图谱（Multi-granularity Brain Region Knowledge Graph）**。系统从多种脑图谱资源出发，经过确定性解析、LLM 辅助提取、Mirror KG 中转、人工审核、晋升等阶段，最终产出结构化的、可追溯的、可探索的知识图谱。

### 1.2 数据来源

系统关注的数据来源涵盖五个粒度层级：

| 粒度层 | 资源 | 数据规模 | 数据格式 |
|--------|------|----------|----------|
| **宏观临床层** (macro_clinical) | AAL3 Atlas | 166 ROI | XML |
| | Macro96 标准池 | 96 脑区 | Excel (.xlsx) |
| **中观解剖层** (meso_anatomical) | HCP-MMP | 待接入 | — |
| | Desikan / Destrieux (FreeSurfer) | 待接入 | — |
| **亚区连接层** (sub_connectivity) | Brainnetome Atlas | 待接入 | — |
| **细胞构筑层** (fine_cyto) | Julich-Brain (siibra) | 待接入 | — |
| **分子属性层** (molecular_attr) | Allen Human Brain Atlas | 待接入 | — |

### 1.3 设计原则（硬约束）

| # | 原则 | 说明 |
|---|------|------|
| 1 | **LLM 不能直接写入正式库** | 所有 LLM 输出只写 `llm_extraction_*` 和 `mirror_*`，禁止写 `final_*` |
| 2 | **所有外部资源必须先进入候选库** | 经 `file_registry` → `import_tasks` → `staging_*` 链路 |
| 3 | **规则校验和人工审核必须执行** | LLM 按风险启用，不得跳过审核步骤 |
| 4 | **正式库只接收通过审核的数据** | 当前主路径为 `final_*` 表族，`kg_*` 仅 legacy |
| 5 | **所有数据必须可追溯** | 保留 `source_atlas`、`source_version`、`source_file`、`import_batch_id` |
| 6 | **不同粒度独立隔离** | DB enum `granularity_level` + 前端 `/:granularity/:source/*` 路由隔离 |
| 7 | **跨粒度映射必须显式建模** | 专用 mapping 表，禁止字符串相似度隐式合并 |
| 8 | **LLM 输出标记来源和审核状态** | `raw_response` 完整保留，写入 `review_queue` |
| 9 | **全程记录日志** | `quality_reports`、`promotion_log`、`import_task_versions`、logger |

---

## 2. 知识体系架构

### 2.1 七层知识模型

Final KG 构建完成后，形成七层结构化的知识体系：

```
┌─────────────────────────────────────────────────────────────┐
│ 第一层：脑区实体层 (Region Layer)                              │
│ · AAL3 (166 ROI)、Macro96 (96 脑区)、Brainnetome 等          │
│ · 按 source_atlas、source_version、granularity 隔离          │
├─────────────────────────────────────────────────────────────┤
│ 第二层：连接层 (Connection Layer)                             │
│ · 同粒度脑区间连接：结构连接 / 功能连接 / 效应连接 / 投射 /   │
│   关联 / 共激活 / 不确定                                      │
│ · directionality: directed / undirected / bidirectional      │
├─────────────────────────────────────────────────────────────┤
│ 第三层：回路层 (Circuit Layer)                                │
│ · 多脑区有序回路：感觉回路 / 运动回路 / 边缘回路 /            │
│   认知控制回路 / 默认模式 / 突显网络 / 记忆回路                │
│ · 回路通过 circuit_step 分解为有序步骤                        │
├─────────────────────────────────────────────────────────────┤
│ 第四层：功能层 (Function Layer)                               │
│ · 功能可关联到脑区 (region_function)、连接 (projection_func)、 │
│   回路 (circuit_function)                                    │
│ · 功能类别：运动 / 感觉 / 视觉 / 听觉 / 语言 / 记忆 / 情绪 /  │
│   执行控制 / 注意 / 自主神经 / 默认模式 / 突显 / 奖赏          │
├─────────────────────────────────────────────────────────────┤
│ 第五层：证据层 (Evidence Layer)                               │
│ · 每条非平凡声明必须绑定证据文本、来源文档、LLM run 或         │
│   人工审核注释                                                │
│ · mirror_evidence_records → 完整溯源链                       │
├─────────────────────────────────────────────────────────────┤
│ 第六层：三元组层 (Triple Layer)                               │
│ · 统一 subject → predicate → object 查询面                   │
│ · final_kg_triples 表 — 确定性 Triple Consolidation 生成     │
├─────────────────────────────────────────────────────────────┤
│ 第七层：映射层 (Mapping Layer)                                │
│ · 跨图谱 / 跨粒度显式映射：exact_match / part_of / overlaps   │
│ · 专用 mapping 表，禁止字符串模糊匹配                          │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 五层粒度物理隔离

PostgreSQL 数据库 `NeuroGraphIQ_KG_V3` 按 schema 进行粒度物理隔离：

| Schema | 粒度族 | 当前状态 | 包含数据 |
|--------|--------|----------|----------|
| `macro_clinical` | 宏观临床层 | ✅ 已实现 | AAL3 166 ROI + Macro96 96 脑区，及其连接/回路/功能/三元组 |
| `meso_anatomical` | 中观解剖层 | 🚧 已预留 | HCP-MMP, Desikan 等 |
| `sub_connectivity` | 亚区连接层 | 🚧 已预留 | Brainnetome 连接网络 |
| `fine_cyto` | 细胞构筑层 | 🚧 已预留 | Julich-Brain 等 |
| `molecular_attr` | 分子属性层 | 🚧 已预留 | Allen Human Brain Atlas |
| `public` | 公共元数据 | ✅ | 跨 schema 共享配置、审计入口 |

**粒度隔离原则**：
- 同粒度内操作自由（连接提取、回路提取、功能提取等）
- 跨粒度关系必须通过显式 Mapping 记录
- 禁止基于名称相似度的自动跨粒度合并
- 禁止将不同粒度数据混入同一张万能表

---

## 3. 构建流水线总览

### 3.1 五阶段漏斗模型

```
                         数据量逐级收敛，质量逐级提升
                              ─────────────────→

┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐
│ 导入解析  │ → │ 候选生成  │ → │ 校验增强  │ → │ LLM提取  │ → │ 审核晋升  │
│ Import & │   │Candidate │   │Validate &│   │   LLM    │   │ Review & │
│  Parse   │   │   Gen    │   │ Enhance  │   │ Extract  │   │ Promote  │
└──────────┘   └──────────┘   └──────────┘   └──────────┘   └──────────┘
     │              │              │              │              │
     ▼              ▼              ▼              ▼              ▼
  raw_*表      candidate_*    validation_*   mirror_*表     final_*表
  staging_*     candidate_    enhance_*     llm_extract_*  final_kg_*
                pool                                         triples

  写边界:        写边界:        写边界:        写边界:        写边界:
  只写raw/staging 只写candidate  只写validation mirror/llm    只写final
  禁写final      禁写final      禁写final      禁写final      唯一入口
  禁写mirror                                    禁自动审核
```

### 3.2 写边界矩阵

这是系统最核心的治理约束。每个阶段只能写入指定范围，不能越界：

| 阶段 | 允许写入 | 严禁写入 |
|------|----------|----------|
| **Raw Parsing** | `raw_*`, `staging_*` | `final_*`, Mirror KG 任何表 |
| **Candidate Generation** | `candidate_brain_regions`, `candidate_pools` | `final_*` |
| **Rule Validation** | `rule_validation_runs`, `candidate_rule_validation_results` | `final_*` |
| **LLM Extraction** | `llm_extraction_runs`, `llm_extraction_items`, Mirror KG 全表（通过 `llm_to_mirror_service`） | `final_*`, 自动审核, 自动晋升, `kg_*` |
| **Mirror Governance** | Mirror 状态变更, `mirror_rule_validation_*`, `mirror_review_*` | `final_*` 直接写入 |
| **Human Review** | `mirror_human_review_records`, Mirror 编辑建议 | `final_*` 直接写入 |
| **Promotion** | `final_*` 全表 + `promotion_runs/records` | 绕过审核环节的数据 |

### 3.3 状态机流转

每个知识实体在构建过程中经历严格的状态变迁：

```
                    ┌─────────────────┐
                    │ mirror_candidate │  ← LLM 提取后自动生成
                    └────────┬────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │ llm_suggested    │  ← LLM 完成提取并写入 Mirror
                    └────────┬────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │ rule_checked     │  ← 规则校验通过
                    └────────┬────────┘
                             │
                             ▼
                    ┌──────────────────────┐
                    │ human_review_pending  │  ← 进入审核队列
                    └──────────┬───────────┘
                               │
                    ┌──────────┴──────────┐
                    ▼                     ▼
           ┌──────────────┐      ┌──────────────┐
           │human_approved │      │human_rejected │
           └──────┬───────┘      └──────┬───────┘
                  │                     │
                  ▼                     ▼
           ┌──────────────┐      ┌──────────────┐
           │promoted_to_   │      │  superseded   │
           │   final       │      └──────────────┘
           └──────────────┘
```

---

## 4. 第一阶段：资源导入与原始解析

### 4.1 资源登记 (Resource Registry)

所有脑图谱资源必须先在系统中注册，记录元信息：

**数据模型** (`atlas_resources` 表)：
- `name` — 资源名称（如 "AAL3"、"Macro96 Standard Pool"）
- `source_granularity` — 所属粒度层
- `source_version` — 资源版本号
- `description` — 资源描述
- `resource_type` — 资源类型
- `status` — 状态（active / archived / deleted）
- `metadata` — JSONB 扩展元数据

**API 端点**：
- `POST /api/resources` — 创建资源
- `GET /api/resources` — 列表（支持筛选、分页）
- `PUT /api/resources/{id}` — 更新
- `DELETE /api/resources/{id}` — 级联删除（强确认，预览影响范围）

### 4.2 文件管理

支持**双轨文件模式**：

| 模式 | 表 | 用途 |
|------|-----|------|
| **Resource File** | `resource_files` | 绑定到特定资源的权威源文件 |
| **Workspace File** | `workspace_files` | 工作区暂存文件，不绑定资源 |

**关键设计**：
- Workspace File 可通过 `attach-to-resource` 操作升级为 Resource File
- 两者之间的桥接是唯一的正式关联路径
- 文件支持上传、预览、下载、归档/恢复/删除

### 4.3 导入批次 (Import Batch)

导入批次是整个构建流程的**核心追踪单元**。

**数据模型** (`import_batches` 表)：
- `batch_id` — 批次唯一标识
- `resource_id` — 关联的资源
- `batch_name` — 批次名称
- `status` — 状态机：draft → queued → running → completed / failed / cancelled
- `config` — JSONB 配置（解析器选择、参数等）

**批次事件** (`import_batch_events` 表)：
- 记录 `queue` / `start` / `progress` / `complete` / `cancel` / `fail` 等事件
- 每事件附带时间戳和上下文 JSON

**批次文件绑定** (`import_batch_files` 表)：
- 绑定 Resource File 和/或 Workspace File
- 定义文件在批次中的角色：`label_dictionary` / `macro_region_pool_source` 等

**关键机制**：
- 解析器兼容性自动检查（AAL3 必须 XML，Macro96 必须 xlsx）
- 运行历史（每次 parse/generate/validate 操作都可追溯）
- 回滚机制（preview → 强确认 → execute，回滚记录写入 `import_batch_rollback_records`）

### 4.4 原始解析 (Raw Parsing)

解析器将原始文件格式转换为结构化的数据库行。

**AAL3 解析链路**：
```
AAL3 XML 文件
  → aal3_xml parser
  → raw_parse_runs (记录解析运行)
  → raw_aal3_region_labels (166 行)
    字段: label_index, label_name, hemisphere, structure_type, ...
```

**Macro96 解析链路**：
```
Brain volume list.xlsx (Sheet1, 96 行数据)
  → macro96_xlsx parser
  → raw_parse_runs (记录解析运行)
  → raw_macro96_region_rows (96 行)
    字段: pool_index, en_name, cn_name, laterality_inferred, ...
```

**解析器约束**：
- 解析器只写 `raw_*` 表，不能生成候选、不能触发 LLM、不能写 Mirror/Final
- 解析运行是**幂等**的 — 通过部分唯一索引防止重复解析
- `parse-macro96` 与 `parse-aal3` 是**独立的 run_type**，不能混用
- run_type 校验：错误 run_type → 400 错误

**解析器插件架构** (`backend/app/parsers/`)：
```
parsers/
├── base_parser.py        — 解析器基类
├── registry.py           — 解析器注册表
├── aal3_parser.py        — AAL3 通用解析
├── aal3_xml.py           — AAL3 XML 专项解析
├── brainnetome_parser.py — Brainnetome 解析（预留）
├── allen_parser.py       — Allen 解析（预留）
├── hcp_mmp_parser.py     — HCP-MMP 解析（预留）
├── freesurfer_parser.py  — FreeSurfer 解析（预留）
├── siibra_parser.py      — Julich-Brain 解析（预留）
├── terminology_parser.py — 术语解析（预留）
└── macro96_xlsx.py       — Macro96 Excel 解析
```

---

## 5. 第二阶段：候选生成

### 5.1 候选脑区生成

从原始解析结果出发，生成标准化的候选脑区记录。

**AAL3 候选生成**：
```
raw_aal3_region_labels (166 行)
  → generate-candidates (candidate_service.py)
  → candidate_brain_regions
    字段: name, semantic_id, source_atlas, source_version,
          source_granularity, hemisphere, region_type, ...
```

**Macro96 候选生成**：
```
raw_macro96_region_rows (96 行)
  → generate-macro96-candidates (macro96_candidate_service.py)
  → candidate_brain_regions
    字段: name, cn_name, pool_index, ...
```

**关键约束**：
- AAL3 和 Macro96 的 candidate generator 是**独立的、不可互换的**
- 使用错误的 generator → 400 错误
- 每条候选记录**完整溯源**：

```
candidate_brain_regions:
  · source_atlas        ← AAL3 / Macro96
  · source_version      ← 资源版本
  · source_granularity  ← macro_clinical
  · import_batch_id     ← 导入批次
  · resource_id         ← 资源 ID
  · file_registry_id    ← 源文件
```

### 5.2 候选池 (Candidate Pool)

候选池跨批次汇总候选脑区，为 LLM 批量提取提供统一的数据入口。

**数据模型**：
- `candidate_pools` — 池定义（名称、描述、粒度筛选条件）
- `candidate_pool_memberships` — 池成员（pool_id → candidate_brain_region_id）

**功能**：
- 跨批次累积候选
- 按粒度/图谱/批次筛选
- 批量选取送 LLM 提取
- 成员添加/移除

### 5.3 连接池 (Connection Pool)

与候选池类似，连接池汇总候选脑区对（pairs），为连接提取提供数据基础。

- `connection_pools` — 连接池定义
- `connection_pool_memberships` — 脑区对成员

---

## 6. 第三阶段：规则校验与数据增强

### 6.1 确定性规则校验

在候选数据进入 LLM 提取和 Mirror KG 之前，先经过**确定性规则校验**。这是不依赖 LLM 的纯逻辑校验，确保数据基本质量。

**规则体系（12 条电路校验规则）**：

| 类别 | 规则 | 检查内容 | 严重级别 |
|------|------|----------|----------|
| 完整性 | R1-R4 | 必填字段非空（name, source_atlas, granularity_level, semantic_id） | BLOCKER |
| 语义ID | R5-R6 | semantic_id 格式合法性、命名规范 | BLOCKER |
| 唯一性 | R7-R8 | 同图谱内候选不重复、semantic_id 唯一 | BLOCKER |
| 拓扑 | R9-R10 | 脑区间引用有效、circuit step 引用完整性 | BLOCKER |
| 溯源 | R11 | source_atlas / source_version / resource_id 齐全 | WARNING |
| 证据 | R12 | evidence_text 完整度、置信度范围 | WARNING |

**校验运行**：
- `rule_validation_runs` — 校验运行记录（run_id, batch_id, status, started_at, completed_at）
- `candidate_rule_validation_results` — 逐项结果（candidate_id, rule_name, passed, severity, detail）

### 6.2 Quality Score

在规则校验基础上，系统自动计算每个候选的**综合质量评分**（0-100 分）：

| 维度 | 权重 | 评分依据 |
|------|------|----------|
| 完整性 (Completeness) | 30% | 必填字段填充率 |
| 溯源 (Provenance) | 20% | source_atlas/version/resource_id/file 齐全度 |
| 拓扑 (Topology) | 20% | 脑区间引用有效性，circuit step 完整性 |
| 证据 (Evidence) | 20% | evidence_text 存在性、置信度合理性 |
| 区域关联 (Region Association) | 10% | 跨表引用关联完整性 |

**计算时机**：
- 规则校验完成后自动触发 `compute_quality_score`
- 分数存入 `mirror_region_circuits.quality_score`
- 前端通过 `QualityScoreBadge` 组件可视化展示

### 6.3 数据增强引擎 (Data Enhancement Engine)

在 Quality Score 评估后，对低质量数据执行分层增强：

```
候选回路 (Validation Run 产出)
        │
        ▼
  quality_score 计算 (加权评分)
        │
        ├── score ≥ 80 ──→ 质量合格，直接通过
        │
        └── score < 80 ──→ 进入增强流程
              │
              ├── Tier 1: 确定性自动修复
              │   · 补充缺失字段（标准化 atlas 名称）
              │   · 修复格式问题（semantic_id 标准化）
              │   · 修复拓扑引用（悬空引用 → 标记)
              │   · 不调 LLM，零成本，即时反馈
              │
              └── Tier 2: LLM 辅助增强 (DeepSeek)
                  · 调用 DeepSeek 分析数据问题
                  · 生成增强建议 → mirror_enhancement_suggestions
                  · 每条建议含：suggestion_type, target_field,
                    proposed_value, rationale, confidence
                  · 人工逐个 approve / reject
```

**增强建议表** (`mirror_enhancement_suggestions`)：
- `circuit_id` — 目标回路
- `suggestion_type` — 增强类型（field_completion / correction / enrichment）
- `target_field` — 目标字段
- `proposed_value` — 建议值
- `rationale` — 增强理由（LLM 生成）
- `confidence` — 建议置信度
- `status` — pending / approved / rejected
- `approved_by` / `approved_at` — 审核信息

**增强 API**：
- `POST /api/validation/circuit/{selection_id}/enhance` — 触发增强
- `GET /api/validation/circuit/{selection_id}/enhancements` — 查看建议
- `POST /api/validation/circuit/enhancements/{id}/approve` — 批准
- `POST /api/validation/circuit/enhancements/{id}/reject` — 拒绝

---

## 7. 第四阶段：LLM 知识提取

### 7.1 双 LLM 架构

系统通过 Provider 抽象层支持多 LLM 后端：

```
┌─────────────────────────────────────────┐
│           Provider 抽象层                 │
│    llm_providers/                        │
│    ├── base.py      — 协议定义           │
│    ├── factory.py   — Provider 工厂       │
│    ├── deepseek.py  — DeepSeek Provider  │
│    └── kimi.py      — Kimi/Moonshot      │
├─────────────────────────────────────────┤
│  · OpenAI-compatible SDK                 │
│  · API Key 后端环境变量，前端不可见       │
│  · 运行时切换 Provider/Model             │
│  · 所有调用 → llm_extraction_runs/items  │
│  · 原始输出 → raw_response 完整保留       │
└─────────────────────────────────────────┘
```

**支持的模型**：

| Provider | 模型 | 定位 | 适用场景 |
|----------|------|------|----------|
| DeepSeek | `deepseek-v4-pro` | 旗舰模型 | 复杂提取、增强 |
| DeepSeek | `deepseek-chat` | V3 通用模型 | 常规提取 |
| DeepSeek | `deepseek-reasoner` | R1 推理模型 | 疑难分析 |
| Kimi | Moonshot 系列 | 第二意见 | 双模型盲审、对照 |

### 7.2 提取能力矩阵

LLM 在同粒度范围内，从候选脑区出发，逐层构建知识关系。共 **7 种提取能力**：

```
                       ┌──────────────────┐
                       │   候选脑区实体     │
                       │  candidate_brain_ │
                       │    regions        │
                       └────────┬─────────┘
                                │
         ┌──────────────────────┼──────────────────────┐
         │                      │                      │
         ▼                      ▼                      ▼
┌─────────────────┐   ┌─────────────────┐   ┌─────────────────────┐
│ 1. 连接提取      │   │ 2. 功能提取      │   │ 3. 回路提取          │
│ (Connection     │   │ (Region         │   │ (Circuit            │
│  Extraction)    │   │  Function)      │   │  Extraction)        │
├─────────────────┤   ├─────────────────┤   ├─────────────────────┤
│ 输入: 候选脑区对  │   │ 输入: 候选脑区    │   │ 输入: 候选脑区 + 连接  │
│ 输出:           │   │ 输出:            │   │ 输出:                │
│  region pairs   │   │  function_term   │   │  circuit_name       │
│  connection_type│   │  function_domain │   │  circuit_type       │
│  directionality │   │  confidence      │   │  description        │
│  evidence_text  │   │  evidence_text   │   │  confidence         │
│  confidence     │   │                  │   │  evidence_text      │
├─────────────────┤   ├─────────────────┤   ├─────────────────────┤
│ 写入:           │   │ 写入:            │   │ 写入:                │
│ mirror_region_  │   │ mirror_region_   │   │ mirror_region_      │
│ connections     │   │ functions        │   │ circuits            │
└────────┬────────┘   └────────┬────────┘   └──────────┬──────────┘
         │                      │                       │
         ▼                      ▼                       ▼
┌─────────────────┐   ┌─────────────────┐   ┌─────────────────────┐
│ 4. 投射功能提取   │   │ 5. 回路功能提取   │   │ 6. 回路步骤提取       │
│ (Projection     │   │ (Circuit        │   │ (Circuit Step       │
│  Function)      │   │  Function)      │   │  Extraction)        │
├─────────────────┤   ├─────────────────┤   ├─────────────────────┤
│ 输入: 连接/投射   │   │ 输入: 回路        │   │ 输入: 回路 + 脑区      │
│ 输出:           │   │ 输出:            │   │ 输出:                │
│  function_term  │   │  function_term   │   │  step_order         │
│  function_domain│   │  function_domain │   │  step_type          │
│  confidence     │   │  confidence      │   │  description        │
│  evidence_text  │   │  evidence_text   │   │  confidence         │
├─────────────────┤   ├─────────────────┤   ├─────────────────────┤
│ 写入:           │   │ 写入:            │   │ 写入:                │
│ mirror_proj_    │   │ mirror_circuit_  │   │ mirror_circuit_     │
│ functions       │   │ functions        │   │ steps               │
└─────────────────┘   └─────────────────┘   └──────────┬──────────┘
                                                        │
                                                        ▼
                                              ┌─────────────────────┐
                                              │ 7. 三元组整合         │
                                              │ (Triple             │
                                              │  Consolidation)     │
                                              ├─────────────────────┤
                                              │ 输入: 所有 Mirror 对象 │
                                              │ 方式: 确定性转换       │
                                              │      (不调 LLM)      │
                                              │ 输出:                │
                                              │  subject_id         │
                                              │  predicate           │
                                              │  object_id           │
                                              ├─────────────────────┤
                                              │ 写入:                │
                                              │ mirror_kg_triples    │
                                              └─────────────────────┘
```

**关键设计约束**：
- 所有 LLM 提取在**同一粒度内**进行（Macro96↔Macro96, AAL3↔AAL3）
- 跨粒度的关系必须通过显式 Mapping 表
- 三元组整合是**确定性转换**（CONNECTION_TO_PREDICATE 映射表），不调 LLM
- 每次 LLM 调用产出 `llm_extraction_item`，保留 `raw_response`（完整 JSON）

### 7.3 复合工作流 (Composite Workflow)

LLM 提取不是单步操作，而是通过复合工作流编排的多阶段流水线：

```
Composite Workflow Run
    │
    ├── Step 1: 连接提取 + 功能提取
    │   ├── Pack 1: N 对候选脑区 → DeepSeek → 解析 → mirror_region_connections
    │   ├── Pack 2: N 对候选脑区 → DeepSeek → 解析 → mirror_region_connections
    │   └── ... Pack K
    │
    ├── Step 2: 回路提取 + 步骤提取
    │   ├── Pack 1: 脑区组 → DeepSeek → 解析 → mirror_region_circuits + steps
    │   └── ... Pack M
    │
    ├── Step 3: 投射提取
    │   ├── Pack 1: 连接组 → DeepSeek → 解析 → mirror_projection_functions
    │   └── ... Pack P
    │
    └── Step 4: 三元组整合
        └── 确定性转换 → mirror_kg_triples (不调 LLM)
```

**工作流特性**：

| 特性 | 说明 |
|------|------|
| **Pack 机制** | 大批量数据分 pack 处理，`pairs_per_pack` 可调（默认 20） |
| **Dry Run 预览** | 执行前预估 pack 数、token 总量、费用估算 |
| **Skip Existing** | 自动跳过已有 Mirror 记录，避免重复提取和浪费 |
| **暂停/取消/恢复** | `POST .../pause` / `POST .../cancel` / `POST .../resume` |
| **实时进度** | pack 级进度推送，`ProgressPanel` 实时显示 |
| **后台执行** | Workflow 在后台异步执行，前端通过轮询或 WebSocket 获取进度 |
| **事件日志** | `llm_workflow_event_log` 记录每一步的详细事件 |

**工作流 API**：
- `POST /api/llm-extraction/composite-workflow/run` — 创建并启动
- `GET /api/llm-extraction/composite-workflow/{run_id}` — 查询状态
- `GET /api/llm-extraction/composite-workflow/{run_id}/steps` — 步骤详情
- `POST .../pause` / `POST .../resume` / `POST .../cancel` — 控制

### 7.4 LLM → Mirror KG 写入链路

```
LLM API 调用
    │
    ├── llm_extraction_runs
    │   字段: run_id, run_type, provider, model, prompt_template,
    │         status, started_at, completed_at, token_usage, ...
    │
    ├── llm_extraction_items
    │   字段: item_id, run_id, input_data, raw_response (完整 JSON),
    │         parsed_output, status, confidence, error_message, ...
    │
    └── llm_to_mirror_service (确定性转换)
         │
         ├── _to_mirror_connection()
         ├── _to_mirror_region_function()
         ├── _to_mirror_circuit()
         ├── _to_mirror_circuit_step()
         ├── _to_mirror_projection_function()
         ├── _to_mirror_circuit_function()
         ├── _to_mirror_triple()
         └── _to_mirror_evidence()
              │
              ▼
         ┌─────────────────────────────┐
         │      Mirror KG 表族          │
         ├─────────────────────────────┤
         │ mirror_region_connections   │
         │ mirror_region_functions     │
         │ mirror_region_circuits      │
         │ mirror_circuit_steps        │
         │ mirror_circuit_functions    │
         │ mirror_projection_functions │
         │ mirror_kg_triples           │
         │ mirror_evidence_records     │
         └─────────────────────────────┘
         status: mirror_candidate → llm_suggested
```

**绝对不会发生的操作**：
- LLM 输出直接写入 `final_*` 表
- 自动审核（无需人工）
- 自动晋升（绕过人工闸门）
- 跨粒度自动合并

### 7.5 字段补全 (Field Completion)

针对已写入 Mirror KG 但字段不完整的记录，提供**异步字段补全**能力。

**补全流程**：
```
已有 Mirror KG 记录（部分字段为空）
    → 选取补全目标（连接/回路/投射功能/回路功能）
    → POST /api/llm-extraction/field-completion/run
    → 后台异步 DeepSeek 补全
    → mirror_* 记录更新，标记补全来源
    → formal_field_overlay 记录（展示用，非 final_*）
```

**补全范围**：
- 连接字段补全（connection_type, directionality, evidence_text）
- 回路字段补全（circuit_type, description, evidence_text）
- 回路步骤字段补全（step_type, role, description）
- 投射功能字段补全（function_domain, function_role, evidence_text）

---

## 8. 第五阶段：Mirror KG 治理

### 8.1 Mirror KG 定位

Mirror KG（镜像知识图谱）是**预正式知识中转层**。它不是简单的缓存，而是知识在进入 Final KG 之前的完整治理空间。

**为什么需要 Mirror KG？**

| 问题 | Mirror KG 如何解决 |
|------|-------------------|
| LLM 多 run / 多 pack 重叠提取，产生大量重复 | 写入时 Canonical Key 去重 |
| 不同时间重跑提取，版本差异无法追踪 | 高置信度合并 + 保留双溯源 + merge_history |
| 审核员面对大量重复行，无法区分"新增"vs"更新" | 唯一 canonical key → 自动合并 vs 跳过 vs 新增 |
| 晋升时不知道选哪条 | 去重后每条 canonical key 只有一条活跃记录 |

### 8.2 写入时去重合并

在每个 Mirror 实体写入时，执行**确定性去重合并算法**。

**Canonical Key 定义**：

| 实体类型 | Mirror 表 | Canonical Key | 特殊处理 |
|----------|-----------|---------------|----------|
| **连接** | `mirror_region_connections` | `(source_region_candidate_id, target_region_candidate_id, connection_type, directionality)` | 无向/双向连接时对 source 和 target **排序后**计算 |
| **脑区功能** | `mirror_region_functions` | `(region_candidate_id, function_term)` | 同一脑区不能有两个完全相同功能术语 |
| **投射功能** | `mirror_projection_functions` | `(projection_id, function_term_en)` | 同一连接不能有两个相同英文功能 |
| **回路** | `mirror_region_circuits` | `(circuit_name, source_atlas, granularity_level)` | 同图谱同粒度内回路名唯一 |
| **回路功能** | `mirror_circuit_functions` | `(circuit_id, function_term_en, function_domain, function_role)` | 同回路内四字段去重 |
| **回路步骤** | `mirror_circuit_steps` | `(circuit_id, step_order)` | 同回路内步骤序号唯一 |
| **三元组** | `mirror_kg_triples` | `(subject_id, predicate, object_id)` | 确定性，不去重 |

**无向连接排序算法**：
```python
if directionality in ("undirected", "bidirectional"):
    a, b = sorted((str(source_id), str(target_id)))
else:
    a, b = str(source_id), str(target_id)

canonical_key = (a, b, connection_type, directionality)
```

**合并策略**：
```
新提取结果 → 计算 canonical key
  → 查询 DB 中是否有相同 key 的现有行?
    ├── 不存在 → 直接 INSERT（新事实）
    │
    └── 存在 → 检查现有行状态:
        ├── 状态为 human_review_pending / human_approved /
        │       promoted_to_final / human_rejected / superseded
        │   → 跳过合并，单独 INSERT 为新行（已进入审核流程，不可自动修改）
        │
        ├── source_atlas 或 granularity_level 不同
        │   → 跳过合并，单独 INSERT（不同来源/粒度不可混）
        │
        └── 状态为 mirror_candidate / llm_suggested / rule_checked
            ├── 新置信度 > 旧置信度:
            │   → 更新字段值 → 旧行标记为 superseded_by_merge
            │   → provenance 追加: old_run_id + new_run_id
            │   → merge_history 记录此次合并
            │
            └── 新置信度 ≤ 旧置信度:
                → 不更新字段，新 run_id 追加到 provenance
                → 返回现有行
```

**合并时的字段处理**：
- `review_status` — 仅当旧状态为 pending 时才可能更新
- `promotion_status` — **永不修改**（晋升状态不可逆）
- Provenance JSON 包含:
  - `llm_run_ids[]` — 所有贡献 run 的 ID
  - `llm_item_ids[]` — 所有贡献 item 的 ID
  - `merge_history[]` — 历次合并记录
  - `previous_versions[]` — 被取代的旧版本 ID

### 8.3 Mirror 规则校验

Mirror KG 数据在进入人工审核前，通过 Mirror 专用规则校验。

**校验运行**：
- `mirror_rule_validation_runs` — 运行记录
- `mirror_rule_validation_results` — 逐项结果

**校验维度**：
- 字段完整性（非空检查）
- 引用完整性（外键有效）
- 逻辑一致性（连接方向与脑区一致性）
- 重复检测（相同 canonical key 的重复行）
- 置信度范围（0-1 合法性）

### 8.4 双模型盲审 (Dual Model Verification)

对于关键知识（回路、投射关系），系统执行双模型独立盲审：

```
同一 Mirror 数据项
        │
        ├───────────────────┐
        ▼                   ▼
┌──────────────┐    ┌──────────────┐
│   DeepSeek   │    │    Kimi      │
│  独立审核     │    │  独立审核     │
│              │    │              │
│ 审核维度:     │    │ 审核维度:     │
│ · 连接合理性  │    │ · 连接合理性  │
│ · 功能一致性  │    │ · 功能一致性  │
│ · 证据充分性  │    │ · 证据充分性  │
│ · 拓扑正确性  │    │ · 拓扑正确性  │
└──────┬───────┘    └──────┬───────┘
       │                   │
       ▼                   ▼
  审核结果 A           审核结果 B
  (verified/           (verified/
   rejected/            rejected/
   uncertain)           uncertain)
       │                   │
       └─────────┬─────────┘
                 ▼
        ┌─────────────────┐
        │    判决逻辑       │
        ├─────────────────┤
        │ consensus        │
        │ _supported       │
        │ → 双模型一致通过  │
        │ → 标记高置信度    │
        │ → 加速审核通道    │
        │                 │
        │ model_conflict   │
        │ → 双模型意见不一致│
        │ → 升级到人工裁决  │
        │ → 提供差异化分析  │
        │ → 标注分歧要点    │
        └─────────────────┘
```

**盲审约束**：
- 两模型**互相不可见**对方的审核结果
- 审核 prompt 完全相同（确保公平）
- 冲突时生成 `divergence_analysis`，标注两模型的分歧点

**数据记录**：
- `mirror_dual_model_verification_runs` — 运行记录
- `mirror_dual_model_verification_results` — 逐项结果

### 8.5 回路-投射交叉验证

确定性双向验证，**不调 LLM**：

```
正向推导 (方向 A)                          反向聚合 (方向 B)
──────────────────                        ──────────────────
回路 C: "Default Mode Network"            投射 P: "PCC → mPFC"
  │                                         │
  ├── step_1 → involves PCC                 ├── 推导: P 可能属于哪些回路?
  ├── step_2 → involves mPFC                │   → 检查 circuit_projection_
  ├── step_3 → involves IPL                 │     memberships 表
  └── step_4 → involves ...                 │   → 回溯: P 的来源回路
      │                                     │
      ▼                                     ▼
  推导投射:                                 推导回路:
  PCC→mPFC, mPFC→IPL, ...                  [回路C, 回路D, ...]
      │                                     │
      └──────────────┬──────────────────────┘
                     ▼
            ┌──────────────────┐
            │    交叉比对        │
            ├──────────────────┤
            │ 方向 A 推导的投射  │
            │   ∩              │
            │ 方向 B 聚合的回路  │
            │                  │
            │ ↓ 匹配 ↓         │
            │                  │
            │ bidirectionally_ │
            │ supported        │
            │ → 正反一致       │
            │                  │
            │ conflict         │
            │ → 不一致         │
            │ → 需要人工判断    │
            └──────────────────┘
```

**数据记录**：
- `mirror_circuit_projection_cross_validation_runs`
- `mirror_circuit_projection_cross_validation_results`

---

## 9. 第六阶段：校验中心——三道闸门

### 9.1 三道闸门架构

校验中心将 Mirror KG 数据通过三道独立闸门，确保进入 Final KG 的每条知识都经过充分验证：

```
                          Mirror KG 数据
                               │
          ┌────────────────────┼────────────────────┐
          ▼                    ▼                    ▼
  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐
  │   闸门 1     │    │   闸门 2     │    │   闸门 3     │
  │   规则校验    │    │  大模型校验   │    │  人工审核    │
  ├──────────────┤    ├──────────────┤    ├──────────────┤
  │ 方式: 确定性  │    │ 方式: LLM    │    │ 方式: 人工    │
  │ 不调 LLM     │    │ DeepSeek+    │    │ 领域专家      │
  │             │    │ Kimi         │    │              │
  ├──────────────┤    ├──────────────┤    ├──────────────┤
  │ 12 条规则    │    │ 双模型盲审    │    │ approve /    │
  │ Blocker →   │    │ consensus →  │    │ reject /     │
  │ 阻断+修复    │    │ 加速通道      │    │ request_     │
  │ Warning →   │    │ conflict →   │    │ changes      │
  │ 标记关注    │    │ 升级人工      │    │              │
  └──────┬───────┘    └──────┬───────┘    └──────┬───────┘
         │                   │                   │
         └───────────────────┼───────────────────┘
                             ▼
                    ┌─────────────────┐
                    │    Final KG     │
                    │  (三道全过)      │
                    │  缺一不可        │
                    └─────────────────┘
```

### 9.2 校验信息流

```
规则校验结果
    │
    ├── BLOCKER ──→ 阻断流程，必须修复
    │   ├── Tier 1 自动修复（确定性，零 LLM 成本）
    │   │   补充缺失字段 · 标准化名称 · 修复悬空引用
    │   └── Tier 2 LLM 增强（疑难问题）
    │       DeepSeek 分析 → 生成建议 → 人工 approve/reject
    │
    └── WARNING ──→ 不阻断，标记提醒审核员关注
         │
         ▼
大模型校验结果
    │
    ├── consensus_supported ──→ 绿色通道，加速审核
    └── model_conflict ──→ 升级到人工，标注分歧点
         │
         ▼
人工审核（最终裁决）
    │
    ├── approve ──→ 进入晋升队列
    │   └── 状态变为 human_approved
    │
    ├── reject ──→ 退回，记录拒绝原因
    │   └── 状态变为 human_rejected
    │
    └── request_changes ──→ 返回修改
        └── 附带修改建议
```

### 9.3 审核操作

人工审核员可以执行以下操作：

| 操作 | API | 效果 |
|------|-----|------|
| **查看审核队列** | `GET /api/mirror-kg/review/queue` | 返回 pending 状态的 Mirror 记录 |
| **查看详情** | `GET /api/mirror-kg/review/{id}` | 完整记录 + 溯源链 + 校验结果 + 盲审结果 |
| **批准** | `POST /api/mirror-kg/review/{id}/approve` | 状态 → human_approved，记录审核信息 |
| **拒绝** | `POST /api/mirror-kg/review/{id}/reject` | 状态 → human_rejected，必须填写拒绝原因 |
| **要求修改** | `POST /api/mirror-kg/review/{id}/request-changes` | 状态保持 pending，附带修改建议 |
| **标记不确定** | `POST /api/mirror-kg/review/{id}/mark-uncertain` | 标记为 uncertain，留待后续 |

---

## 10. 第七阶段：晋升与 Final KG

### 10.1 晋升机制

审核通过的 Mirror KG 数据通过 Promotion 服务写入 Final KG。

**晋升流转**：
```
Mirror KG (状态: human_approved)
    │
    ▼
Promotion 服务
    │
    ├── 预览 (Preview)
    │   · 列出所有待晋升记录
    │   · 显示转换映射
    │   · 报告潜在冲突
    │
    ├── 确认 (Confirm)
    │   · 强确认对话框
    │   · 显示影响范围
    │   · 不可逆警告
    │
    └── 执行 (Execute)
        · Mirror → Final 逐表转换
        · 记录 promotion_run / promotion_record
        · Mirror 状态 → promoted_to_final
        · 审计日志完整
```

**Mirror → Final 表映射**：

| Mirror 表 | → | Final 表 |
|-----------|---|----------|
| `mirror_region_connections` | → | `final_projections` |
| `mirror_region_functions` | → | `final_region_functions` |
| `mirror_region_circuits` | → | `final_region_circuits` |
| `mirror_circuit_steps` | → | `final_circuit_steps` |
| `mirror_projection_functions` | → | `final_projection_functions` |
| `mirror_circuit_functions` | → | `final_circuit_functions` |
| `mirror_circuit_projection_memberships` | → | `final_circuit_projection_memberships` |
| `mirror_kg_triples` | → | `final_kg_triples` |
| `mirror_evidence_records` | → | `final_evidence_records` |

**晋升约束**：
- 只有 `human_approved` 状态可晋升
- 强确认机制（预览 → 确认 → 执行），不可逆
- 晋升后 Mirror 记录标记为 `promoted_to_final`
- 完整 audit：`promotion_runs` / `promotion_records`
- `final_macro_clinical_promotion_runs` / `final_macro_clinical_promotion_records`

### 10.2 Final KG 三元组模型

Final KG 采用三层模型：

```
┌──────────────────────────────────────────────────────────┐
│                    第一层：实体层 (Nodes)                   │
│                                                          │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐ │
│  │ 脑区实体  │  │ 功能实体  │  │ 回路实体  │  │ 步骤实体  │ │
│  │ Region   │  │ Function │  │ Circuit  │  │  Step    │ │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘ │
│                                                          │
├──────────────────────────────────────────────────────────┤
│                    第二层：关系层 (Predicates)              │
│                                                          │
│  脑区 ──connects──→ 脑区     (6 种连接谓词)                │
│  脑区 ──has_function──→ 功能                            │
│  投射 ──has_projection_function──→ 功能                  │
│  回路 ──has_circuit_function──→ 功能                     │
│  回路 ──has_step──→ 步骤                                │
│  步骤 ──involves_region──→ 脑区                          │
│  回路 ──contains_projection──→ 投射                      │
│                                                          │
├──────────────────────────────────────────────────────────┤
│                    第三层：统一查询层                       │
│                                                          │
│  final_kg_triples (subject_id, predicate, object_id)     │
│  确定性 Triple Consolidation 生成，不调 LLM               │
└──────────────────────────────────────────────────────────┘
```

### 10.3 12 种标准谓词

| # | 谓词 (Predicate) | 中文含义 | 主体 (Subject) | 客体 (Object) |
|---|------------------|----------|----------------|---------------|
| 1 | `structurally_connects_to` | 结构连接 | 脑区 | 脑区 |
| 2 | `functionally_connects_to` | 功能连接 | 脑区 | 脑区 |
| 3 | `effectively_connects_to` | 效应连接 | 脑区 | 脑区 |
| 4 | `projects_to` | 投射 | 脑区 | 脑区 |
| 5 | `associated_with` | 关联 | 脑区 | 脑区 |
| 6 | `coactivates_with` | 共激活 | 脑区 | 脑区 |
| 7 | `has_function` | 区域功能 | 脑区 | 功能 |
| 8 | `has_projection_function` | 投射功能 | 投射 | 功能 |
| 9 | `has_circuit_function` | 回路功能 | 回路 | 功能 |
| 10 | `contains_projection` | 回路成员 | 回路 | 投射 |
| 11 | `has_step` | 回路步骤 | 回路 | 步骤 |
| 12 | `involves_region` | 步骤涉及脑区 | 步骤 | 脑区 |

**连接类型 → 谓词映射（确定性）**：
```python
CONNECTION_TO_PREDICATE = {
    "structural":      "structurally_connects_to",
    "functional":      "functionally_connects_to",
    "effective":       "effectively_connects_to",
    "projection":      "projects_to",
    "association":     "associated_with",
    "coactivation":    "coactivates_with",
    "uncertain":       "possibly_connects_to",
}
```

### 10.4 Triple Consolidation（三元组整合）

晋升后自动触发的确定性整合过程：

```python
def consolidate_triples():
    """
    从 Final KG 的所有实体表中确定性生成三元组。
    不调 LLM，纯 SQL 转换。
    """
    triples = []

    # 1. 连接 → 脑区间关系三元组
    for conn in final_projections:
        predicate = CONNECTION_TO_PREDICATE[conn.connection_type]
        triples.append(Triple(conn.source_id, predicate, conn.target_id))

    # 2. 区域功能 → 脑区-功能三元组
    for rf in final_region_functions:
        triples.append(Triple(rf.region_id, "has_function", rf.function_id))

    # 3. 投射功能 → 投射-功能三元组
    for pf in final_projection_functions:
        triples.append(Triple(pf.projection_id, "has_projection_function", pf.function_id))

    # 4-6. 回路相关三元组
    for cf in final_circuit_functions:
        triples.append(Triple(cf.circuit_id, "has_circuit_function", cf.function_id))
    for cs in final_circuit_steps:
        triples.append(Triple(cs.circuit_id, "has_step", cs.step_id))
        triples.append(Triple(cs.step_id, "involves_region", cs.region_id))
    for cm in final_circuit_projection_memberships:
        triples.append(Triple(cm.circuit_id, "contains_projection", cm.projection_id))

    return triples
```

---

## 11. 知识消费与应用

### 11.1 数据中心 (Data Center)

统一的四面板数据浏览系统：

| 面板 | 数据范围 | 操作 |
|------|----------|------|
| Raw | `raw_aal3_region_labels` + `raw_macro96_region_rows` | 查看、筛选 |
| Candidates | `candidate_brain_regions` + `candidate_pools` | 查看、筛选、批量选取 |
| Mirror KG | 全部 `mirror_*` 表族 | 浏览、编辑、删除、字段补全 |
| Final KG | 全部 `final_*` 表族 | 只读浏览、搜索 |

### 11.2 图谱探索 (Graph Explorer)

基于 D3.js 力导向图的知识图谱可视化：

- 节点按类型着色（脑区/功能/回路/步骤/投射）
- 边按谓词类型着色和虚实线区分
- 置信度映射为透明度
- 支持节点聚焦 (focus node)、展开/收起
- 图例面板

### 11.3 症状查询 (Symptom Query)

从临床自然语言症状出发，查询相关脑区和回路：

- 症状输入 → 标准化功能术语匹配（LLM 辅助）
- 功能 → 关联脑区/回路 → 图谱结果
- 生成临床报告（含关联分析和证据引用）
- 症状-回路图可视化

### 11.4 知识导出 (Export)

离线确定性导出，支持多种格式：

- `manifest.json` — 导出清单
- `nodes.jsonl` / `nodes.csv` — 节点文件
- `edges.jsonl` / `edges.csv` — 边文件
- Neo4j 兼容 CSV 格式（可选图数据库同步）

---

## 12. 全链路溯源体系

### 12.1 溯源链

Final KG 中任何一条知识都可以沿以下路径回溯到原始脑图谱资源：

```
Final KG 事实 (final_kg_triples / final_projections / ...)
    │
    ▼
promotion_record
    ├── promotion_run_id — 晋升批次
    ├── promoted_at — 晋升时间戳
    └── promoted_by — 操作者
        │
        ▼
mirror_human_review_record
    ├── reviewer — 审核员
    ├── action — approve / reject / request_changes
    ├── comment — 审核意见
    └── reviewed_at — 审核时间
        │
        ▼
mirror_rule_validation_result
    ├── rule_name — 规则名称
    ├── passed — 是否通过
    └── detail — 检查详情
        │
        ▼
llm_extraction_item
    ├── raw_response — LLM 原始 JSON 输出（完整保留）
    ├── confidence — 置信度
    └── parsed_output — 解析后的结构化数据
        │
        ▼
llm_extraction_run
    ├── provider — DeepSeek / Kimi
    ├── model — v4-pro / chat / reasoner
    ├── prompt_template — 使用的 prompt 模板
    └── token_usage — Token 用量
        │
        ▼
candidate_pool / connection_pool
    ├── pool_name — 候选池
    └── membership — 池成员关系
        │
        ▼
import_batch
    ├── batch_id — 导入批次
    ├── batch_name — 批次名称
    └── created_at — 创建时间
        │
        ▼
resource
    ├── name — 脑图谱资源名称
    ├── source_version — 版本
    └── source_granularity — 粒度层
```

**任何 Final KG 事实 → 7 步回溯 → 原始脑图谱资源出处。**

### 12.2 证据记录

每条 Mirror/Final 记录通过 `mirror_evidence_records` / `final_evidence_records` 保留完整的证据链：

```
evidence_records:
  · evidence_text      — 证据原文
  · source_document    — 来源文档标识
  · source_atlas       — 来源图谱
  · source_version     — 图谱版本
  · llm_run_id         — LLM 运行 ID
  · llm_item_id        — LLM 输出项 ID
  · review_record_id   — 审核记录 ID
  · promotion_run_id   — 晋升运行 ID
  · raw_response       — LLM 原始输出（JSONB）
  · confidence         — 置信度
  · provenance_chain   — 完整溯源链（JSONB）
```

---

## 13. 技术架构与工程规模

### 13.1 后端架构

```
backend/
├── app/
│   ├── main.py              — FastAPI 入口，注册 42 个路由器
│   ├── config.py            — 配置（DB URLs, LLM Keys, CORS）
│   ├── database.py          — 异步引擎，运行时 DB 切换
│   │
│   ├── models/              — SQLAlchemy ORM 模型 (34 个文件)
│   │   ├── resource.py, resource_file.py
│   │   ├── import_batch.py, raw_parsing.py, raw_macro96.py
│   │   ├── candidate.py, candidate_pool.py, connection_pool.py
│   │   ├── rule_validation.py, human_review.py, promotion.py
│   │   ├── llm_extraction.py, llm_field_completion.py
│   │   ├── llm_composite_workflow.py, llm_circuit_extraction.py
│   │   ├── mirror_kg.py, mirror_macro_clinical.py
│   │   ├── mirror_validation.py, mirror_review.py
│   │   ├── mirror_cross_validation.py, mirror_dual_model_verification.py
│   │   ├── mirror_promotion.py, mirror_enhancement_suggestion.py
│   │   ├── mirror_circuit_validation.py, mirror_circuit_correction.py
│   │   ├── final_kg.py, final_macro_clinical.py
│   │   └── molecular_circuit_candidate.py
│   │
│   ├── schemas/             — Pydantic 请求/响应模式
│   │
│   ├── routers/             — API 端点 (42 个文件)
│   │   ├── resources.py, resource_files.py, workspace_files.py
│   │   ├── import_batches.py, raw_parsing.py
│   │   ├── candidate.py, candidate_pool.py, connection_pool.py
│   │   ├── rule_validation.py, human_review.py, promotion.py
│   │   ├── llm_extraction.py, llm_circuit_extraction.py
│   │   ├── llm_field_completion.py, llm_composite_workflow.py
│   │   ├── llm_circuit_connection_extraction.py
│   │   ├── molecular_circuit_extraction.py
│   │   ├── mirror_kg.py, mirror_macro_clinical.py
│   │   ├── mirror_validation.py, mirror_review.py
│   │   ├── mirror_cross_validation.py, mirror_dual_model_verification.py
│   │   ├── mirror_promotion.py
│   │   ├── final_kg.py, final_kg_export.py
│   │   ├── final_macro_clinical_browser.py, final_macro_clinical_promotion.py
│   │   ├── validation_circuit.py, enhancement.py
│   │   ├── symptom_query.py, kg_graph.py
│   │   ├── settings.py, database_admin.py, system_admin.py
│   │   ├── workbench_pipeline.py, unified_tasks.py
│   │   └── file_normalization.py, pricing.py, dev_tools.py
│   │
│   ├── services/            — 业务逻辑 (88 个文件)
│   │   ├── resource_service.py, resource_delete_service.py
│   │   ├── import_batch_service.py, import_batch_rollback_service.py
│   │   ├── raw_parsing_service.py
│   │   ├── candidate_service.py, macro96_candidate_service.py
│   │   ├── candidate_pool_service.py, connection_pool_service.py
│   │   ├── rule_validation_service.py
│   │   ├── human_review_service.py, promotion_service.py
│   │   ├── llm_extraction_service.py
│   │   ├── llm_connection_extraction_service.py
│   │   ├── llm_function_extraction_service.py
│   │   ├── llm_circuit_extraction_service.py
│   │   ├── llm_circuit_step_extraction_service.py
│   │   ├── llm_circuit_projection_extraction_service.py
│   │   ├── llm_projection_function_extraction_service.py
│   │   ├── llm_circuit_function_extraction_service.py
│   │   ├── llm_composite_workflow_service.py
│   │   ├── llm_field_completion_service.py
│   │   ├── llm_to_mirror_service.py
│   │   ├── mirror_kg_service.py
│   │   ├── mirror_macro_clinical_service.py
│   │   ├── mirror_rule_validation_service.py
│   │   ├── mirror_dual_model_verification_service.py
│   │   ├── mirror_circuit_projection_cross_validation_service.py
│   │   ├── mirror_review_service.py
│   │   ├── mirror_promotion_service.py
│   │   ├── triple_consolidation_service.py
│   │   ├── final_kg_service.py, final_kg_export_service.py
│   │   ├── final_macro_clinical_browser_service.py
│   │   ├── final_macro_clinical_promotion_service.py
│   │   ├── enhancement_service.py, validation_state_machine.py
│   │   ├── molecular_circuit_extraction_service.py
│   │   ├── molecular_circuit_graph_engine.py
│   │   ├── molecular_circuit_module_classifier.py
│   │   ├── molecular_circuit_prompt_builder.py
│   │   ├── molecular_circuit_quality_gate.py
│   │   ├── molecular_circuit_datacenter_validator.py
│   │   ├── molecular_circuit_datacenter_writer.py
│   │   ├── field_completion_registry.py, field_completion_execution.py
│   │   ├── canonical_region_resolver.py, skip_existing_service.py
│   │   ├── execution_plan_builder.py
│   │   ├── database_admin_service.py, settings_service.py
│   │   ├── workbench_pipeline_service.py
│   │   └── llm_providers/ (base.py, factory.py, deepseek.py, kimi.py)
│   │
│   ├── parsers/             — 解析器插件
│   └── utils/               — 通用工具
│
├── migrations/              — 手写 SQL 迁移文件 (59 个)
└── tests/                   — 测试 (76 个文件, 1,173 个测试函数)
```

### 13.2 前端架构

```
frontend/src/
├── App.tsx                  — 主路由 (14 个路由)
├── pages/
│   ├── DashboardPage.tsx           — 仪表盘
│   ├── ResourcesPage.tsx           — 资源登记
│   ├── FilesPage.tsx               — 文件管理
│   ├── ImportBatchesPage.tsx       — 批次管理
│   ├── ImportPipelinePage.tsx      — 导入流程（已并入批次管理）
│   ├── LlmExtractionPage.tsx       — LLM 提取工作台
│   ├── DataCenterPage.tsx          — 数据中心
│   ├── MirrorKgPage.tsx            — Mirror KG（已重定向到数据中心）
│   ├── ValidationCenterPage.tsx    — 校验中心
│   ├── GraphExplorerPage.tsx       — 图谱探索
│   ├── Brain3DPage.tsx             — 3D 脑区
│   ├── SymptomQueryPage.tsx        — 症状查询
│   ├── BackgroundTaskCenter.tsx    — 后台任务
│   └── SettingsPage.tsx            — 设置
│
├── components/              — 可复用组件 (33 个)
└── hooks/                   — 自定义 Hooks
```

### 13.3 数据库

```
PostgreSQL: NeuroGraphIQ_KG_V3 (正式库)
    ├── Schema: macro_clinical
    ├── Schema: meso_anatomical
    ├── Schema: sub_connectivity
    ├── Schema: fine_cyto
    ├── Schema: molecular_attr
    └── Schema: public

PostgreSQL: neurographiq_kg_v3_mvp1_e2e (开发/测试库)
    └── 含 candidate + mirror + 临时 final_* 表

PostgreSQL: neurographiq_kg_v3_wb (工作台操作库)

PostgreSQL: NeuroGraphIQ_KG_Candidate (候选侧)
PostgreSQL: NeuroGraphIQ_KG_Unverified (待验证)
```

### 13.4 工程规模统计

| 维度 | 数值 |
|------|------|
| API 路由文件 | 42 |
| 服务模块 | 88 |
| 数据模型文件 | 34 |
| 解析器插件 | 10 |
| 数据库迁移 | 59 |
| 前端页面 | 14 |
| 前端页面组件文件 | 92 |
| 复用组件 | 33 |
| 测试文件 | 76 |
| 测试函数 | 1,173 |
| 架构文档 | 18 篇核心 + 49 篇 Spec/Plan |
| 总 Commit 数 | 209（含 207 次 2026.05 至今） |

---

## 附录：关键 API 前缀速查

| 前缀 | 模块 |
|------|------|
| `/api/resources` | 资源注册 |
| `/api/files` | 文件管理 |
| `/api/import-batches` | 导入批次 |
| `/api/raw-parsing` | 原始解析 |
| `/api/candidates` | 候选库 |
| `/api/rule-validation` | 规则校验 |
| `/api/human-review` | 人工审核 |
| `/api/promotion` | 晋升 |
| `/api/llm-extraction` | LLM 提取 + 复合工作流 |
| `/api/llm-extraction/field-completion` | 字段补全 |
| `/api/llm-extraction/circuit-extraction` | 回路提取 |
| `/api/llm-extraction/molecular-circuit` | 分子回路提取 v2 |
| `/api/mirror-kg` | Mirror KG CRUD |
| `/api/mirror-kg/validation` | Mirror 规则校验 |
| `/api/mirror-kg/review` | Mirror 人工审核 |
| `/api/mirror-kg/promotion` | Mirror → Final 晋升 |
| `/api/mirror-kg/dual-model-verification` | 双模型盲审 |
| `/api/mirror-kg/circuit-projection-cross-validation` | 交叉验证 |
| `/api/final-kg` | Final KG 只读查询 |
| `/api/final-macro-clinical` | Final Macro Clinical 浏览+晋升 |
| `/api/validation/circuit` | 电路校验 + 增强 |
| `/api/symptom-query` | 症状查询 |
| `/api/settings` | 系统设置 |
| `/api/database` | 数据库管理 |
