-- 20260826_multiscale_granularity_refactor.sql (idempotent)
-- BR3-M1: 多尺度粒度体系重构。
--
-- 排序: 编号 20260826,必须排在 20260822_canonical_brain_region.sql 与
-- 20260823_macro96_canonical_l2.sql 之后 — 本迁移 UPDATE 的 granularity_level
-- 行(clinical/research/whole_brain/...)由 20260823 创建/定稿,旧 'meso'/'parcel'
-- 行也由 20260823 置 deprecated,顺序颠倒会导致 UPDATE 命中 0 行。
--
-- 目标尺度:  macro -> meso -> subregion -> cyto -> molecular
-- (标签中的 L1..L5 为五级主尺度 band 序号; level_order 为 10 级交错全局序:
--  0 whole_brain / 1 macro / 2 clinical / 3 meso / 4 research / 5 subregion /
--  6 fine / 7 cyto / 8 ultra_fine / 9 molecular)
--
-- 1. ontology_vocabularies 增加 level_order / source_strategy 两列
--    (granularity_level 词表专用; 其他 vocab_type 保持 NULL)。
-- 2. 粒度词表升级为五级主尺度 + 旧值兼容保留:
--      canonical (new)          legacy (kept active, compat)
--      macro (L1)               whole_brain (L0) / clinical (L2)
--      meso (L2)                research (L3)
--      subregion (L3)           parcel (deprecated, 不激活)
--      cyto (L4)                fine (L4)
--      molecular (L5)           ultra_fine (L5)
--    旧值全部保留 active(除 parcel),不破坏已有数据行与既有测试;
--    兼容映射记录在 granularity_level_compat_map。
-- 3. Macro96 数据(canonical_brain_regions / candidate_brain_regions /
--    canonical_region_hierarchy 中的 clinical 层)一律不动。
--
-- 注: 旧 'meso' 行(20260823 被置 deprecated)重新激活并赋予新语义。

-- ============ 1. 词表新列 ============

ALTER TABLE ontology_vocabularies ADD COLUMN IF NOT EXISTS level_order INT;
ALTER TABLE ontology_vocabularies ADD COLUMN IF NOT EXISTS source_strategy TEXT;

-- ============ 2. 五级主尺度词表 (idempotent upserts) ============

-- macro (L1) — 已有行升级
UPDATE ontology_vocabularies SET
    status='active',
    label_en='macro (L1)',
    label_cn='宏观 (L1)',
    description='L1 Macro: major brain divisions + Macro96 clinical pool. Clinical usage boundary; finer levels are research layers. Canonical scale level: macro.',
    level_order=1,
    source_strategy='Macro96 standard 96-pool (existing clinical canonical layer). No new bulk imports; keep as clinical macro reference.',
    seq=10
WHERE code='macro' AND vocab_type='granularity_level';

-- meso (L2) — 复活旧行并赋予新语义
UPDATE ontology_vocabularies SET
    status='active',
    label_en='meso (L2)',
    label_cn='中观 (L2)',
    description='L2 Meso: meso-anatomical regions (hippocampal formation, DLPFC, ...). Atlas sources: Allen Human Brain Atlas structure ontology + Brainnetome BNA246 (registered; HCP-MMP/Desikan future).',
    level_order=3,
    source_strategy='atlas_region_resources -> atlas_region_mappings -> canonical_brain_regions (granularity_level=meso). Sources: Allen HBA structure ontology (registered), Brainnetome BNA246 (registered).',
    seq=30
WHERE code='meso' AND vocab_type='granularity_level';

-- subregion (L3) — 新行
INSERT INTO ontology_vocabularies (code, vocab_type, label_en, label_cn, description, status, seq, level_order, source_strategy) VALUES
('subregion','granularity_level','subregion (L3)','亚区 (L3)',
 'L3 Subregion: subfield / subnucleus level (hippocampal CA1/CA3/dentate gyrus, amygdala subnuclei). Sources: Allen structure subfields + Hippocampal Subfield Atlas. Curated canonical anchors only — no bulk import in BR3.',
 'active', 50, 5,
 'Registered sources: Allen Human/Mouse Brain Atlas subfields, Hippocampal Subfield Atlas (Winterburn 2013). Import interface ready; curated canonical anchors only.')
ON CONFLICT (code, vocab_type) DO NOTHING;

-- cyto (L4) — 新行
INSERT INTO ontology_vocabularies (code, vocab_type, label_en, label_cn, description, status, seq, level_order, source_strategy) VALUES
('cyto','granularity_level','cyto (L4)','细胞构筑 (L4)',
 'L4 Cyto: cytoarchitectonic regions (Julich-Brain areas) — still BrainRegions. Cell types are NOT BrainRegions: they live in cell_type_registry with region_cell_alignment (Allen Cell Types Database).',
 'active', 70, 7,
 'Region layer: Julich-Brain cytoarchitectonic areas (siibra parser, registered). Cell layer: cell_type_registry + region_cell_alignment (Allen Cell Types Database, registered).'),
('molecular','granularity_level','molecular (L5)','分子 (L5)',
 'L5 Molecular: molecular entities (gene/protein/neurotransmitter) aligned to regions. Molecular entities are NOT BrainRegions: they live in molecular_entity_registry with region_molecular_alignment. No bulk molecular_attr import in BR3.',
 'active', 90, 9,
 'Existing molecular_attr family (Allen HBA expression) stays as-is. New layer: molecular_entity_registry + region_molecular_alignment (interface only, no bulk import).')
ON CONFLICT (code, vocab_type) DO NOTHING;

-- ============ 3. 旧值兼容保留 (仍 active, 补 level_order / source_strategy) ============

UPDATE ontology_vocabularies SET
    level_order=0,
    source_strategy='LEGACY compat level (L0 whole brain). Kept active for existing data; compat_map: whole_brain -> macro.',
    seq=0
WHERE code='whole_brain' AND vocab_type='granularity_level';

UPDATE ontology_vocabularies SET
    level_order=2,
    source_strategy='LEGACY compat level (L2 clinical, Macro96 96-pool). Kept active for existing data; compat_map: clinical -> macro.',
    seq=20
WHERE code='clinical' AND vocab_type='granularity_level';

UPDATE ontology_vocabularies SET
    level_order=4,
    source_strategy='LEGACY compat level (L3 research). Kept active for existing data; compat_map: research -> meso.',
    seq=40
WHERE code='research' AND vocab_type='granularity_level';

UPDATE ontology_vocabularies SET
    level_order=6,
    source_strategy='LEGACY compat level (L4 fine). Kept active for existing data; compat_map: fine -> cyto.',
    seq=60
WHERE code='fine' AND vocab_type='granularity_level';

UPDATE ontology_vocabularies SET
    level_order=8,
    source_strategy='LEGACY compat level (L5 ultra_fine). Kept active for existing data; compat_map: ultra_fine -> molecular.',
    seq=80
WHERE code='ultra_fine' AND vocab_type='granularity_level';

-- parcel 保持 deprecated (历史引用仅查询; 自包含,不依赖 20260823)
UPDATE ontology_vocabularies SET
    status='deprecated',
    description='LEGACY level name (superseded by subregion); kept deprecated for historical references.',
    level_order=NULL,
    source_strategy=NULL
WHERE code='parcel' AND vocab_type='granularity_level';

-- ============ 4. 兼容映射表 ============

CREATE TABLE IF NOT EXISTS granularity_level_compat_map (
    legacy_level VARCHAR(64) PRIMARY KEY,
    canonical_level VARCHAR(64) NOT NULL,
    note TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO granularity_level_compat_map (legacy_level, canonical_level, note) VALUES
('whole_brain','macro','L0 whole-brain level folds into the macro band of the new scale'),
('clinical','macro','Macro96 96-pool clinical layer is part of the macro band'),
('research','meso','legacy L3 research regions align with the meso band (Allen/Brainnetome/HCP-MMP)'),
('fine','cyto','legacy L4 fine aligns with the cyto band'),
('ultra_fine','molecular','legacy L5 ultra_fine aligns with the molecular band'),
('parcel','subregion','legacy L3 parcel aligns with the subregion band')
ON CONFLICT (legacy_level) DO UPDATE SET canonical_level=EXCLUDED.canonical_level, note=EXCLUDED.note;

-- ============ 5. granularity_domain 描述同步 ============

UPDATE ontology_vocabularies SET
    description='BrainRegion anatomical granularity — canonical multi-scale: macro -> meso -> subregion -> cyto -> molecular (legacy whole_brain/clinical/research/fine/ultra_fine kept as compat levels; see granularity_level_compat_map)'
WHERE code='brain_region_anatomical' AND vocab_type='granularity_domain';
