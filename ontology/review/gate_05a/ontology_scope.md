# Gate 5A — Ontology Scope（本体范围）· 第二轮修订

Ontology IRI: `https://neurographiq.org/ontology/macro96`
本轮状态: **仅 review 文档，未修改正式 TTL**

---

## 1. Species Scope：HUMAN BRAIN ONLY

- **species scope = Homo sapiens（仅人脑）**。
- V1 **不建立**：mouse / rat / macaque / drosophila / cross-species homology ontology。
- 跨物种同源、跨物种映射属于**未来扩展**，不是当前 V1 主线。
- **Macro96 不再是知识发现的唯一粒度**，降为**高层映射 / 汇总层（high-level mapping / aggregation layer）之一**。
- 数据生产入口：**Fine Human BrainRegion → Circuit Discovery → Circuit normalization → Circuit-driven BrainRegion + Connection discovery → normalization → ontology mapping**。

## 2. 五个逻辑模块（非 OWL hierarchy）

本轮把推荐类拆为**五个逻辑模块**，替代第一轮过粗的 Domain/Governance 二分。**只做逻辑分组，不建模块父类。**

### A. Neuroscience Domain（神经科学领域本体）
回答："人脑神经科学世界中有什么？"
BrainRegion、CellularNeuralStructure、NeurobiologicalProcess、Connection、ConnectionType、Circuit、CircuitType、Function、CognitiveFunction、Neurotransmitter、Receptor、Gene、Disease、Symptom

### B. Scientific Evidence / Provenance（科学证据与溯源）
回答："科学知识来自什么研究、文献和证据？"
ResearchStudy、Publication、Evidence、EvidenceType

### C. Atlas / Integration（图谱与整合）
回答："外部 atlas / terminology 如何映射到 NeuroGraphIQ？"
Atlas、ExternalRegion、RegionMapping

### D. Modeling / Reification（建模 / 物化）
回答："为了表达结构关系所需的建模辅助实体。"
CircuitConnectionMembership

### E. Knowledge Production / Governance（知识生产与治理）
回答："知识如何被搜索、抽取、审核、推理、验证？"
ConnectionCandidate、CircuitCandidate、EvidenceCandidate、SearchRun、ExtractionRun、ModelReview、HumanReview、InferenceRecord、ValidationRecord

---

## 3. 禁止现在建立模块父类

本轮**不得**在正式设计中新增：

`NeuroscienceDomainEntity` / `ScientificEvidenceEntity` / `IntegrationEntity` / `GovernanceEntity` / `ModelingEntity` / `DomainEntity`

等 OWL Class。是否建立顶层组织类，**留待后续 semantic modeling gate**。

---

## 4. V1 / Future Boundary

| 内容 | V1 | Future |
|---|---|---|
| 物种 | Homo sapiens | 跨物种扩展 |
| 粒度主线 | Fine BrainRegion → Circuit → Connection | — |
| BrainRegion individual | 不建（只定概念） | 数据导入 Gate |
| CellularNeuralStructure 子类 | 不建（Neuron/Axon/Dendrite/DendriticSpine/Synapse） | 未来扩展 |
| NeurobiologicalProcess 子类 | 不建（SynapticPruning/Neurogenesis/SynapticPlasticity） | 未来扩展 |
| Neurotransmitter / Receptor / Gene | 仅 Class | Individual / controlled concept |
| Disease / Symptom | 仅 Class | has_symptom 等 Property |
| EvidenceType | 仅占位，表示未定 | Evidence Formalization Gate |
| ObjectProperty / DataProperty | 禁止 | Property Gate（Gate 5A.1 之后） |
| owl:imports | 禁止（保持空） | 映射对齐 Gate |
| 模块父类 | 不建 | semantic modeling Gate |

---

## 5. 本轮不可跨越的边界

- 不修改 `ontology/neurographiq_macro96_v1.ttl`。
- 不新增/删除/修改任何 OWL Class、Property、Individual、axiom、SHACL、owl:imports。
- 不导入任何 Macro96 / Julich-Brain / Brainnetome / HCP / PubMed 数据。
- 不动 PostgreSQL / API / frontend / Neo4j / Circuit Discovery / LLM extraction。
- 不 commit，不 push。
