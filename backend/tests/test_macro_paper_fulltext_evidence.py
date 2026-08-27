"""Macro Paper Full Text Evidence Extraction 测试(纯函数,不碰 DB)。

覆盖:JATS 解析(title/abstract/嵌套 sec title 传播/Figure caption/
跳过引用区)、正文证据抽取(同句双命中+连接词 0.90/0.85、相邻句 0.65、
无连接词不命中、缩写词边界)、build_fulltext_segment(extracted /
no_direct_evidence / 无 XML / XML 解析失败)、幂等 SQL 形状。
"""

from app.services.macro_paper_fulltext_evidence_service import (
    EXTRACTION_METHOD,
    INSERT_FULLTEXT_SEGMENT_SQL,
    SOURCE_TYPE_FULLTEXT,
    STATUS_EXTRACTED,
    STATUS_NO_DIRECT_EVIDENCE,
    build_fulltext_segment,
    find_fulltext_evidence,
    parse_jats_xml,
)

PAPER = "11111111-1111-1111-1111-111111111111"
CONN = "22222222-2222-2222-2222-222222222222"
PMID = "22917615"

# 基于真实 Europe PMC fullTextXML 结构的 JATS 夹具(嵌套 sec + 图注)
JATS = """<?xml version="1.0"?>
<article>
  <front>
    <article-meta>
      <title-group>
        <article-title>Projections from the amygdala to the hippocampus</article-title>
      </title-group>
      <abstract>
        <p>The amygdala projects to the hippocampus via the ventral pathway.</p>
      </abstract>
    </article-meta>
  </front>
  <body>
    <sec>
      <title>Introduction</title>
      <p>The amygdala sends dense projections to the hippocampus.</p>
      <sec>
        <title>Background</title>
        <p>Previous work established that the amygdala projects to the
           entorhinal cortex and hippocampus.</p>
      </sec>
    </sec>
    <sec>
      <title>Methods</title>
      <p>Tracer injections were placed in the amygdala.</p>
    </sec>
    <sec>
      <title>Results</title>
      <p>We observed strong connectivity between the amygdala and hippocampus.</p>
      <fig>
        <label>Figure 1</label>
        <caption><p>Schematic of amygdala to hippocampus projections.</p></caption>
      </fig>
    </sec>
  </body>
  <back>
    <ref-list>
      <ref><p>A citation, not body text.</p></ref>
    </ref-list>
  </back>
</article>"""


# ---- parse_jats_xml ----

def test_parse_title():
    parsed = parse_jats_xml(JATS)
    assert parsed["title"] == "Projections from the amygdala to the hippocampus"


def test_parse_abstract_section():
    parsed = parse_jats_xml(JATS)
    names = [s["name"] for s in parsed["sections"]]
    assert "Abstract" in names
    abs_sec = next(s for s in parsed["sections"] if s["name"] == "Abstract")
    assert abs_sec["paragraphs"] == [
        "The amygdala projects to the hippocampus via the ventral pathway."]


def test_parse_nested_sec_title_propagation():
    """嵌套 sec:内层段落归属内层 title,不继承外层。"""
    parsed = parse_jats_xml(JATS)
    names = [s["name"] for s in parsed["sections"]]
    assert "Introduction" in names and "Background" in names
    bg = next(s for s in parsed["sections"] if s["name"] == "Background")
    assert any("amygdala projects" in p for p in bg["paragraphs"])
    intro = next(s for s in parsed["sections"] if s["name"] == "Introduction")
    # 外层段落只含 'sends dense projections' 句(嵌套内层段落不重复归属外层)
    assert len(intro["paragraphs"]) == 1
    assert "dense projections" in intro["paragraphs"][0]


def test_parse_figure_caption_section():
    parsed = parse_jats_xml(JATS)
    fig = next(s for s in parsed["sections"] if s["name"] == "Figure 1")
    assert fig["paragraphs"] == [
        "Schematic of amygdala to hippocampus projections."]


def test_parse_skips_reference_list():
    parsed = parse_jats_xml(JATS)
    all_text = " ".join(p for s in parsed["sections"]
                        for p in s["paragraphs"])
    assert "citation" not in all_text
    assert "A citation, not body text." not in all_text


def test_parse_inline_markup_text_joined():
    xml = ("<article><body><sec><title>Results</title><p>The "
           "<bold>amygdala</bold> projects to the <italic>hippocampus</italic>."
           "</p></sec></body></article>")
    parsed = parse_jats_xml(xml)
    results = next(s for s in parsed["sections"]
                   if s["name"] == "Results")
    assert results["paragraphs"] == [
        "The amygdala projects to the hippocampus."]


# ---- find_fulltext_evidence ----

def _terms():
    return ["amygdala"], ["hippocampus"]


def test_find_same_sentence_with_direction():
    """同句双命中 + 连接词 + source 在 target 前 → 0.90。"""
    match = find_fulltext_evidence(parse_jats_xml(JATS)["sections"],
                                   *_terms())
    assert match is not None
    assert match["confidence"] == 0.90
    assert match["matched_source"] == "amygdala"
    assert match["matched_target"] == "hippocampus"
    # 原文真实文本(逐字保留)
    assert match["sentence"] == ("The amygdala projects to the hippocampus "
                                 "via the ventral pathway.")
    assert match["section_name"] == "Abstract"


def test_find_same_sentence_reverse_direction():
    """target 在 source 前(接收句式)→ 0.85(无方向支持)。"""
    xml = ("<article><body><sec><title>Results</title><p>The hippocampus "
           "receives input from the amygdala.</p></sec></body></article>")
    match = find_fulltext_evidence(parse_jats_xml(xml)["sections"], *_terms())
    assert match is not None
    assert match["confidence"] == 0.85


def test_find_no_connect_word_not_hit():
    """同句双命中但无连接语义词 → 不命中(正文严格规则)。"""
    xml = ("<article><body><sec><title>Results</title><p>Amygdala and "
           "hippocampus were examined in this study.</p></sec>"
           "</body></article>")
    match = find_fulltext_evidence(parse_jats_xml(xml)["sections"], *_terms())
    assert match is None


def test_find_adjacent_sentences_weak_hit():
    """相邻句(±1)各含一端 + 连接词 → 0.65。"""
    xml = ("<article><body><sec><title>Results</title>"
           "<p>The amygdala projects densely to the cortex. "
           "A weaker pathway reaches the hippocampus.</p>"
           "</sec></body></article>")
    match = find_fulltext_evidence(parse_jats_xml(xml)["sections"], *_terms())
    assert match is not None
    assert match["confidence"] == 0.65
    assert match["matched_source"] == "amygdala"
    assert match["matched_target"] == "hippocampus"


def test_find_adjacent_sentences_no_connect_word_not_hit():
    xml = ("<article><body><sec><title>Results</title>"
           "<p>The amygdala shows strong activation. "
           "The hippocampus is nearby.</p>"
           "</sec></body></article>")
    match = find_fulltext_evidence(parse_jats_xml(xml)["sections"], *_terms())
    assert match is None


def test_find_abbrev_word_boundary_required():
    """正文同样防缩写子串误报('distinctive' 不命中 'st')。"""
    xml = ("<article><body><sec><title>Results</title>"
           "<p>The amygdala is a distinctive portion of the temporal lobe."
           "</p></sec></body></article>")
    match = find_fulltext_evidence(
        parse_jats_xml(xml)["sections"],
        ["amygdala"], ["st"])  # 'st' 出现在 'distinctive' 内 → 不命中
    assert match is None
    xml2 = ("<article><body><sec><title>Results</title>"
            "<p>The amygdala and ST were co-activated.</p>"
            "</sec></body></article>")
    match = find_fulltext_evidence(
        parse_jats_xml(xml2)["sections"], ["amygdala"], ["st"])
    assert match is not None
    assert match["matched_target"] == "st"


def test_find_best_confidence_wins_across_sections():
    """高分命中压过低分命中(跨章节)。"""
    xml = ("<article><body>"
           "<sec><title>Methods</title>"
           "<p>The amygdala projects densely. "
           "A weaker pathway reaches the hippocampus.</p></sec>"
           "<sec><title>Results</title>"
           "<p>The amygdala projects to the hippocampus directly.</p></sec>"
           "</body></article>")
    match = find_fulltext_evidence(parse_jats_xml(xml)["sections"], *_terms())
    assert match["confidence"] == 0.90
    assert match["section_name"] == "Results"


def test_find_empty_sections_none():
    assert find_fulltext_evidence([], *_terms()) is None


# ---- build_fulltext_segment ----

def test_build_fulltext_segment_extracted():
    seg = build_fulltext_segment(PAPER, CONN, PMID, "structural", JATS,
                                 "Amygdala", "Hippocampus", ["AMY"], ["HIPP"])
    assert seg["status"] == STATUS_EXTRACTED
    assert seg["evidence_source_type"] == SOURCE_TYPE_FULLTEXT
    assert seg["source_type"] == SOURCE_TYPE_FULLTEXT
    assert seg["section_name"] == "Abstract"
    assert seg["confidence"] == 0.90
    # 原文真实文本 + 可追溯位置
    assert seg["evidence_text"] == ("The amygdala projects to the "
                                    "hippocampus via the ventral pathway.")
    assert seg["evidence_location"] == \
        "fulltext:Abstract:paragraph:1:sentence:1"
    assert seg["extraction_method"] == EXTRACTION_METHOD
    assert seg["matched_regions"] == {"source": "amygdala",
                                      "target": "hippocampus"}
    p = seg["provenance_json"]
    assert p["source"] == "paper_fulltext"
    assert p["paper_id"] == PAPER
    assert p["pmid"] == PMID
    assert p["status"] == STATUS_EXTRACTED
    assert p["section_name"] == "Abstract"
    assert p["matched_terms"] == {"source": "amygdala",
                                  "target": "hippocampus"}


def test_build_fulltext_segment_no_direct_evidence():
    xml = ("<article><body><sec><title>Results</title>"
           "<p>No mention of either region here.</p></sec></body></article>")
    seg = build_fulltext_segment(PAPER, CONN, PMID, "structural", xml,
                                 "Amygdala", "Hippocampus", [], [])
    assert seg["status"] == STATUS_NO_DIRECT_EVIDENCE
    assert seg["evidence_text"] is None  # 禁止生成不存在的原文
    assert seg["section_name"] is None
    assert seg["confidence"] is None
    assert seg["evidence_source_type"] == SOURCE_TYPE_FULLTEXT
    assert seg["provenance_json"]["reason"] == "no_direct_evidence"


def test_build_fulltext_segment_no_xml():
    seg = build_fulltext_segment(PAPER, CONN, PMID, "structural", None,
                                 "Amygdala", "Hippocampus", [], [])
    assert seg["status"] == STATUS_NO_DIRECT_EVIDENCE
    assert seg["evidence_text"] is None
    assert seg["provenance_json"]["reason"] == "no_fulltext_xml"


def test_build_fulltext_segment_xml_parse_error():
    seg = build_fulltext_segment(PAPER, CONN, PMID, "structural",
                                 "<article><body>",  # 未闭合 → 解析失败
                                 "Amygdala", "Hippocampus", [], [])
    assert seg["status"] == STATUS_NO_DIRECT_EVIDENCE
    assert seg["evidence_text"] is None
    assert seg["provenance_json"]["reason"] == "xml_parse_error"


# ---- 幂等 SQL 形状 ----

def test_insert_fulltext_sql_idempotent_shape():
    assert ("ON CONFLICT (paper_id, connection_id, evidence_source_type) "
            "DO NOTHING") in INSERT_FULLTEXT_SEGMENT_SQL
    assert "RETURNING id" in INSERT_FULLTEXT_SEGMENT_SQL
    assert "evidence_source_type" in INSERT_FULLTEXT_SEGMENT_SQL
    assert "section_name" in INSERT_FULLTEXT_SEGMENT_SQL
