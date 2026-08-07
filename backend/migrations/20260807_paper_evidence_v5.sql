-- 20260807_paper_evidence_v5.sql (idempotent)
-- Data-integrity closure: real FKs + source verification method. No data loss.

-- 1) source_verification_method on evidence passages (persisted verification provenance).
ALTER TABLE mirror_evidence_passages ADD COLUMN IF NOT EXISTS source_verification_method VARCHAR(32);
COMMENT ON COLUMN mirror_evidence_passages.source_verification_method IS
  'exact | normalized_whitespace | normalized_unicode | NULL(not verified)';

-- 2) Safe orphan cleanup BEFORE adding FKs (keeps migration idempotent and non-failing).
UPDATE mirror_evidence_records e
   SET paper_id = NULL
 WHERE e.paper_id IS NOT NULL
   AND NOT EXISTS (SELECT 1 FROM paper_sources p WHERE p.id = e.paper_id);

UPDATE mirror_evidence_passages ep
   SET paper_passage_id = NULL
 WHERE ep.paper_passage_id IS NOT NULL
   AND NOT EXISTS (SELECT 1 FROM paper_passages pp WHERE pp.id = ep.paper_passage_id);

UPDATE confidence_adjustment_logs l
   SET evidence_id = NULL
 WHERE l.evidence_id IS NOT NULL
   AND NOT EXISTS (SELECT 1 FROM mirror_evidence_records r WHERE r.id = l.evidence_id);

-- 3) Real foreign keys (audit trails use ON DELETE SET NULL, never cascade).
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_evidence_records_paper'
    ) THEN
        ALTER TABLE mirror_evidence_records
            ADD CONSTRAINT fk_evidence_records_paper
            FOREIGN KEY (paper_id) REFERENCES paper_sources(id) ON DELETE SET NULL;
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_evidence_passages_paper_passage'
    ) THEN
        ALTER TABLE mirror_evidence_passages
            ADD CONSTRAINT fk_evidence_passages_paper_passage
            FOREIGN KEY (paper_passage_id) REFERENCES paper_passages(id) ON DELETE SET NULL;
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_conf_adjustment_logs_evidence'
    ) THEN
        ALTER TABLE confidence_adjustment_logs
            ADD CONSTRAINT fk_conf_adjustment_logs_evidence
            FOREIGN KEY (evidence_id) REFERENCES mirror_evidence_records(id) ON DELETE SET NULL;
    END IF;
END $$;
