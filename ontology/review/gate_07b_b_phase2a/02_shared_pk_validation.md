# Gate 7B-B Phase 2A — Shared-PK & entity_type Consistency

## 1. shared-PK 落地

- 9 张表均 `entity_pk BIGINT PRIMARY KEY REFERENCES kg_entities(entity_pk) ON DELETE RESTRICT`。
- 无第二 public ID / 独立 serial PK / 重复 name（测试 `test_subtype_tables_are_shared_pk_no_second_identity` 覆盖全部 9 表）。

## 2. entity_type 一致性（集中式守卫）

单一 PL/pgSQL 函数 + 9 个一行触发器，不在各表复制逻辑：

```
infra.assert_entity_type()            -- 共享守卫函数（RAISE EXCEPTION, fail closed）
trg_<table>_entity_type               -- 9 个 BEFORE INSERT 触发器，TG_ARGV[0]=期望类型
```

行为：
- `entity_pk` 不存在于 kg_entities → `RAISE EXCEPTION`。
- `entity_pk` 存在但 entity_type 与表不符 → `RAISE EXCEPTION`（如 gene 插 brain_regions）。

触发器清单：trg_brain_regions_entity_type / trg_cns_entity_type / trg_nbp_entity_type / trg_functions_entity_type / trg_neurotransmitters_entity_type / trg_receptors_entity_type / trg_genes_entity_type / trg_diseases_entity_type / trg_symptoms_entity_type。

## 3. FK delete 策略

- subtype → kg_entities：**RESTRICT**（禁止物理删除有 subtype 行的 canonical entity，保 lineage）。
- subtype 内部 DERIVED cache 父引用（parent_region_pk / parent_function_pk）：`ON DELETE SET NULL`（cache 语义，不 cascade、不 block）。

## 4. 测试覆盖

- `test_shared_pk_fk_accepts_existing_entity`：合法 entity_pk 可插入。
- `test_orphan_subtype_rejected`：不存在的 entity_pk → 拒绝。
- `test_correct_entity_type_inserts_for_all_subtypes`：9 类正确类型全部可插入。
- `test_wrong_entity_type_rejected`：gene 实体插 brain_regions → 拒绝。
- `test_centralized_entity_type_guard_exists`：守卫函数含 RAISE EXCEPTION + TG_ARGV。
- `test_subtype_delete_keeps_kg_entity`：删 subtype 行不影响 kg_entities。
- `test_delete_entity_with_subtype_is_restricted`：删 kg_entity 带 subtype → RESTRICT。
