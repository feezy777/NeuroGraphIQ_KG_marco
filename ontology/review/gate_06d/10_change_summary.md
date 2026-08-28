# Gate 6D — Change Summary（Function Hierarchy Ontology）

Ontology IRI: `https://neurographiq.org/ontology/human-brain`
version: `0.6.1-gate6c` → `0.6.2-gate6d`

---

## 1. 新增 1 个 ObjectProperty

- `subFunctionOf`（Function → Function，ABox semantic hierarchy，CANONICAL）。

## 2. 版本/统计

| 项 | 旧 | 新 |
|---|---|---|
| version | 0.6.1-gate6c | 0.6.2-gate6d |
| ObjectProperty | 25 | 26 |
| Named Class | 23 | 23 |
| DataProperty | 0 | 0 |
| Named Individual | 0 | 0 |
| imports | 0 | 0 |

## 3. 未做

- 未新增 Function Individual / DataProperty / Class。
- 未新增 Function part_of 正式 OWL relation（DEFER）。
- 未设置 TransitiveProperty / inverseOf / property chain。
- 未修改 BrainRegion partOf/subfieldOf 或 Gate 7A Data Dictionary。

## 4. Git（冻结提交）

- 提交 `8564a77 冻结人脑颗粒度数据字典与脑区层级本体`（Gate 6C + Gate 7A 冻结结果，38 文件，已 push origin/main）。
- Gate 6D 本体变更（subFunctionOf）**未 commit / 未 push**，等待 Protégé 审查。
