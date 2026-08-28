# Gate 6E-A — Reported vs Inferred

本轮状态: **仅设计，不写 TTL**

---

## 1. 定义（冻结）

- **reported** = 外部来源明确陈述（primary/review literature + curated database）。
- **inferred** = 系统依据已知知识 + 规则推导（roll-up / abstraction / graph inference）。

## 2. Evidence 模型差异

| 类型 | Evidence 处理 |
|---|---|
| reported assertion/entity | 有 direct literature/database Evidence |
| inferred assertion/entity | **无** direct literature Evidence；依据 premise assertions + source Connection + aggregation mappings + inference rule |

## 3. inferred 依据不是 Evidence

- G1 inferred Connection 的依据是：G4 Connection + G4→G1 mappings（premise lineage）。
- 这些是 **inference premises / derivation lineage**，不是 direct scientific evidence。
- 分开存：Evidence（direct literature） vs InferenceRecord/premise lineage（derivation provenance）。

## 4. Human review 不改 derivation

- HumanReview 不把 inferred 改成 reported。
- Human review 只确认是否允许进入 canonical knowledge。
