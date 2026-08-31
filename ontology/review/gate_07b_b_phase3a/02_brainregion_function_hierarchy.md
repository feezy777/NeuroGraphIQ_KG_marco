# Gate 7B-B Phase 3A — BrainRegion / Function Hierarchy

## 1. brain_region_hierarchy_relations = canonical truth

- `relation_type` 受控：`part_of` / `subfield_of`（subfield_of ⊂ part_of；DB 不做 OWL inference，但类型受 CHECK 约束）。
- `parent_region_pk` / `child_region_pk` FK → `brain_regions(entity_pk)`。
- **self relation 禁止**：`CHECK (parent_region_pk <> child_region_pk)`（A part_of A 拒绝）。
- 全图 cycle 检测本轮不实现（CURRENT 未规定更强 cycle policy）。

## 2. brain_regions.parent_region_pk 仍是 DERIVED CACHE

- 真实 hierarchy truth = `brain_region_hierarchy_relations`。
- `parent_region_pk` 仅快速读取主要父级，非 truth；不设计双向同步成两份独立 truth（cache refresh 机制未过度实现，仅明确字段角色）。
- 测试 `test_parent_region_pk_is_derived_cache` 验证其为 nullable 缓存列。

## 3. function_hierarchy_relations = canonical truth

- `relation_type`：`subclass_of` / `part_of`。
- `subclass_of` 在 ontology projection 对应 `subFunctionOf`，**不是** `rdfs:subClassOf`（Function concept 是 ABox Individual/未来实体，非 OWL Class）。
- Function `part_of`：仅数据库语义，OWL 仍 DEFER。
- **self relation 禁止**：`CHECK (parent_function_pk <> child_function_pk)`。

## 4. functions.parent_function_pk 仍是 DERIVED CACHE

- 不能代替 `function_hierarchy_relations` canonical truth。

## 5. 测试覆盖

- BRH/FHR FK 正确（`test_brh_fk_valid` / `test_fhr_fk_valid`）
- self relation 拒绝（`test_brh_self_relation_rejected` / `test_fhr_self_relation_rejected`）
- 非法 relation_type 拒绝（`test_brh_illegal_relation_type_rejected` / `test_fhr_illegal_relation_type_rejected`）
