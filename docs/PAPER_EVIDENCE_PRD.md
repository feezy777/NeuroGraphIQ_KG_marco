# NeuroGraphIQ 论文佐证与证据治理系统 PRD

版本：V1.0
阶段：Phase A — 论文证据构建与人工审核
后续阶段：Phase B — 验证中心复核与多证据融合

---

# 1. 产品背景

NeuroGraphIQ 是基于 FastAPI + PostgreSQL + React 构建的脑科学知识图谱系统。

当前已经通过 LLM 提取约 11.4 万条知识数据，包括：

* 脑区连接；
* 投影功能；
* 回路；
* 回路功能；
* 回路步骤；
* 区域功能；
* 其他结构化知识。

当前主要问题是：

1. 大量知识置信度较低；
2. 原有 evidence_text 大量来自 `llm_explanation`，无法作为真实科学证据；
3. 缺少真实论文来源；
4. 论文与知识对象之间没有结构化证据关联；
5. 无法证明某条原文确实来自某篇论文；
6. 没有人工审核闭环；
7. 置信度更新不可解释、不可追溯、不可回滚。

因此需要建立独立的“论文佐证”能力。

---

# 2. 产品目标

建设完整的：

“知识对象 → 查找真实论文 → 获取全文 → 语义定位佐证片段 → DeepSeek 判断 → 原文真实性校验 → 人工审核 → 证据入库 → 更新置信度 → 验证中心复核”

工作流。

系统最终必须满足：

1. 每条正式论文证据都对应真实论文；
2. PMID / DOI / Europe PMC 来源可追溯；
3. 每个论文原文片段能够在原始摘要或 OA 全文中定位；
4. DeepSeek 可以做语义理解，但不能凭空生成证据；
5. 人工是正式证据入库的最终审核者；
6. 一篇论文允许产生多个证据片段；
7. 一个证据片段允许关联一个或多个知识对象；
8. 一个知识对象允许拥有多篇论文、多段证据；
9. 论文证据可以影响知识对象 confidence；
10. 所有置信度调整均可解释、可审计、可回滚；
11. 矛盾证据不能自动提高 confidence；
12. 论文 evidence 与普通 LLM explanation 明确区分；
13. 后续验证中心能够统一复核论文证据。

---

# 3. 非目标

Phase A 暂不实现：

* 自动证明整个知识图谱正确；
* 自动替代人工审核；
* 论文影响因子作为绝对证据权重；
* RDF / OWL 推理；
* 自动全文版权内容长期保存；
* 非公开论文全文绕过授权获取；
* DeepSeek 自动决定最终 confidence；
* DeepSeek 自动把证据直接晋升为正式证据。

---

# 4. 用户角色

## Reviewer

可以：

* 检索论文；
* 选择论文；
* 调用 DeepSeek 提取片段；
* 翻译；
* 修改证据方向；
* 修改推荐 confidence；
* 人工确认；
* 入库；
* 撤销自己或权限范围内的证据。

## Ontology Admin / Evidence Admin

额外可以：

* 批量任务；
* 修改规则；
* 撤销已审核证据；
* 批量重新计算 confidence；
* 查看完整审计日志；
* 管理异常证据。

## Viewer

只能查看。

---

# 5. 支持对象

论文佐证必须支持：

* connection；
* projection_function；
* circuit；
* circuit_function；
* circuit_step；
* region_function；
* 后续可扩展 brain_region 等。

证据记录本身可以跳转回原对象。

---

# 6. 用户入口

入口位于数据中心现有列表。

保持与“字段补全”相同的交互模式：

1. 用户勾选一条或多条记录；
2. 行操作条出现“论文佐证”；
3. 点击后打开底部论文佐证工作台；
4. 不新增独立数据中心 Tab；
5. 所选对象形成处理队列；
6. 用户逐条处理。

---

# 7. 核心产品原则

## 7.1 LLM 负责语义

DeepSeek 负责：

* 判断论文是否与目标事实相关；
* 从多个候选段落中识别真正相关部分；
* 判断支持、部分支持、矛盾或未找到；
* 给出解释；
* 翻译；
* 提取候选原文。

## 7.2 程序负责真实性

程序必须负责：

* 获取原始摘要 / OA 全文；
* 保留 paragraph_id；
* 保留 section；
* 验证返回 passage 确实存在于原文；
* 校验 PMID；
* 校验 DOI；
* 防重复；
* 数据事务；
* confidence 计算；
* 审计。

DeepSeek 不具有“证明原文真实性”的权限。

## 7.3 人工负责最终确认

只有人工确认后，证据才能进入：

`human_verified`

状态。

---

# 8. 整体工作流

数据中心选择对象

↓

打开论文佐证工作台

↓

Step 1：确认知识对象

↓

Step 2：构建检索命题

↓

Step 3：Europe PMC 检索论文

↓

Step 4：选择论文

↓

Step 5：读取 Abstract / OA Full Text

↓

Step 6：全文切分

↓

Step 7：语义召回候选段落

↓

Step 8：DeepSeek 精判

↓

Step 9：返回多个 passages

↓

Step 10：原文反向校验

↓

Step 11：人工审核

↓

Step 12：置信度影响预览

↓

Step 13：确认入库

↓

Step 14：更新 evidence

↓

Step 15：更新 confidence

↓

Step 16：进入下一条

↓

后续验证中心复核。

---

# 9. Step 1：知识对象标准化

在检索论文前，不能直接把数据库一行原样发送给 DeepSeek。

必须构造统一 Evidence Target DTO。

例如 connection：

* target_type；
* target_id；
* source_region；
* target_region；
* relation_type；
* connection_type；
* directionality；
* granularity；
* current_confidence；
* existing_evidence。

例如 circuit_function：

* circuit_name；
* circuit_regions；
* function_term；
* direction/effect；
* current_confidence。

最终生成一个结构化“待验证事实”：

Claim：

“Basolateral amygdala 到 infralimbic cortex 存在投射，该投射参与 fear extinction。”

系统同时保存：

* claim_text；
* claim_structured JSON；
* claim_version。

---

# 10. Step 2：论文检索

数据源第一阶段使用：

Europe PMC。

检索策略：

第一层：严格组合检索。

例如：

"BLA" AND "infralimbic cortex" AND "fear extinction"

第二层：标准名称 + 同义词。

第三层：拆词回退。

第四层：必要时减少功能词，仅搜索结构关系。

系统必须利用本体中心已有：

* canonical term；
* synonym；
* brain region canonical name；
* external mapping。

避免只使用数据库自由文本。

候选论文至少显示：

* title；
* author；
* journal；
* year；
* PMID；
* PMCID；
* DOI；
* abstract available；
* OA fulltext available；
* Europe PMC URL。

---

# 11. Step 3：论文全文处理

有摘要：

获取 Abstract。

有 OA：

优先获取结构化 XML。

全文禁止直接拼成一段大字符串。

解析为：

Paper

→ Section

→ Paragraph

例如：

Results

* results_p001
* results_p002

Discussion

* discussion_p001

每个 paragraph 保存：

* paragraph_id；
* section；
* paragraph_index；
* text；
* char_start；
* char_end；
* text_hash。

---

# 12. Step 4：全文语义召回

不推荐默认把整篇全文一次性送入 DeepSeek。

采用：

全文切片

→ 第一阶段语义召回

→ Top-K

→ DeepSeek 精判。

V1 可以先使用：

* 术语命中；
* synonym 命中；
* BM25 / PostgreSQL FTS；
* 简单语义 ranking；

获得 Top 10–30 paragraph windows。

后续可扩展 embedding。

每个窗口应包含：

当前 paragraph ±1 邻近 paragraph。

避免一句话缺上下文。

---

# 13. Step 5：DeepSeek 精判

输入：

* knowledge claim；
* structured target；
* paper metadata；
* candidate paragraphs。

输出必须为 JSON Schema / Pydantic 结构。

输出：

* paper_relevance；
* overall_direction；
* assessment；
* passages[]。

每个 passage：

* paragraph_id；
* section；
* passage；
* direction；
* evidence_level；
* reason；
* semantic_confidence。

direction：

* support；
* partial；
* contradict；
* not_found。

evidence_level：

* direct；
* indirect；
* interpretive；
* background。

定义：

direct：
实验结果直接支持目标知识。

indirect：
实验与目标知识高度相关，但需要一定推断。

interpretive：
作者在 Discussion 等部分进行解释。

background：
Introduction 或综述式引用其他研究。

DeepSeek 不允许自行生成 paragraph_id。

---

# 14. Step 6：原文真实性校验

DeepSeek 返回 passage 后：

后端必须重新从 paragraph_id 对应原始正文验证。

验证顺序：

1. exact match；
2. normalize whitespace；
3. normalize Unicode punctuation。

禁止：

* semantic similarity 通过；
* paraphrase 通过；
* 模型说是真的就通过。

无法匹配：

`source_verified=false`

该 passage：

* 可以展示；
* 必须红色警告；
* 禁止选择；
* 禁止入库。

---

# 15. Step 7：人工审核

人工必须能够看到：

英文原文；

中文翻译；

section；

paragraph locator；

证据方向；

evidence_level；

DeepSeek reason；

DeepSeek semantic confidence；

source_verified。

允许人工：

* 选择 / 取消片段；
* 修改 direction；
* 修改 evidence_level；
* 修改中文翻译；
* 添加人工备注；
* 修改 reviewer_confidence。

英文原始 passage 默认不可直接改写。

若允许截取其中部分文本：

必须基于原 paragraph 再次做 source 校验。

---

# 16. Step 8：置信度更新

DeepSeek 的 confidence 不能直接成为图谱 confidence。

正式计算由人工审核后的：

reviewer_confidence

驱动。

V1：

support：

new_confidence =
min(
0.85,
max(current_confidence, reviewer_confidence)
)

partial：

new_confidence =
min(
0.75,
max(current_confidence, reviewer_confidence)
)

contradict：

不自动更新。

生成：

confidence adjustment pending。

not_found：

不允许作为正式 paper evidence 入库。

页面必须展示：

当前置信度

→ 人工推荐值

→ 规则计算值

→ 最终值。

---

# 17. 多论文证据

同一对象允许：

Paper A → support

Paper B → support

Paper C → contradict。

V1 不自动进行复杂 Bayesian 合并。

先保留：

* 单次 evidence adjustment；
* adjustment history；
* 最终 current confidence。

Phase B 再统一设计多证据融合。

---

# 18. 一篇论文复用

底层不能设计成：

每个对象独立保存一份完整论文。

应该建立：

Paper

↓

Paper Paragraphs

↓

Evidence Records

↓

Evidence Targets

长期建议支持：

一个 evidence record / passage

→ 多个 knowledge target。

V1 如果改动范围过大，可以暂时保持单 target evidence record，但 paper 和 paragraph 必须支持复用。

---

# 19. 推荐数据模型

## paper_sources

保存论文级元数据：

* id；
* source；
* PMID；
* PMCID；
* DOI；
* title；
* journal；
* year；
* is_oa；
* metadata_json；
* abstract_hash；
* fulltext_hash；
* fetched_at。

唯一约束建议：

PMID；

或 normalized DOI。

## paper_passages

保存论文原文切片：

* id；
* paper_id；
* source_scope；
* section_title；
* paragraph_id；
* paragraph_index；
* text；
* text_hash；
* locator；
* created_at。

## mirror_evidence_records

作为证据主体：

* evidence_type = paper_verification；
* target_type；
* target_id；
* paper_id；
* evidence_direction；
* evidence_level；
* verification_status；
* suggested_confidence；
* reviewer_confidence；
* verification_by；
* verification_at；
* confidence_adjustment_status。

## mirror_evidence_passages

关联具体片段：

* id；
* evidence_id；
* paper_passage_id；
* passage_text_snapshot；
* translation_zh；
* direction；
* evidence_level；
* reason；
* semantic_confidence；
* source_verified；
* selected；
* passage_hash。

## confidence_adjustment_logs

* target_type；
* target_id；
* evidence_id；
* before_confidence；
* reviewer_confidence；
* calculated_confidence；
* after_confidence；
* formula_version；
* status；
* applied_by；
* applied_at；
* rollback。

---

# 20. Evidence 状态机

Evidence：

pending

→ ai_extracted

→ human_verified

或：

pending / ai_extracted

→ rejected

已经正式入库：

human_verified

→ invalidated。

禁止物理删除正式证据。

---

# 21. Evidence 两级分类

第一层：

* brain_region；
* connection；
* circuit；
* other。

第二层：

* paper_evidence；
* llm_explanation；
* literature；
* rule_validation；
* human_note；
* database；
* other。

论文佐证统一属于：

paper_evidence。

---

# 22. 页面设计

论文佐证采用数据中心底部工作台。

布局：

左：

对象队列。

中：

当前对象 + 论文检索 + 全文证据。

右：

人工审核 + confidence。

顶部：

当前对象；

对象类型；

当前 confidence；

已有论文证据；

队列进度。

---

# 23. 左栏对象队列

状态：

pending；

processing；

awaiting_review；

completed；

skipped；

failed。

显示：

名称；

类型；

confidence；

已有 paper evidence 数；

状态。

支持：

点击切换；

失败重试；

只看未完成；

恢复任务。

---

# 24. 中栏 Stepper

明确显示：

1. 对象
2. 查论文
3. 找原文
4. 审核
5. 入库

每一步都显示目的。

---

# 25. 候选论文卡片

每篇至少展示：

标题；

期刊；

年份；

PMID；

DOI；

OA；

abstract；

匹配原因；

是否已使用。

操作：

查看摘要；

Europe PMC；

DOI；

选择；

排除。

---

# 26. Passage 卡片

显示：

section；

paragraph locator；

英文；

中文；

direction；

evidence_level；

reason；

semantic confidence；

source verified。

source_verified：

绿色：

“已核验原文”

红色：

“未能在论文原文定位，禁止入库”。

---

# 27. 右侧人工审核

必须显示：

当前 confidence；

DeepSeek suggestion；

Reviewer confidence；

最终 confidence；

置信度上限；

计算规则。

用户确认：

direction；

evidence_level；

reviewer confidence；

人工备注。

---

# 28. 入库预览

正式提交前显示 Dialog：

论文；

PMID；

DOI；

选中的 passages；

方向；

证据等级；

confidence：

0.31 → 0.78；

写入对象；

是否重复；

状态变化。

---

# 29. 入库结果

成功：

当前对象标记 completed；

刷新原列表 confidence；

刷新 evidence count；

自动进入下一对象。

失败：

保持当前草稿。

不得清空人工编辑内容。

---

# 30. 对象详情中的证据展示

按：

对象类别

→ 证据类型

展示。

论文证据点击后打开 Evidence Detail Drawer。

展示：

论文；

英文 passage；

翻译；

方向；

等级；

reviewer；

confidence 调整；

验证状态；

审计；

撤销。

---

# 31. Evidence 与原对象互跳

Evidence：

“查看原数据”

→ 自动跳到对应数据中心 Tab

→ 定位对象

→ 打开对象 Drawer。

对象 Drawer：

点击 evidence

→ Evidence Drawer。

---

# 32. 批量任务

批量任务的目的不是自动入库。

只允许自动执行：

检索；

获取文章；

全文切片；

语义召回；

DeepSeek 精判；

原文校验；

生成待审核草稿。

最终必须：

人工审核。

批量 item 最终停在：

`awaiting_review`

状态。

---

# 33. 后台任务中心

论文任务必须接入现有后台任务中心。

支持：

暂停；

继续；

取消；

失败重试；

查看任务；

打开对应论文佐证工作台。

---

# 34. 验证中心衔接

正式论文证据入库后，验证中心可以读取。

特别关注：

* contradict；
* confidence pending；
* invalidated evidence；
* 多论文冲突。

建议事件：

EV_PAPER_EVIDENCE_ATTACHED

EV_PAPER_EVIDENCE_CONTRADICTORY

EV_PAPER_EVIDENCE_INVALIDATED

EV_CONFIDENCE_ADJUSTMENT_PENDING。

---

# 35. DeepSeek 要求

必须继续复用项目已有 DeepSeek provider。

禁止新增另一套客户端。

保存：

* model；
* prompt_version；
* raw_response；
* parse_status；
* retry_count；
* source_text_hash。

优先：

JSON Schema / structured output。

否则：

JSON mode + Pydantic。

禁止直接信任自由文本 JSON。

---

# 36. 性能要求

禁止：

一次加载 11.4 万对象；

整篇 OA全文长期塞在 React state；

每一个列表行单独请求 evidence count；

每次切对象都重新下载同一篇全文。

要求：

分页；

paper cache；

passage cache；

全文按需；

请求取消；

搜索 debounce；

批处理可恢复。

---

# 37. 安全与审计

必须记录：

人工选择论文；

修改 query；

选择 passage；

修改 direction；

修改 level；

修改 confidence；

入库；

撤销；

confidence rollback。

正式 evidence 不物理删除。

---

# 38. 成功指标

系统最终达到：

1. 所有正式论文证据均有真实论文来源；
2. PMID / DOI 可追溯；
3. 100% 入库 passage 通过原文校验；
4. LLM 编造 passage 无法入库；
5. 支持多 passage；
6. 支持全文；
7. 人工拥有最终决定权；
8. confidence 调整可解释；
9. 上限 ≤0.85；
10. contradict 不自动升分；
11. 所有 confidence 调整可回滚；
12. 批量任务不得绕过人工；
13. Evidence 和原对象可互跳；
14. 后续验证中心可以完整复核。

---

# 39. 核心验收场景

选择一个低置信 connection。

↓

Europe PMC 找到 OA 论文。

↓

获取全文。

↓

全文切片。

↓

召回相关 Results / Discussion。

↓

DeepSeek 找到 3 个 passages。

↓

其中：

2 个原文验证成功；

1 个模型生成内容验证失败。

↓

失败 passage 不允许选择。

↓

人工选择 2 个。

↓

方向 support。

↓

reviewer confidence = 0.78。

↓

系统展示：

0.31 → 0.78。

↓

确认。

↓

生成 human_verified paper evidence。

↓

confidence = 0.78。

↓

Evidence Drawer 可查看真实原文。

↓

点击撤销。

↓

Evidence → invalidated。

↓

confidence 正确回滚。

↓

审计日志完整。

该流程全部成功，才认为论文佐证核心链路完成。
