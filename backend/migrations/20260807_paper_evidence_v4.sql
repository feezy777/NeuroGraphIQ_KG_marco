-- 20260807_paper_evidence_v4.sql (idempotent)
-- Phase D: unified paper entity + structured paragraphs + evidence link columns.

-- 1) paper_sources: single source of truth for paper metadata.
CREATE TABLE IF NOT EXISTS paper_sources (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source VARCHAR(32) NOT NULL DEFAULT 'europepmc',
    pmid VARCHAR(64),
    pmcid VARCHAR(64),
    doi VARCHAR(256),
    normalized_doi VARCHAR(256),
    title TEXT,
    journal VARCHAR(256),
    publication_year INT,
    is_oa BOOLEAN NOT NULL DEFAULT FALSE,
    abstract_available BOOLEAN NOT NULL DEFAULT FALSE,
    fulltext_available BOOLEAN NOT NULL DEFAULT FALSE,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    abstract_hash VARCHAR(64),
    fulltext_hash VARCHAR(64),
    fetched_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_paper_sources_pmid ON paper_sources (pmid) WHERE pmid IS NOT NULL AND pmid <> '';
CREATE UNIQUE INDEX IF NOT EXISTS uq_paper_sources_norm_doi ON paper_sources (normalized_doi) WHERE normalized_doi IS NOT NULL AND normalized_doi <> '';
CREATE INDEX IF NOT EXISTS idx_paper_sources_doi ON paper_sources (doi);
CREATE INDEX IF NOT EXISTS idx_paper_sources_title ON paper_sources (title);

-- 2) paper_passages: structured original paragraphs (reusable across evidences).
CREATE TABLE IF NOT EXISTS paper_passages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    paper_id UUID NOT NULL REFERENCES paper_sources(id) ON DELETE CASCADE,
    source_scope VARCHAR(16) NOT NULL,          -- abstract | fulltext
    section_title VARCHAR(256),
    paragraph_id VARCHAR(128),
    paragraph_index INT,
    passage_text TEXT NOT NULL,
    text_hash VARCHAR(64) NOT NULL,
    locator VARCHAR(256),
    char_start INT,
    char_end INT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_paper_passage_paragraph UNIQUE (paper_id, paragraph_id)
);
CREATE INDEX IF NOT EXISTS idx_paper_passages_paper ON paper_passages (paper_id, source_scope);
CREATE INDEX IF NOT EXISTS idx_paper_passages_hash ON paper_passages (text_hash);

-- 3) mirror_evidence_records: paper link + level + reviewer fields + invalidation audit.
ALTER TABLE mirror_evidence_records ADD COLUMN IF NOT EXISTS paper_id UUID;
ALTER TABLE mirror_evidence_records ADD COLUMN IF NOT EXISTS evidence_level VARCHAR(16);
ALTER TABLE mirror_evidence_records ADD COLUMN IF NOT EXISTS reviewer_confidence NUMERIC;
ALTER TABLE mirror_evidence_records ADD COLUMN IF NOT EXISTS invalidated_by VARCHAR(64);
ALTER TABLE mirror_evidence_records ADD COLUMN IF NOT EXISTS invalidated_at TIMESTAMPTZ;
ALTER TABLE mirror_evidence_records ADD COLUMN IF NOT EXISTS invalidation_reason TEXT;
CREATE INDEX IF NOT EXISTS idx_evidence_records_paper ON mirror_evidence_records (paper_id);

-- 4) mirror_evidence_passages: link to structured paragraph + level + semantic confidence.
ALTER TABLE mirror_evidence_passages ADD COLUMN IF NOT EXISTS paper_passage_id UUID;
ALTER TABLE mirror_evidence_passages ADD COLUMN IF NOT EXISTS passage_text_snapshot TEXT;
ALTER TABLE mirror_evidence_passages ADD COLUMN IF NOT EXISTS evidence_level VARCHAR(16);
ALTER TABLE mirror_evidence_passages ADD COLUMN IF NOT EXISTS semantic_confidence NUMERIC;
CREATE INDEX IF NOT EXISTS idx_evidence_passages_paper_passage ON mirror_evidence_passages (paper_passage_id);

-- 5) confidence_adjustment_logs: explicit reviewer + calculated values.
ALTER TABLE confidence_adjustment_logs ADD COLUMN IF NOT EXISTS reviewer_confidence NUMERIC;
ALTER TABLE confidence_adjustment_logs ADD COLUMN IF NOT EXISTS calculated_confidence NUMERIC;

-- 6) paper_evidence_task_items: paper/passage draft linkage.
ALTER TABLE paper_evidence_task_items ADD COLUMN IF NOT EXISTS paper_id UUID;
