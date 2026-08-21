-- 20260822_canonical_brain_region.sql (idempotent)
-- BR1: Canonical BrainRegion Core + L0/L1 Macro Backbone.
--
-- 1. canonical_brain_regions          — canonical BrainRegion concepts (L0/L1 in BR1)
-- 2. canonical_region_hierarchy       — child --part_of--> parent relation table
-- 3. candidate_brain_regions.canonical_region_id — FK anchor (legacy canonical_id stays)
-- 4. ontology_vocabularies seeds      — granularity_domain / granularity_level /
--                                       hemisphere_policy / mapping_match_type
--
-- BR1 只写入 L0/L1 数据；L2-L5 词表完整定义但本阶段不产生数据行。

-- ============ 1. canonical_brain_regions ============

CREATE TABLE IF NOT EXISTS canonical_brain_regions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    region_code VARCHAR(128) NOT NULL UNIQUE,
    canonical_name_en VARCHAR(512) NOT NULL,
    canonical_name_cn VARCHAR(512),
    species VARCHAR(16) NOT NULL DEFAULT 'human',
    granularity_domain VARCHAR(64) NOT NULL DEFAULT 'brain_region_anatomical',
    granularity_level VARCHAR(64) NOT NULL,
    hemisphere_policy VARCHAR(32) NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'proposed',
    description TEXT,
    confidence NUMERIC,
    source_summary JSONB NOT NULL DEFAULT '{}',
    external_mappings JSONB NOT NULL DEFAULT '{}',
    created_by VARCHAR(64) NOT NULL DEFAULT 'manual',
    replaced_by_region_id UUID REFERENCES canonical_brain_regions(id),
    merged_at TIMESTAMPTZ,
    merged_by VARCHAR(64),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_canonical_region_level_status
    ON canonical_brain_regions (granularity_level, status);
CREATE INDEX IF NOT EXISTS idx_canonical_region_species
    ON canonical_brain_regions (species);

-- ============ 2. canonical_region_hierarchy ============

CREATE TABLE IF NOT EXISTS canonical_region_hierarchy (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    child_region_id UUID NOT NULL REFERENCES canonical_brain_regions(id) ON DELETE CASCADE,
    parent_region_id UUID NOT NULL REFERENCES canonical_brain_regions(id) ON DELETE CASCADE,
    predicate VARCHAR(32) NOT NULL DEFAULT 'part_of',
    status VARCHAR(16) NOT NULL DEFAULT 'active',
    source VARCHAR(128),
    confidence NUMERIC,
    provenance_json JSONB NOT NULL DEFAULT '{}',
    created_by VARCHAR(64),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT chk_region_hierarchy_not_self CHECK (child_region_id <> parent_region_id),
    CONSTRAINT chk_region_hierarchy_predicate CHECK (predicate = 'part_of'),
    CONSTRAINT uq_region_hierarchy_edge UNIQUE (child_region_id, predicate, parent_region_id)
);
CREATE INDEX IF NOT EXISTS idx_region_hierarchy_child
    ON canonical_region_hierarchy (child_region_id);
CREATE INDEX IF NOT EXISTS idx_region_hierarchy_parent
    ON canonical_region_hierarchy (parent_region_id);

-- ============ 3. candidate_brain_regions anchor ============

ALTER TABLE candidate_brain_regions ADD COLUMN IF NOT EXISTS canonical_region_id UUID
    REFERENCES canonical_brain_regions(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS idx_candidate_canonical_region
    ON candidate_brain_regions (canonical_region_id)
    WHERE canonical_region_id IS NOT NULL;

-- legacy canonical_id 标记为非权威（source-local 回填键，勿再作为跨 Atlas identity 使用）。
COMMENT ON COLUMN candidate_brain_regions.canonical_id IS
    'LEGACY source-local backfill key (e.g. Macro96_<name>); NOT authoritative. Use canonical_region_id.';

-- ============ 4. granularity / hemisphere / mapping vocabularies ============

INSERT INTO ontology_vocabularies (code, vocab_type, label_en, label_cn, description, seq) VALUES
('brain_region_anatomical','granularity_domain','brain_region_anatomical','脑区解剖域','BrainRegion anatomical granularity (L0 whole_brain -> L5 ultra_fine)',10),
('connection_resolution','granularity_domain','connection_resolution','连接分辨率域','Connection resolution (macro_aggregated -> fine_asserted)',20),
('circuit_resolution','granularity_domain','circuit_resolution','回路分辨率域','Circuit resolution (macro_abstract -> fine_topology)',30),
('function_specificity','granularity_domain','function_specificity','功能特化域','Function specificity (broader -> specific)',40),
('whole_brain','granularity_level','whole_brain (L0)','全脑 (L0)','Whole brain / major division',10),
('macro','granularity_level','macro (L1)','宏观 (L1)','Macro clinical layer — reference pool = Macro96 (96 regions, whole pool treated as macro, including Desikan-style cortex); macro layer is the clinical usage boundary; finer levels are research/inference layers',20),
('meso','granularity_level','meso (L2)','中观 (L2)','Meso (HCP-MMP/Desikan)',30),
('parcel','granularity_level','parcel (L3)','图谱分区 (L3)','Atlas parcel / subregion (Brainnetome etc.)',40),
('fine','granularity_level','fine (L4)','精细 (L4)','Fine cytoarchitectonic (Julich)',50),
('ultra_fine','granularity_level','ultra_fine (L5)','超精细 (L5)','Ultra-fine (future)',60),
('bilateral','hemisphere_policy','bilateral','双侧','Canonical concept covers both hemispheres',10),
('lateralized','hemisphere_policy','lateralized','左右配对','Paired structure; left/right anchors via candidate laterality',20),
('midline_unpaired','hemisphere_policy','midline_unpaired','中线不分侧','Midline structure, no laterality split',30),
('exact','mapping_match_type','exact','精确','Direct identity mapping',10),
('close','mapping_match_type','close','接近','High-confidence but not literal identity',20),
('broader','mapping_match_type','broader','更粗','Candidate maps to a broader canonical concept',30),
('narrower','mapping_match_type','narrower','更细','Candidate maps to a narrower canonical concept',40),
('uncertain','mapping_match_type','uncertain','不确定','Ambiguous mapping awaiting review',50),
('rejected','mapping_match_type','rejected','否决','Mapping rejected',60)
ON CONFLICT (code, vocab_type) DO NOTHING;
