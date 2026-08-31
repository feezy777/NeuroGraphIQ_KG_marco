# Gate 7B-B Phase 1 — Identity Architecture

## 1. kg_entities = 唯一 Identity Truth

`kg_entities` 是所有 first-class canonical entity 的 identity / public ID / display name / definition / description / lifecycle status 的**唯一来源**。

未来 BrainRegion / Connection / Circuit / Function / Gene / Disease / Evidence / RegionMapping … 都通过 `kg_entities.entity_pk` 获得统一内部身份。

## 2. shared-PK（Class Table Inheritance）

- `kg_entities.entity_pk`（BIGSERIAL）是全局内部主键。
- 未来 subtype 表**复用** `entity_pk` 作为自己的 PK/FK，**不另生成 `*_pk`**、不重复 name/definition/description truth。
- 例（§E 冻结）：`kg_entities.entity_pk=101（entity_id=NGIQ-BR-00000001）↔ brain_regions.entity_pk=101`。

## 3. 内部身份 vs 公开身份（两套计数，独立）

| 字段 | 语义 | 来源 |
|---|---|---|
| `entity_pk` | 内部 BIGINT 主键（全局唯一） | 全局 BIGSERIAL |
| `entity_id` | 公开 `NGIQ-<TYPE>-<8位>` | per-type sequence |

> 关键：`entity_pk` 是全局递增计数（例 101），`entity_id` 的数字部分是 per-type 计数（例 00000001 = 第 1 个 brain_region）。二者**独立**，不互相编码。

## 4. FK 引用规则（§E 冻结）

所有 FK 引用内部 `*_pk`，**不引用** public `*_id`：

- `entity_aliases.entity_pk → kg_entities.entity_pk`
- `entity_xrefs.entity_pk → kg_entities.entity_pk`
- `entity_aliases.source_pk → sources.source_pk`

## 5. sources 独立（不进 kg_entities）

`sources` 是独立 registry（`source_pk BIGSERIAL`），**不** shared-PK。见 `06_sources_schema.md`。

## 6. 不发第二套 identity

- subtype 表禁止再独立生成第二套 canonical identity / public ID。
- 禁止 UUID 作为第二 canonical ID。
- 禁止 `MAX(id)+1`。
