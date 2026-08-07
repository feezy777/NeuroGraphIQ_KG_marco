-- 20260807_paper_evidence_v9.sql (idempotent)
-- Scale & reliability closure: filter snapshot, async materializer, versions, draft revision.

-- 1) tasks: materialization lifecycle + filter snapshot
ALTER TABLE paper_evidence_tasks ADD COLUMN IF NOT EXISTS scope_type VARCHAR(16);
ALTER TABLE paper_evidence_tasks ADD COLUMN IF NOT EXISTS filter_snapshot JSONB;
ALTER TABLE paper_evidence_tasks ADD COLUMN IF NOT EXISTS estimated_target_count INT;
ALTER TABLE paper_evidence_tasks ADD COLUMN IF NOT EXISTS materialized_target_count INT NOT NULL DEFAULT 0;
ALTER TABLE paper_evidence_tasks ADD COLUMN IF NOT EXISTS materialization_status VARCHAR(16) NOT NULL DEFAULT 'pending';
ALTER TABLE paper_evidence_tasks ADD COLUMN IF NOT EXISTS materialization_cursor UUID;
ALTER TABLE paper_evidence_tasks ADD COLUMN IF NOT EXISTS materialization_error TEXT;
CREATE INDEX IF NOT EXISTS idx_paper_evidence_tasks_materialization ON paper_evidence_tasks (materialization_status);

-- 2) items: pipeline version metadata + draft optimistic concurrency
ALTER TABLE paper_evidence_task_items ADD COLUMN IF NOT EXISTS retrieval_version VARCHAR(64);
ALTER TABLE paper_evidence_task_items ADD COLUMN IF NOT EXISTS draft_revision INT NOT NULL DEFAULT 0;

-- 3) per-task target uniqueness (idempotent materialization)
CREATE UNIQUE INDEX IF NOT EXISTS uq_task_item_target
  ON paper_evidence_task_items (task_id, target_type, target_id);
