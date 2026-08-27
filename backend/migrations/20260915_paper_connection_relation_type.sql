-- Macro Paper-Connection Evidence Reclassification V1
-- connection_paper_evidence 新增关联质量分类字段。
--
-- 设计(用户要求):
-- * 不删除原始 paper_connection_evidence 行
-- * 新增 evidence_relation_type 字段,对 104 条关联重新评估:
--   - direct_support  (A)：论文原文明确描述两脑区间连接(有 extracted segment)
--   - context_support (B)：论文研究相关脑区或功能,但未证明该连接
--   - invalid        (C)：论文与连接无直接关系
-- * 原始 match_method / doi / pmid / confidence 保留在
--   provenance_json / evidence_reference / confidence 列,本迁移不动
--
-- 幂等:ADD COLUMN IF NOT EXISTS(列已存在时连同 CHECK 一起跳过)。

ALTER TABLE connection_paper_evidence
    ADD COLUMN IF NOT EXISTS evidence_relation_type varchar(32)
        CHECK (evidence_relation_type IN
               ('direct_support', 'context_support', 'invalid'));

COMMENT ON COLUMN connection_paper_evidence.evidence_relation_type IS
    'paper-connection 关联质量分类：direct_support=论文明确描述该连接 / '
    'context_support=论文研究相关脑区或功能但未证明该连接 / '
    'invalid=论文与连接无直接关系(由 Macro Paper-Connection '
    'Evidence Reclassification V1 回填)';
