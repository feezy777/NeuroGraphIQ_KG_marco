-- Macro Paper Full Text Evidence Extraction V1
-- paper_connection_evidence_segments 扩展:正文级证据来源。
--
-- 设计(用户要求):
-- * 不修改已有摘要证据(现有行默认 evidence_source_type='paper_abstract')
-- * 新增正文证据来源区分:
--   - evidence_source_type: paper_abstract | paper_fulltext
--   - section_name: Introduction / Methods / Results / Discussion /
--     Figure 等(取自 JATS sec title)
-- * UNIQUE 约束扩展为 (paper_id, connection_id, evidence_source_type):
--   同一 (paper, connection) 允许摘要级 + 正文级各一条,互不覆盖
--
-- 幂等:ADD COLUMN IF NOT EXISTS / DROP CONSTRAINT IF EXISTS。

ALTER TABLE paper_connection_evidence_segments
    ADD COLUMN IF NOT EXISTS evidence_source_type varchar(32)
        NOT NULL DEFAULT 'paper_abstract'
        CHECK (evidence_source_type IN ('paper_abstract', 'paper_fulltext')),
    ADD COLUMN IF NOT EXISTS section_name varchar(128);

-- 现有 UNIQUE(paper_id, connection_id) 升级为按来源区分
-- (先 DROP 两个候选名再 ADD —— ADD CONSTRAINT 无 IF NOT EXISTS,
--  先删后建保证幂等)
ALTER TABLE paper_connection_evidence_segments
    DROP CONSTRAINT IF EXISTS uq_segment_paper_connection_source;
ALTER TABLE paper_connection_evidence_segments
    DROP CONSTRAINT IF EXISTS uq_segment_paper_connection;
ALTER TABLE paper_connection_evidence_segments
    ADD CONSTRAINT uq_segment_paper_connection_source
        UNIQUE (paper_id, connection_id, evidence_source_type);

COMMENT ON COLUMN paper_connection_evidence_segments.evidence_source_type IS
    '证据来源:paper_abstract=摘要级 / paper_fulltext=正文级(fullTextXML)';
COMMENT ON COLUMN paper_connection_evidence_segments.section_name IS
    '正文章节名(Introduction/Methods/Results/Discussion/Figure 等,JATS sec title)';
