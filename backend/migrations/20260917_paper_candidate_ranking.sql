-- Macro Candidate Connection Ranking V1
-- 论文驱动候选连接的优先级排序(仅排序,不审核不晋升)。
--
-- 设计(用户要求):
-- * 不创建新 canonical connection / 不修改 final_canonical_connections /
--   不进入 validation/review/promotion —— 只生成 candidate ranking 数据
-- * 输入 paper_region_pair_candidates(17,609 行),按 (source,target) 聚合:
--   paper_count(不同论文数) + evidence_count(证据句数) + 五因素评分
-- * 每一条 ranking 可追溯:
--   ranking → candidate_pair(paper_region_pair_candidates.id) →
--   evidence_segment(paper_region_evidence_segments) → paper_source
-- * 幂等:UNIQUE(source_region_id, target_region_id) +
--   INSERT ON CONFLICT DO NOTHING → 复跑 0 新增
-- * 所有 COMMENT 单行字符串(PostgreSQL 不支持跨行相邻字符串字面量),
--   注释内全角冒号(防 SQLAlchemy text() bind 解析)。

-- paper_connection_candidate_rankings —— 论文驱动候选连接排名
CREATE TABLE IF NOT EXISTS paper_connection_candidate_rankings (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source_region_id uuid NOT NULL REFERENCES canonical_brain_regions(id) ON DELETE CASCADE,
    target_region_id uuid NOT NULL REFERENCES canonical_brain_regions(id) ON DELETE CASCADE,
    candidate_pair_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
        -- 支持该 pair 的 paper_region_pair_candidates.id 列表(全量可追溯)
    paper_count integer NOT NULL,
        -- 支持该 pair 的不同论文数
    evidence_count integer NOT NULL,
        -- 证据句总数(候选行数,含 title 源)
    score numeric(10, 4) NOT NULL,
        -- paper_support(指数+饱和) × evidence_source(1.0/0.8/0.5) ×
        -- proximity(1.0/0.7/0.4) × (1 + 关键词加成)
    priority_level varchar(8) NOT NULL
        CHECK (priority_level IN ('A', 'B', 'C')),
        -- A: 多篇论文 + same_sentence 证据 + 连接关键词
        -- B: 中等(非 A 非 C)
        -- C: 单论文低价值共现
    ranking_reason jsonb NOT NULL DEFAULT '{}'::jsonb,
        -- {paper_support_score, evidence_source_score, proximity_score,
        --  keyword_hits, paper_list, segment_examples}
    provenance_json jsonb NOT NULL DEFAULT '{}'::jsonb,
        -- {source_table: 'paper_region_pair_candidates',
        --  paper_entries: [{paper_id, pmid, candidate_pair_id,
        --                   evidence_segment_id, source_type, cooccurrence}],
        --  trace_chain: ['ranking','candidate_pair',
        --                'evidence_segment','paper_source']}
    assertion_type varchar(16) NOT NULL DEFAULT 'candidate'
        CHECK (assertion_type = 'candidate'),
    source_type varchar(16) NOT NULL DEFAULT 'literature'
        CHECK (source_type = 'literature'),
    generation_method varchar(64) NOT NULL
        DEFAULT 'paper_candidate_ranking_v1'
        CHECK (generation_method = 'paper_candidate_ranking_v1'),
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_candidate_ranking_pair
        UNIQUE (source_region_id, target_region_id),
    CONSTRAINT chk_candidate_ranking_not_self
        CHECK (source_region_id <> target_region_id)
);

CREATE INDEX IF NOT EXISTS ix_candidate_ranking_level
    ON paper_connection_candidate_rankings (priority_level);
CREATE INDEX IF NOT EXISTS ix_candidate_ranking_score
    ON paper_connection_candidate_rankings (score DESC);

COMMENT ON TABLE paper_connection_candidate_rankings IS
    '论文驱动候选连接排名：candidate 层(仅排序)，五因素评分 + A/B/C 分级，全量可追溯 candidate_pair→evidence_segment→paper_source';
COMMENT ON COLUMN paper_connection_candidate_rankings.score IS
    '综合评分：paper_support_score(2^(paper_count-1) 指数,≥6 篇饱和 32) × evidence_source_score(fulltext 1.0 / abstract 0.8 / title 0.5 取最强) × proximity_score(same_sentence 1.0 / same_section 0.7 / same_paper 0.4 取最强) × (1 + 0.1×min(关键词命中数,5))';
COMMENT ON COLUMN paper_connection_candidate_rankings.priority_level IS
    '优先级：A=高价值候选(多篇论文 + same_sentence 证据 + 连接关键词)；B=中等；C=低价值共现(单论文且无 same_sentence 无关键词)';
COMMENT ON COLUMN paper_connection_candidate_rankings.provenance_json IS
    '溯源：paper_entries 逐篇记录 candidate_pair_id + evidence_segment_id + paper_id + pmid + source_type + cooccurrence';
