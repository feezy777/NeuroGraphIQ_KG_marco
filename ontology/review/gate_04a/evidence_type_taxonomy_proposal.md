# Gate 4A — EvidenceType 科学分类方案（候选，待人工审查）

Ontology IRI: `https://neurographiq.org/ontology/macro96`
本轮状态: **仅方案，未写入正式 TTL**

---

## 0. 核心发现：旧「方法/模态轴」混了三根子轴

旧草案把三根正交子轴混在一个 EvidenceType 里：

| 旧概念 | 真实所属子轴 |
|---|---|
| TracerEvidence / HistologyEvidence / DiffusionMRIEvidence / FunctionalImagingEvidence / ElectrophysiologyEvidence | **acquisition modality**（采集模态） |
| tractography / correlation / coherence / DCM / SEM / Granger | **analysis method**（分析方式） |
| lesion / TMS / DBS / optogenetics | **intervention method**（干预方式） |

**结论：Evidence 方法维度必须拆成三根子轴，不能是一个互斥 EvidenceType 枚举。**

---

## 1. RECOMMENDED EVIDENCE MODEL（三子轴 + 独立维度）

```
Evidence（证据记录）
├── EvidenceType = acquisition modality（采集模态，KEEP 5 类，非互斥于 analysis）
│   ├─ TracerEvidence            [KEEP]
│   ├─ HistologyEvidence         [KEEP]（仅 connection-relevant）
│   ├─ DiffusionMRIEvidence      [KEEP]
│   ├─ FunctionalMRIEvidence     [RENAME：原 FunctionalImagingEvidence，PET 移除]
│   └─ ElectrophysiologyEvidence [KEEP]（single-unit / EEG / MEG）
│
├── analysis_method（分析方式，独立子轴）
│   ├─ tractography / correlation / coherence / DCM / SEM / Granger
│
├── intervention_method（干预方式，独立子轴）
│   ├─ lesion / TMS / DBS / optogenetics
│
├── source_type（来源轴，独立）
├── evidence_directness（direct / indirect，独立）
├── evidence_strength（strong / moderate / weak / unknown，独立）
├── confidence（独立）
└── review_status（独立）
```

### 关键：多标签组合

一条 Evidence 可以**同时**具有：
- EvidenceType（modality）= functional_mri
- analysis_method = DCM

即 `FunctionalMRIEvidence + analysis_method=DCM`，用于 EffectiveConnectivity 证据。

---

## 2. 旧草案逐项裁定

| 旧概念 | 裁定 | 去向 |
|---|---|---|
| ExperimentalEvidence（抽象上位） | **REMODEL** | 采集模态轴根 |
| TracerEvidence | **KEEP** | 模态轴 |
| HistologyEvidence | **KEEP（收紧）** | 模态轴（仅 connection-relevant） |
| DiffusionMRIEvidence | **KEEP** | 模态轴 |
| ImagingEvidence | **REMODEL** | 拆为 DiffusionMRIEvidence + FunctionalMRIEvidence（PET 移除） |
| FunctionalImagingEvidence | **RENAME** | → FunctionalMRIEvidence（fMRI/BOLD；PET 移除） |
| EffectiveConnectivityModelEvidence | **REMODEL** | DCM/SEM/Granger → analysis_method（非模态类） |
| PerturbationEvidence | **REMODEL** | lesion/TMS/DBS/optogenetics → intervention_method |
| GeneticMolecularEvidence | **DEFER** | V1 不建 Gene/Protein/Receptor/MolecularPathway；表达/富集不直接证明 Connection |
| PET | **DEFER** | 未来 metabolic/molecular evidence 模型 |
| LiteratureEvidence | **REMOVE** | → source_type = literature |
| PrimaryStudyStatement | **REMOVE** | → source_level = primary |
| ReviewStatement | **REMOVE** | → source_level = secondary |
| DatabaseEvidence | **REMOVE** | → source_type = database |
| ComputationalEvidence | **REMODEL** | DCM/SEM/Granger → analysis_method；LLM → provenance |
| ManualCuratedEvidence | **REMOVE** | → curation action / review record |

**最终 EvidenceType KEEP = 5（模态轴）。**

---

## 3. 关键科学边界

### 3.1 Tracer vs tractography（保持分离）

- TracerEvidence（模态=tracer）→ 方向性金标准（anterograde/retrograde 判 A→B）。
- DiffusionMRIEvidence（模态=diffusion_mri）+ analysis_method=tractography → 间接结构重建，**不能**单独判定投射方向。

### 3.2 DCM / SEM / Granger 是 analysis_method，不是 modality

- 它们是**分析方式**，施加于 fMRI / electrophysiology 数据之上。
- 与 FunctionalMRIEvidence / ElectrophysiologyEvidence **不是互斥**：DCM 分析的是 fMRI 数据。

### 3.3 lesion / TMS / DBS / optogenetics 是 intervention_method

- 它们能增强 directed influence / causal interpretation，但**不能**因存在 perturbation 就自动生成 EffectiveConnectivity。
- 是否建立 EffectiveConnectivity assertion 取决于实验设计、readout、analysis_method。

### 3.4 HistologyEvidence 收紧

普通 histology/staining **不自动**支持 StructuralConnection。必须是 **connection-relevant** 组织学证据（能观察/追踪/重建与神经通路相关）。

### 3.5 GeneticMolecularEvidence → DEFER

V1 不构建 Gene/Protein/Receptor/MolecularPathway 核心语义；基因表达/富集不能直接证明 brain-region Connection。

### 3.6 PET → DEFER

PET 不自动作为 FunctionalConnectivity evidence；标记 DEFER，留待未来 metabolic/molecular evidence 模型。

---

## 4. 待人工审查的关键决策点

1. EvidenceType 是否 = 采集模态轴（5 类），analysis_method / intervention_method 独立？
2. EffectiveConnectivityModelEvidence 是否改为「DCM/SEM/Granger → analysis_method」（不建模态类）？
3. FunctionalImagingEvidence 是否正名为 FunctionalMRIEvidence（PET 移除）？
4. GeneticMolecularEvidence 是否 DEFER？
5. HistologyEvidence 是否收紧为 connection-relevant only？
6. PerturbationEvidence 是否改为「lesion/TMS/DBS/optogenetics → intervention_method」？

---

## 5. 涉及文件

- evidence_definition.md、evidence_dimensions.md、evidence_type_definition_cards.md、assertion_type_proposal.md、assertion_type_definition_cards.md、evidence_assertion_boundary_matrix.md、worked_examples.md、excluded_or_remodeled_terms.md、references.md、review_checklist.md
