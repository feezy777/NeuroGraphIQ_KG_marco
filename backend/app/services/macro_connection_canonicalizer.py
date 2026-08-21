"""Macro96 Connection Canonicalizer (CN1.2-2B + CI1.3-2).

Batch conversion of mirror_region_connections rows into canonical_connections
concepts. Eligibility (CI1.3-2) is ENDPOINT GROUNDING ONLY: both endpoint
candidates must already be grounded to canonical_brain_regions (BR2) via
candidate_brain_regions.canonical_region_id. The source_atlas label is never
used as a filter — mislabeled rows (e.g. Allen_HBA_2012 labels whose endpoint
candidates are Macro96 pool rows) are eligible like any other grounded row;
the original label is preserved in provenance and source_summary. Rows with
true ungrounded endpoints (real Allen candidates without canonical regions)
remain ineligible.

Uses the frozen CN1.2-2A mapping rules (connection_mapping_service).

Hard boundaries: never modifies mirror_region_connections, never deletes
original rows, never generates triples, never performs inference. Every
canonical_connections row written here carries full provenance
(mapping_method = macro96_canonical_connection_v1 + endpoint_grounding).

Pipeline: fetch (read-only) -> plan (pure grouping/merging) -> write
(dry_run bypasses write; real mode writes then runs the integrity checker and
commits only if it passes).
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.canonical_connection import CanonicalConnectionCreate
from app.services import canonical_connection_service as ccs
from app.services import connection_mapping_service as cms

_PROVENANCE_KEYS = {
    "original_connection_ids",
    "original_relation_types",
    "original_confidence",
    "mapping_method",
    "endpoint_grounding",
}

_CONNECTION_SPECIES = "human"
_CONNECTION_GRANULARITY = "clinical"


class MacroCanonicalizerError(ValueError):
    """Domain error for Macro96 connection canonicalization."""


# --------------------------------------------------------------------------- #
# Direction merge rules
# --------------------------------------------------------------------------- #


def resolve_directionality_policy(
    directions: list[str],
    *,
    reverse_directions: list[str] | None = None,
) -> str:
    """Resolve the canonical directionality_policy for a merged key group.

    ``directions`` = mapped policies of this group's rows (A→B);
    ``reverse_directions`` = mapped policies of the reverse key group's rows
    (B→A, same connection_type), or None when no reverse group exists.

    Rules (frozen in CN1.2-2B):
    1. any bidirectional row              -> bidirectional
    2. reverse group exists AND both sides are all directed -> bidirectional
       (reciprocated directed evidence = bidirectional, never two mirrored rows)
    3. all directed                       -> directed
    4. all undirected                     -> undirected
    5. all unknown/unspecified            -> unspecified
    6. mixed fallback                     -> most determinate present
       (directed > undirected > unspecified)

    Original mirror directionality values are never overwritten — they are
    preserved in source_summary.original_directions by the plan step.
    """
    if not directions:
        raise MacroCanonicalizerError("directions must not be empty")
    if "bidirectional" in directions:
        return "bidirectional"
    if (
        reverse_directions is not None
        and all(d == "directed" for d in directions)
        and all(d == "directed" for d in reverse_directions)
    ):
        return "bidirectional"
    if all(d == "directed" for d in directions):
        return "directed"
    if all(d == "undirected" for d in directions):
        return "undirected"
    if all(d == "unspecified" for d in directions):
        return "unspecified"
    if "directed" in directions:
        return "directed"
    if "undirected" in directions:
        return "undirected"
    return "unspecified"


# --------------------------------------------------------------------------- #
# Fetch (read-only)
# --------------------------------------------------------------------------- #


async def fetch_grounded_canonicalizable_rows(session: AsyncSession) -> list[dict[str, Any]]:
    """Read mirror connections whose BOTH endpoints are grounded (CI1.3-2).

    Eligibility = endpoint grounding only: both endpoint candidates carry a
    canonical_region_id (BR2 grounding; connection_region_alignment has only
    1 row and is NOT the source). The source_atlas label does NOT participate
    in the filter — it is fetched and preserved verbatim for provenance /
    source_summary (mislabeled rows are eligible; true ungrounded-Allen rows
    fall out through the grounding join). The mirror table itself is never
    touched.
    """
    rows = (
        await session.execute(
            text(
                "SELECT mrc.id AS connection_id, "
                "mrc.source_atlas AS source_atlas, "
                "s.id AS source_candidate_id, "
                "t.id AS target_candidate_id, "
                "s.canonical_region_id AS source_canonical_region_id, "
                "t.canonical_region_id AS target_canonical_region_id, "
                "mrc.connection_type, mrc.directionality, mrc.confidence "
                "FROM mirror_region_connections mrc "
                "JOIN candidate_brain_regions s ON s.id = mrc.source_region_candidate_id "
                "JOIN candidate_brain_regions t ON t.id = mrc.target_region_candidate_id "
                "WHERE s.canonical_region_id IS NOT NULL "
                "AND t.canonical_region_id IS NOT NULL"
            )
        )
    ).mappings().all()
    return [dict(r) for r in rows]


# --------------------------------------------------------------------------- #
# Plan (pure: map -> group -> merge)
# --------------------------------------------------------------------------- #


def plan_macro96_canonicalizations(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Map and group raw mirror rows into canonical connection plans.

    Unmapped rows (unknown connection_type/directionality) and self-loop rows
    (both endpoints resolve to the same canonical concept, e.g. left<->right
    hippocampus) are excluded from groups and reported — never silently
    misclassified.
    """
    mapped_rows: list[dict[str, Any]] = []
    unmapped: list[dict[str, Any]] = []
    self_loops: list[dict[str, Any]] = []
    for r in rows:
        try:
            mapped_type = cms.map_connection_type(r["connection_type"])
            mapped_policy = cms.map_directionality_policy(r["directionality"])
        except cms.ConnectionMappingError as exc:
            unmapped.append({**r, "error": str(exc)})
            continue
        if str(r["source_canonical_region_id"]) == str(r["target_canonical_region_id"]):
            self_loops.append(r)
            continue
        mapped_rows.append(
            {**r, "mapped_type": mapped_type, "mapped_policy": mapped_policy}
        )

    groups: dict[tuple[str, str, str], dict[str, Any]] = {}
    for r in mapped_rows:
        key = cms.normalize_macro_connection_key(
            r["source_canonical_region_id"],
            r["target_canonical_region_id"],
            r["mapped_type"],
        )
        groups.setdefault(
            key,
            {
                "key": key,
                "source_canonical_region_id": r["source_canonical_region_id"],
                "target_canonical_region_id": r["target_canonical_region_id"],
                "connection_type": r["mapped_type"],
                "rows": [],
            },
        )["rows"].append(r)

    reverse_pair_groups = 0
    resolved: list[dict[str, Any]] = []
    for key in sorted(groups):
        g = groups[key]
        src, tgt, ctype = key
        reverse_key = (tgt, src, ctype)
        reverse_directions = (
            [x["mapped_policy"] for x in groups[reverse_key]["rows"]]
            if reverse_key in groups
            else None
        )
        directions = [x["mapped_policy"] for x in g["rows"]]
        policy = resolve_directionality_policy(directions, reverse_directions=reverse_directions)
        if policy == "bidirectional" and all(d == "directed" for d in directions):
            reverse_pair_groups += 1
        confidences = [x["confidence"] for x in g["rows"] if x["confidence"] is not None]
        atlas_labels = sorted({str(x["source_atlas"] or "") for x in g["rows"]})
        resolved.append(
            {
                "key": key,
                "source_canonical_region_id": g["source_canonical_region_id"],
                "target_canonical_region_id": g["target_canonical_region_id"],
                "connection_type": ctype,
                "directionality_policy": policy,
                # raw mapped rows, exposed for the evidence-merge path
                # (CI1.3-2: duplicate-key groups merge into existing rows)
                "rows": g["rows"],
                "confidence": float(max(confidences)) if confidences else None,
                "provenance_json": cms.build_connection_provenance(
                    [x["connection_id"] for x in g["rows"]],
                    [x["connection_type"] for x in g["rows"]],
                    [
                        float(x["confidence"]) if x["confidence"] is not None else None
                        for x in g["rows"]
                    ],
                    mapping_method=cms.DEFAULT_MAPPING_METHOD,
                    endpoint_grounding={
                        "grounding_source": "candidate_brain_regions.canonical_region_id",
                        "source_canonical_region_id": str(
                            g["source_canonical_region_id"]
                        ),
                        "target_canonical_region_id": str(
                            g["target_canonical_region_id"]
                        ),
                        "source_candidate_ids": [
                            str(x["source_candidate_id"]) for x in g["rows"]
                        ],
                        "target_candidate_ids": [
                            str(x["target_candidate_id"]) for x in g["rows"]
                        ],
                        "source_atlas_labels": [
                            str(x["source_atlas"] or "") for x in g["rows"]
                        ],
                    },
                ),
                "source_summary": {
                    # original label preserved verbatim; a list only when a
                    # merged group mixes labels
                    "source_atlas": (
                        atlas_labels[0] if len(atlas_labels) == 1 else atlas_labels
                    ),
                    "merged_rows": len(g["rows"]),
                    "original_directions": [x["directionality"] for x in g["rows"]],
                },
                "row_count": len(g["rows"]),
            }
        )

    duplicate_groups = sum(1 for g in groups.values() if len(g["rows"]) > 1)
    return {
        "stats": {
            "total_candidates": len(rows),
            "mapped": len(mapped_rows),
            "unmapped": len(unmapped),
            "self_loop_rows": len(self_loops),
            "distinct_keys": len(groups),
            "duplicate_groups": duplicate_groups,
            "reverse_pair_groups": reverse_pair_groups,
        },
        "groups": resolved,
        "unmapped_rows": unmapped,
        "self_loop_rows": self_loops,
    }


def _raise_on_unmapped(unmapped_rows: list[dict[str, Any]]) -> None:
    if not unmapped_rows:
        return
    sample = "; ".join(
        f"{r['connection_id']}: type={r['connection_type']!r} dir={r['directionality']!r}"
        for r in unmapped_rows[:5]
    )
    raise MacroCanonicalizerError(
        f"{len(unmapped_rows)} unmapped mirror rows — extend the frozen mapping rules "
        f"before writing anything. Sample: {sample}"
    )


# --------------------------------------------------------------------------- #
# Write
# --------------------------------------------------------------------------- #


async def _merge_evidence_into_existing(
    session: AsyncSession,
    existing: Any,
    group: dict[str, Any],
) -> bool:
    """Merge mirror rows missing from an existing canonical row's provenance
    (CI1.3-2).

    A mirror row whose identity key ``(source, target, type)`` already exists
    cannot create a second canonical row (UNIQUE identity) — instead its
    evidence is merged into the existing row's provenance, mirroring the
    write-time dedup merge principle: original_connection_ids / relation
    types / confidence lists are extended, confidence takes the max, the
    original source_atlas labels are preserved, and the endpoint grounding
    basis of the merged rows is recorded under ``endpoint_grounding``.

    Idempotent: ids already covered by the existing provenance are never
    appended twice. Returns True when at least one row was merged. Never
    touches mirror_region_connections.
    """
    prov = dict(existing.provenance_json or {})
    covered = {str(i) for i in prov.get("original_connection_ids", [])}
    new_rows = [r for r in group["rows"] if str(r["connection_id"]) not in covered]
    if not new_rows:
        return False

    prov["original_connection_ids"] = [
        *prov.get("original_connection_ids", []),
        *[str(r["connection_id"]) for r in new_rows],
    ]
    prov["original_relation_types"] = [
        *prov.get("original_relation_types", []),
        *[r["connection_type"] for r in new_rows],
    ]
    prov["original_confidence"] = [
        *prov.get("original_confidence", []),
        *[
            float(r["confidence"]) if r["confidence"] is not None else None
            for r in new_rows
        ],
    ]
    new_grounding = {
        "grounding_source": "candidate_brain_regions.canonical_region_id",
        "source_canonical_region_id": str(group["source_canonical_region_id"]),
        "target_canonical_region_id": str(group["target_canonical_region_id"]),
        "source_candidate_ids": [
            str(r["source_candidate_id"]) for r in new_rows
        ],
        "target_candidate_ids": [
            str(r["target_candidate_id"]) for r in new_rows
        ],
        "source_atlas_labels": [str(r["source_atlas"] or "") for r in new_rows],
        "merged_existing_provenance": True,
    }
    prior_grounding = prov.get("endpoint_grounding")
    if prior_grounding is None:
        prov["endpoint_grounding"] = new_grounding
    else:
        merged_grounding = dict(prior_grounding)
        for k in ("source_candidate_ids", "target_candidate_ids", "source_atlas_labels"):
            merged_grounding[k] = [
                *prior_grounding.get(k, []),
                *new_grounding[k],
            ]
        merged_grounding["merged_existing_provenance"] = True
        prov["endpoint_grounding"] = merged_grounding

    new_conf = [float(r["confidence"]) for r in new_rows if r["confidence"] is not None]
    if new_conf and (existing.confidence is None or max(new_conf) > float(existing.confidence)):
        existing.confidence = max(new_conf)

    ss = dict(existing.source_summary or {})
    ss["merged_rows"] = int(ss.get("merged_rows", 0)) + len(new_rows)
    labels = sorted(
        {str(ss.get("source_atlas", "") or ""), *[str(r["source_atlas"] or "") for r in new_rows]}
    )
    ss["source_atlas"] = labels[0] if len(labels) == 1 else labels
    ss["original_directions"] = [
        *ss.get("original_directions", []),
        *[r["directionality"] for r in new_rows],
    ]
    existing.source_summary = ss
    existing.provenance_json = prov
    return True


async def write_canonical_groups(
    session: AsyncSession, groups: list[dict[str, Any]]
) -> dict[str, int]:
    """Create canonical connections for planned groups; merge duplicate
    evidence into existing rows (idempotent).

    A group whose identity key already exists is not simply skipped (CI1.3-2):
    when it carries mirror ids missing from the existing row's provenance,
    that evidence is merged in (``enriched``). Only when nothing new remains
    is the group counted as ``skipped_existing``. Every written row's
    provenance is verified to carry the frozen provenance keys.
    """
    created = 0
    enriched = 0
    skipped_existing = 0
    for g in groups:
        dup = await ccs.check_duplicate(
            session,
            g["source_canonical_region_id"],
            g["target_canonical_region_id"],
            g["connection_type"],
        )
        if dup is not None:
            if await _merge_evidence_into_existing(session, dup, g):
                enriched += 1
            else:
                skipped_existing += 1
            continue
        conn = await ccs.create_canonical_connection(
            session,
            CanonicalConnectionCreate(
                source_region_id=g["source_canonical_region_id"],
                target_region_id=g["target_canonical_region_id"],
                connection_type=g["connection_type"],
                directionality_policy=g["directionality_policy"],
                species=_CONNECTION_SPECIES,
                granularity_level=_CONNECTION_GRANULARITY,
                status="proposed",
                confidence=g["confidence"],
                provenance_json=g["provenance_json"],
                source_summary=g["source_summary"],
            ),
        )
        missing = _PROVENANCE_KEYS - set(conn.provenance_json)
        if missing:
            raise MacroCanonicalizerError(
                f"provenance incomplete on {conn.connection_code}: missing {sorted(missing)}"
            )
        created += 1
    return {"created": created, "enriched": enriched, "skipped_existing": skipped_existing}


async def _count_existing(groups: list[dict[str, Any]], existing_keys: set[str]) -> tuple[int, int]:
    existing = 0
    new = 0
    for g in groups:
        key = f"{g['source_canonical_region_id']}|{g['target_canonical_region_id']}|{g['connection_type']}"
        if key in existing_keys:
            existing += 1
        else:
            new += 1
    return existing, new


async def _load_existing_keys(session: AsyncSession) -> set[str]:
    rows = (
        await session.execute(
            text(
                "SELECT source_region_id::text || '|' || target_region_id::text || '|' || "
                "connection_type FROM canonical_connections"
            )
        )
    ).scalars().all()
    return set(rows)


async def _load_covered_mirror_ids(session: AsyncSession) -> set[str]:
    """All mirror_region_connections ids already referenced by canonical
    connection provenance (read-only)."""
    rows = (
        await session.execute(
            text(
                "SELECT jsonb_array_elements_text(provenance_json->'original_connection_ids') "
                "FROM canonical_connections "
                "WHERE provenance_json->'original_connection_ids' IS NOT NULL"
            )
        )
    ).scalars().all()
    return set(rows)


# --------------------------------------------------------------------------- #
# Build (fetch -> plan -> optional write)
# --------------------------------------------------------------------------- #


async def forecast_circuit_closure(
    session: AsyncSession, new_mirror_ids: list[str]
) -> dict[str, Any]:
    """Read-only forecast of the circuit-layer impact of canonicalizing
    ``new_mirror_ids`` (CI1.3-2).

    Counts projection memberships that would newly resolve and macro circuits
    whose projection closure would complete (all projections resolved after
    the hypothetical write, at least one unresolved before). Writes nothing;
    circuit data is never modified.
    """
    empty = {
        "newly_resolvable_projection_memberships": 0,
        "newly_closable_circuit_count": 0,
        "newly_closable_circuits": [],
        "fully_aligned_among_closable": 0,
    }
    if not new_mirror_ids:
        return empty

    memberships = int(
        (
            await session.execute(
                text(
                    "SELECT count(*) FROM mirror_circuit_projection_memberships mcp "
                    "WHERE mcp.projection_id::text = ANY(:ids) "
                    "AND NOT EXISTS (SELECT 1 FROM canonical_connections cc "
                    "WHERE cc.provenance_json->'original_connection_ids' "
                    "@> to_jsonb(mcp.projection_id::text))"
                ),
                {"ids": new_mirror_ids},
            )
        ).scalar_one()
    )

    rows = (
        await session.execute(
            text(
                "SELECT c.id, c.circuit_name, "
                "(SELECT count(*) FROM mirror_circuit_projection_memberships mcp "
                " WHERE mcp.circuit_id = c.id) AS total_proj, "
                "(SELECT count(*) FROM mirror_circuit_projection_memberships mcp "
                " WHERE mcp.circuit_id = c.id AND EXISTS ("
                "  SELECT 1 FROM canonical_connections cc "
                "  WHERE cc.provenance_json->'original_connection_ids' "
                "  @> to_jsonb(mcp.projection_id::text))) AS resolved_before, "
                "(SELECT count(*) FROM mirror_circuit_projection_memberships mcp "
                " WHERE mcp.circuit_id = c.id AND mcp.projection_id::text = ANY(:ids) "
                " AND NOT EXISTS (SELECT 1 FROM canonical_connections cc "
                " WHERE cc.provenance_json->'original_connection_ids' "
                " @> to_jsonb(mcp.projection_id::text))) AS new_resolved, "
                "(SELECT count(*) FROM mirror_circuit_regions mcr "
                " WHERE mcr.circuit_id = c.id AND mcr.role = 'unknown') "
                " AS unknown_role_members, "
                "(SELECT count(*) FROM mirror_circuit_regions mcr "
                " LEFT JOIN candidate_brain_regions cand ON cand.id = mcr.region_candidate_id "
                " WHERE mcr.circuit_id = c.id AND cand.canonical_region_id IS NULL) "
                " AS ungrounded_members "
                "FROM mirror_region_circuits c "
                "WHERE c.granularity_level = 'macro'"
            ),
            {"ids": new_mirror_ids},
        )
    ).mappings().all()

    closable: list[dict[str, Any]] = []
    for r in rows:
        was_open = int(r["resolved_before"]) < int(r["total_proj"])
        closed = int(r["resolved_before"]) + int(r["new_resolved"]) == int(r["total_proj"])
        if was_open and closed:
            region_ok = int(r["unknown_role_members"]) == 0 and int(r["ungrounded_members"]) == 0
            closable.append({"name": r["circuit_name"], "region_ok": region_ok})
    closable.sort(key=lambda x: (x["name"] or ""))
    return {
        "newly_resolvable_projection_memberships": memberships,
        "newly_closable_circuit_count": len(closable),
        "newly_closable_circuits": [c["name"] for c in closable],
        "fully_aligned_among_closable": sum(1 for c in closable if c["region_ok"]),
    }


async def build_macro96_canonical_connections(
    session: AsyncSession, *, dry_run: bool = False
) -> dict[str, Any]:
    """Run the Macro96 canonicalization batch.

    dry_run=True predicts everything without writing (deterministic stats).
    Real mode refuses to write if ANY row is unmapped, writes planned groups
    (skipping existing keys), then runs the canonical connection integrity
    checker inside the transaction — committing only when it passes.

    Stats include eligibility scope (CI1.3-2): total mirror rows, rows
    excluded because their endpoints are not both grounded (with the
    Allen-labeled subset broken out), and a read-only forecast of the
    circuit-layer closure impact of the rows this batch would create.
    """
    rows = await fetch_grounded_canonicalizable_rows(session)
    plan = plan_macro96_canonicalizations(rows)
    if not dry_run:
        _raise_on_unmapped(plan["unmapped_rows"])
    existing_keys = await _load_existing_keys(session)
    existing, new = await _count_existing(plan["groups"], existing_keys)

    mirror_total = int(
        (await session.execute(text("SELECT count(*) FROM mirror_region_connections"))).scalar_one()
    )
    ineligible = int(
        (
            await session.execute(
                text(
                    "SELECT count(*) FROM mirror_region_connections mrc "
                    "LEFT JOIN candidate_brain_regions s ON s.id = mrc.source_region_candidate_id "
                    "LEFT JOIN candidate_brain_regions t ON t.id = mrc.target_region_candidate_id "
                    "WHERE s.canonical_region_id IS NULL OR t.canonical_region_id IS NULL"
                )
            )
        ).scalar_one()
    )
    ineligible_allen = int(
        (
            await session.execute(
                text(
                    "SELECT count(*) FROM mirror_region_connections mrc "
                    "LEFT JOIN candidate_brain_regions s ON s.id = mrc.source_region_candidate_id "
                    "LEFT JOIN candidate_brain_regions t ON t.id = mrc.target_region_candidate_id "
                    "WHERE (s.canonical_region_id IS NULL OR t.canonical_region_id IS NULL) "
                    "AND mrc.source_atlas = 'Allen_HBA_2012'"
                )
            )
        ).scalar_one()
    )

    # CI1.3-2: mirror ids this batch would cover (create OR evidence-merge).
    # ``covered_mirror_ids`` spans every mapped group — the closure forecast
    # assumes all of them end up in canonical provenance; ``new_evidence`` is
    # the subset not yet covered by existing provenance.
    covered_mirror_ids = sorted(
        {
            mid
            for g in plan["groups"]
            for mid in g["provenance_json"]["original_connection_ids"]
        }
    )
    covered_existing = await _load_covered_mirror_ids(session)
    new_evidence = sorted(set(covered_mirror_ids) - covered_existing)

    stats: dict[str, Any] = {
        **plan["stats"],
        "dry_run": dry_run,
        "mirror_total_rows": mirror_total,
        "ineligible_ungrounded_rows": ineligible,
        "ineligible_ungrounded_allen_rows": ineligible_allen,
        "new_evidence_mirror_ids": new_evidence,
        "new_evidence_count": len(new_evidence),
        "existing_count": existing,
        "new_canonical_count": new,
        "enriched_count": 0,
        "forecast": await forecast_circuit_closure(session, covered_mirror_ids),
        "integrity": None,
    }
    if dry_run:
        return stats

    write_result = await write_canonical_groups(session, plan["groups"])
    stats["existing_count"] = write_result["skipped_existing"]
    stats["enriched_count"] = write_result["enriched"]
    stats["new_canonical_count"] = write_result["created"]
    integrity = await ccs.check_canonical_connection_integrity(session)
    stats["integrity"] = integrity
    if not integrity["ok"]:
        await session.rollback()
        raise MacroCanonicalizerError(
            "canonical connection integrity check failed — batch rolled back: "
            + "; ".join(f"{i['code']}: {i['message']}" for i in integrity["issues"])
        )
    await session.commit()
    return stats
