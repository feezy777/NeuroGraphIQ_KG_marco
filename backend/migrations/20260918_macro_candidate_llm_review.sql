-- Macro Candidate Connection LLM Scientific Review V1
-- 论文驱动候选连接的 LLM 科学审核结果(candidate 层,不写 final)。
--
-- 设计(用户要求):
-- * 输入 paper_connection_candidate_rankings(Top 200),LLM 判断
--   supported / uncertain / not_supported,保存 prompt+response+model+token
-- * 禁止:创建 canonical connection / validation / promotion /
--   Final KG 写入 / 修改已有连接
-- * 幂等:UNIQUE(ranking_id) + INSERT ON CONFLICT DO NOTHING → 复跑跳过
-- * 所有 COMMENT 单行字符串(PostgreSQL 不支持跨行相邻字符串字面量),
--   注释内全角冒号(防 SQLAlchemy text() bind 解析)。

-- macro_candidate_connection_llm_reviews —— LLM 科学审核结果
CREATE TABLE IF NOT EXISTS macro_candidate_connection_llm_reviews (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    ranking_id uuid NOT NULL REFERENCES paper_connection_candidate_rankings(id) ON DELETE CASCADE,
    source_region_id uuid NOT NULL REFERENCES canonical_brain_regions(id) ON DELETE CASCADE,
    target_region_id uuid NOT NULL REFERENCES canonical_brain_regions(id) ON DELETE CASCADE,
    decision varchar(16) NOT NULL
        CHECK (decision IN ('supported', 'uncertain', 'not_supported')),
    connection_type varchar(32) NOT NULL
        CHECK (connection_type IN ('structural_connection',
                                   'functional_connectivity',
                                   'projection', 'association', 'unknown')),
    direction varchar(16) NOT NULL
        CHECK (direction IN ('A_to_B', 'B_to_A', 'bidirectional', 'unknown')),
    confidence numeric(4, 3) NOT NULL DEFAULT 0,   -- 0-1,LLM 置信度
    evidence_strength varchar(8) NOT NULL
        CHECK (evidence_strength IN ('high', 'medium', 'low')),
    reasoning text NOT NULL DEFAULT '',
        -- LLM 解释为什么(判断依据)
    model_name varchar(64) NOT NULL,
    prompt_version varchar(64) NOT NULL,
    raw_response_json jsonb NOT NULL DEFAULT '{}'::jsonb,
        -- {raw_text, parsed, parse_error, transport_ok, finish_reason,
        --  latency_ms, response_format}
    provenance_json jsonb NOT NULL DEFAULT '{}'::jsonb,
        -- {ranking_id, candidate_pair_ids, prompt_version,
        --  prompt: {system, user}, evidence_refs: [...],
        --  llm: {provider, model, latency_ms}, trace_chain}
    token_usage jsonb NOT NULL DEFAULT '{}'::jsonb,
        -- {prompt_tokens, completion_tokens, total_tokens}(接口提供时)
    assertion_type varchar(16) NOT NULL DEFAULT 'candidate'
        CHECK (assertion_type = 'candidate'),
    source_type varchar(16) NOT NULL DEFAULT 'llm_review'
        CHECK (source_type = 'llm_review'),
    generation_method varchar(64) NOT NULL
        DEFAULT 'macro_candidate_llm_review_v1'
        CHECK (generation_method = 'macro_candidate_llm_review_v1'),
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_llm_review_ranking UNIQUE (ranking_id)
);

CREATE INDEX IF NOT EXISTS ix_llm_review_decision
    ON macro_candidate_connection_llm_reviews (decision);
CREATE INDEX IF NOT EXISTS ix_llm_review_region
    ON macro_candidate_connection_llm_reviews (source_region_id,
                                               target_region_id);

COMMENT ON TABLE macro_candidate_connection_llm_reviews IS
    'LLM 科学审核结果：ranking → LLM judge → 审核结果(candidate 层,不写 final)，保存 prompt/response/model/token 全量可追溯';
COMMENT ON COLUMN macro_candidate_connection_llm_reviews.decision IS
    'LLM 判定：supported(支持) / uncertain(不确定) / not_supported(不支持)';
COMMENT ON COLUMN macro_candidate_connection_llm_reviews.connection_type IS
    '连接类型：structural_connection / functional_connectivity / projection / association / unknown';
COMMENT ON COLUMN macro_candidate_connection_llm_reviews.raw_response_json IS
    'LLM 原始响应全文 + 解析结果 + 解析错误(若有)';
COMMENT ON COLUMN macro_candidate_connection_llm_reviews.provenance_json IS
    '溯源：ranking_id + candidate_pair_ids + prompt 全文 + evidence_refs(paper/segment) + llm 元信息';
