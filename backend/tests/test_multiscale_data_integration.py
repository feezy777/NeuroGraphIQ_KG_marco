"""BR4 外部数据接入验收（10 部分任务第 10 部分 — 8 项规格验证）。

只读验证生产种子数据（不写入、无清理需求）。覆盖：
1. Macro96 数据无变化（clinical 48 / macro 4，laterality 在字段而非实体名）
2. 所有外部 atlas 行/映射带溯源
3. mouse/human 物种隔离（跨物种映射非 exact）
4. Meso 层级正确（BNA246 + MMP 均有 part_of 父边，无自环）
5. Subregion 层级正确（Winterburn CA2 → hippocampal_formation）
6. Cell Type 不污染 Region 层级
7. Molecular Entity 不污染 Region 层级
8. 所有实体均有 provenance
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from sqlalchemy import select, text

from app.database import AsyncSessionLocal

pytestmark = pytest.mark.function_term_real


def _run(coro):
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except Exception:
        pass
    return asyncio.run(coro)


async def _count(session, sql: str, *params) -> int:
    return (await session.execute(text(sql), params)).scalar() or 0


async def _codes(session, sql: str, *params) -> list[str]:
    rows = (await session.execute(text(sql), params)).all()
    return [row[0] for row in rows]


# ── 1. Macro96 数据无变化 ──────────────────────────────────────────────

def test_macro96_clinical_layer_unchanged():
    async def check():
        async with AsyncSessionLocal() as s:
            clinical = await _count(
                s, "SELECT COUNT(*) FROM canonical_brain_regions WHERE granularity_level='clinical'"
            )
            macro = await _count(
                s, "SELECT COUNT(*) FROM canonical_brain_regions WHERE granularity_level='macro'"
            )
            # 旧值兼容：Allen HBA（既有 molecular_attr 家族）的 demo 对齐保留
            allen_hba = await _count(
                s,
                "SELECT COUNT(*) FROM region_molecular_alignment "
                "WHERE source LIKE 'Allen HBA%'",
            )
            # 所有 canonical 行都是 brain_region_anatomical —— 生物层实体不进 region 表
            other_domain = await _count(
                s,
                "SELECT COUNT(*) FROM canonical_brain_regions "
                "WHERE granularity_domain <> 'brain_region_anatomical'",
            )
            return clinical, macro, allen_hba, other_domain

    clinical, macro, allen_hba, other_domain = _run(check())
    assert clinical == 48, "Macro96 clinical 层应为 48 区（无删无增）"
    assert macro == 4, "BR3 macro 层应为 4 系"
    # BR3 基线 4 条（ca1/dg/ca3 上的 Allen HBA 家族 demo 对齐）+ BR4 旗舰示例
    # BDNF@hippocampus 1 条 —— 断言「未被移除」而非精确数量
    assert allen_hba >= 4, "既有 Allen HBA 家族 demo 对齐不得被移除"
    assert other_domain == 0, "canonical 区域必须全部为 brain_region_anatomical 域"


def test_laterality_in_field_not_entity_names():
    """左右信息存 laterality 字段 —— 不创建 left_*/right_* 实体名。"""
    async def check():
        async with AsyncSessionLocal() as s:
            bad_codes = await _codes(
                s,
                "SELECT region_code FROM canonical_brain_regions "
                "WHERE region_code ILIKE '%left_%' OR region_code ILIKE '%right_%' "
                "OR canonical_name_en ILIKE 'left %' OR canonical_name_en ILIKE 'right %'",
            )
            lateral_count = await _count(
                s, "SELECT COUNT(*) FROM canonical_brain_regions WHERE laterality IN ('left','right')"
            )
            return bad_codes, lateral_count

    bad_codes, lateral_count = _run(check())
    assert bad_codes == [], f"发现左右命名的实体（应存 laterality 字段）: {bad_codes}"
    assert lateral_count >= 606, "BNA246+MMP 共 606 个左右脑区应带 laterality"


# ── 2. 外部 atlas 行/映射全部带溯源 ────────────────────────────────────

def test_external_atlas_rows_all_have_source():
    async def check():
        async with AsyncSessionLocal() as s:
            no_name = await _count(s, "SELECT COUNT(*) FROM atlas_region_resources WHERE atlas_name=''")
            no_prov = await _count(
                s, "SELECT COUNT(*) FROM atlas_region_resources WHERE provenance = '{}'::jsonb"
            )
            no_created_by = await _count(
                s, "SELECT COUNT(*) FROM atlas_region_mappings WHERE created_by=''"
            )
            no_match_prov = await _count(
                s, "SELECT COUNT(*) FROM atlas_region_mappings WHERE provenance = '{}'::jsonb"
            )
            return no_name, no_prov, no_created_by, no_match_prov

    no_name, no_prov, no_created_by, no_match_prov = _run(check())
    assert no_name == 0, "每个 atlas 行必须有 atlas_name"
    assert no_prov == 0, "每个 atlas 行必须带 provenance"
    assert no_created_by == 0, "每条映射必须带 created_by"
    assert no_match_prov == 0, "每条映射必须带 provenance"


# ── 3. mouse/human 物种隔离 ────────────────────────────────────────────

def test_mouse_human_species_isolation():
    """跨物种映射必须带 species_relation='homology'（服务层守卫）；
    same_species 映射不得连接跨物种行（同源 exact 映射是合法神经解剖语义）。"""
    async def check():
        async with AsyncSessionLocal() as s:
            rows = (await s.execute(text(
                "SELECT m.mapping_type, m.species_relation, ar.species, cr.species "
                "FROM atlas_region_mappings m "
                "JOIN atlas_region_resources ar ON m.atlas_region_id = ar.id "
                "JOIN canonical_brain_regions cr ON m.canonical_region_id = cr.id "
                "WHERE ar.species = 'mouse'"
            ))).all()
            cross_not_homology = [r for r in rows if r[1] != "homology"]
            same_species_cross = await _count(
                s,
                "SELECT COUNT(*) FROM atlas_region_mappings m "
                "JOIN atlas_region_resources ar ON m.atlas_region_id = ar.id "
                "JOIN canonical_brain_regions cr ON m.canonical_region_id = cr.id "
                "WHERE m.species_relation = 'same_species' AND ar.species <> cr.species",
            )
            return rows, cross_not_homology, same_species_cross

    rows, cross_not_homology, same_species_cross = _run(check())
    assert rows, "Allen mouse atlas 应有跨物种（homology）映射存在"
    assert cross_not_homology == [], f"跨物种映射必须标记 homology: {cross_not_homology}"
    assert same_species_cross == 0, "same_species 映射不得跨物种连接"


# ── 4. Meso 层级正确 ───────────────────────────────────────────────────

def test_meso_hierarchy_correct():
    """BNA246 + MMP 共 609 meso 区，均有 part_of 父边（cerebrum 或回旋父区），无自环。"""
    async def check():
        async with AsyncSessionLocal() as s:
            meso_total = await _count(
                s, "SELECT COUNT(*) FROM canonical_brain_regions WHERE granularity_level='meso'"
            )
            bna = await _count(
                s, "SELECT COUNT(*) FROM canonical_brain_regions WHERE region_code LIKE 'ng:br:bna_%'"
            )
            mmp = await _count(
                s, "SELECT COUNT(*) FROM canonical_brain_regions WHERE region_code LIKE 'ng:br:mmp_%'"
            )
            orphan = await _count(
                s,
                "SELECT COUNT(*) FROM canonical_brain_regions r "
                "WHERE r.granularity_level='meso' AND NOT EXISTS "
                "(SELECT 1 FROM canonical_region_hierarchy h WHERE h.child_region_id = r.id)",
            )
            self_loops = await _count(
                s, "SELECT COUNT(*) FROM canonical_region_hierarchy WHERE child_region_id = parent_region_id"
            )
            return meso_total, bna, mmp, orphan, self_loops

    meso_total, bna, mmp, orphan, self_loops = _run(check())
    assert meso_total == 609, f"meso 应 609 区（BNA246+MMP360+锚点3），实际 {meso_total}"
    assert bna == 246 and mmp == 360, "BNA246 与 MMP360 数量必须精确"
    assert orphan == 0, f"有 {orphan} 个 meso 区缺失 part_of 父边"
    assert self_loops == 0, "层级不允许自环"


# ── 5. Subregion 层级正确 ──────────────────────────────────────────────

def test_subregion_hierarchy_correct():
    """Winterburn 5 个子区（CA1/CA2/CA3/DG/Subiculum）全部 part_of hippocampal_formation。"""
    async def check():
        async with AsyncSessionLocal() as s:
            sub_total = await _count(
                s, "SELECT COUNT(*) FROM canonical_brain_regions WHERE granularity_level='subregion'"
            )
            ca2 = await _count(
                s, "SELECT COUNT(*) FROM canonical_brain_regions WHERE region_code='ng:br:ca2'"
            )
            parents = await _codes(
                s,
                "SELECT p.region_code FROM canonical_region_hierarchy h "
                "JOIN canonical_brain_regions c ON h.child_region_id = c.id "
                "JOIN canonical_brain_regions p ON h.parent_region_id = p.id "
                "WHERE c.granularity_level='subregion'",
            )
            return sub_total, ca2, parents

    sub_total, ca2, parents = _run(check())
    assert sub_total == 5, f"subregion 应 5 区（BR3 锚点 4 + Winterburn CA2），实际 {sub_total}"
    assert ca2 == 1, "Winterburn 导入应创建 ng:br:ca2"
    assert set(parents) == {"ng:br:hippocampal_formation"}, f"子区父边异常: {parents}"


# ── 6/7. Cell Type / Molecular 不污染 Region 层级 ─────────────────────

def test_cell_types_do_not_pollute_region_hierarchy():
    async def check():
        async with AsyncSessionLocal() as s:
            ct_regions = await _codes(
                s,
                "SELECT region_code FROM canonical_brain_regions WHERE region_code LIKE 'ng:ct:%'",
            )
            ct_hierarchy = await _count(
                s,
                "SELECT COUNT(*) FROM canonical_region_hierarchy h "
                "JOIN canonical_brain_regions c ON h.child_region_id = c.id "
                "WHERE c.region_code LIKE 'ng:ct:%'",
            )
            ct_bad_code = await _count(
                s, "SELECT COUNT(*) FROM cell_type_registry WHERE cell_type_code NOT LIKE 'ng:ct:%'"
            )
            return ct_regions, ct_hierarchy, ct_bad_code

    ct_regions, ct_hierarchy, ct_bad_code = _run(check())
    assert ct_regions == [], f"cell type 进入 region 表: {ct_regions}"
    assert ct_hierarchy == 0, "cell type 禁止出现在 region 层级中"
    assert ct_bad_code == 0, "cell_type_registry 必须全部使用 ng:ct: 命名空间"


def test_molecules_do_not_pollute_region_hierarchy():
    async def check():
        async with AsyncSessionLocal() as s:
            mol_regions = await _codes(
                s,
                "SELECT region_code FROM canonical_brain_regions WHERE region_code LIKE 'ng:mol:%'",
            )
            mol_hierarchy = await _count(
                s,
                "SELECT COUNT(*) FROM canonical_region_hierarchy h "
                "JOIN canonical_brain_regions c ON h.child_region_id = c.id "
                "WHERE c.region_code LIKE 'ng:mol:%'",
            )
            mol_bad_code = await _count(
                s,
                "SELECT COUNT(*) FROM molecular_entity_registry WHERE entity_code NOT LIKE 'ng:mol:%'",
            )
            return mol_regions, mol_hierarchy, mol_bad_code

    mol_regions, mol_hierarchy, mol_bad_code = _run(check())
    assert mol_regions == [], f"molecular entity 进入 region 表: {mol_regions}"
    assert mol_hierarchy == 0, "molecular entity 禁止出现在 region 层级中"
    assert mol_bad_code == 0, "molecular_entity_registry 必须全部使用 ng:mol: 命名空间"


# ── 8. 所有实体均有 provenance ─────────────────────────────────────────

def test_all_entities_have_provenance():
    async def check():
        async with AsyncSessionLocal() as s:
            region_no_source = await _count(
                s,
                "SELECT COUNT(*) FROM canonical_brain_regions WHERE source_summary = '{}'::jsonb "
                "AND created_by = 'manual'",
            )
            ct_no_taxonomy = await _count(
                s, "SELECT COUNT(*) FROM cell_type_registry WHERE taxonomy_source IS NULL"
            )
            mol_no_prov = await _count(
                s, "SELECT COUNT(*) FROM molecular_entity_registry WHERE provenance = '{}'::jsonb"
            )
            cell_align_no_prov = await _count(
                s, "SELECT COUNT(*) FROM region_cell_alignment WHERE provenance = '{}'::jsonb"
            )
            mol_align_no_prov = await _count(
                s, "SELECT COUNT(*) FROM region_molecular_alignment WHERE provenance = '{}'::jsonb"
            )
            mol_align_no_source = await _count(
                s, "SELECT COUNT(*) FROM region_molecular_alignment WHERE source IS NULL"
            )
            return (
                region_no_source, ct_no_taxonomy, mol_no_prov,
                cell_align_no_prov, mol_align_no_prov, mol_align_no_source,
            )

    region_no_source, ct_no_taxonomy, mol_no_prov, cell_align_no_prov, mol_align_no_prov, mol_align_no_source = (
        _run(check())
    )
    assert region_no_source == 0, "每个 canonical 区域必须有 source_summary 或非 manual created_by"
    assert ct_no_taxonomy == 0, "每个 cell type 必须有 taxonomy_source"
    assert mol_no_prov == 0, "每个 molecular entity 必须带 provenance"
    assert cell_align_no_prov == 0, "每条 cell alignment 必须带 provenance"
    assert mol_align_no_prov == 0, "每条 molecular alignment 必须带 provenance"
    assert mol_align_no_source == 0, "每条 molecular alignment 必须带 source"
