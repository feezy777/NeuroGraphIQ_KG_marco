-- 20260926: Macro Candidate Rule Validation V1
-- 候选连接(paper_connection_candidate_rankings)规则验证阶段(candidate 层)。
--
-- 复用现有验证架构风格(同 canonical_connection_validation_runs/results 双表)：
--   run(validator_key 幂等：重跑覆盖旧 run 级联删旧 results) + results(每 ranking 最新一条)
--
-- 状态(PASS/FAIL/BLOCKED)：
--   6 条规则全通过           → PASS
--   存在 BLOCK 级规则失败    → BLOCKED
--   其余失败                 → FAIL
--   (前端映射为 rule_pass / rule_failed / rule_blocked；pending_rule 为初始态不落库)
--
-- 只写本组表(候选层)，不修改 final/canonical/mirror/ontology 任何数据。
-- 采用裸 CREATE TABLE IF NOT EXISTS 便于分号拆分执行(无 DO $$ 块)。

CREATE TABLE IF NOT EXISTS macro_candidate_rule_validation_runs (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    validator_key       TEXT NOT NULL UNIQUE,
    validator_version   TEXT NOT NULL,
    status              TEXT NOT NULL DEFAULT 'completed'
                        CHECK (status IN ('created', 'running', 'completed', 'failed')),
    object_count        INTEGER NOT NULL DEFAULT 0,
    passed_count        INTEGER NOT NULL DEFAULT 0,
    failed_count        INTEGER NOT NULL DEFAULT 0,
    blocked_count       INTEGER NOT NULL DEFAULT 0,
    started_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at         TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS macro_candidate_rule_validation_results (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id              UUID NOT NULL REFERENCES macro_candidate_rule_validation_runs(id)
                              ON DELETE CASCADE,
    ranking_id          UUID NOT NULL REFERENCES paper_connection_candidate_rankings(id)
                              ON DELETE CASCADE,
    source_region_id    UUID NOT NULL,
    target_region_id    UUID NOT NULL,
    validation_status   TEXT NOT NULL CHECK (validation_status IN
                          ('PASS', 'FAIL', 'BLOCKED')),
    rule_results        JSONB NOT NULL DEFAULT '[]'::jsonb,
        -- [{code, name, passed, severity(normal|block), detail}]
    duplicate_existing  JSONB NOT NULL DEFAULT '{}'::jsonb,
        -- {final: bool, canonical: bool, mirror: bool, mirror_pairs: [ids]}
    failed_rules        JSONB NOT NULL DEFAULT '[]'::jsonb,
        -- [{code, name, detail}] 简明失败清单
    validator_version   TEXT NOT NULL,
    validation_timestamp TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_macro_cand_rule_ranking UNIQUE (ranking_id)
);

CREATE INDEX IF NOT EXISTS idx_macro_cand_rule_run
    ON macro_candidate_rule_validation_results(run_id);
CREATE INDEX IF NOT EXISTS idx_macro_cand_rule_status
    ON macro_candidate_rule_validation_results(validation_status);

COMMENT ON TABLE macro_candidate_rule_validation_results IS
    'Macro 候选连接规则验证结果(candidate 层，仅候选状态；不改 final/canonical/mirror/ontology)';
COMMENT ON COLUMN macro_candidate_rule_validation_results.validation_status IS
    'PASS=6 规则全通过 / FAIL=有失败无 BLOCK / BLOCKED=存在 BLOCK 级失败(R5 重复已存在连接、R6 非法 Macro 形态)';
COMMENT ON COLUMN macro_candidate_rule_validation_results.duplicate_existing IS
    'R5 duplicate 分解：final/canonical 布尔 + mirror_pairs(mirror 连接 id 抽样，上限 20)';
