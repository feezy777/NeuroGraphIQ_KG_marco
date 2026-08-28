# Gate 6F-A — Reference Space and Version

Ontology IRI: `https://neurographiq.org/ontology/human-brain`

---

## 1. 空间关系必须考虑

- reference_space
- atlas_version
- registration_method
- overlap metric
- source geometry
- confidence

这些丰富属性优先 PostgreSQL。

## 2. Atlas version 影响

Julich-Brain vX vs vY 边界可能变化，故 adjacentTo / spatiallyOverlaps 不能无视 version 成为绝对事实。

## 3. OWL vs DB

- OWL 只适合稳定 coarse semantic。
- 具体 ratio / version / space / method 保留数据库。
- 空间关系因依赖这些数值属性，不适合 OWL canonical truth。
