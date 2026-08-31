# Gate 7B-B Phase 1 — Name Lifecycle Constraints

## 1. 冻结词表（record_status / name source）

- `record_status`：**proposed / active / deprecated / merged**（小写 4 值；本轮修订：与 NeuroGraphIQ Governance 的 proposed→active 语义统一，替换 Gate 7A 16 §1 旧值 `pending`）。
- name source：source / human_curated / translated_human / translated_ai / normalized / unknown。

## 2. 冻结双语显示策略（§F）映射到约束

| 状态 | 规则 | DB 实现 |
|---|---|---|
| active | name_en + name_zh 非空 + 可追踪 name source | `ck_kg_entities_active_bilingual`（active → name_en AND name_zh NOT NULL）+ `ck_kg_entities_active_name_source`（active → 双 source 非空且非 unknown） |
| proposed（= §F 的 PROPOSED） | 允许 name_en/name_zh 其一暂缺，但至少其一存在且 source_name_original 非空 | `ck_kg_entities_proposed_has_name`（proposed → name_en 或 name_zh 至少其一）+ `ck_kg_entities_proposed_source`（proposed → source_name_original NOT NULL） |

## 3. 说明

- `name_en` 由基础 NOT NULL → 允许 NULL（本轮修订）：消除与 §F「PROPOSED 可暂缺一种语言」的冲突；ACTIVE 双语改由 `ck_kg_entities_active_bilingual` 显式保证（name_en 与 name_zh 均非空）。
- `SOURCE_UNKNOWN 不得直接 ACTIVE`：通过 `name_en_source/name_zh_source <> 'unknown'` 的 active CHECK 实现。

## 4. 边界（§33）

- DB CHECK 只承载**确定性存在/词表规则**（name 存在性、status ∈ 词表、source ≠ unknown）。
- **不**用 DB CHECK 判「翻译质量 / 来源是否权威」——那是应用层 policy。

## 5. 测试覆盖

- PROPOSED（proposed）单语 + source_name_original 合法 → pass。
- PROPOSED 仅中文（name_en 缺）+ source_name_original → pass（本轮修复点）。
- active 缺 name_zh → CHECK violation。
- active 缺 name_en → CHECK violation。
- active + unknown source → CHECK violation。
- proposed 缺 source_name_original → CHECK violation。
- proposed name_en/name_zh 均缺 → CHECK violation。
