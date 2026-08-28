# Gate 7A — Open Questions & Risks（开放问题与风险）

本轮状态: **仅设计文档**

---

## 1. 主要风险（逐项）

| # | 风险 | 分析 | 建议 |
|---|---|---|---|
| 1 | kg_entities 过度抽象 | identity layer 统一了展示字段，但可能削弱 subtype 表语义 | kg_entities 只做 identity/展示层，科学事实留在 subtype 表；不做通用 CRUD |
| 2 | entity_type 与 subtype 表不一致 | 两边可能漂移 | CHECK 约束 + 应用层触发器/服务校验，单点写入 |
| 3 | 中英文名来源可信 | AI 翻译可能伪装官方名 | name_en_source/name_zh_source 强制区分 + 前端标注 |
| 4 | aliases 重复 | 同文本多来源 | alias_id 唯一 + (entity_id, alias_text, alias_type) 去重 |
| 5 | xref 一对多 | 一实体多外部映射 | 允许一对多，靠 match_type + is_primary 区分主映射 |
| 6 | connection endpoints 与 source/target 重复 | 两套人工维护 truth | directed 连接只用 source/target，不建 endpoint rows；endpoint 仅用于 non-directional |
| 7 | derived count 失效 | evidence_count 等易过时 | DERIVED 字段，物化/定时刷新，不人工维护 |
| 8 | knowledge_assertions 与 Connection 重复 | 同一事实两处 | reified 事实（Connection/RegionMapping/Membership）专用表，普通 relation 用 assertions，derived 不重复存 |
| 9 | Evidence 挂 reified entity | 无统一路径 | connection_observations / region_mapping 专用 evidence 字段 |
| 10 | Evidence 挂 ordinary relation | 无路径 | assertion_evidence_links |
| 11 | parent_region_pk 与 partOf 冲突 | 可能绕过 ontology hierarchy | **已解决（Round 2）**：新增 brain_region_hierarchy_relations / function_hierarchy_relations 为 canonical hierarchy truth；parent_region_pk / parent_function_pk 降为 DERIVED cache |
| 12 | JSON 字段过多 | 结构丢失 | 仅 metadata_json / 来源特异字段用 JSON，高频字段结构化 |
| 13 | nullable 字段过多 | 数据质量 | 关键身份/分类字段 NN，统计量按方法 nullable |
| 14 | ID 并发安全 | 发号竞争 | DB sequence / 原子发号器 |
| 15 | public ID 复用 | 历史断裂 | 禁止复用；deprecated 永久保留 |
| 16 | deprecated entity ID | 是否永久保留 | 推荐保留（软删除/record_status=deprecated），不物理删除 |

## 2. 待人工确认的开放问题

1. `kg_entities` 是否作为唯一 identity 层，还是各 subtype 表独立维护 name 字段（双写风险 vs 查询便利）？
2. `parent_region_pk` 是否 V1 就保留，还是等 ontology partOf 建立后再加？
3. Connection 的 `source_region_id/target_region_id` 与 `connection_endpoints` 的共存规则是否接受"directed 不建 endpoint"？
4. derived count 字段是否 V1 就物化，还是查询时实时计算？
5. 中英文 name 是否所有实体都强制双语，还是允许仅有单一语言？
6. JSON 字段（authors_json / mesh_terms_json / affiliations_json）是否 V1 拆分关系表，还是先 JSON 缓存？
7. ID 数字部分是否预留区块（如 00000001–99999999），还是全局单调递增？
8. `sources` 是否作为唯一 provenance 外键，还是允许 source_name 文本冗余？
