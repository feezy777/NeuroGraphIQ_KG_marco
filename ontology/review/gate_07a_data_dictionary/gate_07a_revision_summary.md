# Gate 7A — 第二轮修订摘要（Data Dictionary Revision Summary）

修订时间: 2026-08-28
修订性质: 人工审查后结构调整（Round 2）
本轮状态: **仅设计文档，未修改 ontology TTL / 数据库**

---

## 0. 人工反馈

将 ER 模块重组，并新增两个 hierarchy 关系表（解决 hierarchy 显式化问题）。

## 1. 新增 2 张表

| 表 | 目的 | ID 前缀 |
|---|---|---|
| brain_region_hierarchy_relations | 显式记录脑区上位/下位层级关系（HISTORICAL/SUPERSEDED：Round 2 曾列 part_of/overlaps/located_in 与 parent_region_id，现规范为 part_of/subfield_of + parent_region_pk） | NGIQ-BRH-… |
| function_hierarchy_relations | 显式记录功能层级关系（subclass_of / part_of） | NGIQ-FHR-… |

> 直接回应 Round 1 open question #11（parent_region_id 与 partOf 冲突，HISTORICAL/SUPERSEDED：现为 parent_region_pk / parent_function_pk）：hierarchy relation 表成为 **canonical hierarchy truth**，parent_region_pk / parent_function_pk 降为 DERIVED cache。

## 2. 模块重组

| 模块 | 表数 | 表 |
|---|---|---|
| Identity | 4 | kg_entities、entity_aliases、entity_xrefs、sources |
| Scientific Entity | 14 | brain_regions、cellular_neural_structures、neurobiological_processes、functions、neurotransmitters、receptors、genes、diseases、symptoms、research_studies、publications、evidence、atlases、external_regions |
| Hierarchy | 2 | brain_region_hierarchy_relations、function_hierarchy_relations |
| Spatial | 1 | brain_region_spatial_representations |
| Connection | 3 | connections、connection_endpoints、connection_observations |
| Circuit | 3 | circuits、circuit_region_memberships、circuit_connection_memberships |
| Atlas Mapping | 1 | region_mappings |
| Assertion | 3 | relation_definitions、knowledge_assertions、assertion_evidence_links |
| Governance | — | 独立 schema，后续设计 |

## 3. 表总数变化

- Round 1：29
- Round 2：**31**（+2 hierarchy 表）

## 4. 关键语义

- brain_region_hierarchy_relations：canonical hierarchy truth（parent/child + relation_type + hierarchy_source + confidence）。
- parent_region_id（brain_regions 表）/ parent_function_id（functions 表）降为 **DERIVED cache**，不再作为唯一 hierarchy truth（HISTORICAL/SUPERSEDED：现规范为 parent_region_pk / parent_function_pk）。
- 与 CLAUDE.md 原则一致：跨粒度用显式 mapping_type，永不隐式按名合并。

## 5. Final Correction / Freeze Candidate（Round 3）

1. public ID 6 位 → **8 位**（`NGIQ-BR-00000001`）。
2. ID 永不复用；deprecated 永久保留。
3. hierarchy 移除 overlaps / located_in（V1 仅 part_of / subfield_of）。
4. hierarchy table = canonical hierarchy truth（parent_*_pk 仅 DERIVED CACHE）。
5. kg_entities = 唯一 identity truth；subtype 表去双写 identity/display 字段。
6. `*_pk`（内部 BIGINT）/ `*_id`（public ID）规则冻结；FK 引用 `*_pk`。
7. 推荐 shared-PK（Class Table Inheritance）subtype model。
8. Evidence 三层职责（Evidence / ConnectionObservation / AssertionEvidenceLink）明确。
9. evidence_strength / evidence_directness canonical 存储移到 AssertionEvidenceLink。
10. Governance 审核历史移出 scientific schema（仅留 status snapshot）。
11. Scientific Source ≠ Provenance Agent；source_type 删除 llm。
12. LLM 不得作为 scientific source。
13. reciprocal Projection = 两条 directed Connection（reciprocal 为 derived summary）。
14. derived statistics 全部标 Field Role=DERIVED。
15. 总表数 31 → 32（Phase A 新增 brain_region_aggregation_mappings）。

> 详见 `23_gate_07a_freeze_candidate.md`。
