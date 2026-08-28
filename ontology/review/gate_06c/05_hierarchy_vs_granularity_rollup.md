# Gate 6C — Hierarchy vs Granularity Roll-up

Ontology IRI: `https://neurographiq.org/ontology/human-brain`

---

## 1. 关键区分

- **partOf / subfieldOf**（OWL）= canonical anatomical hierarchy truth（如 CA1 subfieldOf Hippocampus）。
- **Granularity G1–G4**（PostgreSQL）= 知识抽象尺度，用于 roll-up / 展示 / 查询。
- **brain_region_aggregation_mappings**（PostgreSQL）= cross-granularity integration truth（G4→G3→G2→G1）。

三者语义不同，不混。

## 2. Granularity 不进 OWL

- 本轮**禁止**创建 granularity DataProperty。
- Granularity 仍属 PostgreSQL / Integration model。

## 3. 不新增 Spatial Relations

- 禁止 overlaps / locatedIn / adjacentTo（未来 Spatial Relation Gate）。

## 4. roll-up 语义（数据库层）

- 细→粗 roll-up（G4→G3→G2→G1）由 brain_region_aggregation_mappings 表达。
- Connection/Circuit roll-up 产物 derivation_type=inferred。
- 不是 strict tree；允许 skip-level；支持 N→1 与 1→N。
- 详见 `ontology/review/gate_07a_data_dictionary/25_cross_granularity_rollup_policy.md`。
