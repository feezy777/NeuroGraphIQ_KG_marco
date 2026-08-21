# Allen Mouse Brain Connectivity Reverse Validation PoC Report

**Generated**: 2026-08-12T02:46:48.915190+00:00

**Connections processed**: 30

## API Metrics

- **Total API requests**: 96
- **Cache hits**: 30
- **Cache hit rate**: 23.8%

## Summary Table

| # | Source | Target | Result | Experiments | Density (median) | Category |
|---|--------|--------|--------|-------------|------------------|----------|
| 1 | Prelimbic area, layer 2/3 | Agranular insular area, dorsal | atlas_supported_candidate | 48 | 0.0003 | high_confidence |
| 2 | Medial visual area, layer 2/3 | Retrosplenial area, ventral pa | atlas_supported_candidate | 50 | 0.0014 | high_confidence |
| 3 | Medial visual area,layer 5 | Medial visual area, layer 6b | atlas_not_observed | 50 | - | high_confidence |
| 4 | Secondary motor area, layer 5 | Infralimbic area, layer 2/3 | atlas_supported_candidate | 49 | 0.0002 | high_confidence |
| 5 | Main olfactory bulb, glomerula | Entorhinal area, lateral part, | atlas_supported_candidate | 3 | 0.0007 | high_confidence |
| 6 | Frontal pole, layer 2/3 | Posterior parietal association | atlas_supported_candidate | 38 | 0.0414 | high_confidence |
| 7 | Rostrolateral lateral visual a | Superior colliculus, motor rel | atlas_supported_candidate | 48 | 0.0000 | high_confidence |
| 8 | Visual areas, layer 2/3 | Visual areas, layer 5 | atlas_not_observed | 49 | - | high_confidence |
| 9 | Parabrachial nucleus, lateral  | Parabrachial nucleus, lateral  | atlas_supported_candidate | 2 | 0.0000 | high_confidence |
| 10 | Primary somatosensory area, la | external capsule | atlas_not_observed | 3 | - | high_confidence |
| 11 | Dorsal peduncular area, layer  | external capsule | atlas_supported_candidate | 3 | 0.0001 | low_confidence |
| 12 | Entorhinal area, medial part,  | Paraflocculus, granular layer | atlas_not_observed | 49 | - | low_confidence |
| 13 | Laterolateral anterior visual  | Presubiculum, layer 3 | atlas_supported_candidate | 46 | 0.0000 | low_confidence |
| 14 | Presubiculum, layer 1 | Lobules IV-V, molecular layer | atlas_supported_candidate | 4 | 0.0103 | low_confidence |
| 15 | Laterolateral anterior visual  | Nucleus of the lateral olfacto | atlas_supported_candidate | 46 | 0.0000 | low_confidence |
| 16 | Posterior auditory area, layer | Agranular insular area, poster | atlas_supported_candidate | 42 | 0.0001 | low_confidence |
| 17 | Somatosensory areas, layer 5 | Cortical amygdalar area, poste | atlas_supported_candidate | 50 | 0.0000 | low_confidence |
| 18 | Dorsal auditory area, layer 6a | Orbital area, medial part, lay | atlas_supported_candidate | 44 | 0.0000 | low_confidence |
| 19 | Mediomedial posterior visual a | Paraventricular hypothalamic n | atlas_supported_candidate | 50 | 0.0000 | low_confidence |
| 20 | posteromedial visual area, lay | Agranular insular area, ventra | atlas_supported_candidate | 44 | 0.0000 | low_confidence |
| 21 | Rostrolateral lateral visual a | Superior colliculus, motor rel | atlas_supported_candidate | 48 | 0.0001 | positive_control |
| 22 | Mediomedial posterior visual a | Superior colliculus, motor rel | atlas_supported_candidate | 50 | 0.0007 | positive_control |
| 23 | Posterolateral visual area, la | Superior colliculus, motor rel | atlas_supported_candidate | 39 | 0.0000 | positive_control |
| 24 | Primary somatosensory area, ba | Primary somatosensory area, mo | atlas_supported_candidate | 47 | 0.0000 | positive_control |
| 25 | Mediomedial anterior visual ar | Superior colliculus, motor rel | atlas_supported_candidate | 50 | 0.0000 | positive_control |
| 26 | Retrosplenial area, lateral ag | Field CA1, stratum oriens | atlas_supported_candidate | 49 | 0.0000 | random_fill |
| 27 | Primary somatosensory area, lo | Medial visual area | atlas_not_observed | 46 | - | random_fill |
| 28 | Mediomedial anterior visual ar | Temporal association areas, la | atlas_supported_candidate | 50 | 0.0009 | random_fill |
| 29 | Rostrolateral area, layer 4 | Cerebellar cortex, molecular l | atlas_not_observed | 46 | - | random_fill |
| 30 | Primary somatosensory area, up | Retrosplenial area, dorsal par | atlas_supported_candidate | 41 | 0.0002 | random_fill |

## Classification Breakdown

| Classification | Count |
|----------------|-------|
| atlas_supported_candidate | 24 |
| atlas_not_observed | 6 |
| atlas_no_data | 0 |
| atlas_mapping_uncertain | 0 |
| atlas_conflicting_experiments | 0 |

## Breakdown by Original Category

| Category | Total | Supported | Not Observed | No Data | Uncertain | Conflicting |
|----------|-------|-----------|-------------|---------|-----------|-------------|
| high_confidence | 10 | 7 | 3 | 0 | 0 | 0 |
| low_confidence | 10 | 9 | 1 | 0 | 0 | 0 |
| positive_control | 5 | 5 | 0 | 0 | 0 | 0 |
| random_fill | 5 | 3 | 2 | 0 | 0 | 0 |

## 5 Interesting Cases

### Case 1: Mediomedial anterior visual area, layer 6b -> Temporal association areas, layer 6a

- **Result**: atlas_supported_candidate
- **Source**: Mediomedial anterior visual area, layer 6b (Allen ID: 480149282, `VISmma6b`)
- **Target**: Temporal association areas, layer 6a (Allen ID: 729, `TEa6a`)
- **Experiments**: 50 total, 39 with projection signal
- **Density**: min=0.0, median=0.0009096389463378359, max=0.0489661172032356
- **Energy**: min=0.0, median=0.4577406264684005, max=42.6756134033203
- **Hierarchy**: sibling
- **Match Type**: ancestor_2_levels_up
- **Reason**: 39/50 experiments show projection from Mediomedial anterior visual area, layer 6b (matched=ancestor_2_levels_up, struct_id=894) to Temporal association areas, layer 6a (density median=0.0009096389463378359, total projection rows=50)

### Case 2: Primary somatosensory area, barrel field, layer 6a -> Primary somatosensory area, mouth, layer 4

- **Result**: atlas_supported_candidate
- **Source**: Primary somatosensory area, barrel field, layer 6a (Allen ID: 1038, `SSp-bfd6a`)
- **Target**: Primary somatosensory area, mouth, layer 4 (Allen ID: 950, `SSp-m4`)
- **Experiments**: 47 total, 36 with projection signal
- **Density**: min=0.0, median=0.0, max=0.00371807580813766
- **Energy**: min=0.0, median=0.0, max=5.98697328567505
- **Hierarchy**: sibling
- **Match Type**: exact_primary
- **Reason**: 36/47 experiments show projection from Primary somatosensory area, barrel field, layer 6a (matched=exact_primary, struct_id=1038) to Primary somatosensory area, mouth, layer 4 (density median=0.0, total projection rows=50)

### Case 3: Prelimbic area, layer 2/3 -> Agranular insular area, dorsal part, layer 2/3

- **Result**: atlas_supported_candidate
- **Source**: Prelimbic area, layer 2/3 (Allen ID: 304, `PL2/3`)
- **Target**: Agranular insular area, dorsal part, layer 2/3 (Allen ID: 328, `AId2/3`)
- **Experiments**: 48 total, 35 with projection signal
- **Density**: min=0.0, median=0.00032161271259675253, max=0.0509462393820286
- **Energy**: min=0.0, median=0.20751822739839598, max=285.519012451172
- **Hierarchy**: sibling
- **Match Type**: exact_primary
- **Reason**: 35/48 experiments show projection from Prelimbic area, layer 2/3 (matched=exact_primary, struct_id=304) to Agranular insular area, dorsal part, layer 2/3 (density median=0.00032161271259675253, total projection rows=50)

### Case 4: Medial visual area, layer 2/3 -> Retrosplenial area, ventral part, layer 2/3

- **Result**: atlas_supported_candidate
- **Source**: Medial visual area, layer 2/3 (Allen ID: 480149322, `VISm2/3`)
- **Target**: Retrosplenial area, ventral part, layer 2/3 (Allen ID: 430, `RSPv2/3`)
- **Experiments**: 50 total, 35 with projection signal
- **Density**: min=0.0, median=0.00136904703686014, max=0.0816100910305977
- **Energy**: min=0.0, median=2.55848045957126, max=703.771728515625
- **Hierarchy**: sibling
- **Match Type**: ancestor_2_levels_up
- **Reason**: 35/50 experiments show projection from Medial visual area, layer 2/3 (matched=ancestor_2_levels_up, struct_id=894) to Retrosplenial area, ventral part, layer 2/3 (density median=0.00136904703686014, total projection rows=50)

### Case 5: Laterolateral anterior visual area, layer 2/3 -> Nucleus of the lateral olfactory tract, molecular layer

- **Result**: atlas_supported_candidate
- **Source**: Laterolateral anterior visual area, layer 2/3 (Allen ID: 480149238, `VISlla2/3`)
- **Target**: Nucleus of the lateral olfactory tract, molecular layer (Allen ID: 260, `NLOT1`)
- **Experiments**: 46 total, 35 with projection signal
- **Density**: min=0.0, median=2.63338194975832e-05, max=0.0364095
- **Energy**: min=0.0, median=0.007905550012255945, max=12.202919960022
- **Hierarchy**: sibling
- **Match Type**: ancestor_2_levels_up
- **Reason**: 35/46 experiments show projection from Laterolateral anterior visual area, layer 2/3 (matched=ancestor_2_levels_up, struct_id=1011) to Nucleus of the lateral olfactory tract, molecular layer (density median=2.63338194975832e-05, total projection rows=50)

## Paper Evidence Comparison

No connections with existing Paper Evidence were found in the sample.

## Recommendations for 64K Full Validation

1. **Caching strategy**: The module-level cache works well for a single run. For 64K connections, consider a persistent cache (Redis or SQLite) to avoid redundant API calls.
2. **Rate limiting**: Allen API has rate limits. The current retry logic handles 429s, but for 64K connections, concurrency control (semaphore) and backpressure are needed.
3. **Structure hierarchy resolution**: Many connections may be between parent/child structures in the Allen ontology. Add logic to aggregate projection signal at the appropriate hierarchy level.
4. **Batch processing**: Group connections by source structure to minimize API calls (injection experiments only need to be queried once per source).
5. **Mapping quality**: The `source_match_type` field already tracks whether the injection is exactly primary or at a descendant level. This helps filter low-quality mappings.
6. **Signal thresholds**: Consider adding minimum density/energy thresholds for 'supported' classification (e.g., density > 0.01). Currently any non-zero signal counts.
7. **Hemisphere awareness**: Allen projections are hemisphere-specific. Connections between left and right sides should account for this.
