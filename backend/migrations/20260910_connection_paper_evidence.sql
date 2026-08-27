-- 20260910_connection_paper_evidence.sql
-- Macro Connection 论文数据导入:Connection-Paper 关联表。
--
-- 背景:阶段 G 已将 104 条 literature reference 追加到
-- final_canonical_connections.evidence_reference(91 连接)。
-- 本迁移建立正式 Connection-Paper 关联结构(非新论文表 —— 论文仍存
-- paper_sources),每条关联 = 一条 literature reference 的落库载体。
--
-- 字段(用户指定)— connection_id, paper_id, support_type,
-- evidence_reference, confidence, provenance_json。

CREATE TABLE IF NOT EXISTS connection_paper_evidence (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    connection_id uuid NOT NULL
        REFERENCES final_canonical_connections(id)
        ON DELETE CASCADE,
    paper_id uuid NOT NULL
        REFERENCES paper_sources(id)
        ON DELETE CASCADE,
    support_type varchar(64) NOT NULL DEFAULT 'literature',
    evidence_reference jsonb NOT NULL DEFAULT '[]'::jsonb,
    confidence numeric NOT NULL DEFAULT 0,
    provenance_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    -- 同一连接同一论文至多一条关联(同论文重复 reference 去重)
    CONSTRAINT uq_connection_paper UNIQUE (connection_id, paper_id)
);

CREATE INDEX IF NOT EXISTS ix_connection_paper_paper
    ON connection_paper_evidence (paper_id);
CREATE INDEX IF NOT EXISTS ix_connection_paper_connection
    ON connection_paper_evidence (connection_id);

COMMENT ON TABLE connection_paper_evidence IS
    'Connection-Paper 关联:final connection 与其支撑论文(paper_sources)的正式关联';
COMMENT ON COLUMN connection_paper_evidence.support_type IS
    '支撑类型:literature(论文文献证据)';
COMMENT ON COLUMN connection_paper_evidence.evidence_reference IS
    '该论文支撑该连接的 evidence_reference 元素(与 final.evidence_reference 中 literature 元素同构,含 DOI/PMID/匹配 provenance)';
COMMENT ON COLUMN connection_paper_evidence.provenance_json IS
    '导入溯源:来源阶段、导入时间、匹配方式等';
