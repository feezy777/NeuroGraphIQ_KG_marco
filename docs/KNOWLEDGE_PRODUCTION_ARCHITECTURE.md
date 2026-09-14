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
不得跨越。工作区页面的具体信息架构见 §8。

---

## 8. BrainRegion-centered Workspace Model（Phase 1B 冻结）

Phase 1 把三个不同维度混在一页里：**A 脑区选择**、**B 知识对象类型**
（Circuit / Connection / Function / Evidence）、**C 工作流阶段**（Discovery /
Canonicalization / Validation / Promotion）。Phase 1B 将其拆分。

```
/knowledge-production
        ↓
BrainRegion Production Index
        ↓  点击一个脑区
/knowledge-production/brain-regions/{entity_id}
        ↓
BrainRegion Workspace
```

**一个 BrainRegion Workspace 代表一个 canonical Gate7B 脑区的完整生产生命周期。**
「一脑区一页面」指的是**一个动态 React workspace 组件**，不是「一个脑区一个源文件」。

### 8.1 Knowledge Production Index

职责：

- 浏览 BrainRegion
- G1 / G2 / G3 / G4 过滤
- Atlas 过滤
- 搜索
- （未来）生产状态总览
- （未来）candidate / evidence / review 计数
- 进入某个 BrainRegion workspace

**Index 不得包含整个生产工作流。** 它只负责「选择与进入」。

### 8.2 BrainRegion Workspace

一个 canonical BrainRegion 是**操作根**。

路由：

```
/knowledge-production/brain-regions/{entity_id}
```

顶层 workspace tabs（**恰好七个**）：

```
Overview
Discovery
Candidates
Evidence
Canonicalization
Validation
History
```

**Candidate 子类型属于 Candidates 内部**：

```
Candidates
    ├── Circuits
    ├── Connections
    ├── Functions
    └── Related Regions
```

**不得**把 Circuits / Connections / Functions 放在与 Discovery / Validation
**同一层级**。

**Promotion 不是常驻顶层 tab。** 它将来是「验证通过后的受治理动作」，
其结果体现在 History / Overview 中。

Graph Explorer 保持独立（见 §7）。

### 8.3 路由身份

公开路由身份 = **BrainRegion `entity_id`**（例：`NGIQ-BR-00000001`）。

**禁止**在公开 URL 中使用：

```
candidate_id
mirror id
final id
entity_pk
```

`entity_pk` 仅作为内部数据库标识。

### 8.4 Phase 1B 状态占位

生产层表尚不存在，因此：

- Index 的 Production 列显示**非持久化**的中性占位（`未初始化`）
- Workspace 的生产汇总区对无权威计数的项显示 `—`，**不显示 `0`**
- 工作流步骤**全部为未激活**（没有 Discovery Run 存在）
- **不得伪造** completed / pending / discovered 状态

---

## 9. 复用 / 重建决策（Reuse / Rebuild Decisions）

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

## 10. 计划中的生命周期状态（Planned Lifecycle Statuses）

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

## 11. Phase 1 实现范围

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

---

## 12. BrainRegion Workspace Visual Contract（Phase 1C 冻结）

本节只约束**呈现**，不改变任何信息架构。任何后续改动若违反下列 8 条，必须先修改本节。

| # | 规则 | 理由 |
|---|---|---|
| 1 | Index 与 Workspace **必须**渲染在同一个 `WorkbenchLayout` 内（顶栏 / 左导航 / 内容区 / 全局间距）。**禁止**为 workspace 另建 app shell 或旁路布局。 | 两个路由是同一产品的两个层级，不是两个应用。 |
| 2 | 样式只有**一处**模块级引入（`App.tsx` 引入 `pages/knowledge-production/knowledge-production.css`）。该文件只拥有 `.kp-*` 命名空间；表格 / 徽章 / 按钮 / Tab / 筛选 一律复用 `styles.css` 既有类。**禁止**新调色板、**禁止**第二个布局系统。 | 一次引入覆盖两个路由；颜色与控件语言保持一致。 |
| 3 | Index 汇总区固定为 **Total + G1–G4 五张卡**。五张卡共用一套视觉族，**只有 Total 使用强调色**（表示聚合），G1–G4 保持中性。 | 层级来自对比，不来自五种无关颜色。 |
| 4 | 生产状态一律**中性呈现**：`未初始化` 与 `Not initialized` 用中性灰徽章 / 文本，**不得**表达为 warning / error；无权威计数时显示 `—`，**永不显示 `0`**。 | 中性状态 ≠ 异常状态；`0` 会被误读为已确认的权威计数。 |
| 5 | Workspace 身份头层级固定：**英文名 = 主 H1** → 中文名 = 次级 → `entity_id` = 小号等宽 → 其余元数据 = **离散 chips**。元数据**禁止**拼接成单一字符串（如 `G3_MESO_FINEleftHuman…`）。 | 每个字段必须可单独识别、单独复制的权威值。 |
| 6 | 生命周期固定为 **4 个工作流步骤 × 7 个 Tab**。Discovery Run 尚不存在时，**不得有任何步骤处于 active / done**；Circuits / Connections / Functions 只能作为 Candidates 的**内部**子类，**不得**提升为顶层 Tab；Promotion 不得成为 Tab。 | 步骤与 Tab 是冻结的信息架构，不是装饰。 |
| 7 | 除 Overview 外的每个 Tab 必须是**有意的空状态**：图标 + 标题 + 说明 + 未来内容。**禁止**只写 “Phase 1 未实现”。 | 空状态要解释该 Tab 的用途，而不是宣告缺失。 |
| 8 | 1280–1920px 桌面为基准：**不得**出现横向溢出、Tab 挤压、卡片出界或元数据拼接；切换 Tab **不得**引起布局跳动（面板预留高度）。页面高度由**内容**决定并交给 `.main` 滚动——**禁止**让 flex 压缩子元素（曾导致 Tab 条塌陷为 ~1px 而无法点击）。 | 由视口高度触发的 flex 压缩是隐蔽缺陷；内容必须能滚动，不能被压扁。 |

**已拒绝的越界建议**（记录以备后续判断，Phase 1C 未采纳）：
为汇总卡引入多色分类、把 Production 占位改成进度条、为未来 Tab 预置假数据或伪计数、
将 Workspace 拆成独立布局或引入 UI 组件库（Tailwind / Ant Design / MUI / Bootstrap）。

### 12.1 界面语言（Phase 2B.1）

**界面语言是呈现层关注点；canonical / API / DB 词表保持语言中立且稳定。**

- 全局**唯一**语言权威是既有 i18n 模块（`i18n.ts` + `I18nProvider`）。
  **禁止**再建第二套 i18n 系统或第二套 locale 状态。
- 支持且仅支持 `zh-CN` / `en-US`，默认 `zh-CN`，持久化于
  `localStorage['neurographiq.language']`（复用既有键，不新增键）；
  非法值回退 `zh-CN`。
- 组件的 `label` 一律改为 `labelKey` + `t(key)`；**禁止**在 JSX 内写
  `locale === 'zh-CN' ? ... : ...`，**禁止**硬编码用户可见文案。
- **业务逻辑永远比较原始枚举值**，绝不比较翻译后的文本：
  `run.status === 'COMPLETED'`、`discovery_type === 'LLM_DISCOVERY'` 等。
- 永不翻译：`NGIQ-*` id、`run_id`、UUID、PMID / DOI、NCBI taxon、
  Gate7B 枚举值（`G1_MACRO`…）、canonical Atlas 名称、provider / model 名。
  只翻译它们的**标签**。
- 脑区名称按语言分主次（`name_zh` / `name_en`），另一方作为次级名称**始终保留**；
  首选名为空时回退另一方。
- 切换语言**不得**引起页面重载、路由变化、脑区切换或 Tab 复位。

**已知遗留（I18N_DEBT，本轮未处理）**：全局顶栏的粒度切换仍使用
Gen-1 词表（`Macro` / `Meso` / `Subregion` / `Cyto` / `Molecular`），
它仍驱动旧业务逻辑（`granularityToFamily`），因此**不得**在本轮做全局粒度重构
（`DEFERRED_GRANULARITY_MIGRATION`）。`validationCenter.*` 的 15 个 en-US 键缺失、
以及 Knowledge Production 之外的历史页面文案未双语化，同样属于遗留债务。

---

## 13. Discovery Run Contract（Phase 2A 冻结）

**Discovery Run = 对**一个** canonical BrainRegion seed 发起**一次**候选知识发现尝试的记录。**

它是**工作流 / 溯源（workflow / provenance）**，**不是知识**。
它本身**永远不代表** Circuit / Connection / Function / Evidence / Knowledge Assertion。

### 13.1 单一运行模型（两条路线共用）

```
        BrainRegion Seed
              ↓
         Discovery Run          ← knowledge_discovery_runs（唯一一张表）
           /        \
  LLM_DISCOVERY   LITERATURE_DISCOVERY
```

**禁止**建立 `llm_discovery_runs` / `literature_discovery_runs` 等按路线分表的模型。
两条路线共用同一生命周期与同一状态机，差异只体现在**可空的路线溯源列**上。

### 13.2 冻结词表

| 维度 | 冻结取值 | 说明 |
|---|---|---|
| `discovery_type` | `LLM_DISCOVERY` / `LITERATURE_DISCOVERY` | 发现路线 |
| `status` | `QUEUED` / `RUNNING` / `COMPLETED` / `FAILED` / `CANCELLED` | **执行**生命周期，默认 `QUEUED` |
| `outcome`（可空） | `CANDIDATES_FOUND` / `NO_CANDIDATES_FOUND` / `NO_EVIDENCE_FOUND` | **科学**结果，仅对已结束的 run 有意义 |

### 13.3 `status != outcome`（必须区分）

`status` 描述**执行**，`outcome` 描述**科学结果**。二者语义正交：

| 记录 | 含义 |
|---|---|
| `status=COMPLETED`, `outcome=NO_EVIDENCE_FOUND` | 跑完了，且“没有证据”**本身就是一个有效答案** |
| 从未处理（无 run） | 该脑区尚未进入发现流程 |
| `status=FAILED` | 执行失败——**不是**科学结论 |

把 `NO_EVIDENCE_FOUND` 与 “未处理” / “执行失败” 混为一谈是**科学错误**。

### 13.4 与其他状态机隔离

Discovery 的 `status` / `outcome` **不得**与后续阶段的
`CandidateStatus` / `ValidationStatus` / `PromotionStatus` 混用、复用或相互赋值。
它们属于不同的层，各有自己的词表。

### 13.5 三层分离（不得混淆）

| 层 | 载体 | 性质 |
|---|---|---|
| 工作流 / 溯源 | **Discovery Run** | 一次尝试的记录，非知识 |
| 待审知识 | 未来 Candidate | 抽取出的**提议**知识 |
| 正式知识 | Gate7B canonical Entity | 已接受的**权威**知识 |

### 13.6 身份约定（Phase 2A 实测 schema 决定）

`knowledge_discovery_runs.run_id` 使用 **UUID**（`gen_random_uuid()`），**不是** `NGIQ-*` id：

- 本仓库**工作流层**（`import_batches` / `raw_parse_runs`）使用 UUID；
  **科学层**（`kg_entities` / `brain_regions` / `connections`）使用 `BIGSERIAL` + `NGIQ-*` 公开 id。
  Discovery Run 属于**工作流层**。
- `infra.next_ngiq_id()` 是**冻结的 29 类实体登记表**（fail-closed）。
  把 run 加进该表等于把工作流层并入 canonical 知识层——**禁止**。
- 因此 run 的公开身份在结构上**不可能**被误认为一个 canonical 实体 id。

内部身份仍遵循 Gate7B 的 `*_pk` / `*_id` 命名：`run_pk`（BIGINT 主键）/ `run_id`（UUID 公开 id）。
FK 一律引用内部 `*_pk`，绝不引用 `*_id`。

### 13.7 Phase 2A 边界

本阶段**只**建立持久化与只读查询：建表、只读 service、只读端点。
**不**执行任何发现路线，**不**调用 LLM，**不**检索文献，**不**产生候选。
`create / start / complete / fail / cancel` 等受控状态迁移属于 **Phase 2B**。

---

## 14. Discovery Run Lifecycle（Phase 2B 冻结）

本阶段**只**实现受控状态迁移。**不**执行发现：**不**调用 LLM、**不**检索文献、
**不**产生候选、**不**绑定证据。

### 14.1 冻结状态图

```
CREATE
  ↓
QUEUED ──start──→ RUNNING ──complete──→ COMPLETED
   │                  ├──fail──────→ FAILED
   │                  └──cancel────→ CANCELLED
   ├──fail──────→ FAILED
   └──cancel────→ CANCELLED
```

| 迁移 | 合法来源 | 结果 |
|---|---|---|
| `create` | — | `QUEUED` |
| `start` | `QUEUED` | `RUNNING` |
| `complete` | `RUNNING` | `COMPLETED` |
| `fail` | `QUEUED` \| `RUNNING` | `FAILED` |
| `cancel` | `QUEUED` \| `RUNNING` | `CANCELLED` |

**终态**：`COMPLETED` / `FAILED` / `CANCELLED` —— **不可变**。
终态**没有**任何出边；`COMPLETED → start`、`FAILED → complete`、
`CANCELLED → cancel` 一律 **409**。

**幂等**（不产生新写入，返回当前 run，HTTP 200）：
`start` 于 `RUNNING`；`complete` 于 `COMPLETED` 且 outcome 相同；
`fail` 于 `FAILED` 且 error_code/error_message 相同；`cancel` 于 `CANCELLED`。
同终态但**载荷不同**（如 `COMPLETED` 换一个 outcome）→ **409**。

**禁止**：从 `QUEUED` 直接 `complete`（必须先 `start`）；
任何终态重开。**暂不实现 retry** —— 未来的重试创建**新 run**，而不是重开终态 run。

### 14.2 status / outcome 语义（Phase 2A §13.3 的强化）

| status | outcome |
|---|---|
| `COMPLETED` | **必须**非空 |
| 非 `COMPLETED` | **必须**为 `NULL` |

**路线兼容性**（属于 lifecycle service，**不**做成 SQL 约束）：
`discovery_type` 与 `outcome` 的合法组合取决于发现路线：

| discovery_type | 允许的 outcome |
|---|---|
| `LLM_DISCOVERY` | `CANDIDATES_FOUND` / `NO_CANDIDATES_FOUND` |
| `LITERATURE_DISCOVERY` | `CANDIDATES_FOUND` / `NO_CANDIDATES_FOUND` / `NO_EVIDENCE_FOUND` |

`LLM_DISCOVERY` **不得**以 `NO_EVIDENCE_FOUND` 完成 —— LLM Discovery
本身**不是**证据检索路线，它无权断言“没有证据”。
非法组合 → **422**（语义非法，不是状态冲突）。

### 14.3 时间戳不变量

| status | started_at | finished_at |
|---|---|---|
| `QUEUED` | 可空 | **必须** NULL |
| `RUNNING` | **必须**非空 | **必须** NULL |
| `COMPLETED` | **必须**非空 | **必须**非空 |
| `FAILED` / `CANCELLED` | 可空 | **必须**非空 |

`FAILED` / `CANCELLED` 的 `started_at` 可空，因为它们可能发生在执行开始**之前**
（`QUEUED → FAILED`）或之后。失败若发生在 `QUEUED`，**不得**伪造 `started_at`。

### 14.4 单活跃 run 不变量

对同一个 `(seed_region_pk, discovery_type)`，**最多**存在 **一个**活跃 run
（`status IN ('QUEUED','RUNNING')`）。终态历史**不**阻塞新 run。

该不变量由 **PostgreSQL 部分唯一索引**保证
（`uq_kdr_active_per_seed_type`，migration `gate7b_012`），
**不是**应用层 `SELECT` 后再 `INSERT` —— 后者在并发下会双写。
数据库是最终权威；lifecycle service 将 `IntegrityError` 转成 **409**。

### 14.5 事务与并发

每一次状态迁移是**一个事务**：`SELECT … FOR UPDATE` 锁定该 run 行，
在锁内判定迁移合法性，再写入。**禁止**「先读状态，之后无条件 UPDATE」。

### 14.6 Phase 2B 边界

本阶段**只**提供生命周期写入与状态不变量。
**没有**执行引擎：`create` 只会产生一个处于 `QUEUED` 的 run，
必须由后续阶段的执行层推进。因此 UI 的
`Start LLM Discovery` / `Start Literature Discovery` **保持禁用** ——
否则会产生无人执行的 `QUEUED` run。

---

## 15. LLM Discovery Structured Contract（Phase 3A 冻结）

LLM Discovery 是**高召回假设生成**，**不是**证据核实、**不是**归一化、
**不是**正式知识创建。本阶段只定义**契约与解析器**，**不调用任何模型**。

构件：`app/schemas/llm_discovery.py`（契约）、
`app/prompts/llm_discovery_prompt.py`（版本化 prompt）、
`app/services/llm_discovery_parser.py`（解析 + 结构校验）。

### 15.1 本地候选 ID（local_id）

- 形如 `<type>_<n>`：`region_1` / `connection_2` / `function_1` / `circuit_3`。
- **仅在一次响应内有效**，是**引用**，不是 canonical ID。
- 模型**绝不**可以编造 `NGIQ-*` 或数据库主键；它收到的唯一 canonical id 是
  `seed_entity_id`。该模式被**确定性拒绝**（大写与连字符都不合法）。
- 同一响应内 local_id **全局唯一**（跨类型复用同样拒绝，避免引用歧义）。

### 15.2 SEED 引用

已知种子用保留引用 `SEED` 表示，**不需要**为它伪造一个 RegionCandidate。
非 `SEED` 的区域引用**必须**命中已声明的 `RegionCandidate.local_id`。

### 15.3 Circuit-first

`CircuitCandidate` 是**主要发现对象**：具有功能一致性的多区域通路/网络。

**神经回路不要求是闭合环**。`LOOP` 只是若干 `topology_hint` 之一；
Gate7B 把闭合性建模为 `circuits.is_closed_loop` **属性**，而非必要条件。

### 15.4 候选与证据分离

| 概念 | 含义 |
|---|---|
| LLM 候选 | **提议**的知识（本阶段产物，纯内存） |
| SourceHint | 模型**记得**的来源线索，**未核实** |
| Evidence | 经确定性文献核实后的证据（未来阶段） |
| Canonical Entity | 正式 Gate7B 知识（未来阶段） |

**`source_hint != Evidence`**。模型给出的 PMID / DOI / 标题**不得**直接写入
`publications` / `evidence` / `evidence_links`。

LLM Discovery **不**要求模型提供引文、原文段落或偏移量 —— 它不读任何文档；
这些属于 Literature Discovery。若模型意外产出引文类字段，**不视为证据**。

### 15.5 候选语义默认值（冻结，但本阶段**不落库**）

    source_type      = LLM_GENERATED
    evidence_status  = UNVERIFIED
    knowledge_status = CANDIDATE

### 15.6 LLM Discovery Candidate Semantics

- **Connection ≠ Projection**：`connection_type` 与 Gate7B
  `connections.connection_class` 一一对应
  （`STRUCTURAL` / `PROJECTION` / `FUNCTIONAL` / `EFFECTIVE`），
  外加**仅用于发现**的 `UNKNOWN`（“来源没有说明”），
  `UNKNOWN` **不得**被静默映射为任何正式类别。
  **绝不**把所有连接一律标成 `PROJECTION`，也**绝不**把投影降级为泛化连接。
- **confidence** 是模型**自评的发现置信度**（`0.0–1.0`），
  **不是**证据质量、**不是**归一化置信度、**不是**验证置信度。
- **跨物种**：种子为人类（`9606`）。非人类知识必须**显式保留物种限定**，
  **绝不**静默转换为人类事实；校验发出 `CROSS_SPECIES_UNCERTAINTY`。
- **`summary` 不是权威**：机器逻辑只读结构化数组。
- **解析器不放行科学修补**：只允许表层修复（BOM、code fence、空白、
  在一个明确 JSON 对象周围包裹的散文）。**禁止**补齐缺失连接、
  **禁止**推断方向、**禁止**补造区域/成员/来源线索、
  **禁止**改写科学枚举值。结构不合法即**失败**，绝不“修”成合法。
- **回路完整性**：`region_refs` 少于 2 个 → **拒绝**；
  `connection_refs` 为空 → **保留**候选并发出
  `CIRCUIT_WITHOUT_CONNECTION`（**绝不**伪造缺失的连接）。
- **种子一致性**：响应中的 `seed_entity_id` 必须与请求的种子**完全一致**，
  否则**拒绝**（防 prompt/model 漂移），不静默覆盖。
- **空结果合法**：`regions=connections=functions=circuits=[]` 是**有效的**
  结构化结果（“无候选”），不是解析失败。

### 15.7 Prompt 契约

| | |
|---|---|
| key | `knowledge_production.llm_discovery` |
| version | `1.1.0`（Phase 3B.2 root-shape hardened；`1.0.0` 代表旧的 `top_level` 版本文本） |

**Prompt version ≠ schema version**：`prompt_version` 标识**描述方式**，
`schema_version = 1.0` 标识**科学契约**。Phase 3B.2 只改了前者。

输出 schema 描述**由类型契约派生**（`compact_output_schema`），不手工维护第二份。

**provider 侧无严格 schema 强制**：当前 provider 仅启用 JSON 模式
（`response_format=json_object`），其 `response_schema` 形参**未被使用**。
因此**解析器是权威**，不得假装存在 provider 侧强校验。

### 15.7a Candidate Species Context（Phase 3A.1 冻结）

`SpeciesContext` 描述**某个候选知识所依据的物种基础**，
与 `RegionCandidate.species_taxon_id`（**命名结构自身**的物种身份）是**两个不同概念**：

| 字段 | 含义 |
|---|---|
| `RegionCandidate.species_taxon_id` | 该**脑区实体**的物种身份 |
| `Candidate.species_context` | 该**知识主张**的物种/研究语境 |

一个脑区可以是人类结构，而联系它的证据来自啮齿类——两者必须能分别表达。
`Connections` / `Functions` / `Circuits` **必须**显式给出 `species_context`
（缺省即校验失败：模型必须**声明**其物种基础，哪怕声明为 `UNKNOWN`）。

```
scope:     HUMAN | NON_HUMAN | MIXED | UNKNOWN
taxon_ids: [int]      # NCBI taxonomy：9606 人类 / 10090 小鼠 / 10116 大鼠
```

**默认值为 `UNKNOWN` + `[]`，绝不是 `HUMAN`。** 没有信息不等于人类适用。

最简表示自洽校验（**不是**分类学判断，也**不**建 taxonomy 库）：

- `HUMAN`：`taxon_ids` 非空时**必须**含 `9606`；
- `NON_HUMAN`：`taxon_ids` **不得**只含 `9606`；
- `MIXED` / `UNKNOWN`：不额外约束；`UNKNOWN` 允许 `[]`。

**人类种子不蕴含人类知识**：脑区种子为人类，**不**意味着发现的连接/回路/功能
都已在人类中确立。凡未明确声明 `HUMAN` 的候选（含 `UNKNOWN`）都会产生
`CROSS_SPECIES_UNCERTAINTY` 结构 warning——让未声明的物种基础**可见**，
而不是被当作人类。这些仍是**结构发现 warning**，不是正式知识验证。

### 15.7b Unknown-field policy：拒绝，而非静默忽略

结构模型的 `extra = "forbid"`：**未定义字段即校验错误**，解析器**失败**。

理由不是某个具体字段危险，而是未定义字段是
**prompt 漂移 / 模型漂移 / schema 漂移**最早的可检测信号；
静默丢弃等于丢掉信号。因此模型返回 `quotation` / `evidence_text`
之类的字段时，结果是**显式失败**，而不是「忽略后继续成功」。

解析器**不得**：删除未知科学字段后继续成功、把 `quotation` 改写成
`source_hint`、把 `evidence_text` 改写成 `note`、或猜测字段含义。
格式修复规则不变（BOM / code fence / 空白 / 单一明确 JSON object 提取）。

### 15.8 Phase 3A 边界

**零**迁移、**零**新表、**零**候选落库、**零**新端点、**零**前端改动、
**零** provider 调用。产物止于**类型化的内存结构**。
候选持久化属于更晚的独立阶段（Phase 3C）。

---

## 16. LLM Discovery Execution（Phase 3B）

Phase 3A 冻结了**契约**，Phase 3B 只做一件事：**把契约跑一遍**。

```
BrainRegion Seed → create LLM_DISCOVERY Run → QUEUED → RUNNING
  → Phase 3A Prompt → DeepSeek Provider → raw text
  → Phase 3A Parser → 类型化候选（内存）→ RUNNING → COMPLETED / FAILED
```

单一端点，**无 body**：

```
POST /api/knowledge-production/brain-regions/{entity_id}/llm-discovery/execute
```

响应 `{run, result, validation_warnings, metrics}`。`result` 是候选，
**只存在于这一次响应中**。

### 16.1 `content` 是唯一答案

`message.content` 是**唯一**权威最终答案。`reasoning_content` 是推理**元数据**，
**绝不**提升为答案——否则未经结构化的思考会被 parser 当作结果接受。
content 为空即视为**空响应失败**，而不是退回原始 body。

### 16.2 业务层只选 provider，不选 model

执行层只声明 `provider = deepseek`；模型由 `app.llm_model_policy` 在 provider
调用点决定。Run 上记录的 `model_name` 是**实际执行的模型**（取自全局策略，
不是请求值、不是新写字面量）。provider 回报的模型与策略不一致时，
run **失败**——策略被绕过必须暴露，不能被当成正常记录。

### 16.3 可信内部调用方（唯一写 provenance 的地方）

公开 Run Create API **不变**：body 仍然只有 `discovery_type`，
`extra="forbid"` 继续拒绝客户端伪造的 provider / model / prompt。
生命周期 service 的内部 create 路径接受 `provider` / `model_name` /
`prompt_key` / `prompt_version`（默认 `None`，即公开行为），
**只有执行服务**会写入它们。

`prompt_key = knowledge_production.llm_discovery`，`prompt_version = 1.1.0`。
版本号只有**一个**权威：`app/prompts/llm_discovery_prompt.py` 的
`PROMPT_VERSION`；任何调用点都不得复制字面量。

### 16.4 结果映射（outcome）

只有四类候选数组决定 outcome：任一非空 → `CANDIDATES_FOUND`，
四类**全空** → `NO_CANDIDATES_FOUND`。
仅有 `source_hints` 非空仍是 `NO_CANDIDATES_FOUND`——source hint 是线索，不是候选。
LLM Discovery **永不**使用 `NO_EVIDENCE_FOUND`：它不是证据检索路线。

### 16.5 失败词汇表（复用，不新造框架）

| error_code | 含义 |
|---|---|
| `LLM_PROVIDER_TIMEOUT` | provider 超时 |
| `LLM_PROVIDER_AUTH_ERROR` | 凭据被拒 / provider 未配置 |
| `LLM_PROVIDER_ERROR` | 其他 provider 失败（含策略被绕过） |
| `LLM_EMPTY_RESPONSE` | 没有可解析的 content |
| `LLM_DISCOVERY_PARSE_FAILED` | 响应不满足 Phase 3A 契约 |

解析失败时 `error_message` 只写**简短结构化摘要**，**不**写入完整响应。
HTTP 上 provider / parser 失败统一为 **502**（上游没有给出可用答案）；
run 在抛出之前**已经**是 FAILED。四类失败路径都不得留下永久 `RUNNING`。

### 16.6 允许记录的 provenance

只允许：response SHA-256、prompt SHA-256、`latency_ms`、token usage、
`schema_version`、warning 数量、各数组计数、provider / effective model /
prompt 版本。

禁止进入 Gate7B 知识表与 `provenance_json`：raw response、`reasoning_content`、
任何候选内容。日志中禁止：API key、auth header、完整 prompt、完整响应。

### 16.7 Seed 装载是确定性的

`name_en` / `name_zh` / `granularity_level` / `hemisphere` / `species_taxon_id` /
`source_atlas_names` 直接取自 Gate7B 声明值；`known_aliases` 取自
`entity_aliases`（`is_preferred` 降序、`alias_pk` 升序，与已声明名称重复的不计入）；
`parent_region_name` 取自 `brain_regions.parent_region_pk`（**派生缓存**，
声明为 NULL 即为 NULL）。

**不猜别名、不推断父区、不从旧 Mirror 数据回填**。缺失的可选字段就是
`None` / `[]`——缺失是模型**允许**不知道的事实，编造是模型**无法**察觉的缺陷。

### 16.8 Phase 3B 边界

**零**迁移、**零**新表、**零**候选落库、**零**前端改动、
**零** Celery / Redis / BackgroundTasks / worker / 调度器 / 重试守护进程。
执行是**同步**的：一次请求一次尝试。`species_context` **不**由执行层填充——
缺失时由 parser 失败（§15.7a）。

前端 Discovery 按钮**保持禁用**：候选尚不能持久化。

### 16.9 DeepSeek runtime policy（Phase 3B.1）

```
NeuroGraphIQ DeepSeek runtime policy:
- model: deepseek-flash
- knowledge-production workloads are quality-first
- token budget must be sufficient for complete structured output
- cost optimization must not silently reduce scientific output quality
```

知识生产阶段（LLM Discovery / Literature Discovery / Evidence extraction /
Evidence judgment / Validation）的优先顺序：

```
1. scientific/structural quality
2. contract compliance
3. execution reliability
4. latency
5. cost
```

具体含义：

* 不为了节省 API 成本降低必要的 **输出预算**（`max_tokens`）。
* 不为了节省 token 删除 `species_context`、Circuit、Connection、Function、
  `source_hints`，或简化科学 schema。
* 不因为 prompt 较长而截断关键科学上下文。
* 优先避免 `finish_reason = "length"` / 不完整 JSON / 被截断的结构化响应：
  **截断是正确性失败，不是节省**。
* token usage / latency 继续记录（见 `metrics`），但只用于诊断与后续性能优化，
  **当前不作为主动降质依据**。

**预算权威**（单一来源）：

```
DeepSeekRuntimeSettings.max_tokens          schemas/settings.py  ← 默认 = 上限
  → settings_service.get_deepseek_runtime_config().max_tokens
  → llm_discovery_execution_service          （透传，不裁决）
  → DeepSeekProvider  →  payload["max_tokens"]  →  HTTP request
```

Provider **不**做 clamp；业务层**不**传字面量。旧值 2000/2048/4096 已废弃：
它们会让推理型模型在产出答案之前耗尽预算，实测即 `finish_reason = "length"`
且 `content` 为空。

`timeout`：Phase 3B.3 由 120s 提高到 **300s**（上限 600s）。120s 是为旧的 2K
预算设定的；64K 生成在合法情况下可能明显更久。仍**有界**，挂死请求不会长期占用 worker。

> **注意**：上述数值属于 **runtime configuration**，不是知识语义。
> **不得**把 `max_tokens` / 数值上限写入科学 ontology、结构化契约或
> `schema_version`。

### 16.9a Thinking / reasoning runtime（Phase 3B.3）

DeepSeek 的 **thinking mode 默认开启**，`reasoning_effort` 默认 **high**——即
在没有显式设置时，推理过程会**先消耗同一份生成预算**，然后才轮到最终答案。
Phase 3B.1 / 3B.2 的 `max_tokens = 8192` 是**项目自身**的限制，
**不是** deepseek-flash 的模型能力上限（官方 Chat Completions 允许远高于此）。

Knowledge Production 采用的显式 runtime profile：

| 项 | 值 | 说明 |
|---|---|---|
| provider / model | `deepseek` / `deepseek-flash` | 全局固定政策，未变 |
| `thinking` | `{"type": "enabled"}` | **显式发送**，不再依赖服务端默认 |
| `reasoning_effort` | `high` | 显式发送 |
| `max_tokens` | `65536` | thinking 模式的默认量级；上限 131072 作为诊断余量 |
| `timeout_seconds` | `300` | |

**只在 caller 显式传入时才发送** `thinking` / `reasoning_effort`。
因此这套 profile **只作用于声明了它的调用方**（当前是 LLM Discovery），
legacy DeepSeek 任务的行为逐字节不变——这是 §6「不要机械改动所有任务」的实现方式。

`max_tokens` 的语义：它控制**本次生成的预算**，thinking 的推理会从中扣除。
因此：

```
completion_tokens ≈ max_tokens  +  finish_reason = length
```

必须读作 **generation budget exhausted**，并且要**连同 reasoning effort 一起解读**；
它本身**不构成**「单次架构不可行」的证明。

**历史诊断（保留原始实验数据）**：

| 阶段 | 预算 | thinking | 结果 |
|---|---|---|---|
| 3B.1 | 8192 | 隐式 high（未声明） | 3/3 `length`，parser 0/3 |
| 3B.2 | 8192 | 隐式 high（未声明） | 1/1 `length`，`content` 为空 |
| **3B.3** | **65536** | **显式 high** | **`finish_reason = "stop"`；`completion_tokens = 23061`（其中 `reasoning_tokens = 11013`）；`content_chars = 40401`；parser **FAIL**（`LOCAL_ID_DRIFT`）** |

Phase 3B.3 结论：**预算不是瓶颈**——模型在 65536 中只用了 23061 就正常收尾
（`stop`），首次给出了**完整可评价**的结构化响应。因此：

* 8K 时代的 `SINGLE_RESPONSE_ARCHITECTURE_EXHAUSTED` **已被推翻**；
  真正的问题是**契约漂移**，不是架构耗尽。
* 新的、也是首个由真实模型产生的失败类别是 **`LOCAL_ID_DRIFT`**：
  模型把 local id 写成缩写形式（实测 `conn_1`），
  违反契约的 `^(region|connection|function|circuit)_[0-9]+$`。
* 依既定规则（Phase 3A §23 / Phase 3B §23）：**不得**为了让模型通过而放宽
  `local_id`。这是 `MODEL_CONTRACT_DRIFT`，契约保持不动。

### 16.10 Response Root Shape（Phase 3B.2）

真实 smoke 暴露过一类**结构性歧义**：Phase 3B 之前，prompt 把 schema 说明
序列化成**一个 JSON object** 交给模型：

```json
{ "schema_version": "1.0", "top_level": {...}, "RegionCandidate": {...}, ... }
```

它看起来**就是一个答案**。模型于是把它当作输出形状，返回了含 `top_level`
的对象；另一次直接返回顶层 JSON **数组**。

现在 prompt 必须把两件事**物理分开**：

```
A. EXPECTED RESPONSE ROOT   ← 唯一的输出形状（root skeleton）
B. FIELD DEFINITIONS        ← 只描述 A 中各数组里的 ITEM，纯文本，不是 JSON
```

约束：

* root 必须是**一个 JSON object**，**不得**是顶层数组；
* root 一级键**恰好**是契约的九个 top-level 字段，无包装、无 `top_level`、
  无 JSON Schema 元数据；
* **A 与 B 不得放在同一个 JSON object 里**；
* root skeleton 由 `LlmDiscoveryResponse.model_fields` **渲染**得出，
  field definitions 由 typed model **渲染**得出——不得手写第二套科学 schema
  （有测试锁定：skeleton 键集合 == 契约 top-level 字段集合）。

`schema_version` / 契约语义本阶段 **零改动**。

**观察记录（非结论）**：在 **8192** 预算下，真实模型仍然
`finish_reason = "length"`、`completion_tokens = 8192`；其中一次
`content` 完全为空（预算全部消耗在推理阶段、未产出任何答案字符）。

该现象**当时**被记为 `SINGLE_RESPONSE_ARCHITECTURE_EXHAUSTED`。Phase 3B.3
修正了这一读法：那是在**项目自设的 8K 生成上限**且 **thinking mode 隐式
high** 的组合下发生的，因此它证明的是「8K 不够」，
**不是**「单次架构不可行」。判定单次架构是否可行，需要先给足预算、
并把 reasoning profile 显式化（见 §16.9a）。

**Phase 3C 候选方向**（本阶段**不**实现）：若在充足预算与显式
reasoning profile 下单次调用仍不可行，再考虑 **Multi-pass LLM Discovery**：

```
Pass 1  Circuit hypotheses
Pass 2  Participating regions / connections
Pass 3  Functions
Pass 4  Local candidate graph consolidation
```

项目策略是 quality-first，因此允许一次 BrainRegion 对应**多次** deepseek-flash
调用，换取更稳定的结构、更完整的候选、更低的单次 JSON 复杂度与更容易的错误隔离。
成本不作为阻止该设计的主要因素。**但 Multi-pass 只有在单次架构被真正证伪后
才启动**——不得以 8K 耗尽为据直接跳入。
