-- 20260829_canonical_region_aliases.sql (idempotent)
-- Phase Q1.5: canonical 脑区别名表 — 让 NL 查询不再只依赖 canonical_name_cn 精确匹配。
--
-- 设计原则（对齐用户规格）:
--   * 别名只挂在已有 canonical_brain_regions 上（FK CASCADE），绝不新增虚假脑区；
--   * 手工 seed 仅覆盖 macro + clinical 粒度（52 区），每个脑区提供
--     常见中文表达 / 医学英文表达 / 缩写；禁止自动生成；
--   * atlas 名称从已有 atlas_region_resources + atlas_region_mappings 映射生成
--     （alias=atlas 原生名称/缩写, source='atlas'），不复制实体只加别名；
--     仅 same_species 映射入表 —— 跨物种 homology 名称未经人工确认不进查找别名；
--   * 解析优先级（服务层实现）:
--     1 canonical_name_cn → 2 canonical_name_en → 3 canonical_region_aliases
--     → 4 atlas 名（实时 join）→ 5 ontology synonym → 6 模糊候选 → 7 unresolved。
--   * 本迁移只建表 + 静态数据；运行时解析见 ontology_query_service.py。

-- ============ 1. 建表 ============

CREATE TABLE IF NOT EXISTS canonical_region_aliases (
    id             UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    region_id      UUID NOT NULL REFERENCES canonical_brain_regions(id) ON DELETE CASCADE,
    alias          TEXT NOT NULL,                    -- 查找文本（规范化后比较）
    alias_language VARCHAR(16) NOT NULL,             -- cn / en / abbr
    source         VARCHAR(32) NOT NULL DEFAULT 'manual_curated',
                                                     -- manual_curated / atlas / ontology_synonym
    confidence     DOUBLE PRECISION,                 -- 0..1，别名可信度
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_canonical_region_aliases UNIQUE (region_id, alias),
    CONSTRAINT chk_canonical_region_aliases_lang CHECK (alias_language IN ('cn', 'en', 'abbr')),
    CONSTRAINT chk_canonical_region_aliases_source CHECK (
        source IN ('manual_curated', 'atlas', 'ontology_synonym')
    ),
    CONSTRAINT chk_canonical_region_aliases_conf CHECK (
        confidence IS NULL OR (confidence >= 0 AND confidence <= 1)
    )
);

CREATE INDEX IF NOT EXISTS idx_canonical_region_aliases_alias
    ON canonical_region_aliases (alias);
CREATE INDEX IF NOT EXISTS idx_canonical_region_aliases_region
    ON canonical_region_aliases (region_id);

-- ============ 2. 手工 seed：macro + clinical（52 区，禁止自动生成） ============
-- 每区提供 常见中文表达(0.95) / 医学英文表达(0.95) / 缩写(0.85)。
-- region_code 不存在时该行自然跳过（INSERT...SELECT），保证幂等与跨环境安全。

INSERT INTO canonical_region_aliases (region_id, alias, alias_language, source, confidence)
SELECT r.id, v.alias, v.alias_language, 'manual_curated', v.confidence
FROM canonical_brain_regions r
JOIN (VALUES
    -- ── clinical 层（Desikan/subcortical + 脑室 + 白质）──
    ('ng:br:3rd_ventricle',                  '三脑室',                     'cn',   0.95),
    ('ng:br:3rd_ventricle',                  'third ventricle',            'en',   0.95),
    ('ng:br:3rd_ventricle',                  '3V',                         'abbr', 0.85),
    ('ng:br:4th_ventricle',                  '四脑室',                     'cn',   0.95),
    ('ng:br:4th_ventricle',                  'fourth ventricle',           'en',   0.95),
    ('ng:br:4th_ventricle',                  '4V',                         'abbr', 0.85),
    ('ng:br:accumbens_area',                 '伏隔核',                     'cn',   0.95),
    ('ng:br:accumbens_area',                 'nucleus accumbens',          'en',   0.95),
    ('ng:br:accumbens_area',                 'NAc',                        'abbr', 0.85),
    ('ng:br:amygdala',                       '杏仁体',                     'cn',   0.95),
    ('ng:br:amygdala',                       'amygdaloid body',            'en',   0.95),
    ('ng:br:amygdala',                       'Amg',                        'abbr', 0.85),
    ('ng:br:basal_forebrain',                '腹侧前脑',                   'cn',   0.95),
    ('ng:br:basal_forebrain',                'ventral forebrain',          'en',   0.95),
    ('ng:br:basal_forebrain',                'BF',                         'abbr', 0.85),
    ('ng:br:caudal_anterior_cingulate',      '尾侧前扣带回',               'cn',   0.95),
    ('ng:br:caudal_anterior_cingulate',      'caudal anterior cingulate cortex', 'en', 0.95),
    ('ng:br:caudal_anterior_cingulate',      'cACC',                       'abbr', 0.85),
    ('ng:br:caudal_middle_frontal',          '尾侧额中回',                 'cn',   0.95),
    ('ng:br:caudal_middle_frontal',          'caudal middle frontal gyrus','en',   0.95),
    ('ng:br:caudal_middle_frontal',          'CMF',                        'abbr', 0.85),
    ('ng:br:caudate',                        'CN',                         'abbr', 0.85),
    ('ng:br:caudate',                        'Cd',                         'abbr', 0.85),
    ('ng:br:cerebellar_vermal_lobules_i_v',  '小脑蚓部小叶I-V',            'cn',   0.95),
    ('ng:br:cerebellar_vermal_lobules_i_v',  'vermis lobules I-V',         'en',   0.95),
    ('ng:br:cerebellar_vermal_lobules_i_v',  'Vermis I-V',                 'abbr', 0.85),
    ('ng:br:cerebellar_vermal_lobules_vi_vii', '小脑蚓部小叶VI-VII',       'cn',   0.95),
    ('ng:br:cerebellar_vermal_lobules_vi_vii', 'vermis lobules VI-VII',    'en',   0.95),
    ('ng:br:cerebellar_vermal_lobules_vi_vii', 'Vermis VI-VII',            'abbr', 0.85),
    ('ng:br:cerebellar_vermal_lobules_viii_x', '小脑蚓部小叶VIII-X',       'cn',   0.95),
    ('ng:br:cerebellar_vermal_lobules_viii_x', 'vermis lobules VIII-X',    'en',   0.95),
    ('ng:br:cerebellar_vermal_lobules_viii_x', 'Vermis VIII-X',            'abbr', 0.85),
    ('ng:br:csf',                            '脑脊液腔',                   'cn',   0.95),
    ('ng:br:csf',                            'cerebrospinal fluid',        'en',   0.95),
    ('ng:br:cuneus',                         '楔叶',                       'cn',   0.95),
    ('ng:br:cuneus',                         'CUN',                        'abbr', 0.85),
    ('ng:br:cuneus',                         'Cu',                         'abbr', 0.85),
    ('ng:br:entorhinal',                     '内嗅皮层',                   'cn',   0.95),
    ('ng:br:entorhinal',                     'entorhinal cortex',          'en',   0.95),
    ('ng:br:entorhinal',                     'EC',                         'abbr', 0.85),
    ('ng:br:entorhinal',                     'Ent',                        'abbr', 0.85),
    ('ng:br:fusiform',                       '梭状回',                     'cn',   0.95),
    ('ng:br:fusiform',                       'fusiform gyrus',             'en',   0.95),
    ('ng:br:fusiform',                       'FuG',                        'abbr', 0.85),
    ('ng:br:fusiform',                       'FG',                         'abbr', 0.85),
    ('ng:br:hippocampus',                    '海马体',                     'cn',   0.95),
    ('ng:br:hippocampus',                    '海马结构',                   'cn',   0.95),
    ('ng:br:hippocampus',                    'hippocampal formation',      'en',   0.95),
    ('ng:br:hippocampus',                    'HF',                         'abbr', 0.85),
    ('ng:br:hippocampus',                    'HPF',                        'abbr', 0.85),
    ('ng:br:hippocampus',                    'Hipp',                       'abbr', 0.85),
    ('ng:br:inferior_lateral_ventricle',     '侧脑室下角',                 'cn',   0.95),
    ('ng:br:inferior_lateral_ventricle',     'inferior horn of lateral ventricle', 'en', 0.95),
    ('ng:br:inferior_lateral_ventricle',     'ILV',                        'abbr', 0.85),
    ('ng:br:inferior_parietal',              '下顶小叶',                   'cn',   0.95),
    ('ng:br:inferior_parietal',              'inferior parietal lobule',   'en',   0.95),
    ('ng:br:inferior_parietal',              'IPL',                        'abbr', 0.85),
    ('ng:br:inferior_temporal',              '颞下回',                     'cn',   0.95),
    ('ng:br:inferior_temporal',              'inferior temporal gyrus',    'en',   0.95),
    ('ng:br:inferior_temporal',              'ITG',                        'abbr', 0.85),
    ('ng:br:inferior_temporal',              'IT',                         'abbr', 0.85),
    ('ng:br:insula',                         '岛叶',                       'cn',   0.95),
    ('ng:br:insula',                         'insular cortex',             'en',   0.95),
    ('ng:br:insula',                         'Ins',                        'abbr', 0.85),
    ('ng:br:isthmus_cingulate',              '扣带回峡',                   'cn',   0.95),
    ('ng:br:isthmus_cingulate',              'isthmus of cingulate gyrus', 'en',   0.95),
    ('ng:br:isthmus_cingulate',              'IST',                        'abbr', 0.85),
    ('ng:br:lateral_occipital',              '枕外侧回',                   'cn',   0.95),
    ('ng:br:lateral_occipital',              'lateral occipital cortex',   'en',   0.95),
    ('ng:br:lateral_occipital',              'LOC',                        'abbr', 0.85),
    ('ng:br:lateral_orbitofrontal',          '外侧眶额皮层',               'cn',   0.95),
    ('ng:br:lateral_orbitofrontal',          'lateral orbitofrontal cortex','en',  0.95),
    ('ng:br:lateral_orbitofrontal',          'lOFC',                       'abbr', 0.85),
    ('ng:br:lateral_orbitofrontal',          'LOFC',                       'abbr', 0.85),
    ('ng:br:lateral_ventricle',              'LV',                         'abbr', 0.85),
    ('ng:br:lingual_gyrus',                  '舌状回',                     'cn',   0.95),
    ('ng:br:lingual_gyrus',                  'LG',                         'abbr', 0.85),
    ('ng:br:lingual_gyrus',                  'Ling',                       'abbr', 0.85),
    ('ng:br:medial_orbitofrontal',           '内侧眶额皮层',               'cn',   0.95),
    ('ng:br:medial_orbitofrontal',           'medial orbitofrontal cortex','en',   0.95),
    ('ng:br:medial_orbitofrontal',           'mOFC',                       'abbr', 0.85),
    ('ng:br:medial_orbitofrontal',           'MOFC',                       'abbr', 0.85),
    ('ng:br:middle_temporal',                '颞中回',                     'cn',   0.95),
    ('ng:br:middle_temporal',                'middle temporal gyrus',      'en',   0.95),
    ('ng:br:middle_temporal',                'MTG',                        'abbr', 0.85),
    ('ng:br:middle_temporal',                'MT',                         'abbr', 0.85),
    ('ng:br:pallidum',                       'globus pallidus',            'en',   0.95),
    ('ng:br:pallidum',                       'GP',                         'abbr', 0.85),
    ('ng:br:pallidum',                       'Pal',                        'abbr', 0.85),
    ('ng:br:paracentral',                    '旁中央小叶',                 'cn',   0.95),
    ('ng:br:paracentral',                    'paracentral lobule',         'en',   0.95),
    ('ng:br:paracentral',                    'PCL',                        'abbr', 0.85),
    ('ng:br:parahippocampal',                '海马旁回',                   'cn',   0.95),
    ('ng:br:parahippocampal',                'parahippocampal gyrus',      'en',   0.95),
    ('ng:br:parahippocampal',                'PHG',                        'abbr', 0.85),
    ('ng:br:pars_opercularis',               '额下回岛盖部',               'cn',   0.95),
    ('ng:br:pars_opercularis',               'opercular part of inferior frontal gyrus', 'en', 0.95),
    ('ng:br:pars_opercularis',               'pOp',                        'abbr', 0.85),
    ('ng:br:pars_orbitalis',                 '额下回眶部',                 'cn',   0.95),
    ('ng:br:pars_orbitalis',                 'orbital part of inferior frontal gyrus', 'en', 0.95),
    ('ng:br:pars_orbitalis',                 'pOrb',                       'abbr', 0.85),
    ('ng:br:pars_triangularis',              '额下回三角部',               'cn',   0.95),
    ('ng:br:pars_triangularis',              'triangular part of inferior frontal gyrus', 'en', 0.95),
    ('ng:br:pars_triangularis',              'pTr',                        'abbr', 0.85),
    ('ng:br:pericalcarine',                  '距状沟周围皮层',             'cn',   0.95),
    ('ng:br:pericalcarine',                  'pericalcarine cortex',       'en',   0.95),
    ('ng:br:pericalcarine',                  'PCAL',                       'abbr', 0.85),
    ('ng:br:pericalcarine',                  'Calc',                       'abbr', 0.85),
    ('ng:br:postcentral',                    '中央后回',                   'cn',   0.95),
    ('ng:br:postcentral',                    'postcentral gyrus',          'en',   0.95),
    ('ng:br:postcentral',                    'PoCG',                       'abbr', 0.85),
    ('ng:br:posterior_cingulate',            '后扣带回',                   'cn',   0.95),
    ('ng:br:posterior_cingulate',            'posterior cingulate cortex', 'en',   0.95),
    ('ng:br:posterior_cingulate',            'PCC',                        'abbr', 0.85),
    ('ng:br:precentral',                     '中央前回',                   'cn',   0.95),
    ('ng:br:precentral',                     'precentral gyrus',           'en',   0.95),
    ('ng:br:precentral',                     'PrCG',                       'abbr', 0.85),
    ('ng:br:precentral',                     'M1',                         'abbr', 0.85),
    ('ng:br:precuneus',                      'PCun',                       'abbr', 0.85),
    ('ng:br:precuneus',                      'PCU',                        'abbr', 0.85),
    ('ng:br:putamen',                        'Put',                        'abbr', 0.85),
    ('ng:br:rostral_anterior_cingulate',     '喙侧前扣带回',               'cn',   0.95),
    ('ng:br:rostral_anterior_cingulate',     'rostral anterior cingulate cortex', 'en', 0.95),
    ('ng:br:rostral_anterior_cingulate',     'rACC',                       'abbr', 0.85),
    ('ng:br:rostral_middle_frontal',         '喙侧额中回',                 'cn',   0.95),
    ('ng:br:rostral_middle_frontal',         'rostral middle frontal gyrus','en',  0.95),
    ('ng:br:rostral_middle_frontal',         'RMF',                        'abbr', 0.85),
    ('ng:br:superior_frontal',               '额上回',                     'cn',   0.95),
    ('ng:br:superior_frontal',               'superior frontal gyrus',     'en',   0.95),
    ('ng:br:superior_frontal',               'SFG',                        'abbr', 0.85),
    ('ng:br:superior_frontal',               'SF',                         'abbr', 0.85),
    ('ng:br:superior_parietal',              '上顶小叶',                   'cn',   0.95),
    ('ng:br:superior_parietal',              'superior parietal lobule',   'en',   0.95),
    ('ng:br:superior_parietal',              'SPL',                        'abbr', 0.85),
    ('ng:br:superior_temporal',              '颞上回',                     'cn',   0.95),
    ('ng:br:superior_temporal',              'superior temporal gyrus',    'en',   0.95),
    ('ng:br:superior_temporal',              'STG',                        'abbr', 0.85),
    ('ng:br:superior_temporal',              'ST',                         'abbr', 0.85),
    ('ng:br:supramarginal',                  '缘上回',                     'cn',   0.95),
    ('ng:br:supramarginal',                  'supramarginal gyrus',        'en',   0.95),
    ('ng:br:supramarginal',                  'SMG',                        'abbr', 0.85),
    ('ng:br:thalamus_proper',                '丘脑',                       'cn',   0.95),
    ('ng:br:thalamus_proper',                'thalamus',                   'en',   0.95),
    ('ng:br:thalamus_proper',                'Thal',                       'abbr', 0.85),
    ('ng:br:transverse_temporal',            '颞横回',                     'cn',   0.95),
    ('ng:br:transverse_temporal',            'transverse temporal gyrus',  'en',   0.95),
    ('ng:br:transverse_temporal',            'Heschl gyrus',               'en',   0.95),
    ('ng:br:transverse_temporal',            'TTG',                        'abbr', 0.85),
    ('ng:br:transverse_temporal',            'HG',                         'abbr', 0.85),
    ('ng:br:white_matter',                   '白质',                       'cn',   0.95),
    ('ng:br:white_matter',                   'cerebral white matter',      'en',   0.95),
    ('ng:br:white_matter',                   'WM',                         'abbr', 0.85),
    -- ── macro 层 ──
    ('ng:br:brain_stem',                     'brainstem',                  'en',   0.95),
    ('ng:br:brain_stem',                     'BS',                         'abbr', 0.85),
    ('ng:br:cerebellum',                     'Cb',                         'abbr', 0.85),
    ('ng:br:cerebrum',                       '大脑半球',                   'cn',   0.95),
    ('ng:br:cerebrum',                       'cerebral hemisphere',        'en',   0.95),
    ('ng:br:cerebrum',                       'Cereb',                      'abbr', 0.85),
    ('ng:br:cerebrum',                       'CB',                         'abbr', 0.85),
    ('ng:br:diencephalon',                   'Dien',                       'abbr', 0.85)
) AS v(region_code, alias, alias_language, confidence) ON v.region_code = r.region_code
ON CONFLICT (region_id, alias) DO NOTHING;

-- ============ 3. Atlas 名称接入（从已有映射自动生成, source='atlas'） ============
-- 只取 same_species 映射（跨物种 homology 名称不自动成为查找别名）；
-- 名称与缩写分别入表；(region_id, alias) 唯一约束 + ON CONFLICT 保证幂等。

INSERT INTO canonical_region_aliases (region_id, alias, alias_language, source, confidence)
SELECT arm.canonical_region_id, ar.region_name,
       CASE WHEN ar.region_name ~ '[^\x00-\x7F]' THEN 'cn' ELSE 'en' END,
       'atlas', 0.9
FROM atlas_region_mappings arm
JOIN atlas_region_resources ar ON ar.id = arm.atlas_region_id
WHERE arm.status = 'active'
  AND ar.status = 'active'
  AND arm.species_relation = 'same_species'
  AND arm.canonical_region_id IS NOT NULL
ON CONFLICT (region_id, alias) DO NOTHING;

INSERT INTO canonical_region_aliases (region_id, alias, alias_language, source, confidence)
SELECT arm.canonical_region_id, ar.region_acronym, 'abbr', 'atlas', 0.9
FROM atlas_region_mappings arm
JOIN atlas_region_resources ar ON ar.id = arm.atlas_region_id
WHERE arm.status = 'active'
  AND ar.status = 'active'
  AND arm.species_relation = 'same_species'
  AND arm.canonical_region_id IS NOT NULL
  AND ar.region_acronym IS NOT NULL
  AND ar.region_acronym <> ar.region_name
ON CONFLICT (region_id, alias) DO NOTHING;
