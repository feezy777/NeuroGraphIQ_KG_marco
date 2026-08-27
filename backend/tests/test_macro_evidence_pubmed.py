"""Macro Evidence Literature PubMed Backfill V1 — 纯函数测试。

覆盖:author_query 构造(单/多作者/缩写/多词姓氏)、region keywords 提取、
PubMed 结果分级(1 篇→matched / region 消歧 / title 相似度消歧 /
多篇→ambiguous / 0 篇→not_found)、L1 本地库匹配、候选构建
(mirror_evidence_ids 定位/lineage 完整)、DOI/PMID 唯一性、幂等运行、
match_summary 报告。PubMed lookup 全部 mock,无网络。
"""

from app.services.macro_evidence_pubmed_service import (
    METHOD_LOCAL,
    METHOD_NOT_FOUND,
    METHOD_PUBMED_AY,
    METHOD_PUBMED_AY_REGION,
    METHOD_PUBMED_TITLE,
    STATUS_AMBIGUOUS,
    STATUS_MATCHED,
    STATUS_NOT_FOUND,
    build_author_query,
    build_pubmed_candidates,
    build_year_query,
    classify_pubmed_hits,
    full_query,
    match_summary,
    region_keywords,
    similarity,
    split_by_status,
    title_hint_from_text,
)
from app.services.macro_evidence_literature_service import (
    build_local_paper_library,
)


# ---- 1. 查询构造 ----

def test_build_author_query():
    assert build_author_query("Habas et al.") == "Habas[Author]"
    assert build_author_query("Petrides & Pandya") == \
        "(Petrides[Author] AND Pandya[Author])"
    assert build_author_query("Mesulam, M.M.") == "Mesulam[Author]"
    assert build_author_query("Von Der Heide et al.") == "Von Der Heide[Author]"
    assert build_author_query("") == ""


def test_build_year_query():
    assert build_year_query("2009") == "2009[Date - Publication]"
    assert build_year_query("2010a") == "2010[Date - Publication]"
    assert build_year_query("") == ""


def test_full_query():
    q = full_query("Habas et al.", "2009", ["prefrontal"])
    assert q == "(Habas[Author]) AND 2009[Date - Publication] AND prefrontal"
    assert full_query("", "2009", []) == ""


def test_region_keywords():
    assert region_keywords("ng:cn:structural_lateral_orbitofrontal_to_"
                           "superior_parietal") == \
        ["lateral_orbitofrontal", "superior_parietal"]
    assert region_keywords("") == []
    assert region_keywords("ng:cn:functional_x_to_y") == ["x_y"]


def test_title_hint_from_text():
    t = title_hint_from_text("Mesulam, M.M. (1995). Topographic organization"
                             " of cholinergic pathways. J Comp Neurol.",
                             "Mesulam", "1995")
    assert "cholinergic" in t
    assert title_hint_from_text("(Habas et al., 2009)", "Habas", "2009") == ""


def test_similarity():
    assert similarity("", "x") == 0.0
    assert similarity("A B C", "A B C") == 1.0
    assert similarity("A B", "A C D") == 0.25  # Jaccard: 1/4


# ---- 2. PubMed 结果分级 ----

def _hit(pmid="1", title="T", doi="10.x/y"):
    return {"pmid": pmid, "title": title, "doi": doi}


def test_classify_single_hit_matched():
    status, chosen, score, method = classify_pubmed_hits(
        [_hit("1", "Prefrontal cortex")], [], "")
    assert status == STATUS_MATCHED
    assert chosen["pmid"] == "1"
    assert score == 0.9
    assert method == METHOD_PUBMED_AY


def test_classify_region_disambiguation():
    hits = [_hit("1", "Some other paper"),
            _hit("2", "Prefrontal cortex connectivity in monkeys")]
    status, chosen, score, method = classify_pubmed_hits(
        hits, ["prefrontal"], "")
    assert status == STATUS_MATCHED
    assert chosen["pmid"] == "2"
    assert score == 0.8
    assert method == METHOD_PUBMED_AY_REGION


def test_classify_region_ambiguous_if_no_unique_top():
    hits = [_hit("1", "Prefrontal cortex A"),
            _hit("2", "Prefrontal cortex B")]
    status, _, score, _m = classify_pubmed_hits(hits, ["prefrontal"], "")
    assert status == STATUS_AMBIGUOUS
    assert score == 0.5


def test_classify_title_similarity():
    hits = [_hit("1", "Unrelated study of neurons"),
            _hit("2", "Topographic organization of cholinergic pathways")]
    status, chosen, score, method = classify_pubmed_hits(
        hits, [], "Topographic organization of cholinergic pathways")
    assert status == STATUS_MATCHED
    assert chosen["pmid"] == "2"
    assert method == METHOD_PUBMED_TITLE


def test_classify_no_hits():
    status, chosen, score, method = classify_pubmed_hits([], [], "")
    assert status == STATUS_NOT_FOUND
    assert chosen is None
    assert method == METHOD_NOT_FOUND


def test_classify_multiple_no_disambiguation():
    status, _, _, _ = classify_pubmed_hits(
        [_hit("1", "A"), _hit("2", "B")], [], "")
    assert status == STATUS_AMBIGUOUS


# ---- 3. 候选构建(全流程 + 本地 L1) ----

def _lit(cid="f1", ccid="c1", code="ng:cn:structural_x_to_y",
         author="Habas et al.", year="2009", text="(Habas et al., 2009)"):
    return {"connection_id": cid, "canonical_connection_id": ccid,
            "connection_code": code, "author": author, "year": year,
            "original_text": text, "evidence_text_snippet": text,
            "match_status": "C_local_unmatched"}


def _lineage_map():
    return {"c1": [{"mirror_connection_ids": ["m1", "m2"]}]}


def _mirror_map():
    return {"m1": {"evidence_text": "connections (Habas et al., 2009)."},
            "m2": {"evidence_text": "unrelated text"}}


def test_candidate_local_unique_match():
    lib = build_local_paper_library(
        [{"publication_year": 2009, "metadata_json": {"authors": "Habas C."},
          "doi": "10.9/h", "pmid": "9", "title": "H", "journal": "J",
          "source": "europepmc"}])
    cs = build_pubmed_candidates([_lit()], _lineage_map(), _mirror_map(),
                                 lib, lambda q: [], do_pubmed=True)
    assert len(cs) == 1
    c = cs[0]
    assert c["status"] == STATUS_MATCHED
    assert c["match_method"] == METHOD_LOCAL
    assert c["doi"] == "10.9/h"
    assert c["pmid"] == "9"
    assert c["match_score"] == 1.0


def test_candidate_mirror_evidence_located():
    cs = build_pubmed_candidates([_lit()], _lineage_map(), _mirror_map(),
                                 [], lambda q: [], do_pubmed=False)
    assert cs[0]["mirror_evidence_ids"] == ["m1"]  # 仅含 original_text 的 text


def test_candidate_pubmed_matched_and_lineage_complete():
    def lookup(q):
        return [_hit("12345", "Prefrontal connectivity", "10.p/1")]
    cs = build_pubmed_candidates([_lit()], _lineage_map(), _mirror_map(),
                                 [], lookup, do_pubmed=True)
    assert cs[0]["status"] == STATUS_MATCHED
    assert cs[0]["doi"] == "10.p/1"
    assert cs[0]["pmid"] == "12345"
    assert cs[0]["match_method"] == METHOD_PUBMED_AY
    # lineage 完整:mirror_evidence_ids 均来自 lineage 展开
    lineage_ids = {"m1", "m2"}
    assert set(cs[0]["mirror_evidence_ids"]) <= lineage_ids


def test_candidate_ambiguous_and_not_found():
    def lookup_multi(q):
        return [_hit("1", "A"), _hit("2", "B")]
    cs = build_pubmed_candidates([_lit()], _lineage_map(), _mirror_map(),
                                 [], lookup_multi, do_pubmed=True)
    assert cs[0]["status"] == STATUS_AMBIGUOUS
    assert cs[0]["match_score"] == 0.5

    cs2 = build_pubmed_candidates([_lit()], _lineage_map(), _mirror_map(),
                                  [], lambda q: [], do_pubmed=True)
    assert cs2[0]["status"] == STATUS_NOT_FOUND


def test_candidate_dedup_same_author_year_in_connection():
    lits = [_lit(text="(Habas et al., 2009)"),
            _lit(text="(Habas et al., 2009) elsewhere")]
    cs = build_pubmed_candidates(lits, _lineage_map(), _mirror_map(),
                                 [], lambda q: [], do_pubmed=False)
    assert len(cs) == 1  # (connection_id, author_query|year) 去重


def test_candidate_skips_a_unique():
    a = _lit()
    a["match_status"] = "A_unique"
    cs = build_pubmed_candidates([a], _lineage_map(), _mirror_map(),
                                 [], lambda q: [], do_pubmed=False)
    assert cs == []


# ---- 4. DOI/PMID 唯一 + 幂等 + 报告 ----

def test_doi_pmid_uniqueness_across_candidates():
    lib = build_local_paper_library(
        [{"publication_year": 2009, "metadata_json": {"authors": "Habas C."},
          "doi": "10.9/h", "pmid": "9", "title": "H", "journal": "J",
          "source": "europepmc"}])
    lits = [_lit(cid="f1", ccid="c1", text="(Habas et al., 2009)"),
            _lit(cid="f2", ccid="c2", code="ng:cn:structural_z_to_w",
                 text="(Habas et al., 2009)")]
    lm = _lineage_map()
    lm["c2"] = [{"mirror_connection_ids": ["m3"]}]
    mm = _mirror_map()
    mm["m3"] = {"evidence_text": "(Habas et al., 2009)"}
    cs = build_pubmed_candidates(lits, lm, mm, lib, lambda q: [],
                                 do_pubmed=True)
    s = match_summary(cs)
    # 同一论文支撑两条连接 → doi 相同合法,但无冲突(同 doi 同 pmid)
    assert s["doi_pmid_uniqueness"]["no_doi_conflict"] is True
    assert s["doi_pmid_uniqueness"]["no_pmid_conflict"] is True
    assert s["doi_pmid_uniqueness"]["doi_conflict_count"] == 0
    assert s["doi_pmid_uniqueness"]["pmid_conflict_count"] == 0


def test_idempotent_same_input_same_output():
    lits = [_lit(), _lit(author="Seeley et al.", year="2007",
                         text="(Seeley et al., 2007)")]
    lm = _lineage_map()
    mm = _mirror_map()
    mm["m1"] = {"evidence_text": "(Seeley et al., 2007)"}
    mm["m2"] = {"evidence_text": "x"}
    cs1 = build_pubmed_candidates(lits, lm, mm, [], lambda q: [], do_pubmed=False)
    cs2 = build_pubmed_candidates(lits, lm, mm, [], lambda q: [], do_pubmed=False)
    assert cs1 == cs2


def test_match_summary_report():
    lib = build_local_paper_library(
        [{"publication_year": 2009, "metadata_json": {"authors": "Habas C."},
          "doi": "10.9/h", "pmid": "9", "title": "H", "journal": "J",
          "source": "europepmc"}])
    lits = [
        _lit(cid="f1", ccid="c1", text="(Habas et al., 2009)"),  # local matched
        _lit(cid="f2", ccid="c2", code="ng:cn:structural_z_to_w",
             author="Seeley et al.", year="2007",
             text="(Seeley et al., 2007)"),                       # pubmed not_found
        _lit(cid="f3", ccid="c3", code="ng:cn:structural_z_to_w",
             author="Uddin", year="2015", text="(Uddin, 2015)"),  # pubmed matched
    ]
    lm = {"c1": [{"mirror_connection_ids": ["m1"]}],
          "c2": [{"mirror_connection_ids": ["m2"]}],
          "c3": [{"mirror_connection_ids": ["m3"]}]}
    mm = {"m1": {"evidence_text": "(Habas et al., 2009)"},
          "m2": {"evidence_text": "(Seeley et al., 2007)"},
          "m3": {"evidence_text": "(Uddin, 2015)"}}
    def lookup(q):
        if "Uddin" in q:
            return [_hit("555", "Uddin paper", "10.u/5")]
        return []
    cs = build_pubmed_candidates(lits, lm, mm, lib, lookup, do_pubmed=True)
    s = match_summary(cs)
    assert s["candidate_total"] == 3
    assert s["by_status"] == {STATUS_MATCHED: 2, STATUS_NOT_FOUND: 1}
    assert s["by_connection"]["matched"] == 2
    assert s["by_connection"]["not_found"] == 1
    assert s["doi_pmid_uniqueness"]["no_doi_conflict"] is True
    assert s["doi_pmid_uniqueness"]["no_pmid_conflict"] is True
    groups = split_by_status(cs)
    assert len(groups["matched"]) == 2
    assert len(groups["not_found"]) == 1
    assert len(groups["ambiguous"]) == 0
