-- 20260807_paper_evidence_v7.sql (idempotent)
-- Formal evidence review snapshot: claim / coverage / model vs reviewer judgment.
-- Historical rows keep NULL snapshots (never fabricated); new human_verified
-- evidence must persist complete snapshots.

ALTER TABLE mirror_evidence_records ADD COLUMN IF NOT EXISTS claim_version VARCHAR(32);
ALTER TABLE mirror_evidence_records ADD COLUMN IF NOT EXISTS claim_text_snapshot TEXT;
ALTER TABLE mirror_evidence_records ADD COLUMN IF NOT EXISTS claim_components_snapshot JSONB;
ALTER TABLE mirror_evidence_records ADD COLUMN IF NOT EXISTS coverage_summary_snapshot JSONB;
ALTER TABLE mirror_evidence_records ADD COLUMN IF NOT EXISTS coverage_formula_version VARCHAR(64);
ALTER TABLE mirror_evidence_records ADD COLUMN IF NOT EXISTS model_direction VARCHAR(16);
ALTER TABLE mirror_evidence_records ADD COLUMN IF NOT EXISTS model_assessment TEXT;
ALTER TABLE mirror_evidence_records ADD COLUMN IF NOT EXISTS reviewer_note TEXT;
COMMENT ON COLUMN mirror_evidence_records.coverage_formula_version IS
  'coverage aggregation formula used at review time (e.g. paper_evidence_coverage_v1)';
