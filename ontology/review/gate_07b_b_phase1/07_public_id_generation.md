# Gate 7B-B Phase 1 — Public ID Generation

## 1. Helper

`infra.next_ngiq_id(p_type text) RETURNS text`（PL/pgSQL，位于 infra schema）。

## 2. 行为

1. 输入 = 冻结 29-entry registry 中的类型键。
2. 映射 type → prefix → per-type sequence（**硬编码 CASE**，非用户传入 sequence）。
3. `nextval(infra.ngiq_<suffix>_seq)` 取号（并发/事务安全）。
4. 拼装 `NGIQ-<PREFIX>-<8位>`（`lpad(..., 8, '0')`）。
5. 未知类型 → `RAISE EXCEPTION`（fail closed）。
6. `nextval > 99999999` → `RAISE EXCEPTION`（禁 silent 9-digit expansion）。

## 3. 安全性质

| 要求（§7） | 实现 |
|---|---|
| 只接受冻结 registry 类型 | 29 分支 CASE，ELSE NULL → 异常 |
| 未知类型 FAIL CLOSED | `IF v_prefix IS NULL THEN RAISE` |
| 不能调用任意用户传入 sequence | 无 EXECUTE，sequence 名硬编码为字面量 |
| > 99,999,999 FAIL CLOSED | `IF v_num > 99999999 THEN RAISE` |
| 不允许 silent 9-digit | 同上前置守卫 |

## 4. 29-entry 映射（复用冻结 prefix registry）

brain_region→BR / cellular_neural_structure→CNS / neurobiological_process→NBP / connection→CON / connection_observation→COB / circuit→CIR / function→FUN / neurotransmitter→NT / receptor→RCP / gene→GEN / disease→DIS / symptom→SYM / research_study→STU / publication→PUB / evidence→EVI / atlas→ATL / external_region→XREG / region_mapping→RMAP / circuit_connection_membership→CCM / circuit_region_membership→CRM / brain_region_hierarchy_relation→BRH / function_hierarchy_relation→FHR / brain_region_aggregation_mapping→BRAM / knowledge_assertion→AST / relation_definition→PRED / evidence_link→ELK / source→SRC / alias→ALS / xref→XRF。

## 5. 无第二套 allocator

- 未建 allocator table / counter table / UUID 表。
- 未用 `MAX(id)+1`。
- per-type sequence 由 Phase 0 的 `gate7b_001` 创建（START 1 / INCREMENT 1 / NO CYCLE）。

## 6. kg_entities 不单独发号

- kg_entities 无自身 NGIQ 前缀；`entity_id` 由 subtype 的 per-type sequence 供给。
- 例：brain_region → `NGIQ-BR-00000001`；gene → `NGIQ-GEN-00000001`。
