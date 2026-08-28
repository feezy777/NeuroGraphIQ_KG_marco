# Gate 7A — Granularity Policy（颗粒度策略）

本轮状态: **仅设计文档，未修改正式 TTL**

---

## 1. 定位

NeuroGraphIQ V1 正式使用 **G1–G4 四级 internal canonical granularity framework**。这是 NeuroGraphIQ 自己定义的知识抽象尺度，**不是国际公认的 Atlas 排名**。

> 关键：parcel 数量 ≠ biological granularity。Schaefer-1000 不比 Julich-Brain 更有组织学意义。

## 2. 四级颗粒度

| 级别 | Canonical value | 中文 | Primary anchor | 定位 |
|---|---|---|---|---|
| G1 | G1_MACRO | 宏观脑区层 | Macro96（96 region） | 最粗粒度，临床展示/全局浏览/汇总层 |
| G2 | G2_MESO_ANATOMICAL | 中尺度解剖脑区层 | AAL3 family | MRI/fMRI 文献脑区定位 |
| G3 | G3_MESO_FINE | 中细粒度脑区层 | Human Brainnetome（246：210 cortical + 36 subcortical） | connectivity-informed parcellation |
| G4 | G4_MICROSTRUCTURAL_FINE | 微结构细粒度脑区层 | Julich-Brain | 组织学/细胞构筑尺度边界 |

## 3. Supplementary anchors

- HCP-MMP1.0：Human、cortex-only、180/hemisphere、360 cortical total → G3，granularity_basis=multimodal_parcellation（360 > 246 不代表更高级别）。
- Schaefer：Human cortical functional parcellation，100/200/…/1000 → G3，granularity_basis=functional_connectivity_parcellation（1000 不创建 G4/G5）。
- BigBrain：Homo sapiens 高分辨率组织学参考脑（~20 μm）→ **spatial/reference resource only，非独立 granularity level**（禁止 G5_BIGBRAIN）。

## 4. 不是严格 Atlas 树

Julich / Brainnetome / AAL3 / Macro96 定义方法、边界、reference space、coverage、parcellation principle 不同，**不是俄罗斯套娃**。禁止假定 G4 恰好组成 G3、G3 恰好组成 G2。

## 5. brain_regions granularity 字段

| 字段 | Role | 说明 |
|---|---|---|
| granularity_level | SCIENTIFIC | G1_MACRO / G2_MESO_ANATOMICAL / G3_MESO_FINE / G4_MICROSTRUCTURAL_FINE |
| granularity_basis | SCIENTIFIC/PROVENANCE | macro_anatomical / anatomical_parcellation / connectivity_parcellation / multimodal_parcellation / functional_parcellation / cytoarchitectonic / microstructural / manual_canonical / other |
| granularity_rank | DERIVED | 1 / 2 / 3 / 4 |
| is_finest_available | DERIVED | 当前 lineage 是否最细可靠 canonical representation |

## 6. external_regions granularity 字段

- granularity_level、granularity_basis（来自 source atlas context，不自动强制 canonical granularity）。

## 7. Connection / Circuit granularity_scope

| 表 | 字段 | Role | 候选 |
|---|---|---|---|
| connections | granularity_scope | DERIVED | G1_MACRO / G2_MESO_ANATOMICAL / G3_MESO_FINE / G4_MICROSTRUCTURAL_FINE / CROSS_GRANULARITY / UNSPECIFIED |
| circuits | granularity_scope | DERIVED | G1 / G2 / G3 / G4 / MIXED / UNSPECIFIED |

- Connection 从 source/target/endpoints 的 BrainRegion.granularity_level 计算；Circuit 从 circuit_region_memberships 派生。

## 8. Finest Available Policy

- 知识发现优先 G4 → G3 → G2 → G1。
- 较粗粒度 BrainRegion 不删除（用于 clinical query / aggregation / roll-up / hierarchy / visualization / cross-scale reasoning）。

## 9. 前端显示

G1·Macro 宏观 / G2·Meso Anatomical 中尺度解剖 / G3·Meso-Fine 中细粒度 / G4·Microstructural Fine 微结构细粒度。查询器支持 All / G1 / G2 / G3 / G4；Connection 有 Cross-granularity，Circuit 有 Mixed。
