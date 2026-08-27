"""Macro Connection A1 Hemisphere Symmetry Candidate Generation V1 — 纯函数测试。

覆盖:mirror 源查找(side/方向/类型匹配)/类型归一化/candidate 构建
(provenance 完整、推断侧别、未映射概念)/幂等键/冲突检测/生成规划分类。
全部为纯函数测试,无 DB 依赖,无写入。
"""

from app.services.macro_connection_symmetry_candidate_service import (
    ASSERTION_TYPE,
    GENERATION_METHOD,
    RULE,
    build_candidate,
    candidate_key,
    find_mirror_source,
    is_conflict,
    is_duplicate,
    normalize_connection_type,
    plan_generation,
)

# ---- 测试数据 helper ----

def _mirror(cid, src, tgt, ctype="structural_connection", mod="structural_connection",
            conf=0.9, directionality="directed"):
    return {"id": cid, "src_name": src, "tgt_name": tgt, "connection_type": ctype,
            "directionality": directionality, "modality": mod, "confidence": conf}


def _a1(pair, missing_side, existing_types):
    # existing 键 = 已有侧的键(与 coverage JSON 结构一致:missing left → right_to_right)
    existing_side = "right" if missing_side == "left" else "left"
    side_key = {"left": "left_to_left", "right": "right_to_right"}[existing_side]
    return {"region_pair": pair, "missing_side": missing_side,
            "existing": {side_key: existing_types}}


def _canon(rid, name, laterality="bilateral"):
    return {"id": rid, "canonical_name_en": name, "laterality": laterality}


# ---- 类型归一化 ----

def test_normalize_connection_type_maps_mirror_vocabulary():
    assert normalize_connection_type("structural_connection") == "structural"
    assert normalize_connection_type("functional_connectivity") == "functional"
    assert normalize_connection_type("uncertain_connection") == "uncertain"
    assert normalize_connection_type("association_connection") == "association"
    assert normalize_connection_type(None) == "unknown"
    assert normalize_connection_type("custom_type") == "custom_type"  # 未知类型原样保留


# ---- mirror 源查找 ----

def test_find_mirror_source_matches_existing_side_only():
    a1 = _a1(["amygdala", "hippocampus"], "left", ["structural_connection"])
    # missing=left → 依据为 right side;left side 连接不匹配
    conns = [
        _mirror("m1", "left amygdala", "left hippocampus"),
        _mirror("m2", "right amygdala", "right hippocampus"),
    ]
    found = find_mirror_source(a1, conns)
    assert [m["id"] for m in found] == ["m2"]


def test_find_mirror_source_accepts_either_direction():
    a1 = _a1(["amygdala", "hippocampus"], "right", ["structural_connection"])
    # 字母序 pair 是 amygdala→hippocampus;反向 mirror 连接也应匹配(保留原方向)
    conns = [_mirror("m1", "left hippocampus", "left amygdala")]
    found = find_mirror_source(a1, conns)
    assert [m["id"] for m in found] == ["m1"]
    assert found[0]["src_name"] == "left hippocampus"  # 原方向保留


def test_find_mirror_source_filters_connection_type():
    a1 = _a1(["amygdala", "hippocampus"], "left", ["structural_connection"])
    conns = [
        _mirror("m1", "right amygdala", "right hippocampus", ctype="functional_connectivity"),
        _mirror("m2", "right amygdala", "right hippocampus", ctype="structural_connection"),
    ]
    found = find_mirror_source(a1, conns)
    assert [m["id"] for m in found] == ["m2"]


def test_find_mirror_source_no_match_returns_empty():
    a1 = _a1(["amygdala", "hippocampus"], "left", ["structural_connection"])
    assert find_mirror_source(a1, [_mirror("m1", "left amygdala", "left hippocampus")]) == []


# ---- candidate 构建 ----

def test_build_candidate_provenance_complete():
    a1 = _a1(["amygdala", "hippocampus"], "left", ["structural_connection"])
    region_map = {"amygdala": "r1", "hippocampus": "r2"}
    cand = build_candidate(_mirror("m2", "right amygdala", "right hippocampus"), a1, region_map)
    p = cand["provenance_json"]
    assert p["rule"] == RULE == "hemisphere_symmetry"
    assert p["original_side"] == "right"
    assert p["inferred_side"] == "left"
    sc = p["source_connection"]
    assert sc["mirror_connection_id"] == "m2"
    assert sc["source_region_name"] == "right amygdala"
    assert sc["connection_type"] == "structural_connection"
    assert sc["directionality"] == "directed"
    assert sc["confidence"] == 0.9
    ic = p["inferred_candidate"]
    assert ic["source_region"] == "left amygdala"    # 推断侧别(对侧)
    assert ic["target_region"] == "left hippocampus"
    assert ic["inferred_side_pair"] == "left amygdala_to_left hippocampus"
    assert p["generation_method"] == GENERATION_METHOD


def test_build_candidate_field_inheritance():
    a1 = _a1(["amygdala", "hippocampus"], "left", ["structural_connection"])
    region_map = {"amygdala": "r1", "hippocampus": "r2"}
    cand = build_candidate(_mirror("m2", "right amygdala", "right hippocampus"), a1, region_map)
    assert cand["source_region_id"] == "r1"
    assert cand["target_region_id"] == "r2"
    assert cand["source_region_name"] == "left amygdala"
    assert cand["target_region_name"] == "left hippocampus"
    assert cand["connection_type"] == "structural"
    assert cand["direction"] == "directed"           # 完全继承已有连接
    assert cand["modality"] == "structural_connection"
    assert cand["source_connection_id"] == "m2"      # 依据必填
    assert cand["generation_method"] == GENERATION_METHOD == "hemisphere_symmetry_v1"
    assert cand["assertion_type"] == ASSERTION_TYPE == "candidate"
    assert cand["status"] == "candidate"
    assert cand["missing_side"] == "left"
    assert cand["region_unmapped"] is False
    assert cand["suggested_mapping"] is None


def test_build_candidate_unmapped_region_kept_with_suggestion():
    a1 = _a1(["amygdala", "cerebellum exterior"], "left", ["functional_connectivity"])
    region_map = {"amygdala": "r1"}  # cerebellum exterior 不在 canonical
    cand = build_candidate(
        _mirror("m9", "right amygdala", "right cerebellum exterior",
                ctype="functional_connectivity"), a1, region_map)
    assert cand["source_region_id"] == "r1"
    assert cand["target_region_id"] is None          # 未映射 → NULL id
    assert cand["target_region_name"] == "left cerebellum exterior"  # 名称保留
    assert cand["region_unmapped"] is True
    # 未映射概念本身 + 已知映射目标都列出(人工决定)
    assert cand["suggested_mapping"]["suggested_macro_targets"] == ["Cerebellum", "amygdala"]
    assert cand["connection_type"] == "functional"


# ---- 幂等键 ----

def test_candidate_key_falls_back_to_names_for_null_ids():
    a1 = _a1(["amygdala", "cerebellum exterior"], "left", ["functional_connectivity"])
    region_map = {"amygdala": "r1"}
    c1 = build_candidate(
        _mirror("m9", "right amygdala", "right cerebellum exterior",
                ctype="functional_connectivity"), a1, region_map)
    c2 = build_candidate(
        _mirror("m9", "right amygdala", "right cerebellum exterior",
                ctype="functional_connectivity"), a1, region_map)
    assert candidate_key(c1) == candidate_key(c2)
    # 名称兜底后键中不含 None(同一源连接 + 归一化名称对 + type)
    assert None not in candidate_key(c1)


# ---- 冲突检测 ----

def test_is_conflict_canonical_exists():
    cand = {"source_region_id": "r1", "target_region_id": "r2", "connection_type": "structural"}
    canon = [{"source_region_id": "r1", "target_region_id": "r2",
              "connection_type": "structural", "status": "active"}]
    assert is_conflict(cand, canon) is True


def test_is_conflict_reverse_direction_also_conflicts():
    cand = {"source_region_id": "r1", "target_region_id": "r2", "connection_type": "structural"}
    canon = [{"source_region_id": "r2", "target_region_id": "r1",
              "connection_type": "structural", "status": "active"}]
    assert is_conflict(cand, canon) is True


def test_is_conflict_ignores_deprecated_and_other_types():
    cand = {"source_region_id": "r1", "target_region_id": "r2", "connection_type": "structural"}
    canon = [
        {"source_region_id": "r1", "target_region_id": "r2",
         "connection_type": "structural", "status": "deprecated"},
        {"source_region_id": "r1", "target_region_id": "r2",
         "connection_type": "functional", "status": "active"},
        {"source_region_id": "r3", "target_region_id": "r4",
         "connection_type": "structural", "status": "active"},
    ]
    assert is_conflict(cand, canon) is False


# ---- 重复检测 ----

def test_is_duplicate_same_key():
    a1 = _a1(["amygdala", "hippocampus"], "left", ["structural_connection"])
    region_map = {"amygdala": "r1", "hippocampus": "r2"}
    c1 = build_candidate(_mirror("m2", "right amygdala", "right hippocampus"), a1, region_map)
    c2 = build_candidate(_mirror("m2", "right amygdala", "right hippocampus"), a1, region_map)
    assert is_duplicate(c1, [c2]) is True
    c3 = build_candidate(_mirror("m3", "right amygdala", "right hippocampus"), a1, region_map)
    assert is_duplicate(c1, [c3]) is False  # 不同源连接 → 不同候选


# ---- 生成规划 ----

def test_plan_generation_classifies_all_outcomes():
    a1_items = [
        _a1(["amygdala", "hippocampus"], "left", ["structural_connection"]),     # generated
        _a1(["caudate", "putamen"], "left", ["structural_connection"]),          # conflict
        _a1(["pons", "medulla"], "right", ["structural_connection"]),            # skipped
    ]
    mirror_conns = [
        _mirror("m1", "right amygdala", "right hippocampus"),
        _mirror("m2", "right caudate", "right putamen"),
        # pons/medulla 无任何 mirror 连接 → no_mirror_source
    ]
    canonical_rows = [_canon("r1", "Amygdala"), _canon("r2", "Hippocampus"),
                      _canon("r3", "Caudate"), _canon("r4", "Putamen")]
    canon_conns = [{"source_region_id": "r3", "target_region_id": "r4",
                    "connection_type": "structural", "status": "active"}]
    plan = plan_generation(a1_items, mirror_conns, canonical_rows, canon_conns, [])
    c = plan["counts"]
    assert c["a1_total"] == 3
    assert c["generated"] == 1
    assert c["conflict"] == 1
    assert c["skipped"] == 1
    assert c["duplicate"] == 0
    assert plan["skip_reasons"] == {"no_mirror_source": 1}
    assert plan["generated"][0]["source_connection_id"] == "m1"


def test_plan_generation_unmapped_generates_not_skips():
    a1_items = [_a1(["amygdala", "cerebellum exterior"], "left",
                    ["functional_connectivity"])]
    mirror_conns = [_mirror("m9", "right amygdala", "right cerebellum exterior",
                            ctype="functional_connectivity")]
    canonical_rows = [_canon("r1", "Amygdala")]
    plan = plan_generation(a1_items, mirror_conns, canonical_rows, [], [])
    assert plan["counts"]["generated"] == 1
    assert plan["counts"]["skipped"] == 0
    assert plan["generated"][0]["region_unmapped"] is True


def test_plan_generation_duplicate_against_existing():
    a1_items = [_a1(["amygdala", "hippocampus"], "left", ["structural_connection"])]
    mirror_conns = [_mirror("m1", "right amygdala", "right hippocampus")]
    canonical_rows = [_canon("r1", "Amygdala"), _canon("r2", "Hippocampus")]
    existing = [{"source_region_id": "r1", "target_region_id": "r2",
                 "connection_type": "structural", "source_connection_id": "m1"}]
    plan = plan_generation(a1_items, mirror_conns, canonical_rows, [], existing)
    assert plan["counts"]["generated"] == 0
    assert plan["counts"]["duplicate"] == 1
