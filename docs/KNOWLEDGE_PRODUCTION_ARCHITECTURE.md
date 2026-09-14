# NeuroGraphIQ 知识生产架构（Knowledge Production Architecture）

> **状态**：Phase 1 冻结
> **权威数据库**：`neurographiq_human_brain_v1`（Gate7B 正式知识表）
> **这是新知识生产流水线的唯一权威设计文档。** 其他文档若与本文件冲突，以本文件为准。

## 0. 适用范围与取代关系

本文档取代 Gen-1 时代的流水线设计作为**新系统的架构权威**：

| 文档 | 状态 |
|---|---|
| `NEUROGRAPHIQ_KG_V3_TARGET_ARCHITECTURE.md` | **历史参考**：描述 Gen-1 的 Mirror → Final 分层，新系统不沿用 |
| `MIRROR_KG_AND_FINAL_PROMOTION_DESIGN.md` | 历史参考 |
| `MIRROR_KG_DEDUP_MERGE_PRINCIPLE.md` | 历史参考（写入时合并思想可借鉴，表结构不沿用） |
| `PAPER_EVIDENCE_WORKBENCH_DESIGN.md` | 历史参考（检索层可复用） |
| `MULTISCALE_GRANULARITY_ARCHITECTURE.md` | BR3 粒度层说明；粒度词表以本文 §6 为准 |

Gen-1 的 `candidate_*` / `mirror_*` / `final_*` 生产架构**不是**新系统需要保留的架构。
相关代码只允许以「通用 UI 组件 / provider 基础设施 / 文献检索基础设施 / 确定性工具 /
图可视化 / 校验设计思路 / 审计与幂等模式」这七类身份被复用。

---

## 1. 架构原则（Architecture Principles）

1. **单一事实源**：PostgreSQL `neurographiq_human_brain_v1` 是新系统唯一权威数据库。
   不存在运行时切库、不存在隐藏回退到遗留库名、不使用 Neo4j。
2. **Gate7B 正式表即正式知识**：`kg_entities` / `brain_regions` / `connections` /
   `circuits` / `functions` / `evidence` / `knowledge_assertions` 等表定义正式知识。
3. **Canonical-first**：正式知识身份必须建立在 canonical 实体上。任何正式实体都必须
   先有 canonical 身份，再谈内容。
4. **Circuit-first**：主要发现目标是围绕 BrainRegion 种子发现**神经回路**；
   Connection / Function / Evidence 是结构化的支撑知识，不是并列的一等目标。
5. **Evidence-centered**：知识必须可追溯到证据与来源。
6. **Knowledge = Claim + Evidence + Provenance**：三者缺一不构成知识。
7. **LLM 输出是候选知识，永远不是正式知识**。LLM Discovery 不得直接写入任何正式表。
8. **检索可以高召回，晋升必须保守**。
9. **Canonical identity 与 discovery provenance 是两个不同的概念**（见 §5）。
10. **动物证据可以支撑知识，但绝不能静默变成人类事实知识**。
11. **Projection ≠ Connection ≠ Pathway ≠ Circuit**。四者是不同概念，不得互相代替。
12. **多尺度知识用 hierarchy / mapping / aggregation 关系表达**，
    不要把每个 atlas 硬塞进同一条扁平层级。

---

## 2. 新生产流程（New Production Flow）

```
BrainRegion Seed
    ↓
Discovery Run
    ├── LLM Discovery
    └── Literature Discovery
    ↓
Raw Knowledge Candidates
    ├── Circuit Candidate
    ├── Connection Candidate
    ├── Function Candidate
    └── Related BrainRegion Candidate
    ↓
Evidence Binding
    ↓
Canonicalization
    ├── MERGE
    ├── CREATE
    ├── REJECT
    └── DEFER
    ↓
Validation / Review
    ↓
Promotion
    ↓
Gate7B Formal Knowledge Tables
```

**硬约束**：LLM Discovery **绝不能**直接插入任何正式表：

```
circuits
connections
functions
evidence
knowledge_assertions
```

LLM 只能产生 Raw Knowledge Candidate。从候选到正式表之间必须依次经过
Evidence Binding → Canonicalization → Validation → Promotion。

---

## 3. 两条发现路线（Two Discovery Routes）

两条路线独立并行、最终汇合于同一套候选与晋升层。

### Route A — LLM Discovery

```
BrainRegion Seed
    ↓
structured prompt
    ↓
candidate Circuits
candidate related BrainRegions
candidate Connections / steps
candidate Functions
    ↓
UNVERIFIED candidates
```

推荐溯源标记：

```
source_type      = LLM_GENERATED
evidence_status  = UNVERIFIED
knowledge_status = CANDIDATE
```

### Route B — Literature Discovery

```
BrainRegion Seed
    ↓
literature query generation
    ↓
PubMed / Europe PMC / OpenAlex / Semantic Scholar
    ↓
Publication identity resolution
    ↓
abstract / OA full text
    ↓
paragraph retrieval
    ↓
LLM extraction
    ↓
evidence-backed candidates
```

Route B 的候选天然带 Evidence Binding；Route A 的候选默认无证据，必须显式标注
`evidence_status = UNVERIFIED`。

### 未来可选路线（尚未实现）

```
Literature passages
    ↓
BioSEPBERT
    ↓
independent A -> B relation extraction
    ↓
cross-validation with LLM extraction
```

BioSEPBERT 目前**未实现**，本阶段不接入。

---

## 4. 证据模型（Evidence Model）

```
Publication
    ↓
Evidence Passage / Paragraph
    ↓
Knowledge Assertion
    ↓
supports / contradicts / qualifies
    ↓
Canonical Circuit / Connection / Function
```

三个必须区分清楚的概念：

| 概念 | 含义 |
|---|---|
| **Evidence Passage** | 源论文**实际说了什么**。必须指向真实源文本。 |
| **Knowledge Assertion** | 从证据**解读出的结构化主张**。 |
| **Canonical Entity** | 正式知识实体。 |

- 一段 Evidence Passage 可以支撑多条 assertion。
- 一个 canonical Connection / Circuit / Function 可以有多条 evidence 记录。
- 相似度匹配可以**帮助定位**原文，但正式的 Evidence Passage 必须指回真实源文本。

### 计划中的证据分级

```
DIRECT_EXPLICIT
DIRECT_PARTIAL
INDIRECT_HIERARCHY
BACKGROUND
CONTRADICTORY
INSUFFICIENT
```

**`INDIRECT_HIERARCHY` 绝不能静默变成直接证据。** 例如「A 属于额叶、额叶与 B 相连」
不能推出「A 与 B 直接相连」。

---

## 5. Canonical Identity 与 Provenance 分离

**Canonical identity 绝不能依赖**：

```
atlas
import batch
discovery run
prompt
model
publication
resource_id
```

以上全部属于 **provenance**。

示例：canonical Connection 身份主要由以下要素决定：

```
canonical source BrainRegion
canonical target BrainRegion
relation type
directionality
species / context（科学上必要时）
```

多次发现同一个事实应当**累积 provenance / evidence，而不是产生重复的正式实体**。

---

## 6. 统一粒度词表（Unified Granularity Vocabulary）

冻结 Gate7B 词表为唯一权威：

```
G1_MACRO
G2_MESO_ANATOMICAL
G3_MESO_FINE
G4_MICROSTRUCTURAL_FINE
```

前端展示可用：

```
G1 Macro
G2 Meso
G3 Fine
G4 Micro
```

以下遗留词表**不得**作为新的权威词表使用：

```
macro
meso
sub_connectivity
fine_cyto
molecular_attr
```

> **迁移方向**：全局粒度 Context（`useGlobalGranularity`）与 `config/granularity.ts`
> 目前仍使用遗留词表，**本轮不重构**。新模块（Knowledge Production）直接使用
> Gate7B 词表，不依赖全局 Context，也不引入第三套词表。

---

## 7. 工作台职责划分（Workbench Responsibility）

```
Knowledge Production Workspace
------------------------------
负责：
    BrainRegion seed 管理
    Discovery Runs
    LLM Discovery
    Literature Discovery
    Candidate knowledge
    Evidence binding
    Canonicalization review
    Validation
    Promotion

Graph Explorer
--------------
负责：
    浏览既有知识
    图谱展开
    过滤
    路径探索
    证据查看
```

**Graph Explorer 不得成为生产工作流引擎。** 可复用的图组件可以共享，但职责边界
不得跨越。

---

## 8. 复用 / 重建决策（Reuse / Rebuild Decisions）

### KEEP AS FOUNDATION

- Data Center 通用 UI 原语（`DataTable` / `States` / 分页 / 抽屉概念）
- Graph / Cytoscape 可视化与 Inspector 设计
- LLM Provider protocol / factory
- DeepSeek / Kimi transport
- LLM JSON 解析基础设施（`llm_json_utils`）
- 文献源客户端（Europe PMC / PubMed / OpenAlex / Semantic Scholar）
- OA 全文检索（`paper_fetch_service`）
- OA XML 段落解析（`oa_xml_parser`）
- 确定性段落检索（`paragraph_retrieval`）
- 源文段落校验（`verify_passage_against_source`）
- 纯函数式校验规则模式（`evidence_target_classifier` / `confidence_rules`）
- 只读工作流总览模式（`workbench_pipeline`）
- 审计 / 幂等设计原则
- 任务中心展示层（`BackgroundTaskCenter` / `taskRegistry` / `unified_tasks` 聚合器）

### REBUILD

- Discovery Run
- LLM Discovery 业务逻辑
- Literature Discovery 编排
- Raw Candidate 模型
- Evidence Binding
- Canonicalization
- Validation 编排
- Promotion
- **Gate7B 应用 API**（当前几乎为空）
- Knowledge Production Workspace

### LEGACY / REFERENCE ONLY

- Mirror 作为生产层
- 重复的 `final_*` 实体层
- 基于 `candidate_id` 的图导航
- 旧 LLM extraction task taxonomy
- 旧 composite workflow
- skip-existing Mirror 逻辑
- PEW `ranking_id` 作为主工作流身份
- 旧 field-completion 流水线作为架构

---

## 9. 计划中的生命周期状态（Planned Lifecycle Statuses）

> 本节只冻结**状态语义**。**本阶段不创建任何 DB schema。**

### RunStatus

```
QUEUED
RUNNING
COMPLETED
FAILED
CANCELLED
```

### CandidateStatus

```
RAW
RESOLVING
REVIEW_REQUIRED
VALIDATED
REJECTED
PROMOTED
```

### ReviewStatus

优先复用 Gate7B 已批准的评审词表（`gate7b_010_aggregation_mapping_review_lifecycle.sql`）：

```
pending
approved
rejected
uncertain
needs_revision
```

配套字段：`reviewed_by` / `reviewed_at`。

### Discovery task semantics

```
NOT_STARTED
DISCOVERING
RAW_COMPLETE
CANONICALIZING
REVIEW_REQUIRED
VALIDATED
COMPLETED
FAILED
NO_EVIDENCE_FOUND
```

**重要**：`NO_EVIDENCE_FOUND != NOT_PROCESSED`。
「查过但没找到证据」与「还没查」是两种不同状态，不得合并。

---

## 10. Phase 1 实现范围

本阶段只落地**只读基础**：

- 文档冻结（本文件）
- `GET /api/knowledge-production/brain-regions`（服务端分页 + 粒度/atlas/搜索过滤）
- `GET /api/knowledge-production/brain-regions/{entity_id}`
- 前端 `/knowledge-production` 路由与侧边栏入口
- BrainRegion seed 列表 + 工作区 7 个 tab（除 Overview 外均为只读空状态）
- 两个**禁用**的 Discovery 占位按钮

明确**未**实现（且不得伪造）：Discovery、Candidate 持久化、Canonicalization、
Validation、Promotion、任何 Discovery Run 表、任何 Discovery 状态字段。

### 当前 Gate7B 数据实况（Phase 1 起点）

| 表 | 行数 |
|---|---|
| `kg_entities` | 2,144 |
| `brain_regions` | 770 |
| `external_regions` / `region_mappings` | 686 / 686 |
| `brain_region_aggregation_mappings` | 707 |
| `connections` / `circuits` / `functions` / `evidence` | **0 / 0 / 0 / 0** |
| `publications` / `evidence_links` / `knowledge_assertions` | **0 / 0 / 0** |
| `relation_definitions` | **0** |

**两个已识别的启动依赖**：

1. `relation_definitions` 为空，而 `knowledge_assertions.predicate_pk` 是 NOT NULL FK
   —— 任何 assertion 写入前必须先 seed 谓词注册表。
2. 知识层（connections / circuits / functions / evidence）**表存在但无代码**，
   应用层目前只有 1 个未接线的 resolver。
