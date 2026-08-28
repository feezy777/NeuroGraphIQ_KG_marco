# Gate 7A — Gene / Neurotransmitter / Receptor Tables

本轮状态: **仅设计文档**

---

## 1. genes

| 字段 | 说明 |
|---|---|
| gene_pk | 内部主键 |
| gene_id | NGIQ-GEN-… |
| name_en / name_zh | 名称 |
| approved_symbol | 批准符号（HGNC） |
| approved_name | 批准名称 |
| hgnc_id | HGNC ID |
| ncbi_gene_id / ensembl_gene_id / uniprot_id | 外部 ID |
| locus_group / locus_type | 基因座组/类型 |
| chromosome / cytogenetic_location | 染色体/细胞遗传学定位 |
| gene_group | 基因家族 |
| summary_en / summary_zh | 摘要 |
| hgnc_status | 状态 |
| remark | 备注 |

> aliases / previous symbol/name 优先用 entity_aliases，不塞 JSON。

## 2. neurotransmitters

| 字段 | 说明 |
|---|---|
| neurotransmitter_pk | 内部主键 |
| neurotransmitter_id | NGIQ-NT-… |
| name_en / name_zh | 名称 |
| abbreviation | 缩写 |
| chebi_id / pubchem_cid | 化学 ID |
| chemical_formula | 化学式 |
| molecular_weight | 分子量 |
| neurotransmitter_class | 类别 |
| description_en / description_zh | 描述 |
| remark | 备注 |

> Human-only 是 knowledge assertion scope，不代表 Dopamine 本身是 Homo-sapiens-specific entity。

## 3. receptors

| 字段 | 说明 |
|---|---|
| receptor_pk | 内部主键 |
| receptor_id | NGIQ-RCP-… |
| name_en / name_zh | 名称 |
| abbreviation | 缩写 |
| iuphar_id | IUPHAR ID |
| gene_symbol / hgnc_id / uniprot_id | 基因/蛋白关联 |
| receptor_family / receptor_type | 家族/类型 |
| description_en / description_zh | 描述 |
| remark | 备注 |
