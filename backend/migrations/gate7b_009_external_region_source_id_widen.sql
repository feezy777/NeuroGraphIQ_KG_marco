-- Gate 7B Phase 6 — widen external_regions.source_region_id (VARCHAR(64) -> VARCHAR(255))
--
-- Rationale:
--   external_regions.source_region_id is the authority for an external atlas parcel's
--   official stable identifier. Julich-Brain v3.1 official region ids reach ~125 chars
--   (e.g. JULICH_BRAIN_CYTOARCHITECTONIC_ATLAS_V3_1_...), which exceeds VARCHAR(64).
--   VARCHAR(255) leaves headroom for future atlases without resorting to truncation /
--   hashing / prefix-stripping (all of which would corrupt identity).
--
-- Scope:
--   ALTER the single column type. No data change (all existing values fit), no other
--   column touched, no index/unique rebuild needed (idx_external_regions_source_region_id
--   is a plain btree index; varchar varlena length is not part of the index).

ALTER TABLE public.external_regions
    ALTER COLUMN source_region_id TYPE VARCHAR(255);

COMMENT ON COLUMN public.external_regions.source_region_id IS
    'Official stable identifier of the external atlas parcel (full original text, up to 255 chars). '
    'Identity authority for the atlas parcel. Widened from VARCHAR(64) for long ids '
    '(e.g. Julich-Brain v3.1, up to ~125 chars).';
