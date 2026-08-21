-- 034: Allen PoC 2.0 — persistent cache + v2 results table
-- Run: backend/.venv/Scripts/python.exe -c "
--   import asyncio, selectors; from app.database import AsyncSessionLocal; from sqlalchemy import text
--   async def m(): async with AsyncSessionLocal() as s: await s.execute(text(open('migrations/034_allen_poc_v2.sql').read())); await s.commit()
--   asyncio.run(m(), loop_factory=lambda: asyncio.SelectorEventLoop(selectors.SelectSelector()))"

-- Persistent cache tables
CREATE TABLE IF NOT EXISTS allen_experiments_cache (
    source_allen_id   INTEGER   NOT NULL,
    total_rows        INTEGER,
    rows_fetched      INTEGER,
    pagination_complete BOOLEAN,
    experiments_json  JSONB     NOT NULL,
    retrieved_at      TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (source_allen_id)
);

CREATE TABLE IF NOT EXISTS allen_unionize_cache (
    experiment_id      INTEGER   NOT NULL,
    total_rows         INTEGER,
    rows_fetched       INTEGER,
    pagination_complete BOOLEAN,
    unionize_json      JSONB     NOT NULL,
    retrieved_at       TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (experiment_id)
);

-- V2 results table (same structure as v1 but with new classification columns)
CREATE TABLE IF NOT EXISTS allen_connectivity_poc_v2 (
    connection_id            UUID      NOT NULL,
    source_candidate_id      UUID,
    target_candidate_id      UUID,
    source_allen_id          INTEGER,
    target_allen_id          INTEGER,
    source_name              TEXT,
    target_name              TEXT,
    source_acronym           TEXT,
    target_acronym           TEXT,

    -- Source match grading (Phase 1.4)
    source_match_type        TEXT,  -- exact_primary|ancestor_1_level|ancestor_2_levels|ancestor_3_plus|descendant|secondary|ambiguous|no_match
    matched_source_id        INTEGER,
    matched_source_name      TEXT,
    source_hierarchy_distance INTEGER,  -- 0=exact, 1=parent, 2=grandparent, ...

    -- Target match grading (Phase 1.5)
    target_match_type        TEXT,  -- exact|ancestor_aggregated|descendant_aggregated|ambiguous

    -- Experiment counts (Phase 1.2: deduped by experiment_id)
    experiment_count         INTEGER,
    positive_experiment_count INTEGER,  -- experiments with AT LEAST ONE positive row
    positive_ratio           DOUBLE PRECISION,  -- positive / total

    -- Pagination metadata (Phase 1.1)
    source_api_total_rows    INTEGER,
    source_rows_fetched      INTEGER,
    source_pagination_complete BOOLEAN,

    -- Statistics *per experiment* (Phase 1.3) — across ALL experiments
    density_all_min          DOUBLE PRECISION,
    density_all_median       DOUBLE PRECISION,
    density_all_max          DOUBLE PRECISION,
    density_all_p75          DOUBLE PRECISION,
    density_all_p90          DOUBLE PRECISION,
    density_positive_min     DOUBLE PRECISION,
    density_positive_median  DOUBLE PRECISION,
    density_positive_max     DOUBLE PRECISION,
    density_positive_p75     DOUBLE PRECISION,
    density_positive_p90     DOUBLE PRECISION,

    energy_all_min           DOUBLE PRECISION,
    energy_all_median        DOUBLE PRECISION,
    energy_all_max           DOUBLE PRECISION,
    energy_all_p75           DOUBLE PRECISION,
    energy_all_p90           DOUBLE PRECISION,
    energy_positive_min      DOUBLE PRECISION,
    energy_positive_median   DOUBLE PRECISION,
    energy_positive_max      DOUBLE PRECISION,
    energy_positive_p75      DOUBLE PRECISION,
    energy_positive_p90      DOUBLE PRECISION,

    -- New classification (Phase 2)
    result                   TEXT,  -- direct_support|hierarchical_support|broad_hierarchical_support|atlas_not_observed|atlas_no_data|atlas_mapping_uncertain|atlas_conflicting|api_incomplete|same_structure_skip
    signal_strength          TEXT,  -- very_weak|weak|moderate|strong
    consistency              TEXT,  -- low_consistency|moderate_consistency|high_consistency|single_experiment

    -- Hierarchy & hemisphere (Phase 1.6, 1.7)
    source_target_relation   TEXT,  -- same_structure|source_contains_target|target_contains_source|sibling|unrelated
    hemisphere_match_type    TEXT,  -- exact|bilateral|unknown|mismatch

    reason                   TEXT,
    experiments_json         JSONB,
    retrieved_at             TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (connection_id)
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_poc_v2_result ON allen_connectivity_poc_v2(result);
CREATE INDEX IF NOT EXISTS idx_poc_v2_source_match ON allen_connectivity_poc_v2(source_match_type);
CREATE INDEX IF NOT EXISTS idx_cache_retrieved ON allen_experiments_cache(retrieved_at);
CREATE INDEX IF NOT EXISTS idx_unionize_retrieved ON allen_unionize_cache(retrieved_at);
