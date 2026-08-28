# Gate 6E-A — Change Summary（Evidence / Assertion 语义模型审查）

Ontology IRI: `https://neurographiq.org/ontology/human-brain`（version 0.6.2-gate6d，本轮不改）
本轮状态: **仅科学语义设计，不写 TTL**

---

## 1. 本 Gate 产出

- Evidence / Assertion 科学语义设计与建模审查（19 文件）。
- 推荐 **Hybrid Model**。

## 2. 核心推荐

| 项 | 推荐 |
|---|---|
| KnowledgeAssertion | 不进 OWL core（保留 DB） |
| supports/contradicts/qualifies | DB evidence_role（非 OWL ObjectProperty） |
| 普通 assertion | knowledge_assertions + assertion_evidence_links |
| Connection | reified proposition，直接挂 Evidence |
| Circuit | reified entity，直接挂 Evidence + membership/observation 层 |
| inferred knowledge | derivation provenance（非 Evidence） |
| external database evidence | provenance = Source（未来 DEFER） |

## 3. 方案比较结论

- RDF reification：不采用（Protégé UX / reasoning 弱）。
- RDF-star：future projection/serialization，非 canonical。
- Wikidata pattern：借鉴（已由 DB knowledge_assertions 实现）。
- PROV-O / ECO：reference only。

## 4. Gate 7A 审计

- 非 blocking；发现 Circuit/RegionMapping → Evidence 无直接路径（真实缺口），建议 Gate 6E-B 前最小修订（统一 evidence link target）。

## 5. 未做

- 未修改 TTL（仍 0.6.2-gate6d / 23 Class / 26 ObjectProperty / 0 DataProperty）。
- 未修改 Gate 7A / 数据库 / migration / API / frontend / Neo4j。
- 未新增任何 Class / ObjectProperty / DataProperty / Individual。

## 6. Gate 6E-A.1 Amendment（后续）

- 见 `20_database_alignment_amendment.md`：`assertion_evidence_links → evidence_links`（XOR target + entity_pk + claim_scope + scientific_source_pk），表总数保持 32。
