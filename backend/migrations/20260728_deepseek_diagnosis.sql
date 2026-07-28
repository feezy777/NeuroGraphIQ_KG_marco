-- Add deepseek_diagnosis_json column to mirror_circuit_validation_results
ALTER TABLE mirror_circuit_validation_results
  ADD COLUMN IF NOT EXISTS deepseek_diagnosis_json JSONB DEFAULT NULL;
