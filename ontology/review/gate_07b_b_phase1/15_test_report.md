# Gate 7B-B Phase 1 — Test Report

## 1. 新增测试

`backend/tests/test_gate7b_phase1_identity.py`（25 用例）

| 覆盖 | 用例 |
|---|---|
| schema parity | test_production_e2e_schema_parity |
| table count | test_table_count_is_exactly_four |
| ID 格式 | test_ngiq_id_format_is_8_digit |
| 未知类型 fail-closed | test_ngiq_id_unknown_type_fails_closed |
| 8 位容量守卫 | test_ngiq_id_capacity_guard_present |
| 非 MAX+1 | test_sequence_not_max_plus_one |
| 并发 distinct | test_ngiq_id_two_connections_distinct |
| PROPOSED 单语 | test_create_proposed_single_language_entity |
| entity_id 唯一 | test_entity_id_unique |
| shared-PK 全局 | test_shared_pk_is_global_serial |
| 未知 entity_type | test_unknown_entity_type_rejected |
| record_status 词表 | test_record_status_vocabulary |
| active bilingual | test_active_requires_bilingual |
| active 缺 name_en | test_active_requires_name_en |
| PROPOSED 仅中文 OK | test_proposed_chinese_only_name_ok |
| PROPOSED 双名均缺 | test_proposed_requires_at_least_one_name |
| SOURCE_UNKNOWN 禁 active | test_source_unknown_cannot_be_active |
| proposed source | test_proposed_requires_source_name |
| alias FK 有效 | test_alias_fk_valid |
| alias FK 无效 | test_alias_invalid_entity_pk_rejected |
| xref FK 有效 | test_xref_fk_valid |
| xref 去重 | test_xref_duplicate_resolved_rejected_unresolved_allowed |
| 科学 source 合法 | test_scientific_source_valid |
| llm 非 source | test_llm_not_a_scientific_source |
| DELETE RESTRICT | test_delete_entity_with_alias_is_restricted |

## 2. 全量结果

```
53 passed, 1 warning
```

- Phase 1 identity：25
- Phase 0（含 runner sha256 归一化）：12
- guard / admin：其余

## 3. warning 说明

1 条 warning 为既有 DB 写测试门禁提示（默认 .env 指向主库 `human_brain_v1`，门禁按设计提示「非隔离测试库」）。Phase 1 测试直连 E2E，写操作在事务内回滚，不污染数据。

## 4. E2E 写测试的数据安全

- 写测试在事务内回滚（fixture `db` teardown rollback）。
- sequence 推进是设计内永久副作用（无害，编号跳过不连续）。
