# Gate 6E-B — Change Summary（Evidence / Assertion Boundary Freeze）

Ontology IRI: `https://neurographiq.org/ontology/human-brain`（version 0.6.2-gate6d，本轮不改）
本轮状态: **Boundary Freeze，无 ontology entity 变化**

---

## 1. 本轮产出

- 14 文件 Boundary Freeze review。
- OWL 零扩展（Class/ObjectProperty/DataProperty/Individual 均 0 新增）。

## 2. 冻结边界

| 层 | 内容 |
|---|---|
| OWL Core | ResearchStudy / Publication / Evidence + reportedIn / providesEvidence |
| PostgreSQL | knowledge_assertions / relation_definitions / evidence_links / connection_observations + supports/contradicts/qualifies + claim_scope + strength/directness + InferenceRecord + Governance |

## 3. 未做

- 未修改 TTL（仍 0.6.2-gate6d / 23 Class / 26 ObjectProperty / 0 DataProperty）。
- 未新增 Class / ObjectProperty / DataProperty / Individual。
- 未创建 migration / 未改数据库。

## 4. 前置 Gate 一致性

- Gate 6E-A：Hybrid Evidence Model（通过）。
- Gate 6E-A.1：assertion_evidence_links → evidence_links（XOR target + entity_pk + claim_scope + scientific_source_pk）。
- Gate 6E-A.2：entity whitelist + claim_scope 必填 + ACTIVE source completeness。
