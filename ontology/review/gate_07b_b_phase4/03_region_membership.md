# Gate 7B-B Phase 4 — Circuit Region Membership

## 1. circuit_region_memberships（link 表）

- 表达 Circuit → includesRegion → BrainRegion 的 canonical membership。
- `circuit_pk → circuits.entity_pk`（RESTRICT）
- `brain_region_pk → brain_regions.entity_pk`（RESTRICT）
- `membership_id`：NGIQ-CRM-…（`infra.ngiq_crm_seq`）

## 2. 不等于 BrainRegion hierarchy

- Circuit 包含某脑区 **不代表** BrainRegion partOf Circuit 的解剖层级。
- 不写入 `brain_region_hierarchy_relations`；不修改 `parent_region_pk`。

## 3. 字段（按 CURRENT dict 18 §11）

- role_en / role_zh、sequence_order、is_core_member、membership_confidence、remark。

## 4. Duplicate protection（§十一）

- `UNIQUE (circuit_pk, brain_region_pk)`：同一 Circuit 中某 BrainRegion 至多出现一次（"完全相同 membership 重复" 拒绝）。
- **V1 modeling policy（正式解释）**：同一 canonical BrainRegion 在同一 Circuit 中当前只保留一条 canonical region membership。这是 V1 建模策略，**不是**对神经科学"一个脑区只能有一个功能角色"的声明。若未来确实需要同一 BrainRegion 承担多个独立角色，通过版本化 schema change 扩展（本轮不改数据库）。

## 5. 测试覆盖

- `test_region_membership_fk`（FK 正确）
- `test_region_membership_invalid_region_rejected`（非法 region 拒绝）
- `test_region_membership_duplicate_rejected`（重复 membership 拒绝）
