# Gate 7B-B Phase 4 — Scope & Schema

## 1. 本轮范围

创建 3 张 Circuit 科学表（25/32 → 28/32）。

| # | 表 | 角色 |
|---|---|---|
| 1 | circuits | first-class reified Circuit（shared-PK） |
| 2 | circuit_region_memberships | Circuit 包含哪些 BrainRegion（link 表，NGIQ-CRM） |
| 3 | circuit_connection_memberships | Circuit 包含哪些 canonical Connection（**shared-PK first-class**） |

## 2. 未创建（RegionMapping/Assertion 后续）

region_mappings / relation_definitions / knowledge_assertions / evidence_links。

## 3. 建模

- **circuits** = shared-PK subtype：`entity_pk → kg_entities(entity_pk)`，entity_type='circuit'，public ID = kg_entities.entity_id（NGIQ-CIR）。
- **circuit_region_memberships** = link 表：`membership_pk BIGSERIAL` + `membership_id NGIQ-CRM`（infra.ngiq_crm_seq）。
- **circuit_connection_memberships** = **shared-PK first-class**：`entity_pk → kg_entities(entity_pk)`，entity_type='circuit_connection_membership'，public ID = kg_entities.entity_id（NGIQ-CCM）。依据见 04。

## 4. 关键 FK

| 表 | FK |
|---|---|
| circuits | entity_pk → kg_entities（RESTRICT） |
| circuit_region_memberships | circuit_pk → circuits.entity_pk；brain_region_pk → brain_regions.entity_pk |
| circuit_connection_memberships | entity_pk → kg_entities；circuit_pk → circuits.entity_pk；connection_pk → connections.entity_pk |

## 5. 边界（本轮落实）

- Circuit = biological/functional circuit，非 graph cycle：无 closed_loop 硬要求、无 ≥3 regions/≥2 connections 硬约束。
- Circuit 不自动从 graph cycle 生成；不自动生成缺失 Connection。
- 未迁 legacy（coarse_circuits / circuit_steps / mirror / molecular_attr circuits / 旧候选）。
- 未创建第二套 circuit→connection canonical truth 表。

## 6. migration

`backend/migrations/gate7b_007_circuit_core.sql`，同一文件应用于 production 与 E2E。
