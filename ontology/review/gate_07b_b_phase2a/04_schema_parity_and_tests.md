# Gate 7B-B Phase 2A — Schema Parity & Tests

## 1. Production / E2E parity

- `test_production_e2e_schema_parity`：13 张表（4 Identity + 9 subtype）的 columns / constraints / indexes 签名一致。
- 同一 `gate7b_003` 分别应用两库。

## 2. Table count

- production：13/32，E2E：13/32。
- 恰为：kg_entities, entity_aliases, entity_xrefs, sources + 9 subtype。
- 无 Phase 2B/3+ leak（atlases/evidence/connections/circuits/… 均不存在）。

## 3. Clean replay 001 → 002 → 003

- 临时库 `neurographiq_human_brain_v1_replay` 全量重放：
  - tables / columns / constraints / indexes 与 production MATCH。
  - infra sequences 29 = 29。
  - 9 个 entity_type 触发器 MATCH。
- 已删除临时库。

## 4. Migration runner 幂等

- 二次运行 production / E2E → 3 条 `skip`（gate7b_001/002/003 all applied）。

## 5. 全量测试

```
68 passed, 1 warning
```

- Phase 2A scientific：15（新增文件 `test_gate7b_phase2a_scientific.py`）
- Phase 1 identity：25（其中 `test_table_count_is_exactly_four` → `test_identity_four_tables_present`，改为子集断言，适配 13 表）
- Phase 0 + guard/admin：其余

## 6. 不变项

- legacy `neurographiq_kg_v3_wb`：34 张 public 表，无 write / 无迁移。
- ontology TTL hash：`37e0e3af…` 未改。
