-- 20260927: Task Center 软删除(最小字段)。
-- 任务删除不做物理删除:deleted_at/deleted_by 标记;列表默认排除已删除。
-- 历史数据(evidence reviews / items / audit)全部保留。

ALTER TABLE paper_evidence_tasks
    ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS deleted_by VARCHAR(64);

CREATE INDEX IF NOT EXISTS idx_paper_evidence_tasks_deleted
    ON paper_evidence_tasks (deleted_at);

COMMENT ON COLUMN paper_evidence_tasks.deleted_at IS
    '软删除时间(非物理删除，历史数据保留；null=未删除)';
COMMENT ON COLUMN paper_evidence_tasks.deleted_by IS
    '软删除操作人';
