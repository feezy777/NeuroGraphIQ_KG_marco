-- Macro Candidate Connection Ranking V1
-- 论文驱动候选连接优先级排序(第二阶段,在 paper_region_pair_candidates 之上的
-- 纯分析读数层,不创建连接不写 final)。
--
-- 设计(用户要求):
-- * 不创建新 canonical connection / 不修改 final_canonical_connections /
--   不进入 validation/review/promotion —— 只生成 candidate ranking 数据
-- * 输入:paper_region_pair_candidates(17609 行,paper×pair 粒度)
-- * 关联:paper_region_evidence_segments + paper_sources
-- * 每条 ranking 可追溯:ranking → candidate_pair → evidence_segment → paper_source
-- * generation_method='paper_candidate_ranking_v1'
--   assertion_type='candidate'(规范词表:reported_fact/inferred/hypothesis/candidate)
--   source_type='literature'(7 值词表之一)
-- * 幂等:行级 UNIQUE(source,target) + generation_method 分区替换运行
--   (每次运行 DELETE 本方法旧行 → 全量重算 INSERT,相同输入结果一致)
--
-- 一、ranking 数据表。
CREATE TABLE IF NOT EXISTS paper_connection_candidate_rankings (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source_region_id uuid NOT NULL REFERENCES canonical_brain_regions(id) ON DELETE CASCADE,
    target_region_id uuid NOT NULL REFERENCES canonical_brain_regions(id) ON DELETE CASCADE,
    candidate_pair_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
        -- 支持该 pair 的 paper_region_pair_candidates.id 列表(论文级,可追溯)
    paper_count integer NOT NULL,
    evidence_count integer NOT NULL,
    score numeric(10, 4) NOT NULL,
    priority_level varchar(1) NOT NULL
        CHECK (priority_level IN ('A', 'B', 'C')),
    ranking_reason jsonb NOT NULL DEFAULT '{}'::jsonb,
        -- 评分成分 + 公式 + 分级规则 + 来源解析方法(可审计)
    provenance_json jsonb NOT NULL DEFAULT '{}'::jsonb,
        -- candidate_pair_ids + papers(paper_id/pmid) + 算法版本(可追溯)
    assertion_type varchar(16) NOT NULL DEFAULT 'candidate'
        CHECK (assertion_type = 'candidate'),
    source_type varchar(16) NOT NULL DEFAULT 'literature'
        CHECK (source_type = 'literature'),
    generation_method varchar(64) NOT NULL DEFAULT 'paper_candidate_ranking_v1',
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_paper_connection_ranking
        UNIQUE (source_region_id, target_region_id),
    CONSTRAINT chk_paper_connection_ranking_not_self
        CHECK (source_region_id <> target_region_id)
);

CREATE INDEX IF NOT EXISTS ix_paper_connection_ranking_source
    ON paper_connection_candidate_rankings (source_region_id);
CREATE INDEX IF NOT EXISTS ix_paper_connection_ranking_target
    ON paper_connection_candidate_rankings (target_region_id);
CREATE INDEX IF NOT EXISTS ix_paper_connection_ranking_priority_score
    ON paper_connection_candidate_rankings (priority_level, score DESC);
CREATE INDEX IF NOT EXISTS ix_paper_connection_ranking_generation
    ON paper_connection_candidate_rankings (generation_method, priority_level);

COMMENT ON TABLE paper_connection_candidate_rankings IS
    '论文驱动候选连接优先级排序:region pair 粒度聚合评分(A/B/C),'
    'generation_method=paper_candidate_ranking_v1,assertion_type=candidate;'
    'ranking→candidate_pair(paper_region_pair_candidates)→evidence_segment→paper_source 可追溯';
COMMENT ON COLUMN paper_connection_candidate_rankings.candidate_pair_ids IS
    '支持该 region pair 的 paper_region_pair_candidates.id 列表(→paper_id→paper_sources)';
COMMENT ON COLUMN paper_connection_candidate_rankings.ranking_reason IS
    '评分成分(paper_support_score/evidence_source_score/keyword_support_score)'
    '+来源权重分级规则+来源解析方法,供人工审计';
