"""CN1.2-1: Canonical Connection infrastructure tests.

Acceptance: canonical_connections CRUD with auto connection_code; endpoint
existence + species validation; identity dedup (source, target, type) with
directional keys; schema-level enum rejection; integrity checker; the 70,029
mirror_region_connections rows are never touched.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from pydantic import ValidationError
from sqlalchemy import text

from app.database import AsyncSessionLocal
from app.models.canonical_connection import CanonicalConnection
from app.schemas.canonical_connection import CanonicalConnectionCreate
from app.schemas.canonical_region import CanonicalRegionCreate
from app.services import canonical_connection_service as ccs
from app.services import canonical_region_service as crs

TEST_PREFIX = "cn1_test_"

pytestmark = pytest.mark.function_term_real


def _run(coro):
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except Exception:
        pass
    return asyncio.run(coro)


@pytest.fixture()
def db():
    """Delete CN1 test connections + regions before and after each test."""

    async def _cleanup() -> None:
        async with AsyncSessionLocal() as s:
            await s.execute(
                text(
                    "DELETE FROM canonical_connections WHERE "
                    "source_region_id IN (SELECT id FROM canonical_brain_regions "
                    "WHERE region_code LIKE 'ng:br:cn1_test_%') "
                    "OR target_region_id IN (SELECT id FROM canonical_brain_regions "
                    "WHERE region_code LIKE 'ng:br:cn1_test_%')"
                )
            )
            await s.execute(
                text("DELETE FROM canonical_brain_regions WHERE region_code LIKE 'ng:br:cn1_test_%'")
            )
            await s.commit()

    _run(_cleanup())
    yield
    _run(_cleanup())


async def _mk(session, code: str, *, species: str = "human", level: str = "clinical"):
    return await crs.create_canonical_region(
        session,
        CanonicalRegionCreate(
            region_code=f"ng:br:{TEST_PREFIX}{code}",
            canonical_name_en=f"cn1 test {code}",
            species=species,
            granularity_level=level,
            hemisphere_policy="lateralized",
            status="active",
            confidence=0.9,
            created_by="cn1_test",
        ),
    )


# --------------------------------------------------------------------------- #
# create + auto connection_code
# --------------------------------------------------------------------------- #


def test_create_with_auto_code(db):
    async def _t():
        async with AsyncSessionLocal() as s:
            src = await _mk(s, "src")
            tgt = await _mk(s, "tgt")
            conn = await ccs.create_canonical_connection(
                s,
                CanonicalConnectionCreate(
                    source_region_id=src.id,
                    target_region_id=tgt.id,
                    connection_type="structural",
                    directionality_policy="bidirectional",
                    confidence=0.8,
                    provenance_json={"phase": "cn1.2-1"},
                ),
            )
            await s.commit()
            assert conn.connection_code == "ng:cn:structural_cn1_test_src_to_cn1_test_tgt"
            assert conn.directionality_policy == "bidirectional"
            assert conn.status == "proposed"
            assert conn.granularity_level == "clinical"
            assert conn.species == "human"
            assert conn.provenance_json == {"phase": "cn1.2-1"}
            got = await s.get(CanonicalConnection, conn.id)
            assert got is not None and got.connection_code == conn.connection_code
    _run(_t())


def test_provided_code_and_code_collision(db):
    async def _t():
        async with AsyncSessionLocal() as s:
            src = await _mk(s, "src")
            tgt = await _mk(s, "tgt")
            c1 = await ccs.create_canonical_connection(
                s,
                CanonicalConnectionCreate(
                    source_region_id=src.id,
                    target_region_id=tgt.id,
                    connection_type="functional",
                    connection_code="ng:cn:cn1_test_custom",
                ),
            )
            assert c1.connection_code == "ng:cn:cn1_test_custom"
            with pytest.raises(ccs.CanonicalConnectionError, match="connection_code already exists"):
                await ccs.create_canonical_connection(
                    s,
                    CanonicalConnectionCreate(
                        source_region_id=tgt.id,
                        target_region_id=src.id,
                        connection_type="functional",
                        connection_code="ng:cn:cn1_test_custom",
                    ),
                )
    _run(_t())


# --------------------------------------------------------------------------- #
# endpoint validation
# --------------------------------------------------------------------------- #


def test_missing_endpoint_rejected(db):
    async def _t():
        async with AsyncSessionLocal() as s:
            src = await _mk(s, "src")
            with pytest.raises(ccs.CanonicalConnectionError, match="source canonical region not found"):
                await ccs.create_canonical_connection(
                    s,
                    CanonicalConnectionCreate(
                        source_region_id=uuid.uuid4(),
                        target_region_id=src.id,
                        connection_type="functional",
                    ),
                )
            with pytest.raises(ccs.CanonicalConnectionError, match="target canonical region not found"):
                await ccs.create_canonical_connection(
                    s,
                    CanonicalConnectionCreate(
                        source_region_id=src.id,
                        target_region_id=uuid.uuid4(),
                        connection_type="functional",
                    ),
                )
    _run(_t())


def test_self_loop_rejected(db):
    async def _t():
        async with AsyncSessionLocal() as s:
            src = await _mk(s, "src")
            with pytest.raises(ccs.CanonicalConnectionError, match="self-loop"):
                await ccs.create_canonical_connection(
                    s,
                    CanonicalConnectionCreate(
                        source_region_id=src.id,
                        target_region_id=src.id,
                        connection_type="structural",
                    ),
                )
    _run(_t())


def test_species_mismatch_rejected(db):
    async def _t():
        async with AsyncSessionLocal() as s:
            src = await _mk(s, "src")
            tgt = await _mk(s, "tgt")
            with pytest.raises(ccs.CanonicalConnectionError, match="species mismatch"):
                await ccs.create_canonical_connection(
                    s,
                    CanonicalConnectionCreate(
                        source_region_id=src.id,
                        target_region_id=tgt.id,
                        connection_type="functional",
                        species="mouse",
                    ),
                )
            mouse = await _mk(s, "mouse_tgt", species="mouse")
            # connection species unknown → per-endpoint guard skipped,
            # the human-vs-mouse endpoint conflict branch fires
            with pytest.raises(ccs.CanonicalConnectionError, match="endpoint species conflict"):
                await ccs.create_canonical_connection(
                    s,
                    CanonicalConnectionCreate(
                        source_region_id=src.id,
                        target_region_id=mouse.id,
                        connection_type="functional",
                        species="unknown",
                    ),
                )
    _run(_t())


# --------------------------------------------------------------------------- #
# identity + dedup
# --------------------------------------------------------------------------- #


def test_duplicate_identity_rejected(db):
    async def _t():
        async with AsyncSessionLocal() as s:
            src = await _mk(s, "src")
            tgt = await _mk(s, "tgt")
            first = await ccs.create_canonical_connection(
                s,
                CanonicalConnectionCreate(
                    source_region_id=src.id,
                    target_region_id=tgt.id,
                    connection_type="association",
                    directionality_policy="directed",
                ),
            )
            await s.flush()
            # same (source,target,type) but different directionality_policy → duplicate:
            # direction is NOT part of identity, so this must be rejected
            with pytest.raises(ccs.CanonicalConnectionError, match="duplicate connection"):
                await ccs.create_canonical_connection(
                    s,
                    CanonicalConnectionCreate(
                        source_region_id=src.id,
                        target_region_id=tgt.id,
                        connection_type="association",
                        directionality_policy="undirected",
                    ),
                )
            # reverse direction is a DIFFERENT key (explicit B->A concept is allowed;
            # CN1.2 only forbids auto-mirroring reverse rows)
            rev = await ccs.create_canonical_connection(
                s,
                CanonicalConnectionCreate(
                    source_region_id=tgt.id,
                    target_region_id=src.id,
                    connection_type="association",
                ),
            )
            assert rev.id != first.id
    _run(_t())


def test_normalize_connection_key(db):
    async def _t():
        async with AsyncSessionLocal() as s:
            src = await _mk(s, "src")
            tgt = await _mk(s, "tgt")
            key = ccs.normalize_connection_key(src.id, tgt.id, "functional")
            assert key == (src.id, tgt.id, "functional")
            rev = ccs.normalize_connection_key(tgt.id, src.id, "functional")
            assert key != rev  # directional identity
            with pytest.raises(ccs.CanonicalConnectionError):
                ccs.normalize_connection_key(src.id, tgt.id, "quantum")
    _run(_t())


# --------------------------------------------------------------------------- #
# schema-level enum rejection
# --------------------------------------------------------------------------- #


def test_invalid_type_rejected_by_schema():
    with pytest.raises(ValidationError, match="invalid connection_type"):
        CanonicalConnectionCreate(
            source_region_id=uuid.uuid4(),
            target_region_id=uuid.uuid4(),
            connection_type="quantum",
        )


def test_invalid_direction_rejected_by_schema():
    with pytest.raises(ValidationError, match="invalid directionality_policy"):
        CanonicalConnectionCreate(
            source_region_id=uuid.uuid4(),
            target_region_id=uuid.uuid4(),
            connection_type="structural",
            directionality_policy="sideways",
        )


def test_invalid_code_rejected_by_schema():
    with pytest.raises(ValidationError):
        CanonicalConnectionCreate(
            source_region_id=uuid.uuid4(),
            target_region_id=uuid.uuid4(),
            connection_type="structural",
            connection_code="bad-code",
        )


# --------------------------------------------------------------------------- #
# integrity checker
# --------------------------------------------------------------------------- #


def test_integrity_checker_clean(db):
    async def _t():
        async with AsyncSessionLocal() as s:
            result = await ccs.check_canonical_connection_integrity(s)
            assert result["ok"] is True, result["issues"]
            assert result["counts"]["mirror_connections_untouched"] == 70029
            src = await _mk(s, "src")
            tgt = await _mk(s, "tgt")
            await ccs.create_canonical_connection(
                s,
                CanonicalConnectionCreate(
                    source_region_id=src.id,
                    target_region_id=tgt.id,
                    connection_type="projection",
                ),
            )
            await s.commit()
            result = await ccs.check_canonical_connection_integrity(s)
            assert result["ok"] is True, result["issues"]
            assert result["counts"]["type_projection"] == 1
    _run(_t())


def test_integrity_detects_species_mismatch(db):
    async def _t():
        async with AsyncSessionLocal() as s:
            src = await _mk(s, "src")
            tgt = await _mk(s, "tgt")
            await s.flush()
            # bypass the service to plant an invalid row (species has no DB CHECK)
            await s.execute(
                text(
                    "INSERT INTO canonical_connections (connection_code, source_region_id, "
                    "target_region_id, connection_type, directionality_policy, species, "
                    "granularity_level, status) VALUES ('ng:cn:cn1_test_planted', :s, :t, "
                    "'structural', 'unspecified', 'mouse', 'clinical', 'proposed')"
                ),
                {"s": str(src.id), "t": str(tgt.id)},
            )
            await s.commit()
            result = await ccs.check_canonical_connection_integrity(s)
            codes = [i["code"] for i in result["issues"]]
            assert "SPECIES_MISMATCH" in codes
            assert result["ok"] is False
    _run(_t())


# --------------------------------------------------------------------------- #
# 70,029 mirror connections untouched
# --------------------------------------------------------------------------- #


def test_mirror_connections_untouched(db):
    async def _t():
        async with AsyncSessionLocal() as s:
            before = int(
                (await s.execute(text("SELECT count(*) FROM mirror_region_connections"))).scalar_one()
            )
            spot = (
                await s.execute(
                    text("SELECT id, updated_at FROM mirror_region_connections ORDER BY id LIMIT 1")
                )
            ).first()
            src = await _mk(s, "src")
            tgt = await _mk(s, "tgt")
            await ccs.create_canonical_connection(
                s,
                CanonicalConnectionCreate(
                    source_region_id=src.id,
                    target_region_id=tgt.id,
                    connection_type="coactivation",
                ),
            )
            await s.commit()
            after = int(
                (await s.execute(text("SELECT count(*) FROM mirror_region_connections"))).scalar_one()
            )
            spot_after = (
                await s.execute(
                    text("SELECT updated_at FROM mirror_region_connections WHERE id=:i"),
                    {"i": str(spot[0])},
                )
            ).scalar_one()
            assert before == 70029
            assert after == 70029
            assert spot_after == spot[1]  # no row was even touched
    _run(_t())
