"""Macro96 Region Hierarchy Alignment 收口 — canonicalization 纯函数测试。

覆盖:anchor 定义完整性 / resolver(带侧别名、剥侧别、canonical 兜底、
未知名称)/ symmetry candidate 重解析(已映射侧保留、双侧 anchor、unresolved
分类)/ 全流程规划(anchor 就绪、环检测、统计)。全部纯函数测试,无 DB、无写入。
"""

from app.services.macro_connection_coverage_gap_service import normalize_region_name
from app.services.macro_region_alignment_service import ALIGNMENT_MAP
from app.services.macro_region_canonicalization_service import (
    CONFIDENCE,
    REGION_ANCHORS,
    RESOLVED_STATUS,
    build_alias_map,
    build_canonical_name_map,
    canonicalize_symmetry_candidates,
    normalize_concept,
    plan_canonicalization,
    resolve_region_name,
)

# 新 anchor 实体 id(测试固定值)
CEX = "cex-anchor"
CWM = "cwm-anchor"
VDI = "vdi-anchor"

FULL_ALIASES = [
    {"alias": "left cerebellum exterior", "region_id": CEX},
    {"alias": "right cerebellum exterior", "region_id": CEX},
    {"alias": "cerebellum exterior", "region_id": CEX},
    {"alias": "left cerebellum white matter", "region_id": CWM},
    {"alias": "right cerebellum white matter", "region_id": CWM},
    {"alias": "cerebellum white matter", "region_id": CWM},
    {"alias": "left ventral diencephalon", "region_id": VDI},
    {"alias": "right ventral diencephalon", "region_id": VDI},
    {"alias": "ventral diencephalon", "region_id": VDI},
]

FULL_CANONS = [
    {"id": "cereb", "canonical_name_en": "Cerebellum"},
    {"id": "di", "canonical_name_en": "Diencephalon"},
    {"id": CEX, "canonical_name_en": "Cerebellum Exterior"},
    {"id": CWM, "canonical_name_en": "Cerebellum White Matter"},
    {"id": VDI, "canonical_name_en": "Ventral Diencephalon"},
]


def _cand(cid, sname, sid, tname, tid, ctype="structural_connection"):
    return {"id": cid, "source_region_id": sid, "source_region_name": sname,
            "target_region_id": tid, "target_region_name": tname,
            "connection_type": ctype}


# ---- anchor 定义 ----

def test_region_anchors_complete():
    assert list(REGION_ANCHORS) == list(ALIGNMENT_MAP)
    for concept, spec in REGION_ANCHORS.items():
        assert spec["region_code"].startswith("ng:br:"), "region_code 格式"
        assert spec["canonical_name_en"], "英文名缺失"
        assert spec["parent_name"] == ALIGNMENT_MAP[concept], "parent 与解剖先验一致"
        assert spec["granularity_level"] == "clinical", "跟随 Macro96 池粒度"
        aliases = spec["aliases"]
        assert len(aliases) == 3, "每概念 3 个别名(左右 + 无侧别)"
        assert f"left {concept}" in aliases and f"right {concept}" in aliases
        assert concept in aliases


def test_resolved_status_and_confidence():
    assert RESOLVED_STATUS == "canonical_region_resolved"
    assert CONFIDENCE == 0.9


# ---- resolver ----

def test_resolve_region_name_lateralized_alias():
    amap = build_alias_map(FULL_ALIASES)
    cmap = build_canonical_name_map(FULL_CANONS)
    assert resolve_region_name("left cerebellum exterior", amap, cmap) == CEX
    assert resolve_region_name("RIGHT ventral diencephalon", amap, cmap) == VDI


def test_resolve_region_name_bare_concept_alias():
    amap = build_alias_map(FULL_ALIASES)
    cmap = build_canonical_name_map(FULL_CANONS)
    assert resolve_region_name("cerebellum white matter", amap, cmap) == CWM


def test_resolve_region_name_stripped_fallback():
    # 别名表缺该侧行:查询 right x,只有 left x + 无侧别 x → 剥侧别回退
    amap = build_alias_map([
        {"alias": "left cerebellum exterior", "region_id": CEX},
        {"alias": "cerebellum exterior", "region_id": CEX},
    ])
    cmap = build_canonical_name_map(FULL_CANONS)
    assert resolve_region_name("right cerebellum exterior", amap, cmap) == CEX


def test_resolve_region_name_canonical_fallback():
    amap = build_alias_map(FULL_ALIASES)
    cmap = build_canonical_name_map(FULL_CANONS)
    # 已知 canonical 名称(不在别名表)兜底命中
    assert resolve_region_name("Cerebellum", amap, cmap) == "cereb"
    assert resolve_region_name("Ventral Diencephalon", amap, cmap) == VDI


def test_resolve_region_name_unknown_returns_none():
    amap = build_alias_map(FULL_ALIASES)
    cmap = build_canonical_name_map(FULL_CANONS)
    assert resolve_region_name("wibble wobble", amap, cmap) is None
    assert resolve_region_name(None, amap, cmap) is None
    assert resolve_region_name("", amap, cmap) is None


def test_normalize_concept_and_region_name():
    assert normalize_concept("  LEFT Amygdala ") == "left amygdala"
    assert normalize_region_name("left cerebellum exterior") == "cerebellum exterior"
    assert normalize_region_name("right ventral diencephalon") == "ventral diencephalon"


# ---- symmetry candidate 重解析 ----

def test_canonicalize_all_resolved_keeping_mapped_side():
    cands = [
        _cand("c1", "left amygdala", "amy", "left cerebellum exterior", None),
        _cand("c2", "right ventral diencephalon", None, "right caudal middle frontal", "rcmf"),
        _cand("c3", "left cerebellum white matter", None, "right cerebellum exterior", None),
    ]
    amap = build_alias_map(FULL_ALIASES)
    cmap = build_canonical_name_map(FULL_CANONS)
    res = canonicalize_symmetry_candidates(cands, amap, cmap)
    assert len(res["resolved"]) == 3
    assert res["unresolved"] == []
    r1 = res["resolved"][0]
    assert r1["source_region_id"] == "amy"                 # 已映射侧保留
    assert r1["resolved_target_region_id"] == CEX          # 未映射侧解析到 anchor
    assert r1["target_was_anchor_resolved"] is True
    assert r1["source_was_anchor_resolved"] is False
    r2 = res["resolved"][1]
    assert r2["source_region_id"] == VDI
    assert r2["target_region_id"] == "rcmf"
    r3 = res["resolved"][2]
    assert r3["source_region_id"] == CWM
    assert r3["target_region_id"] == CEX


def test_canonicalize_unresolved_classification():
    cands = [
        _cand("c1", "left amygdala", "amy", "mystery region", None),
        _cand("c2", None, None, "right caudal middle frontal", "rcmf"),
    ]
    amap = build_alias_map(FULL_ALIASES)
    cmap = build_canonical_name_map(FULL_CANONS)
    res = canonicalize_symmetry_candidates(cands, amap, cmap)
    assert len(res["resolved"]) == 0
    assert len(res["unresolved"]) == 2
    by_id = {u["candidate_id"]: u for u in res["unresolved"]}
    assert by_id["c1"]["missing"] == ["target"]
    assert by_id["c2"]["missing"] == ["source"]
    assert all(u["reason"] == "unresolvable_region_name"
               for u in res["unresolved"])


# ---- 全流程规划 ----

def test_plan_canonicalization_full_flow():
    cands = [
        _cand("c1", "left amygdala", "amy", "left cerebellum exterior", None),
        _cand("c2", "right ventral diencephalon", None, "right caudal middle frontal", "rcmf"),
    ]
    hier = [{"child_region_id": "cereb", "parent_region_id": "brain"},
            {"child_region_id": "di", "parent_region_id": "brain"},
            {"child_region_id": CEX, "parent_region_id": "cereb"},
            {"child_region_id": CWM, "parent_region_id": "cereb"},
            {"child_region_id": VDI, "parent_region_id": "di"}]
    plan = plan_canonicalization(cands, FULL_ALIASES, FULL_CANONS, hier)
    c = plan["counts"]
    assert c["anchor_total"] == 3
    assert c["anchor_ready"] == 3
    assert c["candidates_total"] == 2
    assert c["resolved_candidates"] == 2
    assert c["unresolved_candidates"] == 0
    assert c["hierarchy_cycle_detected"] is False
    assert plan["alias_map_size"] == 9
    for a in plan["anchors"]:
        assert a["ready"] is True
        assert a["canonical_region_id"]
        assert a["parent_region_id"]
        assert a["alias_ready"] == a["alias_total"] == 3


def test_plan_canonicalization_anchor_not_ready_when_alias_missing():
    # 别名表缺 'cerebellum exterior' 无侧别名 → 该 anchor 不 ready
    partial = [a for a in FULL_ALIASES
               if a["alias"] != "cerebellum exterior"]
    plan = plan_canonicalization([], partial, FULL_CANONS, [])
    by_concept = {a["concept"]: a for a in plan["anchors"]}
    assert by_concept["cerebellum exterior"]["ready"] is False
    assert by_concept["cerebellum exterior"]["alias_ready"] == 2
    assert plan["counts"]["anchor_ready"] == 2


def test_plan_canonicalization_detects_cycle():
    hier = [{"child_region_id": "cereb", "parent_region_id": "brain"},
            {"child_region_id": "brain", "parent_region_id": "cereb"}]  # 环
    plan = plan_canonicalization([], FULL_ALIASES, FULL_CANONS, hier)
    assert plan["counts"]["hierarchy_cycle_detected"] is True
