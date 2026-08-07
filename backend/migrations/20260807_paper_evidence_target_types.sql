-- 20260807_paper_evidence_target_types.sql (idempotent)
-- Allow mirror evidence records to target macro/molecular object types.

ALTER TABLE mirror_evidence_records DROP CONSTRAINT IF EXISTS chk_mirror_evidence_target_type;
ALTER TABLE mirror_evidence_records ADD CONSTRAINT chk_mirror_evidence_target_type CHECK (
    evidence_target_type IN (
        'mirror_connection', 'mirror_function', 'mirror_circuit', 'mirror_triple',
        'connection', 'projection', 'projection_function', 'circuit_function',
        'region_function', 'circuit', 'circuit_step', 'unknown'
    )
);

ALTER TABLE mirror_evidence_records DROP CONSTRAINT IF EXISTS chk_mirror_evidence_type;
ALTER TABLE mirror_evidence_records ADD CONSTRAINT chk_mirror_evidence_type CHECK (
    evidence_type IN (
        'llm_explanation', 'literature', 'curated_database',
        'manual_note', 'rule_validation', 'paper_verification', 'unknown'
    )
);
