# G4→G3 Query Contract (Frozen)

**Status:** G4_G3_AGGREGATION_FROZEN · policy `G4_G3_FINAL_SCIENTIFIC_POLICY_V1`
**Table:** `brain_region_aggregation_mappings`
**Granularity:** source `G4_MICROSTRUCTURAL_FINE` → target `G3_MESO_FINE`

## 1. Primary automatic G4→G3 rollup query

```sql
SELECT * FROM brain_region_aggregation_mappings
WHERE source_granularity_level = 'G4_MICROSTRUCTURAL_FINE'
  AND mapping_relation = 'contained_in'
  AND record_status = 'active'
  AND review_status = 'approved'
  AND rollup_eligible = TRUE
  AND is_primary_rollup = TRUE;
```
**Expected = 20** rows · 20 unique G4 sources · 20 unique primary mappings.

## 2. All formal G4→G3 mappings

```sql
SELECT * FROM brain_region_aggregation_mappings
WHERE source_granularity_level = 'G4_MICROSTRUCTURAL_FINE'
  AND target_granularity_level = 'G3_MESO_FINE'
  AND record_status = 'active'
  AND review_status = 'approved';
```
**Expected = 461** rows. This is the Hierarchy & Mapping / cross-granularity relation layer (not only rollup parents).

## 3. Relation filtering (within the 461)

- `contained_in` = **20**
- `dominant_overlap` = **110**
- `partial_overlap` = **331**

## 4. Reverse G3→G4

Reverse lookup uses the SAME table with `target_granularity_level='G3_MESO_FINE'` and the queried G3 as `target_region_pk`. It is a query over existing rows; no reverse duplicate mapping rows are created (reverse duplicate rows = 0).

## 5. Exclusion semantics

The 173 canonical G4 sources with no formal relation are governed by decisions, NOT by relation rows:

- `NO_G3_MAPPING` = 18
- `CONFLICT_REVIEW` = 91
- `SHARED_SPATIAL_EVIDENCE_ONLY` = 64

They never appear in the G4→G3 formal relation query (exclusion leak = 0). Shared components never produce leaf-level mappings.

## 6. Rollup semantics

Only `contained_in` is eligible for hierarchy rollup (record_status active + review approved + rollup_eligible + is_primary_rollup).
`dominant_overlap` and `partial_overlap` NEVER become automatic hierarchy parents (rollup/primary = 0).
