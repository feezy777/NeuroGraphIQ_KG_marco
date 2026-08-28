# Gate 6G-A — Class Matrix（23）

| Class | 中文 | Parent | 科学含义 | TBox/ABox | Status |
|---|---|---|---|---|---|
| BrainRegion | 脑区 | owl:Thing | 人脑区域实体 | Class（Hippocampus/CA1=Individual） | OK |
| CellularNeuralStructure | 细胞与亚细胞神经结构 | owl:Thing | 细胞/亚细胞结构 | Class | OK |
| NeurobiologicalProcess | 神经生物学过程 | owl:Thing | 神经生物学过程 | Class | OK |
| Connection | 连接 | owl:Thing | 连接实体（reified） | Class（CON-xxx=Individual） | OK |
| StructuralConnection | 结构连接 | Connection | 解剖通路 | Class | OK |
| Projection | 投射 | StructuralConnection | 有向轴突投射 | Class | OK |
| FunctionalConnectivity | 功能连接 | Connection | 统计依赖/相关 | Class | OK |
| EffectiveConnectivity | 有效连接 | Connection | 有向影响 | Class | OK |
| Circuit | 神经回路 | owl:Thing | 有组织连接单元 | Class（PapezCircuit=Individual） | OK |
| Function | 功能 | owl:Thing | 神经生物学功能 | Class（Memory=Individual） | OK |
| CognitiveFunction | 认知功能 | Function | 认知域功能 | Class | OK |
| Neurotransmitter | 神经递质 | owl:Thing | 化学信号分子 | Class（Dopamine=Individual） | OK |
| Receptor | 受体 | owl:Thing | 受体蛋白 | Class | OK |
| Gene | 基因 | owl:Thing | 人类基因 | Class（APOE=Individual） | OK |
| Disease | 疾病 | owl:Thing | 神经/精神疾病 | Class（AlzheimerDisease=Individual） | OK |
| Symptom | 症状 | owl:Thing | 临床表现 | Class | OK |
| ResearchStudy | 研究 | owl:Thing | 研究活动 | Class | OK |
| Publication | 文献 | owl:Thing | 文献载体 | Class | OK |
| Evidence | 证据 | owl:Thing | 证据单元 | Class | OK |
| Atlas | 脑图谱 | owl:Thing | 图谱资源 | Class | OK |
| ExternalRegion | 外部脑区 | owl:Thing | 外部区域概念 | Class | OK |
| RegionMapping | 脑区映射 | owl:Thing | 映射实体（reified） | Class | OK |
| CircuitConnectionMembership | 回路连接成员关系 | owl:Thing | 成员关系（reified） | Class | OK |

## 结论

- 23 Class 全部符合冻结清单。
- 无旧名残留（ConnectionType/CircuitType/EvidenceType/NeuralStructure/NeuralProcess/Study/ConnectionAssessment/ConceptDefinition）。
- 无 TBox/ABox 混用（未把 Hippocampus/APOE/Memory 等声明为 Class）。
