-- Paper Evidence Workbench: ranking-level state (papers workspace / rule segments / LLM reviews)
CREATE TABLE IF NOT EXISTS pew_papers (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    ranking_id uuid NOT NULL,
    paper_id uuid NOT NULL REFERENCES paper_sources(id) ON DELETE CASCADE,
    role varchar(16) NOT NULL DEFAULT 'search' CHECK (role IN ('search', 'imported')),
    title text,
    authors text,
    journal varchar(256),
    publication_year integer,
    pmid varchar(64),
    doi varchar(256),
    normalized_doi varchar(256),
    abstract_available boolean NOT NULL DEFAULT false,
    fulltext_available boolean NOT NULL DEFAULT false,
    source varchar(32) NOT NULL DEFAULT 'search',
    retrieved_at timestamptz NOT NULL DEFAULT now(),
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_pew_paper_task UNIQUE (ranking_id, paper_id)
);

CREATE INDEX IF NOT EXISTS ix_pew_papers_ranking ON pew_papers (ranking_id);

CREATE TABLE IF NOT EXISTS pew_segments (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    ranking_id uuid NOT NULL,
    paper_id uuid NOT NULL REFERENCES paper_sources(id) ON DELETE CASCADE,
    section_name varchar(256) NOT NULL DEFAULT '',
    source_type varchar(16) NOT NULL DEFAULT 'paper_abstract' CHECK (source_type IN ('paper_abstract', 'paper_fulltext')),
    sentence_id integer,
    sentence_text text NOT NULL,
    context_before text,
    context_after text,
    matched_source_term varchar(256),
    matched_target_term varchar(256),
    relation_keyword varchar(64),
    proximity varchar(24) NOT NULL DEFAULT 'same_sentence' CHECK (proximity IN ('same_sentence', 'adjacent_sentence', 'same_section', 'same_paper')),
    retrieval_method varchar(64) NOT NULL,
    rule_score numeric(5, 3) NOT NULL DEFAULT 0,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_pew_segment UNIQUE (ranking_id, paper_id, sentence_text, section_name)
);

CREATE INDEX IF NOT EXISTS ix_pew_segments_ranking ON pew_segments (ranking_id);

CREATE TABLE IF NOT EXISTS pew_reviews (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    ranking_id uuid NOT NULL,
    segment_id uuid NOT NULL REFERENCES pew_segments(id) ON DELETE CASCADE,
    decision varchar(24) NOT NULL CHECK (decision IN ('supported', 'partial_support', 'uncertain', 'not_supported')),
    confidence numeric(4, 3),
    evidence_type varchar(24) CHECK (evidence_type IN ('direct', 'indirect', 'context', 'contradictory')),
    reason text,
    suggested_connection_type varchar(64),
    direction_support varchar(16),
    model_name varchar(64),
    raw_response_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    reviewed_at timestamptz NOT NULL DEFAULT now(),
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_pew_review_segment UNIQUE (segment_id)
);

CREATE INDEX IF NOT EXISTS ix_pew_reviews_ranking ON pew_reviews (ranking_id);
