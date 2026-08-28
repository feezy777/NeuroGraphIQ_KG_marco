# Gate 5A — Modeling Issues（建模问题，第二轮升级版）

Ontology IRI: `https://neurographiq.org/ontology/macro96`
本轮状态: **仅记录，未写入正式 TTL**

每个 issue 至少含：Problem / Why it matters / Candidate solutions / Current recommendation / Decision status / Blocking or non-blocking / Which future Gate resolves it。

---

## ISSUE 1 — ConnectionType：OWL Class vs controlled-vocabulary Individual（**BLOCKER**）

- **Problem:** 当前 TTL 中 Connection、ConnectionType 均为 Class；StructuralConnection/Projection/FunctionalConnectivity/EffectiveConnectivity 是 ConnectionType 下的 OWL Class。未来具体连接（如 NGIQ_CONN_001 若为 Connection Individual）需表达 `NGIQ_CONN_001 hasConnectionType Projection`，但 Projection 目前是 Class 而非 controlled vocabulary Individual。
- **Why it matters:** 决定连接如何被分类、查询、约束；影响 Gate 2B hierarchy 的去留。
- **Candidate solutions:**
  - **方案 A — Connection subtype model**：重构为 `Connection ├─ StructuralConnection └─ Projection / FunctionalConnectivity / EffectiveConnectivity`，具体连接 `rdf:type Projection`。优点：符合传统 OWL class typing。缺点：推翻当前 Gate 2B hierarchy，需正式 migration/review。
  - **方案 B — controlled vocabulary model**：Connection 保持 biological relation entity Class；ConnectionType 作为受控类型概念，StructuralConnectionType/ProjectionType/FunctionalConnectivityType/EffectiveConnectivityType 作为 ConnectionType Individuals，`NGIQ_CONN_001 hasConnectionType ProjectionType`。优点：适合数据库枚举/has_type。缺点：需重构 Gate 2B 当前 class hierarchy。
- **Current recommendation:** 本轮**不选择、不实施**任何方案；完整记录双方案，交由 Gate 5A.1 决定。
- **Decision status:** OPEN / BLOCKER。
- **Blocking or non-blocking:** **BLOCKING**（Property Gate / Gate 5B finalization 之前必须解决）。
- **Resolved by:** Gate 5A.1 — Core Semantic Modeling Decision（ConnectionType / CircuitType / EvidenceType 的 Class-hierarchy vs controlled-vocabulary 统一决策）。

## ISSUE 2 — CircuitType：是否需要保留、如何建模

- **Problem:** 当前 reserved extension point（无子类、无 individual），长期价值未定。
- **Why it matters:** 回路是否需要受控分类；若不需要则徒增概念。
- **Candidate solutions:** A 删除；B 保留为 reserved class；C 改 controlled vocabulary；D 未来建科学稳定的 Circuit subtype hierarchy。
- **Current recommendation:** 不决定；保持 reserved。
- **Decision status:** OPEN。
- **Blocking or non-blocking:** non-blocking（但需在 Gate 5A.1 给方向）。
- **Resolved by:** Gate 5A.1。

## ISSUE 3 — EvidenceType：多轴模型与单 Class 的冲突

- **Problem:** Gate 4A 明确 Evidence 有多正交维度（source / acquisition modality / analysis method / intervention method / directness / strength / confidence）；单一 EvidenceType Class taxonomy 与多轴冲突。
- **Why it matters:** 决定 Evidence 分类是"一个互斥类型"还是"多轴属性组合"。
- **Candidate solutions:** A remove EvidenceType；B reserved umbrella concept；C controlled vocabulary；D multi-axis properties（Gate 4A 推荐）。
- **Current recommendation:** DEFER / REMODEL；Gate 4A 多轴模型优先；不重建模态子类 hierarchy。
- **Decision status:** OPEN。
- **Blocking or non-blocking:** non-blocking（但需 Evidence Formalization Gate）。
- **Resolved by:** Gate 5A.1 / Evidence Formalization Gate。

## ISSUE 4 — 全局 TBox / ABox canonical concept policy

- **Problem:** 需明确哪些是 Class（类型）、哪些是 Individual（canonical knowledge concept）。
- **Why it matters:** 决定 BrainRegion/Gene/Disease/Neurotransmitter/Receptor 等的实例化策略，影响整个 KG。
- **Candidate solutions:** 见 `domain_class_proposal.md` 附节——默认 **Class = 概念类型，Individual = 真实 canonical concept**。
- **Current recommendation:** BrainRegion=Class / Hippocampus=Individual；Gene=Class / APOE=Individual；Disease=Class / AlzheimerDisease=Individual；Neurotransmitter=Class / Dopamine=Individual；Receptor=Class / D2Receptor=Individual；Function=Class / WorkingMemory=Individual；Atlas=Class / JulichBrainAtlas=Individual。
- **Decision status:** PROPOSED（默认策略，待确认）。
- **Blocking or non-blocking:** non-blocking（但影响后续 Individual Gate）。
- **Resolved by:** Individual / controlled-vocabulary Gate（在 Gate 5A.1 之后）。

## ISSUE 5 — 外部 ontology Class 与 NGIQ Individual 的 mapping

- **Problem:** MONDO/HPO/ChEBI/Uberon 可能把 biomedical concept 建模为 OWL Class；NGIQ 若用 Individual，不得简单 owl:equivalentClass 对齐。
- **Why it matters:** 跨本体映射的正确性，避免语义层级错位。
- **Candidate solutions:** 用未来 mapping（external_id / source ontology / exactMatch / closeMatch / mapped_to）表达对应，而非 owl:equivalentClass 跨 Individual/Class。
- **Current recommendation:** NGIQ 不复制外部 Class semantics；禁止未经审查用 owl:equivalentClass 跨 NGIQ Individual 与外部 OWL Class。
- **Decision status:** PROPOSED。
- **Blocking or non-blocking:** non-blocking。
- **Resolved by:** Mapping / Alignment Gate。

## ISSUE 6 — Connection entity model vs direct graph edge model

- **Problem:** PPT 用直接 edge（STRUCTURALLY_CONNECTED_TO / FUNCTIONALLY_CONNECTED_TO / PROJECTS_TO）；NGIQ 用 Connection entity（BrainRegion → source of → Connection → target → BrainRegion）。
- **Why it matters:** 可能是 storage model（entity）与 projection model（direct edge）的分工，需澄清是否重复建模。
- **Candidate solutions:** 存储用 Connection entity；Neo4j projection 生成 `A -[:PROJECTS_TO]-> B` 快捷边；是否两者都保留留待决定。
- **Current recommendation:** 记录为 storage vs projection；本轮不正式决定。
- **Decision status:** OPEN。
- **Blocking or non-blocking:** non-blocking（但需在 Property Gate 前澄清）。
- **Resolved by:** Gate 5A.1 / Property Gate。

## ISSUE 7 — CircuitConnectionMembership reification

- **Problem:** 一个 Connection 可属于多个 Circuit，且不同 Circuit 中 step_order / role / entry-exit / membership evidence / confidence / local topology 不同。
- **Why it matters:** 这些属于 Circuit×Connection membership，非 Connection 本身；决定是否需要 reification entity。
- **Candidate solutions:** 保留 reification Class（current）+ 未来属性（circuit_has_connection / connection_member_of_circuit）。
- **Current recommendation:** KEEP 概念，formalization DEFER。
- **Decision status:** PROPOSED（概念保留）。
- **Blocking or non-blocking:** non-blocking。
- **Resolved by:** property / semantic modeling Gate。

## ISSUE 8 — ResearchStudy / Publication / Evidence 未来关系建模

- **Problem:** 三者已三分；未来关系（reported_in / provides / supports）如何建。
- **Why it matters:** provenance 链的正确性。
- **Candidate solutions:** 对象属性 + 可选 PROV-O 风格 provenance。
- **Current recommendation:** 本轮只定义，不建属性。
- **Decision status:** OPEN。
- **Blocking or non-blocking:** non-blocking。
- **Resolved by:** Property Gate。

## ISSUE 9 — Domain / Evidence / Integration / Governance 是否未来正式模块化

- **Problem:** 本轮五模块仅为逻辑分组；是否建 `NeuroscienceDomainEntity` 等父类。
- **Why it matters:** query/约束便利 vs 本体耦合与治理负担。
- **Current recommendation:** 不建父类，保持轻量。
- **Decision status:** OPEN。
- **Blocking or non-blocking:** non-blocking。
- **Resolved by:** 后续 semantic modeling Gate。

## ISSUE 10 — ConceptDefinition 是否有必要

- **Problem:** 概念定义可用 annotation 表达；是否需运行时 Class。
- **Why it matters:** 避免冗余概念污染 TBox。
- **Current recommendation:** REMOVE（见 governance review §2.10）。
- **Decision status:** PROPOSED（REMOVE）。
- **Blocking or non-blocking:** non-blocking。
- **Resolved by:** 本轮给出结论，留待正式写入 TTL 的 Gate 落实。

---

## 附 ISSUE 11 — Ontology IRI / namespace 仍含 macro96

- **Problem:** 项目范围已从 Macro96 转为 human-brain-wide，但正式 IRI 仍为 `https://neurographiq.org/ontology/macro96`。
- **Why it matters:** IRI 语义与实际范围不符；影响长期版本治理与外部引用稳定性。
- **Candidate solutions:**
  - A 保持原 IRI，兼容历史；
  - B 在下一 major ontology version 更换 human-brain IRI（如 `.../ontology/human-brain`）；
  - C 新建 ontology module 拆分。
- **Current recommendation:** 倾向 B（major version 时更换），但**本轮不执行、不修改 IRI**。
- **Decision status:** OPEN。
- **Blocking or non-blocking:** non-blocking（但需在 versioning 决策时解决）。
- **Resolved by:** Ontology versioning / freeze Gate。

## 附 ISSUE 12 — Gate 3B comment 含 legacy Macro96 curation 文本

- **Problem:** 正式 TTL 的 Circuit rdfs:comment 仍含 "Macro96 V1 curation policy（≥3 Macro96 BrainRegion + ≥2 Connection）" 等 legacy 文本，与 new human-fine-region 路线不符。
- **Why it matters:** 注释与实际路线不一致，误导人工审阅。
- **Current recommendation:** 本轮**不修改 TTL**；记录于 modeling_issues，交由 **Gate 5B 正式更新**。
- **Decision status:** OPEN（待 Gate 5B 文本更新）。
- **Blocking or non-blocking:** non-blocking（科学语义未变，仅注释文本过时）。
- **Resolved by:** Gate 5B（正式 TTL 更新）。

---

## 小结

- **BLOCKER（1）**：ConnectionType OWL 表示（ISSUE 1）。
- **需 Gate 5A.1 统一决策**：ConnectionType / CircuitType / EvidenceType 的 Class-hierarchy vs controlled-vocabulary（ISSUE 1/2/3）。
- **Gate 5A.1 通过之前**：禁止建立 ObjectProperty。
- 其余 ISSUE 不阻塞本轮范围重构，但需在对应后续 Gate 解决。
