# Gate 7B-B Phase 1 — Risk Register

## 1. BLOCKER = 0

## 2. 已消解的文档内部冲突（本轮按冻结权威裁决，非 blocker）

| 冲突 | 权威依据 | 裁决 |
|---|---|---|
| `sources.source_type` 是否含 `llm`（18 §4 有 / 16 §5、04 §5、23 §K 无） | 16 §5 Final Correction + §K「删除 llm」 | **无 llm**（7 值） |
| kg_entities PK 列名 `pk` vs `entity_pk` | 23 §E + Final Correction | **entity_pk** |
| `created_by` vs `created_by_agent` | 23 §D + 03 §1 | **created_by_agent** |
| `review_status` 是否保留（18/03 有，23 §D 节略） | 18 §1 完整字典 + 16 §1 词表 | **保留** |
| name_en「PROPOSED 允许暂缺」vs name_en NN | 18 §1 name_en NN | **name_en 永 NN**，仅 name_zh 可空 |

## 3. 记录为后续 requirement（本轮未实现）

- `merged_into` / redirect 字段：冻结 Gate 7A 未落字段，本轮不自行新增 merge 表。
- alias 应用层去重策略：DB 层无硬 UNIQUE（冻结 dictionary 未定义），写入前查重留给应用层。
- sources 缺 `created_at/updated_at`：冻结 dictionary 未定义，遵循现状（`last_checked_at` 承担审计职责）。

## 4. MODERATE / MAJOR

- MODERATE：`core.autocrlf=true` 会导致工作区迁移文件换行漂移 → 已通过 runner checksum 归一化修复；建议未来加 `.gitattributes`（`*.sql text eol=lf`）根治（本轮未做，避免越界改动）。
- 无 MAJOR。
