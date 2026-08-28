# Gate 6G-A — Label / Definition Audit

---

## 结果：PASS（1 MINOR）

- 23 Class + 26 ObjectProperty 均有 en + zh label + comment。
- 中文 label 科学准确（Connection/Projection/FunctionalConnectivity/EffectiveConnectivity/Circuit/Evidence/subFunctionOf/partOf/subfieldOf 等）。
- 无 Macro96-era 残留定义（96 region / Macro96-only / ≥3 region circuit / pair assessment / mouse data / old ConnectionType）作为 ontology definition。

## MINOR-1

- 文件名 `neurographiq_macro96_v1.ttl` 仍含 "macro96"（工程文件名，非 ontology identity；本轮不重命名）。
