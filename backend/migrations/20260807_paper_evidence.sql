-- 20260807_paper_evidence.sql (idempotent)
-- Paper-evidence verification fields on mirror_evidence_records (Phase B).

ALTER TABLE mirror_evidence_records ADD COLUMN IF NOT EXISTS evidence_direction VARCHAR(16);
ALTER TABLE mirror_evidence_records ADD COLUMN IF NOT EXISTS verification_status VARCHAR(16) NOT NULL DEFAULT 'pending';
ALTER TABLE mirror_evidence_records ADD COLUMN IF NOT EXISTS paper_source VARCHAR(32);
ALTER TABLE mirror_evidence_records ADD COLUMN IF NOT EXISTS paper_pmid VARCHAR(64);
ALTER TABLE mirror_evidence_records ADD COLUMN IF NOT EXISTS paper_doi VARCHAR(256);
ALTER TABLE mirror_evidence_records ADD COLUMN IF NOT EXISTS paper_title TEXT;
ALTER TABLE mirror_evidence_records ADD COLUMN IF NOT EXISTS paper_journal VARCHAR(256);
ALTER TABLE mirror_evidence_records ADD COLUMN IF NOT EXISTS paper_year INT;
ALTER TABLE mirror_evidence_records ADD COLUMN IF NOT EXISTS suggested_confidence NUMERIC;
ALTER TABLE mirror_evidence_records ADD COLUMN IF NOT EXISTS confidence_adjustment_status VARCHAR(16) NOT NULL DEFAULT 'none';
ALTER TABLE mirror_evidence_records ADD COLUMN IF NOT EXISTS verification_by VARCHAR(64);
ALTER TABLE mirror_evidence_records ADD COLUMN IF NOT EXISTS verification_at TIMESTAMPTZ;
