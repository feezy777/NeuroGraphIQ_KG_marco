# Gate 6A — Excluded / Deferred Relations（排除与暂缓关系）· 第二轮修订

Ontology IRI: `https://neurographiq.org/ontology/human-brain`
本轮状态: **仅记录，未修改正式 TTL**

---

## 1. DEFER FORMALIZATION（语义保留，暂缓正式化）

| 关系 | 原因 |
|---|---|
| supports | Range 仅 Connection/Circuit 无法覆盖普通 ObjectProperty assertion；需 assertion-level evidence model |
| contradicts | 同上 |

> 语义保留：证据可支持/反驳断言。但暂缓正式写入 ObjectProperty，留 Future Evidence / Assertion Formalization Gate。

## 2. DEFER（留后续，不建）

| 关系/项 | 原因 |
|---|---|
| owl:inverseOf（participatesIn ↔ includesRegion 等） | 正式 inverse axiom 留 Property Gate |
| owl:SymmetricProperty / owl:TransitiveProperty | 留 Property Gate |
| Assertion / RelationAssertion / Statement / EdgeAssertion | 本轮禁止新增；留 Evidence/Assertion Formalization Gate |
| GeneticVariant / Allele | 本轮禁止新增；APOE ε4 等 variant 级风险关系留未来 |
| supportsFunction / supportsMapping / supportsDisease | 若 supports 未来重新 formalize 时再议 |

## 3. 明确排除（不扩展完整 biomedical relations）

| 排除 | 原因 |
|---|---|
| protein interactions | 超出 V1 短期主线 |
| drug relations | 超出主线 |
| molecular pathway | 超出主线 |
| cell ontology relations | 超出主线 |
| detailed disease causality（causes/treats） | 超出主线，仅保留 increasesRiskOf / hasSymptom |
| clinical treatment relations | 超出主线 |

## 4. 禁止的错误关系

| 禁止 | 原因 |
|---|---|
| BrainRegion hasFunction Function（作为第二套 canonical） | 与 participatesIn 重复；hasFunction 收窄为 Circuit → Function |
| FunctionalConnectivity 使用 source/target 伪排序 | 用 hasEndpointRegion；方向语义不能伪造 |
| hasConnection 作为唯一 canonical（跳过 membership） | 丢失 step_order/role/membership evidence |
| mapsTo 作为唯一 canonical（跳过 RegionMapping） | 丢失 mapping_type/confidence/evidence |
| direct edge 作为第二份 canonical truth | 违反 Connection entity 单一真值原则 |
| APOE ε4 作为 Gene 个体示例 | ε4 是 variant，非 Gene；V1 无 GeneticVariant |

## 5. 原则

- 短期主线：BrainRegion / Connection / Circuit / Function。
- Gene / Disease / Neurotransmitter 只保持基础关系。
- 不为"完整性"无限加关系。
