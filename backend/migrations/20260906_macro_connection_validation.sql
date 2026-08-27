-- 20260906: Macro Connection Validation V1
-- Canonical Connection 第一版验证流程(validation_result,不执行 promotion)
--
-- 1) canonical_connection_validation_runs — 一次验证执行的批次统计
-- 2) canonical_connection_validation_results — 每 canonical 一条验证结果
--    entity_type / entity_id / validation_status(PASS/FAIL/REVIEW_REQUIRED)
--    failed_rules JSONB / validation_timestamp / validator_version
-- 幂等:脚本重跑 = 删除同一 validator_key 的旧 run(级联删 results)后重建,
-- 保持"最新验证"语义;不修改 canonical_connections 任何状态字段

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = current_schema()
                   AND tablename = 'canonical_connection_validation_runs') THEN
        CREATE TABLE canonical_connection_validation_runs (
            id                  UUID PRIMARY KEY,
            validator_key       TEXT NOT NULL,
            validator_version   TEXT NOT NULL,
            scope_json          JSONB NOT NULL DEFAULT '{}'::jsonb,
            status              TEXT NOT NULL DEFAULT 'created',
            object_count        INTEGER NOT NULL DEFAULT 0,
            passed_count        INTEGER NOT NULL DEFAULT 0,
            failed_count        INTEGER NOT NULL DEFAULT 0,
            review_count        INTEGER NOT NULL DEFAULT 0,
            started_at          TIMESTAMPTZ,
            finished_at         TIMESTAMPTZ,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
        );
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_tables WHERE schemaname = current_schema()
                   AND tablename = 'canonical_connection_validation_results') THEN
        CREATE TABLE canonical_connection_validation_results (
            id                  UUID PRIMARY KEY,
            run_id              UUID NOT NULL REFERENCES canonical_connection_validation_runs(id)
                                      ON DELETE CASCADE,
            entity_type         TEXT NOT NULL DEFAULT 'canonical_connection',
            entity_id           UUID NOT NULL,
            validation_status   TEXT NOT NULL CHECK (validation_status IN
                                  ('PASS', 'FAIL', 'REVIEW_REQUIRED')),
            failed_rules        JSONB NOT NULL DEFAULT '[]'::jsonb,
            validator_version   TEXT NOT NULL,
            validation_timestamp TIMESTAMPTZ NOT NULL DEFAULT now(),
            created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE INDEX idx_cc_val_results_run ON canonical_connection_validation_results(run_id);
        CREATE INDEX idx_cc_val_results_entity ON canonical_connection_validation_results(entity_id);
        CREATE INDEX idx_cc_val_results_status ON canonical_connection_validation_results(validation_status);
    END IF;
END $$;
