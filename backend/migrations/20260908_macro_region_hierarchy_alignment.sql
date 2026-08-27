-- 20260908_macro_region_hierarchy_alignment.sql
-- Macro96 Region Hierarchy Alignment V1
--
-- macro_region_hierarchy_candidates 表:细粒度区域(Macro96 池细分概念)归属宏观
-- 脑区的 part_of 候选。解决 coverage 补缺中发现的粒度映射问题:
--   cerebellum exterior / cerebellum white matter -> Cerebellum
--   ventral diencephalon                          -> Diencephalon
--
-- 治理定位(硬边界):
--   * assertion_type = 'candidate' —— 不是正式 part_of 边,不写入
--     canonical_region_hierarchy
--   * generation_method = 'macro_region_alignment_v1' —— 基于 candidate 层
--     alignment + 解剖学先验,禁止 LLM / 外部数据库
--   * child 是 candidate_brain_regions 行(candidate 层),parent 是 canonical
--     宏观概念 —— 经人工确认后才落正式 hierarchy 边
--
-- 幂等锚:UNIQUE NULLS NOT DISTINCT(child_region_id, parent_region_id,
--                 relation_type) —— 同一 (child, parent, 关系) 只建一次。

DROP TABLE IF EXISTS macro_region_hierarchy_candidates;

CREATE TABLE macro_region_hierarchy_candidates (
    id              UUID PRIMARY KEY,
    child_region_id UUID REFERENCES candidate_brain_regions(id),
    child_region_name TEXT,
    parent_region_id UUID REFERENCES canonical_brain_regions(id),
    parent_region_name TEXT,
    relation_type   TEXT NOT NULL DEFAULT 'part_of_candidate',
    evidence_source TEXT,
    confidence      NUMERIC,
    provenance_json JSONB NOT NULL DEFAULT '{}',
    generation_method TEXT NOT NULL DEFAULT 'macro_region_alignment_v1',
    assertion_type  TEXT NOT NULL DEFAULT 'candidate',
    status          TEXT NOT NULL DEFAULT 'candidate',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_region_hierarchy_candidate UNIQUE NULLS NOT DISTINCT
        (child_region_id, parent_region_id, relation_type)
);

CREATE INDEX IF NOT EXISTS ix_region_hc_child
    ON macro_region_hierarchy_candidates (child_region_id);
CREATE INDEX IF NOT EXISTS ix_region_hc_parent
    ON macro_region_hierarchy_candidates (parent_region_id);
