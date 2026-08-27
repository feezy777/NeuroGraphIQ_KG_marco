-- Stage 3: AI 语义审核(pew_reviews 扩展:连接类型支持/支持短语/矛盾理由/版本/用量/失败标记)
ALTER TABLE pew_reviews ADD COLUMN IF NOT EXISTS connection_type_supported varchar(64);
ALTER TABLE pew_reviews ADD COLUMN IF NOT EXISTS supporting_phrase text;
ALTER TABLE pew_reviews ADD COLUMN IF NOT EXISTS contradiction_reason text;
ALTER TABLE pew_reviews ADD COLUMN IF NOT EXISTS prompt_version varchar(64);
ALTER TABLE pew_reviews ADD COLUMN IF NOT EXISTS prompt_json jsonb;
ALTER TABLE pew_reviews ADD COLUMN IF NOT EXISTS token_usage jsonb;
ALTER TABLE pew_reviews ADD COLUMN IF NOT EXISTS failed boolean NOT NULL DEFAULT false;

-- evidence_type 词表扩展(none:未命中任何证据类型)
ALTER TABLE pew_reviews DROP CONSTRAINT IF EXISTS pew_reviews_evidence_type_check;
ALTER TABLE pew_reviews ADD CONSTRAINT pew_reviews_evidence_type_check
    CHECK (evidence_type IN ('direct', 'indirect', 'context', 'contradictory', 'none'));
