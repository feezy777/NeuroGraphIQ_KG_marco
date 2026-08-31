# Gate 7B-B Phase 2A — Risk Register

## 1. BLOCKER = 0

## 2. 已消解的设计决策（本轮裁决，非 blocker）

| 决策点 | 裁决 | 依据 |
|---|---|---|
| subtype 外部 ID（hgnc/mondo/hpo/chebi/ncbi/ensembl/uniprot/iuphar） | 从 subtype 移除，统一进 entity_xrefs | Phase 2A 指令 §10 |
| brain_regions.granularity 字段名/词表 | 用 `granularity_level` + G1–G4（弃 dict §5 的 `granularity` macro/meso/fine/unknown） | 指令 §7 + 冻结 granularity framework（16 §7/27/23 §O） |
| genes.approved_symbol / hgnc_status | 保留为基因特有属性（非外部 ID 复制） | dict §16 明确字段 + 指令 §10 例外 |
| parent_region_pk / parent_function_pk | DERIVED cache 保留（ON DELETE SET NULL），不建 hierarchy 表 | dict 标记 DR + 指令 §7/§8 |
| 共享 identity 字段（name/status/timestamps） | subtype 不重复 | Gate 7A §D + 指令 §6 |

## 3. MODERATE

- dict 18 §5 的 `granularity` 旧字段与 `granularity_level` 存在命名漂移（已裁决用 granularity_level；建议后续 Gate 7A 文档同步删除旧 `granularity` 行，避免未来混淆）。属文档层，非 schema 冲突。

## 4. 无 MAJOR

## 5. 边界（本轮未做）

- 未建 Gene ontology / Disease ontology / Receptor pharmacology / Gene-Disease 等 relation 层（Phase 后续）。
- 未迁 legacy / Macro96 / Brainnetome / Julich / HGNC 数据。
- 未生成测试外真实数据（仅 E2E rollback 测试）。
