# Gate 6D — Function Hierarchy Overview

Ontology IRI: `https://neurographiq.org/ontology/human-brain`
version: `0.6.1-gate6c` → `0.6.2-gate6d`
本轮状态: **已正式写入 TTL，等待 Protégé 人工审查**

---

## 1. 目标

解决"Function canonical concept 之间如何表达更细功能属于更宽泛功能"。

## 2. 本轮新增

| 关系 | 中文 | 说明 |
|---|---|---|
| subFunctionOf | 是……的下位功能 | Function 语义层级（ABox） |

## 3. 为什么需要

当前 TBox 只有 `Function └─ CognitiveFunction`（Class hierarchy）。但真实数据（Memory / WorkingMemory / Attention / SelectiveAttention）按 TBox/ABox policy 是 **Individual**，不能写 `WorkingMemory rdfs:subClassOf Memory`。故需专门 Function→Function ObjectProperty。

## 4. 版本与统计

| 项 | 值 |
|---|---|
| version | 0.6.2-gate6d |
| Named Class | 23 |
| ObjectProperty | 26（+subFunctionOf） |
| DataProperty | 0 |
| Named Individual | 0 |
| imports | 0 |

## 5. 不新增

- 不新增 Function Individual（WorkingMemory/Memory 等未来为 Individual）。
- 不新增 Function part_of 正式 OWL relation（DEFER）。
- 不新增 hasSubFunction / functionPartOf / partOfFunction / componentFunctionOf。
- 不设置 TransitiveProperty / inverseOf / propertyChainAxiom。
- 不新增 DataProperty / Class。
