# Gate 7B-B Phase 5 — Tests & Parity

## 1. Production / E2E parity

- `test_production_e2e_schema_parity`：**32 张表** columns / constraints / indexes 签名一致。
- 同一 `gate7b_008` 分别应用两库。

## 2. Table count = 32/32（恰好）

- `test_table_count_is_thirty_two_exact`：public tables == 32 且名称精确匹配。
- `test_no_33rd_table`：无 assertion_evidence_links / brain_region_spatial_relations / connection_types / circuit_types / evidence_types；总数 = 32。

## 3. Clean replay 001 → 008

- 临时库全量重放：tables / columns / constraints / indexes / **sequences(31)** / **functions** / **triggers(22)** 与 production 全 MATCH。
- 已删除临时库。

## 4. Runner 幂等

- production / E2E 二次运行 → 8 条 `skip`（gate7b_001–008 all applied）。

## 5. 全量测试

```
166 passed, 1 warning
```

- Phase 5：22（新增 `test_gate7b_phase5_mapping_assertion.py`）
- Phase 4：17（`test_table_count_is_twenty_eight` → `test_phase4_twenty_eight_tables_present` 子集断言；leak 收敛到 forbidden set）
- Phase 3B / 3A / 2B / 2A：leak 收敛到 forbidden set（assertion_evidence_links 等永不创建的表）
- Phase 1 / Phase 0 / guard / admin：其余

## 6. 不变项

- legacy `neurographiq_kg_v3_wb`：34 张 public 表，无 write / 无迁移。
- ontology TTL hash：`37e0e3af…` 未改。
