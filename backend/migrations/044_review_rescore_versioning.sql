-- 044_review_rescore_versioning.sql (idempotent)
-- S7B: review 版本化(回退并重新评分)。
-- 不添加 is_current(由 superseded_at IS NULL 推导,并发由 review 行锁串行化);
-- 不添加新 review_status 值;不自动为历史 review 建链(旧记录保持 revision_no=1)。

-- 1) reviews 版本列:子→父单向链(新 review 指旧 review)
ALTER TABLE paper_evidence_reviews
    ADD COLUMN IF NOT EXISTS revision_no INT NOT NULL DEFAULT 1;
ALTER TABLE paper_evidence_reviews
    ADD COLUMN IF NOT EXISTS supersedes_review_id UUID
        REFERENCES paper_evidence_reviews(id);
ALTER TABLE paper_evidence_reviews
    ADD COLUMN IF NOT EXISTS superseded_at TIMESTAMPTZ;
ALTER TABLE paper_evidence_reviews
    ADD COLUMN IF NOT EXISTS superseded_by VARCHAR(64);
ALTER TABLE paper_evidence_reviews
    ADD COLUMN IF NOT EXISTS rollback_reason TEXT;

CREATE INDEX IF NOT EXISTS idx_reviews_supersedes
    ON paper_evidence_reviews (supersedes_review_id);
CREATE INDEX IF NOT EXISTS idx_reviews_task_item
    ON paper_evidence_reviews (task_item_id);

-- 2) task items 挂 pending rescore 上下文(build 新版本时消费)
ALTER TABLE paper_evidence_task_items
    ADD COLUMN IF NOT EXISTS rescore_source_review_id UUID
        REFERENCES paper_evidence_reviews(id);
ALTER TABLE paper_evidence_task_items
    ADD COLUMN IF NOT EXISTS rescore_revision_no INT;
