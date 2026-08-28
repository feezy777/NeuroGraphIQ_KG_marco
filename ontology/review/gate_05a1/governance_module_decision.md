# Gate 5A.1 — Governance Module 决策

Ontology IRI（当前）: `https://neurographiq.org/ontology/macro96`
本轮状态: **仅决策文档，未修改正式 TTL**

---

## 1. 问题

Governance 类（ConnectionCandidate / CircuitCandidate / EvidenceCandidate / SearchRun / ExtractionRun / ModelReview / HumanReview / InferenceRecord / ValidationRecord）**不是人脑生物学实体**，属于 knowledge production / workflow / review / inference / validation / governance。

## 2. 三方案比较

| 方案 | 说明 | 评估 |
|---|---|---|
| A | 与 Human Brain Domain 同 ontology TTL | 混淆科学实体与流程实体 |
| B | 未来建独立 Governance Ontology | 需要时再做；当前语义互操作需求未显现 |
| C | **不进入 OWL，仅作 PostgreSQL application schema** | 工作流字段大量是 status/timestamp/model/prompt/version/reviewer/run_id/batch/retry/error/progress/state transition，更适合关系库 |

## 3. 推荐：方案 C — database-first

- **核心科学 ontology** 与 **knowledge production / governance** 逻辑分离。
- Governance classes 第一阶段放 **PostgreSQL application / governance schema**。
- 未来如确有 semantic interoperability 需求，再建 NeuroGraphIQ Governance Ontology。

## 4. 为什么 DB-only Governance（理由）

这些 workflow class 大量需要 status/timestamp/model/prompt/version/reviewer/run_id/batch/retry/error/progress/state transition，**更适合 relational database / application model**，而非核心 scientific ontology。

## 5. 关键边界（防误伤）

- **ResearchStudy / Publication / Evidence 继续保留在 Human Brain scientific knowledge model**（是 scientific provenance / evidence model，直接参与可解释知识），**不要**移入纯 governance database。
- **Atlas / ExternalRegion / RegionMapping** 虽非 human biological entity，但属 knowledge integration layer（服务 fine-region normalization / atlas mapping / canonicalization），**继续保留在 Human Brain ontology scope**；是否未来拆独立 module → DEFER。

## 6. 结论

| 项 | 决策 |
|---|---|
| Governance V1 推荐 | **database-first** |
| 是否进入 core ontology | 否 |
| 推荐存储位置 | PostgreSQL application / governance schema |
| 保留 governance design docs + schema 规划 | 是 |
| ResearchStudy/Publication/Evidence | 保留在 scientific ontology |
| Atlas/ExternalRegion/RegionMapping | 保留在 Human Brain ontology |
