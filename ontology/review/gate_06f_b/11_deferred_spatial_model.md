# Gate 6F-B — Deferred Spatial Model

Ontology IRI: `https://neurographiq.org/ontology/human-brain`

---

## 1. 未来候选（非 V1 blocker）

- `brain_region_spatial_relations` 表：overlap / adjacency / containment / distance + reference_space / atlas_version / source_representation / target_representation / metric / confidence。
- SpatialRepresentation OWL Class（当前 DB 表已足够）。
- symmetric 公理（若未来 OWL spatial relation 需要）。

## 2. 本轮不新增

- 不新增第 33 张科学表（Gate 7A 保持 32）。
- 不正式设计完整 schema，只记录方向。

## 3. 未来 target 方向

更合理：source_spatial_representation / target_spatial_representation（非简单 source_brain_region / target_brain_region），因关系首先发生在 geometry representation 之间。
