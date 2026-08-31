# Gate 7A — Function / Process / Structure Tables

本轮状态: **仅设计文档**

---

## 1. functions

| 字段 | 说明 |
|---|---|
| function_pk | 内部主键 |
| function_id | NGIQ-FUN-… |
| name_en / name_zh | 名称 |
| abbreviation | 缩写 |
| function_category | general / cognitive |
| function_level | 层级 |
| parent_function_pk | 父功能 [DERIVED CACHE] |
| definition_en / definition_zh | 定义 |
| description_en / description_zh | 描述 |
| canonical_status | canonical 状态 |
| remark | 备注 |

> 不单独建 CognitiveFunction 物理表；用 `function_category=cognitive` 区分。

## 1b. function_hierarchy_relations（Round 2 新增，canonical hierarchy truth）

| 字段 | 说明 |
|---|---|
| hierarchy_pk | 内部主键 |
| hierarchy_relation_id | NGIQ-FHR-… |
| parent_function_pk | 上位功能（→ functions） |
| child_function_pk | 下位功能（→ functions） |
| relation_type | subclass_of / part_of |
| hierarchy_source | ontology / curated |
| is_canonical | 是否 canonical |
| confidence | 置信度 |
| source_pk | 来源（→ sources） |
| remark | 备注 |

> `parent_function_pk`（functions 表内）降为 DERIVED cache；canonical hierarchy 走本表。

## 2. cellular_neural_structures（轻量）

| 字段 | 说明 |
|---|---|
| structure_pk | 内部主键 |
| structure_id | NGIQ-CNS-… |
| name_en / name_zh | 名称 |
| abbreviation | 缩写 |
| structure_category | 类别 |
| definition_en / definition_zh | 定义 |
| description_en / description_zh | 描述 |
| canonical_status | canonical 状态 |
| remark | 备注 |

## 3. neurobiological_processes

| 字段 | 说明 |
|---|---|
| process_pk | 内部主键 |
| process_id | NGIQ-NBP-… |
| name_en / name_zh | 名称 |
| abbreviation | 缩写 |
| process_category | 类别 |
| definition_en / definition_zh | 定义 |
| description_en / description_zh | 描述 |
| canonical_status | canonical 状态 |
| remark | 备注 |

> V1 对 structure/process 保持轻量，不展开细胞本体。
