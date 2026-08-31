# Gate 7B-B Phase 3B — Scope & Schema

## 1. 本轮范围

创建 3 张 Connection 科学表（22/32 → 25/32）。

| # | 表 | 角色 |
|---|---|---|
| 1 | connections | first-class reified Connection（shared-PK） |
| 2 | connection_endpoints | canonical endpoint truth（connection ↔ brain_region + role） |
| 3 | connection_observations | 某项 Study 对某 Connection 的结构化观测 |

## 2. 未创建（Circuit/Assertion 后续）

circuits / circuit_region_memberships / circuit_connection_memberships / region_mappings / relation_definitions / knowledge_assertions / evidence_links。

## 3. 建模

- **connections** = shared-PK subtype：`entity_pk BIGINT PK → kg_entities(entity_pk)`，entity_type='connection'。
- **connection_endpoints** / **connection_observations** = link/reified 表（非 kg_entities subtype），各自 `*_pk BIGSERIAL` + NGIQ `*_id`：
  - endpoint_id：NGIQ-EP-…（新增 `infra.ngiq_ep_seq`，registry 30→31）
  - observation_id：NGIQ-COB-…（`infra.ngiq_cob_seq`，registry 既有 COB）

## 4. 关键 FK

| 表 | FK |
|---|---|
| connections | entity_pk → kg_entities（RESTRICT） |
| connection_endpoints | connection_pk → connections.entity_pk；brain_region_pk → brain_regions.entity_pk（RESTRICT） |
| connection_observations | connection_pk → connections.entity_pk；study_pk → research_studies；publication_pk → publications；evidence_pk → evidence（RESTRICT） |

## 5. 边界（本轮落实）

- **connections 不重复保存 source/target region FK**（canonical endpoint truth 只在 connection_endpoints）。
- 未建 direct BrainRegion edge canonical table（structurallyConnectedTo 等为 projection，非 truth）。
- 未实现 Connection roll-up / hierarchical_rollup / intra_region_collapsed_connection。
- 未迁 legacy（kg_connections / mirror / Macro connection / molecular_attr connection）。

## 6. migration

`backend/migrations/gate7b_006_connection_core.sql`，同一文件应用于 production 与 E2E。
