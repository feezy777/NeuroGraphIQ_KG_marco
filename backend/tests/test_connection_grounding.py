"""CN1 canonical grounding tests — Mirror Connection → Canonical Connection.

Covers:
  * analyze_mirror_connection_data — 只读统计口径
  * resolve_region_by_name — 分层名称解析（en/cn/alias/归一化/失败/跨物种守卫）
  * build_connection_grounding — 回填既有 provenance / 名称解析新建 /
    duplicate 合并 / 自环 / unresolved / 幂等 / batch_size 校验
  * grounding_stats — 聚合输出

隔离：全部测试数据带 cn1g_test_ 前缀，前后清理；全表聚合断言一律
用 before/after delta（真实库已有 70k mirror 行，不可假设空表）。
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from sqlalchemy import text

from app.database import AsyncSessionLocal
from app.schemas.canonical_connection import CanonicalConnectionCreate
from app.schemas.canonical_region import CanonicalRegionCreate
from app.services import canonical_connection_service as ccs
from app.services import canonical_region_service as crs
from app.services import connection_grounding_service as cgs

TEST_PREFIX = "cn1g_test_"
TEST_ATLAS = f"{TEST_PREFIX}atlas"

pytestmark = pytest.mark.function_term_real


def _run(coro):
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except Exception:
        pass
    return asyncio.run(coro)


# --------------------------------------------------------------------------- #
# fixtures
# --------------------------------------------------------------------------- #


@pytest.fixture()
def db():
    async def _cleanup() -> None:
        async with AsyncSessionLocal() as s:
            await s.execute(text(
                f"DELETE FROM mirror_connection_canonical_grounding "
                f"WHERE mirror_connection_id IN (SELECT id FROM mirror_region_connections "
                f"WHERE source_atlas = '{TEST_ATLAS}')"
            ))
            await s.execute(text(
                "DELETE FROM canonical_connections WHERE "
                "source_region_id IN (SELECT id FROM canonical_brain_regions "
                f"WHERE region_code LIKE 'ng:br:{TEST_PREFIX}%') "
                "OR target_region_id IN (SELECT id FROM canonical_brain_regions "
                f"WHERE region_code LIKE 'ng:br:{TEST_PREFIX}%')"
            ))
            await s.execute(text(
                f"DELETE FROM mirror_region_connections WHERE source_atlas = '{TEST_ATLAS}'"
            ))
            # 防御：历史版本 species 测试曾向真实 Allen_HBA_2012 插入过测试行
            # （candidate 为空 + 0.8 置信度；真实 Allen 行为 0.2 + 有 candidate）
            await s.execute(text(
                "DELETE FROM mirror_region_connections WHERE source_atlas = 'Allen_HBA_2012' "
                "AND source_region_candidate_id IS NULL AND target_region_candidate_id IS NULL "
                "AND confidence = 0.8"
            ))
            await s.execute(text(
                "DELETE FROM candidate_brain_regions WHERE raw_name LIKE "
                f"'{TEST_PREFIX}%'"
            ))
            await s.execute(text(
                "DELETE FROM candidate_generation_runs WHERE batch_id IN "
                f"(SELECT id FROM import_batches WHERE batch_code LIKE '{TEST_PREFIX}%')"
            ))
            await s.execute(text(
                "DELETE FROM raw_parse_runs WHERE parser_key LIKE "
                f"'{TEST_PREFIX}%'"
            ))
            await s.execute(text(
                "DELETE FROM import_batches WHERE batch_code LIKE "
                f"'{TEST_PREFIX}%'"
            ))
            await s.execute(text(
                "DELETE FROM resource_files WHERE original_filename LIKE "
                f"'{TEST_PREFIX}%'"
            ))
            await s.execute(text(
                "DELETE FROM atlas_resources WHERE resource_code LIKE "
                f"'{TEST_PREFIX}%'"
            ))
            await s.execute(text(
                "DELETE FROM canonical_region_aliases WHERE region_id IN "
                f"(SELECT id FROM canonical_brain_regions WHERE region_code LIKE 'ng:br:{TEST_PREFIX}%')"
            ))
            await s.execute(text(
                f"DELETE FROM canonical_brain_regions WHERE region_code LIKE 'ng:br:{TEST_PREFIX}%'"
            ))
            await s.commit()

    _run(_cleanup())
    yield
    _run(_cleanup())


async def _mk_region(session, code: str, *, en: str, cn: str | None = None) -> uuid.UUID:
    region = await crs.create_canonical_region(
        session,
        CanonicalRegionCreate(
            region_code=f"ng:br:{TEST_PREFIX}{code}",
            canonical_name_en=en,
            canonical_name_cn=cn,
            species="human",
            granularity_level="clinical",
            hemisphere_policy="bilateral",
            status="active",
            confidence=0.9,
            created_by="cn1g_test",
        ),
    )
    await session.commit()
    return region.id


async def _mk_alias(session, region_id: uuid.UUID, alias: str) -> None:
    await session.execute(text(
        "INSERT INTO canonical_region_aliases (region_id, alias, alias_language, source, confidence) "
        "VALUES (:rid, :alias, 'en', 'manual_curated', 0.9)"
    ), {"rid": region_id, "alias": alias})
    await session.commit()


async def _mk_candidate(session, *, canonical_region_id: uuid.UUID | None = None) -> uuid.UUID:
    """父表链最小插入（FK 强制），返回 candidate id。每次调用用唯一后缀。"""
    uid = uuid.uuid4().hex[:10]
    rid = uuid.uuid4()
    await session.execute(text(
        "INSERT INTO atlas_resources (id, resource_code, source_atlas, source_version, "
        "granularity_level, granularity_family) VALUES "
        f"(:id, '{TEST_PREFIX}res{uid}', 'cn1g_test', 'v1', 'macro', 'macro_clinical')"
    ), {"id": rid})
    bid = uuid.uuid4()
    await session.execute(text(
        "INSERT INTO import_batches (id, batch_code, resource_id, batch_type) VALUES "
        f"(:id, '{TEST_PREFIX}batch{uid}', :rid, 'atlas_import')"
    ), {"id": bid, "rid": rid})
    fid = uuid.uuid4()
    sha = "a" * 64
    await session.execute(text(
        "INSERT INTO resource_files (id, resource_id, original_filename, stored_filename, "
        "storage_path, file_size, sha256) VALUES "
        f"(:id, :rid, '{TEST_PREFIX}file{uid}.txt', '{TEST_PREFIX}file{uid}.txt', '/tmp', 1, :sha)"
    ), {"id": fid, "rid": rid, "sha": sha})
    pid = uuid.uuid4()
    await session.execute(text(
        "INSERT INTO raw_parse_runs (id, batch_id, resource_id, parser_key) VALUES "
        f"(:id, :bid, :rid, '{TEST_PREFIX}parser{uid}')"
    ), {"id": pid, "bid": bid, "rid": rid})
    gid = uuid.uuid4()
    await session.execute(text(
        "INSERT INTO candidate_generation_runs (id, batch_id, resource_id, parse_run_id) VALUES "
        "(:id, :bid, :rid, :pid)"
    ), {"id": gid, "bid": bid, "rid": rid, "pid": pid})
    cid = uuid.uuid4()
    await session.execute(text(
        "INSERT INTO candidate_brain_regions "
        "(id, generation_run_id, batch_id, resource_id, parse_run_id, source_raw_label_id, "
        "source_raw_table, source_file_id, source_atlas, source_version, raw_name, en_name, "
        "granularity_level, granularity_family, alignment_status, canonical_region_id, "
        "candidate_status, raw_payload, row_index) VALUES "
        "(:id, :gid, :bid, :rid, :pid, :lbl, 'cn1g_test', :fid, 'cn1g_test', 'v1', "
        f"'{TEST_PREFIX}cand{uid}', '{TEST_PREFIX}cand{uid}', 'macro', 'macro_clinical', "
        ":aligned, :canon, 'candidate_created', '{}', 0)"
    ), {
        "id": cid, "gid": gid, "bid": bid, "rid": rid, "pid": pid,
        "lbl": uuid.uuid4(), "fid": fid,
        "aligned": "aligned" if canonical_region_id else "not_aligned",
        "canon": canonical_region_id,
    })
    await session.commit()
    return cid


async def _mk_mirror(
    session,
    *,
    src_cand: uuid.UUID | None = None,
    tgt_cand: uuid.UUID | None = None,
    src_cn: str | None = None,
    src_en: str | None = None,
    tgt_cn: str | None = None,
    tgt_en: str | None = None,
    atlas: str = TEST_ATLAS,
    ctype: str = "structural_connection",
    direction: str = "directed",
    confidence: float | None = 0.8,
) -> uuid.UUID:
    mid = uuid.uuid4()
    await session.execute(text(
        "INSERT INTO mirror_region_connections "
        "(id, source_region_candidate_id, target_region_candidate_id, "
        "source_region_name_cn, source_region_name_en, target_region_name_cn, target_region_name_en, "
        "granularity_level, source_atlas, source_version, connection_type, directionality, confidence) "
        "VALUES (:id, :sc, :tc, :scn, :sen, :tcn, :ten, 'macro', :atlas, 'v1', :ctype, :dir, :conf)"
    ), {
        "id": mid, "sc": src_cand, "tc": tgt_cand,
        "scn": src_cn, "sen": src_en, "tcn": tgt_cn, "ten": tgt_en,
        "atlas": atlas, "ctype": ctype, "dir": direction, "conf": confidence,
    })
    await session.commit()
    return mid


async def _count_grounding(session) -> int:
    return int(
        (await session.execute(
            text("SELECT count(*) FROM mirror_connection_canonical_grounding")
        )).scalar_one()
    )


async def _count_canonical(session) -> int:
    return int((await session.execute(text("SELECT count(*) FROM canonical_connections"))).scalar_one())


# --------------------------------------------------------------------------- #
# analyze
# --------------------------------------------------------------------------- #


def test_analyze_mirror_connection_data(db):
    async def _t():
        async with AsyncSessionLocal() as s:
            before = await cgs.analyze_mirror_connection_data(s)
            src = await _mk_region(s, "src", en="Test Source Area", cn="测试源区")
            tgt = await _mk_region(s, "tgt", en="Test Target Area", cn="测试靶区")
            cand_src = await _mk_candidate(s, canonical_region_id=src)
            cand_tgt = await _mk_candidate(s, canonical_region_id=tgt)
            await _mk_mirror(s, src_cand=cand_src, tgt_cand=cand_tgt,
                             src_en="Test Source Area", tgt_en="Test Target Area")  # grounded
            await _mk_mirror(s, src_en="Unknown Name A", tgt_en="Unknown Name B")  # ungrounded

            after = await cgs.analyze_mirror_connection_data(s)
            assert after["total_mirror_connections"] - before["total_mirror_connections"] == 2
            assert after["endpoint_grounding"]["both_candidate_grounded"] \
                - before["endpoint_grounding"]["both_candidate_grounded"] == 1
            assert after["endpoint_grounding"]["any_ungrounded"] \
                - before["endpoint_grounding"]["any_ungrounded"] == 1
            assert after["naming"]["source_en_filled"] - before["naming"]["source_en_filled"] == 2
            assert after["unresolved_by_atlas"].get("cn1g_test_atlas", 0) \
                - before["unresolved_by_atlas"].get("cn1g_test_atlas", 0) == 1
    _run(_t())


# --------------------------------------------------------------------------- #
# resolve_region_by_name
# --------------------------------------------------------------------------- #


def test_resolve_region_by_name_layers(db):
    async def _t():
        async with AsyncSessionLocal() as s:
            src = await _mk_region(s, "src", en="Test Source Area", cn="测试源区")
            await _mk_alias(s, src, "TSA")
            index = await cgs._load_name_index(s)

            # canonical en 精确（大小写不敏感）
            rid, method = await cgs.resolve_region_by_name(
                s, cn=None, en="test source area", atlas=TEST_ATLAS, index=index)
            assert rid == str(src) and method == "name_canonical_exact"
            # canonical cn 精确
            rid, method = await cgs.resolve_region_by_name(
                s, cn="测试源区", en=None, atlas=TEST_ATLAS, index=index)
            assert rid == str(src) and method == "name_canonical_exact"
            # alias 精确
            rid, method = await cgs.resolve_region_by_name(
                s, cn=None, en="TSA", atlas=TEST_ATLAS, index=index)
            assert rid == str(src) and method == "name_alias_exact"
            # 归一化（大小写+标点）
            rid, method = await cgs.resolve_region_by_name(
                s, cn=None, en="Test-Source_Area!!", atlas=TEST_ATLAS, index=index)
            assert rid == str(src) and method == "name_normalized_exact"
            # 无匹配
            rid, method = await cgs.resolve_region_by_name(
                s, cn=None, en="No Such Region", atlas=TEST_ATLAS, index=index)
            assert rid is None and method is None
            # 跨物种守卫（Allen 小鼠 → 拒绝）
            rid, method = await cgs.resolve_region_by_name(
                s, cn=None, en="Primary visual area, layer 1", atlas="Allen_HBA_2012", index=index)
            assert rid is None and method is None
    _run(_t())


# --------------------------------------------------------------------------- #
# build: 回填 / 新建 / 合并 / unresolved / 幂等
# --------------------------------------------------------------------------- #


def test_build_backfills_existing_provenance(db):
    """canonical_connections.provenance 已覆盖的 mirror ids → 直接回填 grounded。"""
    async def _t():
        async with AsyncSessionLocal() as s:
            src = await _mk_region(s, "src", en="Test Source Area")
            tgt = await _mk_region(s, "tgt", en="Test Target Area")
            cand_src = await _mk_candidate(s, canonical_region_id=src)
            cand_tgt = await _mk_candidate(s, canonical_region_id=tgt)
            mid = await _mk_mirror(s, src_cand=cand_src, tgt_cand=cand_tgt)
            cc = await ccs.create_canonical_connection(
                s,
                CanonicalConnectionCreate(
                    source_region_id=src,
                    target_region_id=tgt,
                    connection_type="structural",
                    provenance_json={"original_connection_ids": [str(mid)]},
                ),
            )
            await s.commit()

            before_cc = await _count_canonical(s)
            result = await cgs.build_connection_grounding(s, batch_size=500, atlas_filter=TEST_ATLAS)
            assert result["total_mirror_rows"] == 1
            assert result["grounded"]["reused_existing_canonical"] == 1
            assert result["grounded"]["created_new_canonical"] == 0
            assert result["unresolved"] == {"species_mismatch": 0, "no_name_match": 0,
                                            "self_loop": 0, "mapping_error": 0}
            assert await _count_canonical(s) == before_cc  # 不新建 canonical

            stats = await cgs.grounding_stats(s)
            assert stats["total_grounding_rows"] >= 1
            row = (await s.execute(text(
                "SELECT g.canonical_connection_id, g.source_resolution_method, g.status "
                "FROM mirror_connection_canonical_grounding g WHERE g.mirror_connection_id = :mid"
            ), {"mid": mid})).mappings().first()
            assert str(row["canonical_connection_id"]) == str(cc.id)
            assert row["source_resolution_method"] == "candidate_grounded"
            assert row["status"] == "grounded"
    _run(_t())


def test_build_creates_canonical_and_merges_duplicates(db):
    """名称解析成功 → 新建 canonical；同 key 后续行合并指向同一 canonical。"""
    async def _t():
        async with AsyncSessionLocal() as s:
            await _mk_region(s, "src", en="Test Source Area")
            await _mk_region(s, "tgt", en="Test Target Area")
            m1 = await _mk_mirror(s, src_en="Test Source Area", tgt_en="Test Target Area")
            m2 = await _mk_mirror(s, src_en="Test Source Area", tgt_en="Test Target Area")

            before_cc = await _count_canonical(s)
            result = await cgs.build_connection_grounding(s, batch_size=500, atlas_filter=TEST_ATLAS)
            assert result["grounded"]["created_new_canonical"] == 1
            assert result["grounded"]["reused_existing_canonical"] == 1  # m2 合并到 m1 建的
            assert result["new_canonical_connections"] == 1
            assert result["duplicate_mirror_rows_merged"] == 1
            assert await _count_canonical(s) == before_cc + 1

            stats = await cgs.grounding_stats(s)
            assert stats["grounded"] >= 2
            assert stats["distinct_canonical_connections"] >= 1
            # 新建 canonical 保留 provenance（仅首行——不修改既有行；首行由
            # UUID 排序决定，故断言顺序无关）
            row = (await s.execute(text(
                "SELECT provenance_json->'original_connection_ids' AS ids, "
                "connection_type, directionality_policy FROM canonical_connections "
                "WHERE provenance_json->>'mapping_method' = 'cn1_connection_grounding_v1' "
                "AND (provenance_json->'original_connection_ids' ? :m1 "
                "OR provenance_json->'original_connection_ids' ? :m2)"
            ), {"m1": str(m1), "m2": str(m2)})).mappings().first()
            assert row is not None
            assert len(row["ids"]) == 1
            assert row["ids"][0] in (str(m1), str(m2))
            assert row["connection_type"] == "structural"      # frozen rules 映射
            assert row["directionality_policy"] == "directed"  # frozen rules 映射
            # 两条 mirror 行都在 grounding 表指向同一 canonical
            rows = (await s.execute(text(
                "SELECT canonical_connection_id FROM mirror_connection_canonical_grounding "
                "WHERE mirror_connection_id IN (:m1, :m2)"
            ), {"m1": m1, "m2": m2})).scalars().all()
            assert len(set(rows)) == 1
    _run(_t())


def test_build_unresolved_species_mismatch(db):
    async def _t():
        async with AsyncSessionLocal() as s:
            # 用测试专用 atlas + cross_species_atlases 覆盖，模拟 Allen 小鼠场景，
            # 避免向真实 Allen_HBA_2012 数据集插入测试行
            await _mk_mirror(
                s, src_en="Primary visual area, layer 1",
                tgt_en="Secondary visual area, layer 1", atlas=TEST_ATLAS)
            result = await cgs.build_connection_grounding(
                s, batch_size=500, atlas_filter=TEST_ATLAS,
                cross_species_atlases={TEST_ATLAS})
            assert result["unresolved"]["species_mismatch"] == 1
            assert result["grounded"]["created_new_canonical"] == 0
            stats = await cgs.grounding_stats(s)
            assert stats["unresolved"] >= 1
            assert stats["unresolved_by_reason"].get("species_mismatch", 0) >= 1
            # unresolved_report 的 LIMIT 会被真实库大量 unresolved 占满，
            # 用直接 SQL 精确断言测试行
            cnt = (await s.execute(text(
                "SELECT count(*) FROM mirror_connection_canonical_grounding g "
                "JOIN mirror_region_connections mrc ON mrc.id = g.mirror_connection_id "
                "WHERE g.status = 'unresolved' AND g.unresolved_reason = 'species_mismatch' "
                f"AND mrc.source_atlas = '{TEST_ATLAS}'"
            ))).scalar_one()
            assert cnt == 1
    _run(_t())


def test_build_unresolved_no_name_match(db):
    async def _t():
        async with AsyncSessionLocal() as s:
            await _mk_mirror(s, src_en="Mystery Region A", tgt_en="Mystery Region B")
            result = await cgs.build_connection_grounding(s, batch_size=500, atlas_filter=TEST_ATLAS)
            assert result["unresolved"]["no_name_match"] == 1
            stats = await cgs.grounding_stats(s)
            assert stats["unresolved_by_reason"].get("no_name_match", 0) >= 1
    _run(_t())


def test_build_self_loop_rejected(db):
    async def _t():
        async with AsyncSessionLocal() as s:
            src = await _mk_region(s, "src", en="Test Source Area")
            cand = await _mk_candidate(s, canonical_region_id=src)
            await _mk_mirror(s, src_cand=cand, tgt_cand=cand)  # 同一 candidate
            result = await cgs.build_connection_grounding(s, batch_size=500, atlas_filter=TEST_ATLAS)
            assert result["unresolved"]["self_loop"] == 1
            assert result["grounded"]["created_new_canonical"] == 0
            # 名称解析后端点相同也拒绝
            await _mk_mirror(s, src_en="Test Source Area", tgt_en="Test Source Area")
            result2 = await cgs.build_connection_grounding(
                s, batch_size=500, atlas_filter=TEST_ATLAS)
            assert result2["unresolved"]["self_loop"] == 1
    _run(_t())


def test_build_idempotent_rerun(db):
    async def _t():
        async with AsyncSessionLocal() as s:
            await _mk_region(s, "src", en="Test Source Area")
            await _mk_region(s, "tgt", en="Test Target Area")
            await _mk_mirror(s, src_en="Test Source Area", tgt_en="Test Target Area")
            before_g = await _count_grounding(s)
            before_cc = await _count_canonical(s)
            r1 = await cgs.build_connection_grounding(s, batch_size=500, atlas_filter=TEST_ATLAS)
            assert r1["total_mirror_rows"] == 1
            r2 = await cgs.build_connection_grounding(s, batch_size=500, atlas_filter=TEST_ATLAS)
            assert r2["total_mirror_rows"] == 1
            assert r2["already_grounded_rows"] == 1
            assert r2["grounded"]["created_new_canonical"] == 0
            assert r2["grounded"]["reused_existing_canonical"] == 0
            assert await _count_grounding(s) == before_g + 1
            assert await _count_canonical(s) == before_cc + 1
    _run(_t())


def test_build_batch_size_validation(db):
    async def _t():
        async with AsyncSessionLocal() as s:
            with pytest.raises(ValueError):
                await cgs.build_connection_grounding(s, batch_size=300)
            with pytest.raises(ValueError):
                await cgs.build_connection_grounding(s, batch_size=1500)
    _run(_t())


def test_build_dry_run_writes_nothing(db):
    async def _t():
        async with AsyncSessionLocal() as s:
            await _mk_region(s, "src", en="Test Source Area")
            await _mk_region(s, "tgt", en="Test Target Area")
            await _mk_mirror(s, src_en="Test Source Area", tgt_en="Test Target Area")
            before_g = await _count_grounding(s)
            before_cc = await _count_canonical(s)
            result = await cgs.build_connection_grounding(
                s, batch_size=500, dry_run=True, atlas_filter=TEST_ATLAS)
            assert result["grounded"]["created_new_canonical"] == 1
            assert result["dry_run"] is True
            assert await _count_grounding(s) == before_g
            assert await _count_canonical(s) == before_cc
    _run(_t())


def test_grounding_stats_aggregates(db):
    async def _t():
        async with AsyncSessionLocal() as s:
            src = await _mk_region(s, "src", en="Test Source Area")
            tgt = await _mk_region(s, "tgt", en="Test Target Area")
            cand_src = await _mk_candidate(s, canonical_region_id=src)
            cand_tgt = await _mk_candidate(s, canonical_region_id=tgt)
            await _mk_mirror(s, src_cand=cand_src, tgt_cand=cand_tgt)                  # candidate_grounded
            await _mk_mirror(s, src_en="Test Source Area", tgt_en="Test Target Area")  # name 解析
            await _mk_mirror(s, src_en="Mystery A", tgt_en="Mystery B")                # unresolved
            before = await cgs.grounding_stats(s)
            await cgs.build_connection_grounding(s, batch_size=500, atlas_filter=TEST_ATLAS)
            after = await cgs.grounding_stats(s)

            assert after["total_grounding_rows"] - before["total_grounding_rows"] == 3
            assert after["grounded"] - before["grounded"] == 2
            assert after["unresolved"] - before["unresolved"] == 1
            assert after["unresolved_by_reason"].get("no_name_match", 0) \
                - before["unresolved_by_reason"].get("no_name_match", 0) == 1
            assert after["source_resolution_methods"].get("candidate_grounded", 0) \
                - before["source_resolution_methods"].get("candidate_grounded", 0) == 1
            assert after["source_resolution_methods"].get("name_canonical_exact", 0) \
                - before["source_resolution_methods"].get("name_canonical_exact", 0) == 1
            assert after["distinct_source_regions"] >= 1
            assert after["distinct_target_regions"] >= 1
    _run(_t())


def test_analyze_self_loops_and_duplicates(db):
    async def _t():
        async with AsyncSessionLocal() as s:
            before = await cgs.analyze_mirror_connection_data(s)
            src = await _mk_region(s, "src", en="Test Source Area")
            tgt = await _mk_region(s, "tgt", en="Test Target Area")
            cand_src = await _mk_candidate(s, canonical_region_id=src)
            cand_tgt = await _mk_candidate(s, canonical_region_id=tgt)
            await _mk_mirror(s, src_cand=cand_src, tgt_cand=cand_tgt)
            # duplicate：同 (src,tgt,type) 但 direction 不同，避开 mirror 唯一约束，
            # 仍在 analyze 的 duplicate 分组内（分组键不含 direction）
            await _mk_mirror(s, src_cand=cand_src, tgt_cand=cand_tgt, direction="undirected")
            await _mk_mirror(s, src_cand=cand_src, tgt_cand=cand_src)  # self loop
            after = await cgs.analyze_mirror_connection_data(s)
            assert after["self_loops"] - before["self_loops"] == 1
            assert after["duplicates"]["groups"] - before["duplicates"]["groups"] == 1
            assert after["duplicates"]["extra_rows"] - before["duplicates"]["extra_rows"] == 1
    _run(_t())
