# Gate 7B-B Phase 3A — Tests & Parity

## 1. Production / E2E parity

- `test_production_e2e_schema_parity`：22 张表 columns / constraints / indexes 签名一致。
- 同一 `gate7b_005` 分别应用两库。

## 2. Table count

- production / E2E：**22/32**。
- 新增恰为 4 张（BRH / FHR / Spatial / Aggregation）。
- 无 Phase 3B+ leak（connections/circuits/region_mappings/assertion/evidence_links 均不存在）。

## 3. Clean replay 001 → 005

- 临时库全量重放：tables / columns / constraints / indexes 与 production **MATCH**。
- infra sequences 30 = 30（新增 `infra.ngiq_spat_seq`）。
- 已删除临时库。

## 4. Runner 幂等

- production / E2E 二次运行 → 5 条 `skip`（gate7b_001–005 all applied）。

## 5. 全量测试

```
107 passed, 1 warning
```

- Phase 3A：23（新增 `test_gate7b_phase3a_hierarchy_spatial.py`）
- Phase 2B：15（`test_table_count_is_eighteen` → `test_phase2b_eighteen_tables_present` 子集断言；`PHASE3_TABLES` → `PHASE3B_TABLES` 收敛）
- Phase 2A：14（`PHASE3_TABLES` → `PHASE3B_TABLES` 收敛）
- Phase 1 / Phase 0 / guard / admin：其余

## 6. 不变项

- legacy `neurographiq_kg_v3_wb`：34 张 public 表，无 write / 无迁移。
- ontology TTL hash：`37e0e3af…` 未改。
