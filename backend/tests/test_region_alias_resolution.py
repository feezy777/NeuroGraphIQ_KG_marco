"""Phase Q1.5 — canonical_region_aliases 实体解析增强测试。

规格要求的 8 项行为（test_region_alias_resolution.py）：
1. 海马→Hippocampus（canonical_name_cn 精确）
2. 海马体→Hippocampus（manual_curated 中文别名）
3. hippocampal formation→Hippocampus（英文别名）
4. PFC→Prefrontal cortex（缩写别名）
5. 大脑→Cerebrum（canonical_name_cn 精确）
6. Atlas 名称查询（atlas 映射 → 别名，实时 join）
7. 未知词 → unresolved（不报错）
8. 多候选不自动选择（模糊候选随 source_entities 返回，entity 为 null）

确定性策略：自建 `q15_` 前缀数据（独特名，避免与真实 canonical 名称双
匹配），断言解析层级 / 溯源 / 置信度与规格行为等价；另加真实数据条件测试
（开发库有对应数据时直接验证规格问题原文，无数据则 skip）。

额外覆盖规格未列但本阶段承诺的行为：
- 7 级优先级：canonical cn/en 先于 alias，manual_curated alias 先于 atlas 名
- entity_match_detail 完整溯源（matched_by / alias / source / confidence）
- abbr 别名置信度 0.85、atlas 别名置信度 0.9
- atlas 缩写（region_acronym）同样可解析
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.database import AsyncSessionLocal
from app.main import app
from app.models.canonical_region_alias import CanonicalRegionAlias
from app.models.multiscale import AtlasRegionResource
from app.schemas.canonical_region import CanonicalRegionCreate
from app.schemas.multiscale import AtlasRegionMappingCreate
from app.services import canonical_region_service as crs
from app.services import multiscale_service as mss

TEST_PREFIX = "q15_"


def _run(coro):
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except Exception:
        pass
    return asyncio.run(coro)


async def _mk(session, code: str, *, en: str, cn: str, level: str = "clinical"):
    return await crs.create_canonical_region(
        session,
        CanonicalRegionCreate(
            region_code=code,
            canonical_name_en=en,
            canonical_name_cn=cn,
            species="human",
            granularity_level=level,
            hemisphere_policy="bilateral",
            status="active",
            confidence=0.9,
            created_by=TEST_PREFIX,
        ),
    )


async def _alias(session, region, alias: str, lang: str, confidence: float) -> None:
    session.add(
        CanonicalRegionAlias(
            region_id=region.id,
            alias=alias,
            alias_language=lang,
            source="manual_curated",
            confidence=confidence,
        )
    )
    await session.flush()


async def _atlas_resource(session, *, region_name: str, acronym: str | None, native_id: str) -> AtlasRegionResource:
    res = AtlasRegionResource(
        atlas_name="Q15 Test Atlas",
        atlas_version="v1",
        atlas_region_id=native_id,
        region_name=region_name,
        region_acronym=acronym,
        species="human",
        hemisphere="unknown",
        status="active",
    )
    session.add(res)
    await session.flush()
    return res


async def _atlas_mapping(session, resource: AtlasRegionResource, region) -> None:
    await mss.create_atlas_mapping(
        session,
        AtlasRegionMappingCreate(
            atlas_region_id=resource.id,
            canonical_region_id=region.id,
            mapping_type="exact",
            confidence=0.9,
            species_relation="same_species",
            match_details={},
            provenance={},
            created_by=TEST_PREFIX,
        ),
    )


async def _cleanup_q15(session) -> None:
    """按 TEST_PREFIX 清理（FK 级联：mapping 随 resource 删、alias 随 region 删）。

    注意 atlas 资源名是「Q15 Test Atlas」（大写 Q15），必须用 ILIKE 大小写不敏感匹配，
    否则上一轮残留资源会撞 uq_atlas_region_resources_native 唯一约束。
    """
    await session.execute(
        text("DELETE FROM atlas_region_resources WHERE atlas_name ILIKE :p"), {"p": f"{TEST_PREFIX}%"}
    )
    await session.execute(
        text("DELETE FROM canonical_brain_regions WHERE region_code LIKE :p"),
        {"p": f"ng:br:{TEST_PREFIX}%"},
    )
    await session.commit()


@pytest.fixture()
def q15_db():
    """自建别名解析测试图谱：

    - Q15测试海马：别名 海马体测试(cn,0.95) / Q15 Hippocampal Formation(en,0.95) / Q15HF(abbr,0.85)
    - Q15前额叶：别名 Q15PFC(abbr,0.85)（不用 PFC——真实库 20260830 迁移已挂
      PFC→prefrontal_cortex，同名会造成多候选，违背 q15_ 独特名前缀原则）
    - Q15模糊海马甲/乙：模糊候选对（共享前缀 7/6 字符）
    - Q15别名目标：atlas 资源 Q15 Atlas Zone(Q15AZ) 映射
    - Q15手工优先 / Q15地图优先：同名「Q15共享名」分别挂 manual alias 与 atlas 名，
      验证 P3(manual alias) 优先于 P4(atlas 名)
    """

    async def _seed():
        async with AsyncSessionLocal() as session:
            await _cleanup_q15(session)  # 幂等：先清上一轮残留（含失败运行）
            hippo = await _mk(session, "ng:br:q15_hippocampus", en="Q15 Test Hippocampus", cn="Q15测试海马")
            pfc = await _mk(session, "ng:br:q15_prefrontal", en="Q15 Prefrontal Cortex", cn="Q15前额叶")
            fuzzy_a = await _mk(session, "ng:br:q15_fuzzy_a", en="Q15 Fuzzy Hippocampus Alpha", cn="Q15模糊海马甲")
            fuzzy_b = await _mk(session, "ng:br:q15_fuzzy_b", en="Q15 Fuzzy Hippocampus Beta", cn="Q15模糊海马乙")
            alias_tgt = await _mk(session, "ng:br:q15_alias_tgt", en="Q15 Alias Target", cn="Q15别名目标")
            prio_manual = await _mk(session, "ng:br:q15_prio_manual", en="Q15 Manual Priority", cn="Q15手工优先")
            prio_atlas = await _mk(session, "ng:br:q15_prio_atlas", en="Q15 Atlas Priority", cn="Q15地图优先")
            await _alias(session, hippo, "海马体测试", "cn", 0.95)
            await _alias(session, hippo, "Q15 Hippocampal Formation", "en", 0.95)
            await _alias(session, hippo, "Q15HF", "abbr", 0.85)
            await _alias(session, pfc, "Q15PFC", "abbr", 0.85)
            await _alias(session, prio_manual, "Q15共享名", "cn", 0.95)

            zone = await _atlas_resource(session, region_name="Q15 Atlas Zone", acronym="Q15AZ", native_id="Q15:AZ1")
            await _atlas_mapping(session, zone, alias_tgt)
            shared = await _atlas_resource(session, region_name="Q15共享名", acronym=None, native_id="Q15:SH1")
            await _atlas_mapping(session, shared, prio_atlas)

            await session.commit()
            return {
                "hippo": hippo.id,
                "pfc": pfc.id,
                "alias_tgt": alias_tgt.id,
                "prio_manual": prio_manual.id,
                "prio_atlas": prio_atlas.id,
            }

    ids = _run(_seed())

    yield ids

    async def _cleanup():
        async with AsyncSessionLocal() as session:
            await _cleanup_q15(session)

    _run(_cleanup())


def _query(question: str) -> dict:
    with TestClient(app) as client:
        resp = client.post("/api/ontology-query", json={"question": question})
        assert resp.status_code == 200, resp.text
        return resp.json()


# --------------------------------------------------------------------------- #
# 真实数据条件测试（开发库有数据时直接验证规格问题原文，无则 skip）
# --------------------------------------------------------------------------- #


def _real_region_code(cn_name: str) -> str | None:
    async def _f():
        async with AsyncSessionLocal() as session:
            row = (
                await session.execute(
                    text(
                        "SELECT region_code FROM canonical_brain_regions "
                        "WHERE canonical_name_cn = :n AND status = 'active'"
                    ),
                    {"n": cn_name},
                )
            ).first()
            return row[0] if row else None

    return _run(_f())


def _alias_target(alias_text: str) -> str | None:
    """返回真实库中该别名的目标 region_code（无则 None）。"""

    async def _f():
        async with AsyncSessionLocal() as session:
            row = (
                await session.execute(
                    text(
                        "SELECT r.region_code FROM canonical_region_aliases a "
                        "JOIN canonical_brain_regions r ON r.id = a.region_id "
                        "WHERE a.alias = :n AND r.status = 'active'"
                    ),
                    {"n": alias_text},
                )
            ).first()
            return row[0] if row else None

    return _run(_f())


def _atlas_pair_label() -> str | None:
    """找一个映射到 ≥2 个 canonical 脑区（L/R 对）的 atlas 名。

    这些标签已被 atlas alias seed 写入 canonical_region_aliases（每半球一行），
    P3a 会命中两行 → 多候选不自动选择（L/R 半球歧义）。
    """

    async def _f():
        async with AsyncSessionLocal() as session:
            row = (
                await session.execute(
                    text(
                        """
                        SELECT ar.region_name FROM atlas_region_mappings m
                        JOIN atlas_region_resources ar ON ar.id = m.atlas_region_id
                        JOIN canonical_brain_regions c ON c.id = m.canonical_region_id
                        WHERE m.status = 'active' AND ar.status = 'active'
                          AND m.species_relation = 'same_species'
                        GROUP BY ar.region_name HAVING COUNT(DISTINCT c.id) >= 2
                        ORDER BY ar.region_name LIMIT 1
                        """
                    )
                )
            ).first()
            return row[0] if row else None

    return _run(_f())


def test_1_real_海马_cn_exact():
    """规格 1：海马→Hippocampus（canonical_name_cn 精确）。"""
    code = _real_region_code("海马")
    if code is None:
        pytest.skip("开发库无 canonical_name_cn=海马 的 active 脑区")

    resp = _query("海马有哪些亚区")
    assert resp["entity"] is not None
    assert resp["entity"]["code"] == code
    assert resp["entity"]["matched_by"] == "canonical_name_cn"
    assert resp["entity_match_detail"]["source"] == "canonical_region"
    assert resp["entity_match_detail"]["confidence"] == 0.95


def test_2_real_海马体_alias():
    """规格 2：海马体→Hippocampus（manual_curated 中文别名）。"""
    code = _alias_target("海马体")
    if code is None:
        pytest.skip("开发库 canonical_region_aliases 无「海马体」别名")

    resp = _query("海马体有哪些亚区")
    assert resp["entity"] is not None
    assert resp["entity"]["code"] == code
    assert resp["entity"]["matched_by"] == "alias"
    detail = resp["entity_match_detail"]
    assert detail["matched_by"] == "alias"
    assert detail["alias"] == "海马体"
    assert detail["source"] == "manual_curated"
    assert detail["confidence"] == 0.95


def test_5_real_大脑_cn_exact():
    """规格 5：大脑→Cerebrum（canonical_name_cn 精确）。"""
    code = _real_region_code("大脑")
    if code is None:
        pytest.skip("开发库无 canonical_name_cn=大脑 的 active 脑区")

    resp = _query("大脑有哪些亚区")
    assert resp["entity"] is not None
    assert resp["entity"]["code"] == code
    assert resp["entity"]["matched_by"] == "canonical_name_cn"


# --------------------------------------------------------------------------- #
# 自建数据确定性测试（q15_db fixture）
# --------------------------------------------------------------------------- #


def test_2b_cn_alias_resolves_with_match_detail(q15_db):
    """规格 2（确定性）：中文别名命中 + 完整 entity_match_detail 溯源。"""
    resp = _query("海马体测试有哪些亚区")

    assert resp["entity"] is not None
    assert resp["entity"]["id"] == str(q15_db["hippo"])
    assert resp["entity"]["code"] == "ng:br:q15_hippocampus"
    assert resp["entity"]["matched_by"] == "alias"
    assert resp["entity_match_detail"] == {
        "matched_by": "alias",
        "alias": "海马体测试",
        "source": "manual_curated",
        "confidence": 0.95,
    }


def test_3_en_alias_resolves(q15_db):
    """规格 3：hippocampal formation→Hippocampus（英文别名）。

    注：真实库中「hippocampal formation」会经 P2 canonical_name_en 命中
    ng:br:hippocampal_formation（该脑区真实存在）——这是规格优先级
    （canonical en 先于 alias）的正确行为；此处用独特英文别名验证 alias 层。
    """
    resp = _query("Q15 Hippocampal Formation有哪些亚区")

    assert resp["entity"]["id"] == str(q15_db["hippo"])
    detail = resp["entity_match_detail"]
    assert detail["matched_by"] == "alias"
    assert detail["alias"] == "Q15 Hippocampal Formation"
    assert detail["source"] == "manual_curated"
    assert detail["confidence"] == 0.95


def test_4_abbr_alias_resolves(q15_db):
    """规格 4：缩写别名（置信度 0.85）→ canonical 实体。

    用独特名 Q15PFC 验证缩写层（真实库的 PFC→prefrontal_cortex 由 20260830
    迁移提供，测试数据若也用 PFC 会双命中 → 多候选，违背 q15_ 独特名前缀原则）。
    """
    resp = _query("Q15PFC有哪些亚区")

    assert resp["entity"]["id"] == str(q15_db["pfc"])
    assert resp["entity"]["name"] == "Q15前额叶"
    detail = resp["entity_match_detail"]
    assert detail["alias"] == "Q15PFC"
    assert detail["source"] == "manual_curated"
    assert detail["confidence"] == 0.85


def test_priority_canonical_en_before_alias(q15_db):
    """优先级：P2 canonical_name_en 先于 P3 alias（别名同名共存时）。"""
    resp = _query("Q15 Test Hippocampus有哪些亚区")

    assert resp["entity"]["id"] == str(q15_db["hippo"])
    assert resp["entity"]["matched_by"] == "canonical_name_en"
    assert resp["entity_match_detail"]["source"] == "canonical_region"
    assert resp["entity_match_detail"]["confidence"] == 0.95


def test_6_atlas_name_resolves_via_mapping(q15_db):
    """规格 6：Atlas 名称查询（atlas 映射 → 别名，source=atlas，0.9）。"""
    resp = _query("Q15 Atlas Zone有哪些亚区")

    assert resp["entity"]["id"] == str(q15_db["alias_tgt"])
    assert resp["entity"]["matched_by"] == "alias"
    assert resp["entity_match_detail"] == {
        "matched_by": "alias",
        "alias": "Q15 Atlas Zone",
        "source": "atlas",
        "confidence": 0.9,
    }


def test_6b_atlas_acronym_resolves_via_mapping(q15_db):
    """规格 6 扩展：atlas 缩写（region_acronym）同样命中。"""
    resp = _query("Q15AZ有哪些亚区")

    assert resp["entity"]["id"] == str(q15_db["alias_tgt"])
    assert resp["entity_match_detail"]["alias"] == "Q15AZ"
    assert resp["entity_match_detail"]["source"] == "atlas"
    assert resp["entity_match_detail"]["confidence"] == 0.9


def test_priority_manual_alias_before_atlas_name(q15_db):
    """优先级：P3 manual alias 先于 P4 atlas 名（同名「Q15共享名」）。"""
    resp = _query("Q15共享名有哪些亚区")

    assert resp["entity"]["id"] == str(q15_db["prio_manual"])
    assert resp["entity"]["matched_by"] == "alias"
    assert resp["entity_match_detail"]["source"] == "manual_curated"
    # 若 P3 缺失，P4 会把「Q15共享名」解析到 prio_atlas —— 不允许
    assert resp["entity"]["id"] != str(q15_db["prio_atlas"])


def test_7_unknown_word_unresolved(q15_db):
    """规格 7：未知词 → unresolved，不报错，无候选无溯源。"""
    resp = _query("QQQQQXYZ有哪些亚区")

    assert resp["intent"] == "unresolved"
    assert resp["entity"] is None
    assert resp["confidence"] == 0.0
    assert resp["source_entities"] == []
    assert resp["entity_match_detail"] is None
    assert resp["warnings"]  # 可解释性说明存在


def test_8_multi_candidate_no_auto_pick(q15_db):
    """规格 8：多候选不自动选择 — 模糊候选随 source_entities 返回。"""
    resp = _query("Q15模糊海马甲体有哪些亚区")

    assert resp["intent"] == "unresolved"
    assert resp["entity"] is None
    assert resp["entity_match_detail"] is None
    # 共享前缀占比：8/9 ≈ 0.89（甲，完整前缀命中），7/9 ≈ 0.78（乙）
    assert resp["source_entities"] == [
        {"candidate": "Q15模糊海马甲", "confidence": 0.89},
        {"candidate": "Q15模糊海马乙", "confidence": 0.78},
    ]
    assert any("候选" in w for w in resp["warnings"])


def test_6c_real_atlas_label_pair_returns_candidates():
    """规格 6（真实数据）：成对 atlas 标签（如 HCP-MMP「1」）→ 多候选不自动选择。

    标签「1」在 aliases 表中有两行（L/R 半球各一），P3a 同时命中 →
    entity 为 null，source_entities 返回两个 0.9 候选（不做自动选择）。
    """
    label = _atlas_pair_label()
    if label is None:
        pytest.skip("开发库无成对 same_species atlas 映射")

    resp = _query(f"{label}有哪些亚区")
    assert resp["entity"] is None
    assert resp["entity_match_detail"] is None
    assert len(resp["source_entities"]) >= 2
    assert all(it["confidence"] == 0.9 for it in resp["source_entities"])
    assert any("候选" in w for w in resp["warnings"])
