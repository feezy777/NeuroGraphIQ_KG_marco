# Gate 6G-B — Semantic Diff Report

---

## 1. 方法

rdflib 7.6.0 解析修改前后 TTL，`rdflib.compare.isomorphic` 比较（排除 `owl:versionInfo`）。

## 2. 结果

| 项 | 值 |
|---|---|
| old_hash | 7ccc888b3c01a0c7063203e890490ca0fc1c36feac6efbcb3c3f5962ae96cb4d |
| new_hash | 37e0e3aff4aca4c4f898fba0f7b1c0b6121fe086725d89517db9601c0fe7b790 |
| isomorphic（排除 versionInfo） | True |
| **semantic_diff_count** | **0** |

## 3. 结论

排除 version metadata 后语义完全一致；本轮仅修改 version metadata。
