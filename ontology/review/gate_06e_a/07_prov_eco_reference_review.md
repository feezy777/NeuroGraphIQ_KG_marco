# Gate 6E-A — PROV-O / ECO Reference Review

本轮状态: **REFERENCE ONLY，禁止 owl:imports**

---

## 1. PROV-O（Provenance Ontology）

- Namespace `http://www.w3.org/ns/prov#`。
- 核心：prov:Entity / prov:Activity / prov:Agent；wasGeneratedBy / wasDerivedFrom / wasAttributedTo。
- **借鉴**：inferred 知识（roll-up 产物）的 derivation lineage（wasDerivedFrom 对应 premise lineage + inference rule）。
- **不采用**：不 import；derivation provenance 放 DB InferenceRecord / provenance_json。

## 2. ECO（Evidence & Conclusion Ontology）

- evidence = "a type of information used to support an assertion"；assertion method = "a means by which a statement is made about an entity"。
- **借鉴**：印证 Evidence 的"内容/方法"与"产生方式/断言"是不同轴（Gate 4A 多轴模型已体现）。
- **不采用**：不 import；EvidenceType 已 REMOVE，多轴模型已冻结。

## 3. 结论

- 二者仅作 reference，不 import、不复制。
- PROV-O 思想用于 inferred 知识 derivation lineage；ECO 思想用于 Evidence 多轴。
