# Gate 4A — References（参考文献）

**引用纪律：** 只记录经确认的来源；未确认的单独列于 Pending。禁止编造 DOI / PMID / IRI / ontology term。

**验证方法：** Verified 引用均通过实时联网检索核实。

---

## Verified References（本轮新核实）

### 1. Evidence & Conclusion Ontology（ECO）

- **ECO, the Evidence & Conclusion Ontology.** OBO Foundry library ontology.
  - OBO IRI: `http://purl.obolibrary.org/obo/eco.owl`
  - Homepage: https://www.evidenceontology.org
  - 结构：两大高层类 `evidence`（a type of information used to support an assertion）与 `assertion method`（a means by which a statement is made about an entity）。
- **关键论文（verified，经检索确认 PMID）：**
  - "ECO, the Evidence & Conclusion Ontology: community standard for evidence information." PMID 30407590.
  - "ECO: the Evidence and Conclusion Ontology, an update for 2022." PMID 34986598.
  - "Standardized description of scientific evidence using the Evidence Ontology (ECO)." PMID 25052702.
- 用途：论证 evidence 的「内容/方法」与「产生方式/断言方法」是不同轴；作为 term mapping/reference 参考，**不整套 import**。

### 2. W3C PROV-O（Provenance Ontology）

- **PROV-O: The PROV Ontology.** W3C Recommendation, 30 April 2013.
  - Namespace: `http://www.w3.org/ns/prov#`
  - 核心类：`prov:Entity` / `prov:Activity` / `prov:Agent`；核心属性 `prov:wasGeneratedBy` / `prov:wasDerivedFrom` / `prov:wasAttributedTo`。
- 用途：provenance 模型参考（provenance axis：谁/什么流程产生证据）。

---

## Reused Verified References（Gate 2A / 3A 已核实，本轮复用）

3. **Lanciego JL, Wouterlood FG (2011).** A half century of experimental neuroanatomical tracing. *J Chem Neuroanat* 42(3):157–183. DOI 10.1016/j.jchemneu.2011.07.001. PMID 21782932.（tracer 方法学）
4. **Jones DK, Cercignani M (2010).** Twenty-five pitfalls in the analysis of diffusion MRI data. *NMR Biomed* 23(7):803–820. DOI 10.1002/nbm.1543. PMID 20886566.（DTI 局限）
5. **Friston KJ (1994).** Functional and effective connectivity in neuroimaging: a synthesis. *Hum Brain Mapp* 2(1–2):56–78. DOI 10.1002/hbm.460020107.
6. **Friston KJ (2011).** Functional and effective connectivity: a review. *Brain Connectivity* 1(1):13–36. DOI 10.1089/brain.2011.0008. PMID 22432952.
7. **Bullmore E, Sporns O (2009).** Complex brain networks. *Nat Rev Neurosci* 10(3):186–198. DOI 10.1038/nrn2575. PMID 19190637.
8. **Felleman DJ, Van Essen DC (1991).** Distributed hierarchical processing in the primate cerebral cortex. *Cereb Cortex* 1(1):1–47. DOI 10.1093/cercor/1.1.1-a. PMID 1822724.
9. **Douglas RJ, Martin KAC (2004).** Neuronal circuits of the neocortex. *Annu Rev Neurosci* 27:419–451. DOI 10.1146/annurev.neuro.27.070203.144152. PMID 15217339.

---

## Pending References（待后续人工/联网确认）

以下为可能补充、但本轮未逐条核实具体 term/IRI 的来源，**不用于正式定义**：

1. ECO 具体 evidence term 的精确 IRI（如 tracer evidence / curated evidence 对应 term）——需在 OLS / Ontobee 逐条核对，本轮不引用具体 term IRI。
2. PROV-O 具体属性与 NeuroGraphIQ provenance 字段的映射表——需人工确认，本轮只记录命名空间。
3. primary vs secondary evidence 的方法学综述（specific 论文标题未核实）——pending。

> 以上均明确 pending，未伪装成 verified。本轮 ECO / PROV-O 仅作「参考/映射方向」，不 import、不引用具体 term IRI。

---

## 引用诚实性声明

- 本轮 2 条新核实标准（ECO、PROV-O）+ 7 条复用 Gate 2A/3A 已核实引用。
- ECO / PROV-O 的命名空间与关键 PMID 经联网核实；未引用未经核实的具体 ECO term IRI。
- Pending 3 条明确标注 pending。
