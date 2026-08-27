# Gate 2B Validation Report — NeuroGraphIQ Macro96 Ontology

校验工具: rdflib 7.6.0（只读解析校验，无写入）
校验文件: `ontology/neurographiq_macro96_v1.ttl`
校验时间: 2026-08-27

## 校验结果（21 / 21 PASS）

| # | Check | Result | Detail |
|---|---|---|---|
| 1 | TTL Parse | **PASS** | Turtle 语法正常解析 |
| 2 | owl:Ontology = 1 | **PASS** | count = 1 |
| 3 | Gate 1 24 Class 全部仍存在 | **PASS** | missing = 0 |
| 4 | 新增 ConnectionType Class = 4 | **PASS** | StructuralConnection / Projection / FunctionalConnectivity / EffectiveConnectivity |
| 5 | 总业务 Class = 28 | **PASS** | count = 28 |
| 6 | StructuralConnection parent = ConnectionType | **PASS** | parents = [ConnectionType] |
| 7 | Projection parent = StructuralConnection | **PASS** | parents = [StructuralConnection] |
| 8 | FunctionalConnectivity parent = ConnectionType | **PASS** | parents = [ConnectionType] |
| 9 | EffectiveConnectivity parent = ConnectionType | **PASS** | parents = [ConnectionType] |
| 10 | FiberTractConnection 不存在 | **PASS** | — |
| 11 | Coactivation 不存在 | **PASS** | — |
| 12 | AssociationConnection 不存在 | **PASS** | — |
| 13 | LocalAnatomicalConnection 不存在 | **PASS** | — |
| 14 | UnknownConnection 不存在 | **PASS** | — |
| 15 | UncertainConnection 不存在 | **PASS** | — |
| 16 | ObjectProperty = 0 | **PASS** | count = 0 |
| 17 | DataProperty = 0 | **PASS** | count = 0 |
| 18 | Individual = 0 | **PASS** | count = 0 |
| 19 | owl:imports = 0 | **PASS** | count = 0 |
| 20 | 中文/英文 label 完整（28 Class） | **PASS** | 每个 Class 均含 @en 与 @zh label |
| 21 | owl:versionInfo = 0.2.0-gate2b | **PASS** | version = 0.2.0-gate2b |

## 校验说明

- **altLabel 处理**：`StructuralConnection` 的英文替代术语 `anatomical connection` 以 `rdfs:comment`（@en）文本记录，未引入 SKOS 或自定义 AnnotationProperty（遵循 Gate 2B §四/§六约束）。后续若需规范 altLabel，留待 Property / Annotation Gate 决定。
- **方向 / directness / source / target / evidence 语义**：仅存在于 `rdfs:comment` 文本中，未建立任何 ObjectProperty / DataProperty。
- **未使用** pySHACL / ROBOT 等额外依赖；校验仅依赖现有 rdflib。

## 结论

Gate 2B 正式 TTL 修改通过全部 21 项自动校验，可交由 Protégé Desktop 人工打开验收。
