# BrainRegion Integration — Phase 2I-C Gate Report
## Final Owner Scientific Decision Freeze (440 canonical G4)

**Date:** 2026-09-03
**Branch:** develop (no commit / no push). **DB writes:** none. **Overlap recompute:** none. **2G/2H/2I-A/2I-B artifacts:** untouched. **Staging / approval / promotion:** none.

---

## Result

**G4_G3_SCIENTIFIC_DECISIONS_FROZEN** — one final source-level decision per canonical G4 (440 unique), `owner_review_status=OWNER_SCIENTIFIC_REVIEWED` (metadata only, not production approval).

## Final ledger composition (sum = 440)

| decision | count |
|---|---|
| APPROVE_CONTAINED_IN | **20** |
| APPROVE_DOMINANT_OVERLAP | **110** |
| PARTIAL_OVERLAP | **137** |
| NO_G3_MAPPING | **18** (frozen) |
| CONFLICT_REVIEW | **91** |
| SHARED_SPATIAL_EVIDENCE_ONLY | **64** (frozen) |

### Key owner decisions applied
- VTM (Amygdala) L `00000370` → **CONFLICT_REVIEW**, SEMANTIC_FAMILY_MISMATCH, rollup FALSE.
- Ph3 (PhG) R `00000591` → **APPROVE_DOMINANT_OVERLAP**, STRONG_SPATIAL_OVERLAP_BUT_NOT_HIERARCHICAL_CONTAINMENT, rollup FALSE.
- FG5 (FusG) R `00000599` → **APPROVE_CONTAINED_IN**, OWNER_SEMANTIC_AND_SPATIAL_CONCORDANCE, rollup TRUE.
- Contained semantic gate on the 20: all EXACT_FAMILY / NESTED_COMPATIBLE_FAMILY → **semantic_contained_failure = 0**, contained_rollup_count = 20.

### Multi-target final gate (21 plausible → freeze)
- **accepted 16** (PARTIAL, e.g. 7M SPL L n3 expl .805, 8v1 MFG R n4 .962, hOc4v LingG L n4 .995) → final partial = 101 + 20 concordant + 16 = **137**.
- **rejected 5** (CONFLICT, MULTI_TARGET_DIFFUSE_REMAINDER: 7M SPL R .742, 45 IFG R .652, Te3 STG L .691, hOc1 CalcS L .713, EC Hipp L .621).
- Operational note recorded: selected_cumulative ≥0.60 and explained_covered_fraction ≥0.75 are **PROJECT_OPERATIONAL thresholds**, not universal neuroscience thresholds.

### Final conflict (91) by reason
LOW_DOMINANCE 6 · HIGH_FRAGMENTATION 50 · PARTIAL_TARGET_EVIDENCE_INCONSISTENT 5 · PROBABILITY_HARDLABEL_TOP1_DISAGREEMENT 15 · DIFFUSE_ASSOCIATION 8 · LOW_BNA_COVERAGE 1 · SEMANTIC_FAMILY_MISMATCH 1 · MULTI_TARGET_DIFFUSE_REMAINDER 5.

## Relation / exclusion files
- `g4_g3_final_relation_decisions.csv` — **461 rows** = contained 20 (1:1) + dominant 110 (1:1) + partial 331 (1:N, no truncation); no NO_MAPPING/CONFLICT/SHARED, no production mapping_id.
- `g4_g3_final_scientific_exclusions.csv` — 173 rows (18 NO_G3_MAPPING + 91 CONFLICT + 64 SHARED) with reasons/provenance.
- `g4_g3_final_scientific_decision_summary.json` — all counts + gate detail + semantic rule + operational-threshold note.

## Integrity
20 + 110 + 137 + 18 + 91 + 64 = 440; each canonical G4 exactly one decision; closure asserted. DB: G3→G1 rows=246 active=246 approved=246 rollup=172; G4→G3 production rows = 0.

## Tests
`backend/tests/test_g4_g3_final_scientific_decisions.py` — **13 passed**. 2I-C + 2I-B + 2I-A combined — **41 passed**.
