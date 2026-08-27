-- 20260928: Paper Library 升级(最小字段)。
-- 论文删除采用软删除(deleted_at/deleted_by),禁止物理删除;历史证据/引用全保留。
-- 其余升级(添加/筛选/detail 扩展)均为只读或已有 upsert 逻辑,无需新列。

ALTER TABLE paper_sources
    ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS deleted_by VARCHAR(64);

CREATE INDEX IF NOT EXISTS idx_paper_sources_deleted
    ON paper_sources (deleted_at);

COMMENT ON COLUMN paper_sources.deleted_at IS
    '软删除时间(论文资产保留，禁止物理删除；null=未删除)';
COMMENT ON COLUMN paper_sources.deleted_by IS
    '软删除操作人';
