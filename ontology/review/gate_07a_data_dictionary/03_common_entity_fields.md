# Gate 7A — Common Entity Fields（统一展示字段）

本轮状态: **仅设计文档**

---

## 1. kg_entities：canonical entity identity layer

所有主要实体在 `kg_entities` 有统一身份记录。

| 字段 | 说明 |
|---|---|
| pk | 内部主键 |
| entity_id | `NGIQ-…` public ID |
| entity_type | 实体类型（brain_region / gene / disease …） |
| name_en / name_zh | 英文名 / 中文名 |
| abbreviation | 缩写 |
| definition_en / definition_zh | 定义 |
| description_en / description_zh | 描述 |
| source_name_original | 原始来源名称 |
| source_language | 来源语言 |
| name_en_source | 英文名来源 |
| name_zh_source | 中文名来源 |
| translation_review_status | 翻译审核状态 |
| record_status | 记录状态（active/deprecated/merged…） |
| review_status | 审核状态 |
| version | 版本 |
| created_at / updated_at | 时间戳 |
| created_by_agent / updated_by_agent | 操作者/Agent |
| metadata_json | 元数据 JSON |
| remark | 备注 |

## 1b. kg_entities = 唯一 Identity Truth（Final Correction）

- kg_entities 是所有 first-class canonical entity 的 identity / public ID / display name / definition / description / lifecycle status 的**唯一来源**。
- **Subtype 表禁止独立维护第二套 name/definition/description truth**（从 subtype 表删除，或标 DERIVED DISPLAY CACHE；优先删除）。
- 推荐 **shared-PK（Class Table Inheritance）**：`kg_entities.entity_pk` 同时作为 subtype 表 PK/FK，subtype 表不另生成 `*_pk`。
- first-class / user-visible 实体进 kg_entities；技术 link 记录（connection_endpoints、assertion_evidence_links）不要求完整 identity（仅 PK + public ID + FK + 结构字段 + remark）。

## 2. Name Source 必须区分（禁止 AI 翻译伪装官方名）

| name source | 含义 |
|---|---|
| source | 来自原始来源官方名 |
| human_curated | 人工整理 |
| translated_human | 人工翻译 |
| translated_ai | AI 翻译 |
| normalized | 规范化 |
| unknown | 未知 |

例（Julich）：
- `source_name_original = Area hOc1`
- `name_en = Area hOc1`，`name_en_source = source`
- `name_zh = hOc1 区`，`name_zh_source = translated_ai`

前端可明确区分：官方来源名称 vs 系统翻译名称。

## 3. remark 统一原则

- 所有主要业务表含 `remark TEXT NULL`，默认 `NULL`。
- 禁止用 `''` / `N/A` / `none` / `暂无` 作默认值。
- remark 只用于：人工补充说明、例外情况、暂时无法结构化的信息。
- remark 不能代替正式结构化字段。

## 4. 时间戳/审计字段

- `created_at` / `updated_at`（TIMESTAMPTZ）。
- `created_by` / `updated_by`（操作者，可为自动 pipeline id）。
- 所有自动生成内容必须保留 provenance（来源字段 + 生成方式 + 版本）。
