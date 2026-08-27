"""Macro Connection Coverage Gap Analysis V1 — 纯函数测试。

覆盖:区域归一化 / Coverage Matrix / Region Degree / 双侧对称性(A1/A2/B)/
功能候选 / 汇总候选。全部为纯函数测试,无 DB 依赖,无写入。
"""

from app.services.macro_connection_coverage_gap_service import (
    analyze_symmetry,
    build_coverage_matrix,
    build_supplementation_candidates,
    compute_region_degree,
    find_functional_gap_candidates,
    normalize_region_name,
    parse_side,
)

# ---- 区域归一化 ----

def test_normalize_region_name_strips_side_prefix():
    assert normalize_region_name("left amygdala") == "amygdala"
    assert normalize_region_name("Right-Amygdala") == "amygdala"
    assert normalize_region_name("Amygdala") == "amygdala"
    assert normalize_region_name("left superior frontal gyrus") == "superior frontal gyrus"


def test_normalize_region_name_collapses_spaces_and_case():
    assert normalize_region_name("  Left   Precentral   Gyrus  ") == "precentral gyrus"
    assert normalize_region_name("") == ""
    assert normalize_region_name(None) == ""


def test_parse_side():
    assert parse_side("left amygdala") == ("amygdala", "L")
    assert parse_side("Right-Thalamus proper") == ("thalamus proper", "R")
    assert parse_side("brain stem") == ("brain stem", "M")


# ---- Coverage Matrix ----

def test_build_coverage_matrix_counts_pairs_and_evidence():
    pool = ["amygdala", "hippocampus", "thalamus proper"]
    conns = [
        {"src_name": "Amygdala", "tgt_name": "Hippocampus",
         "evidence_count": 3, "connection_type": "structural"},
        {"src_name": "hippocampus", "tgt_name": "Amygdala",  # 反向 → 同一对
         "evidence_count": 2, "connection_type": "functional"},
        {"src_name": "Thalamus proper", "tgt_name": "Hippocampus",
         "evidence_count": 1, "connection_type": "structural"},
        {"src_name": "Amygdala", "tgt_name": "outside_pool",  # 池外 → 忽略
         "evidence_count": 9, "connection_type": "structural"},
    ]
    m = build_coverage_matrix(pool, conns)
    assert m["pool_size"] == 3
    assert m["total_pairs"] == 3  # 3 区域 → 3 个无向对
    assert m["covered_pairs"] == 2
    assert m["uncovered_regions"] == []  # 3 区域全部有连接
    detail = {tuple(e["region_pair"]): e for e in m["pair_detail"]}
    assert ("amygdala", "hippocampus") in detail  # 字母序无向对
    pair = detail[("amygdala", "hippocampus")]
    assert pair["connection_count"] == 2  # 双向合并为同一对
    assert pair["evidence_count"] == 5
    assert pair["connection_types"] == {"structural": 1, "functional": 1}


def test_build_coverage_matrix_all_uncovered():
    pool = ["a", "b", "c"]
    m = build_coverage_matrix(pool, [])
    assert m["covered_pairs"] == 0
    assert m["coverage_pct"] == 0.0
    assert m["uncovered_regions"] == ["a", "b", "c"]
    assert m["region_rows"][0]["covered_pairs"] == 0


# ---- Region Degree ----

def test_compute_region_degree_split_types():
    pool = ["amygdala", "hippocampus", "thalamus proper", "prefrontal cortex"]
    conns = [
        {"src_name": "amygdala", "tgt_name": "hippocampus",
         "connection_type": "structural"},
        {"src_name": "amygdala", "tgt_name": "thalamus proper",
         "connection_type": "structural"},
        {"src_name": "amygdala", "tgt_name": "hippocampus",
         "connection_type": "functional"},
        {"src_name": "prefrontal cortex", "tgt_name": "amygdala",
         "connection_type": "functional"},
    ]
    d = compute_region_degree(pool, conns)
    by_region = {r["region"]: r for r in d["regions"]}
    a = by_region["amygdala"]
    assert a["outgoing_degree"] == 3
    assert a["incoming_degree"] == 1
    assert a["total_degree"] == 4
    assert a["structural_degree"] == 2  # 仅 structural 两端
    assert a["functional_degree"] == 2  # 1 functional out + 1 functional in
    assert by_region["thalamus proper"]["incoming_degree"] == 1
    assert by_region["prefrontal cortex"]["outgoing_degree"] == 1
    assert d["zero_degree_regions"] == []  # 4 区域全有连接


def test_compute_region_degree_zero_and_high_classification():
    pool = ["hub", "leaf", "isolated"]
    conns = [
        {"src_name": "hub", "tgt_name": "hub", "connection_type": "structural"},
    ]
    d = compute_region_degree(pool, conns)
    by_region = {r["region"]: r for r in d["regions"]}
    # self-loop 被排除 → 全部 0 degree
    assert d["zero_degree_regions"] == ["hub", "isolated", "leaf"]
    assert by_region["isolated"]["potential_missing"] is True


def test_compute_region_degree_classification_tiers():
    pool = [f"r{i}" for i in range(5)]
    conns = [
        # r0 高度连接(3 出),r4 零度
        {"src_name": "r0", "tgt_name": f"r{i}", "connection_type": "structural"}
        for i in range(1, 4)
    ] + [{"src_name": "r1", "tgt_name": "r2", "connection_type": "functional"}]
    d = compute_region_degree(pool, conns)
    by_region = {r["region"]: r for r in d["regions"]}
    assert by_region["r0"]["total_degree"] == 3
    assert by_region["r0"]["classification"] == "high_connectivity"
    assert by_region["r4"]["total_degree"] == 0
    assert by_region["r4"]["classification"] == "low_connectivity"
    assert "r0" in d["high_connectivity_regions"]
    assert "r4" in d["low_connectivity_regions"]


# ---- 双侧对称性 ----

def test_analyze_symmetry_a1_missing_mirror():
    pool = ["amygdala", "hippocampus", "thalamus proper"]
    mirrors = [
        {"src_name": "left amygdala", "tgt_name": "left hippocampus",
         "connection_type": "structural"},
        {"src_name": "right amygdala", "tgt_name": "right hippocampus",
         "connection_type": "structural"},
        {"src_name": "left hippocampus", "tgt_name": "left thalamus proper",
         "connection_type": "structural"},  # 右侧无 → A1
    ]
    s = analyze_symmetry(pool, mirrors)
    # A1 缺失(hippocampus→thalamus proper 仅左侧)+ A2 区域级
    # (thalamus proper 右侧整体无连接)——两者不同粒度,可并存
    assert s["counts"] == {"A1": 1, "A2": 1, "B": 0}
    a1 = s["A1_high_confidence_missing"][0]
    assert a1["region_pair"] == ("hippocampus", "thalamus proper")
    assert a1["missing_side"] == "right"
    a2 = s["A2_possible_missing"][0]
    assert a2["region"] == "thalamus proper"
    assert a2["missing_side"] == "right"


def test_analyze_symmetry_a2_side_entirely_missing():
    pool = ["amygdala", "hippocampus", "thalamus proper"]
    mirrors = [
        # right amygdala 完全无任何连接;hippocampus 双侧都有参与
        {"src_name": "left amygdala", "tgt_name": "left hippocampus",
         "connection_type": "structural"},
        {"src_name": "left amygdala", "tgt_name": "right hippocampus",
         "connection_type": "functional"},
    ]
    s = analyze_symmetry(pool, mirrors)
    assert s["counts"]["A2"] == 1
    a2 = s["A2_possible_missing"][0]
    assert a2["region"] == "amygdala"
    assert a2["missing_side"] == "right"
    assert a2["existing_side"] == "left"


def test_analyze_symmetry_b_type_mismatch():
    pool = ["amygdala", "hippocampus", "thalamus proper"]
    mirrors = [
        {"src_name": "left amygdala", "tgt_name": "left hippocampus",
         "connection_type": "structural"},
        {"src_name": "right amygdala", "tgt_name": "right hippocampus",
         "connection_type": "functional"},  # 类型不一致 → B
    ]
    s = analyze_symmetry(pool, mirrors)
    assert s["counts"]["B"] == 1
    b = s["B_requires_literature"][0]
    assert b["region_pair"] == ("amygdala", "hippocampus")
    assert b["left_types"] == ["structural"]
    assert b["right_types"] == ["functional"]


def test_analyze_symmetry_skips_midline_and_out_of_pool():
    pool = ["amygdala", "hippocampus", "brain stem"]
    mirrors = [
        {"src_name": "brain stem", "tgt_name": "left hippocampus",
         "connection_type": "structural"},  # midline 参与 → 跳过
        {"src_name": "left amygdala", "tgt_name": "left outside",
         "connection_type": "structural"},  # 池外 → 跳过
        {"src_name": "left amygdala", "tgt_name": "left amygdala",
         "connection_type": "structural"},  # 自环 → 跳过
    ]
    s = analyze_symmetry(pool, mirrors)
    assert s["counts"] == {"A1": 0, "A2": 0, "B": 0}


# ---- 功能合理性 ----

def test_find_functional_gap_candidates():
    pool = ["amygdala", "hippocampus", "prefrontal cortex", "thalamus proper"]
    finals = [
        {"src_name": "Amygdala", "tgt_name": "Hippocampus",
         "connection_type": "structural"},  # 已有连接 → 不算候选
    ]
    functions = [
        {"region_name": "left amygdala", "function_term": "memory"},
        {"region_name": "right amygdala", "function_term": "memory"},
        {"region_name": "hippocampus", "function_term": "memory"},  # 共享 memory
        {"region_name": "left prefrontal cortex", "function_term": "memory"},
        {"region_name": "thalamus proper", "function_term": "attention"},  # 无共享
    ]
    cands = find_functional_gap_candidates(pool, finals, functions)
    pairs = {tuple(c["region_pair"]) for c in cands}
    assert ("amygdala", "hippocampus") not in pairs  # 已有连接
    assert ("hippocampus", "prefrontal cortex") in pairs  # 共享 memory(字母序)
    assert ("amygdala", "prefrontal cortex") in pairs
    assert ("thalamus proper", "amygdala") not in pairs  # 无共享功能
    mem_c = next(c for c in cands
                 if c["region_pair"] == ("hippocampus", "prefrontal cortex"))
    assert "memory" in mem_c["shared_functions"]


# ---- 汇总候选 ----

def test_build_supplementation_candidates_merges_all_kinds():
    matrix = {"uncovered_regions": ["cerebellum exterior"]}
    degree = {"zero_degree_regions": ["cerebellum exterior", "ventral diencephalon"]}
    symmetry = {
        "A1_high_confidence_missing": [
            {"region_pair": ("amygdala", "hippocampus"), "reason": "mirror missing",
             "existing": {"left_to_left": ["structural"]}}],
        "A2_possible_missing": [
            {"region_pair": ("amygdala", "thalamus proper"), "reason": "side missing",
             "existing": {"left_connections": ["structural"]}}],
    }
    functional = [{"region_pair": ("amygdala", "prefrontal cortex"),
                   "shared_functions": ["memory"]}]
    s = build_supplementation_candidates(matrix, degree, symmetry, functional)
    assert s["total_candidates"] == 5
    assert s["by_kind"] == {
        "functional_gap": 1, "symmetry_A1": 1, "symmetry_A2": 1,
        "uncovered_region": 1, "zero_degree_region": 1}
    kinds = {c["kind"] for c in s["candidates"]}
    assert kinds == {"uncovered_region", "zero_degree_region", "symmetry_A1",
                     "symmetry_A2", "functional_gap"}
    # 零度区域与未覆盖区域重叠时不重复
    zero = [c for c in s["candidates"] if c["kind"] == "zero_degree_region"]
    assert zero[0]["region"] == "ventral diencephalon"


def test_build_supplementation_candidates_empty():
    s = build_supplementation_candidates(
        {"uncovered_regions": []}, {"zero_degree_regions": []},
        {"A1_high_confidence_missing": [], "A2_possible_missing": []}, [])
    assert s["total_candidates"] == 0
    assert s["by_kind"] == {}
