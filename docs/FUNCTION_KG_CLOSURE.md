# Function KG Closure（P1 收口架构）

最终稳定架构：Function 在 Mirror 与 Final 两层都以 **ontology_terms.id** 为唯一
canonical identity，三层（Relation / Triple / Promotion）闭环。

## 1. Function identity

```
ontology_terms.id   ← 唯一 canonical Function identity
ontology_terms.term_code (ng:func:*) ← 稳定逻辑 IRI
```

- Mirror 与 Final **共享**同一个概念身份；任何层都不创建新的 Function Entity。
- `function_term / function_term_en / function_term_cn` 只作为 source text /
  display snapshot / provenance —— **永不参与身份**。

## 2. Mirror relations（domain fact / source of truth）

| 表 | subject | identity |
|---|---|---|
| mirror_region_functions | region_candidate_id | subject + term_id + category + relation_type |
| mirror_projection_functions | projection_id | subject + term_id + category + relation_type |
| mirror_circuit_functions | circuit_id | subject + term_id + domain + role + effect_type |

- 写路径统一走 resolver（resolve_or_propose_function_term + anchor_function_relation）。
- `mirror_region_circuits.function_association` 已降级为 display/legacy snapshot。

## 3. Mirror projection（Triple = graph projection）

- 增量：`function_triple_projection_service.reconcile_function_subject`
  —— subject-scope desired-state reconcile，复用 P1.5 builder。
- 全量：`rebuild_function_triples`（integrity repair / migration）。
- 两者共用 `apply_desired_diff` → **zero-diff 保证**。
- Triple：subject（镜像主体）--predicate--> Function（object_id=term_id）。

## 4. Promotion（Mirror → Final）

- Eligibility：review/validation 通过 + **canonical active term 才可晋升**
  （proposed/deprecated/invalid/missing → blocker；merged resolve 后末端 active 才放行）。
- parent gate：projection/circuit 的 Final 主体必须先晋升（parent_not_promoted blocker）。
- 同事务：eligibility → final relation → final triple → status →（run 级）commit。

## 5. Final relations

| 表 | subject | 关键字段 |
|---|---|---|
| final_region_functions | region_candidate_id（region 无独立 final 表） | term_id、source_mirror_function_id |
| final_projection_functions | final_projection_id | term_id、source_mirror_id、final_uid |
| final_circuit_functions | final_circuit_id | term_id、source_mirror_id、final_uid |

- 幂等：source_mirror_id / final_uid / business key。
- `promote_circuit_function` 已从 preview-only 改为正式落库。

## 6. Final triples

- 从 **Final Function Relation 投影**（不复制 Mirror Triple）：
  subject=Final entity id、object_type='function'、object_id=ontology_terms.id、
  object_label=canonical name snapshot。
- lineage：source_final_relation_id + source_mirror_relation_id。

## 7. Ontology lifecycle

- auto-propose：新文本经匹配阶梯无命中 → proposed term（治理台激活）。
- merge：relation/triple 级联重指 canonical（Mirror 增量投影 + Final 传播），
  duplicate-safe，不留 merged reference。
- rename：受控 refresh 只刷新 object_label，identity/canonical_key 不变。

## 8. Rebuild / integrity

- `check_function_kg_integrity()`（A..H 八段）
- `check_function_kg_invariants()`（INV-F01..F12）
- `rebuild_function_triples(dry_run)` zero-diff 是验收门槛。

## 9. Legacy fields

- `function_association`：保留（display/snapshot/prompt/export/validation），
  不再是事实源。
- function text 三列：保留为 snapshot/provenance。
- 已删除：提取路径直接写 Function Triple 的旧 helper。

## 10. Invariants（已晋升有效 Function）

```
Mirror Relation.term_id
= Mirror Triple.object_id
= Final Relation.term_id
= Final Triple.object_id
= ontology_terms.id
```

- INV-F01..F12 由 `check_function_kg_invariants()` 强制（见
  `backend/app/services/function_kg_integrity_service.py`）。
