# Gate 6G-A — Canonical vs Derived Audit

---

## 结果：PASS（0 issue，无两份 independent canonical truth）

| Canonical truth | Derived projection |
|---|---|
| Connection entity + endpoint/source/target | structurallyConnectedTo / functionallyConnectedTo / projectsTo / effectivelyConnectedTo |
| CircuitConnectionMembership | hasConnection |
| RegionMapping（mappingSource/mappingTarget） | mapsTo |

- 上述 derived 关系是查询/Neo4j 投影，不是第二份 canonical truth。
