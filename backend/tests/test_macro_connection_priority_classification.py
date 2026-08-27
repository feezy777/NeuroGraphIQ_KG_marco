"""Macro Connection Priority Classification V2 — 纯函数测试。

覆盖:coverage matrix V2(覆盖/缺失对)/ region degree / 缺失对三分类
(细分 hierarchy 覆盖、同父内部、父概念未覆盖转 B、非实质脑室、mirror 证据 A、
无证据 B)/ 27 条 A1 candidate 重评估(父概念提升 + 覆盖判定 + 自环)/
全流程规划与新旧对比。全部纯函数测试,无 DB、无写入。
"""

from app.services.macro_connection_priority_classification_service import (
    NON_SUBSTANTIVE_REGIONS,
    SUBDIVISION_CONCEPTS,
    SUBDIVISION_PARENT,
    V1_BASELINE,
    build_coverage_matrix_v2,
    classify_missing_pairs,
    compute_region_degree,
    normalize_region_name,
    parse_side,
    plan_priority_classification,
    reassess_a1_candidates,
)

POOL = ["amygdala", "cerebellum exterior", "cerebellum white matter",
        "caudal middle frontal", "diencephalon", "hippocampus",
        "thalamus proper", "ventral diencephalon", "3rd ventricle"]


def _conn(s, t, ctype="structural_connection", ev=1):
    return {"src_name": s, "tgt_name": t, "connection_type": ctype,
            "evidence_count": ev}


def _mirror(s, t, ctype="structural_connection"):
    return {"src_name": s, "tgt_name": t, "connection_type": ctype}


# ---- 常量与归一化 ----

def test_constants():
    assert SUBDIVISION_CONCEPTS == ("cerebellum exterior", "cerebellum white matter",
                                    "ventral diencephalon")
    assert SUBDIVISION_PARENT == {"cerebellum exterior": "cerebellum",
                                  "cerebellum white matter": "cerebellum",
                                  "ventral diencephalon": "diencephalon"}
    assert "3rd ventricle" in NON_SUBSTANTIVE_REGIONS
    assert V1_BASELINE["covered_pairs"] == 1145
    assert V1_BASELINE["coverage_pct"] == 86.35


def test_normalize_and_parse_side():
    assert normalize_region_name("Left-Amygdala") == "amygdala"
    assert normalize_region_name("right cerebellum exterior") == "cerebellum exterior"
    assert parse_side("left amygdala") == ("amygdala", "L")
    assert parse_side("amygdala") == ("amygdala", "M")


# ---- coverage matrix v2 ----

def test_coverage_matrix_v2_counts_and_missing():
    conns = [_conn("left amygdala", "left hippocampus"),
             _conn("right hippocampus", "right amygdala"),  # 同对合并
             _conn("left caudal middle frontal", "left thalamus proper"),
             _conn("amygdala", "3rd ventricle"),
             _conn("out of pool", "amygdala")]  # 池外忽略
    m = build_coverage_matrix_v2(POOL, conns)
    assert m["pool_size"] == 9
    assert m["total_pairs"] == 36
    assert m["covered_pairs"] == 3          # amygdala-hippocampus 合并 + 2
    assert ("amygdala", "hippocampus") not in [tuple(p) for p in m["missing_pairs"]]
    assert m["pair_detail"][0]["region_pair"] == ("amygdala", "hippocampus")  # 计数最多
    assert len(m["missing_pairs"]) == 33
    assert m["covered_region_count"] == 5   # amygdala/hippocampus/cmf/thalamus/3v
    assert "3rd ventricle" not in m["uncovered_regions"]
    assert "cerebellum exterior" in m["uncovered_regions"]


def test_region_degree_isolated():
    conns = [_conn("left amygdala", "left hippocampus")]
    d = compute_region_degree(POOL, conns)
    assert d["region_count"] == 9
    assert d["regions"][0]["region"] == "3rd ventricle"
    assert "cerebellum exterior" in d["isolated_regions"]
    amy = [r for r in d["regions"] if r["region"] == "amygdala"][0]
    assert amy["total_degree"] == 1
    assert amy["isolated"] is False


# ---- 三分类 ----

def _classify(missing, mirrors=None, finals=None, funcs=None):
    return classify_missing_pairs(
        missing,
        mirrors or [],
        finals or [],
        funcs or {},
    )


def test_classify_subdivision_parent_covered_is_C():
    # 细分对(cex-amygdala):父概念对 cerebellum-amygdala 在 final 层已覆盖 → C
    missing = [("amygdala", "cerebellum exterior")]
    finals = [_conn("Cerebellum", "left amygdala")]
    cl = _classify(missing, [], finals)
    assert cl["counts"] == {"A": 0, "B": 0, "C": 1, "total": 1}
    c = cl["C"][0]
    assert c["reason"] == "hierarchy_covered_subdivision"
    assert c["parent"] == "cerebellum"
    assert c["parent_pair"] == ["amygdala", "cerebellum"]


def test_classify_subdivision_parent_missing_is_B():
    # 细分对(vdi-amygdala):父概念对 diencephalon-amygdala 未覆盖 → B
    missing = [("amygdala", "ventral diencephalon")]
    finals = [_conn("Cerebellum", "left amygdala")]  # 只有 cerebellum-amygdala
    cl = _classify(missing, [], finals)
    assert cl["counts"] == {"A": 0, "B": 1, "C": 0, "total": 1}
    assert cl["B"][0]["reason"] == "subdivision_parent_missing"
    assert cl["B"][0]["parent_pair"] == ["amygdala", "diencephalon"]


def test_classify_same_parent_subdivision_is_C():
    # cex-cwm 同父概念内部细分对 → C
    cl = _classify([("cerebellum exterior", "cerebellum white matter")],
                   [], [_conn("Cerebellum", "left amygdala")])
    assert cl["counts"] == {"A": 0, "B": 0, "C": 1, "total": 1}
    assert cl["C"][0]["reason"] == "subdivision_same_parent"


def test_classify_non_substantive_is_C():
    cl = _classify([("3rd ventricle", "amygdala")])
    assert cl["C"][0]["reason"] == "non_substantive_region"


def test_classify_mirror_evidence_is_A():
    missing = [("amygdala", "hippocampus")]
    mirrors = [_mirror("left amygdala", "left hippocampus"),
               _mirror("left amygdala", "right hippocampus")]
    cl = _classify(missing, mirrors)
    assert cl["counts"] == {"A": 1, "B": 0, "C": 0, "total": 1}
    a = cl["A"][0]
    assert a["reason"] == "mirror_evidence_missing_in_final"
    assert "ll" in a["mirror_combos"]
    assert "lr" in a["mirror_combos"]


def test_classify_no_evidence_is_B_with_function_support():
    missing = [("amygdala", "hippocampus")]
    funcs = {"amygdala": {"memory"}, "hippocampus": {"memory", "spatial"}}
    cl = _classify(missing, [], [], funcs)
    assert cl["counts"] == {"A": 0, "B": 1, "C": 0, "total": 1}
    b = cl["B"][0]
    assert b["reason"] == "no_mirror_evidence_requires_literature"
    assert b["shared_functions"] == ["memory"]


# ---- A1 candidate 重评估 ----

def test_reassess_discard_when_parent_pair_covered():
    cands = [{"id": "c1", "source_region_name": "left amygdala",
              "target_region_name": "left cerebellum exterior"}]
    finals = [_conn("Cerebellum", "left amygdala")]  # 父概念对已覆盖
    out = reassess_a1_candidates(cands, finals, set(POOL))
    assert out[0]["recommendation"] == "discard"
    assert out[0]["reason"] == "ontology_covered"
    assert out[0]["parent_concept_pair"] == ["amygdala", "cerebellum"]
    assert "cerebellum exterior" in out[0]["parent_substitution"][0]


def test_reassess_keep_when_parent_pair_missing():
    cands = [{"id": "c2", "source_region_name": "left ventral diencephalon",
              "target_region_name": "left amygdala"}]
    finals = [_conn("Cerebellum", "left amygdala")]  # 父概念对 di-amygdala 未覆盖
    out = reassess_a1_candidates(cands, finals, set(POOL))
    assert out[0]["recommendation"] == "keep"
    assert out[0]["reason"] == "still_missing"
    assert out[0]["parent_concept_pair"] == ["amygdala", "diencephalon"]


def test_reassess_discard_self_loop():
    cands = [{"id": "c3", "source_region_name": "left amygdala",
              "target_region_name": "right amygdala"}]
    out = reassess_a1_candidates(cands, [], set(POOL))
    assert out[0]["recommendation"] == "discard"
    assert out[0]["reason"] == "self_loop"


def test_reassess_full_flow_counts():
    cands = [
        {"id": "c1", "source_region_name": "left amygdala",
         "target_region_name": "left cerebellum exterior"},   # covered → discard
        {"id": "c2", "source_region_name": "left ventral diencephalon",
         "target_region_name": "left amygdala"},              # missing → keep
    ]
    finals = [_conn("Cerebellum", "left amygdala")]
    out = reassess_a1_candidates(cands, finals, set(POOL))
    assert [o["recommendation"] for o in out] == ["discard", "keep"]


# ---- 全流程规划 ----

def test_plan_priority_classification_full_flow():
    # 可控小池 4 区:total 6 对。父概念 Cerebellum 不在池内(full-range 覆盖判定)
    pool = ["amygdala", "cerebellum exterior", "hippocampus", "3rd ventricle"]
    finals = [_conn("Cerebellum", "left amygdala")]   # 池外,不占 matrix 覆盖
    mirrors = [_mirror("left amygdala", "left hippocampus"),
               _mirror("right amygdala", "right hippocampus")]
    cands = [{"id": "c1", "source_region_name": "left amygdala",
              "target_region_name": "left cerebellum exterior"}]
    funcs = {"amygdala": {"memory"}, "hippocampus": {"memory"}}
    plan = plan_priority_classification(pool, finals, mirrors, funcs, cands)
    m, cl = plan["matrix"], plan["classification"]
    assert m["covered_pairs"] == 0
    assert cl["counts"]["total"] == len(m["missing_pairs"]) == 6
    # 6 个缺失对逐个判定:
    #   (amygdala, cex)   → C hierarchy_covered_subdivision(父概念对 cerebellum-amygdala 在 final)
    #   (3rd ventricle, *)→ C non_substantive(3 对中 2 对; (3v, cex) 先命中细分分支 → B)
    #   (amygdala, hippocampus) → A(mirror 直接证据 ll/lr)
    #   (cex, hippocampus) → B(父概念对未覆盖);(3v, cex) → B(细分+脑室,细分分支优先)
    assert cl["counts"] == {"A": 1, "B": 2, "C": 3, "total": 6}
    assert cl["A"][0]["region_pair"] == ["amygdala", "hippocampus"]
    # A1 重评估:cex 父概念对 cerebellum-amygdala 已覆盖 → discard
    assert plan["reassessment_counts"] == {
        "total": 1, "keep": 0, "discard": 1, "discard_ontology_covered": 1}
    # 新旧对比
    assert plan["delta_v1_v2"]["coverage_pct"]["v2"] == m["coverage_pct"]
    assert plan["delta_v1_v2"]["missing_pairs"]["v2"] == 6
