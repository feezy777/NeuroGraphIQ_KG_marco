# Gate 6E-A — Assertion Model Options（方案比较）

本轮状态: **仅设计比较，不写 TTL**

---

## 1. 五个方案

| 方案 | 说明 |
|---|---|
| A | Assertion 仅存在于 PostgreSQL 层，不进入核心 OWL ontology |
| B | 新增 OWL Class KnowledgeAssertion + supportsAssertion/contradictsAssertion/qualifiesAssertion |
| C | 标准 RDF reification（rdf:Statement / rdf:subject / rdf:predicate / rdf:object） |
| D | RDF-star（`<<s p o>>` 直接挂 Evidence/confidence） |
| E | 其他 OWL-compatible assertion model |

## 2. 比较表（15 维）

| 维度 | A（DB-only） | B（OWL Class） | C（RDF reification） | D（RDF-star） |
|---|---|---|---|---|
| OWL 2 DL 兼容 | ✅ 完全（不进 OWL） | ⚠️ 需 predicate reification，meta-modeling 风险 | ⚠️ rdf:Statement 非 OWL Class，reasoning 弱 | ⚠️ 非 OWL DL 标准 |
| Protégé 可读性 | ✅（不涉及） | ⚠️ 需额外节点 | ❌ 冗长 | ❌ 工具支持不稳 |
| Neo4j 投影 | ✅ 直接 | ⚠️ 需 assertion 节点 | ⚠️ 四元组 | ⚠️ 需扩展 |
| PostgreSQL 对齐 | ✅ 完全（已冻结） | ⚠️ 需映射 | ⚠️ 需映射 | ❌ 无 DB 对应 |
| Evidence linking | ✅ assertion_evidence_links | ⚠️ 需 OWL relation | ⚠️ 需 reification 层 | ⚠️ |
| 普通 assertion 支持 | ✅ | ✅ | ✅ | ✅ |
| reified Connection/Circuit | ✅（直接 entity 关联） | ⚠️ 需 wrapper | ⚠️ | ⚠️ |
| provenance | ✅ DB | ⚠️ | ⚠️ | ⚠️ |
| qualifiers | ✅ qualifiers_json | ⚠️ 需 property | ⚠️ | ⚠️ |
| supports/contradicts/qualifies | ✅ DB evidence_role | ✅ OWL relation | ⚠️ | ⚠️ |
| inference trace | ✅ | ⚠️ | ❌ | ❌ |
| future reasoning | ⚠️（DB 推理） | ✅（OWL 推理） | ❌ | ❌ |
| 实现复杂度 | 低 | 高（meta-modeling） | 中 | 中 |
| duplication risk | 低 | 中 | 高 | 中 |
| interoperability | 中 | 高 | 高 | 中 |

## 3. 初步结论

- 方案 A（DB-only）与已冻结 Gate 7A 完全对齐，实现最简，无 OWL meta-modeling 风险。
- 方案 B 的 meta-modeling 风险（predicate reification）是核心障碍。
- 方案 C/D 不适合作为 V1 core ontology canonical model（工具/reasoning 不稳定）。

## 4. 推荐方向

**Hybrid Model（以 A 为主 + reified entity 直接关联）**：
- 普通 ObjectProperty assertion → KnowledgeAssertion（DB，非 OWL）。
- reified entity（Connection/Circuit/RegionMapping）→ 直接作为 first-class knowledge object，Evidence 直接关联。
- supports/contradicts/qualifies → DB evidence_role（非 OWL ObjectProperty）。

详见 `15_recommended_v1_model.md`。
