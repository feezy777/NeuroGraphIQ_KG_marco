# Gate 7A — Change Summary（数据字典设计变更记录）

本轮状态: **仅设计文档，未修改 ontology TTL / 数据库 / API / 前端 / Neo4j**

---

## 1. 本 Gate 产出

- PostgreSQL V1 数据字典设计，最终共 **32 张表**（Round 2 新增 2 张 hierarchy 表；Phase A 新增 1 张 aggregation mapping 表）。
- 模块架构（Round 2）：Identity / Scientific Entity / Hierarchy / Spatial / Connection / Circuit / Atlas Mapping / Assertion / Governance（独立 schema）。

## 1b. Round 2 修订（人工反馈）

- 新增 `brain_region_hierarchy_relations`、`function_hierarchy_relations`（canonical hierarchy truth）。
- 模块重组：Spatial 独立、Atlas Mapping 独立、Hierarchy 独立。
- `parent_region_id` / `parent_function_id` 降为 DERIVED cache（HISTORICAL/SUPERSEDED：现规范为 parent_region_pk / parent_function_pk）。
- 表总数 29 → 31 → 32（HISTORICAL：Round 2 为 31，Phase A 新增 aggregation 表后为 32）。

## 2. 表清单（32）

- Identity（4）：kg_entities、entity_aliases、entity_xrefs、sources
- Scientific Entity（14）：brain_regions、cellular_neural_structures、neurobiological_processes、functions、neurotransmitters、receptors、genes、diseases、symptoms、research_studies、publications、evidence、atlases、external_regions
- Hierarchy（2）：brain_region_hierarchy_relations、function_hierarchy_relations
- Spatial（1）：brain_region_spatial_representations
- Connection（3）：connections、connection_endpoints、connection_observations
- Circuit（3）：circuits、circuit_region_memberships、circuit_connection_memberships
- Atlas Mapping（1）：region_mappings
- Granularity Integration（1）：brain_region_aggregation_mappings
- Assertion（3）：relation_definitions、knowledge_assertions、assertion_evidence_links
- Governance：独立 schema，后续设计

## 3. 关键设计决策

- ID：`NGIQ-<TYPE>-<8位>`，稳定、唯一、不复用、不编码科学含义。
- 名称来源：`source_name_original` + `name_en_source` / `name_zh_source` 区分官方名 vs 翻译名。
- remark：所有主要业务表保留 `remark TEXT NULL`。
- aliases / xrefs 独立建表。
- reified（Connection/RegionMapping/Membership）专用表 vs 普通 relation（knowledge_assertions）vs derived（不重复存）。
- assertion_evidence_links 解决普通 KG edge 挂 Evidence。
- Field Role + Frontend Display 双分类。
- Governance 类不进入本科学 schema。

## 4. 未做

- 未修改 ontology TTL（仍 0.6.0-gate6b / 23 Class / 23 ObjectProperty）。
- 未创建 migration / 未修改数据库 / API / 前端 / Neo4j。
- 未新增 OWL DataProperty / ObjectProperty / Class / Individual。

## 5. Final Correction / Freeze Candidate（Round 3）

8 项最终校正：① public ID 6 位→8 位；② hierarchy relation_type 仅 part_of/subfield_of（移除 overlaps/located_in）；③ kg_entities 唯一 identity truth + shared-PK（subtype 去双写）；④ `*_pk`/`*_id` 命名冻结（FK 引用 *_pk）；⑤ Evidence/ConnectionObservation/AssertionEvidenceLink 三层职责 + strength/directness 移到 assertion context；⑥ Governance 审核历史移出 scientific schema；⑦ Scientific Source ≠ Provenance Agent（source_type 删 llm）；⑧ reciprocal Projection = 两条 directed Connection（reciprocal 为 derived summary）。

- 表总数 32（Phase A 新增 brain_region_aggregation_mappings）。
- 最终冻结候选见 `23_gate_07a_freeze_candidate.md`。
