-- 20260807_paper_evidence_v8.sql (idempotent)
-- Phase 4: batch review lifecycle, error taxonomy, backend review draft persistence.

-- 1) tasks: review lifecycle + creation config
ALTER TABLE paper_evidence_tasks ADD COLUMN IF NOT EXISTS name TEXT;
ALTER TABLE paper_evidence_tasks ADD COLUMN IF NOT EXISTS review_status VARCHAR(16) NOT NULL DEFAULT 'not_started';
ALTER TABLE paper_evidence_tasks ADD COLUMN IF NOT EXISTS granularity_level VARCHAR(32);
ALTER TABLE paper_evidence_tasks ADD COLUMN IF NOT EXISTS only_oa BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE paper_evidence_tasks ADD COLUMN IF NOT EXISTS confidence_lt NUMERIC;
ALTER TABLE paper_evidence_tasks ADD COLUMN IF NOT EXISTS stop_after_strong_support BOOLEAN NOT NULL DEFAULT FALSE;
CREATE INDEX IF NOT EXISTS idx_paper_evidence_tasks_review ON paper_evidence_tasks (review_status);
CREATE INDEX IF NOT EXISTS idx_paper_evidence_tasks_created ON paper_evidence_tasks (created_at DESC);

-- 2) items: attempts / error taxonomy / outcomes / review draft
ALTER TABLE paper_evidence_task_items ADD COLUMN IF NOT EXISTS attempt_count INT NOT NULL DEFAULT 0;
ALTER TABLE paper_evidence_task_items ADD COLUMN IF NOT EXISTS last_error_code VARCHAR(48);
ALTER TABLE paper_evidence_task_items ADD COLUMN IF NOT EXISTS last_error_message TEXT;
ALTER TABLE paper_evidence_task_items ADD COLUMN IF NOT EXISTS last_error_at TIMESTAMPTZ;
ALTER TABLE paper_evidence_task_items ADD COLUMN IF NOT EXISTS next_retry_at TIMESTAMPTZ;
ALTER TABLE paper_evidence_task_items ADD COLUMN IF NOT EXISTS started_at TIMESTAMPTZ;
ALTER TABLE paper_evidence_task_items ADD COLUMN IF NOT EXISTS finished_preprocessing_at TIMESTAMPTZ;
ALTER TABLE paper_evidence_task_items ADD COLUMN IF NOT EXISTS preprocess_outcome VARCHAR(32);
ALTER TABLE paper_evidence_task_items ADD COLUMN IF NOT EXISTS claim_version VARCHAR(32);
ALTER TABLE paper_evidence_task_items ADD COLUMN IF NOT EXISTS claim_text_snapshot TEXT;
ALTER TABLE paper_evidence_task_items ADD COLUMN IF NOT EXISTS claim_components_snapshot JSONB;
ALTER TABLE paper_evidence_task_items ADD COLUMN IF NOT EXISTS search_query TEXT;
ALTER TABLE paper_evidence_task_items ADD COLUMN IF NOT EXISTS candidate_papers JSONB;
ALTER TABLE paper_evidence_task_items ADD COLUMN IF NOT EXISTS model_direction VARCHAR(16);
ALTER TABLE paper_evidence_task_items ADD COLUMN IF NOT EXISTS model_assessment TEXT;
ALTER TABLE paper_evidence_task_items ADD COLUMN IF NOT EXISTS coverage_summary JSONB;
ALTER TABLE paper_evidence_task_items ADD COLUMN IF NOT EXISTS preprocessing_version VARCHAR(32);
ALTER TABLE paper_evidence_task_items ADD COLUMN IF NOT EXISTS llm_model VARCHAR(128);
ALTER TABLE paper_evidence_task_items ADD COLUMN IF NOT EXISTS prompt_version VARCHAR(64);
ALTER TABLE paper_evidence_task_items ADD COLUMN IF NOT EXISTS review_draft JSONB;
CREATE INDEX IF NOT EXISTS idx_evidence_task_items_retry ON paper_evidence_task_items (next_retry_at);
CREATE INDEX IF NOT EXISTS idx_evidence_task_items_evidence ON paper_evidence_task_items (evidence_id);
CREATE INDEX IF NOT EXISTS idx_evidence_task_items_tt ON paper_evidence_task_items (target_type, target_id);

-- 3) preprocessing draft passages (review-only; never formal evidence)
CREATE TABLE IF NOT EXISTS paper_evidence_task_item_passages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_item_id UUID NOT NULL REFERENCES paper_evidence_task_items(id) ON DELETE CASCADE,
    paper_id UUID,
    paper_passage_id UUID,
    paragraph_id VARCHAR(128),
    passage_text_snapshot TEXT NOT NULL,
    translation_zh TEXT,
    direction VARCHAR(16),
    evidence_level VARCHAR(16),
    supported_components JSONB NOT NULL DEFAULT '[]'::jsonb,
    reason TEXT,
    semantic_confidence NUMERIC,
    source_verified BOOLEAN NOT NULL DEFAULT FALSE,
    source_verification_method VARCHAR(32),
    rank INT,
    is_recommended BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_draft_passages_item ON paper_evidence_task_item_passages (task_item_id);
CREATE INDEX IF NOT EXISTS idx_draft_passages_paper ON paper_evidence_task_item_passages (paper_id);
