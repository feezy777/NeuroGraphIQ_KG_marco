"""Macro Evidence Literature Backfill V1 — 纯函数测试。

覆盖:文献线索解析(形态 A 作者(年份)/形态 B (作者, 年份)/et al./
& 连接/缩写全格式/多引用同句/去重排序)、姓氏提取、本地 paper 库构建、
作者+年份匹配(唯一/多篇/无)、A/B/C 分级、连接级扫描聚合(经 lineage
展开多 mirror)、统计报告(by_candidate / by_connection / distinct pairs)、
829 优先连接统计(有线索/可匹配/无法匹配)。
全部纯函数测试,无 DB、无写入。
"""

from app.services.macro_evidence_literature_service import (
    STATUS_MULTIPLE,
    STATUS_NO_CLUE,
    STATUS_UNIQUE,
    STATUS_UNMATCHED,
    build_local_paper_library,
    classify_match,
    extract_surnames,
    literature_match_report,
    match_citation,
    parse_citation,
    priority_literature_stats,
    scan_literature_candidates,
)


# ---- 1. 文献线索解析 ----

def test_parse_author_et_al_year():
    out = parse_citation("Goldman-Rakic et al. (1984); Cavada et al. (2000); DMN.")
    assert len(out) == 2
    assert out[0]["author"] == "Goldman-Rakic et al."
    assert out[0]["year"] == "1984"
    assert out[1]["author"] == "Cavada et al."
    assert out[0]["original_text"] == "Goldman-Rakic et al. (1984)"


def test_parse_paren_author_comma_year():
    out = parse_citation("fMRI shows coupling (Habas et al., 2009).")
    assert len(out) == 1
    assert out[0]["author"] == "Habas et al."
    assert out[0]["year"] == "2009"


def test_parse_ampersand_and_initials():
    out = parse_citation(
        "Petrides & Pandya (2002) describe connections; Mesulam, M.M. (1995) "
        "also described the cholinergic pathways.")
    assert len(out) == 2
    assert out[0]["author"] == "Mesulam, M.M." or out[1]["author"] == "Mesulam, M.M."
    authors = {c["author"] for c in out}
    assert "Petrides & Pandya" in authors
    assert "Mesulam, M.M." in authors


def test_parse_et_al_initials_combo():
    out = parse_citation("Selden, N.R., et al. (1998). Trajectories of cholinergic pathways.")
    assert len(out) == 1
    assert out[0]["author"] == "Selden, N.R., et al."
    assert out[0]["year"] == "1998"


def test_parse_multi_word_surname():
    out = parse_citation("uncinate fasciculus connects (Von Der Heide et al., 2013).")
    assert len(out) == 1
    assert out[0]["author"] == "Von Der Heide et al."
    assert out[0]["year"] == "2013"


def test_parse_multiple_in_one_paren_and_dedupe():
    t = "(Alexander et al., 1986; Parent & Hazrati, 1995) and Alexander et al. (1986)."
    out = parse_citation(t)
    assert len(out) == 3  # 括号内 2 条 + 括号外 1 条
    pairs = {(c["author"], c["year"]) for c in out}
    assert len(pairs) == 2  # Alexander 1986 两处 → 1 个不同 pair
    assert ("Alexander et al.", "1986") in pairs
    assert ("Parent & Hazrati", "1995") in pairs


def test_parse_none_and_empty():
    assert parse_citation(None) == []
    assert parse_citation("no citations here 1999") == []


def test_parse_suffix_years():
    out = parse_citation("studies (Smith et al., 2010a; Jones, 1995b)")
    assert len(out) == 2
    assert out[0]["year"] == "1995b" or out[1]["year"] == "1995b"
    assert any(c["year"] == "2010a" for c in out)


# ---- 2. 姓氏提取 ----

def test_extract_surnames():
    assert extract_surnames("Goldman-Rakic et al.") == ["goldman-rakic"]
    assert extract_surnames("Petrides & Pandya") == ["petrides", "pandya"]
    assert extract_surnames("Mesulam, M.M.") == ["mesulam"]
    assert extract_surnames("Von Der Heide et al.") == ["von", "der", "heide"]
    assert extract_surnames("Selemon LD, Goldman-Rakic PS.") == \
        ["selemon", "goldman-rakic"]


# ---- 3. 本地库构建与匹配 ----

def _paper(year, authors, doi="10.x/y", pmid="1", title="T"):
    return {"publication_year": year, "metadata_json": {"authors": authors},
            "doi": doi, "pmid": pmid, "title": title,
            "journal": "J", "source": "europepmc"}


def test_build_library_skips_missing_fields():
    lib = build_local_paper_library([
        _paper(1984, "Goldman-Rakic PS.", "10.1/a"),
        {"publication_year": None, "metadata_json": {"authors": "X Y."}},
        _paper(2009, "Habas C.", "10.2/b", pmid="2", title="H"),
    ])
    assert len(lib) == 2
    assert lib[0]["year"] == 1984
    assert "goldman-rakic" in lib[0]["surnames"]


def test_match_unique_and_multiple_and_none():
    lib = build_local_paper_library([
        _paper(1984, "Goldman-Rakic PS."),
        _paper(2009, "Margulies DS, Petrides M."),
        _paper(2009, "Habas C.", pmid="2"),
        _paper(2009, "Baumann O, Habas C.", pmid="3"),
    ])
    assert len(match_citation("Goldman-Rakic et al.", "1984", lib)) == 1
    assert len(match_citation("Petrides & Pandya", "2009", lib)) == 1
    assert len(match_citation("Habas et al.", "2009", lib)) == 2  # 两篇 Habas
    assert match_citation("Mesulam", "1995", lib) == []
    assert match_citation("", "1984", lib) == []


def test_classify_statuses():
    lib = build_local_paper_library([_paper(1984, "Goldman-Rakic PS.")])
    m1 = match_citation("Goldman-Rakic et al.", "1984", lib)
    status, ref = classify_match(m1)
    assert status == STATUS_UNIQUE and "doi=" in ref
    status2, _ = classify_match([])
    assert status2 == STATUS_UNMATCHED
    lib2 = build_local_paper_library([_paper(2009, "Habas C."),
                                      _paper(2009, "Baumann O, Habas C.")])
    m3 = match_citation("Habas et al.", "2009", lib2)
    assert classify_match(m3)[0] == STATUS_MULTIPLE


# ---- 4. 连接级扫描 ----

def _final(fid="f1", ccid="c1"):
    return {"id": fid, "canonical_connection_id": ccid, "connection_code": "ng:cn:" + fid}


def test_scan_across_lineage_and_dedupe():
    finals = [_final("f1", "c1"), _final("f2", "c2")]
    lineage_map = {"c1": [{"mirror_connection_ids": ["m1", "m2"]}],
                   "c2": [{"mirror_connection_ids": ["m3"]}]}
    mirror_map = {
        "m1": {"evidence_text": "connections (Habas et al., 2009)"},
        "m2": {"evidence_text": "connections (Habas et al., 2009); (Seeley et al., 2007)"},
        "m3": {"evidence_text": "no citation"},
    }
    lib = build_local_paper_library([_paper(2009, "Habas C.")])
    cs = scan_literature_candidates(finals, lineage_map, mirror_map, lib)
    f1_cs = [c for c in cs if c["connection_id"] == "f1"]
    assert len(f1_cs) == 2  # Habas 去重 + Seeley
    assert all(c["connection_id"] == "f1" for c in f1_cs)
    assert f1_cs[0]["author"] == "Habas et al."
    assert f1_cs[0]["match_status"] == STATUS_UNIQUE
    assert f1_cs[0]["possible_reference"].startswith("{doi=")
    assert not [c for c in cs if c["connection_id"] == "f2"]  # 无线索


def test_scan_connection_without_lineage():
    finals = [_final("f1", "cX")]
    cs = scan_literature_candidates(finals, {}, {}, [])
    assert cs == []


# ---- 5. 统计报告 ----

def test_literature_match_report():
    candidates = [
        {"connection_id": "f1", "author": "Habas et al.", "year": "2009",
         "match_status": STATUS_UNIQUE},
        {"connection_id": "f1", "author": "Mesulam", "year": "1995",
         "match_status": STATUS_UNMATCHED},
        {"connection_id": "f2", "author": "Habas et al.", "year": "2015",
         "match_status": STATUS_MULTIPLE},
    ]
    r = literature_match_report(candidates)
    assert r["by_candidate"] == {"total": 3, "A_unique": 1, "B_multiple": 1,
                                 "C_local_unmatched": 1}
    assert r["by_connection"]["with_citation_clue"] == 2
    assert r["by_connection"]["with_any_match"] == 2
    assert r["distinct_author_year_pairs"] == 3


def test_priority_stats():
    candidates = [
        {"connection_id": "p1", "author": "A", "year": "2000",
         "match_status": STATUS_UNIQUE},
        {"connection_id": "p2", "author": "B", "year": "2001",
         "match_status": STATUS_UNMATCHED},
        {"connection_id": "x1", "author": "C", "year": "2002",
         "match_status": STATUS_UNIQUE},  # 非优先
    ]
    s = priority_literature_stats(candidates, {"p1", "p2"}, total_priority=3)
    assert s["priority_total"] == 3
    assert s["with_citation_clue"] == 2
    assert s["no_citation_clue"] == 1
    assert s["matchable"] == 1
    assert s["matchable_unique"] == 1
    assert s["unmatchable"] == 2
