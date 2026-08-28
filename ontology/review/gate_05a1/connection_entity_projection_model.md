# Gate 5A.1 — Connection Entity vs Direct Edge（投影模型）

Ontology IRI（当前）: `https://neurographiq.org/ontology/macro96`
本轮状态: **仅原则决定，未建 Property**

---

## 1. 原则性决定

- **Canonical semantic / storage model = Connection entity**。
- 例：
```
Connection C001
  source_region = A
  target_region = B
  rdf:type = Projection
  evidence = E001
  direction = directed
  ...
```
- Connection 需承载：evidence / direction / provenance / confidence / review / inference / source/target / connection class。

## 2. Neo4j 定位

Neo4j 可生成 `(A)-[:PROJECTS_TO]->(B)` 作为 **query / visualization projection**。

- Neo4j direct edge **不是第二份 canonical truth**。
- Canonical truth = Connection entity；Neo4j convenience projection = direct graph relationship。

## 3. 与 PPT 直接 edge 的关系

老师 PPT 的 STRUCTURALLY_CONNECTED_TO / FUNCTIONALLY_CONNECTED_TO / PROJECTS_TO 是 direct edge 表达。它们与本模型的 Connection entity 是 **storage model（entity） vs projection model（direct edge）** 的关系，不冲突、不重复建真。

## 4. 具体 ObjectProperty 后续设计

具体 ObjectProperty（source/target/has_evidence/has_direction 等）留后续 Property Gate。本 Gate 只确定总体原则。

## 5. 结论

| 项 | 决策 |
|---|---|
| Connection canonical representation | reified Connection entity |
| Neo4j direct edge 定位 | derived projection only（非 canonical truth） |
| 具体 ObjectProperty | 后续 Property Gate |
