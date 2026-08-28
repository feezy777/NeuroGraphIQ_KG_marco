# Gate 6D — TBox / ABox Function Model

Ontology IRI: `https://neurographiq.org/ontology/human-brain`

---

## 1. TBox（Class hierarchy，不变）

```
Function
└─ CognitiveFunction（rdfs:subClassOf Function）
```

- `CognitiveFunction rdfs:subClassOf Function` 保持不变。

## 2. ABox（canonical Function Individual，未来数据）

- WorkingMemory、Memory、Attention、SelectiveAttention、EpisodicMemory 等 → 未来作为 Function/CognitiveFunction 的 **Individual**。

例：
- `WorkingMemory rdf:type CognitiveFunction`
- `Memory rdf:type CognitiveFunction`
- `WorkingMemory subFunctionOf Memory`

## 3. 两个层面

| 层面 | 关系 | 例子 |
|---|---|---|
| Class membership | rdf:type | WorkingMemory rdf:type CognitiveFunction |
| ABox Function hierarchy | subFunctionOf | WorkingMemory subFunctionOf Memory |

## 4. 为什么不写 rdfs:subClassOf

WorkingMemory / Memory 是 canonical Function entities（Individual），不是新 OWL Class。因此不写 `WorkingMemory rdfs:subClassOf Memory`，而写 `WorkingMemory subFunctionOf Memory`。

## 5. 本轮不创建 Function Individual

本轮 Named Class 保持 23；具体 function term 未来作为 Individual 数据进入。
