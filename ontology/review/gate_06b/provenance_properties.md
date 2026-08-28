# Gate 6B — Provenance Properties（证据溯源属性）

Ontology IRI: `https://neurographiq.org/ontology/human-brain`
version: `0.6.0-gate6b`

---

## 1. 研究/文献/证据链

```
ResearchStudy ──reportedIn──> Publication ──providesEvidence──> Evidence
```

| Property | Domain | Range | Role |
|---|---|---|---|
| reportedIn | ResearchStudy | Publication | Canonical |
| providesEvidence | Publication | Evidence | Canonical |

## 2. 未写入

- **supports / contradicts** 未写入（DEFER）。
- 原因：其真正 Range 应是一条 scientific assertion / relation assertion，而非仅 Connection/Circuit entity。
- 未来需 Evidence / Assertion Formalization Gate 解决普通 ObjectProperty edge 如何绑定具体 Evidence。
- 本轮禁止新增 Assertion / RelationAssertion / Statement Class。
