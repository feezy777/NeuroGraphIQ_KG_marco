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

## 3. assertion_evidence_links（解决普通 KG edge 如何挂 Evidence）

| 字段 | 说明 |
|---|---|
| link_pk | 内部主键 |
| link_id | NGIQ-AEL-… |
| assertion_id | 指向 knowledge_assertions |
| evidence_id | 指向 evidence |
| evidence_role | supports / contradicts / qualifies |
| evidence_strength | 强度 |
| evidence_directness | 直接性 |
| is_primary_evidence | 是否主证据 |
| created_at | 时间戳 |
| remark | 备注 |

> 例：APOE increasesRiskOf AlzheimerDisease 也能绑定具体 Evidence。
