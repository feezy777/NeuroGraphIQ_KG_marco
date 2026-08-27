-- Macro Paper Evidence Extraction V1
-- paper_connection_evidence_segments —— 论文摘要 → 连接证据片段。
--
-- 设计(用户要求):
-- * 可解释证据链:Paper → Evidence Segment → Connection
-- * evidence_text = 论文摘要中的原文片段(逐字提取,禁止生成不存在的原文)
-- * 摘要没有明确支持句 → 不生成 evidence_text,标记 status='no_direct_evidence'
-- * 数据来源:paper_sources.enrichment_json.abstract
-- * 只处理已有 connection_paper_evidence 关联的论文
--
-- 字段(用户指定):
--   id, paper_id, connection_id, evidence_text, evidence_location,
--   extraction_method, confidence, provenance_json
-- 扩展:status(extracted / no_direct_evidence)、created_at/updated_at
--
-- 幂等:UNIQUE(paper_id, connection_id) → INSERT ON CONFLICT DO NOTHING。

CREATE TABLE IF NOT EXISTS paper_connection_evidence_segments (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    paper_id uuid NOT NULL REFERENCES paper_sources(id) ON DELETE CASCADE,
    connection_id uuid NOT NULL
        REFERENCES final_canonical_connections(id) ON DELETE CASCADE,
    evidence_text text,
    evidence_location varchar(128),
    extraction_method varchar(64) NOT NULL,
    confidence numeric(4, 3),
    provenance_json jsonb DEFAULT '{}'::jsonb,
    status varchar(32) NOT NULL DEFAULT 'extracted'
        CHECK (status IN ('extracted', 'no_direct_evidence')),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_segment_paper_connection UNIQUE (paper_id, connection_id)
);

CREATE INDEX IF NOT EXISTS ix_segments_connection
    ON paper_connection_evidence_segments (connection_id);
CREATE INDEX IF NOT EXISTS ix_segments_paper
    ON paper_connection_evidence_segments (paper_id);

COMMENT ON TABLE paper_connection_evidence_segments IS
    '论文摘要证据片段:Paper → Evidence → Connection 可解释证据链'
    '(evidence_text 必须为摘要原文,status=no_direct_evidence 表示无明确支持句)';
