# Gate 7A Evidence Context Field Amendment（简短 change note）

## 目的

清除 Gate 7A CURRENT 数据字典中 `evidence` 表的 `evidence_directness` / `evidence_strength` 历史残留，与冻结语义 §I / Phase 2B 实现一致。

## 修订内容

- **`evidence_directness` 从 evidence 定义移除**（不再作为 Evidence 全局属性）。
- **`evidence_strength` 从 evidence 定义移除**（确认不属于 Evidence 固有全局属性）。
- 二者为 **Evidence ↔ target** 的关联上下文，未来位于 **`evidence_links`**（target-specific）。
- **`model_confidence` 保持独立**（模型/抽取器置信度，≠ evidence_strength）。
- **数据库 `gate7b_004` 当前实现无需修改**（evidence 表本就不含这两个字段，符合冻结设计）。

## 修改文件

- `18_complete_data_dictionary.md`：evidence §23 删除 evidence_directness / evidence_strength 两行；evidence_links §29 的 target-specific 版本保持不变。
- `16_controlled_vocabularies.md`：evidence_directness / evidence_strength 词表标注为 evidence_links target-specific context。

## 未修改

ontology TTL / migration / database / tests / legacy / Phase 3。
