-- 20260823_macro96_canonical_l2.sql (idempotent)
-- BR2: Macro96 -> Canonical BrainRegion L2 (Clinical regions).
--
-- 1. granularity_level vocabulary revision:
--    L0 whole_brain / L1 macro (system) / L2 clinical (Macro96) /
--    L3 research / L4 fine / L5 ultra_fine (future)
--    (legacy 'meso'/'parcel' rows are deprecated, kept for historical references)
-- 2. connection_region_alignment table (endpoint canonical alignment, CN1 prep)
-- 3. canonical_brain_regions._laterality? no — laterality lives on candidates.

-- ============ 1. granularity_level vocabulary revision ============

UPDATE ontology_vocabularies SET label_en='macro (L1 system)', label_cn='宏观 (L1 系统)',
    description='L1 Macro system: major brain divisions (Cerebrum / Diencephalon / Brain stem / Cerebellum). '
                'Clinical reference family is the Macro96 pool, whose 96 structures form the L2 clinical layer.',
    seq=20
WHERE code='macro' AND vocab_type='granularity_level';

INSERT INTO ontology_vocabularies (code, vocab_type, label_en, label_cn, description, seq) VALUES
('clinical','granularity_level','clinical (L2)','临床 (L2)','L2 Clinical regions: Macro96 96-pool structures (whole pool, incl. Desikan-style cortex). Clinical usage boundary — clinical browsing/query stops here.',30),
('research','granularity_level','research (L3)','研究 (L3)','L3 Research regions: finer research-layer regions (Allen/Brainnetome/HCP-MMP alignment in BR3).',40)
ON CONFLICT (code, vocab_type) DO NOTHING;

UPDATE ontology_vocabularies SET label_en='fine (L4)', label_cn='精细 (L4)', seq=50
WHERE code='fine' AND vocab_type='granularity_level';

UPDATE ontology_vocabularies SET label_en='ultra_fine (L5)', label_cn='超精细 (L5)', seq=60
WHERE code='ultra_fine' AND vocab_type='granularity_level';

-- legacy meso/parcel rows: deprecated (no longer assignable to canonical regions)
UPDATE ontology_vocabularies SET status='deprecated',
    description='LEGACY level name (superseded by clinical/research); kept for historical references'
WHERE code IN ('meso','parcel') AND vocab_type='granularity_level';

-- ============ 2. connection_region_alignment ============

CREATE TABLE IF NOT EXISTS connection_region_alignment (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    connection_id UUID NOT NULL REFERENCES mirror_region_connections(id) ON DELETE CASCADE,
    source_candidate_id UUID REFERENCES candidate_brain_regions(id) ON DELETE SET NULL,
    source_canonical_region_id UUID REFERENCES canonical_brain_regions(id) ON DELETE SET NULL,
    target_candidate_id UUID REFERENCES candidate_brain_regions(id) ON DELETE SET NULL,
    target_canonical_region_id UUID REFERENCES canonical_brain_regions(id) ON DELETE SET NULL,
    mapping_type VARCHAR(32) NOT NULL DEFAULT 'exact',
    confidence NUMERIC,
    source_atlas VARCHAR(128),
    granularity_level VARCHAR(64),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_connection_alignment UNIQUE (connection_id)
);
CREATE INDEX IF NOT EXISTS idx_connection_alignment_source_canonical
    ON connection_region_alignment (source_canonical_region_id);
CREATE INDEX IF NOT EXISTS idx_connection_alignment_target_canonical
    ON connection_region_alignment (target_canonical_region_id);
