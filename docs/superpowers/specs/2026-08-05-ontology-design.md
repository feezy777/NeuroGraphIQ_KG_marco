# 本体层与论文证据验证设计（Phase 1：质量控制优先）

> 状态：待用户评审
> 日期：2026-08-05
> 来源：grill-me 决策树会话（Q1–Q12，用户已逐轮确认“按推荐来”）

## 1. 背景与现状

NeuroGraphIQ 已具备知识图谱形态（typed entities + typed edges + S/P/O 三元组 + 证据与治理状态），但缺四层：本体层、标准标识、正式事实层、标准查询接口。Phase 1 只解决“本体层”，且以**质量控制**为第一目的：用本体把 LLM 自由文本输出变成可校验、可锚定、可晋升的知识。

现状事实（2026-08-05 实测）：

| 对象 | 行数 | 去重术语（lower） |
|---|---|---|
| mirror_region_connections | 70,029 | — |
| mirror_region_circuits | 53,562 | — |
| mirror_circuit_functions | 100,627 | 5,687 |
| mirror_projection_functions | 6,118 | 2,029 |
| mirror_region_functions | 142 | 63 |

现状约束：

- `function_category` / `relation_type` 硬编码在 `mirror_region_functions`、`mirror_projection_functions` 两张表的 CHECK 约束里，同时在 `llm_function_extraction_service.py` / `llm_projection_function_extraction_service.py` 里以 frozenset 重复定义；status / step_type / role 等枚举也散落在多张表 CHECK 中；
- `function_term` 是自由文本，仅做 `lower().strip()` 去重，没有任何本体锚点；
- 无 ontology 表；`TRIPLE_MODEL_AND_ONTOLOGY_DESIGN.md` 仍是规划文档（`ontology_predicate_registry` planned、triple 层未迁移）；
- 无 SPARQL/GQL 端点；Neo4j 同步服务未接线。

## 2. 已确认决策（Q1–Q12）

| # | 决策 | 结论 |
|---|---|---|
| Q1 | 本体第一目的 | 质量控制（约束/校验/门禁）；标准互操作与查询留 Phase 2 |
| Q2 | 第一版范围 | 功能术语注册表 + 谓词/枚举注册表 + 脑区外部标识字段；回路/证据不进本体 |
| Q3 | 落地方式 | 关系库表 + 迁移，不上 TTL/OWL/推理引擎 |
| Q4 | 谓词载体 | `ontology_predicates` 注册表取代 CHECK 硬编码（实现细化见 4.1） |
| Q5 | 术语挂接 | `ontology_terms` + 业务表 nullable `term_id` + grounding 映射表；原文保留 |
| Q6 | 标识符 | 内部短码（`ng:func:memory`）；UBERON/NIFSTD 放外部对齐表；不生成 RDF |
| Q7 | 术语治理 | LLM 只能提议 `proposed`，人工激活；完全同义词自动合并 |
| Q8 | 校验规则 | 3 硬 1 软（术语锚定/谓词存在/枚举合法 = blocker；脑区外部标识缺失 = warning） |
| Q9 | 生成链路 | 混合模式：prompt 注入高频术语但允许新词；落地即锚定；frozenset 改读注册表 |
| Q10 | 落地顺序 | 设计文档 → 迁移 → 注册表服务/API → 存量对齐（先出全景报告）→ 校验+链路接入 → 前端只读 → 验收 |
| Q11 | 验收标准 | 5 条（见第 13 节）；RDF 导出放 Phase 2 |
| Q12 | 交付物边界 | 前端只做只读覆盖率卡片 + proposed 列表；管理面板 Phase 2 |

## 3. 目标与非目标

Phase 1 做：

- 本体词汇表（谓词 / 关系类型 / 分类 / 域 / 角色 / 效应类型）；
- 功能术语注册表 + 同义词 + 外部标识映射 + grounding 映射；
- 业务表挂 `term_id`，移除 CHECK / frozenset 硬编码；
- 镜像校验规则（3 硬 1 软）；
- 提取/字段补全改读注册表，输出落地即锚定；
- 存量约 7,000 个去重术语对齐（≥95%），先交付术语全景报告；
- 前端只读覆盖率卡片 + proposed 词列表。
- 论文证据验证（Phase B，见第 16 章）：低置信数据接真实文献检索佐证，置信度调整需人工/双模型确认。

Phase 1 不做（明确 YAGNI）：

- RDF/OWL、SPARQL/GQL、推理引擎；
- 完整术语管理面板（审批先走 API/SQL）；
- 回路 / 步骤 / 证据的本体化；
- 全量脑区自动对齐 UBERON/NIFSTD（先加字段 + 核心图谱手工/半自动对齐）。

## 4. 数据模型

新增 5 张表，迁移文件：`backend/migrations/20260805_ontology_layer.sql`（幂等：`IF NOT EXISTS` / `ADD COLUMN IF NOT EXISTS` / `DROP CONSTRAINT IF EXISTS`）。

### 4.1 ontology_vocabularies（词汇表：谓词/枚举合并）

```text
id            UUID PK
code          VARCHAR(128) NOT NULL        -- 如 associated_with / motor / memory
vocab_type    VARCHAR(32)  NOT NULL        -- predicate | relation_type | category | domain | role | effect_type
label_cn      VARCHAR(256)
label_en      VARCHAR(256)
description   TEXT
status        VARCHAR(16)  NOT NULL DEFAULT 'active'   -- active | deprecated
seq           INT          NOT NULL DEFAULT 0
created_at / updated_at
UNIQUE (code, vocab_type)
```

> **相对 Q4 的实现细化（需你确认）**：谓词与枚举合并为一张词汇表，避免 6 张几乎同构的表；“CHECK → FK”调整为“**移除 CHECK + 服务层/校验规则读注册表**”。原因是过滤型外键（只允许 relation_type 类别的值）需要复合键或触发器，收益低、迁移风险高。`term_id` 用真外键；`category` / `relation_type` 等保留 TEXT 标签列，合法性由注册表 + 校验规则保证。

### 4.2 ontology_terms（术语注册表）

```text
id               UUID PK
term_code        VARCHAR(128) NOT NULL UNIQUE   -- ng:func:memory
canonical_term_en VARCHAR(512) NOT NULL
canonical_term_cn VARCHAR(512)
term_type        VARCHAR(32) NOT NULL DEFAULT 'function'   -- function | projection | region | other
category         VARCHAR(128)                   -- 软引用 ontology_vocabularies(category)
domain           VARCHAR(128)
role             VARCHAR(128)
effect_type      VARCHAR(128)
description      TEXT
status           VARCHAR(16) NOT NULL DEFAULT 'proposed'   -- proposed | active | deprecated
created_by       VARCHAR(64) NOT NULL DEFAULT 'manual'     -- system | llm | manual
created_at / updated_at
```

### 4.3 ontology_term_synonyms（同义词）

```text
id            UUID PK
term_id       UUID NOT NULL REFERENCES ontology_terms(id) ON DELETE CASCADE
synonym_text  VARCHAR(512) NOT NULL
lang          VARCHAR(8) NOT NULL DEFAULT 'en'
match_type    VARCHAR(16) NOT NULL            -- exact | normalized | synonym | llm
confidence    NUMERIC
status        VARCHAR(16) NOT NULL DEFAULT 'active'   -- active | disabled
UNIQUE (term_id, synonym_text, lang)
```

### 4.4 ontology_term_external_mappings（外部标准标识对齐）

```text
id            UUID PK
term_id       UUID NOT NULL REFERENCES ontology_terms(id) ON DELETE CASCADE
external_system VARCHAR(64) NOT NULL          -- UBERON | NIFSTD | NeuroLex | BTO
external_iri  VARCHAR(512) NOT NULL
match_type    VARCHAR(16) NOT NULL            -- exact | close_match | partial_match
confidence    NUMERIC
verified_by   VARCHAR(64)
UNIQUE (term_id, external_system, external_iri)
```

### 4.5 ontology_term_groundings（目标记录 → 术语锚定）

```text
id            UUID PK
target_type   VARCHAR(32) NOT NULL            -- circuit_function | projection_function | region_function
target_id     UUID NOT NULL
term_id       UUID REFERENCES ontology_terms(id) ON DELETE SET NULL
grounded_by   VARCHAR(16) NOT NULL            -- deterministic | synonym | llm | manual | ungrounded
confidence    NUMERIC
created_by    VARCHAR(64)
grounded_at   TIMESTAMPTZ NOT NULL DEFAULT now()
UNIQUE (target_type, target_id)               -- 一条目标记录只有一个 grounding，可更新
```

### 4.6 业务表改动

- `mirror_circuit_functions` / `mirror_projection_functions` / `mirror_region_functions`：各加 `term_id UUID NULL REFERENCES ontology_terms(id)`；`function_term*` 原文保留作快照；
- 移除 CHECK 约束（先回填非法值为 `unknown` 再 DROP），仅 4 个：`chk_mirror_function_category`、`chk_mirror_function_relation_type`（mirror_region_functions）、`chk_mirror_projection_function_category`、`chk_mirror_projection_function_relation_type`（mirror_projection_functions）；
- `mirror_circuit_functions` 本身没有 function_category/relation_type 列与对应 CHECK，只加 `term_id`；
- `mirror_circuit_steps` 的 `step_type` / `role` CHECK 保留不动（回路/步骤本体化不在 Phase 1 范围）；
- `final_circuit_functions` / `final_projection_functions` 只有 final_status CHECK，无枚举 CHECK，**无需改动**，未来注册表扩容不会阻塞晋升；
- `candidate_brain_regions`：加 `uberon_iri VARCHAR(512)`、`nifstd_iri VARCHAR(512)`、`alignment_status VARCHAR(32) NOT NULL DEFAULT 'not_aligned'`；
- `mirror_region_functions` / `mirror_projection_functions` 的 `function_category` / `relation_type` 列保留 TEXT，不加 FK（见 4.1 细化说明）；`mirror_circuit_functions` 无这两列。

## 5. 种子数据

迁移内写入 `ontology_vocabularies` 种子（与现有 CHECK/frozenset 完全一致，避免破坏存量）：

- `relation_type`：involved_in、associated_with、necessary_for、modulates、participates_in、uncertain_association、unknown；
- `function_category`：motor、sensory、visual、auditory、language、memory、emotion、executive_control、attention、autonomic、default_mode、salience、reward、cognitive、unknown；
- `predicate`（来自 TRIPLE_MODEL_AND_ONTOLOGY_DESIGN.md）：structurally_connects_to、functionally_connects_to、effectively_connects_to、projects_to、associated_with、coactivates_with、has_uncertain_connection_to、has_participant_region、has_ordered_participant、instance_of_circuit_type、associated_with_function、involved_in_function、necessary_for_function、modulates_function、participates_in_process、close_match、partial_match、related_to、not_same_as、supported_by_evidence、generated_by_llm_run、confirmed_by_reviewer（`associated_with` 同时存在于 relation_type 与 predicate，靠 `(code, vocab_type)` 区分，属有意为之）；
- `domain` / `role` / `effect_type`：初始从现有数据 DISTINCT 值提取（术语全景报告定稿），未知归 `unknown`。

## 6. 术语治理流程

```text
LLM 提取/字段补全输出
  └─ grounding 服务：
       exact（归一匹配）→ synonym（同义词表）→ LLM 建议（confidence ≥ 0.9）
       └─ 全部未命中 → grounded_by=ungrounded + 自动创建 proposed 词（含来源）
人工（API/SQL，Phase 1）：
  propose → activate（激活时合并同义词）→ active
  active → deprecate → deprecated（新输出禁止锚定，旧记录保留）
```

规则：

- LLM 只能创建 `proposed` 词，绝不自动激活；
- 完全同义词（normalized 后相同）自动合并到已有 `active` 词；
- `deprecated` 词在 prompt 与校验中不可用，但历史 grounding 保留。

## 7. 存量对齐方案（约 7,000 个去重术语）

1. **术语全景报告**（先交付）：`DISTINCT lower(function_term*)` + 计数 + 样例 + 现有 category/domain/role 分布；
2. **Deterministic pass**：lower/trim/去标点/压缩空白后 exact 匹配；
3. **同义词词典**：人工维护 300–600 条高频映射（如 `working memory` → `memory`、`attentional control` → `attention`）；
4. **LLM residual**：对剩余未命中分批调用 deepseek-v4-flash，输出 `{canonical_term, confidence}`；≥0.9 → grounding + 创建 proposed 词；<0.9 → 显式 `ungrounded`；
5. **验收**：≥95% 去重术语锚定到 active/可解释状态（`grounded_by ∈ deterministic/synonym/llm` 且术语 active），其余显式 `ungrounded`。

## 8. 校验规则接入（mirror_rule_validation_service）

| 规则码 | 含义 | 级别 |
|---|---|---|
| `ONT_TERM_UNGROUNDED` | function_term 未锚定，或锚定到 proposed/deprecated | blocker |
| `ONT_PREDICATE_UNKNOWN` | relation_type / predicate 不在词汇表 active 值内 | blocker |
| `ONT_ENUM_INVALID` | category / domain / role / effect_type 不在词汇表内 | blocker |
| `ONT_REGION_ALIGNMENT_MISSING` | candidate_brain_regions 缺 uberon_iri / nifstd_iri | warning |

结果写入 `mirror_rule_validation_results`，前端展示规则码、原因与修复建议（如“锚定到术语 X”）。

## 9. 生成链路集成

- 删除 `llm_function_extraction_service.py` / `llm_projection_function_extraction_service.py` 中的 `DEFAULT_ALLOWED_FUNCTION_CATEGORIES` / `DEFAULT_ALLOWED_RELATION_TYPES` frozenset，改为从 `ontology_vocabularies` 读取 active 值；
- prompt 注入按 grounding 计数排序的高频 top-N canonical 术语作为参考，但**允许输出新词**（新词 → proposed）；
- `field_completion_registry` 的 category/relation_type 允许值改从注册表动态生成；function_term 补全提供 canonical 候选；
- 写入后强制 grounding（不阻塞写入），未锚定记录由校验门禁阻断晋升。

## 10. API（backend/app/routers/ontology.py，prefix `/api/ontology`）

| 端点 | 用途 |
|---|---|
| `GET /vocabularies?vocab_type=` | 查询词汇表 |
| `POST /vocabularies` | 新增/弃用词汇（admin） |
| `GET /terms?status=&q=&page=` | 查询术语（含 proposed 列表） |
| `POST /terms` | 提议术语（LLM 服务内部调用） |
| `POST /terms/{id}/activate` / `deprecate` | 激活 / 弃用（admin） |
| `POST /terms/{id}/merge` | 合并到目标术语（admin） |
| `GET /coverage` | 只读覆盖率（总数/已锚定/未锚定/按类型/按 grounding 方式） |
| `GET /groundings?target_type=&target_id=` | 查询锚定记录 |
| `POST /groundings/run` | 确定性对齐批次（存量用） |
| `GET /report/term-panorama` | 术语全景报告 |

写操作标记 `created_by/updated_by`，LLM 内部调用走 service 层，不暴露 admin 端点。

## 11. 前端（Phase 1 最小）

- 数据中心 / 校验中心：只读“本体锚定覆盖率”卡片（`/coverage`）；
- proposed 词列表（只读：词、来源、出现次数）；
- Phase 2 再做管理面板（审批、合并、同义词编辑）。

## 12. 测试策略

- 单元：词汇/术语 CRUD、grounding 确定性归一、merge/deprecate 规则、prompt 构建读注册表、校验规则生成 `ONT_*` 结果；
- 迁移：`20260805_ontology_layer.sql` 幂等 + 回填正确性；
- 集成：模拟 LLM 输出 → grounding → 校验 blocker → `/coverage` 反映；
- 对齐抽查：全量对齐后随机 100 条人工核对 grounding 准确率。

## 13. 验收标准（Q11 确认的 5 条）

a) ≥95% 去重术语锚定到 active/可解释状态，其余显式 `ungrounded`；
b) 谓词/枚举不再有 DDL/代码硬编码（CHECK 与 frozenset 全部清除），一律读注册表；
c) 镜像校验能产出 `ONT_*` blocker，且跑一轮 0 系统错误；
d) 前端可见覆盖率卡片与 proposed 词列表；
e) 新提取/补全输出落地即锚定（proposed 池自动增长）。

> RDF/OWL 导出、SPARQL/GQL 属于 Phase 2，不计入本验收。

## 14. 实施顺序（Q10，含证据验证两阶段）

### Phase A：本体层（原 Q10 ①–⑧）

1. 本设计文档评审通过；
2. 数据库迁移（本体 5 表 + 业务表 term_id + 移除 4 个 CHECK）+ 种子数据；
3. 注册表服务与 API（CRUD/审批/合并/查询/coverage）；
4. 术语全景报告（先交付给用户过目）；
5. 存量对齐（deterministic → 同义词词典 → LLM 残差）；
6. 校验规则接入 + 提取/补全改读注册表；
7. 前端只读覆盖率卡片 + proposed 列表；
8. 验收（第 13 节 5 条）。

### Phase B：论文证据验证（第 16 章）

9. 证据字段迁移 + 文献检索/判定服务；
10. 置信度校准诊断（300 条分层抽样，先出报告不改数据）；
11. 投影功能 200 条试点（低置信 150 + 高置信 50 对照）；
12. EV_* 校验规则 + 预算护栏；
13. 数据中心 / 验证中心证据展示（面板、待确认队列、覆盖率卡）；
14. 试点验收 + 扩展决策（投影功能 > 回路功能 > 连接 > 回路）。

## 15. 风险与缓解

| 风险 | 缓解 |
|---|---|
| LLM 语义合并错误 | grounding 只产生“建议”，激活必须人工；同义词合并保留来源 |
| 10 万行回填/对齐性能 | 分批执行 + `term_id` 索引；对齐只处理去重术语 |
| 移除 CHECK 后历史非法值 | 先回填 `unknown` 再 DROP，服务层同时兜底 |
| 术语漂移（多 canonical 表达同一概念） | 定期 coverage 报告 + 人工合并；prompt 注入高频词抑制漂移 |
| 与正在运行的全量 molecular 提取任务并行 | 新逻辑默认兼容旧数据，存量对齐与校验在提取完成后切换 |

## 16. 论文证据验证（Phase B）

> 用户新增需求：低置信度数据由大模型检索真实论文佐证；数据中心与验证中心都要展示证据。决策经 grill-me 会话 Q1–Q8 确认。

### 16.1 背景与事实

- 置信度普遍偏低（2026-08-05 实测）：回路功能 84.8% < 0.5、投影功能 96.8% < 0.5、连接 90.4% < 0.5、回路 92.2% < 0.5；
- 现有 `mirror_evidence_records` 99,478 条全部是 `llm_explanation`，无一条论文引用；
- 大模型不会真实检索文献，凭记忆生成的引用存在编造风险，必须接入文献检索 API 并强制校验。

### 16.2 已确认决策（Q1–Q8 + UI）

| # | 决策 | 结论 |
|---|---|---|
| Q1 | 论文来源 | 免费文献检索 API（Europe PMC 主 + PubMed 兜底），引用必须来自检索结果，禁止 LLM 编造 |
| Q2 | 前置步骤 | 先做 300 条置信度校准诊断，再定验证范围；不做 20 万条无差别验证 |
| Q3 | 试点规模 | 先小批次（500 条内）跑通流程再扩 |
| Q4 | 证据用法 | 证据只作置信度上调候选；最终提升必须人工确认或双模型一致 |
| Q5 | 存储 | 复用 `mirror_evidence_records` + 新增字段，不建平行证据库 |
| Q6 | 校准报告 | 只出报告不改存量；重打分单独立项批准 |
| Q7 | 试点范围 | 投影功能 200 条（低置信 150 + 高置信 50 对照） |
| Q8 | 预算护栏 | 试点不设上限；扩展阶段单任务预算上限默认 50 美元，超限自动暂停 |
| UI | 展示 | 数据中心对象详情证据面板 + 验证中心 EV_* 详情 / 待确认队列 / 覆盖率卡 |

### 16.3 数据模型改动

迁移文件：`backend/migrations/20260805_evidence_verification.sql`（幂等）。

`mirror_evidence_records` 新增列：

```text
evidence_direction           VARCHAR(16)            -- supports | partial | contradicts | not_found
verification_status          VARCHAR(16) DEFAULT 'pending'   -- pending | verified | rejected
paper_source                 VARCHAR(32)            -- europepmc | pubmed | openalex
paper_pmid                   VARCHAR(64)
paper_doi                    VARCHAR(256)
paper_title                  TEXT
paper_journal                VARCHAR(256)
paper_year                   INT
suggested_confidence         NUMERIC                -- 上调候选值，上限 0.85
confidence_adjustment_status VARCHAR(16) DEFAULT 'none'   -- none | pending | applied | rejected
verification_by              VARCHAR(64)
verification_at              TIMESTAMPTZ
```

- 现有 `citation_json` / `source_reference_text` 保留，存完整文献快照；
- 业务表 `confidence` **不直接改**：只有 `verification_status=verified` 且人工/双模型确认后才允许更新，并写入 `confidence_adjustment_status=applied`；
- `direction=not_found` 也算完成一轮验证（`verification_status=verified`），但业务置信度不调整。

### 16.4 检索与判定流程

```text
对象（如投影功能：术语 + 源/靶区域）
  └─ 1. 检索：Europe PMC REST（5 req/s 限速），PubMed 兜底，top-N 候选
  └─ 2. 判定：deepseek-v4-flash 读标题+摘要，输出
             {direction, papers[], reason}   -- papers 必须来自检索结果
  └─ 3. 校验：PMID/DOI 与检索结果比对，真实性硬校验；direction 四选一
  └─ 4. 存储：mirror_evidence_records（evidence_type='paper_verification'）
  └─ 5. 使用：support/partial → suggested_confidence 候选
              → 人工确认或双模型一致 → verified → 才允许更新业务表 confidence
              not_found → 标记已验证未找到，置信度不动
```

### 16.5 置信度校准诊断（前置步骤）

- 300 条分层抽样：低置信 200 + 中置信 50 + 高置信 50，按对象类型覆盖；
- 现有双模型验证服务交叉复核，另抽 30 条人工核验兜底；
- 产出校准报告：每类 precision@置信区间、建议阈值、是否值得重打分；
- 不改存量数据；若建议重打分，作为独立任务另行批准。

### 16.6 试点与扩展

- 试点：投影功能 200 条（低置信 150 + 高置信 50 对照），跑通全流程；
- 扩展顺序：投影功能 > 回路功能 > 连接 > 回路；
- 限速：文献 API 5 req/s；LLM 批量 20–50 条/批；
- 预算：试点不限；扩展阶段单任务预算上限默认 50 美元，超限自动暂停（运行配置可调）。

### 16.7 校验规则（EV_*，接入 mirror_rule_validation_service）

| 规则码 | 含义 | 级别 |
|---|---|---|
| `EV_REFERENCE_INVALID` | 引用的 PMID/DOI 校验失败或不存在 | blocker |
| `EV_DIRECTION_INVALID` | evidence_direction 不在四类内 | blocker |
| `EV_VERIFICATION_PENDING` | 依赖证据提升置信度但未人工/双模型确认 | blocker |
| `EV_EVIDENCE_MISSING` | 标记“需要论文验证”但无 paper_verification 记录 | warning |

### 16.8 前端展示（数据中心 + 验证中心）

- 数据中心：对象详情新增“证据面板”——论文列表（PMID/DOI 可点击跳转）、方向、验证状态、置信度调整记录；列表页加证据徽章（有论文支持 / 待验证 / 未找到）；
- 验证中心：EV_* 规则详情；“论文支持但未确认”对象进待确认队列（人工确认或双模型）；证据覆盖率统计卡（有真实引用数 / 待验证数 / 未找到数）；
- 新增只读端点：`GET /api/evidence/coverage`、`GET /api/evidence/objects?target_type=&verification_status=`、`GET /api/evidence/objects/{target_type}/{target_id}`。

### 16.9 验收标准（Phase B）

a) 试点 200 条跑通，30 条人工抽检一致率出报告；
b) 引用真实性 100%：每条 PMID/DOI 通过校验，0 条 LLM 编造；
c) 置信度只允许在 `verified` 后调整，且上限 0.85；
d) 数据中心 / 验证中心可见证据面板、待确认队列与覆盖率卡；
e) 预算护栏生效（扩展任务超 50 美元自动暂停）。
