-- 20260807_paper_evidence_v6.sql (idempotent)
-- Persist human-adjusted supported_components on evidence passages.
ALTER TABLE mirror_evidence_passages ADD COLUMN IF NOT EXISTS supported_components JSONB NOT NULL DEFAULT '[]'::jsonb;
