-- mirror_circuit_validation_runs: validation run master table
CREATE TABLE IF NOT EXISTS mirror_circuit_validation_runs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  granularity_level TEXT NOT NULL,
  source_atlas TEXT,
  target_types TEXT[] NOT NULL DEFAULT '{}',
  scope_json JSONB NOT NULL DEFAULT '{}',
  rule_validation_status TEXT NOT NULL DEFAULT 'pending',
  rule_total_count INTEGER DEFAULT 0,
  rule_passed_count INTEGER DEFAULT 0,
  rule_failed_count INTEGER DEFAULT 0,
  rule_warning_count INTEGER DEFAULT 0,
  rule_blocked_count INTEGER DEFAULT 0,
  rule_hard_failure_count INTEGER DEFAULT 0,
  dual_review_status TEXT NOT NULL DEFAULT 'pending',
  dual_review_total_count INTEGER DEFAULT 0,
  dual_review_agreement_count INTEGER DEFAULT 0,
  dual_review_conflict_count INTEGER DEFAULT 0,
  dual_review_rejection_count INTEGER DEFAULT 0,
  dual_review_uncertain_count INTEGER DEFAULT 0,
  dual_review_low_evidence_count INTEGER DEFAULT 0,
  adjudication_status TEXT NOT NULL DEFAULT 'pending',
  reviewer_a_provider TEXT NOT NULL DEFAULT 'deepseek',
  reviewer_a_model TEXT NOT NULL DEFAULT 'deepseek-chat',
  reviewer_b_provider TEXT NOT NULL DEFAULT 'kimi',
  reviewer_b_model TEXT NOT NULL DEFAULT 'kimi',
  status TEXT NOT NULL DEFAULT 'created',
  dry_run BOOLEAN DEFAULT FALSE,
  error_message TEXT,
  started_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- mirror_circuit_validation_results: per-object validation result
CREATE TABLE IF NOT EXISTS mirror_circuit_validation_results (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id UUID NOT NULL REFERENCES mirror_circuit_validation_runs(id) ON DELETE CASCADE,
  target_type TEXT NOT NULL,
  target_id UUID NOT NULL,
  object_label TEXT,
  rule_validation_result_json JSONB NOT NULL DEFAULT '[]',
  rule_overall_status TEXT,
  rule_blocked BOOLEAN DEFAULT FALSE,
  reviewer_a_decision TEXT,
  reviewer_a_confidence DOUBLE PRECISION,
  reviewer_a_payload_json JSONB,
  reviewer_b_decision TEXT,
  reviewer_b_confidence DOUBLE PRECISION,
  reviewer_b_payload_json JSONB,
  adjudication_status TEXT,
  adjudication_confidence_diff DOUBLE PRECISION,
  adjudication_summary TEXT,
  recommended_review_priority TEXT,
  mirror_review_record_id UUID,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_validation_runs_status ON mirror_circuit_validation_runs(status);
CREATE INDEX IF NOT EXISTS idx_validation_results_run ON mirror_circuit_validation_results(run_id);
CREATE INDEX IF NOT EXISTS idx_validation_results_target ON mirror_circuit_validation_results(target_type, target_id);
