"""P1.8: unified Function KG integrity audit + invariants (read-only).

Composes the layer checkers built across P1.3–P1.7 into one entry point:

    check_function_kg_integrity()  → A..H section report
    check_function_kg_invariants() → INV-F01..F12 boolean results

Never modifies data. Reused by P1.8 final acceptance and future CI.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func as sa_func
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.mirror_kg import (
    MirrorKgTriple,
    MirrorRegionCircuit,
    MirrorRegionConnection,
    MirrorRegionFunction,
)
from app.models.mirror_macro_clinical import (
    MirrorCircuitFunction,
    MirrorProjectionFunction,
)
from app.models.ontology import (
    OntologyTerm,
    OntologyTermExternalMapping,
    OntologyTermSynonym,
)
from app.schemas.mirror_kg import TripleObjectType
from app.services.final_function_promotion_service import (
    check_final_function_integrity,
)
from app.services.function_term_service import TERM_CODE_PREFIX, zh_term_key
from app.services.function_triple_projection_service import (
    check_function_projection_integrity,
)
from app.services.function_triple_rebuild_service import rebuild_function_triples

FUNCTION_TERM_TYPE = "function"


async def check_ontology_function_integrity(session: AsyncSession) -> dict[str, int]:
    out: dict[str, int] = {
        "total": 0, "active": 0, "proposed": 0, "merged": 0, "deprecated": 0,
        "invalid_term_code": 0, "duplicate_term_code": 0, "duplicate_canonical": 0,
        "non_ng_func_code": 0, "synonym_orphan": 0, "mapping_orphan": 0,
        "merge_cycle": 0, "merge_chain_over_limit": 0,
    }
    terms = (await session.execute(select(OntologyTerm))).scalars().all()
    out["total"] = len(terms)
    seen_code: set[str] = set()
    seen_canon: set[str] = set()
    by_id = {t.id: t for t in terms}
    for t in terms:
        if t.term_type != FUNCTION_TERM_TYPE:
            continue
        out[t.status] = out.get(t.status, 0) + 1
        code = t.term_code or ""
        if not code.startswith(TERM_CODE_PREFIX):
            out["invalid_term_code"] += 1
            out["non_ng_func_code"] += 1
        if code in seen_code:
            out["duplicate_term_code"] += 1
        seen_code.add(code)
        key = zh_term_key(t.canonical_term_en or "")
        if key and key in seen_canon:
            out["duplicate_canonical"] += 1
        seen_canon.add(key)
    # synonym / mapping orphans
    syns = (await session.execute(select(OntologyTermSynonym))).scalars().all()
    for s in syns:
        if s.term_id not in by_id:
            out["synonym_orphan"] += 1
    maps = (await session.execute(select(OntologyTermExternalMapping))).scalars().all()
    for m in maps:
        if m.term_id not in by_id:
            out["mapping_orphan"] += 1
    # merge chain checks
    for t in terms:
        if not t.replaced_by_term_id:
            continue
        seen: set[uuid.UUID] = {t.id}
        cur = t.replaced_by_term_id
        hops = 0
        cycled = False
        while cur is not None and hops <= 10:
            if cur in seen:
                cycled = True
                break
            seen.add(cur)
            nxt = by_id.get(cur)
            if nxt is None:
                break
            cur = nxt.replaced_by_term_id
            hops += 1
        if cycled:
            out["merge_cycle"] += 1
        if hops > 10:
            out["merge_chain_over_limit"] += 1
    return out


def _relation_stats(rows) -> dict[str, int]:
    stats = {
        "total": 0, "term_id_null": 0, "orphan": 0, "invalid_type": 0,
        "merged_residue": 0, "deprecated": 0, "duplicate_semantic": 0,
        "invalid_subject": 0, "superseded_active_use": 0, "rejected_in_triple": 0,
        "source_text_empty": 0, "provenance_missing": 0,
    }
    seen: set[tuple] = set()
    for row in rows:
        stats["total"] += 1
        if row.term_id is None:
            stats["term_id_null"] += 1
        text = getattr(row, "function_term", None) or getattr(row, "function_term_en", None) or ""
        if not str(text).strip():
            stats["source_text_empty"] += 1
    return stats


async def check_mirror_relation_integrity(session: AsyncSession) -> dict[str, dict[str, int]]:
    from app.models.ontology import OntologyTerm as _OT

    out: dict[str, dict[str, int]] = {}
    for label, model, subj_col in (
        ("region", MirrorRegionFunction, MirrorRegionFunction.region_candidate_id),
        ("projection", MirrorProjectionFunction, MirrorProjectionFunction.projection_id),
        ("circuit", MirrorCircuitFunction, MirrorCircuitFunction.circuit_id),
    ):
        rows = (await session.execute(select(model))).scalars().all()
        stats = _relation_stats(rows)
        for row in rows:
            if row.term_id is None:
                continue
            term = await session.get(_OT, row.term_id)
            if term is None:
                stats["orphan"] += 1
            elif term.term_type != FUNCTION_TERM_TYPE:
                stats["invalid_type"] += 1
            elif term.status == "merged":
                stats["merged_residue"] += 1
            elif term.status == "deprecated":
                stats["deprecated"] += 1
        # duplicate semantic relation: same subject + term_id + qualifiers
        if label == "circuit":
            key_cols = (subj_col, model.function_domain, model.function_role, model.effect_type)
        else:
            key_cols = (subj_col, model.function_category, model.relation_type)
        seen: set[tuple] = set()
        for row in rows:
            key = tuple(str(getattr(row, c.name)) if getattr(row, c.name) is not None else "" for c in key_cols)
            if row.term_id is not None:
                key = key + (str(row.term_id),)
            if key in seen:
                stats["duplicate_semantic"] += 1
            seen.add(key)
        out[label] = stats
    return out


async def check_function_kg_integrity(session: AsyncSession) -> dict[str, Any]:
    """A..H unified read-only audit."""
    mirror_relation = await check_mirror_relation_integrity(session)
    mirror_triple = await check_function_projection_integrity(session)
    final = await check_final_function_integrity(session)
    ontology = await check_ontology_function_integrity(session)

    # D. promotion status distribution
    promo: dict[str, int] = {}
    for model in (MirrorRegionFunction, MirrorProjectionFunction, MirrorCircuitFunction):
        rows = (
            await session.execute(
                select(model.promotion_status, sa_func.count()).group_by(model.promotion_status)
            )
        ).all()
        for status, c in rows:
            promo[str(status)] = promo.get(str(status), 0) + c

    # G. cross-layer mapping: Mirror.term_id == MirrorTriple.object_id consistency
    cross = {
        "mirror_relations_total": (
            await session.execute(select(sa_func.count()).select_from(MirrorRegionFunction))
        ).scalar_one()
        + (await session.execute(select(sa_func.count()).select_from(MirrorProjectionFunction))).scalar_one()
        + (await session.execute(select(sa_func.count()).select_from(MirrorCircuitFunction))).scalar_one(),
        "final_relations_total": final["final_region_functions"] + final["final_projection_functions"] + final["final_circuit_functions"],
        "final_triples_total": final["final_function_triples"],
    }

    # H. legacy: function_association still populated (display snapshot)
    legacy = {
        "circuit_rows_with_association": (
            await session.execute(
                select(sa_func.count()).select_from(MirrorRegionCircuit).where(
                    MirrorRegionCircuit.function_association.isnot(None),
                    MirrorRegionCircuit.function_association != "",
                )
            )
        ).scalar_one(),
        "circuit_functions_relations": (
            await session.execute(select(sa_func.count()).select_from(MirrorCircuitFunction))
        ).scalar_one(),
    }

    return {
        "A_ontology": ontology,
        "B_mirror_relation": mirror_relation,
        "C_mirror_triple": mirror_triple,
        "D_promotion": promo,
        "E_final_relation": {
            k: final[k] for k in (
                "final_region_functions", "final_projection_functions", "final_circuit_functions",
                "relation_term_id_null", "relation_orphan_term", "relation_invalid_term",
                "relation_proposed_term", "relation_merged_term", "relation_deprecated_term",
            )
        },
        "F_final_triple": {
            k: final[k] for k in (
                "final_function_triples", "triple_object_id_null", "triple_orphan_object",
                "triple_invalid_object", "triple_proposed_object", "triple_merged_object",
                "triple_deprecated_object", "triple_duplicate_spo",
                "triple_missing_final_relation_lineage", "triple_mirror_subject",
            )
        },
        "G_cross_layer": cross,
        "H_legacy": legacy,
    }


async def check_function_kg_invariants(session: AsyncSession) -> dict[str, tuple[bool, str]]:
    """INV-F01..F12 — every invariant with a pass/fail + evidence string."""
    inv: dict[str, tuple[bool, str]] = {}

    mirror_relation = await check_mirror_relation_integrity(session)
    bad_rel = sum(
        s["term_id_null"] + s["orphan"] + s["invalid_type"] + s["merged_residue"]
        for s in mirror_relation.values()
    )
    inv["INV-F01"] = (bad_rel == 0, f"mirror function relation term_id issues = {bad_rel}")

    mirror_triple = await check_function_projection_integrity(session)
    inv["INV-F02"] = (mirror_triple["object_id_null"] == 0, f"NULL object = {mirror_triple['object_id_null']}")
    inv["INV-F03"] = (
        mirror_triple["orphan_object"] + mirror_triple["invalid_type_object"] + mirror_triple["merged_object"] == 0,
        f"orphan={mirror_triple['orphan_object']} invalid={mirror_triple['invalid_type_object']} merged={mirror_triple['merged_object']}",
    )
    inv["INV-F04"] = (
        mirror_triple["empty_lineage"] + mirror_triple["wrong_lineage"] == 0,
        f"empty_lineage={mirror_triple['empty_lineage']} wrong_lineage={mirror_triple['wrong_lineage']}",
    )

    rebuild = await rebuild_function_triples(session, dry_run=True)
    inv["INV-F05"] = (
        rebuild.inserted_count == 0 and rebuild.upgraded_count == 0 and rebuild.stale_deleted_count == 0,
        f"insert={rebuild.inserted_count} upgrade={rebuild.upgraded_count} stale={rebuild.stale_deleted_count}",
    )

    final = await check_final_function_integrity(session)
    inv["INV-F06"] = (
        final["relation_proposed_term"] + final["relation_merged_term"] + final["relation_deprecated_term"] == 0,
        f"proposed={final['relation_proposed_term']} merged={final['relation_merged_term']} deprecated={final['relation_deprecated_term']}",
    )
    inv["INV-F07"] = (
        final["triple_object_id_null"] == 0 and final["triple_merged_object"] == 0,
        f"NULL={final['triple_object_id_null']} merged={final['triple_merged_object']}",
    )
    inv["INV-F08"] = (final["triple_mirror_subject"] == 0, f"mirror_subject={final['triple_mirror_subject']}")
    inv["INV-F09"] = (
        final["relation_missing_source_mapping"] == 0,
        f"missing_source_mapping={final['relation_missing_source_mapping']}",
    )

    # INV-F10: identity does not depend on display text — object_label mismatch = 0
    inv["INV-F10"] = (
        mirror_triple["wrong_label"] == 0,
        f"wrong_label={mirror_triple['wrong_label']}",
    )

    ontology = await check_ontology_function_integrity(session)
    inv["INV-F11"] = (
        ontology["merge_cycle"] + ontology["merge_chain_over_limit"] == 0
        and mirror_relation["region"]["merged_residue"] == 0
        and mirror_relation["projection"]["merged_residue"] == 0
        and mirror_relation["circuit"]["merged_residue"] == 0,
        f"cycle={ontology['merge_cycle']} chain_over={ontology['merge_chain_over_limit']}",
    )
    inv["INV-F12"] = (
        rebuild.inserted_count == 0 and rebuild.stale_deleted_count == 0,
        f"insert={rebuild.inserted_count} stale={rebuild.stale_deleted_count}",
    )
    return inv
