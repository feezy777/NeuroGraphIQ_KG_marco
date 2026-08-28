# Gate 4A — EvidenceType 定义卡（采集模态轴，KEEP 5 类）

EvidenceType = **acquisition modality**（采集模态）。analysis_method 与 intervention_method 是独立子轴（见文末）。

---

## Card 1 — TracerEvidence

- **Canonical Name:** TracerEvidence
- **中文:** 示踪证据
- **Axis:** EvidenceType（modality = tracer）
- **Status:** KEEP
- **定义:** 逆行/顺行示踪得到的解剖连接证据。
- **支持:** StructuralConnection、Projection、方向判定（anterograde/retrograde/combined）。
- **边界:** 方向性金标准；**不等于** tractography（间接重建，不能判向）。
- **Reference:** Lanciego & Wouterlood 2011.

## Card 2 — HistologyEvidence（收紧）

- **Canonical Name:** HistologyEvidence
- **中文:** 组织学证据（connection-relevant）
- **Axis:** EvidenceType（modality = histology）
- **Status:** KEEP（收紧）
- **定义:** 能够观察、追踪或重建与**神经通路相关**的组织学/染色证据。
- **支持:** StructuralConnection（仅 connection-relevant）。
- **边界:** 普通 histology / staining **不自动**支持 StructuralConnection；须为 connection-relevant。

## Card 3 — DiffusionMRIEvidence

- **Canonical Name:** DiffusionMRIEvidence
- **中文:** 弥散 MRI 证据
- **Axis:** EvidenceType（modality = diffusion_mri）
- **Status:** KEEP
- **定义:** dMRI 采集数据；结构连接由 analysis_method = tractography 重建。
- **支持:** StructuralConnection（间接重建）。
- **边界:** 间接重建，有 crossing/kissing fibers 局限；**不能单独判定投射方向**。
- **Reference:** Jones & Cercignani 2010.

## Card 4 — FunctionalMRIEvidence（RENAME）

- **Canonical Name:** FunctionalMRIEvidence
- **中文:** 功能 MRI 证据
- **Axis:** EvidenceType（modality = functional_mri / BOLD）
- **Status:** KEEP（RENAME：原 FunctionalImagingEvidence）
- **定义:** fMRI / BOLD 功能证据。
- **支持:** FunctionalConnectivity（correlation）；配合 analysis_method=DCM 可支持 EffectiveConnectivity。
- **边界:** 统计依赖，不隐含结构连接；**PET 不在此类**（DEFER）。

## Card 5 — ElectrophysiologyEvidence

- **Canonical Name:** ElectrophysiologyEvidence
- **中文:** 电生理证据
- **Axis:** EvidenceType（modality = electrophysiology）
- **Status:** KEEP
- **定义:** single-unit / LFP / EEG / MEG 等电生理证据。
- **支持:** FunctionalConnectivity（coherence/coupling）；配合 analysis_method 可支持 EffectiveConnectivity。

---

## 独立子轴 1 — analysis_method（分析方式）

| 值 | 说明 |
|---|---|
| tractography | dMRI 纤维追踪重建 |
| correlation | 时间序列相关 |
| coherence | 相干 |
| DCM | 动态因果建模 |
| SEM | 结构方程模型 |
| Granger | 格兰杰因果 |

> **DCM / SEM / Granger 是 analysis_method，不是 modality 类。** 它们施加于 FunctionalMRIEvidence / ElectrophysiologyEvidence 数据之上，与后者不互斥。

## 独立子轴 2 — intervention_method（干预方式）

| 值 | 说明 |
|---|---|
| lesion | 损伤 |
| TMS | 经颅磁刺激 |
| DBS | 深部脑刺激 |
| optogenetics | 光遗传 |

> **lesion / TMS / DBS / optogenetics 是 intervention_method。** 可增强 directed influence / causal interpretation，但**不能**因存在 perturbation 就自动生成 EffectiveConnectivity。是否建立 EffectiveConnectivity assertion 取决于实验设计、readout、analysis_method。

---

## DEFER（移出 V1 KEEP）

| 概念 | 去向 |
|---|---|
| GeneticMolecularEvidence | DEFER（V1 不建 Gene/Protein/Receptor/MolecularPathway；表达/富集不直接证明 Connection） |
| PET | DEFER（未来 metabolic/molecular evidence 模型） |

## REMODEL（移出 EvidenceType，归 analysis/intervention）

| 概念 | 去向 |
|---|---|
| EffectiveConnectivityModelEvidence | → DCM/SEM/Granger → analysis_method |
| PerturbationEvidence | → lesion/TMS/DBS/optogenetics → intervention_method |

---

## 多标签组合原则

一条 Evidence 可**同时**具有多个子轴值：

- `FunctionalMRIEvidence` + `analysis_method = DCM` → EffectiveConnectivity 证据
- `DiffusionMRIEvidence` + `analysis_method = tractography` → StructuralConnection 证据（间接）
- `ElectrophysiologyEvidence` + `analysis_method = coherence` → FunctionalConnectivity 证据
