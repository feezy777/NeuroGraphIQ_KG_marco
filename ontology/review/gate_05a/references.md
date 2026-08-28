# Gate 5A — References（参考文献）

Ontology IRI: `https://neurographiq.org/ontology/macro96`

**引用纪律：** 只记录经确认的来源；未确认的单独列于 Pending。禁止编造 DOI / PMID / IRI / ontology term。

**验证方法：** Verified 引用经实时联网检索核实（2026-08-28）；复用 Gate 2A/3A/4A 已核实引用单独标注。

---

## Verified References（本轮新核实，2026-08-28 联网）

### 1. Uberon（多物种解剖本体，含人脑区域）

- **Uberon: multi-species anatomy ontology.**
  - Ontology IRI: `http://purl.obolibrary.org/obo/uberon.owl`
  - Term namespace: `http://purl.obolibrary.org/obo/UBERON_`
  - Homepage: https://obophenotype.github.io/uberon/
  - 用途：BrainRegion 的参考/映射方向（**不整套 import**）。

### 2. ChEBI（化学实体本体，含神经递质）

- **ChEBI: Chemical Entities of Biological Interest.**
  - Homepage: https://www.ebi.ac.uk/chebi/
  - `neurotransmitter` = CHEBI:25512（"an endogenous compound that is used to transmit information across the synapse"）。
  - `L-glutamic acid` = CHEBI:16015（has role neurotransmitter）。
  - 用途：Neurotransmitter 的参考（**不 import**）。

### 3. Cell Ontology（CL，细胞类型本体，含 neuron）

- **Cell Ontology (CL).**
  - Ontology IRI: `http://purl.obolibrary.org/obo/cl.owl`
  - Term namespace: `http://purl.obolibrary.org/obo/CL_`
  - neuron = CL:0000540（glutamatergic neuron CL:0000679 等子类）。
  - 用途：NeuralStructure 未来子类（Neuron 等）的参考。

### 4. MONDO（Monarch Disease Ontology）

- **Mondo Disease Ontology.**
  - Ontology IRI: `http://purl.obolibrary.org/obo/mondo.owl`
  - Term namespace: `http://purl.obolibrary.org/obo/MONDO_`
  - Homepage: https://mondo.monarchinitiative.org/
  - 用途：Disease 的参考/映射方向。

### 5. Human Phenotype Ontology（HPO，含症状/表型）

- **Human Phenotype Ontology (HPO).**
  - Ontology IRI: `http://purl.obolibrary.org/obo/hp.owl`
  - Term namespace: `http://purl.obolibrary.org/obo/HP_`
  - 描述："standardized vocabulary of phenotypic abnormalities and clinical features encountered in human disease"。
  - 用途：Symptom 的参考/映射方向。

### 6. Gene Ontology（GO）

- **Gene Ontology (GO).**
  - Ontology IRI: `http://purl.obolibrary.org/obo/go.owl`
  - Term namespace: `http://purl.obolibrary.org/obo/GO_`（如 GO:0007186）。
  - 用途：Gene 相关功能注解的参考方向（**不 import**；Gene 本体命名以 HGNC 为准，见 §7）。

### 7. Human Disease Ontology（DO）

- **Human Disease Ontology (DO).**
  - Homepage: https://disease-ontology.org/
  - Term prefix: `DOID`（如 Alzheimer's disease DOID:10652）。
  - 用途：Disease 的参考/映射方向（与 MONDO 并列参考）。

### 8. HGNC（人类基因命名委员会）

- **HUGO Gene Nomenclature Committee (HGNC).**
  - Homepage: https://www.genenames.org/
  - 描述：人类基因符号/名称的权威来源（>43,000 批准符号）。
  - 用途：Gene 概念的命名参考（APOE / DISC1 符号以 HGNC 为准）。

### 9. IUPHAR/BPS Guide to Pharmacology（受体数据库）

- **IUPHAR/BPS Guide to Pharmacology.**
  - Homepage: https://www.guidetopharmacology.org/
  - 覆盖：ionotropic glutamate receptor（NMDA/AMPA/kainate，NMDA 为 GluN1+GluN2 异聚体）等受体家族。
  - 用途：Receptor 的权威参考（D1/D2/NMDA/AMPA 命名与分类）。

### 10. BIBO / FaBiO（文献本体）

- **BIBO (The Bibliographic Ontology).** Namespace: `http://purl.org/ontology/bibo/`（文献描述，较通行）。
- **FaBiO (FRBR-aligned Bibliographic Ontology).** Namespace: `http://purl.org/spar/fabio/`（FRBR 对齐的替代词汇）。
- 用途：Publication / Study 的文献元数据参考方向。

### 11. Julich-Brain atlas（人脑细胞构筑图谱）

- Amunts K, Mohlberg H, Bludau S, Zilles K. **Julich-Brain: A 3D probabilistic atlas of the human brain's cytoarchitecture.** *Science* 2020;369(6506):988–992. DOI 10.1126/science.abb4588。
- 用途：Atlas / ExternalRegion 的人脑图谱参考。

### 12. Brainnetome atlas（人脑连接组图谱）

- Fan L, et al. **The Human Brainnetome Atlas: A New Brain Atlas Based on Connectional Architecture.** *Cereb Cortex* 2016;26:3508–3526. DOI 10.1093/cercor/bhw157。
- 用途：Atlas / ExternalRegion 的人脑图谱参考。

---

## Reused Verified References（Gate 2A / 3A / 4A 已核实，本轮复用）

13. Lanciego JL, Wouterlood FG (2011). A half century of experimental neuroanatomical tracing. *J Chem Neuroanat* 42(3):157–183. PMID 21782932.（tracer 方法学）
14. Jones DK, Cercignani M (2010). Twenty-five pitfalls in the analysis of diffusion MRI data. *NMR Biomed* 23(7):803–820. PMID 20886566.（DTI 局限）
15. Friston KJ (1994). Functional and effective connectivity in neuroimaging: a synthesis. *Hum Brain Mapp* 2(1–2):56–78.
16. Friston KJ (2011). Functional and effective connectivity: a review. *Brain Connectivity* 1(1):13–36. PMID 22432952.
17. Bullmore E, Sporns O (2009). Complex brain networks. *Nat Rev Neurosci* 10(3):186–198. PMID 19190637.
18. Felleman DJ, Van Essen DC (1991). Distributed hierarchical processing in the primate cerebral cortex. *Cereb Cortex* 1(1):1–47. PMID 1822724.
19. Douglas RJ, Martin KAC (2004). Neuronal circuits of the neocortex. *Annu Rev Neurosci* 27:419–451. PMID 15217339.
20. ECO (Evidence & Conclusion Ontology). PMID 30407590 / 34986598 / 25052702.（Gate 4A）
21. W3C PROV-O (Provenance Ontology). W3C Recommendation 2013.（Gate 4A）

---

## Pending References（待后续人工/联网确认，不用于正式定义）

1. 老师 PPT 原文（节点类型列表）——**待老师提供正式版本/页码**；本轮按任务描述中的节点清单引用，未逐页核对 PPT 原文。
2. 各参考本体**具体 term IRI** 的精确映射（如 Uberon 具体脑区 term、ChEBI 具体递质 term、CL 具体 neuron term、HPO 具体 symptom term、DOID/MONDO 具体 disease term）——需在 OLS / Ontobee 逐条核对，本轮只记录命名空间/已知稳定 ID，不引用未经核对的 term IRI。
3. HGNC 具体 gene symbol report（APOE / DISC1 的精确 HGNC ID）——本轮只确认 HGNC 权威地位，未逐条核对具体 HGNC ID。
4. Study / Publication / Evidence 关系建模的方法学综述（specific 论文标题未核实）——pending。

---

## 引用诚实性声明

- 本轮 **12 条新核实参考**（Uberon / ChEBI / CL / MONDO / HPO / GO / DO / HGNC / IUPHAR-BPS / BIBO-FaBiO / Julich-Brain / Brainnetome）+ 9 条复用 Gate 2A/3A/4A 已核实引用。
- 命名空间、已知稳定 ID 与关键 DOI 经联网核实；**未引用任何未经核对的 term IRI**。
- Pending 4 条明确标注 pending，未伪装成 verified。
- 所有外部本体仅作「参考/映射方向」，**本轮不 import、不引用具体 term IRI**。
