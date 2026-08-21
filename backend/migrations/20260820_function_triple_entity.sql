-- P1.5: Function Triple entity-ization support.
--
-- projection_version tags the consolidation/rebuild run that produced each
-- triple row — used by P1.6 incremental projection / rebuild / integrity
-- compare. Idempotent.
--
-- NOTE: idx (object_type, object_id) already exists as idx_mirror_triple_object
-- (verified 2026-08-20), so no duplicate index is created.

ALTER TABLE mirror_kg_triples
    ADD COLUMN IF NOT EXISTS projection_version VARCHAR(64);
