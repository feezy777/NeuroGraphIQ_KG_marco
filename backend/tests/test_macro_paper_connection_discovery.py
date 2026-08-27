"""Macro Paper-driven Connection Discovery V1 测试(纯函数,不碰 DB)。

覆盖用户要求:
- region alias 正确解析(canonical/en/cn/abbr 四级置信)
- 左右半球解析(left/right/unspecified)
- 同句双脑区召回(→ same_sentence pair)
- 不相关词过滤(缩写大写独立成词,代词 it 不误报)
- evidence lineage 完整(句 → mention → segment 可追溯)
- 幂等运行(INSERT ON CONFLICT DO NOTHING 形状)
扩展:同节/跨节 pair 级别、重叠最长词优先、上下文前后句、
title 源只进 mentions 不建 segment、pair 方向排序确定性。
"""

from app.services.macro_paper_connection_discovery_service import (
    ASSERTION_TYPE,
    CREATED_METHOD,
    GENERATION_METHOD,
    INSERT_MENTION_SQL,
    INSERT_PAIR_SQL,
    INSERT_SEGMENT_SQL,
    MATCH_SOURCE_TITLE,
    SECTION_ABSTRACT,
    SECTION_TITLE,
    SOURCE_TYPE,
    build_paper_discovery,
    build_region_lexicon,
    detect_laterality,
    discover_paper_sentences,
    iter_abstract_sentences,
    iter_fulltext_sentences,
    iter_source_sentences,
    iter_title_sentences,
    scan_sentence,
)

A = "11111111-1111-1111-1111-111111111111"  # Amygdala
H = "22222222-2222-2222-2222-222222222222"  # Hippocampus
T = "33333333-3333-3333-3333-333333333333"  # Inferior temporal
C = "44444444-4444-4444-4444-444444444444"  # Cerebellum
P = "55555555-5555-5555-5555-555555555555"  # Cerebellar peduncle

REGIONS = [
    {"region_id": A, "canonical_name_en": "Amygdala",
     "aliases": [("amygdaloid body", "alias_en"), ("杏仁体", "alias_cn"),
                 ("Amg", "alias_abbr")]},
    {"region_id": H, "canonical_name_en": "Hippocampus",
     "aliases": [("hippocampal formation", "alias_en"),
                 ("海马体", "alias_cn"), ("Hipp", "alias_abbr")]},
    {"region_id": T, "canonical_name_en": "Inferior temporal",
     "aliases": [("IT", "alias_abbr")]},
    {"region_id": C, "canonical_name_en": "Cerebellum",
     "aliases": [("cerebella", "alias_en")]},
    {"region_id": P, "canonical_name_en": "Cerebellar peduncle",
     "aliases": []},
]

LEXICON = build_region_lexicon(REGIONS)


def _hits(sentence: str):
    return scan_sentence(sentence, LEXICON)


# ---- 1. region alias 正确解析(四级置信) ----

def test_canonical_name_resolution():
    hits = _hits("The amygdala projects to the cortex.")
    assert any(h["region_id"] == A for h in hits)
    amy = next(h for h in hits if h["region_id"] == A)
    assert amy["matched_term"] == "amygdala"
    assert amy["confidence"] == 0.95


def test_en_alias_resolution():
    hits = _hits("The amygdaloid body was examined.")
    assert any(h["region_id"] == A for h in hits)
    assert next(h for h in hits if h["region_id"] == A)["confidence"] == 0.85


def test_cn_alias_resolution():
    hits = _hits("杏仁体与海马体参与了记忆形成。")
    assert any(h["region_id"] == A for h in hits)
    assert any(h["region_id"] == H for h in hits)
    assert next(h for h in hits if h["region_id"] == A)["confidence"] == 0.80


def test_abbrev_uppercase_resolution():
    """'It'(代词)不命中 IT;'IT'(大写独立成词)命中 → 0.60。"""
    assert not any(h["region_id"] == T for h in _hits(
        "It remains debated whether this pathway is direct."))
    hits = _hits("The amygdala projects to IT and adjacent areas.")
    assert any(h["region_id"] == T for h in hits)
    it = next(h for h in hits if h["region_id"] == T)
    assert it["confidence"] == 0.60


# ---- 2. 左右半球解析 ----

def test_laterality_left_right_unspecified():
    assert detect_laterality("the left amygdala projects", 4, 12) == "left"
    assert detect_laterality("the right hippocampus was scanned", 4, 9) == "right"
    assert detect_laterality("the amygdala projects", 4, 12) == "unspecified"


def test_laterality_window_limits():
    """远词(>30 字符)不算修饰。"""
    assert detect_laterality(
        "the amygdala is located deep in the temporal lobe and "
        "the right side showed activation", 4, 12) == "unspecified"


# ---- 3. 同句双脑区召回 ----

def test_same_sentence_pair_generation():
    sentences = iter_abstract_sentences(
        ["The amygdala projects to the hippocampus."])
    hits, mentions = discover_paper_sentences(sentences, LEXICON)
    discovery = build_paper_discovery(hits, mentions, "paper-1")
    assert len(discovery["pairs"]) == 1
    pair = discovery["pairs"][0]
    assert {pair["source_region_id"], pair["target_region_id"]} == {A, H}
    assert pair["cooccurrence"] == "same_sentence"
    assert pair["confidence"] == 0.80
    assert pair["generation_method"] == GENERATION_METHOD
    assert pair["assertion_type"] == ASSERTION_TYPE
    assert pair["source_type"] == SOURCE_TYPE
    assert pair["evidence_sentence"] == "The amygdala projects to the hippocampus."


def test_same_section_pair():
    sentences = iter_abstract_sentences(
        ["The amygdala was examined.", "The hippocampus was activated."])
    hits, mentions = discover_paper_sentences(sentences, LEXICON)
    discovery = build_paper_discovery(hits, mentions, "paper-1")
    pair = discovery["pairs"][0]
    assert pair["cooccurrence"] == "same_section"
    assert pair["confidence"] == 0.60


def test_same_paper_pair_cross_section():
    fulltext = [
        {"name": "Introduction", "paragraphs": ["The amygdala is a key region."]},
        {"name": "Methods", "paragraphs": ["The hippocampus was segmented."]},
    ]
    sentences = iter_fulltext_sentences(fulltext)
    hits, mentions = discover_paper_sentences(sentences, LEXICON)
    discovery = build_paper_discovery(hits, mentions, "paper-1")
    pair = discovery["pairs"][0]
    assert pair["cooccurrence"] == "same_paper"
    assert pair["confidence"] == 0.40
    assert pair["section_name"] == "Introduction"  # 证据句 = 先出现句


def test_pair_strongest_cooccurrence_wins():
    """同句 + 跨节同时存在 → 取最强(same_sentence)。"""
    sentences = iter_abstract_sentences(
        ["The amygdala projects to the hippocampus.",
         "The amygdala was also examined."])
    hits, mentions = discover_paper_sentences(sentences, LEXICON)
    discovery = build_paper_discovery(hits, mentions, "paper-1")
    assert discovery["pairs"][0]["cooccurrence"] == "same_sentence"


def test_pair_direction_sorted():
    """无向对按 region_id 排序,与句子顺序无关。"""
    s1 = iter_abstract_sentences(["The hippocampus receives amygdala input."])
    h1, m1 = discover_paper_sentences(s1, LEXICON)
    p1 = build_paper_discovery(h1, m1, "paper-1")["pairs"][0]
    assert p1["source_region_id"] == A  # 1111... < 2222...
    assert p1["target_region_id"] == H


def test_no_self_pair():
    sentences = iter_abstract_sentences(
        ["The amygdala and the amygdaloid body overlap."])
    hits, mentions = discover_paper_sentences(sentences, LEXICON)
    discovery = build_paper_discovery(hits, mentions, "paper-1")
    assert discovery["pairs"] == []


# ---- 4. 不相关词过滤 ----

def test_irrelevant_sentence_no_mentions():
    sentences = iter_abstract_sentences(
        ["Participants were scanned with a 3T MRI scanner."])
    hits, mentions = discover_paper_sentences(sentences, LEXICON)
    assert all(not s["hits"] for s in hits)  # 全部句子保留,但无命中
    assert mentions == []


def test_overlap_longest_term_wins():
    """'cerebellar peduncle' 覆盖 'cerebellum' 子串 → 长词胜,不双命中。"""
    hits = _hits("The cerebellar peduncle carries fibres to the pons.")
    region_ids = [h["region_id"] for h in hits]
    assert P in region_ids
    assert C not in region_ids  # 长词消解后不再命中 Cerebellum


def test_abbrev_not_substring_matched():
    """缩写(含 'Hipp' 4 字符 abbr)不能作子串命中。
    'Hippocampal' 里的 'Hipp' 前缀后跟字母 → 不命中。
    """
    assert not any(h["region_id"] == H and h["matched_term"] == "hipp"
                   for h in _hits("Hippocampal volume was measured."))
    assert not any(h["region_id"] == H and h["matched_term"] == "hipp"
                   for h in _hits("The hippocampal formation was large."))
    hits = _hits("Hipp and the amygdala were examined.")
    assert any(h["region_id"] == H for h in hits)  # 大写独立成词 → 命中


# ---- 5. evidence lineage 完整 ----

def test_evidence_lineage_sentence_to_segment():
    text = "The amygdala projects to the hippocampus."
    sentences = iter_abstract_sentences([text])
    hits, mentions = discover_paper_sentences(sentences, LEXICON)
    discovery = build_paper_discovery(hits, mentions, "paper-1")
    assert len(discovery["segments"]) == 1
    seg = discovery["segments"][0]
    assert seg["sentence_text"] == text              # 原文逐字
    assert seg["source_type"] == "paper_abstract"
    assert seg["section_name"] == SECTION_ABSTRACT
    # segment 命中区 = mentions 区(全量可追溯)
    seg_regions = {m["region_id"] for m in seg["matched_regions"]}
    assert seg_regions == {m["region_id"] for m in mentions}
    # mention 的句子文本与 segment 一致
    assert {m["sentence_text"] for m in mentions} == {seg["sentence_text"]}


def test_segment_context_before_after():
    """上下文 = 原文相邻句(含无命中句);边界为同节首/末句。"""
    sentences = iter_abstract_sentences(
        ["First sentence about activation.",
         "The amygdala and hippocampus were both engaged.",
         "Third sentence with no regions."])
    hits, mentions = discover_paper_sentences(sentences, LEXICON)
    discovery = build_paper_discovery(hits, mentions, "paper-1")
    seg = discovery["segments"][0]
    assert seg["context_before"] == "First sentence about activation."
    assert seg["context_after"] == "Third sentence with no regions."
    # 边界:命中句为同节首句 → before=None
    s2 = iter_abstract_sentences(
        ["The amygdala and hippocampus were both engaged.",
         "Later sentence about structure."])
    h2, m2 = discover_paper_sentences(s2, LEXICON)
    d2 = build_paper_discovery(h2, m2, "paper-2")
    seg2 = d2["segments"][0]
    assert seg2["context_before"] is None
    assert seg2["context_after"] == "Later sentence about structure."


def test_title_source_no_segment():
    """title 只进 mentions(match_source='title'),不建 evidence segment。"""
    sentences = iter_title_sentences("Amygdala–hippocampus connectivity")
    hits, mentions = discover_paper_sentences(sentences, LEXICON)
    discovery = build_paper_discovery(hits, mentions, "paper-1")
    assert mentions and all(m["match_source"] == MATCH_SOURCE_TITLE
                            for m in mentions)
    assert all(m["section_name"] == SECTION_TITLE for m in mentions)
    assert discovery["segments"] == []


# ---- 6. 幂等运行 ----

def test_insert_sql_idempotent_shapes():
    assert "ON CONFLICT" in INSERT_MENTION_SQL
    assert "DO NOTHING" in INSERT_MENTION_SQL
    assert "ON CONFLICT" in INSERT_PAIR_SQL
    assert "ON CONFLICT (paper_id, source_region_id, target_region_id)" \
        in INSERT_PAIR_SQL
    assert "ON CONFLICT" in INSERT_SEGMENT_SQL
    for sql in (INSERT_MENTION_SQL, INSERT_PAIR_SQL, INSERT_SEGMENT_SQL):
        assert "DELETE" not in sql
        assert "UPDATE" not in sql


def test_same_input_deterministic():
    """同输入两次 → 相同 mentions/pairs/segments(确定性幂等前提)。"""
    text = ["The amygdala projects to the hippocampus.",
            "The cerebellum also responded."]
    r1 = build_paper_discovery(
        *discover_paper_sentences(iter_abstract_sentences(text), LEXICON),
        "paper-1")
    r2 = build_paper_discovery(
        *discover_paper_sentences(iter_abstract_sentences(text), LEXICON),
        "paper-1")
    assert r1["mentions"] == r2["mentions"]
    assert r1["pairs"] == r2["pairs"]
    assert r1["segments"] == r2["segments"]


# ---- 扩展:结构完整性 ----

def test_fulltext_source_sections():
    fulltext = [
        {"name": "Results", "paragraphs": ["The amygdala was activated."]},
        {"name": "Discussion", "paragraphs": ["The hippocampus co-activated."]},
    ]
    sentences = iter_fulltext_sentences(fulltext)
    hits, mentions = discover_paper_sentences(sentences, LEXICON)
    discovery = build_paper_discovery(hits, mentions, "paper-1")
    assert discovery["segments"][0]["section_name"] == "Results"
    assert discovery["segments"][0]["source_type"] == "paper_fulltext"
    assert discovery["pairs"][0]["cooccurrence"] == "same_paper"


def test_mention_aggregation_same_sentence_same_region():
    """同句同区多词命中 → 聚合一条 mention,首现词 + 最高置信。"""
    sentences = iter_abstract_sentences(
        ["The amygdala, i.e. the amygdaloid body, was examined."])
    hits, mentions = discover_paper_sentences(sentences, LEXICON)
    amy = [m for m in mentions if m["region_id"] == A]
    assert len(amy) == 1
    assert amy[0]["matched_term"] == "amygdala"   # 首现词
    assert amy[0]["confidence"] == 0.95           # 最高置信(canonical)


def test_created_method_defaults():
    sentences = iter_abstract_sentences(["The amygdala projects to the hippocampus."])
    hits, mentions = discover_paper_sentences(sentences, LEXICON)
    discovery = build_paper_discovery(hits, mentions, "paper-1")
    assert discovery["mentions"][0]["created_method"] == CREATED_METHOD
    assert discovery["segments"][0]["created_method"] == CREATED_METHOD
