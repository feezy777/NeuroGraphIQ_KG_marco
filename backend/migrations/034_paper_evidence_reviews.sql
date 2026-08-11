-- paper_evidence_reviews: formal human review records (独立于 batch task items 和 sessionStorage)
-- Each review captures a reviewer's decision + frozen passage snapshots at review time.
-- Does NOT write mirror_evidence_records during review; promotion is a separate step.
CREATE TABLE IF NOT EXISTS paper_evidence_reviews (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    target_type VARCHAR(64) NOT NULL,
    target_id UUID NOT NULL,
    paper_id UUID REFERENCES paper_sources(id),
    task_id UUID,
    task_item_id UUID,
    reviewer_id VARCHAR(128),
    review_status VARCHAR(32) NOT NULL DEFAULT 'draft',
    promotion_status VARCHAR(32) NOT NULL DEFAULT 'not_ready',
    claim_version VARCHAR(32),
    claim_text_snapshot TEXT,
    claim_components_snapshot JSONB,
    model_direction VARCHAR(32),
    model_assessment TEXT,
    reviewer_direction VARCHAR(32),
    reviewer_evidence_level VARCHAR(32),
    reviewer_confidence DOUBLE PRECISION,
    reviewer_note TEXT,
    coverage_summary_snapshot JSONB,
    coverage_formula_version VARCHAR(32),
    draft_revision INTEGER NOT NULL DEFAULT 0,
    reviewed_at TIMESTAMPTZ,
    approved_at TIMESTAMPTZ,
    rejected_at TIMESTAMPTZ,
    promoted_at TIMESTAMPTZ,
    promoted_by VARCHAR(128),
    returned_at TIMESTAMPTZ,
    returned_by VARCHAR(128),
    return_reason TEXT,
    evidence_id UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_reviews_target ON paper_evidence_reviews(target_type, target_id);
CREATE INDEX IF NOT EXISTS idx_reviews_status ON paper_evidence_reviews(review_status, promotion_status);
CREATE INDEX IF NOT EXISTS idx_reviews_task ON paper_evidence_reviews(task_id);

-- paper_evidence_review_passages: frozen passage snapshots at review time
CREATE TABLE IF NOT EXISTS paper_evidence_review_passages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    review_id UUID NOT NULL REFERENCES paper_evidence_reviews(id) ON DELETE CASCADE,
    paper_passage_id UUID,
    passage_text TEXT NOT NULL,
    passage_text_snapshot TEXT NOT NULL,
    source_scope VARCHAR(16),
    section_title VARCHAR(256),
    paragraph_index INTEGER,
    paragraph_id VARCHAR(128),
    translation_zh TEXT,
    direction VARCHAR(32),
    evidence_level VARCHAR(32),
    reason TEXT,
    confidence DOUBLE PRECISION,
    semantic_confidence DOUBLE PRECISION,
    source_locator VARCHAR(128),
    source_verified BOOLEAN NOT NULL DEFAULT false,
    source_verification_method VARCHAR(32),
    supported_components JSONB DEFAULT '[]',
    passage_hash VARCHAR(64),
    rank INTEGER NOT NULL DEFAULT 0,
    is_selected BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_review_passages ON paper_evidence_review_passages(review_id);
