-- Gate 7B Phase 3E.1A — Publication Persistence Foundation
--
-- Builds the MINIMUM persistence needed to record, later and traceably:
--
--   BrainRegion -> Discovery Run -> Discovery Hit -> Publication
--                                              -> Evidence Passage
--                                              -> Candidate / Assertion
--
-- This migration deliberately REUSES the frozen literature layer. It does not
-- create a parallel one:
--
--   publications  = Publication Registry authority   (REUSED, not replaced)
--   entity_xrefs  = external identifier authority    (REUSED for OpenAlex /
--                                                     Semantic Scholar ids)
--   evidence      = one atomic Evidence Unit/Passage  (REUSED, not replaced)
--   evidence_links= Evidence -> Assertion/Entity      (REUSED, untouched)
--
-- It therefore does NOT create: papers / literature_papers / evidence_passages
-- / article_evidence. A second paper table would split publication identity
-- across two authorities; a second passage table would split evidence
-- semantics across two.
--
-- It adds exactly two things:
--
--   1. knowledge_discovery_runs — WIDENED, not created. The table already
--      exists (gate7b_011/012) and its audit found it sufficient EXCEPT for
--      the run-type vocabulary and a schema-version column.
--   2. publication_discovery_hits — NEW. Records WHY and THROUGH WHICH SEARCH
--      a publication was found. This is RETRIEVAL PROVENANCE, not scientific
--      evidence.
--
-- Frozen boundaries honored:
--   * A discovery hit is NOT evidence and NOT knowledge. It creates no
--     evidence row, no knowledge_assertion, and no kg_entities entity.
--   * ONE publication may have MANY hits: the same paper found by Europe PMC,
--     by PubMed, by citation chaining and by a functional query is still ONE
--     publication. There is deliberately NO UNIQUE(publication_pk).
--   * A FAILED SEARCH IS NOT A HIT. Phase 3E.1 froze the rule that a provider
--     failure (rate limit / transport / upstream / malformed) is not an empty
--     result. Persistence keeps that rule: only a publication actually
--     RETURNED by a completed search may create a hit. Failure diagnostics
--     belong in the run's provenance_json / logs.
--   * Publication identity is PMID > DOI > PMCID > normalized title. Title is
--     a FALLBACK RESOLVER and gets NO unique constraint (titles collide across
--     genuinely different works, and normalize differently in different hands).
--   * No publication-level relevance verdict. The same publication can be
--     SUPPORT for one circuit, BACKGROUND for another, IRRELEVANT for a third;
--     relevance is a relation, not a property of the paper. Evidence keeps its
--     existing human_review_status.
--   * No candidate links. Raw candidate persistence is not frozen yet; Phase 3C
--     local ids (circuit_1...) must not enter permanent storage.
--   * No url columns for pubmed/europepmc/doi. Those are derivable from
--     pmid/pmcid/doi. `publications.full_text_url` already exists and is the
--     only url worth storing.
--   * Idempotent: re-runnable.

-- ===========================================================================
-- 1. knowledge_discovery_runs — extend the run vocabulary (no new table)
-- ===========================================================================
-- The audit found the table sufficient for LLM/LITERATURE runs but unable to
-- express the two retrieval-side run types this phase needs. Widen only:
-- evidence_search and citation_chaining are REQUESTS against literature
-- sources, so they are runs with the same lifecycle, not a different concept.
ALTER TABLE knowledge_discovery_runs
    DROP CONSTRAINT IF EXISTS ck_kdr_discovery_type;

ALTER TABLE knowledge_discovery_runs
    ADD CONSTRAINT ck_kdr_discovery_type CHECK (discovery_type IN (
        'LLM_DISCOVERY',
        'LITERATURE_DISCOVERY',
        'EVIDENCE_SEARCH',
        'CITATION_CHAINING'
    ));

-- Contract provenance. prompt_key/prompt_version already record which PROMPT
-- ran; this records which STRUCTURED CONTRACT the run's output was validated
-- against. The two are separate versions (Phase 3B.2 made that explicit) and a
-- run that cannot name its contract cannot be replayed.
--
-- metrics_json is deliberately NOT added: `provenance_json` already exists as a
-- NOT NULL jsonb container for exactly this, and a second jsonb column holding
-- the same kind of data would give the same fact two homes.
ALTER TABLE knowledge_discovery_runs
    ADD COLUMN IF NOT EXISTS schema_version VARCHAR(32);

COMMENT ON COLUMN knowledge_discovery_runs.schema_version IS
    'Structured-contract version the run output was validated against (e.g. 1.0). '
    'Distinct from prompt_version. NULL for runs that consume no contract.';
COMMENT ON COLUMN knowledge_discovery_runs.provenance_json IS
    'Non-content run provenance AND metrics (counts, token usage, latency, '
    'provider failure diagnostics). Never candidate content or raw responses.';

-- ===========================================================================
-- 2. publication_discovery_hits — NEW: retrieval provenance
-- ===========================================================================
-- Identity: NGIQ-PDH-* mirrors the relationship-layer convention used by
-- evidence_links (NGIQ-ELK-*). A hit is NOT a kg_entities entity: it is
-- workflow provenance, so it stays out of the frozen 29-type id registry, just
-- as knowledge_discovery_runs does.
CREATE SEQUENCE IF NOT EXISTS infra.ngiq_pdh_seq;

CREATE TABLE IF NOT EXISTS publication_discovery_hits (
    hit_pk                BIGSERIAL   PRIMARY KEY,
    hit_id                VARCHAR(32) NOT NULL UNIQUE
        DEFAULT 'NGIQ-PDH-' || lpad(nextval('infra.ngiq_pdh_seq')::text, 8, '0'),

    -- WHICH paper. publications is keyed on entity_pk (a kg_entities subtype).
    publication_pk        BIGINT      NOT NULL,

    -- WHICH run, WHICH source, WHICH seed.
    discovery_run_pk      BIGINT,
    source_pk             BIGINT,
    seed_brain_region_pk  BIGINT,

    -- HOW it was found. query_text is the mandatory part: a hit that cannot
    -- reproduce the query that produced it is not provenance.
    query_family          VARCHAR(64),
    query_level           VARCHAR(32),
    query_text            TEXT        NOT NULL,
    result_rank           INTEGER,

    retrieved_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    metadata_json         JSONB       NOT NULL DEFAULT '{}'::jsonb,
    remark                TEXT,

    CONSTRAINT fk_pdh_publication
        FOREIGN KEY (publication_pk) REFERENCES publications (entity_pk)
        ON DELETE RESTRICT,
    CONSTRAINT fk_pdh_run
        FOREIGN KEY (discovery_run_pk) REFERENCES knowledge_discovery_runs (run_pk)
        ON DELETE RESTRICT,
    CONSTRAINT fk_pdh_source
        FOREIGN KEY (source_pk) REFERENCES sources (source_pk)
        ON DELETE RESTRICT,
    CONSTRAINT fk_pdh_seed_region
        FOREIGN KEY (seed_brain_region_pk) REFERENCES brain_regions (entity_pk)
        ON DELETE RESTRICT,

    -- Phase 3E query levels and families, frozen so a stored hit always says
    -- which retrieval STRATEGY produced it rather than a free-text label.
    CONSTRAINT ck_pdh_query_level CHECK (
        query_level IS NULL OR query_level IN (
            'NAME', 'MEMBER_COMBINATION', 'TOPOLOGY', 'FUNCTION_EXPANSION',
            'CITATION_BACKWARD', 'CITATION_FORWARD', 'REVIEW_EXPANSION'
        )
    ),
    CONSTRAINT ck_pdh_result_rank CHECK (result_rank IS NULL OR result_rank >= 1)
);

COMMENT ON TABLE publication_discovery_hits IS
    'RETRIEVAL PROVENANCE: which publication was found, by which run, source, '
    'query and rank. NOT evidence, NOT knowledge, NOT a relevance verdict. One '
    'publication may have many hits; there is deliberately no '
    'UNIQUE(publication_pk).';

-- No UNIQUE(publication_pk): the same paper found by Europe PMC, by PubMed, by
-- citation chaining and by a functional query is ONE publication reached FOUR
-- ways. Collapsing those would destroy the recall evidence this phase produced.

CREATE INDEX IF NOT EXISTS idx_pdh_publication     ON publication_discovery_hits (publication_pk);
CREATE INDEX IF NOT EXISTS idx_pdh_run             ON publication_discovery_hits (discovery_run_pk);
CREATE INDEX IF NOT EXISTS idx_pdh_seed_region     ON publication_discovery_hits (seed_brain_region_pk);
CREATE INDEX IF NOT EXISTS idx_pdh_retrieved_at    ON publication_discovery_hits (retrieved_at);
CREATE INDEX IF NOT EXISTS idx_pdh_family_level    ON publication_discovery_hits (query_family, query_level);

-- ===========================================================================
-- 3. publications — identity guards (audit was CLEAN: zero duplicates)
-- ===========================================================================
-- Added only because the duplicate audit found no PMID/PMCID/DOI collisions.
-- Had it found any, this block would have been omitted and the collisions
-- reported instead: a unique constraint over dirty data is not a fix, it just
-- moves the failure to the next writer.
--
-- Partial (`WHERE ... IS NOT NULL AND btrim(...) <> ''`): a publication may
-- legitimately have no PMID, and many non-empty '' values must not collide
-- with each other.
CREATE UNIQUE INDEX IF NOT EXISTS uq_publications_pmid
    ON publications (pmid)
    WHERE pmid IS NOT NULL AND btrim(pmid) <> '';

CREATE UNIQUE INDEX IF NOT EXISTS uq_publications_pmcid
    ON publications (pmcid)
    WHERE pmcid IS NOT NULL AND btrim(pmcid) <> '';

-- DOI comparison is case-insensitive and whitespace-insensitive, so the guard
-- must be too, or the same DOI in two casings slips past it.
CREATE UNIQUE INDEX IF NOT EXISTS uq_publications_doi_norm
    ON publications (lower(btrim(doi)))
    WHERE doi IS NOT NULL AND btrim(doi) <> '';

-- Indexes for identity RESOLUTION (not only enforcement).
CREATE INDEX IF NOT EXISTS idx_publications_pmcid     ON publications (pmcid);
CREATE INDEX IF NOT EXISTS idx_publications_doi_norm  ON publications (lower(btrim(doi)));

-- NO unique constraint on title: too many distinct works share a normalized
-- title, and normalization rules differ between resolvers. Title remains a
-- fallback resolver only.
