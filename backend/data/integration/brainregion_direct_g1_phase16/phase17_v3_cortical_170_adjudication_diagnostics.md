# Phase1.7 V3 - final adjudication of the 170 cortical Brainnetome <-> DK relations

universe: 170 relations | scope: BNA G3_MESO_FINE cortical -> DK-derived G1 cortical
frozen methodology basis: b970f48 CORTICAL_CROSS_ATLAS_SUPPORT_DOMAIN_MISMATCH_CONFIRMED / SPATIALLY_COMPATIBLE
criteria NOT used: absolute containment, COM displacement, raw outside-union fraction, support-domain volume difference.
criteria used as supporting only: relative spatial ranking and GM-weighted margin.

## Final states
- A. VERIFIED_DIRECT_MAPPING: 0
- B. VERIFIED_HIERARCHICAL_MAPPING: 166
- C. PLAUSIBLE_MAPPING_NEEDS_HUMAN_REVIEW: 4
- D. REJECTED_SEMANTIC_MISMATCH: 0
- E. REJECTED_LATERALITY_MISMATCH: 0
- F. UNRESOLVED_INSUFFICIENT_EVIDENCE: 0
- review queue: 4 (weak margin < 0.1 or midline crossing < 0.96)
- excluded BNA cortical parcels (no frozen G1 target, out of scope): 40

## Relation type
all 170 relations are `narrower` (BR3 vocabulary), hierarchy predicate `part_of`; 0 `exact`. Rationale: documented subdivision relation, not volume-based.

## Decision reason codes
- HIER_FINE_SUBDIVISION_OF_MACRO_GYRUS: 170
- LAT_SIDE_CONSISTENT: 170
- SPATIAL_RANK1_RAW_AND_GM: 170
- SEM_EXACT_MACRO_GYRUS_MATCH: 116
- SEM_MACRO_GYRUS_SPLIT_BY_DK: 54

No existing evidence file was modified. No DB access. No new candidate relations.

