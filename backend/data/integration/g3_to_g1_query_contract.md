# G3→G1 Aggregation Query Contract

**Freeze**: `G3_G1_AGGREGATION_FINAL_FREEZE_V1` — production DB `neurographiq_human_brain_v1`, table `brain_region_aggregation_mappings`.

## A. Formal primary G3→G1 (hierarchical parent)
```sql
SELECT * FROM brain_region_aggregation_mappings
WHERE mapping_relation = 'contained_in'
  AND record_status    = 'active'
  AND review_status    = 'approved'
  AND rollup_eligible  = TRUE
  AND is_primary_rollup= TRUE;
```
→ 172 rows, 172 distinct G3 sources. This is the ONLY query that yields hierarchical parents.

## B. All formal relations
```sql
SELECT * FROM brain_region_aggregation_mappings
WHERE record_status = 'active'
  AND review_status = 'approved';
```
→ 246 rows (contained 172 + dominant 34 + partial 40).

## C. Overlap relations (spatial only — never hierarchy)
```sql
SELECT * FROM brain_region_aggregation_mappings
WHERE record_status = 'active' AND review_status = 'approved'
  AND mapping_relation IN ('dominant_overlap','partial_overlap');
```
→ 74 rows (dominant 34 + partial 40). These are spatial relations only; **rollup_eligible / is_primary_rollup are always FALSE** — they are NOT hierarchical parents.

## D. Reverse G1→G3
Query the same mapping table backwards — no second reverse mapping set.
```sql
SELECT target_region_pk, count(DISTINCT source_region_pk)
FROM brain_region_aggregation_mappings
WHERE record_status='active' AND review_status='approved'
  AND mapping_relation='contained_in' AND rollup_eligible=TRUE
GROUP BY target_region_pk;
```
Contained children sum to 172. Reverse query respects hemisphere (never cross-hemisphere).

## E. NO_G1_ROLLUP / CONFLICT_REVIEW
These decisions never appear in `brain_region_aggregation_mappings`. They live only in the frozen decision artifacts (`g3_to_g1_final_scientific_decisions.*`, `g3_to_g1_full_decision_coverage_manifest.*`, `g3_to_g1_mapping_candidate_exclusions.csv`). No query on the aggregation table will ever return them.

## Lifecycle invariants
- `approved` = scientific relation confirmed. `active` = formal knowledge.
- Roll-up (hierarchical inference) is enabled ONLY via query A (contained_in + active + approved + rollup + primary).
- dominant_overlap / partial_overlap are formal knowledge but never participate in roll-up.
