-- Macro Paper-driven Connection Discovery V1
-- 论文驱动的候选连接发现基础设施(第一阶段,仅候选发现,不审核不晋升)。
--
-- 设计(用户要求):
-- * 不修改 final_canonical_connections / canonical_connections /
--   paper_sources —— 所有新发现只进入 candidate 层新表
-- * 三张表:
--   1. paper_region_mentions         论文内脑区实体命中(句子粒度)
--   2. paper_region_pair_candidates  同论文脑区组合候选(无向对,幂等合并)
--   3. paper_region_evidence_segments 命中句证据库(原文 + 上下文 + 溯源)
-- * 本阶段只生成候选,不判断真假(assertion_type='candidate')
-- * 所有 evidence 必须可追溯到论文原文(segment 保存原文句子文本,
--   幂等键保证同源同句同节只存一条)
-- * generation_method='paper_region_cooccurrence_v1'(论文内共现驱动)
--
-- 幂等:全部 CREATE TABLE IF NOT EXISTS + 列内 UNIQUE 约束,
-- 脚本 INSERT ON CONFLICT DO NOTHING → 复跑 0 新增。

-- 1) paper_region_mentions —— 论文×脑区×句子 实体命中
CREATE TABLE IF NOT EXISTS paper_region_mentions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    paper_id uuid NOT NULL REFERENCES paper_sources(id) ON DELETE CASCADE,
    region_id uuid NOT NULL REFERENCES canonical_brain_regions(id) ON DELETE CASCADE,
    matched_term varchar(256) NOT NULL,           -- 命中的词(原文书写,小写存储)
    match_source varchar(16) NOT NULL
        CHECK (match_source IN ('title', 'abstract', 'fulltext')),
    sentence_id integer NOT NULL,                 -- (paper, source, section) 内句子序号,1-based
    section_name varchar(256) NOT NULL DEFAULT '',
    laterality varchar(16) NOT NULL DEFAULT 'unspecified'
        CHECK (laterality IN ('left', 'right', 'unspecified')),
    confidence numeric(4, 3) NOT NULL,            -- canonical 0.95 / en 别名 0.85 / cn 0.80 / abbr 0.60
    created_method varchar(64) NOT NULL DEFAULT 'paper_region_ner_v1',
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_paper_region_mention
        UNIQUE (paper_id, region_id, match_source, sentence_id, section_name)
);

CREATE INDEX IF NOT EXISTS ix_paper_region_mentions_paper
    ON paper_region_mentions (paper_id);
CREATE INDEX IF NOT EXISTS ix_paper_region_mentions_region
    ON paper_region_mentions (region_id);

COMMENT ON TABLE paper_region_mentions IS
    '论文内 Macro96 脑区实体命中:句子粒度 NER 结果(candidate 层,不写 final)';
COMMENT ON COLUMN paper_region_mentions.matched_term IS
    '命中的词(小写),来自 canonical 名或 canonical_region_aliases';
COMMENT ON COLUMN paper_region_mentions.laterality IS
    '左右半球解析:命中词前后 4 词内 left/right → left/right,否则 unspecified';
COMMENT ON COLUMN paper_region_mentions.confidence IS
    '命中置信:canonical 名 0.95 / en 别名 0.85 / cn 别名 0.80 / 缩写(≤3字符大写成词)0.60';

-- 2) paper_region_pair_candidates —— 同论文脑区组合候选(无向对)
CREATE TABLE IF NOT EXISTS paper_region_pair_candidates (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    paper_id uuid NOT NULL REFERENCES paper_sources(id) ON DELETE CASCADE,
    source_region_id uuid NOT NULL REFERENCES canonical_brain_regions(id) ON DELETE CASCADE,
    target_region_id uuid NOT NULL REFERENCES canonical_brain_regions(id) ON DELETE CASCADE,
    evidence_sentence text NOT NULL,              -- 证据句原文(最强共现句,可追溯)
    context_before text,                          -- 证据句同节前句(无则 NULL)
    context_after text,                           -- 证据句同节后句(无则 NULL)
    section_name varchar(256) NOT NULL DEFAULT '',
    matched_terms jsonb NOT NULL DEFAULT '{}'::jsonb,
        -- {source: {term, sentence_id, laterality}, target: {term, sentence_id, laterality}}
    generation_method varchar(64) NOT NULL
        DEFAULT 'paper_region_cooccurrence_v1',
    assertion_type varchar(16) NOT NULL DEFAULT 'candidate'
        CHECK (assertion_type = 'candidate'),     -- 本阶段只生成候选,不判断真假
    source_type varchar(16) NOT NULL DEFAULT 'literature'
        CHECK (source_type = 'literature'),
    cooccurrence varchar(16) NOT NULL
        CHECK (cooccurrence IN ('same_sentence', 'same_section', 'same_paper')),
    confidence numeric(4, 3) NOT NULL,            -- 同句 0.80 / 同节 0.60 / 同论文 0.40
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_paper_region_pair
        UNIQUE (paper_id, source_region_id, target_region_id),
    CONSTRAINT chk_paper_region_pair_not_self
        CHECK (source_region_id <> target_region_id)
);

CREATE INDEX IF NOT EXISTS ix_paper_region_pair_source
    ON paper_region_pair_candidates (source_region_id);
CREATE INDEX IF NOT EXISTS ix_paper_region_pair_target
    ON paper_region_pair_candidates (target_region_id);
CREATE INDEX IF NOT EXISTS ix_paper_region_pair_paper
    ON paper_region_pair_candidates (paper_id);

COMMENT ON TABLE paper_region_pair_candidates IS
    '论文内 Macro96 脑区组合候选：无向对(region_id 排序)按论文合并一条，generation_method=paper_region_cooccurrence_v1，assertion_type=candidate';
COMMENT ON COLUMN paper_region_pair_candidates.cooccurrence IS
    '共现级别：same_sentence(同句,0.80) / same_section(同节不同句,0.60) / same_paper(跨节,0.40)；多条共现取最强写入';
COMMENT ON COLUMN paper_region_pair_candidates.evidence_sentence IS
    '最强共现证据句原文(论文原文逐字),可追溯性由文本源重建断言保证';

-- 3) paper_region_evidence_segments —— 命中句证据库
CREATE TABLE IF NOT EXISTS paper_region_evidence_segments (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    paper_id uuid NOT NULL REFERENCES paper_sources(id) ON DELETE CASCADE,
    sentence_id integer NOT NULL,                 -- (paper, source_type, section) 内序号
    sentence_text text NOT NULL,                  -- 原文逐字
    context_before text,                          -- 同节前句
    context_after text,                           -- 同节后句
    section_name varchar(256) NOT NULL DEFAULT '',
    source_type varchar(16) NOT NULL
        CHECK (source_type IN ('paper_abstract', 'paper_fulltext')),
    matched_regions jsonb NOT NULL DEFAULT '[]'::jsonb,
        -- [{region_id, matched_term, laterality, confidence}]
    created_method varchar(64) NOT NULL DEFAULT 'paper_region_ner_v1',
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_paper_region_evidence
        UNIQUE (paper_id, source_type, section_name, sentence_id)
);

CREATE INDEX IF NOT EXISTS ix_paper_region_evidence_paper
    ON paper_region_evidence_segments (paper_id);

COMMENT ON TABLE paper_region_evidence_segments IS
    '论文命中句证据库:每个含 Macro96 脑区的句子保存原文 + 前后文 + 章节,'
    '全部可追溯到论文原文(evidence lineage)';
COMMENT ON COLUMN paper_region_evidence_segments.matched_regions IS
    '该句命中的全部脑区列表(region_id / matched_term / laterality / confidence)';
