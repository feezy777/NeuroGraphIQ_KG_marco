# Gate 7A RegionMapping mapping_type Amendment（简短 change note）

## 目的

统一 `region_mappings.mapping_type` 词表为人工验收通过的 **7 values**，消除 dict 中残留的 6-value 旧表达。

## 正式冻结 vocabulary（7 values）

```
exact / close / broader / narrower / related / overlapping / unresolved
```

- **`related` 正式纳入**：表示存在可靠映射关联，但不足以归入 exact / close / broader / narrower / overlapping 的保守关系。
- **`related ≠ overlapping`**：related = 一般关联；overlapping = 空间重叠。
- **`unresolved` 保留**：歧义/未消解映射。
- **gate7b_008 数据库实现无需修改**（`ck_rm_mapping_type` 已含 related 7 值，与冻结一致）。

## 修改文件

- `18_complete_data_dictionary.md` §26（region_mappings.mapping_type → 7 values）
- `12_atlas_external_region_mapping_tables.md`（mapping_type → 7 values）
- `16_controlled_vocabularies.md` §1 原本已是 7 values（无需改）

## 未修改

ontology TTL / migration / database / legacy。
