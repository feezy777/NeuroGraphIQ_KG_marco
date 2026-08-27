"""Inference governance tests — assertion_type 体系 + provenance metadata (20260902).

Covers:
  * assertion_type 词表 — 4 值（reported_fact / inferred / hypothesis / candidate）+ seq + active
  * 4 类对象关联 — canonical_connections / canonical_circuits /
    canonical_circuit_functions（Function relation）/ atlas_region_mappings
    （BrainRegion mapping）均有 assertion_type / source_type /
    generation_method / evidence_reference 四列
  * 历史行默认值回填（NOT NULL DEFAULT 生效，无 NULL）
  * CHECK 约束 — 非法 assertion_type / source_type 拒绝
  * inferred 写入往返 — 证明推理产出可分层写入（不执行任何推理）
  * migration 幂等重跑

隔离：测试数据带 ig_test_ 前缀，前后清理；不执行 roll-up / abstraction /
promotion，不修改 mirror 行。
"""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.database import AsyncSessionLocal
from app.schemas.canonical_connection import CanonicalConnectionCreate
from app.schemas.canonical_region import CanonicalRegionCreate
from app.services import canonical_connection_service as ccs
from app.services import canonical_region_service as crs

TEST_PREFIX = "ig_test_"
MIGRATION_PATH = Path(__file__).resolve().parent.parent / "migrations" / "20260902_assertion_type_inference_governance.sql"

# 4 类对象 + 各自的清理条件键
GOVERNED_TABLES = (
    "canonical_connections",
    "canonical_circuits",
    "canonical_circuit_functions",
    "atlas_region_mappings",
)

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
            # 1) canonical_circuit_functions（FK circuit CASCADE，显式删更稳）
            await s.execute(text(
                "DELETE FROM canonical_circuit_functions WHERE circuit_id IN "
                f"(SELECT id FROM canonical_circuits WHERE circuit_code LIKE 'ng:ci:{TEST_PREFIX}%')"
            ))
            # 2) atlas_region_mappings + resources（mappings FK CASCADE，显式删）
            await s.execute(text(
                "DELETE FROM atlas_region_mappings WHERE atlas_region_id IN "
                f"(SELECT id FROM atlas_region_resources WHERE atlas_name LIKE '{TEST_PREFIX}%')"
            ))
            await s.execute(text(
                f"DELETE FROM atlas_region_resources WHERE atlas_name LIKE '{TEST_PREFIX}%'"
            ))
            # 3) canonical circuits
            await s.execute(text(
                f"DELETE FROM canonical_circuits WHERE circuit_code LIKE 'ng:ci:{TEST_PREFIX}%'"
            ))
            # 4) canonical connections（按 region 归属清理）
            await s.execute(text(
                "DELETE FROM canonical_connections WHERE "
                "source_region_id IN (SELECT id FROM canonical_brain_regions "
                f"WHERE region_code LIKE 'ng:br:{TEST_PREFIX}%') "
                "OR target_region_id IN (SELECT id FROM canonical_brain_regions "
                f"WHERE region_code LIKE 'ng:br:{TEST_PREFIX}%')"
            ))
            # 5) ontology terms + canonical regions
            await s.execute(text(f"DELETE FROM ontology_terms WHERE term_code LIKE '{TEST_PREFIX}%'"))
            await s.execute(text(
                f"DELETE FROM canonical_brain_regions WHERE region_code LIKE 'ng:br:{TEST_PREFIX}%'"
            ))
            await s.commit()

    _run(_cleanup())
    yield
    _run(_cleanup())


async def _mk_region(session, code: str, *, en: str) -> uuid.UUID:
    region = await crs.create_canonical_region(
        session,
        CanonicalRegionCreate(
            region_code=f"ng:br:{TEST_PREFIX}{code}",
            canonical_name_en=en,
            species="human",
            granularity_level="clinical",
            hemisphere_policy="bilateral",
            status="active",
            confidence=0.9,
            created_by="ig_test",
        ),
    )
    await session.commit()
    return region.id


async def _mk_connection(session, src: uuid.UUID, tgt: uuid.UUID) -> uuid.UUID:
    conn = await ccs.create_canonical_connection(
        session,
        CanonicalConnectionCreate(
            source_region_id=src,
            target_region_id=tgt,
            connection_type="structural",
            provenance_json={"original_connection_ids": [str(uuid.uuid4())]},
        ),
    )
    await session.commit()
    return conn.id


async def _mk_circuit(session) -> uuid.UUID:
    cid = uuid.uuid4()
    await session.execute(text(
        "INSERT INTO canonical_circuits "
        "(id, circuit_code, canonical_name_en, species, granularity_level, "
        "circuit_type, status) VALUES "
        f"(:id, 'ng:ci:{TEST_PREFIX}{uuid.uuid4().hex[:10]}', 'IG Test Circuit', "
        "'human', 'clinical', 'network', 'proposed')"
    ), {"id": cid})
    await session.commit()
    return cid


async def _mk_term(session) -> uuid.UUID:
    tid = uuid.uuid4()
    await session.execute(text(
        "INSERT INTO ontology_terms (id, term_code, canonical_term_en, term_type, status) "
        "VALUES (:id, :code, 'ig test function', 'function', 'active')"
    ), {"id": tid, "code": f"{TEST_PREFIX}term{uuid.uuid4().hex[:10]}"})
    await session.commit()
    return tid


async def _mk_circuit_function(session, circuit_id: uuid.UUID, term_id: uuid.UUID) -> uuid.UUID:
    fid = uuid.uuid4()
    await session.execute(text(
        "INSERT INTO canonical_circuit_functions (id, circuit_id, function_term_id, relation_type) "
        "VALUES (:id, :cid, :tid, 'associated_with')"
    ), {"id": fid, "cid": circuit_id, "tid": term_id})
    await session.commit()
    return fid


async def _mk_atlas_mapping(session) -> uuid.UUID:
    aid = uuid.uuid4()
    await session.execute(text(
        "INSERT INTO atlas_region_resources "
        "(id, atlas_name, atlas_version, atlas_region_id, region_name, species, hemisphere) "
        f"VALUES (:id, '{TEST_PREFIX}atlas', 'v1', 'A1', 'IG Area 1', 'human', 'bilateral')"
    ), {"id": aid})
    mid = uuid.uuid4()
    await session.execute(text(
        "INSERT INTO atlas_region_mappings "
        "(id, atlas_region_id, mapping_type, species_relation, status, created_by) "
        "VALUES (:id, :aid, 'exact', 'same_species', 'active', 'ig_test')"
    ), {"id": mid, "aid": aid})
    await session.commit()
    return mid


async def _assert_check_rejects(session, sql: str, params: dict) -> None:
    """CHECK 拒绝验证：执行后必须 IntegrityError，然后 rollback。"""
    try:
        await session.execute(text(sql), params)
        await session.commit()
        raise AssertionError(f"expected IntegrityError for {sql}")
    except IntegrityError:
        await session.rollback()


# --------------------------------------------------------------------------- #
# 1. assertion_type 词表
# --------------------------------------------------------------------------- #


def test_vocab_assertion_type_entries(db):
    async def _t():
        async with AsyncSessionLocal() as s:
            rows = (await s.execute(text(
                "SELECT code, seq, status FROM ontology_vocabularies "
                "WHERE vocab_type = 'assertion_type' ORDER BY seq"
            ))).all()
            assert [(r.code, r.seq, r.status) for r in rows] == [
                ("reported_fact", 10, "active"),
                ("inferred", 20, "active"),
                ("hypothesis", 30, "active"),
                ("candidate", 40, "active"),
            ]
            # label_en 非空
            labels = (await s.execute(text(
                "SELECT count(*) FROM ontology_vocabularies "
                "WHERE vocab_type = 'assertion_type' AND label_en IS NULL"
            ))).scalar_one()
            assert labels == 0
    _run(_t())


# --------------------------------------------------------------------------- #
# 2. 4 类对象关联 — 列存在 + 默认值
# --------------------------------------------------------------------------- #


def test_four_tables_have_governance_columns(db):
    async def _t():
        async with AsyncSessionLocal() as s:
            for table in GOVERNED_TABLES:
                cols = (await s.execute(text(
                    "SELECT column_name, is_nullable, column_default "
                    "FROM information_schema.columns WHERE table_name = :t "
                    "AND column_name IN ('assertion_type','source_type','generation_method',"
                    "'evidence_reference')"
                ), {"t": table})).all()
                col_map = {c: (n, d) for c, n, d in cols}
                assert set(col_map) == {"assertion_type", "source_type", "generation_method", "evidence_reference"}, table
                assert col_map["assertion_type"] == ("NO", "'reported_fact'::character varying"), table
                assert col_map["source_type"] == ("NO", "'unknown'::character varying"), table
                assert col_map["generation_method"] == ("NO", "'unknown'::character varying"), table
                assert col_map["evidence_reference"][0] == "NO", table
                # CHECK 约束各 2 条
                cons = (await s.execute(text(
                    "SELECT conname FROM pg_constraint WHERE conrelid = CAST(:t AS regclass) "
                    "AND conname LIKE 'ck_%'"
                ), {"t": table})).all()
                names = sorted(c[0] for c in cons)
                assert f"ck_{table}_assertion_type" in names, table
                assert f"ck_{table}_source_type" in names, table
    _run(_t())


def test_insert_defaults_roundtrip(db):
    """不指定新列 INSERT → 默认值 reported_fact / unknown / unknown / []。"""
    async def _t():
        async with AsyncSessionLocal() as s:
            src = await _mk_region(s, "src", en="IG Source")
            tgt = await _mk_region(s, "tgt", en="IG Target")
            conn = await _mk_connection(s, src, tgt)
            circ = await _mk_circuit(s)
            term = await _mk_term(s)
            cf = await _mk_circuit_function(s, circ, term)
            mp = await _mk_atlas_mapping(s)

            checks = [
                ("canonical_connections", conn),
                ("canonical_circuits", circ),
                ("canonical_circuit_functions", cf),
                ("atlas_region_mappings", mp),
            ]
            for table, row_id in checks:
                row = (await s.execute(text(
                    "SELECT assertion_type, source_type, generation_method, evidence_reference "
                    f"FROM {table} WHERE id = :id"
                ), {"id": row_id})).one()
                assert row == ("reported_fact", "unknown", "unknown", []), table
    _run(_t())


def test_defaults_applied_to_existing_rows(db):
    """迁移后既有行已回填默认值（NOT NULL DEFAULT 生效，无 NULL/漂移）。"""
    async def _t():
        async with AsyncSessionLocal() as s:
            for table in GOVERNED_TABLES:
                total, complete = (await s.execute(text(
                    f"SELECT count(*), "
                    f"count(*) FILTER (WHERE assertion_type = 'reported_fact' "
                    f"AND source_type = 'unknown' AND generation_method = 'unknown' "
                    f"AND evidence_reference = '[]'::jsonb) "
                    f"FROM {table}"
                ))).one()
                assert total == complete, f"{table}: {complete}/{total} 行默认值完整"
    _run(_t())


# --------------------------------------------------------------------------- #
# 3. inferred 写入往返 — 推理产出可分层写入（不执行推理本身）
# --------------------------------------------------------------------------- #


def test_inferred_write_roundtrip(db):
    async def _t():
        async with AsyncSessionLocal() as s:
            src = await _mk_region(s, "i_src", en="IG Inferred Source")
            tgt = await _mk_region(s, "i_tgt", en="IG Inferred Target")
            conn = await ccs.create_canonical_connection(
                s,
                CanonicalConnectionCreate(
                    source_region_id=src,
                    target_region_id=tgt,
                    connection_type="structural",
                    provenance_json={"original_connection_ids": [str(uuid.uuid4())]},
                ),
            )
            # 推理产出：显式写 assertion_type='inferred' + 完整 provenance metadata
            conn.assertion_type = "inferred"
            conn.source_type = "rule_inference"
            conn.generation_method = "cn2_connection_rollup_v1"
            conn.evidence_reference = [str(uuid.uuid4()), str(uuid.uuid4())]
            await s.commit()

            row = (await s.execute(text(
                "SELECT assertion_type, source_type, generation_method, "
                "jsonb_array_length(evidence_reference), confidence "
                "FROM canonical_connections WHERE id = :id"
            ), {"id": conn.id})).one()
            assert row == ("inferred", "rule_inference", "cn2_connection_rollup_v1", 2, None)
    _run(_t())


# --------------------------------------------------------------------------- #
# 4. CHECK 约束
# --------------------------------------------------------------------------- #


def test_check_rejects_bad_assertion_type(db):
    async def _t():
        async with AsyncSessionLocal() as s:
            src = await _mk_region(s, "c_src", en="IG Check Source")
            tgt = await _mk_region(s, "c_tgt", en="IG Check Target")
            conn = await _mk_connection(s, src, tgt)
            circ = await _mk_circuit(s)
            term = await _mk_term(s)
            cf = await _mk_circuit_function(s, circ, term)
            mp = await _mk_atlas_mapping(s)

            await _assert_check_rejects(s,
                "UPDATE canonical_connections SET assertion_type = 'fabricated' WHERE id = :id",
                {"id": conn})
            await _assert_check_rejects(s,
                "UPDATE canonical_circuits SET assertion_type = 'fabricated' WHERE id = :id",
                {"id": circ})
            await _assert_check_rejects(s,
                "UPDATE canonical_circuit_functions SET assertion_type = 'fabricated' WHERE id = :id",
                {"id": cf})
            await _assert_check_rejects(s,
                "UPDATE atlas_region_mappings SET assertion_type = 'fabricated' WHERE id = :id",
                {"id": mp})
    _run(_t())


def test_check_rejects_bad_source_type(db):
    async def _t():
        async with AsyncSessionLocal() as s:
            circ = await _mk_circuit(s)
            await _assert_check_rejects(s,
                "UPDATE canonical_circuits SET source_type = 'crystal_ball' WHERE id = :id",
                {"id": circ})
            mp = await _mk_atlas_mapping(s)
            await _assert_check_rejects(s,
                "UPDATE atlas_region_mappings SET source_type = 'crystal_ball' WHERE id = :id",
                {"id": mp})
    _run(_t())


def test_migration_idempotent_rerun(db):
    """migration 文件重跑安全（ON CONFLICT + IF NOT EXISTS + 约束存在性守卫）。"""
    assert MIGRATION_PATH.exists(), str(MIGRATION_PATH)
    sql = MIGRATION_PATH.read_text(encoding="utf-8")

    async def _t():
        async with AsyncSessionLocal() as s:
            await s.execute(text(sql))
            await s.commit()
            # 重跑后词表仍 4 行、列仍存在
            n = (await s.execute(text(
                "SELECT count(*) FROM ontology_vocabularies WHERE vocab_type = 'assertion_type'"
            ))).scalar_one()
            assert n == 4
            cols = (await s.execute(text(
                "SELECT count(*) FROM information_schema.columns WHERE table_name = 'canonical_connections' "
                "AND column_name = 'assertion_type'"
            ))).scalar_one()
            assert cols == 1
    _run(_t())
