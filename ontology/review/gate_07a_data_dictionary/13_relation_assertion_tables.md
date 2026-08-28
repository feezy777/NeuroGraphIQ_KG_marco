# Gate 7A — Relation / Assertion Tables

本轮状态: **仅设计文档**

---

## 1. relation_definitions（管理 Gate 6B ObjectProperty vocabulary）

| 字段 | 说明 |
|---|---|
| predicate_pk | 内部主键 |
| predicate_id | NGIQ-PRED-… |
| predicate_key | participatesIn / modulates / … |
| name_en / name_zh | 名称 |
| description_en / description_zh | 描述 |
| domain_class | domain |
| range_description | range 描述 |
| is_directional | 是否有向 |
| representation_role | canonical / derived |
| owl_iri | OWL IRI |
| is_active | 是否启用 |
| display_order | 展示顺序 |
| remark | 备注 |

例：`NGIQ-PRED-00000001`，predicate_key=participatesIn，name_en=participates in，name_zh=参与，representation_role=canonical。

## 2. knowledge_assertions（数据库 assertion layer，非 OWL Class）

| 字段 | 说明 |
|---|---|
| assertion_pk | 内部主键 |
| assertion_id | NGIQ-AST-… |
| subject_entity_id | 主语实体 |
| predicate_id | 谓词 |
| object_entity_id | 宾语实体 |
| display_name_en / display_name_zh | 展示名 |
| derivation_type | reported / inferred |
| assertion_status | 状态 |
| confidence | 置信度 |
| qualifiers_json | 限定词 |
| condition_en / condition_zh | 条件 |
| source_scope | 来源范围 |
| valid_from / valid_to | 有效期 |
| review_status / reviewer / reviewed_at | 审核 |
| created_at / updated_at | 时间戳 |
| remark | 备注 |

例：`NGIQ-AST-00000001`，Hippocampus participatesIn Memory，display_name_en=Hippocampus participates in memory，display_name_zh=海马参与记忆功能。

## 3. evidence_links（Evidence Association Layer；原 assertion_evidence_links，HISTORICAL/SUPERSEDED）

统一表达 Evidence 对 KnowledgeAssertion 或 reified scientific entity 的 epistemic 作用。

| 字段 | 说明 |
|---|---|
| link_pk | 内部主键 |
| link_id | NGIQ-ELK-…（8 位） |
| evidence_pk | 指向 evidence（必填） |
| assertion_pk | 指向 knowledge_assertions（XOR，nullable） |
| entity_pk | 指向 kg_entities（XOR，nullable） |
| evidence_role | supports / contradicts / qualifies |
| evidence_strength | target-specific 强度 |
| evidence_directness | target-specific 直接性 |
| claim_scope | entity_overall / direction / connection_type / membership / function / mapping_* / other（entity target 用） |
| is_primary_evidence | 是否主证据 |
| record_status | active / deprecated / merged / pending |
| created_at / updated_at | 时间戳 |
| remark | 备注 |

> **XOR 约束**：assertion_pk 与 entity_pk 必须且只能填一个（普通 assertion 走 assertion_pk；Connection/Circuit/RegionMapping 走 entity_pk）。未来 Gate 7B 用 CHECK constraint 表达。

> **Entity whitelist（V1）**：entity_pk 仅允许 entity_type ∈ {connection, circuit, region_mapping, circuit_connection_membership}。BrainRegion/Gene/Disease/Function 等普通 domain entity 不得直接作为 entity-level Evidence target。
>
> **claim_scope 规则**：entity_pk NOT NULL → claim_scope 必填；assertion_pk NOT NULL → claim_scope 可 NULL。
