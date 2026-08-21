# Allen Mouse Brain Connectivity PoC 2.0 Calibration Report

**Generated**: 2026-08-12T06:21:20.504244+00:00

**Original 30 connections**: re-validated with PoC 2.0 pipeline
**New connections**: 170 validated

## API Metrics

| Metric | Value |
|--------|-------|
| API requests | 781 |
| In-memory cache hits | 522 |
| DB cache hits | 73 |
| Total cache hit rate | 43.2% |

## 1. Before/After: Original 30 Connections

| # | Source | Target | V1 Result | V2 Result | V1 Exp | V2 Exp | V1 Den Med | V2 Den Med | Change |
|---|--------|--------|-----------|-----------|--------|--------|------------|------------|--------|
| 1 | Frontal pole, layer 2/3 | Posterior parietal associ | atlas_supported_candidate | direct_support | 38 | 52 | 0.0414 | 0.0449 | **atlas_supported_candidate → direct_support** |
| 2 | Rostrolateral lateral vis | Superior colliculus, moto | atlas_supported_candidate | broad_hierarchical_support | 48 | 133 | 0.0001 | 0.0035 | **atlas_supported_candidate → broad_hierarchical_support** |
| 3 | Medial visual area,layer  | Medial visual area, layer | atlas_not_observed | atlas_not_observed | 50 | 131 | - | - |  |
| 4 | Medial visual area, layer | Retrosplenial area, ventr | atlas_supported_candidate | broad_hierarchical_support | 50 | 131 | 0.0014 | 0.0070 | **atlas_supported_candidate → broad_hierarchical_support** |
| 5 | Primary somatosensory are | external capsule | atlas_not_observed | atlas_not_observed | 3 | 3 | - | - |  |
| 6 | Posterolateral visual are | Superior colliculus, moto | atlas_supported_candidate | direct_support | 39 | 70 | - | 0.0001 | **atlas_supported_candidate → direct_support** |
| 7 | Presubiculum, layer 1 | Lobules IV-V, molecular l | atlas_supported_candidate | direct_support | 4 | 4 | 0.0103 | 0.0117 | **atlas_supported_candidate → direct_support** |
| 8 | Primary somatosensory are | Primary somatosensory are | atlas_supported_candidate | direct_support | 47 | 129 | - | 0.0000 | **atlas_supported_candidate → direct_support** |
| 9 | Parabrachial nucleus, lat | Parabrachial nucleus, lat | atlas_supported_candidate | atlas_not_observed | 2 | 2 | - | - | **atlas_supported_candidate → atlas_not_observed** |
| 10 | Entorhinal area, medial p | Paraflocculus, granular l | atlas_not_observed | atlas_not_observed | 49 | 130 | - | - |  |
| 11 | Primary somatosensory are | Medial visual area | atlas_not_observed | atlas_not_observed | 46 | 80 | - | - |  |
| 12 | Visual areas, layer 2/3 | Visual areas, layer 5 | atlas_not_observed | atlas_not_observed | 49 | 148 | - | - |  |
| 13 | Primary somatosensory are | Retrosplenial area, dorsa | atlas_supported_candidate | direct_support | 41 | 87 | 0.0002 | 0.0003 | **atlas_supported_candidate → direct_support** |
| 14 | Dorsal peduncular area, l | external capsule | atlas_supported_candidate | direct_support | 3 | 3 | 0.0001 | 0.0013 | **atlas_supported_candidate → direct_support** |
| 15 | Rostrolateral lateral vis | Superior colliculus, moto | atlas_supported_candidate | broad_hierarchical_support | 48 | 133 | 0.0000 | 0.0007 | **atlas_supported_candidate → broad_hierarchical_support** |
| 16 | Posterior auditory area,  | Agranular insular area, p | atlas_supported_candidate | direct_support | 42 | 73 | 0.0001 | 0.0014 | **atlas_supported_candidate → direct_support** |
| 17 | Somatosensory areas, laye | Cortical amygdalar area,  | atlas_supported_candidate | hierarchical_support | 50 | 140 | 0.0000 | 0.0000 | **atlas_supported_candidate → hierarchical_support** |
| 18 | Secondary motor area, lay | Infralimbic area, layer 2 | atlas_supported_candidate | direct_support | 49 | 140 | 0.0002 | 0.0122 | **atlas_supported_candidate → direct_support** |
| 19 | Mediomedial posterior vis | Superior colliculus, moto | atlas_supported_candidate | hierarchical_support | 50 | 131 | 0.0007 | 0.0021 | **atlas_supported_candidate → hierarchical_support** |
| 20 | Mediomedial posterior vis | Paraventricular hypothala | atlas_supported_candidate | atlas_not_observed | 50 | 131 | - | - | **atlas_supported_candidate → atlas_not_observed** |
| 21 | Mediomedial anterior visu | Superior colliculus, moto | atlas_supported_candidate | broad_hierarchical_support | 50 | 131 | 0.0000 | 0.0002 | **atlas_supported_candidate → broad_hierarchical_support** |
| 22 | Mediomedial anterior visu | Temporal association area | atlas_supported_candidate | broad_hierarchical_support | 50 | 131 | 0.0009 | 0.0011 | **atlas_supported_candidate → broad_hierarchical_support** |
| 23 | Retrosplenial area, later | Field CA1, stratum oriens | atlas_supported_candidate | direct_support | 49 | 125 | 0.0000 | 0.0000 | **atlas_supported_candidate → direct_support** |
| 24 | Prelimbic area, layer 2/3 | Agranular insular area, d | atlas_supported_candidate | direct_support | 48 | 119 | 0.0003 | 0.0016 | **atlas_supported_candidate → direct_support** |
| 25 | Main olfactory bulb, glom | Entorhinal area, lateral  | atlas_supported_candidate | direct_support | 3 | 3 | 0.0007 | 0.0021 | **atlas_supported_candidate → direct_support** |
| 26 | Dorsal auditory area, lay | Orbital area, medial part | atlas_supported_candidate | atlas_not_observed | 44 | 98 | - | - | **atlas_supported_candidate → atlas_not_observed** |
| 27 | Laterolateral anterior vi | Nucleus of the lateral ol | atlas_supported_candidate | broad_hierarchical_support | 46 | 118 | 0.0000 | 0.0001 | **atlas_supported_candidate → broad_hierarchical_support** |
| 28 | Laterolateral anterior vi | Presubiculum, layer 3 | atlas_supported_candidate | atlas_not_observed | 46 | 118 | - | - | **atlas_supported_candidate → atlas_not_observed** |
| 29 | Rostrolateral area, layer | Cerebellar cortex, molecu | atlas_not_observed | atlas_not_observed | 46 | 103 | - | - |  |
| 30 | posteromedial visual area | Agranular insular area, v | atlas_supported_candidate | direct_support | 44 | 110 | 0.0000 | 0.0000 | **atlas_supported_candidate → direct_support** |

### Reclassification Details (24 changed)

  1. Frontal pole, layer 2/3 → Posterior parietal associ: atlas_supported_candidate → direct_support ([exact_primary] Frontal pole, layer 2/3 → Posterior parietal association areas, )
  2. Rostrolateral lateral vis → Superior colliculus, moto: atlas_supported_candidate → broad_hierarchical_support ([ancestor_2_levels] Rostrolateral lateral visual area, layer 2/3 → Superior coll)
  4. Medial visual area, layer → Retrosplenial area, ventr: atlas_supported_candidate → broad_hierarchical_support ([ancestor_2_levels] Medial visual area, layer 2/3 → Retrosplenial area, ventral )
  6. Posterolateral visual are → Superior colliculus, moto: atlas_supported_candidate → direct_support ([exact_primary] Posterolateral visual area, layer 1 → Superior colliculus, motor)
  7. Presubiculum, layer 1 → Lobules IV-V, molecular l: atlas_supported_candidate → direct_support ([exact_primary] Presubiculum, layer 1 → Lobules IV-V, molecular layer: 4/4 exper)
  8. Primary somatosensory are → Primary somatosensory are: atlas_supported_candidate → direct_support ([exact_primary] Primary somatosensory area, barrel field, layer 6a → Primary som)
  9. Parabrachial nucleus, lat → Parabrachial nucleus, lat: atlas_supported_candidate → atlas_not_observed ([exact_primary] Parabrachial nucleus, lateral division, dorsal lateral part → Pa)
  13. Primary somatosensory are → Retrosplenial area, dorsa: atlas_supported_candidate → direct_support ([exact_primary] Primary somatosensory area, upper limb, layer 2/3 → Retrosplenia)
  14. Dorsal peduncular area, l → external capsule: atlas_supported_candidate → direct_support ([exact_primary] Dorsal peduncular area, layer 1 → external capsule: 2/3 experime)
  15. Rostrolateral lateral vis → Superior colliculus, moto: atlas_supported_candidate → broad_hierarchical_support ([ancestor_2_levels] Rostrolateral lateral visual area, layer 4 → Superior collic)
  16. Posterior auditory area,  → Agranular insular area, p: atlas_supported_candidate → direct_support ([exact_primary] Posterior auditory area, layer 4 → Agranular insular area, poste)
  17. Somatosensory areas, laye → Cortical amygdalar area, : atlas_supported_candidate → hierarchical_support ([ancestor_1_level] Somatosensory areas, layer 5 → Cortical amygdalar area, poste)
  18. Secondary motor area, lay → Infralimbic area, layer 2: atlas_supported_candidate → direct_support ([exact_primary] Secondary motor area, layer 5 → Infralimbic area, layer 2/3: 18/)
  19. Mediomedial posterior vis → Superior colliculus, moto: atlas_supported_candidate → hierarchical_support ([ancestor_1_level] Mediomedial posterior visual area → Superior colliculus, moto)
  20. Mediomedial posterior vis → Paraventricular hypothala: atlas_supported_candidate → atlas_not_observed ([ancestor_1_level] Mediomedial posterior visual area → Paraventricular hypothala)
  21. Mediomedial anterior visu → Superior colliculus, moto: atlas_supported_candidate → broad_hierarchical_support ([ancestor_2_levels] Mediomedial anterior visual area, layer 6b → Superior collic)
  22. Mediomedial anterior visu → Temporal association area: atlas_supported_candidate → broad_hierarchical_support ([ancestor_2_levels] Mediomedial anterior visual area, layer 6b → Temporal associ)
  23. Retrosplenial area, later → Field CA1, stratum oriens: atlas_supported_candidate → direct_support ([exact_primary] Retrosplenial area, lateral agranular part, layer 2/3 → Field CA)
  24. Prelimbic area, layer 2/3 → Agranular insular area, d: atlas_supported_candidate → direct_support ([exact_primary] Prelimbic area, layer 2/3 → Agranular insular area, dorsal part,)
  25. Main olfactory bulb, glom → Entorhinal area, lateral : atlas_supported_candidate → direct_support ([exact_primary] Main olfactory bulb, glomerular layer → Entorhinal area, lateral)
  26. Dorsal auditory area, lay → Orbital area, medial part: atlas_supported_candidate → atlas_not_observed ([exact_primary] Dorsal auditory area, layer 6a → Orbital area, medial part, laye)
  27. Laterolateral anterior vi → Nucleus of the lateral ol: atlas_supported_candidate → broad_hierarchical_support ([ancestor_2_levels] Laterolateral anterior visual area, layer 2/3 → Nucleus of t)
  28. Laterolateral anterior vi → Presubiculum, layer 3: atlas_supported_candidate → atlas_not_observed ([ancestor_2_levels] Laterolateral anterior visual area,layer 5 → Presubiculum, l)
  30. posteromedial visual area → Agranular insular area, v: atlas_supported_candidate → direct_support ([exact_primary] posteromedial visual area, layer 2/3 → Agranular insular area, v)

## 2. Original 30 Re-classification Breakdown

| Classification | V1 Count | V2 Count |
|----------------|----------|----------|
| atlas_not_observed | 6 | 10 |
| atlas_supported_candidate | 24 | 0 |
| broad_hierarchical_support | 0 | 6 |
| direct_support | 0 | 12 |
| hierarchical_support | 0 | 2 |

## 3. 200 Calibration Set Statistics (Total: 200)

### Classification

| Classification | Count | % |
|----------------|-------|---|
| atlas_not_observed | 75 | 37.5% |
| broad_hierarchical_support | 19 | 9.5% |
| direct_support | 92 | 46.0% |
| hierarchical_support | 14 | 7.0% |

### Signal Strength

| Strength | Count |
|----------|-------|
| very_weak | 28 |
| weak | 21 |
| moderate | 43 |
| strong | 33 |

### Consistency

| Consistency | Count |
|-------------|-------|
| single_experiment | 3 |
| low_consistency | 103 |
| moderate_consistency | 13 |
| high_consistency | 6 |

### Source Match Distribution

| Match Type | Count |
|------------|-------|
| ancestor_1_level | 29 |
| ancestor_2_levels | 24 |
| exact_primary | 147 |

### Hierarchy Relations

| Relation | Count |
|----------|-------|
| sibling | 200 |

## 4. Paper Evidence Comparison

*No connections with existing Paper Evidence in sample.*


## 5. Top 10 Interesting Cases (by positive experiment count)

### 1. Primary motor area, Layer 5 → Secondary motor area, layer 2/3

- **Result**: direct_support | Signal: strong | Consistency: low_consistency
- **Source**: Allen ID=648 (`MOp5`), Match: exact_primary (dist=0)
- **Target**: Allen ID=962 (`MOs2/3`)
- **Experiments**: 28/135 positive (ratio=0.21)
- **Density (positive)**: min=5.84113477088977e-05, median=0.023894, max=0.542057
- **Relation**: sibling | Hemisphere: bilateral
- **Pagination**: complete=False, fetched=150/576
- **Reason**: [exact_primary] Primary motor area, Layer 5 → Secondary motor area, layer 2/3: 28/135 experiments, signal=strong, consistency=low_consistency, pos_density_median=0.023894, pos_energy_median=78.1230

### 2. Primary motor area, Layer 6a → Primary somatosensory area, barrel field, layer 1

- **Result**: direct_support | Signal: strong | Consistency: low_consistency
- **Source**: Allen ID=844 (`MOp6a`), Match: exact_primary (dist=0)
- **Target**: Allen ID=981 (`SSp-bfd1`)
- **Experiments**: 28/130 positive (ratio=0.22)
- **Density (positive)**: min=5.16802401762106e-06, median=0.001620, max=0.633101
- **Relation**: sibling | Hemisphere: bilateral
- **Pagination**: complete=False, fetched=150/556
- **Reason**: [exact_primary] Primary motor area, Layer 6a → Primary somatosensory area, barrel field, layer 1: 28/130 experiments, signal=strong, consistency=low_consistency, pos_density_median=0.001620, pos_energy_median=0.7556

### 3. Frontal pole, layer 5 → lateral olfactory tract, body

- **Result**: direct_support | Signal: strong | Consistency: moderate_consistency
- **Source**: Allen ID=526157192 (`FRP5`), Match: exact_primary (dist=0)
- **Target**: Allen ID=665 (`lot`)
- **Experiments**: 28/89 positive (ratio=0.31)
- **Density (positive)**: min=3.57047e-07, median=0.000766, max=0.242189
- **Relation**: sibling | Hemisphere: bilateral
- **Pagination**: complete=False, fetched=150/201
- **Reason**: [exact_primary] Frontal pole, layer 5 → lateral olfactory tract, body: 28/89 experiments, signal=strong, consistency=moderate_consistency, pos_density_median=0.000766, pos_energy_median=0.1856

### 4. Primary somatosensory area, lower limb, layer 2/3 → Primary visual area, layer 2/3

- **Result**: direct_support | Signal: weak | Consistency: moderate_consistency
- **Source**: Allen ID=113 (`SSp-ll2/3`), Match: exact_primary (dist=0)
- **Target**: Allen ID=821 (`VISp2/3`)
- **Experiments**: 27/80 positive (ratio=0.34)
- **Density (positive)**: min=2.62201593770328e-10, median=0.000028, max=0.008897
- **Relation**: sibling | Hemisphere: bilateral
- **Pagination**: complete=False, fetched=150/171
- **Reason**: [exact_primary] Primary somatosensory area, lower limb, layer 2/3 → Primary visual area, layer 2/3: 27/80 experiments, signal=weak, consistency=moderate_consistency, pos_density_median=0.000028, pos_energy_median=0.0054

### 5. Visceral area, layer 5 → lateral olfactory tract, body

- **Result**: direct_support | Signal: strong | Consistency: moderate_consistency
- **Source**: Allen ID=1058 (`VISC5`), Match: exact_primary (dist=0)
- **Target**: Allen ID=665 (`lot`)
- **Experiments**: 27/44 positive (ratio=0.61)
- **Density (positive)**: min=3.38775762998011e-08, median=0.000723, max=0.266241
- **Relation**: sibling | Hemisphere: bilateral
- **Pagination**: complete=True, fetched=95/95
- **Reason**: [exact_primary] Visceral area, layer 5 → lateral olfactory tract, body: 27/44 experiments, signal=strong, consistency=moderate_consistency, pos_density_median=0.000723, pos_energy_median=0.1549

### 6. Mediomedial anterior visual area,layer 5 → Retrosplenial area, dorsal part, layer 1

- **Result**: broad_hierarchical_support | Signal: strong | Consistency: low_consistency
- **Source**: Allen ID=480149274 (`VISmma5`), Match: ancestor_2_levels (dist=2)
- **Target**: Allen ID=442 (`RSPd1`)
- **Experiments**: 27/131 positive (ratio=0.21)
- **Density (positive)**: min=8.28431984700728e-06, median=0.007342, max=0.134507
- **Relation**: sibling | Hemisphere: bilateral
- **Pagination**: complete=False, fetched=150/757
- **Reason**: [ancestor_2_levels] Mediomedial anterior visual area,layer 5 → Retrosplenial area, dorsal part, layer 1: 27/131 experiments, signal=strong, consistency=low_consistency, pos_density_median=0.007342, pos_energy_median=9.9435

### 7. Prelimbic area, layer 2/3 → Agranular insular area, dorsal part, layer 2/3

- **Result**: direct_support | Signal: moderate | Consistency: low_consistency
- **Source**: Allen ID=304 (`PL2/3`), Match: exact_primary (dist=0)
- **Target**: Allen ID=328 (`AId2/3`)
- **Experiments**: 26/119 positive (ratio=0.22)
- **Density (positive)**: min=1.06369486729818e-06, median=0.001591, max=0.060809
- **Relation**: sibling | Hemisphere: bilateral
- **Pagination**: complete=False, fetched=150/380
- **Reason**: [exact_primary] Prelimbic area, layer 2/3 → Agranular insular area, dorsal part, layer 2/3: 26/119 experiments, signal=moderate, consistency=low_consistency, pos_density_median=0.001591, pos_energy_median=0.9401

### 8. Primary somatosensory area, barrel field, layer 6b → Supplemental somatosensory area, layer 2/3

- **Result**: direct_support | Signal: strong | Consistency: low_consistency
- **Source**: Allen ID=1062 (`SSp-bfd6b`), Match: exact_primary (dist=0)
- **Target**: Allen ID=806 (`SSs2/3`)
- **Experiments**: 26/124 positive (ratio=0.21)
- **Density (positive)**: min=5.88530788547814e-08, median=0.004210, max=0.299235
- **Relation**: sibling | Hemisphere: bilateral
- **Pagination**: complete=False, fetched=150/373
- **Reason**: [exact_primary] Primary somatosensory area, barrel field, layer 6b → Supplemental somatosensory area, layer 2/3: 26/124 experiments, signal=strong, consistency=low_consistency, pos_density_median=0.004210, pos_energy_median=5.4292

### 9. Anterior cingulate area, layer 2/3 → Retrosplenial area, lateral agranular part, layer 5

- **Result**: hierarchical_support | Signal: strong | Consistency: low_consistency
- **Source**: Allen ID=1053 (`ACA2/3`), Match: ancestor_1_level (dist=1)
- **Target**: Allen ID=774 (`RSPagl5`)
- **Experiments**: 26/141 positive (ratio=0.18)
- **Density (positive)**: min=2.90661041978084e-05, median=0.013693, max=0.113526
- **Relation**: sibling | Hemisphere: bilateral
- **Pagination**: complete=False, fetched=150/1090
- **Reason**: [ancestor_1_level] Anterior cingulate area, layer 2/3 → Retrosplenial area, lateral agranular part, layer 5: 26/141 experiments, signal=strong, consistency=low_consistency, pos_density_median=0.013693, pos_energy_median=10.9932

### 10. Medial visual area, layer 2/3 → Retrosplenial area, ventral part, layer 2/3

- **Result**: broad_hierarchical_support | Signal: moderate | Consistency: low_consistency
- **Source**: Allen ID=480149322 (`VISm2/3`), Match: ancestor_2_levels (dist=2)
- **Target**: Allen ID=430 (`RSPv2/3`)
- **Experiments**: 25/131 positive (ratio=0.19)
- **Density (positive)**: min=2.63344441009394e-06, median=0.006998, max=0.095604
- **Relation**: sibling | Hemisphere: bilateral
- **Pagination**: complete=False, fetched=150/757
- **Reason**: [ancestor_2_levels] Medial visual area, layer 2/3 → Retrosplenial area, ventral part, layer 2/3: 25/131 experiments, signal=moderate, consistency=low_consistency, pos_density_median=0.006998, pos_energy_median=4.9570

## 6. Recommendations for 64K Full Validation

Based on the 200-connection calibration run:

1. **Pagination**: 0/200 connections had incomplete pagination. Ensure all API calls use the page-looping logic from Phase 1.1.
2. **Same-structure filtering**: 0 connections were skipped as same-structure. Apply this filter before any Allen validation to avoid wasted API calls.
3. **Coverage**: 125/200 (62.5%) connections have Allen support (92 direct, 14 hierarchical, 19 broad). 75 not observed, 0 no data.
4. **Signal quality**: 28 connections had very_weak signal (density < 0.001). Consider raising the minimum density threshold for 'supported' classification.
5. **DB cache effectiveness**: 73 DB cache hits saved API calls. The persistent cache is critical for the 64K run.
6. **Concurrency control**: The 200-connection run used sequential processing. For 64K, group connections by source structure and use async semaphore with concurrency ~5-10.
7. **Cost estimation**: At ~781 API calls for 200 connections, 64K connections would require ~249920 API calls. With caching by source structure (reuse injection data), actual calls should be significantly lower.
