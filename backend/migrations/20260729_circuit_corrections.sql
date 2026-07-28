-- Mirror Circuit Corrections Overlay Table
-- All corrections write to this separate overlay table.
-- DeepSeek may ONLY propose corrections here. Direct source data is NEVER modified.
-- Human approval required before applying.

CREATE TABLE IF NOT EXISTS mirror_circuit_corrections (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  circuit_id UUID NOT NULL,
  validation_result_id UUID,
  rule_code TEXT NOT NULL,
  field_path TEXT NOT NULL,
  original_value JSONB,
  suggested_value JSONB,
  approved_value JSONB,
  correction_type TEXT NOT NULL DEFAULT 'metadata',
  repairability TEXT NOT NULL DEFAULT 'manual_required',
  suggestion_source TEXT DEFAULT 'deepseek',
  suggestion_confidence DOUBLE PRECISION,
  authoritative_source TEXT,
  deterministic_validation_status TEXT DEFAULT 'pending',
  deterministic_validation_message TEXT,
  approval_status TEXT NOT NULL DEFAULT 'proposed',
  approved_by TEXT,
  approved_at TIMESTAMPTZ,
  approval_reason TEXT,
  revalidation_status TEXT DEFAULT 'not_started',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_corrections_circuit ON mirror_circuit_corrections(circuit_id);
CREATE INDEX IF NOT EXISTS idx_corrections_approval ON mirror_circuit_corrections(approval_status);
CREATE INDEX IF NOT EXISTS idx_corrections_validation_result ON mirror_circuit_corrections(validation_result_id);
