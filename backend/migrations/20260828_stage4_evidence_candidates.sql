-- Stage 4 Evidence Candidate (candidate layer references segment and review, no text copy)
-- Still NOT formal Evidence: no connection_paper_evidence / Final KG writes
CREATE TABLE IF NOT EXISTS pew_evidence_candidates (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    ranking_id uuid NOT NULL,
    segment_id uuid NOT NULL REFERENCES pew_segments(id) ON DELETE CASCADE,
    paper_id uuid NOT NULL REFERENCES paper_sources(id) ON DELETE CASCADE,
    llm_review_id uuid REFERENCES pew_reviews(id) ON DELETE SET NULL,
    candidate_status varchar(24) NOT NULL DEFAULT 'candidate'
        CHECK (candidate_status IN ('candidate', 'review_required', 'excluded')),
    evidence_type varchar(24),
    ai_decision varchar(24) NOT NULL,
    ai_confidence numeric(4, 3),
    selected_for_review boolean NOT NULL DEFAULT false,
    translated_text text,
    translation_language varchar(16),
    translation_model varchar(64),
    translation_prompt_version varchar(64),
    translation_created_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_pew_evidence_candidate UNIQUE (ranking_id, segment_id)
);
CREATE INDEX IF NOT EXISTS ix_pew_evidence_candidates_ranking ON pew_evidence_candidates (ranking_id);
