"""Macro Candidate Connection Ranking V1 测试(纯函数,不碰 DB)。

覆盖用户要求 6 项:
1. 同一 region pair 多论文评分提升(指数)
2. same_sentence 优先于 same_paper
3. fulltext 权重大于 title
4. 关键词增强有效
5. ranking 幂等运行(INSERT ON CONFLICT DO NOTHING)
6. 所有 ranking 均有完整 provenance(ranking→candidate_pair→segment→paper)

扩展:优先级 A/B/C 判定、指数饱和帽、短语关键词、无向对排序聚合。
"""

from app.services.macro_candidate_connection_ranking_service import (
    ASSERTION_TYPE,
    GENERATION_METHOD,
    INSERT_RANKING_SQL,
    SOURCE_TYPE,
    build_ranking_row,
    detect_keywords,
    keyword_bonus,
    link_evidence_segments,
    paper_support_score,
    rank_priority,
)

A = "11111111-1111-1111-1111-111111111111"  # Amygdala
H = "22222222-2222-2222-2222-222222222222"  # Hippocampus
T = "33333333-3333-3333-3333-333333333333"  # Inferior temporal
P1 = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
P2 = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"

PAIR_ID_1 = "c1111111-1111-1111-1111-111111111111"
PAIR_ID_2 = "c2222222-2222-2222-2222-222222222222"
SEG_ID_1 = "e1111111-1111-1111-1111-111111111111"
SEG_ID_2 = "e2222222-2222-2222-2222-222222222222"

SENT_FULLTEXT = "The amygdala sends a dense projection to the hippocampus."
SENT_ABSTRACT = "Amygdala–hippocampus connectivity was examined."
SENT_TITLE = "Amygdala and hippocampus volumes"

SEGMENTS = [
    {"id": SEG_ID_1, "paper_id": P1, "sentence_text": SENT_FULLTEXT,
     "source_type": "paper_fulltext"},
    {"id": SEG_ID_2, "paper_id": P2, "sentence_text": SENT_ABSTRACT,
     "source_type": "paper_abstract"},
]

SEG_MAP = link_evidence_segments([], SEGMENTS)


def _row(paper_id, evidence_sentence, cooccurrence, row_id=PAIR_ID_1):
    return {"id": row_id, "paper_id": paper_id,
            "evidence_sentence": evidence_sentence,
            "cooccurrence": cooccurrence}


def _rank(rows, seg_map=SEG_MAP, pmid_map=None):
    return build_ranking_row(A, H, rows, seg_map, pmid_map)


# ---- 1. 同一 region pair 多论文评分提升 ----

def test_paper_support_exponential():
    assert paper_support_score(1) == 1.0
    assert paper_support_score(2) == 2.0
    assert paper_support_score(3) == 4.0
    assert paper_support_score(4) == 8.0


def test_multi_paper_score_increases():
    """2 篇论文评分 > 1 篇(指数提升),paper_count 记录。"""
    one = _rank([_row(P1, SENT_FULLTEXT, "same_sentence")])
    two = _rank([_row(P1, SENT_FULLTEXT, "same_sentence", PAIR_ID_1),
                 _row(P2, SENT_ABSTRACT, "same_section", PAIR_ID_2)])
    assert one["paper_count"] == 1
    assert two["paper_count"] == 2
    assert two["evidence_count"] == 2
    assert two["score"] > one["score"]


def test_paper_support_saturation():
    """≥6 篇饱和 2^5=32,长尾不爆炸。"""
    assert paper_support_score(6) == 32.0
    assert paper_support_score(104) == 32.0


# ---- 2. same_sentence 优先于 same_paper ----

def test_same_sentence_beats_same_paper():
    rows = [_row(P1, SENT_FULLTEXT, "same_sentence"),
            _row(P2, SENT_ABSTRACT, "same_paper")]
    rank = _rank(rows)
    assert rank["ranking_reason"]["proximity_score"] == 1.0
    assert rank["ranking_reason"]["has_same_sentence"] is True
    rows_paper = [_row(P1, SENT_FULLTEXT, "same_paper")]
    rank_paper = _rank(rows_paper)
    assert rank_paper["ranking_reason"]["proximity_score"] == 0.4
    assert rank["score"] > rank_paper["score"]


# ---- 3. fulltext 权重大于 title ----

def test_fulltext_beats_title():
    """fulltext 1.0 > title 0.5;title 源(无 segment)记 source_type=title。"""
    rows_ft = [_row(P1, SENT_FULLTEXT, "same_sentence")]  # 有 segment → fulltext
    rows_title = [_row(P1, SENT_TITLE, "same_sentence")]  # 无 segment → title
    rank_ft = _rank(rows_ft)
    rank_title = _rank(rows_title, seg_map={})
    assert rank_ft["ranking_reason"]["evidence_source_score"] == 1.0
    assert rank_title["ranking_reason"]["evidence_source_score"] == 0.5
    assert rank_title["provenance_json"]["paper_entries"][0]["source_type"] == "title"
    assert rank_title["provenance_json"]["paper_entries"][0]["evidence_segment_id"] is None
    assert rank_ft["score"] > rank_title["score"]


# ---- 4. 关键词增强有效 ----

def test_keyword_enhancement():
    kw_yes = _rank([_row(P1, SENT_FULLTEXT, "same_sentence")])
    kw_no = _rank([_row(P1, "The amygdala and hippocampus were examined.",
                        "same_sentence")])
    assert kw_yes["ranking_reason"]["keyword_hits"] == ["projection"]
    assert kw_yes["ranking_reason"]["keyword_bonus"] == 0.1
    assert kw_no["ranking_reason"]["keyword_hits"] == []
    assert kw_no["ranking_reason"]["keyword_bonus"] == 0.0
    assert kw_yes["score"] > kw_no["score"]


def test_keyword_phrase_and_word_boundary():
    hits = detect_keywords("Functional connectivity of the amygdala was high.")
    assert "functional connectivity" in hits and "connectivity" in hits
    # 词边界:connectivity 不触发 connect
    hits2 = detect_keywords("The pathway connects the two regions.")
    assert "pathway" in hits2
    assert "connect" not in hits2  # 'connects' ≠ 'connect' 词边界
    # 'connect' 单独命中
    hits3 = detect_keywords("These areas connect via a tract.")
    assert "connect" in hits3 and "tract" in hits3


def test_keyword_bonus_capped():
    """命中数 >5 → 加成封顶 0.5。"""
    text = ("projection projects connect connectivity connected "
            "tract fiber pathway bundle")
    hits = detect_keywords(text)
    assert len(hits) >= 6
    assert keyword_bonus(hits) == 0.5


# ---- 5. ranking 幂等运行 ----

def test_ranking_insert_idempotent_sql():
    assert "ON CONFLICT (source_region_id, target_region_id)" in INSERT_RANKING_SQL
    assert "DO NOTHING" in INSERT_RANKING_SQL
    assert "DELETE" not in INSERT_RANKING_SQL
    assert "UPDATE" not in INSERT_RANKING_SQL
    # generation_method 列存在(bind 参数形式,值由参数传入)
    assert "generation_method" in INSERT_RANKING_SQL


def test_ranking_deterministic():
    rows = [_row(P1, SENT_FULLTEXT, "same_sentence", PAIR_ID_1),
            _row(P2, SENT_ABSTRACT, "same_section", PAIR_ID_2)]
    r1 = _rank(rows)
    r2 = _rank(rows)
    assert r1 == r2


# ---- 6. 所有 ranking 均有完整 provenance ----

def test_ranking_full_provenance_chain():
    rows = [_row(P1, SENT_FULLTEXT, "same_sentence", PAIR_ID_1),
            _row(P2, SENT_ABSTRACT, "same_section", PAIR_ID_2)]
    rank = _rank(rows, pmid_map={P1: 1001, P2: 1002})
    prov = rank["provenance_json"]
    assert prov["trace_chain"] == ["ranking", "candidate_pair",
                                   "evidence_segment", "paper_source"]
    assert prov["source_table"] == "paper_region_pair_candidates"
    entries = prov["paper_entries"]
    assert len(entries) == 2
    for entry, seg_id, source in zip(entries, [SEG_ID_1, SEG_ID_2],
                                     ["paper_fulltext", "paper_abstract"]):
        assert entry["candidate_pair_id"] in (PAIR_ID_1, PAIR_ID_2)
        assert entry["evidence_segment_id"] == seg_id
        assert entry["source_type"] == source
        assert entry["cooccurrence"] in ("same_sentence", "same_section")
    assert entries[0]["pmid"] == 1001
    # candidate_pair_ids 与 entries 一一对应
    assert set(rank["candidate_pair_ids"]) == {PAIR_ID_1, PAIR_ID_2}


def test_ranking_assertion_constraints():
    rank = _rank([_row(P1, SENT_FULLTEXT, "same_sentence")])
    assert rank["assertion_type"] == ASSERTION_TYPE == "candidate"
    assert rank["source_type"] == SOURCE_TYPE == "literature"
    assert rank["generation_method"] == GENERATION_METHOD


# ---- 扩展:优先级 A/B/C 判定 ----

def test_priority_levels():
    # A: ≥2 篇 + same_sentence + 关键词
    rows_a = [_row(P1, SENT_FULLTEXT, "same_sentence", PAIR_ID_1),
              _row(P2, SENT_ABSTRACT, "same_sentence", PAIR_ID_2)]
    assert _rank(rows_a)["priority_level"] == "A"
    # B: 多篇但无 same_sentence
    rows_b = [_row(P1, SENT_FULLTEXT, "same_paper", PAIR_ID_1),
              _row(P2, SENT_ABSTRACT, "same_paper", PAIR_ID_2)]
    assert _rank(rows_b)["priority_level"] == "B"
    # C: 单篇 + 无 same_sentence + 无关键词
    rows_c = [_row(P1, "The amygdala and hippocampus were examined.",
                   "same_paper")]
    assert _rank(rows_c)["priority_level"] == "C"
    # 纯函数等价断言
    assert rank_priority(2, True, True) == "A"
    assert rank_priority(1, True, True) == "B"   # 单篇有 same_sentence
    assert rank_priority(1, False, False) == "C"
    assert rank_priority(3, False, False) == "B"  # 多篇但无证据质量
