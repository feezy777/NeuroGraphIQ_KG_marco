# Gate 7A — Field Role & Frontend Display（字段角色与前端展示）

本轮状态: **仅设计文档**

---

## 1. Field Role（字段角色）

| Role | 含义 | 示例 |
|---|---|---|
| IDENTITY | 标识字段 | entity_id、connection_id |
| SCIENTIFIC | 科学事实（canonical truth） | connection_class、directionality、source_region_id |
| DISPLAY | 展示缓存 | name_zh、display_name_zh |
| DERIVED | 派生统计（非 truth） | evidence_count、latest_evidence_year |
| PROVENANCE | 溯源 | derivation_type、extractor_name、source_id |
| GOVERNANCE | 治理 | review_status、reviewer、canonical_status |
| TECHNICAL | 技术字段 | pk、created_at、updated_by |

## 2. Frontend Display（前端展示）

| 级别 | 含义 |
|---|---|
| PRIMARY | 列表/卡片主展示 |
| DETAIL | 详情页展示 |
| ADVANCED | 高级/折叠面板展示 |
| HIDDEN | 不展示（内部字段） |

例（BrainRegion）：
- PRIMARY：entity_id、name_en、name_zh、abbreviation
- DETAIL：hemisphere、granularity_level、region_category、definition、description
- ADVANCED：source、mapping、hierarchy、metadata
- HIDDEN：internal PK、created_by、technical 字段

## 3. 事实 vs 派生 vs 治理的区分（防重复）

- `connection.evidence_count / publication_count / latest_evidence_year` = **DERIVED**，不能成为 independent truth。
- `derivation_type`（reported/inferred）= **PROVENANCE**。
- `review_status / reviewer` = **GOVERNANCE**，不改变 derivation（Gate 4A）。
- 每张表都需在数据字典标 Field Role，避免把缓存当事实。

## 4. 后端页面复用

前端详情页可直接复用本数据字典的 Field Role + Frontend Display 标注，减少重复设计。
