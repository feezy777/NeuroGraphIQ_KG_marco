# Gate 6E-A — Database Alignment Audit

本轮状态: **仅审计，不修改 Gate 7A**

---

## 1. 已冻结的 32 表相关部分

| 表 | 角色 |
|---|---|
| knowledge_assertions | 普通 relation assertion（subject/predicate/object） |
| relation_definitions | 谓词 vocabulary |
| assertion_evidence_links | Evidence ↔ Assertion（evidence_role/strength/directness） |
| evidence | 证据单元 |
| connection_observations | Connection 观测层（可 reference evidence） |
| connections / circuits | reified entity |
| circuit_region_memberships / circuit_connection_memberships | 成员 |

## 2. 审计结论

| 需求 | 现状 | 判定 |
|---|---|---|
| 普通 assertion 挂 Evidence | assertion_evidence_links | ✅ 满足 |
| Connection 挂 Evidence | connection_observations（可 ref evidence） | ✅ 基本满足 |
| Circuit 挂 Evidence | **无直接路径**（无 circuit_evidence_links） | ⚠️ gap |
| RegionMapping 挂 Evidence | evidence_summary（字段级） | ⚠️ 弱 |
| inferred provenance | provenance_json / InferenceRecord | ✅ 基本满足 |

## 3. 是否 blocking

- **非 blocking**（Gate 6E-B 才正式化 Evidence/Assertion model；当前 TTL 未写 supports/contradicts）。
- 但 Circuit → Evidence 无直接可追踪路径，是**真实缺口**，需在 Gate 6E-B 前提出最小修订建议。

## 4. 最小修订建议（不修改 Gate 7A，仅建议）

- 建议 Gate 6E-B 增加一个统一 evidence link 层：`assertion_evidence_links` 扩展 target 为「Assertion OR reified entity（Connection/Circuit/RegionMapping）」；或新增 `entity_evidence_links`（target_type + target_id + evidence_id + evidence_role + strength + directness）。
- 这样 reified entity 与 ordinary assertion 共用同一套 evidence_role 语义。
