"""Macro Evidence Lineage Recovery V1 — 纯函数测试。

覆盖:evidence_record 恢复(A doi+pmid / B 仅 citation_json / 空→None)、
evidence_text 恢复(C 作者+年份+本地唯一匹配 / 无匹配→空)、
Evidence merge 去重(doi > pmid > citation_hash > title+year,同论文合并
mirror_evidence_ids)、lineage 完整性(无 lineage / 无证据)、
全量规划统计、幂等(同输入同输出)、报告(coverage_before /
coverage_after_preview / unresolved / candidates)。
全部纯函数测试,无 DB、无写入。
"""

from app.services.macro_evidence_lineage_recovery_service import (
    build_lineage_recovery,
    citation_hash,
    coverage_after_preview,
    coverage_before,
    dedup_key_of,
    dedup_references,
    literature_recovery_candidates,
    plan_lineage_recovery,
    recover_from_evidence_record,
    recover_from_evidence_text,
    text_only_reference,
    unresolved_evidence,
)
from app.services.macro_evidence_literature_service import (
    build_local_paper_library,
)


def _record(doi="", pmid="", year="", title="", cj=None, text="", rid="er1"):
    return {"id": rid, "paper_doi": doi, "paper_pmid": pmid,
            "paper_year": year, "paper_title": title,
            "paper_journal": "J", "citation_json": cj,
            "evidence_text": text, "verification_status": "human_reviewed",
            "confidence": 0.9}


def _paper(year, authors, doi="10.x/y", pmid="1", title="T"):
    return {"publication_year": year, "metadata_json": {"authors": authors},
            "doi": doi, "pmid": pmid, "title": title,
            "journal": "J", "source": "europepmc"}


def _final(fid="f1", ccid="c1", code="ng:cn:x", refs=None):
    return {"id": fid, "canonical_connection_id": ccid,
            "connection_code": code, "evidence_reference": refs or [],
            "evidence_summary": {"evidence_count": 2}}


def _lineage(mirror_ids, cluster="k1"):
    return [{"cluster_id": cluster, "mirror_connection_ids": mirror_ids}]


# ---- 1. evidence_record 恢复(A / B / 空) ----

def test_record_doi_pmid_priority_a():
    r = recover_from_evidence_record(
        _record(doi="10.1/x", pmid="12345", year="1990",
                title="Topo", cj={"doi": "10.1/x", "pmid": "12345"}))
    assert r is not None
    assert r["priority"] == "A"
    assert r["source_type"] == "literature"
    assert r["doi"] == "10.1/x"
    assert r["pmid"] == "12345"
    assert r["paper_title"] == "Topo"
    assert "10.1/x" in r["citation"] and "12345" in r["citation"]
    assert r["mirror_evidence_ids"] == ["er1"]


def test_record_citation_json_only_priority_b():
    r = recover_from_evidence_record(
        _record(cj={"doi": "", "pmid": "", "year": "2009",
                    "title": "H", "authors": "Habas C."}))
    assert r is not None
    assert r["priority"] == "B"
    assert r["citation_hash"] is not None


def test_record_no_structured_info_returns_none():
    r = recover_from_evidence_record(
        _record(text="only text, no citation json"))
    assert r is None


def test_record_pmid_numeric():
    r = recover_from_evidence_record(_record(pmid=2158523, year=1990,
                                             title="T", doi=""))
    assert r["priority"] == "B"
    assert r["pmid"] == "2158523"


# ---- 2. evidence_text 恢复(C 类) ----

def test_text_local_unique_match_priority_c():
    lib = build_local_paper_library(
        [_paper(1984, "Goldman-Rakic PS.", doi="10.2/a", pmid="7",
                title="G")])
    refs = recover_from_evidence_text(
        "projections (Goldman-Rakic et al., 1984).", lib, "m1")
    assert len(refs) == 1
    assert refs[0]["priority"] == "C"
    assert refs[0]["doi"] == "10.2/a"
    assert refs[0]["mirror_connection_ids"] == ["m1"]


def test_text_no_local_match_returns_empty():
    # 本地库无同姓同年论文 → 无 C 类引用(降级为 D)
    lib = build_local_paper_library([_paper(2009, "Mesulam M.")])
    refs = recover_from_evidence_text("(Habas et al., 2009)", lib, "m1")
    assert refs == []


def test_text_ambiguous_match_returns_empty():
    lib = build_local_paper_library([_paper(2009, "Habas C."),
                                     _paper(2009, "Baumann O, Habas C.")])
    refs = recover_from_evidence_text("(Habas et al., 2009)", lib, "m1")
    assert refs == []  # 多篇候选 → 不产生 C(降级为 D)


def test_text_no_citation_clue_returns_empty():
    refs = recover_from_evidence_text("no citations here", [], "m1")
    assert refs == []


# ---- 3. Evidence merge 去重(doi > pmid > citation_hash > title+year) ----

def test_dedup_key_priority_order():
    assert dedup_key_of({"doi": " 10.1/X ", "pmid": "1"}).startswith("doi:")
    assert dedup_key_of({"doi": "", "pmid": "2"}).startswith("pmid:")
    assert dedup_key_of({"doi": "", "pmid": "", "citation_hash": "abc"}) \
        .startswith("hash:")
    assert dedup_key_of({"doi": "", "pmid": "", "citation_hash": None,
                         "paper_title": "T", "year": "1990"}) \
        .startswith("title_year:")


def test_dedup_same_doi_merges_evidence_ids():
    refs = dedup_references([
        recover_from_evidence_record(
            _record(doi="10.1/x", pmid="1", year="1990", title="T",
                    rid="er1")),
        recover_from_evidence_record(
            _record(doi="10.1/x", pmid="1", year="1990", title="T",
                    rid="er2")),
    ])
    assert len(refs) == 1  # 同论文(同 doi)只保留 1 条
    assert refs[0]["mirror_evidence_ids"] == ["er1", "er2"]


def test_dedup_pmid_key_merges():
    refs = dedup_references([
        recover_from_evidence_record(_record(pmid="42", title="T", rid="a")),
        recover_from_evidence_record(_record(pmid="42", title="T", rid="b")),
    ])
    assert len(refs) == 1
    assert refs[0]["mirror_evidence_ids"] == ["a", "b"]


def test_dedup_citation_hash_key_merges():
    cj = {"doi": "", "pmid": "", "year": "2009", "title": "H"}
    refs = dedup_references([
        recover_from_evidence_record(_record(cj=cj, rid="a")),
        recover_from_evidence_record(_record(cj=cj, rid="b")),
    ])
    assert len(refs) == 1
    assert refs[0]["mirror_evidence_ids"] == ["a", "b"]


def test_dedup_title_year_key_merges_text_only():
    refs = dedup_references([
        text_only_reference(["m1"], ["text a"]),
        text_only_reference(["m2"], ["text b"]),
    ])
    assert len(refs) == 1  # 同键(title_year 空|空)→ 合并
    assert refs[0]["mirror_connection_ids"] == ["m1", "m2"]


def test_dedup_keeps_highest_priority_base():
    cj = {"doi": "10.9/z", "pmid": "9", "year": "2000", "title": "Z"}
    a = recover_from_evidence_record(_record(doi="10.9/z", pmid="9",
                                             year="2000", title="Z",
                                             rid="high"))
    low = recover_from_evidence_record(_record(cj=cj, rid="low"))
    out = dedup_references([low, a])
    assert len(out) == 1
    assert out[0]["priority"] == "A"
    assert out[0]["mirror_evidence_ids"] == ["high", "low"]


# ---- 4. lineage 完整性 + 单条 final 恢复 ----

def test_build_no_lineage():
    r = build_lineage_recovery(_final(), [], {}, {}, [])
    assert r["resolved"] is False
    assert r["reason"] == "no_lineage"
    assert r["evidence_references"] == []


def test_build_record_and_text_merge_by_doi():
    # mirror m1 有 evidence_record(A 类 LeDoux)+ evidence_text 引用同论文
    lib = build_local_paper_library(
        [_paper(1990, "LeDoux JE, Farb C, Ruggiero DA.",
                doi="10.1523/jneurosci.10-04-01043.1990", pmid="2158523",
                title="Topographic organization")])
    r = build_lineage_recovery(
        _final("f1", "c1", "ng:cn:thalamus"),
        _lineage(["m1", "m2"]),
        {"m1": {"evidence_text": "connections (LeDoux et al., 1990)."},
         "m2": {"evidence_text": "other text"}},
        {"m1": [_record(doi="10.1523/jneurosci.10-04-01043.1990",
                        pmid="2158523", year="1990", title="Topographic",
                        rid="er1")]},
        lib)
    assert r["resolved"] is True
    assert r["literature_recovered"] is True
    assert len(r["evidence_references"]) == 1  # A 与 C 同论文 → DOI 去重
    ref = r["evidence_references"][0]
    assert ref["priority"] == "A"
    assert ref["mirror_evidence_ids"] == ["er1"]
    assert ref["mirror_connection_ids"] == ["m1"]


def test_build_text_only_degrades_to_d():
    r = build_lineage_recovery(
        _final("f2", "c2", "ng:cn:y"),
        _lineage(["m1"]),
        {"m1": {"evidence_text": "no citation here at all"}},
        {}, [])
    assert r["resolved"] is False
    assert r["reason"] == "text_only_no_citation"
    assert len(r["evidence_references"]) == 1
    assert r["evidence_references"][0]["priority"] == "D"
    assert r["evidence_references"][0]["source_type"] == "llm_extraction"


def test_build_no_evidence_at_all():
    r = build_lineage_recovery(_final("f3", "c3"), _lineage(["m1"]),
                               {}, {}, [])
    assert r["resolved"] is False
    assert r["reason"] == "no_evidence_text"
    assert r["evidence_references"] == []


def test_build_multiple_distinct_papers():
    lib = build_local_paper_library(
        [_paper(2000, "Ongur D, Price JL.", doi="10.a", pmid="1",
                title="Prefrontal"),
         _paper(1988, "Goldman-Rakic PS.", doi="10.b", pmid="2",
                title="Circuitry")])
    r = build_lineage_recovery(
        _final("f4", "c4"),
        _lineage(["m1", "m2"]),
        {"m1": {"evidence_text": "(Ongur & Price, 2000)"},
         "m2": {"evidence_text": "(Goldman-Rakic et al., 1988)"}},
        {}, lib)
    assert r["resolved"] is True
    assert len(r["evidence_references"]) == 2
    assert {x["priority"] for x in r["evidence_references"]} == {"C"}


# ---- 5. 全量规划 + 幂等 ----

def test_plan_counts_and_idempotent():
    lib = build_local_paper_library(
        [_paper(1984, "Goldman-Rakic PS.", doi="10.2/a", pmid="7")])
    finals = [
        _final("f1", "c1", "ng:cn:a"),   # evidence_record A 类
        _final("f2", "c2", "ng:cn:b"),   # evidence_text C 类
        _final("f3", "c3", "ng:cn:c"),   # 纯文本 D
        _final("f4", "c4", "ng:cn:d"),   # 无 lineage
    ]
    lineage_map = {"c1": _lineage(["m1"]), "c2": _lineage(["m2"]),
                   "c3": _lineage(["m3"])}
    mirror_map = {"m2": {"evidence_text": "(Goldman-Rakic et al., 1984)"},
                  "m3": {"evidence_text": "no citation"}}
    evidence_map = {"m1": [_record(doi="10.9/z", pmid="9", year="2000",
                                   title="Z", rid="er1")]}
    plan = plan_lineage_recovery(finals, lineage_map, mirror_map,
                                 evidence_map, lib)
    c = plan["counts"]
    assert c["total"] == 4
    assert c["with_lineage"] == 3
    assert c["no_lineage"] == 1
    assert c["literature_recovered"] == 2  # f1 A + f2 C
    assert c["unresolved"] == 2            # f3 D + f4 no_lineage
    assert c["by_reason"]["text_only_no_citation"] == 1
    assert c["by_reason"]["no_lineage"] == 1
    assert c["by_reason"].get("no_evidence_text", 0) == 0
    # 幂等:同输入 → 同输出
    plan2 = plan_lineage_recovery(finals, lineage_map, mirror_map,
                                  evidence_map, lib)
    assert plan == plan2


# ---- 6. 报告 ----

def test_coverage_before():
    finals = [
        _final("f1", "c1", refs=[{"source_type": "llm_extraction",
                                  "paper": "", "doi": ""}]),
        _final("f2", "c2", refs=[{"source_type": "llm_extraction",
                                  "paper": "Some Paper", "doi": "10.x"}]),
        _final("f3", "c3", refs=[]),
    ]
    r = coverage_before(finals)
    assert r["total_final"] == 3
    assert r["evidence_reference_coverage"]["with_references"] == 2
    assert r["evidence_reference_coverage"]["with_paper_field_nonempty"] == 1
    assert r["evidence_reference_coverage"]["with_doi_or_pmid"] == 1


def test_coverage_after_preview_stats():
    lib = build_local_paper_library(
        [_paper(1984, "Goldman-Rakic PS.", doi="10.2/a", pmid="7")])
    finals = [_final("f1", "c1"), _final("f2", "c2")]
    lineage_map = {"c1": _lineage(["m1"]), "c2": _lineage(["m2"])}
    mirror_map = {"m1": {"evidence_text": "(Goldman-Rakic et al., 1984)"},
                  "m2": {"evidence_text": "no citation"}}
    plan = plan_lineage_recovery(finals, lineage_map, mirror_map, {}, lib)
    r = coverage_after_preview(plan, evidence_records_hit=2)
    assert r["preview_only"] is True
    assert r["literature_coverage"]["with_literature_reference"] == 1
    assert r["literature_coverage"]["coverage_pct"] == 50.0
    assert r["literature_coverage"]["by_priority"]["C"] == 1
    assert r["literature_coverage"]["by_priority"]["D"] == 1
    assert r["unresolved"]["count"] == 1


def test_unresolved_and_candidates_reports():
    lib = build_local_paper_library(
        [_paper(1984, "Goldman-Rakic PS.", doi="10.2/a", pmid="7")])
    finals = [_final("f1", "c1"), _final("f2", "c2")]
    lineage_map = {"c1": _lineage(["m1"]), "c2": _lineage(["m2"])}
    mirror_map = {"m1": {"evidence_text": "(Goldman-Rakic et al., 1984)"},
                  "m2": {"evidence_text": "no citation"}}
    plan = plan_lineage_recovery(finals, lineage_map, mirror_map, {}, lib)
    unresolved = unresolved_evidence(plan)
    assert len(unresolved) == 1
    assert unresolved[0]["final_id"] == "f2"
    assert unresolved[0]["reason"] == "text_only_no_citation"
    cands = literature_recovery_candidates(plan)
    assert len(cands) == 1
    assert cands[0]["final_id"] == "f1"
    assert cands[0]["references"][0]["priority"] == "C"


def test_citation_hash_deterministic():
    cj = {"doi": "10.x", "pmid": "1", "year": "2000", "title": "T"}
    assert citation_hash(cj) == citation_hash(cj)
    assert citation_hash(None) is None
    assert citation_hash("") is None
    assert citation_hash('{"doi": "10.x", "pmid": "1"}') == \
        citation_hash({"doi": "10.x", "pmid": "1"})
