# Gate 7A — Freeze Candidate（冻结候选总结）

> Gate 7B 将以此文件作为 migration 实施依据。本文只总结最终冻结决策，不含未决问题细节。

---

## A. Schema Module Structure

```
Identity（4）        kg_entities, entity_aliases, entity_xrefs, sources
Scientific Entity（14） brain_regions, cellular_neural_structures, neurobiological_processes,
                        functions, neurotransmitters, receptors, genes, diseases, symptoms,
                        research_studies, publications, evidence, atlases, external_regions
Hierarchy（2）        brain_region_hierarchy_relations, function_hierarchy_relations
Spatial（1）          brain_region_spatial_representations
Connection（3）       connections, connection_endpoints, connection_observations
Circuit（3）          circuits, circuit_region_memberships, circuit_connection_memberships
Atlas Mapping（1）    region_mappings
Granularity Integration（1） brain_region_aggregation_mappings
Assertion（3）        relation_definitions, knowledge_assertions, evidence_links
Governance            → 独立 schema（后续设计，不计入）
```

**B. 总表数 = 32**（Governance 不在此 schema）。

## C. Public ID Policy（冻结）

- 格式：`NGIQ-<TYPE>-<8位>`（8 位，非 6 位），例 `NGIQ-BR-00000001`。
- 规则：一经分配永久不变；不因 name 修改改变；不因 merge 重新分配；不因 deprecated 释放；**永不复用**。
- 数字部分不编码科学语义；不把 hemisphere / atlas / type / version 写进 ID。
- deprecated 实体旧 ID 永久保留；merge 时旧 ID 指向 canonical replacement，不分配给新实体。
- prefix 全表（禁止重复）：

| 实体 | prefix |
|---|---|
| BrainRegion | NGIQ-BR |
| CellularNeuralStructure | NGIQ-CNS |
| NeurobiologicalProcess | NGIQ-NBP |
| Connection | NGIQ-CON |
| ConnectionObservation | NGIQ-COB |
| Circuit | NGIQ-CIR |
| Function | NGIQ-FUN |
| Neurotransmitter | NGIQ-NT |
| Receptor | NGIQ-RCP |
| Gene | NGIQ-GEN |
| Disease | NGIQ-DIS |
| Symptom | NGIQ-SYM |
| ResearchStudy | NGIQ-STU |
| Publication | NGIQ-PUB |
| Evidence | NGIQ-EVI |
| Atlas | NGIQ-ATL |
| ExternalRegion | NGIQ-XREG |
| RegionMapping | NGIQ-RMAP |
| CircuitConnectionMembership | NGIQ-CCM |
| CircuitRegionMembership | NGIQ-CRM |
| BrainRegionHierarchyRelation | NGIQ-BRH |
| FunctionHierarchyRelation | NGIQ-FHR |
| KnowledgeAssertion | NGIQ-AST |
| RelationDefinition | NGIQ-PRED |
| Source | NGIQ-SRC |
| Alias | NGIQ-ALS |
| Xref | NGIQ-XRF |
| EvidenceLink | NGIQ-ELK |

## D. kg_entities Identity Policy（冻结）

- `kg_entities` 是 **唯一 identity truth**：所有 first-class canonical entity 的 identity / public ID / display name / definition / description / lifecycle status 的唯一来源。
- 字段：entity_pk、entity_id、entity_type、name_en/name_zh、abbreviation、definition_en/definition_zh、description_en/description_zh、source_name_original、source_language、name_en_source/name_zh_source、translation_review_status、record_status、version、created_at/updated_at、created_by_agent/updated_by_agent、metadata_json、remark。
- **Subtype 表禁止独立维护第二套 name/definition/description truth**（移除或标 DERIVED DISPLAY CACHE；优先移除）。
- first-class / user-visible 实体进入 kg_entities；技术 link 记录（connection_endpoints、evidence_links）不要求完整 identity（只需 PK + public ID + FK + 结构字段 + remark）。

## E. PK / FK Policy（冻结）

- `*_pk` = PostgreSQL 内部主键/外键目标（BIGINT）。
- `*_id` = 对外 stable public ID（`NGIQ-…`）。
- 所有 FK 引用内部 `*_pk`，不引用 public `*_id`。
- **推荐 shared-PK（Class Table Inheritance）**：`kg_entities.entity_pk` 同时作为 subtype 表 PK/FK，subtype 表不另生成 `*_pk`。
- 例：kg_entities.entity_pk=101（entity_id=NGIQ-BR-00000001）↔ brain_regions.entity_pk=101。

## F. Bilingual Display Policy（冻结）

- **ACTIVE** first-class 实体必须具备 name_en + name_zh，并记录 name_en_source / name_zh_source。
- **PROPOSED** 允许 name_en/name_zh 其一暂空，但 source_name_original 必须保留。
- name source 取值：source / human_curated / translated_human / translated_ai / normalized / unknown。
- 技术 link 记录不要求双语名称。

## G. Hierarchy Policy（冻结）

- `brain_region_hierarchy_relations` / `function_hierarchy_relations` = **canonical hierarchy truth**。
- BrainRegion hierarchy `relation_type` V1 仅：`part_of`、`subfield_of`（移除 overlaps / located_in）。
- Function hierarchy `relation_type`：`subclass_of`（概念分类）、`part_of`（组成）；traversal 必须显式指定 relation_type，不混同。
- `parent_region_pk` / `parent_function_pk` = **DERIVED / DISPLAY CACHE ONLY**，非 canonical truth。

## H. Connection Direction Policy（冻结）

- `directionality` V1：`directed` / `non_directional` / `direction_unknown`。
- `reciprocal` = **DERIVED display vocabulary**（derived_only），不作为 Projection canonical storage 首选。
- **Reciprocal Projection 存为两条 directed Connection**（A→B 与 B→A 各一条 Projection），因两方向 Evidence/Publication/strength/confidence/method 可不同；前端/Neo4j 派生 `A↔B`。
- FunctionalConnectivity 用 endpoint（不伪造 source/target）；directed 连接用 source/target。

## I. Evidence Model（冻结，三层职责）

- **Evidence** = 具体证据内容与来源（publication/study、evidence_text、定位、modality/analysis/intervention、extraction provenance）。
- **ConnectionObservation** = 某项研究对某 Connection 的 study-level 结构化观测（condition/population/sample_size/metric/effect_size/p_value/CI/direction_reported/strength_reported）。
- **AssertionEvidenceLink** = 某 Evidence 对某 Assertion 的作用（evidence_role=supports/contradicts/qualifies、evidence_strength、evidence_directness、is_primary_evidence）。
- **evidence_strength / evidence_directness 的 canonical 存储 = AssertionEvidenceLink**（同一 Evidence 对不同 Assertion 可 direct/strong vs indirect/moderate）。
- **model_confidence ≠ evidence_strength**（前者是模型/抽取器置信度，非科学证据强度）。区分：model_confidence / evidence_strength / evidence_directness / mapping_confidence / membership_confidence / overall_confidence。

## J. Assertion Model（冻结）

- `relation_definitions` 管理 ObjectProperty vocabulary（predicate_key、representation_role=canonical/derived、owl_iri）。
- `knowledge_assertions` = 普通 ObjectProperty 的 assertion（subject_entity_id/predicate_id/object_entity_id/derivation_type/confidence/qualifiers_json）。
- reified 事实（Connection/RegionMapping/Membership）用专用表，不进 assertions；derived relation 不重复存。

## K. Source / Provenance Policy（冻结）

- **Scientific Source**（进入 sources）= 知识/数据真正来源：Julich-Brain、Brainnetome、HCP、PubMed、Europe PMC、HGNC、MONDO、HPO、ChEBI、IUPHAR、具体 Publication。
- **Provenance Agent**（不进入 sources）= DeepSeek/GPT/BioSEPBERT/Human curator/ImportPipeline/RuleEngine，表示谁抽取/翻译/归一化/审核/推理。
- `sources.source_type` **删除 `llm`**。
- **LLM 不得作为 Evidence scientific source**；Evidence 记 publication=PMID，extraction agent=DeepSeek，二者分离。

## L. Governance Boundary（冻结）

- Governance 审核历史（human_reviews / model_reviews / validation_records / promotion_records / rollback_history）→ 未来 Governance schema。
- 科学表最多保留当前状态快照：record_status / canonical_status / review_status_snapshot（Field Role：GOVERNANCE SNAPSHOT），不存完整 reviewer/reviewed_at 历史。

## M. Derived / Cache Policy（冻结）

- evidence_count / publication_count / observation_count / region_count / connection_count / first_reported_year / latest_evidence_year / hierarchy_depth / parent_*_pk cache → Field Role = **DERIVED**，可重算，非 independent truth。
- 未来实现可 VIEW / MATERIALIZED VIEW / generated cache（本轮不决定）。

## N. Remaining Non-Blocking Future Questions

1. controlled vocabulary 实现：极稳定用 CHECK/ENUM，可能扩展用 reference table 或 VARCHAR + validation（不全部锁 ENUM）。
2. derived 字段具体物化实现（VIEW vs MATERIALIZED VIEW）。
3. publication 的 authors_json / mesh_terms_json 是否 V1 拆关系表。
4. overlaps/located_in 等 spatial relations 是否未来建 brain_region_spatial_relations（当前 DEFER，不增第 32 张表）。

---

## O. Granularity & Roll-up（新增，Phase A）

- **Human-only**：V1 production = Homo sapiens（NCBI taxon 9606）；非人脑（Allen Mouse 等）production_eligible=FALSE；Allen 名称必须解析 Human/Mouse；Allen Human 需验证 9606 才为 auxiliary source。
- **G1–G4**：G1_MACRO=Macro96(96)、G2_MESO_ANATOMICAL=AAL3、G3_MESO_FINE=Human Brainnetome(246)（HCP-MMP 360 / Schaefer 皆 G3 supplementary）、G4_MICROSTRUCTURAL_FINE=Julich-Brain；BigBrain=spatial reference only（禁 G5）。
- **不是严格 Atlas 树**；roll-up 依赖显式 mapping，不依赖名称匹配。
- **新增 brain_region_aggregation_mappings（第 32 表）**：source=较细、target=较粗；mapping_relation/mapping_method/coverage/rollup_eligible/is_primary_rollup；partial_overlap 默认不 roll-up；geometry 不自动 union。
- aggregation mapping 的 source_granularity_level / target_granularity_level = **DERIVED / SNAPSHOT**（= 对应 BrainRegion.granularity_level，自动复制，非独立 SCIENTIFIC CANONICAL TRUTH）。
- Connection/Circuit roll-up 产物 derivation_type=inferred（hierarchical_rollup），去重、self-loop collapse、N→1 不宣称几何 union。
- brain_region_hierarchy_relations（part_of/subfield_of）保持 anatomical truth，不混 aggregation。

## P. Evidence Link Constraints（Gate 6E-A.2）

- **evidence_links**（原 assertion_evidence_links）：XOR target（assertion_pk ⊕ entity_pk）。
- **Entity whitelist（V1）**：entity_pk 仅 connection / circuit / region_mapping / circuit_connection_membership。
- **claim_scope**：entity target 必填；assertion target 可 NULL；vocab 已移除 function。
- **ACTIVE Evidence source completeness**：publication_pk OR scientific_source_pk 必填（study_pk 单独不足；LLM 非 source）。

**结论：Gate 7A 冻结候选已就绪，32 表 + 上述 A–P 决策作为 Gate 7B migration 实施依据。**
