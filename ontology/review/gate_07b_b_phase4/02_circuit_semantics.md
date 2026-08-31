# Gate 7B-B Phase 4 — Circuit Scientific Semantics

## 1. Circuit = biological/functional circuit，非 graph cycle

- **不要求 `closed_loop = TRUE`**：`is_closed_loop` 为可空 BOOLEAN 描述属性，无 CHECK 强制（测试 `test_closed_loop_not_required`）。
- **不要求 A→B→C→A** 才成 Circuit。
- **无 "≥3 BrainRegion + ≥2 Connection" DB 硬约束**：region_count / connection_count 为 DERIVED 描述列（测试 `test_two_region_circuit_allowed`：2-region circuit 可保存）。

## 2. Circuit ≠ 随机 Connection 集合

- 数据库不自动从"共享脑区的若干 Connection"生成 Circuit。
- 检测到 graph cycle 也**不**自动创建 Circuit（测试 `test_graph_cycle_does_not_auto_generate_circuit`）。
- Circuit entity 必须来自：source-reported circuit / 人工批准 authoritative circuit / 明确标记 inferred/composed candidate。generation pipeline 后续实现。

## 3. Circuit 不自动补 Connection

- Circuit A→B→C 若缺 B→C，**不**自动生成 canonical Connection；只可能未来产生 candidate/hypothesis。本轮不实现推理。

## 4. Circuit type 不重新建立 ontology taxonomy

- 未创建 `circuit_types` / 未恢复 CircuitType OWL class。
- 属性字段按 CURRENT 词表：`construction_mode`（composed/reconstructed）、`derivation_type`（reported/inferred）、`granularity_scope`（DERIVED，G1–G4/MIXED/UNSPECIFIED）、`canonical_status`。
- **`granularity_scope` 正式角色 = DERIVED**：由 Circuit 的 region memberships + BrainRegion.granularity_level + 必要 mapping context 推导；**不是**与 BrainRegion granularity 并列的独立 canonical truth，禁止当作独立粒度事实维护。

## 5. Circuit derivation

- `derivation_type`：reported（外部 source 明确报告）/ inferred（根据 Region/Connection/Function 推导的候选）。
- 人工审核**不能**把 inferred 自动改成 reported。

## 6. 测试覆盖

- `test_closed_loop_not_required`
- `test_two_region_circuit_allowed`
- `test_proposed_incomplete_circuit_saved`（PROPOSED 可暂不完整）
- `test_graph_cycle_does_not_auto_generate_circuit`
