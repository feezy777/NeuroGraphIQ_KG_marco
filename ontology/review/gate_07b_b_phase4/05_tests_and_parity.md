# Gate 7B-B Phase 4 — Tests & Parity

## 1. Production / E2E parity

- `test_production_e2e_schema_parity`：28 张表 columns / constraints / indexes 签名一致。
- 同一 `gate7b_007` 分别应用两库。

## 2. Table count

- production / E2E：**28/32**。
- 新增恰为 3 张（circuits / circuit_region_memberships / circuit_connection_memberships）。
- 无 RegionMapping/Assertion leak（region_mappings / relation_definitions / knowledge_assertions / evidence_links 均不存在）。

## 3. Clean replay 001 → 007

- 临时库全量重放：tables / columns / constraints / indexes / **sequences(31)** / **functions** / **triggers(20)** 与 production 全 MATCH。
- 已删除临时库。

## 4. Runner 幂等

- production / E2E 二次运行 → 7 条 `skip`（gate7b_001–007 all applied）。

## 5. 全量测试

```
144 passed, 1 warning
```

- Phase 4 circuit：18（新增 `test_gate7b_phase4_circuit.py`）
- Phase 3B：18（`test_table_count_is_twenty_five` → `test_phase3b_twenty_five_tables_present` 子集断言；leak 收敛到 RegionMapping/Assertion）
- Phase 3A / 2B / 2A：leak 列表收敛到 RegionMapping/Assertion
- Phase 1 / Phase 0 / guard / admin：其余

## 6. 不变项

- legacy `neurographiq_kg_v3_wb`：34 张 public 表，无 write / 无迁移。
- ontology TTL hash：`37e0e3af…` 未改。
