-- Fix StringDataRightTruncation on promote:
-- confidence_adjustment_status was VARCHAR(16) but the weak-evidence branch
-- writes 'no_change_weak_evidence' (23 chars). Widen to 32.
ALTER TABLE mirror_evidence_records ALTER COLUMN confidence_adjustment_status TYPE VARCHAR(32);
