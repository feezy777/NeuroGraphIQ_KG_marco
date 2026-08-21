"""CN1.2-2B: Macro96 connection canonicalization tests.

Acceptance: single-row groups become canonical connections with full
provenance; duplicate rows merge (max confidence); reverse directed pairs
become bidirectional (no mirrored rows); structural/functional never merge;
unmapped rows are refused; dry_run is deterministic and writes nothing;
the 70,029 mirror rows are never touched.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from sqlalchemy import select, text

from app.database import AsyncSessionLocal
from app.models.canonical_connection import CanonicalConnection
from app.schemas.canonical_region import CanonicalRegionCreate
from app.services import canonical_connection_service as ccs
from app.services import canonical_region_service as crs
from app.services import macro_connection_canonicalizer as mcs

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


async def _mk(session, code: str):
    return await crs.create_canonical_region(
        session,
        CanonicalRegionCreate(
            region_code=f"ng:br:{TEST_PREFIX}{code}",
            canonical_name_en=f"cn1 test {code}",
            species="human",
            granularity_level="clinical",
            hemisphere_policy="lateralized",
            status="active",
            confidence=0.9,
            created_by="cn1_test",
        ),
    )


def _row(src, tgt, rtype, direction, confidence, cid=None):
    return {
        "connection_id": cid or uuid.uuid4(),
        "source_atlas": "Macro96",
        "source_candidate_id": uuid.uuid4(),
        "target_candidate_id": uuid.uuid4(),
        "source_canonical_region_id": src,
        "target_canonical_region_id": tgt,
        "connection_type": rtype,
        "directionality": direction,
        "confidence": confidence,
    }


# --------------------------------------------------------------------------- #
# resolve_directionality_policy unit rules
# --------------------------------------------------------------------------- #


def test_direction_merge_rules():
    assert mcs.resolve_directionality_policy(["directed", "directed"]) == "directed"
    assert mcs.resolve_directionality_policy(["undirected", "directed"]) == "directed"  # rule: bidirectional only upgrades
    assert mcs.resolve_directionality_policy(["bidirectional", "directed"]) == "bidirectional"
    assert mcs.resolve_directionality_policy(["undirected", "undirected"]) == "undirected"
    assert mcs.resolve_directionality_policy(["unspecified", "unspecified"]) == "unspecified"
    # reverse pair of all-directed groups -> bidirectional
    assert (
        mcs.resolve_directionality_policy(
            ["directed"], reverse_directions=["directed"]
        )
        == "bidirectional"
    )
    # reverse pair where this side is not all directed -> no upgrade
    assert (
        mcs.resolve_directionality_policy(
            ["unspecified"], reverse_directions=["directed"]
        )
        == "unspecified"
    )
    # mixed fallback: most determinate wins
    assert mcs.resolve_directionality_policy(["directed", "unspecified"]) == "directed"
    assert mcs.resolve_directionality_policy(["undirected", "unspecified"]) == "undirected"


# --------------------------------------------------------------------------- #
# plan/write on synthetic rows
# --------------------------------------------------------------------------- #


def test_single_connection_generated(db):
    async def _t():
        async with AsyncSessionLocal() as s:
            src = await _mk(s, "src")
            tgt = await _mk(s, "tgt")
            plan = mcs.plan_macro96_canonicalizations(
                [_row(src.id, tgt.id, "structural_connection", "directed", 0.9)]
            )
            assert plan["stats"]["total_candidates"] == 1
            assert plan["stats"]["unmapped"] == 0
            assert len(plan["groups"]) == 1
            g = plan["groups"][0]
            assert g["connection_type"] == "structural"
            assert g["directionality_policy"] == "directed"
            result = await mcs.write_canonical_groups(s, plan["groups"])
            assert result == {"created": 1, "enriched": 0, "skipped_existing": 0}
            await s.commit()
            rows = (
                await s.execute(
                    select(CanonicalConnection).where(
                        CanonicalConnection.source_region_id == src.id,
                        CanonicalConnection.target_region_id == tgt.id,
                    )
                )
            ).scalars().all()
            assert len(rows) == 1
            assert rows[0].connection_type == "structural"
            assert rows[0].directionality_policy == "directed"
            assert float(rows[0].confidence) == 0.9
            assert rows[0].status == "proposed"
            assert rows[0].granularity_level == "clinical"
            integrity = await ccs.check_canonical_connection_integrity(s)
            assert integrity["ok"] is True, integrity["issues"]
    _run(_t())


def test_duplicate_rows_merge(db):
    async def _t():
        async with AsyncSessionLocal() as s:
            src = await _mk(s, "src")
            tgt = await _mk(s, "tgt")
            rows = [
                _row(src.id, tgt.id, "projection", "directed", 0.3),
                _row(src.id, tgt.id, "structural_connection", "directed", 0.7),
            ]
            plan = mcs.plan_macro96_canonicalizations(rows)
            assert plan["stats"]["duplicate_groups"] == 1
            assert len(plan["groups"]) == 1
            g = plan["groups"][0]
            # projection + structural_connection collapse into one structural key
            assert g["connection_type"] == "structural"
            assert len(g["provenance_json"]["original_connection_ids"]) == 2
            result = await mcs.write_canonical_groups(s, plan["groups"])
            assert result["created"] == 1
            await s.commit()
            conns = (
                await s.execute(
                    select(CanonicalConnection).where(
                        CanonicalConnection.source_region_id == src.id,
                        CanonicalConnection.target_region_id == tgt.id,
                    )
                )
            ).scalars().all()
            assert len(conns) == 1
    _run(_t())


def test_confidence_takes_max(db):
    async def _t():
        async with AsyncSessionLocal() as s:
            src = await _mk(s, "src")
            tgt = await _mk(s, "tgt")
            plan = mcs.plan_macro96_canonicalizations(
                [_row(src.id, tgt.id, "association", "undirected", 0.2),
                 _row(src.id, tgt.id, "association", "undirected", 0.8)]
            )
            assert plan["groups"][0]["confidence"] == 0.8
            # None mixed with a value -> value wins
            plan2 = mcs.plan_macro96_canonicalizations(
                [_row(src.id, tgt.id, "coactivation", "undirected", None),
                 _row(src.id, tgt.id, "coactivation", "undirected", 0.5)]
            )
            assert plan2["groups"][0]["confidence"] == 0.5
            # all None -> None
            plan3 = mcs.plan_macro96_canonicalizations(
                [_row(src.id, tgt.id, "uncertain_connection", "unknown", None)]
            )
            assert plan3["groups"][0]["confidence"] is None
    _run(_t())


def test_provenance_complete(db):
    async def _t():
        async with AsyncSessionLocal() as s:
            src = await _mk(s, "src")
            tgt = await _mk(s, "tgt")
            cid1, cid2 = uuid.uuid4(), uuid.uuid4()
            rows = [
                _row(src.id, tgt.id, "functional_connectivity", "directed", 0.4, cid=cid1),
                _row(src.id, tgt.id, "effective_connectivity", "unknown", 0.6, cid=cid2),
            ]
            plan = mcs.plan_macro96_canonicalizations(rows)
            g = plan["groups"][0]
            assert g["connection_type"] == "functional"
            assert set(g["provenance_json"].keys()) == {
                "original_connection_ids",
                "original_relation_types",
                "original_confidence",
                "mapping_method",
                "endpoint_grounding",
            }
            assert g["provenance_json"]["endpoint_grounding"]["grounding_source"] == (
                "candidate_brain_regions.canonical_region_id"
            )
            assert g["provenance_json"]["endpoint_grounding"]["source_atlas_labels"] == [
                "Macro96",
                "Macro96",
            ]
            assert g["provenance_json"]["original_connection_ids"] == [str(cid1), str(cid2)]
            assert g["provenance_json"]["original_relation_types"] == [
                "functional_connectivity",
                "effective_connectivity",
            ]
            assert g["provenance_json"]["original_confidence"] == [0.4, 0.6]
            assert g["provenance_json"]["mapping_method"] == "macro96_canonical_connection_v1"
            # original directions preserved (never overwritten)
            assert g["source_summary"]["original_directions"] == ["directed", "unknown"]
            await mcs.write_canonical_groups(s, plan["groups"])
            await s.commit()
            conn = (
                await s.execute(
                    select(CanonicalConnection).where(
                        CanonicalConnection.source_region_id == src.id,
                        CanonicalConnection.target_region_id == tgt.id,
                    )
                )
            ).scalar_one()
            assert conn.provenance_json == g["provenance_json"]
            assert conn.directionality_policy == "directed"  # mixed directed+unspecified -> directed
    _run(_t())


def test_reverse_pair_becomes_bidirectional(db):
    async def _t():
        async with AsyncSessionLocal() as s:
            a = await _mk(s, "a")
            b = await _mk(s, "b")
            rows = [
                _row(a.id, b.id, "projection", "directed", 0.5),
                _row(a.id, b.id, "structural_connection", "directed", 0.6),
                _row(b.id, a.id, "projection", "directed", 0.4),
            ]
            plan = mcs.plan_macro96_canonicalizations(rows)
            assert len(plan["groups"]) == 2  # A->B and B->A stay separate keys
            assert plan["stats"]["reverse_pair_groups"] == 2
            assert {g["directionality_policy"] for g in plan["groups"]} == {"bidirectional"}
            await mcs.write_canonical_groups(s, plan["groups"])
            await s.commit()
            conns = (
                await s.execute(
                    select(CanonicalConnection).where(
                        CanonicalConnection.connection_code.like("ng:cn:structural_cn1_test_%")
                    )
                )
            ).scalars().all()
            assert len(conns) == 2
            assert {c.directionality_policy for c in conns} == {"bidirectional"}
    _run(_t())


def test_structural_and_functional_not_merged(db):
    async def _t():
        async with AsyncSessionLocal() as s:
            a = await _mk(s, "a")
            b = await _mk(s, "b")
            plan = mcs.plan_macro96_canonicalizations(
                [
                    _row(a.id, b.id, "structural_connection", "directed", 0.5),
                    _row(a.id, b.id, "functional_connectivity", "directed", 0.5),
                ]
            )
            assert len(plan["groups"]) == 2
            assert {g["connection_type"] for g in plan["groups"]} == {"structural", "functional"}
            assert {g["key"] for g in plan["groups"]} == {
                (str(a.id), str(b.id), "structural"),
                (str(a.id), str(b.id), "functional"),
            }
    _run(_t())


def test_mislabeled_atlas_rows_are_eligible(db):
    """CI1.3-2: eligibility is endpoint grounding, never the source_atlas label.

    A row labeled Allen_HBA_2012 whose endpoint candidates are grounded enters
    the plan like any Macro96 row; the original label is preserved verbatim in
    source_summary and endpoint_grounding.
    """

    async def _t():
        async with AsyncSessionLocal() as s:
            src = await _mk(s, "src")
            tgt = await _mk(s, "tgt")
            row = _row(src.id, tgt.id, "structural_connection", "undirected", 0.5)
            row["source_atlas"] = "Allen_HBA_2012"
            plan = mcs.plan_macro96_canonicalizations([row])
            assert plan["stats"]["self_loop_rows"] == 0
            assert plan["stats"]["unmapped"] == 0
            assert len(plan["groups"]) == 1
            g = plan["groups"][0]
            assert g["source_summary"]["source_atlas"] == "Allen_HBA_2012"
            eg = g["provenance_json"]["endpoint_grounding"]
            assert eg["grounding_source"] == "candidate_brain_regions.canonical_region_id"
            assert eg["source_canonical_region_id"] == str(src.id)
            assert eg["target_canonical_region_id"] == str(tgt.id)
            assert eg["source_atlas_labels"] == ["Allen_HBA_2012"]
            assert eg["source_candidate_ids"] == [str(row["source_candidate_id"])]
            assert eg["target_candidate_ids"] == [str(row["target_candidate_id"])]

    _run(_t())


def test_mixed_atlas_labels_in_merged_group(db):
    """CI1.3-2: merged groups mixing labels keep every original label."""

    async def _t():
        async with AsyncSessionLocal() as s:
            a = await _mk(s, "a")
            b = await _mk(s, "b")
            row_macro = _row(a.id, b.id, "association", "undirected", 0.5)
            row_allen = _row(a.id, b.id, "association", "undirected", 0.6)
            row_allen["source_atlas"] = "Allen_HBA_2012"
            plan = mcs.plan_macro96_canonicalizations([row_macro, row_allen])
            assert len(plan["groups"]) == 1
            g = plan["groups"][0]
            assert g["source_summary"]["source_atlas"] == [
                "Allen_HBA_2012",
                "Macro96",
            ]
            assert g["provenance_json"]["endpoint_grounding"]["source_atlas_labels"] == [
                "Macro96",
                "Allen_HBA_2012",
            ]
            assert g["confidence"] == 0.6

    _run(_t())


def test_duplicate_key_evidence_merges_into_existing(db):
    """CI1.3-2: a new mirror row whose identity key already exists cannot
    create a second canonical row — its evidence merges into the existing
    row's provenance (idempotent, max confidence, label preserved)."""

    async def _t():
        async with AsyncSessionLocal() as s:
            a = await _mk(s, "a")
            b = await _mk(s, "b")
            cid1 = uuid.uuid4()
            first = mcs.plan_macro96_canonicalizations(
                [_row(a.id, b.id, "association", "undirected", 0.4, cid=cid1)]
            )
            assert (await mcs.write_canonical_groups(s, first["groups"])) == {
                "created": 1,
                "enriched": 0,
                "skipped_existing": 0,
            }
            await s.flush()

            # second mirror row, same key, mislabeled atlas
            row2 = _row(a.id, b.id, "association", "undirected", 0.9)
            row2["source_atlas"] = "Allen_HBA_2012"
            second = mcs.plan_macro96_canonicalizations([row2])
            assert (await mcs.write_canonical_groups(s, second["groups"])) == {
                "created": 0,
                "enriched": 1,
                "skipped_existing": 0,
            }
            await s.flush()

            conn = (
                await s.execute(
                    select(CanonicalConnection).where(
                        CanonicalConnection.source_region_id == a.id,
                        CanonicalConnection.target_region_id == b.id,
                    )
                )
            ).scalar_one()
            assert conn.provenance_json["original_connection_ids"] == [
                str(cid1),
                str(row2["connection_id"]),
            ]
            assert conn.provenance_json["original_confidence"] == [0.4, 0.9]
            assert float(conn.confidence) == 0.9  # max wins
            eg = conn.provenance_json["endpoint_grounding"]
            assert eg["merged_existing_provenance"] is True
            # endpoint_grounding is cumulative: prior rows' grounding basis first,
            # then the newly merged rows'
            assert eg["source_atlas_labels"] == ["Macro96", "Allen_HBA_2012"]
            assert conn.source_summary["source_atlas"] == [
                "Allen_HBA_2012",
                "Macro96",
            ]
            assert conn.source_summary["merged_rows"] == 2

            # third write of the same plan merges nothing new
            assert (await mcs.write_canonical_groups(s, second["groups"])) == {
                "created": 0,
                "enriched": 0,
                "skipped_existing": 1,
            }

    _run(_t())


def test_forecast_empty_ids_returns_zeros(db):
    async def _t():
        async with AsyncSessionLocal() as s:
            forecast = await mcs.forecast_circuit_closure(s, [])
            assert forecast == {
                "newly_resolvable_projection_memberships": 0,
                "newly_closable_circuit_count": 0,
                "newly_closable_circuits": [],
                "fully_aligned_among_closable": 0,
            }

    _run(_t())


def test_unmapped_rows_refused(db):
    async def _t():
        async with AsyncSessionLocal() as s:
            a = await _mk(s, "a")
            b = await _mk(s, "b")
            plan = mcs.plan_macro96_canonicalizations(
                [
                    _row(a.id, b.id, "quantum", "directed", 0.5),
                    _row(a.id, b.id, "association", "sideways", 0.5),
                    _row(a.id, b.id, "association", "directed", 0.5),
                ]
            )
            assert plan["stats"]["unmapped"] == 2
            assert len(plan["groups"]) == 1  # only the mappable row becomes a group
            with pytest.raises(mcs.MacroCanonicalizerError, match="unmapped mirror rows"):
                mcs._raise_on_unmapped(plan["unmapped_rows"])
            # writing the groups writes ONLY the mapped one — unmapped never reaches DB
            result = await mcs.write_canonical_groups(s, plan["groups"])
            assert result == {"created": 1, "enriched": 0, "skipped_existing": 0}
    _run(_t())


def test_self_loop_rows_excluded(db):
    async def _t():
        async with AsyncSessionLocal() as s:
            a = await _mk(s, "a")
            b = await _mk(s, "b")
            plan = mcs.plan_macro96_canonicalizations(
                [
                    _row(a.id, a.id, "association", "directed", 0.5),
                    _row(a.id, b.id, "association", "directed", 0.5),
                ]
            )
            assert plan["stats"]["self_loop_rows"] == 1
            assert len(plan["groups"]) == 1
    _run(_t())


def test_idempotent_write(db):
    async def _t():
        async with AsyncSessionLocal() as s:
            a = await _mk(s, "a")
            b = await _mk(s, "b")
            plan = mcs.plan_macro96_canonicalizations(
                [_row(a.id, b.id, "association", "directed", 0.5)]
            )
            assert (await mcs.write_canonical_groups(s, plan["groups"])) == {
                "created": 1,
                "enriched": 0,
                "skipped_existing": 0,
            }
            await s.flush()
            # second write of the same plan skips everything
            assert (await mcs.write_canonical_groups(s, plan["groups"])) == {
                "created": 0,
                "enriched": 0,
                "skipped_existing": 1,
            }
    _run(_t())


# --------------------------------------------------------------------------- #
# real-data dry_run + untouched mirror rows
# --------------------------------------------------------------------------- #


def test_dry_run_deterministic_and_writes_nothing(db):
    async def _t():
        async with AsyncSessionLocal() as s:
            before_cc = int(
                (await s.execute(text("SELECT count(*) FROM canonical_connections"))).scalar_one()
            )
            before_mirror = int(
                (await s.execute(text("SELECT count(*) FROM mirror_region_connections"))).scalar_one()
            )
            stats1 = await mcs.build_macro96_canonical_connections(s, dry_run=True)
            stats2 = await mcs.build_macro96_canonical_connections(s, dry_run=True)
            assert stats1 == stats2  # deterministic prediction
            assert stats1["dry_run"] is True
            assert stats1["total_candidates"] > 0
            assert stats1["unmapped"] == 0
            assert stats1["integrity"] is None
            after_cc = int(
                (await s.execute(text("SELECT count(*) FROM canonical_connections"))).scalar_one()
            )
            after_mirror = int(
                (await s.execute(text("SELECT count(*) FROM mirror_region_connections"))).scalar_one()
            )
            assert after_cc == before_cc  # dry_run writes nothing
            assert after_mirror == before_mirror
    _run(_t())


def test_mirror_rows_untouched_after_writes(db):
    async def _t():
        async with AsyncSessionLocal() as s:
            before = int(
                (await s.execute(text("SELECT count(*) FROM mirror_region_connections"))).scalar_one()
            )
            spot = (
                await s.execute(
                    text(
                        "SELECT id, updated_at FROM mirror_region_connections "
                        "ORDER BY id LIMIT 1"
                    )
                )
            ).first()
            a = await _mk(s, "a")
            b = await _mk(s, "b")
            plan = mcs.plan_macro96_canonicalizations(
                [
                    _row(a.id, b.id, "projection", "directed", 0.5),
                    _row(a.id, b.id, "structural_connection", "directed", 0.7),
                ]
            )
            await mcs.write_canonical_groups(s, plan["groups"])
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
            assert spot_after == spot[1]
    _run(_t())
