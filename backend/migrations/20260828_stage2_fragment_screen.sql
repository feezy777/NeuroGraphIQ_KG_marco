-- Stage 2: 系统函数筛选疑似证据片段(Evidence Discovery Workspace 临时候选层)
-- pew_segments 演进:candidate_level/matched_relation_terms + source_type/proximity 词表扩展
ALTER TABLE pew_segments ADD COLUMN IF NOT EXISTS candidate_level varchar(16);
ALTER TABLE pew_segments ADD COLUMN IF NOT EXISTS matched_relation_terms jsonb NOT NULL DEFAULT '[]'::jsonb;

ALTER TABLE pew_segments DROP CONSTRAINT IF EXISTS pew_segments_source_type_check;
ALTER TABLE pew_segments ADD CONSTRAINT pew_segments_source_type_check
    CHECK (source_type IN ('fulltext', 'abstract', 'title', 'paper_abstract', 'paper_fulltext'));

ALTER TABLE pew_segments DROP CONSTRAINT IF EXISTS pew_segments_proximity_check;
ALTER TABLE pew_segments ADD CONSTRAINT pew_segments_proximity_check
    CHECK (proximity IN ('same_sentence', 'adjacent_sentence', 'same_section', 'same_paper', 'same_paragraph'));

-- 旧值映射为统一值(原 paper_abstract/paper_fulltext → abstract/fulltext)
UPDATE pew_segments SET source_type = 'abstract' WHERE source_type = 'paper_abstract';
UPDATE pew_segments SET source_type = 'fulltext' WHERE source_type = 'paper_fulltext';
