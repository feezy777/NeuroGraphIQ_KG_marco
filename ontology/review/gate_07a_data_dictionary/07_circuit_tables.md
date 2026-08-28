# Gate 7A — Circuit Tables（回路由）

本轮状态: **仅设计文档**

---

## 1. circuits

| 字段 | 说明 |
|---|---|
| circuit_pk | 内部主键 |
| circuit_id | NGIQ-CIR-… |
| name_en / name_zh | 名称 |
| abbreviation | 缩写 |
| description_en / description_zh | 描述 |
| construction_mode | composed / reconstructed |
| derivation_type | reported / inferred |
| topology_summary_en / topology_summary_zh | 拓扑摘要 |
| is_closed_loop | 是否闭合（nullable） |
| has_feedback | 是否有反馈（nullable） |
| has_recurrence | 是否有循环（nullable） |
| region_count / connection_count | 成员统计（DERIVED） |
| evidence_count / publication_count | 证据统计（DERIVED） |
| canonical_status | canonical 状态 |
| confidence_summary | 置信度摘要 |
| first_reported_year / latest_evidence_year | 年份 |
| remark | 备注 |

> 不因此重新创建 CircuitType ontology（已 REMOVE）。

## 2. circuit_region_memberships

| 字段 | 说明 |
|---|---|
| membership_pk | 内部主键 |
| membership_id | NGIQ-CRM-… |
| circuit_id | 指向 circuits |
| brain_region_id | 指向 brain_regions |
| role_en / role_zh | 角色 |
| sequence_order | 顺序 |
| is_core_member | 是否核心成员 |
| membership_confidence | 成员置信度 |
| remark | 备注 |

## 3. circuit_connection_memberships（对应 ontology CircuitConnectionMembership）

| 字段 | 说明 |
|---|---|
| membership_pk | 内部主键 |
| membership_id | NGIQ-CCM-… |
| circuit_id | 指向 circuits |
| connection_id | 指向 connections |
| step_order | 步骤顺序 |
| branch_group | 分支组 |
| role_en / role_zh | 角色 |
| is_required | 是否必需 |
| is_core_connection | 是否核心连接 |
| membership_confidence | 成员置信度 |
| remark | 备注 |

> 同一 Connection 可属于多个 Circuit，且 step_order / role 不同，故用 reified membership 表，不把顺序塞进 Connection 主表。
