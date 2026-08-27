-- Segment translations derived asset 
-- Translation is NOT evidence truth and identity stays paper segment original text
CREATE TABLE IF NOT EXISTS evidence_segment_translations (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    segment_id uuid NOT NULL REFERENCES pew_segments(id) ON DELETE CASCADE,
    paper_id uuid NOT NULL REFERENCES paper_sources(id) ON DELETE CASCADE,
    source_language varchar(16) NOT NULL DEFAULT 'en',
    target_language varchar(16) NOT NULL DEFAULT 'zh-CN',
    translated_text text NOT NULL,
    translation_method varchar(16) NOT NULL DEFAULT 'llm',
    translation_model varchar(64),
    translation_prompt_version varchar(64) NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    provenance_json jsonb NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT uq_segment_translation UNIQUE (segment_id, target_language, translation_prompt_version)
);
CREATE INDEX IF NOT EXISTS ix_segment_translations_segment ON evidence_segment_translations (segment_id);

-- Backfill: existing candidate-level translations become segment-level assets
INSERT INTO evidence_segment_translations (segment_id, paper_id, target_language, translated_text,
    translation_model, translation_prompt_version)
SELECT c.segment_id, c.paper_id, 'zh-CN', c.translated_text, c.translation_model,
    COALESCE(c.translation_prompt_version, 'stage4_zh_v1')
FROM pew_evidence_candidates c
WHERE c.translated_text IS NOT NULL AND c.translated_text <> ''
ON CONFLICT DO NOTHING;

-- Token history backfill from reviews table is not applicable (translations never had usage)
-- Existing candidate column retained as legacy mirror; read path goes through translations table
