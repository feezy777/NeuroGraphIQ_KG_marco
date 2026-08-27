"""Macro Paper Knowledge Enrichment 测试(纯函数,不碰 DB)。

覆盖:Europe PMC core → 6 字段映射(含缺失容错)、溯源字段
(metadata_source/retrieved_at/pmid)、不覆盖已有非空字段、
幂等规划(已富化跳过)、journal 条件更新参数、UPDATE 幂等 SQL 形状。
"""

from app.services.macro_paper_enrichment_service import (
    METADATA_SOURCE,
    UPDATE_ENRICHMENT_SQL,
    already_enriched,
    build_update,
    enrich_json,
    merge_enrichment,
    parse_europepmc_core,
    plan_enrichment,
)


def _core(**overrides) -> dict:
    base = {
        "pmid": "19074045",
        "title": "Distinct cerebellar contributions to cognitive networks",
        "abstractText": "We report a dissociation in cerebellar function.",
        "journalInfo": {"journal": {"title": "J Neurosci"}},
        "pubTypeList": {"pubType": ["Journal Article",
                                    "Research Support, N.I.H., Extramural"]},
        "keywordList": {"keyword": ["cerebellum", "functional MRI"]},
        "meshHeadingList": {"meshHeading": [
            {"majorTopic_YN": "Y", "descriptorName": "Cerebellum",
             "meshQualifierList": {"meshQualifier": [
                 {"abbreviation": "PH", "qualifierName": "physiology"}]}},
            {"majorTopic_YN": "N", "descriptorName": "Brain",
             "meshQualifierList": {"meshQualifier": []}},
        ]},
        "authorList": {"author": [
            {"fullName": "Mesulam MM", "firstName": "M M",
             "lastName": "Mesulam", "initials": "MM",
             "authorAffiliationDetailsList": {"authorAffiliation": [
                 {"affiliation": "Northwestern Univ"}]}},
        ]},
        "pubYear": "1995",
    }
    base.update(overrides)
    return base


def _paper(pmid="19074045", enrichment_json=None, journal=None,
           paper_id="p1") -> dict:
    return {"paper_id": paper_id, "pmid": pmid, "journal": journal,
            "enrichment_json": enrichment_json}


# ---- parse_europepmc_core:6 字段映射 ----

def test_parse_core_full():
    p = parse_europepmc_core(_core())
    assert p["abstract"] == "We report a dissociation in cerebellar function."
    assert p["journal"] == "J Neurosci"
    assert p["publication_type"] == ["Journal Article",
                                     "Research Support, N.I.H., Extramural"]
    assert p["keywords"] == ["cerebellum", "functional MRI"]
    # mesh:descriptor + qualifier 拼接
    assert p["mesh_terms"] == ["Cerebellum/physiology", "Brain"]
    assert p["authors"] == [{"full_name": "Mesulam MM",
                             "last_name": "Mesulam",
                             "initials": "MM",
                             "affiliations": ["Northwestern Univ"]}]


def test_parse_core_missing_sections():
    p = parse_europepmc_core({"pmid": "1"})
    assert p["abstract"] is None
    assert p["journal"] is None
    assert p["publication_type"] == []
    assert p["keywords"] == []
    assert p["mesh_terms"] == []
    assert p["authors"] == []


def test_parse_core_null_sections():
    p = parse_europepmc_core(_core(abstractText=None, keywordList=None,
                                   journalInfo=None, meshHeadingList=None))
    assert p["abstract"] is None
    assert p["journal"] is None
    assert p["keywords"] == []
    assert p["mesh_terms"] == []


def test_parse_mesh_ignores_plain_strings():
    """meshHeading 元素必须是 dict;脏数据跳过不报错。"""
    p = parse_europepmc_core(_core(meshHeadingList={"meshHeading":
                                                    ["garbage"]}))
    assert p["mesh_terms"] == []


# ---- enrich_json:溯源字段 ----

def test_enrich_json_provenance():
    e = enrich_json("19074045", {"abstract": "A", "journal": "J"},
                    retrieved_at="2026-08-25T00:00:00Z")
    assert e["metadata_source"] == METADATA_SOURCE
    assert e["retrieved_at"] == "2026-08-25T00:00:00Z"
    assert e["pmid"] == "19074045"
    assert e["abstract"] == "A"
    assert e["journal"] == "J"


# ---- merge_enrichment:不覆盖已有非空 ----

def test_merge_keeps_existing_nonempty():
    existing = {"metadata_source": "older", "abstract": "已有摘要",
                "keywords": []}
    fresh = {"metadata_source": METADATA_SOURCE,
             "abstract": "新摘要", "journal": "J Neurosci",
             "keywords": ["cerebellum"]}
    m = merge_enrichment(existing, fresh)
    assert m["abstract"] == "已有摘要"  # 已有非空 → 保留
    assert m["journal"] == "J Neurosci"  # 空 → 填充
    assert m["keywords"] == ["cerebellum"]  # 空列表 → 填充
    assert m["metadata_source"] == METADATA_SOURCE  # 溯源刷新


def test_merge_none_existing():
    m = merge_enrichment(None, {"abstract": "A", "journal": "J"})
    assert m["abstract"] == "A"
    assert m["journal"] == "J"


# ---- already_enriched / plan_enrichment:幂等 ----

def test_already_enriched_false_when_missing():
    assert not already_enriched(None)
    assert not already_enriched({})
    assert not already_enriched({"metadata_source": "other"})


def test_already_enriched_true():
    assert already_enriched({"metadata_source": METADATA_SOURCE})


def test_plan_skip_enriched():
    papers = [_paper(enrichment_json={"metadata_source": METADATA_SOURCE}),
              _paper(pmid="2"), _paper(pmid="3", enrichment_json=None)]
    plan = plan_enrichment(papers)
    assert len(plan["skip"]) == 1
    assert len(plan["to_fetch"]) == 2


def test_plan_idempotent_second_run_all_skip():
    """复跑:全部已富化 → to_fetch=0。"""
    papers = [_paper(enrichment_json={"metadata_source": METADATA_SOURCE})
              for _ in range(3)]
    plan = plan_enrichment(papers)
    assert len(plan["to_fetch"]) == 0
    assert len(plan["skip"]) == 3


# ---- build_update:journal 不覆盖 + enrichment 合并 ----

def test_build_update_journal_conditional():
    parsed = {"journal": "J Neurosci", "abstract": "A", "keywords": [],
              "publication_type": [], "mesh_terms": [], "authors": []}
    # journal 已有非空 → 传入但 SQL COALESCE 保留旧值
    u = build_update(_paper(journal="已有期刊"), parsed,
                     retrieved_at="2026-08-25T00:00:00Z")
    assert u["id"] == "p1"
    assert u["journal"] == "J Neurosci"
    assert u["enrichment_json"]["journal"] == "J Neurosci"
    assert u["enrichment_json"]["metadata_source"] == METADATA_SOURCE
    assert u["enrichment_json"]["pmid"] == "19074045"
    assert "retrieved_at" in u["enrichment_json"]


def test_build_update_keeps_existing_enrichment_fields():
    parsed = {"journal": "J", "abstract": "A", "keywords": [],
              "publication_type": [], "mesh_terms": [], "authors": []}
    u = build_update(_paper(
        enrichment_json={"metadata_source": METADATA_SOURCE,
                         "abstract": "已富化摘要"}), parsed)
    assert u["enrichment_json"]["abstract"] == "已富化摘要"
    assert u["enrichment_json"]["journal"] == "J"


# ---- UPDATE SQL 幂等形状 ----

def test_update_sql_is_distinct_from_guard():
    """变化检测锚点:enrichment_json IS DISTINCT FROM → 复跑 update=0。"""
    assert "IS DISTINCT FROM" in UPDATE_ENRICHMENT_SQL
    assert "COALESCE(NULLIF(journal, ''), :journal)" in UPDATE_ENRICHMENT_SQL
    assert "RETURNING id" in UPDATE_ENRICHMENT_SQL
