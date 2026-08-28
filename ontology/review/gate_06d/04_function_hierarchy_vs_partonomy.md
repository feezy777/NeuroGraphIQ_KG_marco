# Gate 6D — Function Hierarchy vs Partonomy

Ontology IRI: `https://neurographiq.org/ontology/human-brain`

---

## 1. 两者不同

| 关系 | 语义 | Domain/Range |
|---|---|---|
| partOf / subfieldOf | BrainRegion anatomical partonomy（解剖组成） | BrainRegion → BrainRegion |
| subFunctionOf | Function semantic hierarchy（功能特化） | Function → Function |

## 2. 禁止复用 partOf 于 Function

- 禁止 `WorkingMemory partOf Memory`。
- partOf Domain/Range 已冻结为 BrainRegion，用于 Function 会引发错误类型推断。

## 3. 禁止 subFunctionOf subPropertyOf partOf

- subFunctionOf 与 partOf 完全不同，不建立 subProperty 关系。
- 本轮验证：subPropertyOf 仍为 4 条（projectsTo / hasSourceRegion / hasTargetRegion / subfieldOf），无 subFunctionOf ⊑ partOf。

## 4. Function part_of 暂缓（DEFER）

- DB function_hierarchy_relations.relation_type 仍允许 part_of（不删）。
- 但 OWL 暂不新增 functionPartOf / partOfFunction / componentFunctionOf / hasFunctionalComponent。
- 原因：encoding / retrieval / maintenance / updating 等"功能组成"可能属 NeurobiologicalProcess / cognitive operation / task component，需后续单独科学审查。
