"""Macro Evidence Literature Promotion V1 测试。

覆盖(用户要求):追加不覆盖已有引用、DOI 去重、PMID 去重、citation hash
去重、authors 提取、幂等规划、before/after 覆盖率、duplicate 报告、
evidence_count 不变、DOI 无重复(连接内)。

全部纯函数 —— 不触碰数据库。
"""

from app.services.macro_evidence_literature_promotion_service import (
    build_after_finals,
    build_literature_reference,
    coverage_stats,
    extract_author_display,
    lit_dedup_key,
    plan_connection_promotion,
    plan_literature_merge,
    plan_literature_promotion,
)

CID = "11111111-1111-1111-1111-111111111111"

LLM_REF = {
    "source_type": "llm_extraction",
    "source_id": "a978512c-99ae-41a0-905b-9a0f8287af3f",
    "paper": "", "dataset": "Macro96 v1", "confidence": "0.1",
    "extraction_run": "same_granularity_connection_completion deepseek-v3",
    "mirror_connection_ids": ["m1", "m2"],
}


def _cand(**overrides) -> dict:
    base = {
        "connection_id": CID,
        "connection_code": "ng:cn:structural_a_to_b",
        "mirror_evidence_ids": ["ev-1", "ev-2"],
        "author_query": "Habas[Author]",
        "year": 2009,
        "matched_title": "Distinct cerebellar contributions to cognitive networks",
        "doi": "10.1523/jneurosci.1234-09.2009",
        "pmid": "19074045",
        "match_score": 0.9,
        "match_method": "pubmed_author_year",
        "status": "matched",
        "original_text": "(Habas et al., 2009)",
        "evidence_text_snippet": "Habas (2009) ...",
    }
    base.update(overrides)
    return base


# ---- extract_author_display ----

def test_extract_author_display_variants():
    assert extract_author_display("Mesulam, M.M. (1995)") == "Mesulam, M.M."
    assert extract_author_display("(Habas et al., 2009)") == "Habas et al."
    assert extract_author_display("Petrides & Pandya (2002)") == "Petrides & Pandya"
    assert extract_author_display("Haber & Knutson 2010") == "Haber & Knutson"
    assert extract_author_display("Von Der Heide et al. (2013)") == "Von Der Heide et al."
    assert extract_author_display("") == ""
    assert extract_author_display("Buckner (2013)") == "Buckner"


# ---- build_literature_reference ----

def test_build_literature_reference_full_fields():
    ref = build_literature_reference(_cand())
    # 用户指定字段全部存在
    for field in ("source_type", "doi", "pmid", "title", "authors", "journal",
                  "year", "evidence_source", "confidence",
                  "matched_connection_id"):
        assert field in ref, f"missing {field}"
    assert ref["source_type"] == "literature"
    assert ref["doi"] == "10.1523/jneurosci.1234-09.2009"
    assert ref["pmid"] == "19074045"
    assert ref["title"] == "Distinct cerebellar contributions to cognitive networks"
    assert ref["authors"] == "Habas et al."
    assert ref["year"] == "2009"
    assert ref["evidence_source"] == "pubmed_backfill_v1"
    assert ref["confidence"] == 0.9
    assert ref["matched_connection_id"] == CID
    # provenance
    assert ref["generation_method"] == "pubmed_backfill_v1"
    assert ref["source"] == "PubMed"
    assert ref["match_score"] == 0.9
    assert ref["match_method"] == "pubmed_author_year"
    assert ref["mirror_evidence_ids"] == ["ev-1", "ev-2"]


def test_build_literature_reference_missing_optional_fields():
    ref = build_literature_reference(_cand(doi="", pmid="", original_text=""))
    assert ref["doi"] == "" and ref["pmid"] == "" and ref["authors"] == ""
    assert lit_dedup_key(ref).startswith("hash:")  # 无 doi/pmid → hash 兜底


# ---- lit_dedup_key 优先级 DOI > PMID > hash ----

def test_dedup_key_doi_prefers_over_pmid():
    a = _cand(doi="10.1/x", pmid="999")
    b = _cand(doi="10.1/x", pmid="888")  # 同 DOI 不同 PMID
    assert lit_dedup_key(build_literature_reference(a)) == \
        lit_dedup_key(build_literature_reference(b))
    assert lit_dedup_key(build_literature_reference(a)).startswith("doi:")


def test_dedup_key_pmid_when_no_doi():
    a = build_literature_reference(_cand(doi="", pmid="12345"))
    b = build_literature_reference(_cand(doi="", pmid="12345", title="other"))
    assert lit_dedup_key(a) == lit_dedup_key(b)
    assert lit_dedup_key(a).startswith("pmid:")


def test_dedup_key_hash_fallback_requires_same_identity():
    a = build_literature_reference(_cand(doi="", pmid="",
                                         title="Same Paper", year=2009,
                                         original_text="(Author, 2009)"))
    b = build_literature_reference(_cand(doi="", pmid="",
                                         title="Same Paper", year=2009,
                                         original_text="(Author, 2009)"))
    c = build_literature_reference(_cand(doi="", pmid="",
                                         title="Other Paper", year=2010,
                                         original_text="(Author, 2010)"))
    assert lit_dedup_key(a) == lit_dedup_key(b)
    assert lit_dedup_key(a) != lit_dedup_key(c)
    assert lit_dedup_key(a).startswith("hash:")


# ---- merge:追加 + 去重 + 不覆盖 ----

def test_merge_appends_when_no_collision():
    verdict, merged = plan_literature_merge(
        [LLM_REF], build_literature_reference(_cand()))
    assert verdict == "append"
    assert len(merged) == 2
    assert merged[0] == LLM_REF  # 已有引用原样保留(未被覆盖)
    assert merged[1]["source_type"] == "literature"


def test_merge_duplicate_same_doi_skipped():
    existing = [build_literature_reference(_cand())]
    verdict, merged = plan_literature_merge(
        existing, build_literature_reference(_cand(pmid="different")))
    assert verdict == "duplicate"
    assert len(merged) == 1  # 同 DOI 跳过,不追加


def test_merge_duplicate_same_pmid_skipped():
    existing = [build_literature_reference(_cand(doi=""))]
    verdict, merged = plan_literature_merge(
        existing, build_literature_reference(_cand(doi="")))
    assert verdict == "duplicate"
    assert len(merged) == 1


def test_merge_duplicate_hash_skipped():
    existing = [build_literature_reference(_cand(doi="", pmid=""))]
    verdict, merged = plan_literature_merge(
        existing, build_literature_reference(_cand(doi="", pmid="")))
    assert verdict == "duplicate"
    assert len(merged) == 1


def test_merge_no_override_existing_reference():
    """已有 llm_extraction 引用 + 同 DOI 的 literature → 不覆盖、不追加。"""
    lit = build_literature_reference(_cand())
    ref_with_doi = dict(LLM_REF, doi=lit["doi"])  # 非 literature 也带同 DOI
    verdict, merged = plan_literature_merge([ref_with_doi], lit)
    assert verdict == "duplicate"
    assert merged == [ref_with_doi]


# ---- 连接级规划:多候选 ----

def test_connection_merge_distinct_papers_all_appended():
    c1 = _cand(doi="10.1/paper1", pmid="1")
    c2 = _cand(doi="10.2/paper2", pmid="2")
    p = plan_connection_promotion(CID, [LLM_REF], [c1, c2])
    assert len(p["appended"]) == 2
    assert len(p["duplicates"]) == 0
    assert p["before_count"] == 1
    assert p["after_count"] == 3
    assert p["merged_refs"][0] == LLM_REF


def test_connection_merge_same_paper_candidates_dedup():
    c1 = _cand(doi="10.1/x", pmid="1")
    c2 = _cand(doi="10.1/x", pmid="1", original_text="(Habas et al., 2009b)")
    p = plan_connection_promotion(CID, [], [c1, c2])
    assert len(p["appended"]) == 1  # 同论文只追加 1 次
    assert len(p["duplicates"]) == 1
    assert p["after_count"] == 1


def test_connection_merge_doi_pmid_cross_dedup():
    """同论文:一条候选有 DOI,另一条只有 PMID(同论文)→ 命中 DOI 键,判重。"""
    c1 = _cand(doi="10.1/x", pmid="1")
    c2 = _cand(doi="", pmid="1")
    p = plan_connection_promotion(CID, [], [c1, c2])
    assert len(p["appended"]) == 1
    assert len(p["duplicates"]) == 1


# ---- 全量规划 ----

def test_plan_literature_promotion_counts():
    finals = {CID: {"evidence_reference": [LLM_REF]},
              "22222222-2222-2222-2222-222222222222": {"evidence_reference": []}}
    by_conn = {CID: [_cand(), _cand(doi="10.2/y", pmid="2")],
               "22222222-2222-2222-2222-222222222222": [_cand(doi="10.3/z",
                                                              pmid="3")]}
    plan = plan_literature_promotion(finals, by_conn)
    assert plan["connections_planned"] == 2
    assert plan["candidates_total"] == 3
    assert plan["to_append"] == 3
    assert plan["duplicates"] == 0


def test_plan_idempotent_second_run_zero_append():
    """幂等:用第一次规划后的 merged_refs 作为已有引用再跑 → 0 追加。"""
    finals = {"22222222-2222-2222-2222-222222222222": {"evidence_reference": []}}
    by_conn = {"22222222-2222-2222-2222-222222222222": [_cand()]}
    plan1 = plan_literature_promotion(finals, by_conn)
    after = build_after_finals(finals, by_conn)
    plan2 = plan_literature_promotion(after, by_conn)
    assert plan1["to_append"] == 1
    assert plan2["to_append"] == 0
    assert plan2["duplicates"] == 1
    # 第二轮 merged 结果与第一轮完全一致
    assert plan2["plans"][0]["merged_refs"] == plan1["plans"][0]["merged_refs"]


# ---- 覆盖率统计 ----

def test_coverage_stats_before_after():
    before = {CID: {"evidence_reference": [LLM_REF]},
              "22222222-2222-2222-2222-222222222222": {"evidence_reference": []}}
    stat_before = coverage_stats(before)
    assert stat_before["total_connections"] == 2
    assert stat_before["with_literature_refs"] == 0
    assert stat_before["doi_covered_connections"] == 0

    by_conn = {CID: [_cand()],
               "22222222-2222-2222-2222-222222222222": [_cand(doi="10.3/z",
                                                              pmid="3")]}
    after = build_after_finals(before, by_conn)
    stat_after = coverage_stats(after)
    assert stat_after["with_literature_refs"] == 2
    assert stat_after["doi_covered_connections"] == 2
    assert stat_after["pmid_covered_connections"] == 2
    assert stat_after["literature_refs_total"] == 2
    assert stat_after["unique_dois"] == 2
    assert stat_after["unique_pmids"] == 2
    assert stat_after["doi_cover_rate"] == 1.0


def test_coverage_stats_same_doi_multiple_connections():
    """同论文支撑多连接合法:unique_dois 去重,连接数分别计数。"""
    f = {"1": {"evidence_reference": [_cand(doi="10.1/x", pmid="1")]},
         "2": {"evidence_reference": [_cand(doi="10.1/x", pmid="1")]}}
    s = coverage_stats(f)
    assert s["doi_covered_connections"] == 2
    assert s["unique_dois"] == 1  # 同一 DOI 不重复计数


# ---- 约束:连接内 DOI/PMID 无重复 ----

def test_no_duplicate_doi_within_connection():
    p = plan_connection_promotion(CID, [], [
        _cand(doi="10.1/x", pmid="1"), _cand(doi="10.1/x", pmid="2"),
        _cand(doi="10.2/y", pmid="3")])
    refs = p["merged_refs"]
    dois = [r["doi"] for r in refs if (r.get("doi") or "").strip()]
    assert len(dois) == len(set(dois))
    assert len(p["appended"]) == 2  # 10.1/x 去重一次 + 10.2/y


def test_no_duplicate_pmid_within_connection():
    p = plan_connection_promotion(CID, [], [
        _cand(doi="", pmid="123"), _cand(doi="", pmid="123"),
        _cand(doi="", pmid="456")])
    refs = p["merged_refs"]
    pmids = [r["pmid"] for r in refs if (r.get("pmid") or "").strip()]
    assert len(pmids) == len(set(pmids))
    assert len(p["appended"]) == 2


# ---- evidence_count 语义:mirror 证据数不受 literature 追加影响 ----

def test_evidence_count_semantics():
    """evidence_summary.supporting_records 是 mirror 证据计数,
    与 evidence_reference 元素数解耦 —— 追加 literature 不改变它。"""
    plan = plan_literature_promotion(
        {CID: {"evidence_reference": [LLM_REF]}},
        {CID: [_cand(), _cand(doi="10.2/y", pmid="2")]})
    before_refs = len(LLM_REF.get("mirror_connection_ids", []))
    after = plan["plans"][0]["merged_refs"]
    # mirror 溯源集合不变(仍只有原 llm 引用的 m1/m2)
    mirror_ids = {mid for r in after for mid in r.get("mirror_connection_ids", [])}
    assert mirror_ids == {"m1", "m2"}
    assert before_refs == 2
