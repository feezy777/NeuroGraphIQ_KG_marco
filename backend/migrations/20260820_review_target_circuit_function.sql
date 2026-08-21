-- P1.7: mirror_human_review_records must accept 'circuit_function' targets.
--
-- mirror_review_service already normalizes circuit_function (P1.1 audit), but
-- the DB CHECK constraint (extended by 029) never listed it — circuit functions
-- could not be human-reviewed and therefore could never be promoted.
-- Idempotent: re-adds the full constraint with circuit_function included.

ALTER TABLE mirror_human_review_records
    DROP CONSTRAINT IF EXISTS chk_mirror_review_target_type;

ALTER TABLE mirror_human_review_records
    ADD CONSTRAINT chk_mirror_review_target_type CHECK (
        target_type IN (
            'connection',
            'function',
            'region_function',
            'circuit',
            'triple',
            'projection',
            'circuit_step',
            'projection_function',
            'circuit_function',
            'circuit_projection_membership',
            'circuit_projection_cross_validation_result',
            'dual_model_verification_result'
        )
    );
