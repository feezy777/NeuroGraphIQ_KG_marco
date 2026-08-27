"""CR1 canonical grounding tests — Mirror Circuit → Canonical Circuit.

Covers:
  * analyze_mirror_circuit_data — 只读统计口径
  * _normalize_circuit_name — 名称标准化（strip + 压缩空白）
  * build_circuit_grounding — CI1.2-B 回填 / species 拒绝 / 成员判定矩阵
    （no_region_members / too_few_regions / no_grounded_regions /
    unknown_region_role）/ resolved connections / 幂等 / dry_run /
    batch_size 校验
  * grounding_stats / unresolved_report — 聚合输出

隔离：全部测试数据带 cr1g_test_ 前缀，前后清理；全表聚合断言一律
用 before/after delta（真实库已有 53k mirror circuits，不可假设空表）。
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
from app.services import circuit_grounding_service as cgs

TEST_PREFIX = "cr1g_test_"
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
            # 1) grounding 表（先删子表，FK CASCADE 亦保险）
            await s.execute(text(
                f"DELETE FROM mirror_circuit_canonical_grounding "
                f"WHERE mirror_circuit_id IN (SELECT id FROM mirror_region_circuits "
                f"WHERE source_atlas = '{TEST_ATLAS}')"
            ))
            await s.execute(text(
                f"DELETE FROM mirror_connection_canonical_grounding "
                f"WHERE mirror_connection_id IN (SELECT id FROM mirror_region_connections "
                f"WHERE source_atlas = '{TEST_ATLAS}')"
            ))
            # 2) circuit 成员表
            await s.execute(text(
                f"DELETE FROM mirror_circuit_projection_memberships "
                f"WHERE circuit_id IN (SELECT id FROM mirror_region_circuits "
                f"WHERE source_atlas = '{TEST_ATLAS}')"
            ))
            await s.execute(text(
                f"DELETE FROM mirror_circuit_regions "
                f"WHERE circuit_id IN (SELECT id FROM mirror_region_circuits "
                f"WHERE source_atlas = '{TEST_ATLAS}')"
            ))
            await s.execute(text(
                f"DELETE FROM mirror_circuit_steps "
                f"WHERE circuit_id IN (SELECT id FROM mirror_region_circuits "
                f"WHERE source_atlas = '{TEST_ATLAS}')"
            ))
            await s.execute(text(
                f"DELETE FROM mirror_circuit_functions "
                f"WHERE circuit_id IN (SELECT id FROM mirror_region_circuits "
                f"WHERE source_atlas = '{TEST_ATLAS}')"
            ))
            # 3) 测试 canonical circuits（provenance 引用 test mirror circuits）
            await s.execute(text(
                f"DELETE FROM canonical_circuits WHERE "
                f"provenance_json->>'source_mirror_circuit_id' IN "
                f"(SELECT id::text FROM mirror_region_circuits WHERE source_atlas = '{TEST_ATLAS}')"
            ))
            # 4) 测试 mirror circuits（无外部 FK 指向它）
            await s.execute(text(
                f"DELETE FROM mirror_region_circuits WHERE source_atlas = '{TEST_ATLAS}'"
            ))
            # 5) 测试 canonical connections + mirror connections
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
            # 6) 防御：历史版本 species 测试曾向真实 Allen_HBA_2012 插入过测试行
            await s.execute(text(
                "DELETE FROM mirror_region_connections WHERE source_atlas = 'Allen_HBA_2012' "
                "AND source_region_candidate_id IS NULL AND target_region_candidate_id IS NULL "
                "AND confidence = 0.8"
            ))
            # 7) candidate + 父表链 + canonical regions
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
            created_by="cr1g_test",
        ),
    )
    await session.commit()
    return region.id


async def _mk_candidate(session, *, canonical_region_id: uuid.UUID | None = None) -> uuid.UUID:
    """父表链最小插入（FK 强制），返回 candidate id。每次调用用唯一后缀。"""
    uid = uuid.uuid4().hex[:10]
    rid = uuid.uuid4()
    await session.execute(text(
        "INSERT INTO atlas_resources (id, resource_code, source_atlas, source_version, "
        "granularity_level, granularity_family) VALUES "
        f"(:id, '{TEST_PREFIX}res{uid}', 'cr1g_test', 'v1', 'macro', 'macro_clinical')"
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
        "(:id, :gid, :bid, :rid, :pid, :lbl, 'cr1g_test', :fid, 'cr1g_test', 'v1', "
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


async def _mk_circuit(
    session,
    *,
    atlas: str = TEST_ATLAS,
    granularity: str = "macro",
    name: str = "Test Circuit",
    name_cn: str | None = None,
    circuit_type: str = "network",
    confidence: float | None = 0.8,
    evidence_text: str | None = None,
    function_association: str | None = None,
) -> uuid.UUID:
    cid = uuid.uuid4()
    await session.execute(text(
        "INSERT INTO mirror_region_circuits "
        "(id, granularity_level, granularity_family, source_atlas, source_version, "
        "circuit_name, name_cn, circuit_type, function_association, description, "
        "confidence, evidence_text, mirror_status, review_status, promotion_status, "
        "raw_payload_json, normalized_payload_json) VALUES "
        "(:id, :g, :gf, :atlas, 'v1', :name, :name_cn, :ctype, :fa, NULL, "
        ":conf, :ev, 'llm_suggested', 'pending', 'not_promoted', '{}', '{}')"
    ), {
        "id": cid, "g": granularity, "gf": "macro_clinical" if granularity == "macro" else "molecular",
        "atlas": atlas, "name": name, "name_cn": name_cn, "ctype": circuit_type,
        "fa": function_association, "conf": confidence, "ev": evidence_text,
    })
    await session.commit()
    return cid


async def _mk_circuit_region(
    session, circuit_id: uuid.UUID, region_candidate_id: uuid.UUID, *, role: str = "participant"
) -> uuid.UUID:
    mid = uuid.uuid4()
    await session.execute(text(
        "INSERT INTO mirror_circuit_regions (id, circuit_id, region_candidate_id, role, sort_order) "
        "VALUES (:id, :cid, :rid, :role, 0)"
    ), {"id": mid, "cid": circuit_id, "rid": region_candidate_id, "role": role})
    await session.commit()
    return mid


async def _mk_circuit_function(session, circuit_id: uuid.UUID) -> uuid.UUID:
    fid = uuid.uuid4()
    await session.execute(text(
        "INSERT INTO mirror_circuit_functions "
        "(id, circuit_id, granularity_level, source_atlas, function_term_en, function_term_cn, "
        "function_role, confidence_score) VALUES "
        "(:id, :cid, 'macro', :atlas, 'test function', '测试功能', 'associated_with', 0.8)"
    ), {"id": fid, "cid": circuit_id, "atlas": TEST_ATLAS})
    await session.commit()
    return fid


async def _mk_mirror_connection(
    session, *, src_cand: uuid.UUID, tgt_cand: uuid.UUID, atlas: str = TEST_ATLAS
) -> uuid.UUID:
    mid = uuid.uuid4()
    await session.execute(text(
        "INSERT INTO mirror_region_connections "
        "(id, source_region_candidate_id, target_region_candidate_id, "
        "source_region_name_cn, source_region_name_en, target_region_name_cn, target_region_name_en, "
        "granularity_level, source_atlas, source_version, connection_type, directionality, confidence) "
        "VALUES (:id, :sc, :tc, 'a', 'a', 'b', 'b', 'macro', :atlas, 'v1', "
        "'structural_connection', 'directed', 0.8)"
    ), {"id": mid, "sc": src_cand, "tc": tgt_cand, "atlas": atlas})
    await session.commit()
    return mid


async def _mk_projection_membership(
    session, circuit_id: uuid.UUID, projection_id: uuid.UUID
) -> uuid.UUID:
    pid = uuid.uuid4()
    await session.execute(text(
        "INSERT INTO mirror_circuit_projection_memberships "
        "(id, circuit_id, projection_id, granularity_level, source_atlas, role_in_circuit) "
        "VALUES (:id, :cid, :pid, 'macro', :atlas, 'unknown')"
    ), {"id": pid, "cid": circuit_id, "pid": projection_id, "atlas": TEST_ATLAS})
    await session.commit()
    return pid


async def _mk_canonical_circuit(
    session, mirror_circuit_id: uuid.UUID, *, en: str = "Canonical Test Circuit", cn: str | None = None
) -> uuid.UUID:
    cc_id = uuid.uuid4()
    await session.execute(text(
        "INSERT INTO canonical_circuits "
        "(id, circuit_code, canonical_name_en, canonical_name_cn, species, granularity_level, "
        "circuit_type, status, provenance_json) VALUES "
        "(:id, :code, :en, :cn, 'human', 'clinical', 'network', 'proposed', "
        f"jsonb_build_object('source_mirror_circuit_id', '{mirror_circuit_id}'))"
    ), {"id": cc_id, "code": f"ng:ci:{TEST_PREFIX}{uuid.uuid4().hex[:10]}", "en": en, "cn": cn})
    await session.commit()
    return cc_id


async def _mk_cn1_grounded_connection(
    session, *, src_region: uuid.UUID, tgt_region: uuid.UUID, src_cand: uuid.UUID, tgt_cand: uuid.UUID
) -> tuple[uuid.UUID, uuid.UUID]:
    """建 canonical connection + CN1 grounding 行（resolved connection 测试用）。"""
    cc = await ccs.create_canonical_connection(
        session,
        CanonicalConnectionCreate(
            source_region_id=src_region,
            target_region_id=tgt_region,
            connection_type="structural",
            provenance_json={"original_connection_ids": [str(uuid.uuid4())]},
        ),
    )
    await session.commit()
    conn_id = await _mk_mirror_connection(session, src_cand=src_cand, tgt_cand=tgt_cand)
    await session.execute(text(
        "INSERT INTO mirror_connection_canonical_grounding "
        "(mirror_connection_id, canonical_connection_id, source_resolution_method, "
        "target_resolution_method, status, created_by) VALUES "
        "(:mid, :cid, 'candidate_grounded', 'candidate_grounded', 'grounded', 'cr1g_test')"
    ), {"mid": conn_id, "cid": cc.id})
    await session.commit()
    return conn_id, cc.id


async def _count_grounding(session) -> int:
    """只统计 TEST_ATLAS 的行（真实库已有 53k+ grounding 行，不可全库计数）。"""
    return int((await session.execute(
        text("SELECT count(*) FROM mirror_circuit_canonical_grounding g "
             "JOIN mirror_region_circuits c ON c.id = g.mirror_circuit_id "
             f"WHERE c.source_atlas = '{TEST_ATLAS}'")
    )).scalar_one())


# --------------------------------------------------------------------------- #
# analyze
# --------------------------------------------------------------------------- #


def test_analyze_mirror_circuit_data(db):
    async def _t():
        async with AsyncSessionLocal() as s:
            before = await cgs.analyze_mirror_circuit_data(s)
            src = await _mk_region(s, "src", en="Test Source Area")
            cand = await _mk_candidate(s, canonical_region_id=src)
            c1 = await _mk_circuit(s, name="  Test   Circuit  One  ", name_cn="回路一")
            await _mk_circuit_region(s, c1, cand)  # grounded 成员
            c2 = await _mk_circuit(s, granularity="molecular_attr", name="Mol Circuit")
            await _mk_circuit_function(s, c1)

            after = await cgs.analyze_mirror_circuit_data(s)
            assert after["total_mirror_circuits"] - before["total_mirror_circuits"] == 2
            assert after["granularity_distribution"]["macro"] \
                - before["granularity_distribution"]["macro"] == 1
            assert after["granularity_distribution"]["molecular_attr"] \
                - before["granularity_distribution"]["molecular_attr"] == 1
            assert after["member_grounding"]["candidate_grounded"] \
                - before["member_grounding"]["candidate_grounded"] == 1
            assert after["members_per_circuit"].get(1, 0) - before["members_per_circuit"].get(1, 0) == 1
            assert after["naming"]["circuit_name_filled"] - before["naming"]["circuit_name_filled"] == 2
            assert after["circuit_functions_total"] - before["circuit_functions_total"] == 1
    _run(_t())


def test_normalize_circuit_name(db):
    assert cgs._normalize_circuit_name("  Test   Circuit  One  ") == "Test Circuit One"
    assert cgs._normalize_circuit_name("Single") == "Single"
    assert cgs._normalize_circuit_name("  ") == ""


# --------------------------------------------------------------------------- #
# build: 回填 / 判定矩阵 / 统计 / 幂等
# --------------------------------------------------------------------------- #


def test_build_backfills_existing_canonical(db):
    """CI1.2-B 已 canonicalized（provenance 引用）→ 直接回填 grounded，不新建。"""
    async def _t():
        async with AsyncSessionLocal() as s:
            src = await _mk_region(s, "src", en="Test Source Area")
            tgt = await _mk_region(s, "tgt", en="Test Target Area")
            cand_src = await _mk_candidate(s, canonical_region_id=src)
            cand_tgt = await _mk_candidate(s, canonical_region_id=tgt)
            cid = await _mk_circuit(s, name="Test Circuit")
            await _mk_circuit_region(s, cid, cand_src)
            await _mk_circuit_region(s, cid, cand_tgt)
            cc_id = await _mk_canonical_circuit(s, cid, en="Canonical Test Circuit", cn="标准回路")

            result = await cgs.build_circuit_grounding(s, batch_size=500, atlas_filter=TEST_ATLAS)
            assert result["total_mirror_rows"] == 1
            assert result["grounded"]["backfilled_from_canonical"] == 1
            assert result["unresolved"] == {"species_granularity_mismatch": 0, "no_region_members": 0,
                                            "too_few_regions": 0, "no_grounded_regions": 0,
                                            "unknown_region_role": 0}

            row = (await s.execute(text(
                "SELECT g.canonical_circuit_id, g.canonical_name_en, g.canonical_name_cn, "
                "g.status, g.total_region_members, g.grounded_region_members, "
                "g.ungrounded_region_members, g.mapping_method, g.granularity_level "
                "FROM mirror_circuit_canonical_grounding g WHERE g.mirror_circuit_id = :cid"
            ), {"cid": cid})).mappings().first()
            assert str(row["canonical_circuit_id"]) == str(cc_id)
            assert row["canonical_name_en"] == "Canonical Test Circuit"  # 取 canonical 侧名称
            assert row["canonical_name_cn"] == "标准回路"
            assert row["status"] == "grounded"
            assert row["total_region_members"] == 2
            assert row["grounded_region_members"] == 2
            assert row["ungrounded_region_members"] == 0
            assert row["mapping_method"] == "cr1_circuit_grounding_v1"
            assert row["granularity_level"] == "macro"
    _run(_t())


def test_build_species_granularity_mismatch(db):
    """molecular_attr 粒度 → species 拒绝（优先于成员判定：0 成员也走 species）。"""
    async def _t():
        async with AsyncSessionLocal() as s:
            await _mk_circuit(s, granularity="molecular_attr", name="Mol Circuit")
            result = await cgs.build_circuit_grounding(s, batch_size=500, atlas_filter=TEST_ATLAS)
            assert result["total_mirror_rows"] == 1
            assert result["unresolved"]["species_granularity_mismatch"] == 1
            assert result["unresolved"]["no_region_members"] == 0
            row = (await s.execute(text(
                "SELECT g.status, g.unresolved_reason FROM mirror_circuit_canonical_grounding g "
                "JOIN mirror_region_circuits c ON c.id = g.mirror_circuit_id "
                "WHERE c.circuit_name = 'Mol Circuit'"
            ))).mappings().first()
            assert row["status"] == "unresolved"
            assert row["unresolved_reason"] == "species_granularity_mismatch"
    _run(_t())


def test_build_no_region_members(db):
    async def _t():
        async with AsyncSessionLocal() as s:
            await _mk_circuit(s, name="Empty Circuit")
            result = await cgs.build_circuit_grounding(s, batch_size=500, atlas_filter=TEST_ATLAS)
            assert result["unresolved"]["no_region_members"] == 1
            row = (await s.execute(text(
                "SELECT g.unresolved_reason FROM mirror_circuit_canonical_grounding g "
                "JOIN mirror_region_circuits c ON c.id = g.mirror_circuit_id "
                "WHERE c.circuit_name = 'Empty Circuit'"
            ))).mappings().first()
            assert row["unresolved_reason"] == "no_region_members"
    _run(_t())


def test_build_too_few_regions(db):
    """仅 1 个 region 成员 → too_few_regions（即使该成员已 grounded）。"""
    async def _t():
        async with AsyncSessionLocal() as s:
            src = await _mk_region(s, "src", en="Test Source Area")
            cand = await _mk_candidate(s, canonical_region_id=src)
            cid = await _mk_circuit(s, name="Single Member Circuit")
            await _mk_circuit_region(s, cid, cand)  # grounded 但只有 1 个
            result = await cgs.build_circuit_grounding(s, batch_size=500, atlas_filter=TEST_ATLAS)
            assert result["unresolved"]["too_few_regions"] == 1
            assert result["unresolved"]["no_grounded_regions"] == 0
            row = (await s.execute(text(
                "SELECT g.unresolved_reason, g.total_region_members, g.grounded_region_members "
                "FROM mirror_circuit_canonical_grounding g WHERE g.mirror_circuit_id = :cid"
            ), {"cid": cid})).mappings().first()
            assert row["unresolved_reason"] == "too_few_regions"
            assert row["total_region_members"] == 1
            assert row["grounded_region_members"] == 1
    _run(_t())


def test_build_no_grounded_regions(db):
    """≥2 成员但 0 个 grounded（candidate 未对齐 canonical）→ no_grounded_regions。"""
    async def _t():
        async with AsyncSessionLocal() as s:
            cand_a = await _mk_candidate(s)  # 未对齐
            cand_b = await _mk_candidate(s)
            cid = await _mk_circuit(s, name="Ungrounded Members Circuit")
            await _mk_circuit_region(s, cid, cand_a)
            await _mk_circuit_region(s, cid, cand_b)
            result = await cgs.build_circuit_grounding(s, batch_size=500, atlas_filter=TEST_ATLAS)
            assert result["unresolved"]["no_grounded_regions"] == 1
            row = (await s.execute(text(
                "SELECT g.unresolved_reason, g.total_region_members, g.grounded_region_members "
                "FROM mirror_circuit_canonical_grounding g WHERE g.mirror_circuit_id = :cid"
            ), {"cid": cid})).mappings().first()
            assert row["unresolved_reason"] == "no_grounded_regions"
            assert row["total_region_members"] == 2
            assert row["grounded_region_members"] == 0
    _run(_t())


def test_build_unknown_region_role(db):
    """≥2 grounded 成员但未被 canonicalizer 处理 → unknown_region_role。"""
    async def _t():
        async with AsyncSessionLocal() as s:
            src = await _mk_region(s, "src", en="Test Source Area")
            tgt = await _mk_region(s, "tgt", en="Test Target Area")
            cand_a = await _mk_candidate(s, canonical_region_id=src)
            cand_b = await _mk_candidate(s, canonical_region_id=tgt)
            cid = await _mk_circuit(s, name="Grounded Members Circuit")
            await _mk_circuit_region(s, cid, cand_a)
            await _mk_circuit_region(s, cid, cand_b)
            result = await cgs.build_circuit_grounding(s, batch_size=500, atlas_filter=TEST_ATLAS)
            assert result["unresolved"]["unknown_region_role"] == 1
            row = (await s.execute(text(
                "SELECT g.unresolved_reason, g.total_region_members, g.grounded_region_members "
                "FROM mirror_circuit_canonical_grounding g WHERE g.mirror_circuit_id = :cid"
            ), {"cid": cid})).mappings().first()
            assert row["unresolved_reason"] == "unknown_region_role"
            assert row["total_region_members"] == 2
            assert row["grounded_region_members"] == 2
    _run(_t())


def test_build_grounded_row_carries_function_and_name_normalization(db):
    """回填行保留 function 计数 + 未回填行名称标准化落库。"""
    async def _t():
        async with AsyncSessionLocal() as s:
            src = await _mk_region(s, "src", en="Test Source Area")
            cand = await _mk_candidate(s, canonical_region_id=src)
            c1 = await _mk_circuit(s, name="  Norm   Name  Circuit  ", name_cn="标准名")
            await _mk_circuit_region(s, c1, cand)
            await _mk_circuit_function(s, c1)

            c2 = await _mk_circuit(s, name="  Grounded   Circuit  ")
            await _mk_circuit_region(s, c2, cand)
            await _mk_canonical_circuit(s, c2, en="Canonical Norm")

            result = await cgs.build_circuit_grounding(s, batch_size=500, atlas_filter=TEST_ATLAS)
            assert result["grounded"]["backfilled_from_canonical"] == 1
            assert result["unresolved"]["too_few_regions"] == 1

            row1 = (await s.execute(text(
                "SELECT g.canonical_name_en, g.function_count, g.status "
                "FROM mirror_circuit_canonical_grounding g WHERE g.mirror_circuit_id = :cid"
            ), {"cid": c1})).mappings().first()
            assert row1["canonical_name_en"] == "Norm Name Circuit"  # 标准化（压缩空白）
            assert row1["function_count"] == 1
            assert row1["status"] == "unresolved"

            row2 = (await s.execute(text(
                "SELECT g.canonical_name_en, g.status FROM mirror_circuit_canonical_grounding g "
                "WHERE g.mirror_circuit_id = :cid"
            ), {"cid": c2})).mappings().first()
            assert row2["canonical_name_en"] == "Canonical Norm"  # 回填取 canonical 侧
            assert row2["status"] == "grounded"
    _run(_t())


def test_build_resolved_connections(db):
    """projection membership → CN1 grounding 已 grounded 的 canonical connection。"""
    async def _t():
        async with AsyncSessionLocal() as s:
            src = await _mk_region(s, "src", en="Test Source Area")
            tgt = await _mk_region(s, "tgt", en="Test Target Area")
            cand_a = await _mk_candidate(s, canonical_region_id=src)
            cand_b = await _mk_candidate(s, canonical_region_id=tgt)
            cid = await _mk_circuit(s, name="Projection Circuit")
            await _mk_circuit_region(s, cid, cand_a)
            await _mk_circuit_region(s, cid, cand_b)
            conn_id, _ = await _mk_cn1_grounded_connection(
                s, src_region=src, tgt_region=tgt, src_cand=cand_a, tgt_cand=cand_b)
            await _mk_projection_membership(s, cid, conn_id)

            result = await cgs.build_circuit_grounding(s, batch_size=500, atlas_filter=TEST_ATLAS)
            assert result["unresolved"]["unknown_region_role"] == 1
            row = (await s.execute(text(
                "SELECT g.projection_membership_count, g.resolved_connection_count "
                "FROM mirror_circuit_canonical_grounding g WHERE g.mirror_circuit_id = :cid"
            ), {"cid": cid})).mappings().first()
            assert row["projection_membership_count"] == 1
            assert row["resolved_connection_count"] == 1
    _run(_t())


def test_build_idempotent(db):
    """重跑：已有行跳过，0 新写。"""
    async def _t():
        async with AsyncSessionLocal() as s:
            await _mk_circuit(s, name="Idempotent Circuit")
            first = await cgs.build_circuit_grounding(s, batch_size=500, atlas_filter=TEST_ATLAS)
            assert first["total_mirror_rows"] == 1

            second = await cgs.build_circuit_grounding(s, batch_size=500, atlas_filter=TEST_ATLAS)
            assert second["already_grounded_rows"] == 1
            assert second["total_mirror_rows"] == 1  # 扫描到已有行但不重写
            assert sum(second["unresolved"].values()) == 0
            assert second["grounded"]["backfilled_from_canonical"] == 0

            assert await _count_grounding(s) == 1  # 无重复行
    _run(_t())


def test_build_dry_run_writes_nothing(db):
    async def _t():
        async with AsyncSessionLocal() as s:
            await _mk_circuit(s, name="Dry Run Circuit")
            result = await cgs.build_circuit_grounding(s, batch_size=500, dry_run=True,
                                                       atlas_filter=TEST_ATLAS)
            assert result["total_mirror_rows"] == 1
            assert result["dry_run"] is True
            assert await _count_grounding(s) == 0
    _run(_t())


def test_build_batch_size_validation(db):
    async def _t():
        async with AsyncSessionLocal() as s:
            with pytest.raises(ValueError):
                await cgs.build_circuit_grounding(s, batch_size=100)
            with pytest.raises(ValueError):
                await cgs.build_circuit_grounding(s, batch_size=2000)
    _run(_t())


def test_stats_and_unresolved_report(db):
    async def _t():
        async with AsyncSessionLocal() as s:
            src = await _mk_region(s, "src", en="Test Source Area")
            cand = await _mk_candidate(s, canonical_region_id=src)
            c1 = await _mk_circuit(s, name="Grounded Stats Circuit")
            await _mk_circuit_region(s, c1, cand)
            await _mk_canonical_circuit(s, c1)
            await _mk_circuit(s, name="Unresolved Stats Circuit")

            before = await cgs.grounding_stats(s)
            await cgs.build_circuit_grounding(s, batch_size=500, atlas_filter=TEST_ATLAS)
            after = await cgs.grounding_stats(s)
            assert after["total_grounding_rows"] - before["total_grounding_rows"] == 2
            assert after["grounded"] - before["grounded"] == 1
            assert after["unresolved"] - before["unresolved"] == 1
            assert after["unresolved_by_reason"]["no_region_members"] \
                - before["unresolved_by_reason"].get("no_region_members", 0) == 1
            assert after["distinct_canonical_circuits"] - before["distinct_canonical_circuits"] == 1

            report = await cgs.unresolved_report(s, limit=5)
            assert report["sample_limit"] == 5
            assert any(r["reason"] == "no_region_members" for r in report["samples"])
            sample = next(r for r in report["samples"] if r["reason"] == "no_region_members")
            assert sample["circuit_name"] == "Unresolved Stats Circuit"
            assert sample["granularity_level"] == "macro"
            assert sample["total_region_members"] == 0
    _run(_t())
