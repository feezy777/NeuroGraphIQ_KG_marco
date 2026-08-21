-- 20260827_multiscale_atlas_layer.sql (idempotent)
-- BR3-M2: 多尺度 Atlas Resource 数据层。
--
-- 排序: 编号 20260827,必须排在 20260826_multiscale_granularity_refactor.sql
-- (粒度词表)与 20260822_canonical_brain_region.sql (atlas_region_mappings /
-- region_*_alignment 的 FK 目标 canonical_brain_regions) 之后。
--
-- 设计原则:
--   * 外部 atlas 原始数据一律进 atlas_region_resources,绝不直接写入 canonical;
--   * atlas_region -> canonical_region 经由 atlas_region_mappings (可审计、可撤销);
--   * CellType / MolecularEntity 不是 BrainRegion,独立注册表 + 对齐表;
--   * 本迁移只建表 + 登记来源;数据行由 seed 脚本 / 导入接口写入。

-- ============ 1. atlas_resources CHECK 升级 (允许 subregion/cyto; 保留既有 legacy 值) ============

DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'chk_atlas_resources_granularity_level'
  ) THEN
    ALTER TABLE atlas_resources DROP CONSTRAINT chk_atlas_resources_granularity_level;
  END IF;
  IF EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'chk_atlas_resources_granularity_family'
  ) THEN
    ALTER TABLE atlas_resources DROP CONSTRAINT chk_atlas_resources_granularity_family;
  END IF;
END $$;

ALTER TABLE atlas_resources ADD CONSTRAINT chk_atlas_resources_granularity_level CHECK (
    granularity_level IN (
        'macro', 'meso', 'subregion', 'cyto', 'molecular', 'term', 'micro',
        -- legacy values kept for existing rows (live DB constraints were previously altered):
        'sub_connectivity', 'fine_cyto', 'molecular_attr'
    )
);

ALTER TABLE atlas_resources ADD CONSTRAINT chk_atlas_resources_granularity_family CHECK (
    granularity_family IN (
        'macro_clinical', 'meso_anatomical', 'subregion_connectivity', 'cytoarchitectonic',
        'histological', 'molecular', 'terminology',
        -- legacy values kept for existing rows:
        'sub_connectivity', 'fine_cyto', 'molecular_attr'
    )
);

-- ============ 2. atlas_region_resources (atlas 原始脑区行) ============

CREATE TABLE IF NOT EXISTS atlas_region_resources (
    id                 UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    atlas_resource_id  UUID REFERENCES atlas_resources(id) ON DELETE SET NULL,
    atlas_name         VARCHAR(128) NOT NULL,
    atlas_version      VARCHAR(64) NOT NULL DEFAULT '',
    atlas_region_id    VARCHAR(128) NOT NULL,   -- atlas 原生 ID (如 Allen structure id 1089)
    region_name        VARCHAR(500) NOT NULL,
    region_acronym     VARCHAR(64),
    parent_region_id   VARCHAR(128),            -- atlas 原生父 ID (同表引用,应用层校验)
    species            VARCHAR(32) NOT NULL DEFAULT 'human',
    hemisphere         VARCHAR(16) NOT NULL DEFAULT 'unknown',  -- L/R/bilateral/midline/unknown
    source_file        VARCHAR(500),
    provenance         JSONB NOT NULL DEFAULT '{}'::jsonb,
    status             VARCHAR(32) NOT NULL DEFAULT 'active',   -- active/superseded
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_atlas_region_resources_native UNIQUE (atlas_name, atlas_version, atlas_region_id),
    CONSTRAINT chk_atlas_region_resources_status CHECK (status IN ('active', 'superseded')),
    CONSTRAINT chk_atlas_region_resources_hemisphere CHECK (
        hemisphere IN ('L', 'R', 'bilateral', 'midline', 'unknown')
    )
);

CREATE INDEX IF NOT EXISTS idx_atlas_region_resources_parent
    ON atlas_region_resources (atlas_name, atlas_version, parent_region_id);
CREATE INDEX IF NOT EXISTS idx_atlas_region_resources_atlas
    ON atlas_region_resources (atlas_resource_id);

-- ============ 3. atlas_region_mappings (atlas_region -> canonical_region) ============

CREATE TABLE IF NOT EXISTS atlas_region_mappings (
    id                 UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    atlas_region_id    UUID NOT NULL REFERENCES atlas_region_resources(id) ON DELETE CASCADE,
    canonical_region_id UUID REFERENCES canonical_brain_regions(id) ON DELETE SET NULL,
    mapping_type       VARCHAR(32) NOT NULL,   -- exact/broader/narrower/uncertain
    confidence         DOUBLE PRECISION,
    species_relation   VARCHAR(32) NOT NULL DEFAULT 'same_species',  -- same_species/homology/unknown
    match_details      JSONB NOT NULL DEFAULT '{}'::jsonb,
    provenance         JSONB NOT NULL DEFAULT '{}'::jsonb,
    status             VARCHAR(32) NOT NULL DEFAULT 'active',  -- active/superseded
    created_by         VARCHAR(64) NOT NULL DEFAULT 'manual',
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_atlas_region_mappings_type CHECK (
        mapping_type IN ('exact', 'broader', 'narrower', 'uncertain')
    ),
    CONSTRAINT chk_atlas_region_mappings_species_rel CHECK (
        species_relation IN ('same_species', 'homology', 'unknown')
    ),
    CONSTRAINT chk_atlas_region_mappings_status CHECK (status IN ('active', 'superseded')),
    CONSTRAINT chk_atlas_region_mappings_conf CHECK (
        confidence IS NULL OR (confidence >= 0 AND confidence <= 1)
    )
);

CREATE INDEX IF NOT EXISTS idx_atlas_region_mappings_atlas
    ON atlas_region_mappings (atlas_region_id) WHERE status = 'active';
CREATE INDEX IF NOT EXISTS idx_atlas_region_mappings_canonical
    ON atlas_region_mappings (canonical_region_id) WHERE status = 'active';

-- ============ 4. cell_type_registry (细胞类型: 独立实体,不是 BrainRegion) ============

CREATE TABLE IF NOT EXISTS cell_type_registry (
    id                 UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    cell_type_code     VARCHAR(128) NOT NULL,    -- ng:ct:<slug>
    canonical_name_en  VARCHAR(512) NOT NULL,
    canonical_name_cn  VARCHAR(512),
    species            VARCHAR(32) NOT NULL DEFAULT 'human',
    taxonomy_source    VARCHAR(256),             -- e.g. Allen Cell Types Database
    taxonomy_version   VARCHAR(64),
    external_iri       VARCHAR(256),
    description        TEXT,
    provenance         JSONB NOT NULL DEFAULT '{}'::jsonb,
    status             VARCHAR(32) NOT NULL DEFAULT 'active',  -- active/deprecated
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_cell_type_registry_code UNIQUE (cell_type_code),
    CONSTRAINT chk_cell_type_registry_status CHECK (status IN ('active', 'deprecated'))
);

-- ============ 5. region_cell_alignment (脑区 x 细胞类型 对齐) ============

CREATE TABLE IF NOT EXISTS region_cell_alignment (
    id                 UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    region_id          UUID NOT NULL REFERENCES canonical_brain_regions(id) ON DELETE CASCADE,
    cell_type_id       UUID NOT NULL REFERENCES cell_type_registry(id) ON DELETE CASCADE,
    mapping_type       VARCHAR(32) NOT NULL,   -- contains/enriched/marker/unknown
    confidence         DOUBLE PRECISION,
    provenance         JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_region_cell_alignment UNIQUE (region_id, cell_type_id, mapping_type),
    CONSTRAINT chk_region_cell_alignment_type CHECK (
        mapping_type IN ('contains', 'enriched', 'marker', 'unknown')
    ),
    CONSTRAINT chk_region_cell_alignment_conf CHECK (
        confidence IS NULL OR (confidence >= 0 AND confidence <= 1)
    )
);

CREATE INDEX IF NOT EXISTS idx_region_cell_alignment_region ON region_cell_alignment (region_id);
CREATE INDEX IF NOT EXISTS idx_region_cell_alignment_cell ON region_cell_alignment (cell_type_id);

-- ============ 6. molecular_entity_registry (分子实体: 独立实体,不是 BrainRegion) ============

CREATE TABLE IF NOT EXISTS molecular_entity_registry (
    id                 UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    entity_code        VARCHAR(128) NOT NULL,    -- ng:mol:<slug>
    entity_type        VARCHAR(32) NOT NULL,     -- gene/protein/neurotransmitter/receptor
    canonical_name_en  VARCHAR(512) NOT NULL,
    canonical_name_cn  VARCHAR(512),
    external_iri       VARCHAR(256),
    species            VARCHAR(32) NOT NULL DEFAULT 'human',
    description        TEXT,
    provenance         JSONB NOT NULL DEFAULT '{}'::jsonb,
    status             VARCHAR(32) NOT NULL DEFAULT 'active',  -- active/deprecated
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_molecular_entity_registry_code UNIQUE (entity_code),
    CONSTRAINT chk_molecular_entity_registry_type CHECK (
        entity_type IN ('gene', 'protein', 'neurotransmitter', 'receptor')
    ),
    CONSTRAINT chk_molecular_entity_registry_status CHECK (status IN ('active', 'deprecated'))
);

-- ============ 7. region_molecular_alignment (脑区 x 分子实体 对齐) ============

CREATE TABLE IF NOT EXISTS region_molecular_alignment (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    region_id           UUID NOT NULL REFERENCES canonical_brain_regions(id) ON DELETE CASCADE,
    molecular_entity_id UUID NOT NULL REFERENCES molecular_entity_registry(id) ON DELETE CASCADE,
    entity_type         VARCHAR(32) NOT NULL,     -- 冗余自 registry,便于按 spec 字段查询
    evidence_type       VARCHAR(32) NOT NULL DEFAULT 'expression',  -- expression/enrichment/literature
    confidence          DOUBLE PRECISION,
    source              VARCHAR(500),
    provenance          JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_region_molecular_alignment UNIQUE (region_id, molecular_entity_id, evidence_type),
    CONSTRAINT chk_region_molecular_alignment_conf CHECK (
        confidence IS NULL OR (confidence >= 0 AND confidence <= 1)
    )
);

CREATE INDEX IF NOT EXISTS idx_region_molecular_alignment_region ON region_molecular_alignment (region_id);
CREATE INDEX IF NOT EXISTS idx_region_molecular_alignment_entity ON region_molecular_alignment (molecular_entity_id);

-- ============ 8. 来源登记 (idempotent) ============

INSERT INTO atlas_resources (
    resource_code, source_atlas, source_version, resource_type, species,
    granularity_level, granularity_family, template_space,
    cn_name, en_name, description, remark, status
) VALUES
('allen_mouse_p56_structure',
 'Allen Mouse Brain Atlas', 'P56 structure ontology', 'ontology', 'mouse',
 'meso', 'meso_anatomical', 'native',
 'Allen 小鼠脑图谱 P56 结构本体', 'Allen Mouse Brain Atlas P56 structure ontology',
 '1327-structure mouse P56 ontology (structures.json, CCFv3 native space); raw rows imported into atlas_region_resources in BR3.',
 'structures.json 实际内容为小鼠 P56 结构本体(ontology_id=1); 物种已按事实标记为 mouse,不复用 HBA 标签。', 'active'),
('allen_hba_structure',
 'Allen Human Brain Atlas', 'structure ontology (ABA API)', 'ontology', 'human',
 'meso', 'meso_anatomical', 'MNI152',
 'Allen 人脑图谱结构本体', 'Allen Human Brain Atlas structure ontology',
 'Registered meso source. ABA structures ontology provides human HBA region tree.',
 '数据文件待获取 (ABA API structures dump); 本阶段仅登记 + 导入接口,不虚构数据。', 'active'),
('brainnetome_bna246',
 'Brainnetome Atlas', 'BNA246 (2016)', 'atlas', 'human',
 'meso', 'meso_anatomical', 'MNI152',
 '脑网络组图谱 BNA246', 'Brainnetome Atlas BNA246',
 'Registered meso source. 246 human subregions with MNI coordinates.',
 '官方 BNA_subregions.xlsx 在当前开发环境无法下载(网络受限); 本阶段仅登记 + parser 接口,不虚构 BNA 行。', 'active'),
('hippocampal_subfield_winterburn',
 'Hippocampal Subfield Atlas', 'Winterburn 2013', 'atlas', 'human',
 'subregion', 'subregion_connectivity', 'MNI152',
 '海马亚区图谱 (Winterburn 2013)', 'Hippocampal Subfield Atlas (Winterburn et al. 2013)',
 'Registered subregion source: CA1/CA2/CA3/CA4/DG/subiculum subfield maps.',
 '数据文件待获取; 本阶段仅登记 + 导入接口。', 'active'),
('allen_cell_types_database',
 'Allen Cell Types Database', '2020 taxonomy', 'ontology', 'human',
 'cyto', 'cytoarchitectonic', 'unknown',
 'Allen 细胞类型数据库', 'Allen Cell Types Database',
 'Registered cyto-layer cell type source (human + mouse). Cell types are NOT BrainRegions — feed cell_type_registry + region_cell_alignment.',
 '本阶段仅登记接口,不做细胞类型批量导入。', 'active'),
('julich_brain_siibra',
 'Julich-Brain Atlas', 'siibra cytoarchitectonic maps', 'atlas', 'human',
 'cyto', 'cytoarchitectonic', 'MNI152',
 'Julich-Brain 细胞构筑图谱', 'Julich-Brain Atlas (siibra)',
 'Registered cyto-layer region source; existing siibra_parser covers JSON/CSV region trees.',
 '本阶段仅登记; 区域接入待后续阶段。', 'active'),
('allen_hba_expression',
 'Allen Human Brain Atlas', 'microarray expression', 'connectivity_matrix', 'human',
 'molecular', 'molecular', 'MNI152',
 'Allen 人脑基因表达数据集', 'Allen Human Brain Atlas microarray expression',
 'Existing molecular_attr family source (Allen HBA gene expression).',
 'BR3 不做大规模 molecular_attr 导入; 仅登记既有来源。', 'active')
ON CONFLICT (resource_code) DO NOTHING;
