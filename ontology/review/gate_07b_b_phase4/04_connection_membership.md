# Gate 7B-B Phase 4 — Circuit Connection Membership（first-class）

## 1. 裁决：shared-PK first-class（§十二默认方向）

`circuit_connection_memberships` 采用 **shared-PK**（`entity_pk → kg_entities(entity_pk)`，entity_type = `circuit_connection_membership`）。

依据（CURRENT 首类信号占优，非单边裁决）：
- **entity_type 词表（16 §1）明确包含 `circuit_connection_membership`**（18 值之一）。
- **prefix registry（05）**：`circuit_connection_membership | NGIQ-CCM | first-class | reified, evidence-targetable`。
- **冻结 OWL manifest**：CircuitConnectionMembership 为正式 Class。
- **Evidence entity-target whitelist**：允许 `circuit_connection_membership` 直接接收 Evidence —— 这要求它是 identity-bearing kg_entities entity（evidence_links.entity_pk → kg_entities.entity_pk）。

> dict 18 §12 的 `membership_pk BIGSERIAL` 表达视为历史漂移（先于 shared-PK 决策）；因 CURRENT 的 entity_type 词表 + registry 明确首类，不触发 §十三停止条件。

## 2. canonical relations

- Circuit → hasConnectionMembership → CircuitConnectionMembership（`circuit_pk`）
- CircuitConnectionMembership → membershipConnection → Connection（`connection_pk`）

## 3. hasConnection 保持 Derived

- `circuit_connection_memberships` = 唯一 circuit→connection canonical truth。
- **未创建** `circuit_connections` 第二张 direct truth 表（测试 `test_no_second_circuit_connection_table`）。

## 4. 不复制 Connection truth

- membership 只表达"这条 canonical Connection 参与这个 Circuit"。
- **未复制** source_region/target_region/connection_class/directionality（测试 `test_ccm_is_shared_pk_first_class` 断言无这些列）。

## 5. 字段

- circuit_pk、connection_pk、step_order、branch_group、role_en/zh、is_required、is_core_connection、membership_confidence、remark。
- public ID = kg_entities.entity_id（NGIQ-CCM，`infra.ngiq_ccm_seq`）。

## 6. 测试覆盖

- `test_ccm_is_shared_pk_first_class`（entity_pk 存在、无 membership_id、无 Connection truth 复制）
- `test_ccm_entity_type_mismatch_rejected`（错误 entity_type 拒绝）
- `test_ccm_fk_and_shared_pk`（FK 正确 + NGIQ-CCM public ID）
- `test_ccm_invalid_connection_rejected`（非法 connection 拒绝）
- `test_no_second_circuit_connection_table`
