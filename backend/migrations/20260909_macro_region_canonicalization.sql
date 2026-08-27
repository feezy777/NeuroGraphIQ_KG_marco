-- 20260909_macro_region_canonicalization.sql
-- Macro96 Region Hierarchy Alignment 收口:正式纳入 BrainRegion ontology
--
-- 将已验证的 Macro96 池细分概念(part_of_candidate, macro_region_hierarchy_candidates
-- 6 条, confidence=0.9)正式纳入 canonical ontology,为 A1 symmetry candidate
-- 提供 canonical region anchor:
--   cerebellum exterior     -> 新 canonical 实体 -> part_of -> Cerebellum
--   cerebellum white matter -> 新 canonical 实体 -> part_of -> Cerebellum
--   ventral diencephalon    -> 新 canonical 实体 -> part_of -> Diencephalon
--
-- 原则(用户指定):
--   * 不简单 merge 到 parent —— 保持 child canonical region ↓ part_of ↓ parent
--   * 保留 provenance / evidence_source / confidence
--   * 不删除 macro_region_hierarchy_candidates 记录(候选层留存)
--   * 更新 resolver:canonical_region_aliases 加 9 行(6 带侧别 + 3 概念名,
--     source='manual_curated' 满足 CHECK 枚举),resolve_region_by_name 据此解析
--
-- 幂等锚:
--   * canonical_brain_regions      UNIQUE(region_code)
--   * canonical_region_hierarchy   UNIQUE(child_region_id, predicate, parent_region_id)
--   * canonical_region_aliases     UNIQUE(region_id, alias)
-- 全部 ON CONFLICT DO NOTHING —— 重跑零覆盖、零新增。
--
-- 本迁移不触碰:final_canonical_connections / mirror_region_connections /
-- canonical_connections / macro_connection_candidates 既有行。

-- --------------------------------------------------------------------------- #
-- 1. 三个 canonical region anchor(确定性 UUID,region_code 幂等)
--    granularity_level='clinical' 跟随 Macro96 池先例(Amygdala / Cerebellar
--    vermal lobules i-v 均 clinical, br2_seed);hemisphere_policy='lateralized'
--    因 left/right 成对池概念;laterality='bilateral' 合并表示。
-- --------------------------------------------------------------------------- #
INSERT INTO canonical_brain_regions (
    id, region_code, canonical_name_en, canonical_name_cn, species,
    granularity_domain, granularity_level, hemisphere_policy, status,
    description, confidence, source_summary, external_mappings, created_by,
    laterality
) VALUES
(
    '7b15ade5-deb0-5431-a82c-592b70e32a1b',
    'ng:br:cerebellum_exterior',
    'Cerebellum Exterior',
    '小脑外部',
    'human', 'brain_region_anatomical', 'clinical', 'lateralized', 'active',
    'L2 clinical region from the Macro96 96-pool: cerebellum exterior (cerebellar grey matter surface).',
    0.9,
    '{"macro96": {"key": "cerebellum exterior", "pool": "Macro96",
                  "laterality_values": ["left", "right"],
                  "basis": "macro_region_alignment_v1 (part_of_candidate confirmed)"}}',
    '{}', 'macro_region_alignment_v1', 'bilateral'
),
(
    'e09259a6-5984-523b-98d3-007bb6cadac4',
    'ng:br:cerebellum_white_matter',
    'Cerebellum White Matter',
    '小脑白质',
    'human', 'brain_region_anatomical', 'clinical', 'lateralized', 'active',
    'L2 clinical region from the Macro96 96-pool: cerebellum white matter.',
    0.9,
    '{"macro96": {"key": "cerebellum white matter", "pool": "Macro96",
                  "laterality_values": ["left", "right"],
                  "basis": "macro_region_alignment_v1 (part_of_candidate confirmed)"}}',
    '{}', 'macro_region_alignment_v1', 'bilateral'
),
(
    'b70bad97-5c72-513e-821d-f86ad94269ec',
    'ng:br:ventral_diencephalon',
    'Ventral Diencephalon',
    '腹侧间脑',
    'human', 'brain_region_anatomical', 'clinical', 'lateralized', 'active',
    'L2 clinical region from the Macro96 96-pool: ventral diencephalon (FreeSurfer subdivision of diencephalon).',
    0.9,
    '{"macro96": {"key": "ventral diencephalon", "pool": "Macro96",
                  "laterality_values": ["left", "right"],
                  "basis": "macro_region_alignment_v1 (part_of_candidate confirmed)"}}',
    '{}', 'macro_region_alignment_v1', 'bilateral'
)
ON CONFLICT (region_code) DO NOTHING;

-- --------------------------------------------------------------------------- #
-- 2. 三条正式 part_of 边(child canonical ↓ part_of ↓ parent canonical)
--    predicate CHECK 限 'part_of';UNIQUE(child,predicate,parent) 幂等。
--    provenance 保留候选链(candidate rows / confidence / 先例)。
-- --------------------------------------------------------------------------- #
INSERT INTO canonical_region_hierarchy (
    id, child_region_id, parent_region_id, predicate, status, source,
    confidence, provenance_json, created_by
) VALUES
(
    '78147073-0484-5fe9-a66d-849a44829fcf',
    '7b15ade5-deb0-5431-a82c-592b70e32a1b',
    '1a364407-028e-4116-a5b9-f03a2ae6865e',  -- Cerebellum
    'part_of', 'active', 'macro_region_alignment_v1', 0.9,
    '{"rule": "anatomical_part_of",
      "basis": ["macro96_pool_anatomy", "candidate_layer_alignment"],
      "candidate_rows": ["left cerebellum exterior (candidate)",
                         "right cerebellum exterior (candidate)"],
      "candidate_source": "macro_region_hierarchy_candidates (relation_type=part_of_candidate, confidence=0.9)",
      "precedent": "Cerebellar vermal lobules -> Cerebellum (macro96_pool_mapping)",
      "generation_method": "macro_region_alignment_v1"}',
    'macro_region_alignment_v1'
),
(
    'c1cce2b4-3626-56f3-a7d6-1f1516ad44d1',
    'e09259a6-5984-523b-98d3-007bb6cadac4',
    '1a364407-028e-4116-a5b9-f03a2ae6865e',  -- Cerebellum
    'part_of', 'active', 'macro_region_alignment_v1', 0.9,
    '{"rule": "anatomical_part_of",
      "basis": ["macro96_pool_anatomy", "candidate_layer_alignment"],
      "candidate_rows": ["left cerebellum white matter (candidate)",
                         "right cerebellum white matter (candidate)"],
      "candidate_source": "macro_region_hierarchy_candidates (relation_type=part_of_candidate, confidence=0.9)",
      "precedent": "Cerebellar vermal lobules -> Cerebellum (macro96_pool_mapping)",
      "generation_method": "macro_region_alignment_v1"}',
    'macro_region_alignment_v1'
),
(
    '9fc283b5-b6eb-5df2-94ce-0efe82a1d256',
    'b70bad97-5c72-513e-821d-f86ad94269ec',
    '613edf8f-6577-47e8-ad5d-a591ed616a74',  -- Diencephalon
    'part_of', 'active', 'macro_region_alignment_v1', 0.9,
    '{"rule": "anatomical_part_of",
      "basis": ["macro96_pool_anatomy", "candidate_layer_alignment"],
      "candidate_rows": ["left ventral diencephalon (candidate)",
                         "right ventral diencephalon (candidate)"],
      "candidate_source": "macro_region_hierarchy_candidates (relation_type=part_of_candidate, confidence=0.9)",
      "precedent": "Thalamus proper -> Diencephalon (macro96_pool_mapping)",
      "generation_method": "macro_region_alignment_v1"}',
    'macro_region_alignment_v1'
)
ON CONFLICT (child_region_id, predicate, parent_region_id) DO NOTHING;

-- --------------------------------------------------------------------------- #
-- 3. Resolver 更新:9 个别名(6 带侧别 + 3 概念名) -> 新 canonical region。
--    source='manual_curated'(CHECK 枚举内):本阶段人工 review 确认。
--    resolve_region_by_name 索引 canonical_region_aliases(alias casefold),
--    left/right 前缀名称从此可解析到新 canonical id。
-- --------------------------------------------------------------------------- #
INSERT INTO canonical_region_aliases (id, region_id, alias, alias_language, source, confidence) VALUES
    (gen_random_uuid(), '7b15ade5-deb0-5431-a82c-592b70e32a1b', 'left cerebellum exterior',  'en', 'manual_curated', 0.9),
    (gen_random_uuid(), '7b15ade5-deb0-5431-a82c-592b70e32a1b', 'right cerebellum exterior', 'en', 'manual_curated', 0.9),
    (gen_random_uuid(), '7b15ade5-deb0-5431-a82c-592b70e32a1b', 'cerebellum exterior',       'en', 'manual_curated', 0.9),
    (gen_random_uuid(), 'e09259a6-5984-523b-98d3-007bb6cadac4', 'left cerebellum white matter',  'en', 'manual_curated', 0.9),
    (gen_random_uuid(), 'e09259a6-5984-523b-98d3-007bb6cadac4', 'right cerebellum white matter', 'en', 'manual_curated', 0.9),
    (gen_random_uuid(), 'e09259a6-5984-523b-98d3-007bb6cadac4', 'cerebellum white matter',       'en', 'manual_curated', 0.9),
    (gen_random_uuid(), 'b70bad97-5c72-513e-821d-f86ad94269ec', 'left ventral diencephalon',  'en', 'manual_curated', 0.9),
    (gen_random_uuid(), 'b70bad97-5c72-513e-821d-f86ad94269ec', 'right ventral diencephalon', 'en', 'manual_curated', 0.9),
    (gen_random_uuid(), 'b70bad97-5c72-513e-821d-f86ad94269ec', 'ventral diencephalon',       'en', 'manual_curated', 0.9)
ON CONFLICT (region_id, alias) DO NOTHING;

-- --------------------------------------------------------------------------- #
-- 4. macro_connection_candidates 增加解析回填列(不触碰幂等锚列
--    source_region_id/target_region_id —— 原列保持 NULL 语义,
--    新列记录 canonical 解析结果,由 finalize 脚本回填)。
-- --------------------------------------------------------------------------- #
ALTER TABLE macro_connection_candidates
    ADD COLUMN IF NOT EXISTS resolved_source_region_id UUID REFERENCES canonical_brain_regions(id),
    ADD COLUMN IF NOT EXISTS resolved_target_region_id UUID REFERENCES canonical_brain_regions(id);
