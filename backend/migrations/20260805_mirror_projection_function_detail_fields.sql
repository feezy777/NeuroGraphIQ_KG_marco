-- Projection function detail fields (LLM already returns them; persist as columns)

ALTER TABLE mirror_projection_functions
    ADD COLUMN IF NOT EXISTS function_term_cn TEXT,
    ADD COLUMN IF NOT EXISTS function_domain TEXT,
    ADD COLUMN IF NOT EXISTS function_role TEXT,
    ADD COLUMN IF NOT EXISTS effect_type TEXT;
