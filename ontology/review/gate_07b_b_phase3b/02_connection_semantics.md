# Gate 7B-B Phase 3B — Connection Scientific Semantics

## 1. connection_class 四类科学语义（CHECK 受控）

```
structural_connection / projection / functional_connectivity / effective_connectivity
```

- 未引入 ConnectionType ontology table / `connection_types`（不做第二套 taxonomy truth）。

## 2. StructuralConnection

- 表示存在物理/解剖神经通路。
- directionality 可为 directed / non_directional / direction_unknown。
- **directed ≠ Projection**：source/target 已知不自动升级为 Projection（测试 `test_directed_structural_not_auto_projection`）。

## 3. Projection

- StructuralConnection 的特殊类型，需明确 source + target + axonal projection 科学语义。
- **DTI/tractography alone 不能证明 Projection direction**（科学语义，未编码成"directed=true → projection"）。
- 测试 `test_projection_source_target_ok`：projection 可带 source+target endpoints。

## 4. FunctionalConnectivity

- V1 默认 **non-directional** statistical dependence / correlation / synchrony。
- 相关 ≠ StructuralConnection。
- **不伪造 source/target 方向**：FC 用两个 endpoint-role endpoint（测试 `test_functional_connectivity_not_forced_direction`）。

## 5. EffectiveConnectivity

- model-dependent directed influence / coupling，可有方向。
- **≠ Projection**：DCM/Granger/SEM 不自动产生 StructuralConnection/Projection（测试 `test_effective_connectivity_not_auto_projection`）。

## 6. directionality vocabulary

- CHECK：`directed / non_directional / direction_unknown`。
- `reciprocal` = DERIVED display vocabulary（27 audit §H）：不存储为 canonical directionality；Reciprocal 用两条 directed Connection（A→B、B→A）表达。本轮只建 schema，不做 dedup algorithm。

## 7. Canonical / Derived 边界

- Canonical = Connection entity + connection_endpoints。
- Derived（structurallyConnectedTo / functionallyConnectedTo / projectsTo / effectivelyConnectedTo）= 投影，**未**建第二套 PostgreSQL truth / 未写 Neo4j edge（测试 `test_no_direct_edge_canonical_duplication`）。
