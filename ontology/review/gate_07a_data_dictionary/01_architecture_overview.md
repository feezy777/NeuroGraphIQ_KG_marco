# Gate 7A — Architecture Overview（数据字典架构总览）· 第二轮修订

本轮状态: **仅设计文档，未修改 ontology TTL / 数据库 / API / 前端 / Neo4j**

---

## 1. 定位

核心本体（Gate 5B/6B）负责 **Class + ObjectProperty + 科学语义**。具体属性主要作为数据库字段保存，而非立即全部写成 OWL DataProperty。本轮设计 PostgreSQL V1 数据字典。

## 2. 分层架构（Round 2）

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

Granularity Integration
└─ brain_region_aggregation_mappings

Assertion
├─ relation_definitions
├─ knowledge_assertions
└─ evidence_links

Governance
→ 独立 schema，后续设计
```

## 3. 15 条核心设计原则

1. 所有主要实体有稳定、有意义的 NeuroGraphIQ ID（`NGIQ-<TYPE>-<8位>`）。
2. 可展示知识尽量有中英文名。
3. 中英文定义/描述尽量保留。
4. 原始来源名称必须保留（`source_name_original`）。
5. 翻译得到的名称不能伪装成来源官方名称（name source 区分）。
6. 所有主要业务表保留 `remark TEXT NULL`。
7. 高频、科学意义明确、需筛选的字段结构化为列。
8. 不稳定、来源特异、低频字段进入 `metadata_json`。
9. aliases 单独建表。
10. external IDs / xrefs 单独建表。
11. canonical scientific entities 与 observation/evidence 分层。
12. 普通 KG relation 使用 assertion model。
13. Connection / RegionMapping / CircuitMembership 保持 reified model。
14. 所有自动生成内容保留 provenance。
15. 数据库服务于：前端详情、搜索、筛选、人工审核、Evidence tracing、Neo4j projection、后续推理。

## 4. 表清单（32 张）

| 模块 | 表数 | 表 |
|---|---|---|
| Identity | 4 | kg_entities、entity_aliases、entity_xrefs、sources |
| Scientific Entity | 14 | brain_regions、cellular_neural_structures、neurobiological_processes、functions、neurotransmitters、receptors、genes、diseases、symptoms、research_studies、publications、evidence、atlases、external_regions |
| Hierarchy | 2 | brain_region_hierarchy_relations、function_hierarchy_relations |
| Spatial | 1 | brain_region_spatial_representations |
| Connection | 3 | connections、connection_endpoints、connection_observations |
| Circuit | 3 | circuits、circuit_region_memberships、circuit_connection_memberships |
| Atlas Mapping | 1 | region_mappings |
| Granularity Integration | 1 | brain_region_aggregation_mappings |
| Assertion | 3 | relation_definitions、knowledge_assertions、evidence_links |
| Governance | — | 独立 schema，后续设计 |

> 合计 **32 张科学表**（Governance 不在此 schema）。

## 5. Hierarchy 显式化（Round 2 关键变更）

- hierarchy 关系表（brain_region_hierarchy_relations / function_hierarchy_relations）是 **canonical hierarchy truth**。
- 实体表内 `parent_region_pk` / `parent_function_pk` 降为 **DERIVED cache**，不再作为唯一 hierarchy truth。
- 跨粒度/层级用显式 relation_type（BrainRegion: part_of / subfield_of；Function: subclass_of / part_of），永不隐式按名合并。
