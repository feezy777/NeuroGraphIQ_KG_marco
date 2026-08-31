# Gate 7B-B Phase 2B — Schema Parity & Tests

## 1. Production / E2E parity

- `test_production_e2e_schema_parity`：18 张表 columns / constraints / indexes 签名一致。
- 同一 `gate7b_004` 分别应用两库。

## 2. Table count

- production / E2E：**18/32**。
- 新增恰为：research_studies, publications, evidence, atlases, external_regions。
- 无 Phase 3+ leak（hierarchy/spatial/aggregation/connection/circuit/mapping/assertion/evidence_links 均不存在）。

## 3. Clean replay 001 → 002 → 003 → 004

- 临时库全量重放：tables / columns / constraints / indexes 与 production **MATCH**，infra sequences 29 = 29。
- 已删除临时库。

## 4. Runner 幂等

- production / E2E 二次运行 → 4 条 `skip`（gate7b_001–004 all applied）。

## 5. 全量测试

```
84 passed, 1 warning
```

- Phase 2B：16（新增 `test_gate7b_phase2b_evidence_atlas.py`）
- Phase 2A：15（`test_table_count_is_thirteen` → `test_phase2a_thirteen_tables_present` 子集断言；`test_no_phase2b_table_leak` → `test_no_phase3_table_leak` 收敛到 Phase 3+ 列表）
- Phase 1 / Phase 0 / guard / admin：其余

## 6. 不变项

- legacy `neurographiq_kg_v3_wb`：34 张 public 表，无 write / 无迁移。
- ontology TTL hash：`37e0e3af…` 未改。
