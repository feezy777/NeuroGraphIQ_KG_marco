# Gate 6E-B — Reported vs Inferred Boundary

Ontology IRI: `https://neurographiq.org/ontology/human-brain`

---

## 1. reported

- 外部来源明确陈述（primary/review literature + curated database）。
- 晋升 active/canonical 须有 direct scientific Evidence 或已审核 authoritative source provenance。
- Human Review 不把 inferred 改成 reported。

## 2. inferred

- 系统依据已知知识 + 规则推导（roll-up / abstraction / graph inference）。
- 主要依赖 InferenceRecord / premise lineage / source entities / aggregation mappings / inference rule，不要求 direct literature Evidence。

## 3. Inference premise ≠ Evidence

G4 Connection + G4→G1 mapping → G1 Connection：G4 Connection 和 mapping 是 derivation premise / inference lineage，不是 G1 的 direct Evidence。

## 4. Upstream Evidence 不自动继承

G4 Evidence 不自动 EvidenceLink → G1 inferred Connection 作为 direct supports。前端可显示 upstream/inherited/premise evidence，但标非 direct。
