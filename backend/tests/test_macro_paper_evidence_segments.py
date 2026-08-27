"""Macro Paper Evidence Extraction 测试(纯函数,不碰 DB)。

覆盖:句子切分(原文保留)、region 词表(exact + 别名)、支持句判定
(同句双命中 / 无命中 / 缩写)、confidence 分级(连接动词 / 方向支持 /
缩写降级)、no_direct_evidence 标记、provenance 结构、幂等 SQL 形状。
"""

from app.services.macro_paper_evidence_segments_service import (
    ABBREV_LEN,
    EXTRACTION_METHOD,
    INSERT_SEGMENT_SQL,
    STATUS_EXTRACTED,
    STATUS_NO_DIRECT_EVIDENCE,
    build_segment,
    build_provenance,
    find_support_sentence,
    region_terms,
    score_confidence,
    split_sentences,
)

PAPER = "11111111-1111-1111-1111-111111111111"
CONN = "22222222-2222-2222-2222-222222222222"

ABSTRACT_HIT = ("The cerebellum is known to project via the thalamus to "
                "multiple motor areas of the cerebral cortex. Our data show "
                "that select nuclear divisions of the amygdala project to "
                "the entorhinal cortex, hippocampus, subiculum, and "
                "parasubiculum in segregated rather than overlapping "
                "termination zones.")

ABSTRACT_NO_HIT = ("Hedonic experience is arguably at the heart of what "
                   "makes us human. In recent neuroimaging studies of the "
                   "cortical networks that mediate hedonic experience, the "
                   "orbitofrontal cortex has emerged as the strongest "
                   "candidate for linking food and other types of reward.")


# ---- split_sentences ----

def test_split_sentences_original_text_preserved():
    sents = split_sentences(ABSTRACT_HIT)
    assert len(sents) == 2
    # 原文逐字保留(分句只按标点切,不改写内容)
    assert sents[0].startswith("The cerebellum is known to project")
    assert "amygdala project to" in sents[1]


def test_split_sentences_handles_question_and_exclaim():
    sents = split_sentences("First sentence. Second question? Third!")
    assert sents == ["First sentence.", "Second question?", "Third!"]


def test_split_sentences_empty():
    assert split_sentences("") == []
    assert split_sentences("   ") == []


# ---- region_terms ----

def test_region_terms_name_and_aliases():
    terms = region_terms("Cerebellum", ["CB", "Cereb", "cerebellum"])
    assert terms == ["cerebellum", "cb", "cereb"]
    assert len(terms) == 3  # 去重(小写后)


def test_region_terms_skip_too_short():
    # 单字符被 MIN_TERM_LEN=2 过滤(防单字母误报);AB 保留
    assert region_terms("XA", ["a", "AB"]) == ["xa", "ab"]


# ---- find_support_sentence ----

def test_find_support_sentence_same_sentence():
    sup = find_support_sentence(
        ABSTRACT_HIT, region_terms("Amygdala", []),
        region_terms("Hippocampus", ["HIPP"]))
    assert sup is not None
    assert sup["sentence_index"] == 2
    assert sup["matched_source"] == "amygdala"
    assert sup["matched_target"] == "hippocampus"
    # evidence_text 必须为摘要原文片段
    assert sup["sentence"] in ABSTRACT_HIT


def test_find_support_sentence_alias_hit():
    sup = find_support_sentence(
        "Precuneus activity links SPL to attention networks.",
        region_terms("Precuneus", []), region_terms("Superior parietal", ["SPL"]))
    assert sup is not None
    assert sup["matched_target"] == "spl"
    assert sup["sentence_index"] == 1


def test_abbrev_word_boundary_required():
    """缩写必须独立成词:防 'cued' 命中 cu、'distinctive' 命中 st。"""
    # 'cu' 出现在 'cued' 内 → 不命中
    sup = find_support_sentence(
        "Subjects matched a feature, cued by a word, to a display.",
        region_terms("Precuneus", ["CU"]), region_terms("Superior parietal", ["SPL"]))
    assert sup is None
    # 'st' 出现在 'distinctive' 内 → 不命中
    sup = find_support_sentence(
        "The amygdala is a distinctive portion of the temporal lobe.",
        region_terms("Amygdala", []), region_terms("Superior temporal", ["ST"]))
    assert sup is None
    # 独立成词的缩写 → 命中
    sup = find_support_sentence(
        "The amygdala and ST were co-activated.",
        region_terms("Amygdala", []), region_terms("Superior temporal", ["ST"]))
    assert sup is not None
    assert sup["matched_target"] == "st"


def test_abbrev_requires_uppercase_in_original():
    """缩写必须原文大写独立成词:防代词 'it'/'It' 命中 'IT'。"""
    # 句首大写代词 'It' → 不命中(IT 是 Inferior temporal 缩写)
    sup = find_support_sentence(
        "It remains debated whether the amygdala projects to the cortex.",
        region_terms("Amygdala", []),
        region_terms("Inferior temporal", ["IT"]))
    assert sup is None
    # 小写代词 'it' → 不命中
    sup = find_support_sentence(
        "The amygdala projects to the cortex, and it was confirmed.",
        region_terms("Amygdala", []),
        region_terms("Inferior temporal", ["IT"]))
    assert sup is None
    # 论文书写的大写 'IT' → 命中
    sup = find_support_sentence(
        "The amygdala projects to IT and adjacent areas.",
        region_terms("Amygdala", []),
        region_terms("Inferior temporal", ["IT"]))
    assert sup is not None
    assert sup["matched_target"] == "it"


def test_find_support_sentence_none_when_no_hit():
    sup = find_support_sentence(
        ABSTRACT_NO_HIT, region_terms("Amygdala", []),
        region_terms("Hippocampus", []))
    assert sup is None


def test_find_support_sentence_none_when_single_region():
    # 只含一个 region → 不生成(需要同句双命中)
    sup = find_support_sentence(
        "Amygdala plays a role in fear conditioning.",
        region_terms("Amygdala", []), region_terms("Hippocampus", []))
    assert sup is None


def test_find_support_sentence_regions_in_adjacent_sentences_no_match():
    """跨句(相邻句各含一区)→ 不算明确支持句(保守)。"""
    ab = "Amygdala mediates fear. Hippocampus handles memory."
    sup = find_support_sentence(ab, region_terms("Amygdala", []),
                                region_terms("Hippocampus", []))
    assert sup is None


# ---- score_confidence ----

def _support(sentence, s="amygdala", t="hippocampus", s_pos=20, t_pos=50):
    return {"sentence": sentence, "sentence_index": 1,
            "matched_source": s, "matched_target": t,
            "source_pos": s_pos, "target_pos": t_pos}


def test_confidence_with_verb_and_direction():
    conf = score_confidence(_support(
        "the amygdala projects to the hippocampus"))
    assert conf == 0.90


def test_confidence_with_verb_no_direction():
    # target 在 source 前(如 'the hippocampus receives input from the amygdala')
    conf = score_confidence(_support(
        "the hippocampus receives input from the amygdala",
        s_pos=40, t_pos=15))
    assert conf == 0.85


def test_confidence_no_verb():
    # 无连接动词词干 → 基础 0.70
    conf = score_confidence(_support(
        "amygdala and hippocampus were examined in this study."))
    assert conf == 0.70


def test_confidence_activation_verb_counted():
    # 'activated' 命中 activ 词干(功能共激活语境)→ 0.90
    conf = score_confidence(_support(
        "amygdala and hippocampus were both activated"))
    assert conf == 0.90


def test_confidence_abbrev_downscale():
    conf = score_confidence(_support(
        "SPL and IPL are connected", s="spl", t="ipl"))
    assert conf == 0.60


# ---- build_segment / no_direct_evidence ----

def test_build_segment_extracted():
    seg = build_segment(PAPER, CONN, "9886046", "structural",
                        ABSTRACT_HIT, "Amygdala", "Hippocampus",
                        ["HIPP"], ["HIPP"])
    assert seg["status"] == STATUS_EXTRACTED
    assert seg["evidence_text"] in ABSTRACT_HIT  # 原文片段
    assert seg["evidence_location"] == "abstract:sentence:2"
    assert seg["extraction_method"] == EXTRACTION_METHOD
    assert seg["confidence"] == 0.90
    p = seg["provenance_json"]
    assert p["source"] == "paper_abstract"
    assert p["paper_id"] == PAPER
    assert p["pmid"] == "9886046"
    assert p["extraction_method"] == EXTRACTION_METHOD
    assert p["matched_terms"] == {"source": "amygdala",
                                  "target": "hippocampus"}
    assert p["sentence_index"] == 2


def test_build_segment_no_direct_evidence():
    seg = build_segment(PAPER, CONN, "16136173", "structural",
                        ABSTRACT_NO_HIT, "Amygdala", "Hippocampus",
                        [], [])
    assert seg["status"] == STATUS_NO_DIRECT_EVIDENCE
    assert seg["evidence_text"] is None  # 禁止生成不存在的原文
    assert seg["evidence_location"] is None
    assert seg["confidence"] is None
    assert seg["provenance_json"]["reason"] == "no_direct_evidence"


def test_build_segment_empty_abstract():
    seg = build_segment(PAPER, CONN, "1", "structural", None,
                        "Amygdala", "Hippocampus", [], [])
    assert seg["status"] == STATUS_NO_DIRECT_EVIDENCE
    assert seg["evidence_text"] is None


def test_build_provenance_no_evidence():
    p = build_provenance(PAPER, "16136173", "structural", None,
                         generated_at="2026-08-25T00:00:00Z")
    assert p["source"] == "paper_abstract"
    assert p["paper_id"] == PAPER
    assert p["pmid"] == "16136173"
    assert p["extraction_method"] == EXTRACTION_METHOD
    assert p["status"] == STATUS_NO_DIRECT_EVIDENCE
    assert "generated_at" in p


# ---- 幂等 SQL 形状 ----

def test_insert_sql_idempotent_shape():
    assert "ON CONFLICT (paper_id, connection_id) DO NOTHING" in INSERT_SEGMENT_SQL
    assert "RETURNING id" in INSERT_SEGMENT_SQL
