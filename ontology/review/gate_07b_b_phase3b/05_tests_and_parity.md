# Gate 7B-B Phase 3B — Tests & Parity

## 1. Production / E2E parity

- `test_production_e2e_schema_parity`：25 张表 columns / constraints / indexes 签名一致。
- 同一 `gate7b_006` 分别应用两库。

## 2. Table count

- production / E2E：**25/32**。
- 新增恰为 3 张（connections / connection_endpoints / connection_observations）。
- 无 Circuit/Assertion leak（circuits / circuit_* / region_mappings / relation_definitions / knowledge_assertions / evidence_links 均不存在）。
- 无 direct-edge canonical duplication（无 brain_region_direct_connections / projects_to / structural_edges / functional_edges）。

## 3. Clean replay 001 → 006

- 临时库全量重放：tables / columns / constraints / indexes / **sequences(31)** / **functions** / **triggers(18)** 与 production 全 MATCH。
- 已删除临时库。

## 4. Runner 幂等

- production / E2E 二次运行 → 6 条 `skip`（gate7b_001–006 all applied）。

## 5. 全量测试

```
126 passed, 1 warning
```

- Phase 3B connection：19（新增 `test_gate7b_phase3b_connection.py`）
- Phase 3A：22（`test_table_count_is_twenty_two` → `test_phase3a_twenty_two_tables_present` 子集断言；leak 列表收敛到 Circuit+）
- Phase 2A/2B：leak 列表收敛到 Circuit+
- Phase 1 / Phase 0 / guard / admin：其余

## 6. 不变项

- legacy `neurographiq_kg_v3_wb`：34 张 public 表，无 write / 无迁移。
- ontology TTL hash：`37e0e3af…` 未改。
