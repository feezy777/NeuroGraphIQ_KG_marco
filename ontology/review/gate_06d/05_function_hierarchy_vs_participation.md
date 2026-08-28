# Gate 6D — Function Hierarchy vs Participation

Ontology IRI: `https://neurographiq.org/ontology/human-brain`

---

## 1. subFunctionOf vs participatesIn

| 关系 | 语义 | 例子 |
|---|---|---|
| participatesIn | BrainRegion 参与某功能 | PrefrontalCortex participatesIn WorkingMemory |
| subFunctionOf | Function 概念上下位 | WorkingMemory subFunctionOf Memory |

- participatesIn：脑区 → 功能。
- subFunctionOf：功能 → 功能。
- 两者 Domain/Range 完全不同。

## 2. subFunctionOf vs hasFunction

| 关系 | 语义 | 例子 |
|---|---|---|
| hasFunction | Circuit 关联功能 | Circuit-X hasFunction WorkingMemory |
| subFunctionOf | Function 层级 | WorkingMemory subFunctionOf Memory |

## 3. 不设 property chain

禁止：
```
BrainRegion participatesIn Function
+ Function subFunctionOf Function
→ BrainRegion participatesIn broader Function
```
这类推理留后续 Reasoning Gate，本轮只定义 relation semantic。
