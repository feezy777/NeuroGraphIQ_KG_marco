# Gate 6F-B — Reference Space and Version

Ontology IRI: `https://neurographiq.org/ontology/human-brain`

---

## 1. Reference Space 必须保留

未来所有 spatial computation 必须保留 reference_space（MNI152 / ICBM / BigBrain / native / atlas-specific）。无明确 reference space 不能把 overlap/adjacency 作为正式 canonical spatial result。

## 2. Atlas Version 必须保留

必须可追踪 atlas / atlas_version / representation version（同一 atlas 不同版本边界可能变）。

## 3. Registration 必须可追踪

跨 space 比较需保留 registration method / transform provenance / source & target space / confidence。不把注册结果伪装成原生 atlas truth。

## 4. 归属

reference_space / atlas_version / registration_method 均属 DB spatial/provenance 上下文，非 OWL 语义。
