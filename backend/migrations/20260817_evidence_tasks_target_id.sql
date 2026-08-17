-- 佐证任务一对一:任务行即对象。
-- target_id = 对象身份;新建任务必填,旧行为 NULL(由拆分迁移回填)。
ALTER TABLE paper_evidence_tasks ADD COLUMN IF NOT EXISTS target_id UUID;
CREATE INDEX IF NOT EXISTS idx_paper_evidence_tasks_target ON paper_evidence_tasks (target_type, target_id);
