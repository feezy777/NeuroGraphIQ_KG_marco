# Gate 7A — ER Model（实体关系模型）· 第二轮修订

本轮状态: **仅设计文档**

---

## 1. 模块化 ER 结构（Round 2）

```
Identity
├─ kg_entities
├─ entity_aliases
├─ entity_xrefs
└─ sources

Scientific Entity
├─ brain_regions
├─ cellular_neural_structures
├─ neurobiological_processes
├─ functions
├─ neurotransmitters
├─ receptors
├─ genes
├─ diseases
├─ symptoms
├─ research_studies
├─ publications
├─ evidence
├─ atlases
└─ external_regions

Hierarchy
├─ brain_region_hierarchy_relations
└─ function_hierarchy_relations

Spatial
└─ brain_region_spatial_representations

Connection
├─ connections
├─ connection_endpoints
└─ connection_observations

Circuit
├─ circuits
├─ circuit_region_memberships
└─ circuit_connection_memberships

Atlas Mapping
└─ region_mappings

Assertion
├─ relation_definitions
├─ knowledge_assertions
└─ evidence_links

Governance
→ 独立 schema，后续设计
```

## 2. 关键关系

| 关系 | 说明 |
|---|---|
| kg_entities 1—N entity_aliases / entity_xrefs | 别名与外部映射统一挂 identity 层 |
| brain_regions 1—N brain_region_hierarchy_relations | 上位/下位层级（canonical hierarchy truth） |
| functions 1—N function_hierarchy_relations | 功能层级（canonical） |
| brain_regions 1—N brain_region_spatial_representations | 多 atlas/version/space 空间表示 |
| connections 1—N connection_endpoints | endpoint 模型（non-directional / direction-unknown） |
| connections 1—N connection_observations | canonical vs observation 分层 |
| circuits 1—N circuit_region_memberships | 回路成员 |
| circuits 1—N circuit_connection_memberships | 回路连接成员（reified） |
| atlases 1—N external_regions | 图谱—外部区域 |
| external_regions + brain_regions 1—N region_mappings | 映射 reification |
| relation_definitions 1—N knowledge_assertions | 谓词 vocabulary |
| knowledge_assertions 1—N evidence_links 1—1 evidence | 断言挂证据 |
| publications 1—N evidence | 文献—证据 |
| research_studies 1—N publications / evidence | 研究—文献/证据 |

## 3. Hierarchy 语义（Round 2 关键）

- `brain_region_hierarchy_relations` / `function_hierarchy_relations` = canonical hierarchy truth（relation_type + hierarchy_source + confidence）。
- 实体表内 `parent_region_pk` / `parent_function_pk` = DERIVED cache（非唯一 truth）。
- 跨粒度/层级用显式 relation_type，永不隐式按名合并。

## 4. 备注

- 各 subtype 表通过 `entity_id` 与 `kg_entities` 关联（1—1）。
- `sources` 作为 provenance 被广泛引用（source_id 外键）。
- 所有表含内部 `*_pk` 主键 + stable public `*_id`。
- 表总数 32（Governance 不在此 schema）。
