# Gate 6A — Gene / Neurotransmitter / Disease 基础关系 · 第二轮修订

Ontology IRI: `https://neurographiq.org/ontology/human-brain`
本轮状态: **仅设计文档，未修改正式 TTL**

> 短期主线仍是 BrainRegion / Connection / Circuit / Function；Gene / Disease / Neurotransmitter 只保持基础关系，不扩展完整 biomedical relations。

---

## 1. MODULATES / 调控（PPT）

- Domain: Gene OR Neurotransmitter；Range: BrainRegion OR Circuit OR Function。
- 方向: Directed。
- 例子: Dopamine modulates RewardFunction；某 Gene modulates SynapticFunction。
- Role: Canonical。
- 边界: 不是 associated_with，也不是 causes；无调控证据不能使用。
- **暂不扩宽** Domain/Range（不加入 Disease/Receptor/Process/CellularNeuralStructure）。

## 2. INCREASES_RISK_OF / 增加风险（PPT，示例修正）

- Domain: Gene；Range: Disease。
- 方向: Directed。
- **例子: APOE increasesRiskOf AlzheimerDisease**。
- Role: Canonical。
- 边界: ≠ causes（风险 ≠ 必然发病）；associated_with 不能自动升级为 increasesRiskOf。
- **注意**：`APOE ε4` 更准确属于 allele / genetic variant，而非 Gene 本身。当前 V1 只有 Gene、无 GeneticVariant/Allele，故示例用 `APOE`。allele/variant 级风险关系需未来 GeneticVariant / Allele 模型才能更精确表达，V1 暂不扩展（本轮**禁止新增** GeneticVariant/Allele Class）。

## 3. HAS_SYMPTOM / 具有症状

- Domain: Disease；Range: Symptom。
- 方向: Directed。
- 例子: AlzheimerDisease hasSymptom MemoryImpairment。
- Role: Canonical。
- 边界: 表示常见/报道临床表现，非所有患者必然。

## 4. ACTS_ON / 作用于

- Domain: Neurotransmitter；Range: Receptor。
- 方向: Directed。
- 例子: Dopamine actsOn D2Receptor；Glutamate actsOn NMDAReceptor。
- Role: Canonical。
- 边界: 不扩展 pharmacology hierarchy。

---

## 汇总

| Source | Relation | Target | 方向 | Role |
|---|---|---|---|---|
| Gene/Neurotransmitter | modulates | BrainRegion/Circuit/Function | Directed | Canonical |
| Gene | increasesRiskOf | Disease | Directed | Canonical |
| Disease | hasSymptom | Symptom | Directed | Canonical |
| Neurotransmitter | actsOn | Receptor | Directed | Canonical |

## 禁止扩展

- 不展开 protein interactions、drug relations、molecular pathway、cell ontology relations、detailed disease causality、clinical treatment relations。
- 不新增 GeneticVariant / Allele Class。
