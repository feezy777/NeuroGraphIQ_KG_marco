"""Macro Connection 论文数据导入测试(纯函数,不碰 DB)。

覆盖:DOI 归一化、论文唯一标识、104 refs → 论文去重聚合、paper_sources
插入字段映射(用户指定)、Connection-Paper 关联结构(用户指定)、
复用/新增规划、幂等语义。
"""

from app.services.macro_connection_paper_import_service import (
    PAPER_SOURCE,
    SUPPORT_TYPE,
    build_link,
    build_paper_insert,
    group_paper_records,
    normalize_doi,
    paper_identity,
    plan_paper_reuse,
)

CID = "11111111-1111-1111-1111-111111111111"


def _ref(**overrides) -> dict:
    base = {
        "source_type": "literature",
        "connection_id": CID,
        "connection_code": "ng:cn:structural_a_to_b",
        "mirror_evidence_ids": ["ev-1"],
        "author_query": "Habas[Author]",
        "year": 2009,
        "matched_title": "Distinct cerebellar contributions to cognitive networks",
        "title": "Distinct cerebellar contributions to cognitive networks",
        "authors": "Habas et al.",
        "journal": "",
        "doi": "10.1523/JNEUROSCI.1234-09.2009",
        "pmid": "19074045",
        "match_score": 0.9,
        "confidence": 0.9,
        "match_method": "pubmed_author_year",
        "status": "matched",
        "original_text": "(Habas et al., 2009)",
        "evidence_source": "pubmed_backfill_v1",
        "generation_method": "pubmed_backfill_v1",
        "source": "PubMed",
    }
    base.update(overrides)
    return base


# ---- normalize_doi / paper_identity ----

def test_normalize_doi():
    assert normalize_doi("  10.1523/JNEUROSCI.1234-09.2009 ") == \
        "10.1523/jneurosci.1234-09.2009"
    assert normalize_doi("") == ""
    assert normalize_doi("DOI:10.1/x") == "doi:10.1/x"  # 前缀不剥离,保持原文


def test_paper_identity_doi_priority():
    ident = paper_identity(_ref())
    assert ident[0] == "10.1523/jneurosci.1234-09.2009"
    assert ident[1] == "19074045"


def test_paper_identity_pmid_when_no_doi():
    ident = paper_identity(_ref(doi=""))
    assert ident[0] == ""
    assert ident[1] == "19074045"


# ---- group_paper_records:104 refs → 唯一论文 ----

def test_group_paper_records_dedup_same_doi():
    refs = [_ref(doi="10.1/x", pmid="1"),
            _ref(doi="10.1/x", pmid="1", original_text="(A, 2009b)")]
    groups = group_paper_records(refs)
    assert len(groups) == 1
    assert len(groups[0]["refs"]) == 2  # 同论文多 ref 聚合


def test_group_paper_records_distinct_papers():
    refs = [_ref(doi="10.1/x", pmid="1"),
            _ref(doi="10.2/y", pmid="2"),
            _ref(doi="", pmid="3")]  # 无 DOI → PMID 标识
    groups = group_paper_records(refs)
    assert len(groups) == 3


def test_group_paper_records_doi_case_insensitive():
    refs = [_ref(doi="10.1/X", pmid="1"),
            _ref(doi="10.1/x", pmid="2")]  # 大小写不同 → 同论文
    groups = group_paper_records(refs)
    assert len(groups) == 1


def test_group_paper_records_multi_connection_same_paper():
    """同论文支撑多连接:合并为 1 条论文记录(关联仍按连接分)。"""
    refs = [_ref(connection_id=CID, doi="10.1/x", pmid="1"),
            _ref(connection_id="22222222-2222-2222-2222-222222222222",
                 doi="10.1/x", pmid="1")]
    groups = group_paper_records(refs)
    assert len(groups) == 1
    assert len(groups[0]["refs"]) == 2


# ---- build_paper_insert:用户指定导入字段 ----

def test_build_paper_insert_fields():
    rec = group_paper_records([_ref()])[0]
    ins = build_paper_insert(rec)
    assert ins["source"] == PAPER_SOURCE  # PubMed
    assert ins["doi"] == "10.1523/JNEUROSCI.1234-09.2009"
    assert ins["normalized_doi"] == "10.1523/jneurosci.1234-09.2009"
    assert ins["pmid"] == "19074045"
    assert ins["title"] == "Distinct cerebellar contributions to cognitive networks"
    assert ins["journal"] is None  # 无 journal 数据 → NULL
    assert ins["publication_year"] == 2009
    assert ins["metadata_json"]["authors"] == "Habas et al."
    assert ins["metadata_json"]["mode"] == "literature"
    assert ins["metadata_json"]["matched_refs"] == ["(Habas et al., 2009)"]


def test_build_paper_insert_no_doi_year_invalid():
    ins = build_paper_insert({"doi": "", "pmid": "3", "title": "T",
                              "authors": "A", "journal": "", "year": "",
                              "refs": [_ref()]})
    assert ins["doi"] is None
    assert ins["normalized_doi"] is None
    assert ins["pmid"] == "3"
    assert ins["publication_year"] is None


# ---- build_link:用户指定关联结构 ----

def test_build_link_structure():
    ref = _ref()
    link = build_link(CID, "paper-uuid", ref)
    for field in ("connection_id", "paper_id", "support_type",
                  "evidence_reference", "confidence", "provenance_json"):
        assert field in link, f"missing {field}"
    assert link["connection_id"] == CID
    assert link["paper_id"] == "paper-uuid"
    assert link["support_type"] == SUPPORT_TYPE
    assert link["confidence"] == 0.9
    # evidence_reference 与 final 中 literature 元素同构(原样保存)
    assert link["evidence_reference"] == ref
    # provenance 完整
    p = link["provenance_json"]
    assert p["imported_from"] == "macro_connection_paper_import_v1"
    assert p["source"] == "PubMed"
    assert p["match_method"] == "pubmed_author_year"
    assert p["match_score"] == 0.9
    assert p["original_text"] == "(Habas et al., 2009)"
    assert "imported_at" in p


def test_build_link_confidence_fallback():
    ref = _ref(confidence=None)
    link = build_link(CID, "p", ref)
    assert link["confidence"] == 0.9  # 回退到 match_score


# ---- plan_paper_reuse:复用 vs 新增 ----

def _existing(pid="paper-1", doi="10.1523/jneurosci.1234-09.2009",
              pmid="19074045"):
    return [(pid, doi, pmid)]


def test_plan_reuse_by_doi():
    recs = group_paper_records([_ref()])
    plan = plan_paper_reuse(_existing(), recs)
    assert len(plan["reuse"]) == 1
    assert plan["reuse"][0]["paper_id"] == "paper-1"
    assert plan["reuse"][0]["matched_by"] == "doi"
    assert len(plan["new"]) == 0


def test_plan_reuse_by_pmid_when_doi_missing():
    recs = group_paper_records([_ref(doi="")])
    plan = plan_paper_reuse(_existing(), recs)
    assert len(plan["reuse"]) == 1
    assert plan["reuse"][0]["matched_by"] == "pmid"


def test_plan_new_when_not_in_db():
    recs = group_paper_records([_ref(doi="10.999/x", pmid="999")])
    plan = plan_paper_reuse(_existing(), recs)
    assert len(plan["reuse"]) == 0
    assert len(plan["new"]) == 1
    assert plan["new"][0]["paper_id"] is None


def test_plan_mixed_reuse_and_new():
    existing = _existing()
    recs = group_paper_records([
        _ref(doi="10.1523/jneurosci.1234-09.2009", pmid="19074045"),
        _ref(doi="10.2/y", pmid="2"),
    ])
    plan = plan_paper_reuse(existing, recs)
    assert len(plan["reuse"]) == 1
    assert len(plan["new"]) == 1


# ---- 幂等语义 ----

def test_plan_idempotent_second_run_all_reuse():
    """复跑:paper 全部已存在 → reuse,新增 0。"""
    recs = group_paper_records([_ref()])
    existing = [(f"p{i}", r["normalized_doi"] or "", r["pmid"] or "")
                for i, r in enumerate(
                    [build_paper_insert(r) for r in recs])]
    plan = plan_paper_reuse(existing, recs)
    assert len(plan["reuse"]) == len(recs)
    assert len(plan["new"]) == 0


def test_evidence_reference_untouched_semantics():
    """本阶段不改 evidence_reference —— 只读 literature reference 输入。"""
    ref = _ref()
    # 输入来自 final.evidence_reference 的 literature 元素(阶段 G 已追加)
    assert ref["source_type"] == "literature"  # 由阶段 G 结构保证
    link = build_link(CID, "p", ref)
    # 关联保存的是同一元素(不新增/不修改)
    assert link["evidence_reference"]["doi"] == ref["doi"]
    assert link["evidence_reference"]["evidence_source"] == "pubmed_backfill_v1"
