# Gate 4A — 排除（REMOVE）/ 重塑（REMODEL）/ 暂缓（DEFER）术语

本文件记录 Gate 4A 对旧 EvidenceType 草案与 assertion 模型的完整裁定。

---

## 1. EvidenceType 旧草案裁定

| 旧概念 | 裁定 | 去向 |
|---|---|---|
| ExperimentalEvidence | **REMODEL** | 采集模态轴根 |
| TracerEvidence | **KEEP** | 模态轴 |
| HistologyEvidence | **KEEP（收紧）** | 模态轴（仅 connection-relevant） |
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

## 2. 旧单一 assertion_type 枚举 → 多轴拆分

| 旧值 | 裁定 | 新归属 |
|---|---|---|
| reported_fact | **RENAME** | → derivation_type = reported（正名 reported_assertion / reported_claim，弃「fact」） |
| inferred | **KEEP（重定位）** | → derivation_type = inferred |
| hypothesis | **KEEP（重定位）** | → epistemic_status = hypothesis（与 inferred 正交） |
| candidate | **REMOVE（从 assertion_type）** | → lifecycle_status = candidate |
| curated_fact | **REMOVE** | = reported + review_status=approved |
| generated_by_llm_run | **REMOVE** | → generation_method / provenance |
| confirmed_by_reviewer | **REMOVE** | → review_status |
| composed / reconstructed | **REMODEL** | → construction_mode（Circuit-specific） |

## 3. 其余被移出 EvidenceType / assertion 轴的概念

| 概念 | 正确归属 |
|---|---|
| `direct / indirect / context / contradictory`（旧 evidence_type） | evidence_directness / evidence_strength |
| `llm_explanation / manual_note / rule_validation`（旧 evidence_type） | generation_method / provenance |
| `expression / enrichment`（旧 evidence_type） | → DEFER（GeneticMolecularEvidence 移出 V1 KEEP） |
| `confidence` | 独立 confidence 字段（≠ strength） |
| `review_status` | 独立 review_status 字段 |
| `lifecycle_status`（candidate/promoted/rejected） | 独立 lifecycle_status 字段 |

## 4. 裁定总表（最终推荐模型）

- **EvidenceType（KEEP，采集模态轴，5 类）**: TracerEvidence, HistologyEvidence（connection-relevant）, DiffusionMRIEvidence, FunctionalMRIEvidence, ElectrophysiologyEvidence。
- **analysis_method（KEEP，独立子轴）**: tractography, correlation, coherence, DCM, SEM, Granger。
- **intervention_method（KEEP，独立子轴）**: lesion, TMS, DBS, optogenetics。
- **DEFER**: PET, GeneticMolecularEvidence。
- **derivation_type（KEEP）**: reported（≡ reported_assertion，= 外部来源明确陈述，非纯人工输入）, inferred（2 值）。
- **epistemic_status（KEEP 部分）**: hypothesis（唯一正式确认值；fact/established/supported/confirmed 一律 DEFER，待 Property / Data Dictionary Gate）。
- **lifecycle_status（KEEP，workflow 轴）**: candidate, promoted, rejected；主要适用于 workflow entity，是否挂到其他实体留待 Data Dictionary Gate。
- **review_status（KEEP，聚合）**: pending, approved, rejected, uncertain；ModelReview / HumanReview 独立记录，approved 不自动晋升。
- **generation_method / provenance（KEEP）**: literature_extraction, database_import, rule_inference, deepseek, biosebbert, human_manual（开放集）。
- **construction_mode（REMODEL）**: composed / reconstructed（Circuit-specific）。
