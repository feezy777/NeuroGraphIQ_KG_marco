# Gate 7A — Disease / Symptom Tables

本轮状态: **仅设计文档**

---

## 1. diseases

| 字段 | 说明 |
|---|---|
| disease_pk | 内部主键 |
| disease_id | NGIQ-DIS-… |
| name_en / name_zh | 名称 |
| abbreviation | 缩写 |
| mondo_id / doid / mesh_id / umls_cui / icd10_code | 外部 ID |
| disease_category | 类别（neurodegenerative / psychiatric / neurological …） |
| definition_en / definition_zh | 定义 |
| description_en / description_zh | 描述 |
| remark | 备注 |

## 2. symptoms

| 字段 | 说明 |
|---|---|
| symptom_pk | 内部主键 |
| symptom_id | NGIQ-SYM-… |
| name_en / name_zh | 名称 |
| abbreviation | 缩写 |
| hpo_id / mesh_id / umls_cui | 外部 ID |
| symptom_category | 类别 |
| definition_en / definition_zh | 定义 |
| description_en / description_zh | 描述 |
| remark | 备注 |

> Disease ≠ Symptom。diseases 与 symptoms 是独立表，通过 knowledge_assertions（hasSymptom）关联，不在 diseases 表内嵌 symptom 列表。
