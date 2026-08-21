# UO1.1 统一 NeuroGraphIQ Ontology Core — 审计 + 设计

> 阶段：UO1.1（审计 + 设计，零写入）
> 日期：2026-08-20
> 状态：设计稿，未实施。BR1 及之后任何数据库变更须另行批准。
> 原则：本阶段不改 70,029 连接 / 53,562 回路 / 8,189 功能；不建脑区本体；不推理；不 Neo4j/AGE；不改前端。

---

## 0. 审计方法

- 6 个只读审计代理并行核查：ORM / Service / Router / Schema / Parser / Migration / 设计文档，全部以当前代码为准（文件:行号引用）。
- 只读 DB 核实（2026-08-20，e2e 库 `neurographiq_kg_v3_mvp1_e2e`）：

| 表 | 行数 | 备注 |
|---|---|---|
| candidate_brain_regions | 1,327 | Macro96 96 + Allen_HBA_2012 1,231；**96 行有 canonical_id** |
| final_brain_regions | 0 | — |
| raw_aal3_region_labels | 0 | AAL3 未落库（数据文件 aal3_labels.json 存在） |
| raw_macro96_region_rows | 96 | — |
| mirror_region_connections | 70,029 | 100% LLM 生成（llm_suggested） |
| mirror_region_circuits | 53,562 | — |
| mirror_circuit_steps | 103,880 | — |
| mirror_circuit_functions | 102,041 | term_id 覆盖 100%（142/142、102,041/102,041、13,341/13,341） |
| mirror_region_functions | 142 | — |
| mirror_projection_functions | 13,341 | — |
| mirror_circuit_projection_memberships | 2,948 | 回路↔连接显式关联已存在 |
| mirror_kg_triples | 171,494 | triple_scope 100% same_granularity |
| final_region_connections / final_kg_triples / final_projections / final_circuit_steps / final_circuit_functions | 0 | final 侧为空 |
| ontology_terms | 8,189 | proposed 5,315 + active 2,874；term_type 100% function |
| ontology_term_relations | 0 | 功能层级边为空 |
| ontology_alignment_candidates | 86 | 全部 pending（exact 24 / close 28 / weak 34） |
| paper_sources / mirror_evidence_records | 570 / 99,481 | — |

---

## 1. 四类核心对象当前 identity（A）

### 1.1 BrainRegion

| 项 | 现状 |
|---|---|
| 实体表 | `candidate_brain_regions`（枢纽，1,327 行）；`raw_aal3_region_labels`（0）、`raw_macro96_region_rows`（96）；`final_brain_regions`（0） |
| canonical identity（运行时） | **`candidate_brain_regions.id`（UUID）** — `canonical_region_resolver.py:121-128` 明确"用 candidate id 作为 mirror 引用" |
| source-specific identity | `source_atlas + source_label_id`；名称冗余 `en_name/cn_name` |
| canonical_id 列 | 存在（96 行），但**代码不生成、ORM 不声明、schema 不暴露**，仅一次迁移回填（见 §3） |
| ontology_term_id | 无（脑区不进 ontology_terms，O1.1 明确为开放决策） |
| granularity | `granularity_level + granularity_family`（自 atlas_resources 继承） |
| species | **无行级字段**（仅 `atlas_resources.species`，默认 human） |
| hemisphere | `laterality`（left/right/bilateral/midline/unknown），候选与 final 均保留；Mirror 层无脑区实体，不保留 |
| external mapping | `uberon_iri / nifstd_iri` 列为空（0 值）；`ontology_alignment_candidates` 86 条全 pending |
| parent/hierarchy | **完全不存在**（无任何表的脑区父级字段） |
| Mirror / Final | Mirror 经 `region_candidate_id` FK 引用候选；`final_brain_regions` 0 行 |
| Triple | 参与（subject/object_type ∈ region_candidate/region_final） |
| 事实源 | AAL3 XML / Macro96 xlsx / Allen_HBA_2012 候选池 |

### 1.2 Connection

| 项 | 现状 |
|---|---|
| 实体表 | `mirror_region_connections`（70,029）→ `final_region_connections`（0）/ `final_projections`（0）。**不存在 mirror_projections 表**（cleanup 统计标签误名） |
| canonical identity | 无显式 canonical key；写时合并 key = `(source_candidate_id, target_candidate_id, connection_type, directionality)` + 同 `source_atlas` + 同 `granularity_level`（`mirror_kg_service.py:80-138`） |
| 端点 | FK → `candidate_brain_regions`（真外键）；名称字符串冗余（036 迁移） |
| granularity | 有（molecular_attr 64,313 / macro 5,716）；hemisphere/species | **无** |
| assertion | **无**（mirror_status 三态是治理状态，不是断言类型） |
| 跨粒度 | **被硬性禁止**（`SameGranularityValidationError`），无任何聚合概念 |

### 1.3 Circuit

| 项 | 现状 |
|---|---|
| 实体表 | `mirror_region_circuits`（53,562）+ `mirror_circuit_regions` + `mirror_circuit_steps`（103,880）+ `mirror_circuit_functions`（102,041）+ `mirror_circuit_projection_memberships`（2,948） |
| canonical identity | 写时合并 key = `(circuit_name, source_atlas, granularity_level)`；有 `canonical_start_region_id / canonical_end_region_id`（名称误导，实为候选 id） |
| 关联 Connection | **已显式关联**：`mirror_circuit_projection_memberships(circuit_id, projection_id FK→mirror_region_connections, source_step_id, target_step_id)` |
| granularity | 主表/步骤/功能/成员均有；hemisphere/species | 无 |
| 层级/抽象 | **无**（无 subcircuit/parent/abstract 字段） |
| assertion | 无 |

### 1.4 Function

| 项 | 现状 |
|---|---|
| 实体表 | `ontology_terms`（8,189，P1 canonical）+ `ontology_term_relations`（subclass_of，**0 边**）+ `ontology_hierarchy_candidates` |
| canonical identity | **`ontology_terms.id`**（P1 收口）；term_code `ng:func:*` 为稳定 IRI；三个 mirror function 表 term_id 100% 覆盖 |
| 层级 | `child --subclass_of--> parent` DAG，深度运行时计算（`ontology_hierarchy_service.py`），不投影 triple（TBox/ABox 分离） |
| 证据 | `mirror_evidence_records` 多态（evidence_target_type → mirror function 行 → term_id）；DeepSeek 语义置信度 `suggested_confidence`（可审阅推荐），`reviewer_confidence` 权威 |
| Triple | **投影（projection）非事实源**：`function_triple_projection_service` reconcile 语义 + `projection_version`；171,494 条 mirror triple 100% same_granularity |

---

## 2. BrainRegion 当前 identity 问题（B）

1. **无跨 Atlas canonical 实体**：只有 Atlas-specific 行（AAL3/Macro96/Allen），"Left Hippocampus" 作为统一概念不存在。
2. **canonical_id 列断裂**：迁移回填 SQL 引用不存在的 `label_code` 列（`20260706_add_canonical_ids.sql:8-13`），ORM/Schema/代码三方不维护。
3. **外部本体身份未落地**：UBERON/NIFSTD 列为空，86 条对齐候选全 pending。
4. **无层级**：Brainnetome/HCP/Siibra parser 的 `parent_region`（lobe）与 Allen `structure_id_path` 均悬空不持久化。
5. **物种歧义**：Allen_HBA（人类结构）候选与 Mouse Allen connectivity 证据混在同一资源语境；`paper_search_multi.py:360-368` 用 atlas 字符串子串推断物种（"allen"→mouse，误判 HBA）。
6. **粒度混入 atlas 语义**：连接/回路行用 `source_atlas='llm_circuit_connection_extraction'/'llm_bundle'` 这类伪造 atlas 名承载粒度（`llm_circuit_connection_extraction_service.py:160`、`field_completion_execution.py:669`）。

## 3. canonical_id 真实含义（C）

- **生成**：仅一次迁移回填 `source_atlas || '_' || COALESCE(label_code, std_name, en_name, cn_name)`；对 Macro96 实际值形如 `Macro96_{cn_name}`（中文名，含乱码风险）。
- **范围**：仅 96 行 Macro96；**不跨 Atlas 共享**；**无唯一约束**；**不稳定**（改名不更新）。
- **运行语义**：无。任何代码不读不写。
- **结论**：它是 **source-local 回填键，不是 ontology identity**。不能作为 Canonical BrainRegion identity。
- **建议**（实施期）：删除该列或以 `canonical_region_id`（FK → 未来的 canonical_brain_regions.id）取代，作为 Atlas 行 → Canonical 概念的锚点引用。

## 4. Atlas 与 Granularity 必须分离（D）

**正式链路已分离**：candidate 的 granularity 来自 `atlas_resources` 注册值（人工选择 enum），非 atlas 名推断（`candidate_service.py:245-246`、`macro96_candidate_service.py:242-243`）。

**但耦合残留（证据）**：

| 位置 | 混用形式 |
|---|---|
| `parsers/*.py`（8 个） | 每个 parser 按 Atlas 身份硬编码 granularity（AAL3→macro、HCP/Brainnetome→meso、Allen→molecular/micro…）——虽仅内存，但固化"Atlas=粒度"心智 |
| `llm_circuit_connection_extraction_service.py:160` | `source_atlas="llm_circuit_connection_extraction"` 伪造 atlas 名承载粒度 |
| `field_completion_execution.py:669` | `source_atlas='llm_bundle'` + `granularity_level='macro'` |
| `paper_search_multi.py:360-368` | atlas 子串 + granularity 子串混用推断物种 |
| `unified_tasks.py:214` | `target_type="molecular_attr"` 把粒度值当 target_type 用 |

**统一原则**（写死）：Atlas = source；Granularity = semantic/anatomical level。Allen 一个 Atlas 内含多粒度（HBA 同时有 macro 概念与 fine cytoarchitectonic 与 molecular）。**不允许**任何代码以 atlas 名推导 granularity 或 species。

## 5. Granularity Model 推荐（E）

采用最小方案：**受控词汇入 `ontology_vocabularies`（复用现有机制，20260806 先例）+ 放开 001 CHECK**，不建新表。

```
vocab_type='granularity_domain'
  brain_region_anatomical | connection_resolution | circuit_resolution | function_specificity

vocab_type='granularity_level'（brain_region_anatomical 域）
  level_code=whole_brain level_order=0   Whole brain / major division
  level_code=macro         level_order=1   Macro（临床参照系 = Macro96 96 池整体；临床使用边界）
  level_code=meso          level_order=2   Meso（HCP-MMP/Desikan）
  level_code=parcel        level_order=3   Atlas parcel / subregion（Brainnetome 等）
  level_code=fine          level_order=4   Fine（cyto：Julich）
  level_code=ultra_fine    level_order=5   Ultra-fine（未来）
```

> **决策（2026-08-20，用户确认）**：Macro96 96 池整体作为 L1 Macro 临床参照系
> （含 62 个 Desikan 式皮层区，整体按宏观层对待，不再按解剖细分到 meso）；
> **macro 层是临床使用边界**——临床浏览/查询停在 macro 层，向下细分（meso/parcel/fine）
> 供研究/推理层使用。此语义已写入 `ontology_vocabularies` 的 `macro` 行 description。

connection_resolution：macro_aggregated | meso | fine_asserted
circuit_resolution：macro_abstract | meso | fine_topology
function_specificity：broader | intermediate | specific
```

- **层数不写死在代码**；`level_order` 提供排序与衰减系数入口。
- **遗留值兼容**：现有 `granularity_level` 存量值（macro / fine_cyto / molecular_attr…）通过"词汇行映射到 level_code/level_order"（例如 fine_cyto→parcel/fine，molecular_attr→fine），**不改存量数据**。
- 三套词汇（parser 短值集 / enum / DB CHECK）在实施期收敛到词表；`sub_connectivity` 从未存在于任何 schema，作为文档词汇废弃。

## 6. Canonical BrainRegion 模型（F）

**选方案 B：独立 `canonical_brain_regions` 表，不塞进 ontology_terms。** 理由：

1. ontology_terms 事实上是 Function-only（代码强制；term_type 为自由字符串但所有写入路径写 "function"）。
2. BrainRegion 需要 hemisphere/species/解剖层级/atlas 映射/粒度，ontology_terms 无这些字段且生命周期（candidate→final 晋升链）与 term 不同。
3. P1 已锁 Function identity=ontology_terms.id；统一的是**身份规范、关系语义、粒度、断言、溯源、推理契约**，不是共用一张表。

```
canonical_brain_regions
  id UUID PK
  canonical_name_en VARCHAR(512) NOT NULL      -- 概念级名称（hemisphere 中性）
  canonical_name_cn VARCHAR(512)
  term_code VARCHAR(128) UNIQUE                -- ng:br:* 稳定 IRI（对齐 P1 风格）
  granularity_domain VARCHAR(64) = 'brain_region_anatomical'
  granularity_level VARCHAR(64)                -- 词表引用
  species VARCHAR(16) NOT NULL                 -- human（v1 全部 human）
  hemisphere_policy VARCHAR(16)                -- bilateral | lateralized | midline_unpaired
  status VARCHAR(16) DEFAULT 'proposed'        -- proposed/active/deprecated（复用 term 生命周期模式）
  description TEXT
  confidence NUMERIC
  source_summary JSONB                         -- 哪些 atlas/Allen 支撑
  external_mappings JSONB                      -- uberon/nifstd/allen_id（或复用 alignment 表）
  created_by/created_at/updated_at
  replaced_by_region_id UUID                   -- merge 链（对齐 ontology_terms 模式）
```

- 表结构为设计稿，**本阶段不实施**（列入最小 Schema 清单，见 §22）。

## 7. Atlas Region → Canonical 映射（BR2/BR3 设计）

- 复用 `ontology_alignment_candidates`（扩展 target_type='canonical_region' 或新增 region 锚点表），不重复建表。
- 治理状态：`exact / close / broader / narrower / uncertain / rejected`（现 match_type 仅 exact/close/weak/not_found——扩展词表）。
- 锚点模型：`candidate_brain_regions.canonical_region_id`（FK）+ 每侧 `laterality` 保留 → hemisphere 在锚点层不丢失。
- **本阶段不自动合并**；映射须人工/半自动评审（对齐现有治理流）。

## 8. Hemisphere 策略（G）

**选 B：Canonical 概念 = hemisphere 中性；左右 = 锚点实例。**

- `Hippocampus`（canonical, hemisphere_policy=lateralized）下挂 `left hippocampus` / `right hippocampus` 两个候选锚点（Macro96 左右不合并的 96 池天然符合）。
- Allen 人类结构默认 bilateral（数据实测 1,230/1,327），midline_unpaired 用于脑干/蚓部（3 条 unknown 小脑蚓部不强制分配）。
- **Connection 方向不丢**：连接端点始终是 candidate（分侧）id，L→R 方向天然保留；未来 canonical 级连接带 `source_hemisphere/target_hemisphere` 限定符，绝不因 canonicalization 丢失半球。

## 9. Species 策略（H）

**选 B：Canonical 概念 = 物种限定（v1 全部 human）；跨物种仅 `homologous_to`，永不 equivalent。**

- 数据现实：所有资源 species=human；Allen_HBA=人类结构；Mouse Allen connectivity 是**证据**（experiment 数据），不是 region 概念源。
- 修复点：`paper_search_multi.py` 的 atlas 子串推断改为显式资源元数据。
- 规则：名称相同 ≠ 同一 region；跨物种映射须显式声明 `homologous_to` + confidence。

## 10. Connection 统一模型（L）

- **不迁移 70,029 行**。保持 `mirror_region_connections` 为 asserted domain source；端点继续锚定 candidate（未来经 canonical_region_id 归组）。
- 跨粒度语义（未来表/字段）：
  - `fine → meso → macro` 用 **`aggregated_into`（向上）/ `derived_from_finer_connection`（向下引用）**；只设计一套 canonical direction（aggregated_into），inverse 查询派生。
  - 宏级连接区分 **asserted**（有独立宏观证据）与 **inferred_aggregate**（由子区向上 roll-up）。

## 11. Connection 跨粒度边界（硬约束，写进契约）

- **Upward roll-up = inferred knowledge**：BLA part_of Amygdala ∧ IL part_of mPFC ∧ BLA projects_to IL ⇒ `Amygdala --has_descendant_projection_to--> mPFC`（新谓词），**禁止**直接断言 `Amygdala projects_to mPFC`。
- **Downward expansion = candidate only**：仅 Amygdala→mPFC 宏观断言时，BLA→IL 只能进 **candidate pool**（复用 `candidate_pools` 机制），禁止写为事实。
- 推论：向上=知识；向下=假设。

## 12. Circuit 统一模型（M）

- 保持 mirror_circuit_projection_memberships（已显式连接 Connection）为核心拓扑载体。
- 两种关系**明确分离**：
  - `subcircuit_of` = 真实生物学子回路（嵌套，同粒度）；
  - `abstracted_to` = 解剖抽象（fine→macro，跨粒度）。
  - **不得共用一个 parent 字段**；两者 assertion_type 均可为 asserted（文献/人工）或 inferred（规则）。
- 未来：`fine circuit --abstracted_to--> macro circuit`（如 BLA→IL→PAG 抽象为 Amygdala→mPFC→Midbrain），派生回路标记 `derived_anatomical_abstraction`。

## 13. Function 保留模型（N）

- P1/O1.2 结果全部保留：canonical identity=ontology_terms.id；层级只存 subclass_of；TBox/ABox 分离；Mirror=投影。
- 横向连接已天然存在（triple 谓词实测已含）：`participates_in_function`（684）、`modulates_function`（2,594）、`involved_in_function`（1,183）、`necessary_for_function`（2）、`associated_with_function`（98,290）、`possibly_associated_with_function`（8,025）。
- 本阶段**不生成 Function hierarchy 数据**（FN1 另行排期）。

## 14. assertion_type（O）

**全库现状：无任何 assertion/inferred/derived 字段**（grep 零命中；"asserted" 状态不存在于 mirror_status 枚举）。

设计（未来字段，枚举入 ontology_vocabularies）：

| 值 | 语义 | 示例 |
|---|---|---|
| asserted | Atlas/论文/人工审核后事实 | 审核通过的 mirror 行、final 行 |
| inferred | 规则/推理产生（向上 roll-up、跨粒度抽象） | Amygdala has_descendant_projection_to mPFC |
| candidate | 向下展开或待验证假设 | BLA→IL 假设 |
| rejected | 被否决 | 审核拒绝 |

**注意**：LLM 提取 ≠ asserted。现链路（llm_suggested → review → promote）保持不变，LLM 产物在审核通过前恒为 candidate 性质。

## 15. Inference metadata（P）

未来 inferred 事实的数据契约（不实现引擎）：

```
inference_rule_id VARCHAR            -- 规则标识
derived_from JSONB                   -- 源事实 id 列表（[ {type, id} ]）
source_granularity / target_granularity VARCHAR
inference_depth INT
rule_weight NUMERIC                  -- 0..1
inferred_confidence NUMERIC
provenance_chain JSONB               -- 继承证据链
assertion_type VARCHAR = 'inferred'
```

## 16. Confidence 衰减原则（Q）

```
inferred_confidence =
  source_confidence
  × hierarchy_mapping_confidence        -- part_of 边的可信度
  × rule_weight
  × attenuation(depth)                  -- 如 1 / (1 + inference_depth)
```

- 不修改现有 P1 Confidence V1（`paper_evidence_v1` 公式、reviewer 权威、DeepSeek 仅建议）——衰减仅用于**未来推理层**。

## 17. Evidence / Provenance 规则（R）

- inferred fact 的 `derived_from` 必须追踪到 asserted fact，asserted fact 挂 `mirror_evidence_records`（evidence_target 多态）→ 原始论文/Atlas。
- **推理知识只继承 provenance chain，绝不伪造 direct evidence**。
- Final 侧 provenance 四元组（source_mirror_*_id / promotion_run_id / review_record_id / llm_run_id, llm_item_id）晋升后不可变——推理知识不得绕过该不可变链。

## 18. Unified Ontology Core 边界（统一但不合并）

```
NeuroGraphIQ Semantic Core
├── BrainRegionConcept      part_of BrainRegionConcept        (canonical_brain_regions + hierarchy)
│       ├── Atlas Region anchors   (candidate_brain_regions.canonical_region_id)
│       └── External mapping       (UBERON/NIFSTD/Allen ID)
├── Connection              source/target → BrainRegionConcept
│       └── aggregated_into Connection（跨粒度，assertion_type=inferred）
├── Circuit                 has_region / has_connection / has_function
│       └── subcircuit_of / abstracted_to Circuit
├── FunctionConcept         subclass_of FunctionConcept        (ontology_terms, P1 现状)
└── 横向                     participates_in / modulates / involved_in / associated_with
统一契约：Granularity(domain+level) · AssertionType · Provenance · Confidence · InferenceMetadata
```

**不建万能 `entity_relations` 表**。Domain Relation = source of truth；Triple = projection（P1 已确认，继续遵守）。BrainRegion hierarchy 有自己的 relation 源（canonical_region_hierarchy）；Connection 有 mirror_region_connections；Circuit 有拓扑源；Function hierarchy 有 ontology_term_relations。

## 19. 统一关系矩阵（S）

| Subject | Predicate | Object | Relation meaning | Hierarchy type | 可向上推? | 可向下推? | 向下结果类型 |
|---|---|---|---|---|---|---|---|
| BrainRegion | part_of | BrainRegion | 解剖包含（child part_of parent） | **Ontology hierarchy（partonomy）** | 是（roll-up 聚合） | 否（只生成 candidate） | candidate |
| BrainRegion | participates_in_function / modulates_function / involved_in_function / associated_with_function | Function | 功能参与/调制 | KG fact（ABox） | 有限（父级继承需规则） | 否 | candidate |
| Connection | source/target | BrainRegion | 连接端点（锚定 canonical） | KG fact | — | — | — |
| Connection | aggregated_into | Connection | 细粒度连接聚合进粗粒度 | Derived relation | 是 | 否 | candidate |
| Connection | has_descendant_projection_to | BrainRegion | 子区投影向上归属（宏级推断） | Derived relation | — | 否 | candidate |
| Connection | modulates_function / has_projection_function | Function | 连接功能 | KG fact | — | — | — |
| Circuit | has_participant | BrainRegion | 回路参与者 | KG fact | — | — | — |
| Circuit | has_connection | Connection | 回路包含连接（memberships） | KG fact（拓扑） | — | — | — |
| Circuit | abstracted_to | Circuit | 解剖抽象（跨粒度） | Derived relation | 是 | 否 | candidate |
| Circuit | subcircuit_of | Circuit | 生物学子回路（同粒度嵌套） | Ontology-ish（拓扑层级） | 是 | 否 | candidate |
| Circuit | has_function / supports_function | Function | 回路功能 | KG fact | — | — | — |
| Function | subclass_of | Function | 概念特化 | **Ontology hierarchy（IS-A）** | 是（属性继承） | 否 | candidate |
| BrainRegion/Connection/Circuit | associated_with_* | Function | 横向功能链接 | KG fact | — | — | — |

Ontology hierarchy：BrainRegion part_of、Function subclass_of（+ Circuit subcircuit_of 拓扑层级）
KG fact：全部 domain relation + triple 投影
Derived relation：aggregated_into、has_descendant_projection_to、abstracted_to（assertion_type=inferred）

## 20. 统一粒度矩阵（T）

| Domain | 层级 | 说明 |
|---|---|---|
| BrainRegion（brain_region_anatomical） | whole_brain(L0) → macro(L1) → meso(L2) → parcel(L3) → fine(L4) → ultra_fine(L5) | L0 脑根/大分区；L1 临床层（AAL3/Macro96）；L2 HCP-MMP/Desikan；L3 Atlas parcel（Brainnetome）；L4 cyto（Julich）；L5 未来 |
| Connection（connection_resolution） | macro_aggregated → meso → fine_asserted | 细=原始断言层；粗=聚合层（inferred_aggregate） |
| Circuit（circuit_resolution） | macro_abstract → meso → fine_topology | 抽象层与拓扑层分离 |
| Function（function_specificity） | broader → intermediate → specific | **不机械套解剖 L0-L5**；用 domain 区分 |

## 21. 实施顺序（U）

| 阶段 | 内容 | 前置 | 说明 |
|---|---|---|---|
| **BR1** | Macro canonical BrainRegion（v1 ~25 候选） | — | 依赖最小 Schema（§22） |
| BR2 | Macro→Meso partonomy（part_of 数据） | BR1 | Allen structure_id_path 可直接复用 |
| BR3 | Meso→Atlas Parcel grounding（锚点+治理状态） | BR2 | 扩展 ontology_alignment_candidates |
| BR4 | Parcel→Fine / Allen 深潜 | BR3 | 1,327 Allen 结构全量层级化 |
| CN1 | Connection canonical region grounding | BR1 | 端点归组不迁移数据 |
| CN2 | Connection upward roll-up（inferred_aggregate） | CN1 + 推理契约 | 需 assertion_type + inference metadata |
| CR1 | Circuit canonical participant grounding | BR1 | circuit_regions/memberships 归组 |
| CR2 | Circuit abstraction（abstracted_to） | CR1 + CN2 契约 | 区分 subcircuit_of |
| FN1 | Function hierarchy 数据生成 | — | 可并行；ontology_term_relations 现为 0 边 |
| IR1 | Cross-domain inference（participates_in 等横向） | CN2/CR2/FN1 | 仅规则，不建引擎 |
| IR2 | Confidence / provenance governance | IR1 | 衰减公式 + 证据链校验 |

顺序调整说明：FN1 不依赖脑区，可与 BR 系列并行；IR 全部依赖 BR1 形成的 canonical 锚点。

## 22. 必须新增的最小 Schema 清单（V）

仅 4 项，全部为**提案，本阶段不实施**：

1. `canonical_brain_regions`（§6 结构）+ `canonical_region_hierarchy`（child part_of parent：subject_canonical_region_id, predicate='part_of', object_canonical_region_id, source, confidence, status, provenance_json）——BR1 前置，最小且必需。
2. `candidate_brain_regions.canonical_region_id`（FK，取代断裂的 canonical_id 列）+ laterality 锚点语义——BR1 同批。
3. `ontology_vocabularies` 新增 vocab_type：granularity_domain / granularity_level / assertion_type / mapping_match_type 扩展（exact/close/broader/narrower/uncertain/rejected）+ 放开 001 的 granularity CHECK——BR1 前置（词表先行）。
4. （未来 CN2/IR1 才需要）assertion_type + inference metadata 列；连接/回路的 canonical 限定符列——**本阶段不实施**。

无其他迁移需求；不新建万能 relations 表。

## 23. 当前最大的 5 个统一本体结构问题（W）

1. **无 Canonical BrainRegion 实体**：canonical_id 列是孤儿回填（引用了不存在的 label_code 列），跨 Atlas 概念身份完全缺失；mirror 全部锚在 candidate UUID 上。
2. **粒度三套词汇并存 + Atlas/Granularity 混用**：parser 短值集 / enum / 001 CHECK 三套；伪造 source_atlas（llm_circuit_connection_extraction、llm_bundle）承载粒度；species 靠 atlas 字符串子串推断（"allen"→mouse 误判 HBA）。
3. **脑区层级零存储**：part_of 无处落地；Brainnetome/HCP/Siibra 的 lobe/父级与 Allen structure_id_path 全部悬空（parser 产出无消费者）。
4. **无断言语义**：全部事实统一 llm_suggested；asserted/inferred/candidate 无字段；跨粒度写入被硬禁（SameGranularityValidationError），而推理需求必然跨粒度。
5. **物种语义缺失**：行级无 species；Allen_HBA（human）与 Mouse Allen connectivity 证据混语境；对齐（UBERON/NIFSTD）86 条全 pending、0 落地。

## 24. Macro BrainRegion Candidate v1（J）

数据来源：Allen HBA structures.json（1,327 条，depth 字段齐全）+ Macro96 96 池 + 存量 aal3_labels.json。原则：**每个候选必须有数据支撑**；lobe 级概念（frontal/temporal…）因无直接 Allen 节点且需 lobe 映射表，**不进 v1**（留 BR2）。

| # | canonical_name_en | canonical_name_cn（建议） | level | suggested parent | Allen 支撑 | Macro96 支撑 | hemisphere | species | confidence | ambiguity |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Brain | 脑 | L0 whole_brain | — | root 997 | — | midline | human | high | 根节点，仅作为 partonomy 根 |
| 2 | Cerebrum | 大脑 | L1 macro | Brain | 567 CH | — | bilateral | human | high | — |
| 3 | Cerebral cortex | 大脑皮层 | L2 macro | Cerebrum | 688 CTX | —（皮层各叶） | bilateral | human | high | — |
| 4 | Isocortex | 同型皮层（新皮层） | L3 macro | Cerebral cortex | 315 | — | bilateral | human | high | Allen 名 "Isocortex" |
| 5 | Olfactory areas | 嗅觉区 | L3 macro | Cerebral cortex | 698 OLF | — | bilateral | human | high | — |
| 6 | Hippocampal formation | 海马结构 | L3 macro | Cerebral cortex | 1089 HPF | hippocampus（left/right 锚点） | lateralized | human | high | Macro96 仅海马体，formation 含齿状回等——BR2 展开 |
| 7 | Cortical subplate | 皮层下板 | L3 macro | Cerebral cortex | 703 CTXsp | — | bilateral | human | high | — |
| 8 | Cerebral nuclei | 大脑核团 | L2 macro | Cerebrum | 623 CNU | — | bilateral | human | high | 含纹状体/苍白球/杏仁核（部分） |
| 9 | Striatum | 纹状体 | L3 macro | Cerebral nuclei | 477 STR | caudate/putamen/accumbens | lateralized | human | high | Macro96 三区均为其子区 |
| 10 | Pallidum | 苍白球 | L3 macro | Cerebral nuclei | 803 PAL | pallidum | lateralized | human | high | — |
| 11 | Amygdala | 杏仁核 | L3 macro | Cerebral nuclei | 核团分散于 703 下（LA/BLA/BMA/PA） | amygdala | lateralized | human | medium | Allen 无 "Amygdala" 聚合节点，需显式分组规则 |
| 12 | Claustrum | 屏状核 | L3 macro | Cortical subplate | 583 CLA | — | bilateral | human | medium | Macro96/AAL3 无直接对应（AAL3 有 insula 无 claustrum） |
| 13 | Interbrain (Diencephalon) | 间脑 | L1 macro | Brain | 1129 IB | ventral diencephalon（部分） | bilateral | human | high | Macro96 的 VD 是 FreeSurfer 残留结构，仅部分对应 |
| 14 | Thalamus | 丘脑 | L2 macro | Interbrain | 549 TH | thalamus proper | lateralized | human | high | — |
| 15 | Hypothalamus | 下丘脑 | L2 macro | Interbrain | 1097 HY | — | bilateral | human | high | Macro96 无直接项 |
| 16 | Brain stem | 脑干 | L1 macro | Brain | 343 BS | brain stem | midline | human | high | — |
| 17 | Midbrain | 中脑 | L2 macro | Brain stem | 313 MB | — | midline | human | high | — |
| 18 | Pons | 脑桥 | L2 macro | Brain stem | 771 P | — | midline | human | high | — |
| 19 | Medulla | 延髓 | L2 macro | Brain stem | 354 MY | — | midline | human | high | — |
| 20 | Cerebellum | 小脑 | L1 macro | Brain | 512 CB | cerebellum exterior/white matter | bilateral | human | high | — |
| 21 | Cerebellar cortex | 小脑皮层 | L2 macro | Cerebellum | 528 CBX | — | bilateral | human | high | — |
| 22 | Cerebellar vermal regions | 小脑蚓部 | L3 macro | Cerebellar cortex | 645 VERM | vermal lobules I-V/VI-VII/VIII-X | midline | human | high | Macro96 3 条 unknown 恰好对应 |
| 23 | Cerebellar hemispheric regions | 小脑半球区 | L3 macro | Cerebellar cortex | 1073 HEM | — | bilateral | human | high | — |
| 24 | Cerebellar nuclei | 小脑核团 | L2 macro | Cerebellum | 519 CBN（FN/IP/DN/VeCB） | — | bilateral | human | high | 仅 Allen 支撑 |
| 25 | Basal forebrain | 基底前脑 | L2 macro | Cerebrum | 无 Allen 聚合节点 | basal forebrain（left/right） | lateralized | human | low | 仅 Macro96 支撑；Allen 胆碱能核散布——候选而非确定项 |

v1 = 25 候选（L0 1 + L1 6 + L2 9 + L3 9），全部有 Allen 或 Macro96 直接数据支撑。排除项（非脑区或非神经结构，不入 v1）：white matter / fiber tracts（Allen 1009）、ventricular system（Allen 73，含侧脑室/三/四脑室）、CSF、grooves（Allen 1024）、retina、cranial nerves。lobe 级（Frontal/Temporal/Parietal/Occipital/Cingulate/Insular lobe）与 Limbic system 聚合不在 v1（需要显式 lobe 映射表，Allen 无节点；Macro96/AAL3 名称隐含但无结构支撑）。

---

## 25. 本阶段完成核对（15 问）

| # | 问题 | 答案 |
|---|---|---|
| 1 | BrainRegion canonical identity 应该是什么 | 独立 canonical_brain_regions.id（概念级，hemisphere 中性，species=human）；运行时镜像锚定先保留 candidate UUID，逐步换成 canonical_region_id |
| 2 | Atlas region 如何映射 canonical | 扩展 ontology_alignment_candidates（治理状态 exact/close/broader/narrower/uncertain/rejected）+ candidate.canonical_region_id 锚点；不自动合并 |
| 3 | Hemisphere 怎么处理 | 概念中性 + 左右锚点（方案 B）；连接端点保持分侧候选 id，方向不丢 |
| 4 | Species 怎么处理 | 概念带 species 字段（v1 human）；跨物种仅 homologous_to，禁 equivalent；修 paper_search_multi 字符串推断 |
| 5 | Macro/Meso/Parcel/Fine 怎么定义 | brain_region_anatomical 域词表 L0-L5（whole_brain→macro→meso→parcel→fine→ultra_fine），level_order 排序，不写死代码 |
| 6 | part_of 怎么保存 | canonical_region_hierarchy 专属表（child part_of parent），不用通用 parent_id，不用 subclass_of |
| 7 | Fine Connection 如何向 Macro roll-up | aggregated_into 链 + has_descendant_projection_to 谓词，assertion_type=inferred，带推理元数据 |
| 8 | Macro Connection 为什么不能向下推成事实 | 向下展开只产生 candidate（candidate_pools），缺独立宏观证据不得断言子区事实 |
| 9 | Circuit 如何跨粒度抽象 | abstracted_to（解剖抽象）与 subcircuit_of（生物子回路）分离；memberships 已支撑拓扑 |
| 10 | Function hierarchy 如何与其他三类连接 | P1 不变（ontology_terms.id + subclass_of）；横向谓词已存在（participates/modulates/involved/associated） |
| 11 | asserted/inferred/candidate 如何区分 | 新增 assertion_type 词表 + 字段；LLM 提取恒为 candidate 性质直至审核通过 |
| 12 | confidence 如何随推理变化 | inferred = source × mapping × rule_weight × attenuation(depth)；不改 P1 公式 |
| 13 | Evidence 如何追踪到 asserted source | derived_from → asserted 事实 → mirror_evidence_records → 论文；只继承链不伪造 direct evidence |
| 14 | 四类对象怎样处在同一语义体系 | Semantic Core：统一 Granularity/AssertionType/Provenance/Confidence/InferenceMetadata 契约；不共用一张表；Triple=projection 不变 |
| 15 | Macro v1 从哪些真实数据建立 | Allen HBA 层级（1,327 结构，depth 0-6）+ Macro96 96 池 + aal3_labels.json；25 候选（§24） |

---

## 26. 本阶段产物

- 本设计文档（新增 docs）
- 只读审计（6 代理 + 只读 SQL 核实）
- **未做任何数据库写入/迁移/前端改动**
- 未启动 BR1 及任何后续实施

---

## 27. BR1 实施记录（2026-08-20，已完成）

> BR1 已按本设计实施（L0/L1 Canonical BrainRegion Core + Macro Backbone）。
> 与 §6/§7/§8 设计一致；真实执行细节以代码与 DB 为准。

**产物**：
- 迁移 `backend/migrations/20260822_canonical_brain_region.sql`（canonical_brain_regions + canonical_region_hierarchy + candidate.canonical_region_id FK + granularity_domain/level、hemisphere_policy、mapping_match_type 词表）
- 模型 `app/models/canonical_region.py`、Schema `app/schemas/canonical_region.py`
- Service `app/services/canonical_region_service.py`（CRUD / part_of 约束 / 递归 CTE 遍历 / grounding / integrity checker / Connection+Circuit readiness helper）
- Router `/api/canonical-regions`（main.py 注册）
- Species 修复：`paper_search_multi._resolve_expected_species`（显式 metadata 优先；"allen"/"molecular" 不再推断 mouse）+ `evidence_target_adapter._target_species`（从 atlas_resources 注入）
- 种子脚本 `scripts/seed_brain_region_backbone.py`（幂等）
- 测试 `tests/test_canonical_brain_region_br1.py`（20 项全绿；全量回归无新增失败）

**真实 DB 状态（e2e）**：
- L0=1：`ng:br:brain`（whole_brain, bilateral, human, active）
- L1=4：`ng:br:cerebrum` / `ng:br:diencephalon` / `ng:br:brain_stem` / `ng:br:cerebellum`（macro，全 active）
- L1→L0 part_of 边 4 条（Allen path 溯源；diencephalon 记录经典划分偏离 Allen path 的说明）
- candidate grounding 7 行：Brain stem exact×1（Macro96）、Cerebellum close×4（L/R exterior+white matter）、Diencephalon close×2（L/R ventral diencephalon）
- integrity checker：`ok=true`，L2+ count=0，orphan=0，cross-species=0，isolated=0

**25 候选重新分类（L0/L1 写入；L2/L3 候选清单留 BR2/BR3）**：
- L0：Brain
- L1：Cerebrum / Diencephalon(Interbrain) / Brain stem / Cerebellum（原报告的 Cerebral nuclei、Basal forebrain 降为 L2——Cerebral nuclei 与 Cerebral cortex 同级 Allen depth 3，Basal forebrain 仅 Macro96 支撑）
- L2（候选）：Cerebral cortex、Cerebral nuclei、Cortical plate、Cortical subplate、Thalamus、Hypothalamus、Midbrain、Pons、Medulla、Cerebellar cortex、Cerebellar nuclei、Basal forebrain
- L3（候选）：Isocortex、Olfactory areas、Hippocampal formation、Amygdala、Claustrum、Striatum、Pallidum、Cerebellar vermal regions、Cerebellar hemispheric regions

**BR2 就绪判断**：yes —— canonical 层已落地、grounding 链路已验证、遍历/完整性基建支持任意深度、Connection/Circuit readiness 已提供（CN1/CR1 前置条件具备）。

---

## 28. BR2 实施记录（2026-08-20，已完成）

> Macro96 → Canonical BrainRegion L2 (Clinical regions)。层级模型修订：
> **L0 Brain → L1 Macro system → L2 Clinical regions (Macro96) → L3 Research → L4 Fine → L5 Ultra-fine（未来）**。
> 用户决策：Macro96 96 池整体为临床参照系，macro 层（L1 系统 + L2 临床）为**临床使用边界**，向下细分供研究/推理。

**产物**：
- 迁移 `backend/migrations/20260823_macro96_canonical_l2.sql`：granularity_level 词表修订（macro=L1 system、新增 clinical(L2)/research(L3)、meso/parcel 标 deprecated）+ `connection_region_alignment` 表
- 种子脚本 `scripts/seed_macro96_canonical_l2.py`（幂等，52 个 hemisphere-neutral key 分组）
- Service 扩展：`_GRANULARITY_LEVEL_ORDER` 修订、`_load_level_order` 过滤 deprecated、`resolve_and_record_connection_alignment`（BR2-6）、integrity 新增 hemisphere conflict / Macro96 96/96 验收（BR2-7）
- 模型 `ConnectionRegionAlignment`；测试 `tests/test_macro96_canonical_br2.py`（11 项）

**真实 DB 状态（e2e）**：
- canonical 概念 53 = L0 1 + L1 4 + **L2 clinical 48**
- hierarchy 边 52 = 48（L2→L1/L0）+ 4（L1→L0）
- **Macro96 grounding 96/96**（mapped_candidates=96）
- integrity：`ok=true`，hemisphere conflict=0、orphan=0、cross-species=0、isolated=0

**L2 48 概念构成**：31 皮层（→Cerebrum）+ 7 皮层下（accumbens/amygdala/basal forebrain/caudate/hippocampus/pallidum/putamen，→Cerebrum）+ thalamus proper（→Diencephalon）+ 3 vermal lobules（→Cerebellum）+ lateral/inferior lateral/3rd/4th ventricle + CSF + white matter（→Brain）
**复用 L1 概念（无新节点）**：Brain stem、Cerebellum（exterior+WM）、Diencephalon（VD）——7 个 96 池候选直接锚定 L1
**hemisphere 策略**：44 对左右结构 → 44 个 lateralized 概念（左右候选锚同一概念，laterality 保留在候选行）；5 个 midline + 3 个 unknown（vermal）→ midline_unpaired

**连接未动**：70,029 行连接零修改；`connection_region_alignment` 提供端点 canonical 解析落库（CN1 前置）。

**BR3 就绪判断**：yes —— 只有 L0–L2 完整后（本阶段达成）才有资格对齐 Allen/Brainnetome/HCP-MMP 细粒度 Atlas；避免小鼠区域混入人脑、层级混乱、连接无法向上推理。
