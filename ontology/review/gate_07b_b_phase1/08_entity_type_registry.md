# Gate 7B-B Phase 1 — entity_type Registry

## 1. kg_entities.entity_type 允许值 = 18（依据 16 §1）

```
brain_region / cellular_neural_structure / neurobiological_process /
connection / circuit / function / neurotransmitter / receptor / gene /
disease / symptom / research_study / publication / evidence / atlas /
external_region / region_mapping / circuit_connection_membership
```

## 2. 23 OWL Class → 18 entity_type 的映射

23 个冻结 OWL Class 因 subClassOf 层级折叠为 16 个 entity_type + 2 个 reified 实体：

| 折叠 | 结果 |
|---|---|
| Connection + StructuralConnection + Projection + FunctionalConnectivity + EffectiveConnectivity | `connection` |
| Function + CognitiveFunction | `function` |

23 − 4（Connection 子类）− 1（CognitiveFunction）= 18。✅

## 3. 不在 kg_entities.entity_type 的类型

| 类型 | 原因 |
|---|---|
| `knowledge_assertion` | §11 指令：KnowledgeAssertion 不进 OWL entity type；是 DB reified 概念（NGIQ-AST 前缀仍在 prefix registry，用于独立表） |
| `source` | 独立 registry，非 shared-PK |
| `alias` / `xref` / `evidence_link` / `brain_region_hierarchy_relation` / `function_hierarchy_relation` | 技术 link 记录（不要求完整 identity） |
| `connection_observation` | link/obs |
| `circuit_region_membership` / `brain_region_aggregation_mapping` / `relation_definition` | reified 表，独立 `*_pk`（不进 kg_entities.entity_type 词表，但保留 NGIQ 前缀） |

## 4. 实现

- `kg_entities.entity_type` 用 **VARCHAR(48) + CHECK**（18 值），非 ENUM（§N.1：可能扩展用 VARCHAR + validation，不锁 ENUM）。
- ID helper `infra.next_ngiq_id` 用完整 29-entry registry（含上述 link/obs/reified 类型），供对应表发号。

## 5. 校验

- 未知 entity_type（如 `knowledge_assertion`、`bogus`）→ CHECK violation（DB 层拒绝）。
- helper 未知类型 → RAISE（fail closed）。
