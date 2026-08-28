# Gate 6B — Domain / Range Review（域与值域审查）

Ontology IRI: `https://neurographiq.org/ontology/human-brain`
version: `0.6.0-gate6b`

---

## 1. 关键：unionOf 正确使用

多个 `rdfs:domain` / `rdfs:range` 会被 OWL 解释为**交集**（AND），不是 OR。union 必须用 `owl:unionOf`。

### participatesIn（range = Circuit ∪ Function）

```turtle
rdfs:range [ owl:unionOf ( ngiq:Circuit ngiq:Function ) ] ;
```

✅ 正确：Circuit OR Function。

❌ 错误写法（会产生 Circuit ∩ Function 语义）：
```turtle
rdfs:range ngiq:Circuit ;
rdfs:range ngiq:Function .
```

### modulates（domain = Gene ∪ Neurotransmitter；range = BrainRegion ∪ Circuit ∪ Function）

```turtle
rdfs:domain [ owl:unionOf ( ngiq:Gene ngiq:Neurotransmitter ) ] ;
rdfs:range  [ owl:unionOf ( ngiq:BrainRegion ngiq:Circuit ngiq:Function ) ] ;
```

✅ 正确。

## 2. 单值 Domain/Range 属性

其余属性 Domain/Range 均为单 Class，直接 `rdfs:domain` / `rdfs:range`，无交集风险。

## 3. 不做过强推理

- 本 Gate 目标仍是轻量但明确的 OWL schema，Domain/Range 用于 schema 约束，不追求强自动 typing。
- hasFunction 只设 Circuit → Function；BrainRegion→Function 走 participatesIn。
- hasSourceRegion/hasTargetRegion 通过 subPropertyOf hasEndpointRegion 支持 endpoint 推理。
