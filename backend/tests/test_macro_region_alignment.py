"""Macro96 Region Hierarchy Alignment V1 — 纯函数测试。

覆盖:解剖学先验表 / 各层存在状态分析 / part_of_candidate 生成(左右成对、
provenance 完整)/ cycle guard(自环、环、合法新增)/ 幂等 / 规划分类
(已映射 / 新发现 / 无法判断 / 冲突)。全部为纯函数测试,无 DB 依赖,无写入。
"""

from app.services.macro_region_alignment_service import (
    ALIGNMENT_MAP,
    ASSERTION_TYPE,
    CONFIDENCE,
    GENERATION_METHOD,
    RELATION_TYPE,
    analyze_region_status,
    build_hierarchy_candidates,
    has_cycle,
    is_duplicate_candidate,
    plan_alignment,
)

CONCEPTS = list(ALIGNMENT_MAP.keys())

# ---- 测试数据 helper ----

def _cand(rid, name, canon_name="Cerebellum", aligned=True):
    return {"id": rid, "en_name": name, "alignment_status": "aligned" if aligned else "pending",
            "canonical_region_id": f"canon-{canon_name.lower()}" if aligned else None,
            "canonical_region_name": canon_name if aligned else None}


def _canon(cid, name, status="active"):
    return {"id": cid, "canonical_name_en": name, "status": status}


def _hier(child, parent, source="macro96_pool_mapping"):
    return {"child_region_id": child, "parent_region_id": parent,
            "child_region_name": child, "parent_region_name": parent, "source": source}


# ---- 解剖学先验 ----

def test_alignment_map_complete():
    assert ALIGNMENT_MAP == {
        "cerebellum exterior": "Cerebellum",
        "cerebellum white matter": "Cerebellum",
        "ventral diencephalon": "Diencephalon",
    }


# ---- 存在状态分析 ----

def test_analyze_region_status_reports_layers():
    concepts = ["cerebellum exterior", "ventral diencephalon"]
    canonical_names = ["Cerebellum", "Diencephalon", "Amygdala"]
    hier = [_hier("Cerebellar vermal lobules i-v", "Cerebellum"),
            _hier("Cerebellum", "Brain")]
    aliases = [{"alias": "CB"}, {"alias": "DI"}]
    atlas = [{"atlas_region_name": "Cerebellum"}, {"atlas_region_name": "Thalamus proper"}]
    cand_rows = [_cand("c1", "left cerebellum exterior"), _cand("c2", "right cerebellum exterior"),
                 _cand("c3", "left ventral diencephalon", canon_name="Diencephalon")]
    st = analyze_region_status(concepts, canonical_names, hier, aliases, atlas, cand_rows)
    ce = st["cerebellum exterior"]
    assert ce["has_canonical_region"] is False        # 细分概念在 canonical 无实体
    assert ce["has_parent_edge"] is False             # 无 part_of 边
    assert ce["has_alias"] is False
    assert ce["has_atlas_mapping"] is False
    assert ce["candidate_alignment_count"] == 2       # 左右 2 行已对齐
    assert ce["candidate_alignment_targets"] == ["Cerebellum"]
    assert ce["expected_parent"] == "Cerebellum"
    vd = st["ventral diencephalon"]
    assert vd["candidate_alignment_targets"] == ["Diencephalon"]


def test_analyze_region_status_ignores_unaligned_rows():
    st = analyze_region_status(
        ["cerebellum exterior"], ["Cerebellum"], [], [], [],
        [_cand("c1", "left cerebellum exterior", aligned=False)])
    assert st["cerebellum exterior"]["candidate_alignment_count"] == 0


# ---- 候选生成 ----

def test_build_hierarchy_candidates_generates_6_bilateral_pairs():
    cand_rows = [
        _cand("lce", "left cerebellum exterior"),
        _cand("rce", "right cerebellum exterior"),
        _cand("lcw", "left cerebellum white matter"),
        _cand("rcw", "right cerebellum white matter"),
        _cand("lvd", "left ventral diencephalon", canon_name="Diencephalon"),
        _cand("rvd", "right ventral diencephalon", canon_name="Diencephalon"),
    ]
    canon_by_name = {"cerebellum": _canon("cereb", "Cerebellum"),
                     "diencephalon": _canon("di", "Diencephalon")}
    cands = build_hierarchy_candidates(cand_rows, canon_by_name)
    assert len(cands) == 6
    for g in cands:
        assert g["child_region_id"] != g["parent_region_id"]  # child != parent
        assert g["relation_type"] == RELATION_TYPE == "part_of_candidate"
        assert g["evidence_source"] == "macro96_pool_anatomy + candidate_layer_alignment"
        assert g["confidence"] == CONFIDENCE == 0.9
        assert g["generation_method"] == GENERATION_METHOD
        assert g["assertion_type"] == ASSERTION_TYPE == "candidate"
        assert g["status"] == "candidate"
        assert g["provenance_json"]["rule"] == "anatomical_part_of"
        assert g["provenance_json"]["basis"] == ["macro96_pool_anatomy",
                                                 "candidate_layer_alignment"]


def test_build_hierarchy_candidates_parents_and_pairs_correct():
    cand_rows = [
        _cand("lce", "left cerebellum exterior"),
        _cand("rce", "right cerebellum exterior"),
        _cand("lvd", "left ventral diencephalon", canon_name="Diencephalon"),
        _cand("rvd", "right ventral diencephalon", canon_name="Diencephalon"),
    ]
    canon_by_name = {"cerebellum": _canon("cereb", "Cerebellum"),
                     "diencephalon": _canon("di", "Diencephalon")}
    cands = build_hierarchy_candidates(cand_rows, canon_by_name)
    by_child = {g["child_region_id"]: g for g in cands}
    assert by_child["lce"]["parent_region_id"] == "cereb"
    assert by_child["lce"]["parent_region_name"] == "Cerebellum"
    assert by_child["rce"]["parent_region_id"] == "cereb"
    assert by_child["lvd"]["parent_region_id"] == "di"
    # bilateral 成对
    assert by_child["lce"]["provenance_json"]["bilateral_pair"] == "right cerebellum exterior"
    assert by_child["rce"]["provenance_json"]["bilateral_pair"] == "left cerebellum exterior"


def test_build_hierarchy_candidates_skips_missing_parent():
    cand_rows = [_cand("lce", "left cerebellum exterior")]
    canon_by_name = {}  # Cerebellum 缺失 → 不生成
    assert build_hierarchy_candidates(cand_rows, canon_by_name) == []


# ---- cycle guard ----

def test_has_cycle_acyclic_graph():
    edges = [("a", "b"), ("b", "c"), ("c", "d")]
    assert has_cycle(edges, []) is False
    # 合法新增:叶子挂到既有节点
    assert has_cycle(edges, [("e", "a")]) is False


def test_has_cycle_detects_cycle():
    edges = [("a", "b"), ("b", "c"), ("c", "a")]  # a->b->c->a 环
    assert has_cycle(edges, []) is True


def test_has_cycle_detects_self_loop():
    assert has_cycle([], [("a", "a")]) is True  # child == parent


def test_has_cycle_new_edge_creates_cycle():
    edges = [("a", "b"), ("b", "c")]
    assert has_cycle(edges, [("c", "b")]) is True  # b->c->b


def test_has_cycle_candidate_edges_into_canonical_tree():
    # 既有 canonical 树 + candidate 层节点(仅出边)→ 无环
    edges = [("Cerebellum", "Brain"), ("Diencephalon", "Brain"),
             ("Thalamus proper", "Diencephalon")]
    new_edges = [("lce-cand", "Cerebellum"), ("rce-cand", "Cerebellum"),
                 ("lvd-cand", "Diencephalon")]
    assert has_cycle(edges, new_edges) is False


# ---- 幂等 ----

def test_is_duplicate_candidate():
    g = {"child_region_id": "lce", "parent_region_id": "cereb",
         "relation_type": "part_of_candidate"}
    assert is_duplicate_candidate(g, [g]) is True
    other = {"child_region_id": "rce", "parent_region_id": "cereb",
             "relation_type": "part_of_candidate"}
    assert is_duplicate_candidate(g, [other]) is False


# ---- 规划 ----

def test_plan_alignment_full_flow():
    cand_rows = [
        _cand("lce", "left cerebellum exterior"),
        _cand("rce", "right cerebellum exterior"),
        _cand("lcw", "left cerebellum white matter"),
        _cand("rcw", "right cerebellum white matter"),
        _cand("lvd", "left ventral diencephalon", canon_name="Diencephalon"),
        _cand("rvd", "right ventral diencephalon", canon_name="Diencephalon"),
    ]
    canon_rows = [_canon("cereb", "Cerebellum"), _canon("di", "Diencephalon")]
    hier = [_hier("Cerebellum", "Brain"), _hier("Diencephalon", "Brain"),
            _hier("Thalamus proper", "Diencephalon")]
    plan = plan_alignment(CONCEPTS, canon_rows, hier, [], [], cand_rows, [])
    c = plan["counts"]
    assert c["concepts_total"] == 3
    assert c["existing_mapped_rows"] == 6       # candidate 层已对齐
    assert c["generated_candidates"] == 6       # 新发现 part_of 候选
    assert c["unresolved_concepts"] == 0
    assert c["conflict_candidates"] == 0
    assert c["duplicate_candidates"] == 0
    assert c["cycle_detected"] is False
    assert len(plan["candidates"]) == 6


def test_plan_alignment_idempotent_against_existing():
    cand_rows = [_cand("lce", "left cerebellum exterior"),
                 _cand("rce", "right cerebellum exterior")]
    canon_rows = [_canon("cereb", "Cerebellum")]
    existing = [{"child_region_id": "lce", "parent_region_id": "cereb",
                 "relation_type": "part_of_candidate"}]
    plan = plan_alignment(["cerebellum exterior"], canon_rows, [], [], [],
                          cand_rows, existing)
    assert plan["counts"]["generated_candidates"] == 1
    assert plan["counts"]["duplicate_candidates"] == 1


def test_plan_alignment_unresolved_when_no_candidate_rows():
    plan = plan_alignment(CONCEPTS, [_canon("cereb", "Cerebellum"),
                                     _canon("di", "Diencephalon")],
                          [], [], [], [], [])
    assert plan["counts"]["unresolved_concepts"] == 3
    reasons = {u["concept"]: u["reason"] for u in plan["unresolved"]}
    assert reasons == {"cerebellum exterior": "no_candidate_alignment",
                       "cerebellum white matter": "no_candidate_alignment",
                       "ventral diencephalon": "no_candidate_alignment"}


def test_plan_alignment_conflict_on_mismatch():
    # candidate 层对齐到 Amygdala(与解剖先验 Cerebellum 矛盾)→ conflict
    cand_rows = [_cand("lce", "left cerebellum exterior", canon_name="Amygdala")]
    canon_rows = [_canon("cereb", "Cerebellum"), _canon("amy", "Amygdala")]
    plan = plan_alignment(["cerebellum exterior"], canon_rows, [], [], [],
                          cand_rows, [])
    assert plan["counts"]["conflict_candidates"] == 1
    assert plan["counts"]["generated_candidates"] == 0
    assert plan["conflict"][0]["reason"] == "alignment_mismatch"
