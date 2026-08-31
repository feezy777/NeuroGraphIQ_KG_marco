# Gate 7A Circuit Connection Membership Identity Amendment（简短 change note）

## 目的

将 `circuit_connection_memberships` 的表达统一为共享身份（shared-PK），与冻结首类模型一致。

## 修订内容

### 1. circuit_connection_memberships = shared-PK（正式 CURRENT）

- `entity_pk BIGINT PK → kg_entities(entity_pk)`，`entity_type = circuit_connection_membership`。
- public NGIQ ID = `kg_entities.entity_id`（NGIQ-CCM）。
- **无**独立 `membership_pk` / `membership_id`。
- 原因：CircuitConnectionMembership 是 first-class reified scientific object、Ontology Core 正式 Class、Evidence direct entity target whitelist 成员，需要稳定 public NGIQ identity。
- 修改文件：`18_complete_data_dictionary.md` §12、`07_circuit_tables.md` §3（旧 `membership_pk BIGSERIAL` 表达修正为 shared-PK）。

### 2. circuit_region_memberships 保持 link 表

- `membership_pk BIGSERIAL` + `membership_id NGIQ-CRM`（entity_type 词表未含 circuit_region_membership）。

### 3. CircuitRegionMembership UNIQUE = V1 modeling policy

- `UNIQUE(circuit_pk, brain_region_pk)` 继续生效。
- 正式解释：同一 canonical BrainRegion 在同一 Circuit 中当前只保留一条 canonical region membership。
- 这是 **V1 modeling policy**，**不是**对神经科学"一个脑区只能有一个功能角色"的声明。若未来需要多角色 membership，通过版本化 schema change 扩展。

### 4. circuits.granularity_scope = DERIVED

- 正式角色 **DERIVED**：由 Circuit 的 region memberships + BrainRegion.granularity_level + 必要 mapping context 推导。
- **不**是独立 canonical truth，不得与 BrainRegion granularity 并列。

## 未修改

gate7b_007 migration / database / ontology TTL / legacy。
