# MirrorRegionConnection Provenance / Data-Lineage Analysis

**Date**: 2026-08-12
**Scope**: All `mirror_region_connections` rows across AAL3, Macro96, Allen_HBA_2012
**Method**: Code-path trace (parsers, services, models) + live DB statistics

---

## 1. Executive Summary

**All 70,029 MirrorRegionConnection records are LLM-generated.** Not a single connection originates from a parser directly reading an original Atlas connectivity matrix or published connection dataset. The only data flowing from parsers to the system are region definitions (names, coordinates, structure IDs). Connections are exclusively produced by LLM extraction services that pair candidate brain regions and infer connectivity attributes from model knowledge.

---

## 2. Data Flow Diagram

```
Atlas Files (XML/XLSX/CSV/JSON)
        |
        v
    Parsers (aal3_parser, macro96_xlsx, allen_parser)
        |  Produce: region_records, molecular_records, mapping_candidates
        |  Does NOT produce: connection data of any kind
        v
    raw_* staging tables (raw_aal3_region_labels, raw_macro96_region_rows)
        |
        v
    Candidate Generation
        |
        v
    candidate_brain_regions  (Allen_HBA_2012: 1231, Macro96: 96)
        |
        v
    LLM Extraction Services
        |  Pair candidates, send to LLM, parse JSON response
        |  Services:
        |    - llm_connection_extraction_service.py (main producer, ~70k connections)
        |    - llm_circuit_connection_extraction_service.py (~6 items)
        |    - llm_circuit_projection_extraction_service.py
        v
    mirror_kg_service.create_mirror_connection()
        |  Write-time dedup & merge by canonical key
        v
    mirror_region_connections  (70,029 rows)
```

---

## 3. Per-Atlas Provenance

### 3.1 Macro96

| Dimension | Value |
|-----------|-------|
| Connections | **5,715** |
| Candidates | 96 (macro, macro_clinical) |
| Import batches | 137 |
| Parser | `macro96_xlsx` (v1) -- parses Excel region table only |
| Parser output | 96 `raw_macro96_region_rows` (region_index, en_name, cn_name) |
| Connections from parser | **0** (parser only produces region data) |
| Connection source | LLM: `same_granularity_connection_completion` runs |
| Connection types | structural_connection: 5,104; functional_connectivity: 422; uncertain: 172 |
| Directionality | bidirectional: 1,319; directed: 1,645; unknown: 2,751 |
| All have llm_run_id | **Yes** (5,715 / 5,715) |
| All have candidate IDs | **Yes** (5,715 / 5,715) |
| mirror_status | **100% "llm_suggested"** |
| created_by | **100% NULL** |

**Code-path evidence:**

- `backend/app/parsers/macro96_xlsx.py:30-129` -- `parse_macro96_table_from_intermediate()`: reads `macro_region_table_v1` content_jsonb, extracts `region_index`, `en_name`, `cn_name` per row. No connection fields (no `connection_type`, `strength`, `source`, `target`, `dataset_id`).
- `backend/app/services/macro96_candidate_service.py` -- grep shows 0 references to `mirror_region_connections` or `MirrorRegionConnection`.
- `backend/app/services/candidate_service.py` -- grep shows 0 references to `mirror_region_connections` or `MirrorRegionConnection`.

### 3.2 Allen_HBA_2012

| Dimension | Value |
|-----------|-------|
| Connections | **64,273** |
| Candidates | 1,231 (fine_cyto: 657, molecular_attr: 574) |
| Import batches | 2 |
| Parser | `allen_parser` / `allen_rest_api` -- parses gene expression CSV/JSON |
| Parser output | `molecular_records` (gene_symbol, expression_level) + `region_records` (structure_name, allen_structure_id) |
| Connections from parser | **0** (parser only produces gene expression and structure records) |
| Connection source | LLM: `same_granularity_connection_completion` runs (multiple) |
| Connection types | projection: 53,674; structural: 9,377; association: 956 |
| Directionality | directed: 57,473; undirected: 2,262; unknown: 4,257; bidirectional: 281 |
| All have llm_run_id | **Yes** (64,273 / 64,273) |
| All have candidate IDs | **Yes** (64,273 / 64,273) |
| mirror_status | **100% "llm_suggested"** |
| created_by | **100% NULL** |

**Code-path evidence:**

- `backend/app/parsers/allen_parser.py:22-189` -- `AllenParser.parse()`: reads CSV/JSON gene expression data. Outputs `molecular_records` (gene_symbol, expression_level, donor_id, structure_id) and `region_records` (structure_name, allen_structure_id). Produces `mapping_candidates` for cross-atlas mapping (structure -> AAL3). **No connection/projection data**.
- No service imports connections from Allen raw data into mirror tables.

### 3.3 AAL3 (Mislabeled)

| Dimension | Value |
|-----------|-------|
| Connections | **41** |
| Candidates with source_atlas='AAL3' | **0** (no AAL3 candidate rows exist) |
| Import batches | **0** |
| Raw region labels | **0** (`raw_aal3_region_labels`: 0 rows) |
| Parser | `aal3_parser` (v1.1.0) -- parses NIfTI+XML pair |
| Actual candidates referenced | **Allen_HBA_2012** candidates (all 41 connections) |
| Actual LLM runs | 3 runs: 2 with `source_atlas='Allen_HBA_2012'`, 1 with `source_atlas='Macro96'` |
| Connection types | unknown: 16; structural: 14; projection: 10; association: 1 |

**Critical finding:** The 41 connections with `source_atlas='AAL3'` are **mislabeled**. Their `source_region_candidate_id` and `target_region_candidate_id` all point to `candidate_brain_regions` rows where `source_atlas='Allen_HBA_2012'`. The LLM extraction runs that created them have `source_atlas='Allen_HBA_2012'` and `granularity_level='molecular_attr'`. This suggests the `source_atlas` column in `mirror_region_connections` was set to `'AAL3'` due to a configuration or code issue at creation time, rather than reflecting the actual source.

**Code-path evidence:**

- `backend/app/parsers/aal3_parser.py` -- `AAL3Parser.parse_pair()`: parses NIfTI coordinates + XML labels. Produces `region_records` (label index, name, hemisphere, spatial coordinates). **No connection/projection data**.
- No AAL3 import batches exist. No raw AAL3 region labels exist.
- The AAL3 resource (`resource_code='aal3_v1_macro'`) is registered and `active`, but was never fully imported through the pipeline.

---

## 4. How Connections Are Actually Created

### 4.1 LLM Extraction Pipeline (Primary Path)

All connections flow through a single write function:

**`backend/app/services/mirror_kg_service.py:268-367`** -- `create_mirror_connection()`

Called by:
- **`backend/app/services/llm_connection_extraction_service.py`** (main producer: ~64,000+ connections from `same_granularity_connection_completion` task type)
- **`backend/app/services/llm_circuit_connection_extraction_service.py:150`** (circuit step connection extraction)
- **`backend/app/services/llm_circuit_projection_extraction_service.py`** (circuit projection extraction)
- **`backend/app/routers/mirror_kg.py`** (REST API, manual creation/edit)

The LLM services work as follows:
1. Load all candidate regions for a given source_atlas + granularity
2. Pair candidates together (n x n combinations or sampled subset)
3. Pack pairs into prompts and send to LLM (DeepSeek/Kimi)
4. Parse LLM JSON response into connection attributes
5. Call `create_mirror_connection()` for each parsed connection
6. Write-time dedup: canonical key = `(source_candidate_id, target_candidate_id, connection_type, directionality)`

### 4.2 REST API (Secondary Path)

`backend/app/routers/mirror_kg.py` exposes CRUD endpoints for manual creation/editing. Currently `created_by` is NULL for all rows, indicating no connections were created through the API (or the field was not populated at creation time).

### 4.3 ConnectionPool (Grouping, Not Import)

`connection_pools` and `connection_pool_memberships` tables group existing `mirror_region_connections` for LLM extraction purposes. They do NOT create connections from raw atlas data. The `source` column on `ConnectionPool` defaults to `"manual"`.

---

## 5. Provenance Fields Analysis

### 5.1 `raw_payload_json` Structure

The `raw_payload_json` column contains LLM output metadata, not original Atlas data. Key fields:

| Field | Source | Example |
|-------|--------|---------|
| `pair_id` | Constructed from candidate IDs | `"065eac78-...::ed4d9faf-..."` |
| `confidence` / `confidence_score` | LLM output | `0.15`, `0.5` |
| `evidence_text` | LLM output | "Indirect." / "DTI studies show..." |
| `description` | LLM output | "Possible connection via arcuate fasciculus" |
| `directionality` | LLM output | `"directed"`, `"unknown"` |
| `evidence_level` | LLM output | `"insufficient"` |
| `strength` / `strength_score` | LLM output | `0.0`, `0.4`, `0.15` |
| `provenance` | System-generated | `{llm_run_id, llm_model, updated_at, merge_history: [...]}` |

**Missing fields** (not present in raw_payload_json for any connection):
- `source_dataset_id` / `dataset` / `atlas_connectivity_source`
- `original_record_id` (reference to a row in the original Atlas file)
- `source_file_path` / `source_file_hash`
- `published_reference` / `doi` / `pmid`
- `tract_name` (DTI tractography ID)
- `correlation_coefficient` (if from functional connectivity matrix)

### 5.2 Traceability Assessment

| Atlas | Has source_record_id? | Has dataset/version? | Has atlas evidence? |
|-------|----------------------|---------------------|-------------------|
| Macro96 | No | No (only `source_atlas='Macro96'`, `source_version='v1'`) | No |
| Allen_HBA_2012 | No | No (only `source_atlas='Allen_HBA_2012'`) | No |
| AAL3 | No (mislabeled) | No | No |

### 5.3 `source_region_candidate_id` / `target_region_candidate_id`

These fields ARE populated for all 70,029 connections. They point to `candidate_brain_regions` rows, which in turn trace back to:
- A `generation_run_id` -> `batch_id` -> `resource_id` -> `atlas_resources`
- A `source_file_id` -> the original uploaded file
- A `raw_payload` containing the original parser output (region names, coordinates, structure IDs)

This means **the regions being connected have provenance**, but **the connections themselves do not**.

---

## 6. Evidence for Atlas Connectivity

### 6.1 Which connections have original Atlas records?

**None.** No connection in `mirror_region_connections` references an original Atlas-sourced connectivity record because:
1. The parsers do not produce connectivity data at all
2. There is no import pipeline for Atlas-provided connection/connectivity matrices
3. The `mirror_evidence_records` table stores LLM-generated evidence from paper retrieval, not Atlas-provided evidence

### 6.2 What COULD constitute Atlas Evidence?

If connections were to have Atlas Evidence, the system would need:
- An import path for Atlas-provided connectivity matrices (e.g., DTI tractography data, functional connectivity matrices, published connection tables)
- Fields to store provenance: `source_dataset_id`, `source_record_id`, `publication_doi`
- Parser support for connection data formats

Currently, none of these exist for any Atlas in the system.

---

## 7. Database Statistics Summary

```
=== RAW DATA ===
raw_aal3_region_labels:       0 rows
raw_macro96_region_rows:     96 rows
raw_parse_runs:               4 runs

=== CANDIDATES ===
Allen_HBA_2012 (fine_cyto):    657
Allen_HBA_2012 (molecular):    574
Macro96 (macro):                96
AAL3:                            0

=== CONNECTIONS BY SOURCE_ATLAS ===
AAL3:                     41    (all reference Allen candidates -- mislabeled)
Allen_HBA_2012:       64,273    (all LLM-generated)
Macro96:               5,715    (all LLM-generated)
TOTAL:                70,029

=== PROVENANCE INDICATORS ===
has_source_candidate_id:  70,029 / 70,029  (100%)
has_target_candidate_id:  70,029 / 70,029  (100%)
has_llm_run_id:           70,029 / 70,029  (100%)
mirror_status='llm_suggested': 70,029 / 70,029  (100%)
created_by NOT NULL:               0 / 70,029  (0%)

=== TOP LLM EXTRACTION RUNS ===
run_id=6004f4a2...  task=connection_completion  status=running             24,537 conns
run_id=cc874893...  task=connection_completion  status=running             24,336 conns
run_id=f2490ad0...  task=connection_completion  status=partially_succeeded 10,964 conns
```

---

## 8. Conclusions

1. **All MirrorRegionConnection records are LLM-generated.** The provenance chain is: Region parsers (region only) -> Candidate generation -> LLM pairwise extraction -> Mirror KG connection write. No parser reads or outputs connectivity data.

2. **No connection has Atlas Evidence in the formal sense.** The `raw_payload_json` contains LLM output metadata (confidence, evidence_text, directionality), not original Atlas-provided connectivity data. There is no `source_dataset_id`, `tract_name`, `correlation_coefficient`, or `original_record_id` that could be traced back to a published Atlas connectivity matrix.

3. **AAL3 connections are mislabeled.** All 41 AAL3-tagged connections actually reference Allen_HBA_2012 candidates. AAL3 has never been properly imported (0 candidates, 0 raw labels, 0 batches).

4. **Region provenance is intact, connection provenance is not.** Each connection's `source_region_candidate_id` and `target_region_candidate_id` point to candidates with full lineage to parser output and original files. But the connection itself has no reference to any original connectivity data source.

5. **The `raw_payload_json` is insufficient for Atlas Evidence.** It stores LLM outputs (confidence scores, evidence text descriptions), not structured provenance data. To support Atlas Evidence, the system would need additional fields (or a dedicated parser/schema) for importing and tracking connectivity data from original Atlas publications.

---

## 9. File References

| File | Lines | Relevance |
|------|-------|-----------|
| `backend/app/parsers/macro96_xlsx.py` | 30-129 | Region-only parser, no connection data |
| `backend/app/parsers/aal3_parser.py` | 20-80 | NIfTI+XML parser, no connection data |
| `backend/app/parsers/allen_parser.py` | 22-189 | Gene expression parser, no connection data |
| `backend/app/models/mirror_kg.py` | 33-87 | MirrorRegionConnection model definition |
| `backend/app/services/mirror_kg_service.py` | 80-118, 268-367 | Canonical key + create_mirror_connection (write function) |
| `backend/app/services/llm_connection_extraction_service.py` | 1-80 | Main LLM connection extraction orchestration |
| `backend/app/services/llm_circuit_connection_extraction_service.py` | 123-150 | Circuit connection extraction + write |
| `backend/app/models/candidate.py` | 45-102 | CandidateBrainRegion model (full lineage fields) |
| `backend/app/models/import_batch.py` | 14-40 | ImportBatch model (batch tracking, no connection import) |
| `backend/migrations/022_mirror_kg_schema.sql` | 11-50 | Mirror KG schema creation (all connections start as llm_suggested) |
| `backend/app/models/connection_pool.py` | 15-51 | ConnectionPool (grouping, not import) |
