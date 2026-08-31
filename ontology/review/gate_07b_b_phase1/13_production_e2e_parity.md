# Gate 7B-B Phase 1 — Production / E2E Parity

## 1. 要求（§29/§30）

同一个 `gate7b_002_identity_foundation.sql` 分别应用，schema 必须一致；禁止 E2E 专用简化表。

## 2. 实现

`test_production_e2e_schema_parity` 自动抽取 4 张表的：

- columns（name / data_type / is_nullable / column_default）
- constraints（contype / conname / pg_get_constraintdef）
- indexes（indexname / indexdef）

比较 production 与 E2E 的签名。

## 3. 结果

```
test_production_e2e_schema_parity PASSED
```

- production：`['entity_aliases','entity_xrefs','kg_entities','sources']`，29 infra seqs。
- E2E：`['entity_aliases','entity_xrefs','kg_entities','sources']`，29 infra seqs。
- 签名完全一致（column_default 中的 BIGSERIAL sequence 名也一致，因为同一迁移生成）。

## 4. 结论

Production / E2E 完全一致；无 E2E 专用简化表。
