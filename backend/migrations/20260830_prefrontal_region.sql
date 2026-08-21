-- 20260830_prefrontal_region.sql
-- 前额叶 canonical 脑区 + 别名 + 亚区层级（Phase Q1.5 实体解析收尾）
--
-- 背景: Q1.5 规格示例要求「前额叶(前额叶/前额叶皮层/Prefrontal cortex/PFC)」可解析，
-- 但 canonical 库缺少该实体（仅有其子区 dlpfc/vmpfc 与 Desikan 5 区）。
-- 前额叶（Prefrontal cortex, PFC）是真实解剖结构，本迁移补足该实体——
-- 不是虚构脑区；子区挂 part_of 层级后可支持「前额叶有哪些亚区 / 有什么功能」。
--
-- 幂等: 全部 ON CONFLICT DO NOTHING，可重复执行。

-- 1) 前额叶实体（clinical 粒度，与 Desikan 家族一致）
INSERT INTO canonical_brain_regions (
    region_code, canonical_name_en, canonical_name_cn, species,
    granularity_domain, granularity_level, hemisphere_policy,
    status, confidence, source_summary, created_by
)
VALUES (
    'ng:br:prefrontal_cortex', 'Prefrontal cortex', '前额叶', 'human',
    'brain_region_anatomical', 'clinical', 'bilateral',
    'active', 0.95, '{"source": "q15_manual", "note": "真实解剖结构 PFC，Q1.5 规格示例所需"}'::jsonb,
    'q15_manual'
)
ON CONFLICT (region_code) DO NOTHING;

-- 2) 别名（cn/en/abbr）
INSERT INTO canonical_region_aliases (region_id, alias, alias_language, source, confidence)
SELECT r.id, v.alias, v.lang, 'manual_curated', v.confidence
FROM canonical_brain_regions r
JOIN (
    VALUES
        ('ng:br:prefrontal_cortex', '前额叶',          'cn',   0.95),
        ('ng:br:prefrontal_cortex', '前额叶皮层',      'cn',   0.95),
        ('ng:br:prefrontal_cortex', 'Prefrontal cortex', 'en', 0.95),
        ('ng:br:prefrontal_cortex', 'PFC',             'abbr', 0.85)
) AS v(region_code, alias, lang, confidence) ON v.region_code = r.region_code
ON CONFLICT (region_id, alias) DO NOTHING;

-- 3) 亚区层级（7 区 part_of 前额叶；多父边允许——UNIQUE(child, predicate, parent)）
INSERT INTO canonical_region_hierarchy (child_region_id, parent_region_id, predicate, status, source, confidence, provenance_json, created_by)
SELECT child.id, parent.id, 'part_of', 'active', 'q15_manual', 0.95,
       '{"source": "q15_manual", "note": "Desikan 5 区 + meso dlpfc/vmpfc 均为前额叶亚区"}'::jsonb,
       'q15_manual'
FROM canonical_brain_regions child
JOIN canonical_brain_regions parent ON parent.region_code = 'ng:br:prefrontal_cortex'
WHERE child.region_code IN (
    'ng:br:superior_frontal',
    'ng:br:rostral_middle_frontal',
    'ng:br:caudal_middle_frontal',
    'ng:br:lateral_orbitofrontal',
    'ng:br:medial_orbitofrontal',
    'ng:br:dlpfc',
    'ng:br:vmpfc'
)
ON CONFLICT (child_region_id, predicate, parent_region_id) DO NOTHING;
