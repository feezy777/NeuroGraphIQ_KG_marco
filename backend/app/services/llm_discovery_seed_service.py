"""Phase 3B — deterministic BrainRegion seed -> LlmDiscoveryInput.

Read-only. Every field of the discovery input is taken from the Gate7B
authority (``neurographiq_human_brain_v1``) or left absent:

    name_en / name_zh / granularity_level / hemisphere / species_taxon_id /
    source_atlas_names  <- the existing Phase 1 seed read, reused rather than
                           re-implemented, so atlas provenance has ONE query
    parent_region_name   <- brain_regions.parent_region_pk, a DERIVED cache
                           (the canonical statement lives in
                           brain_region_hierarchy_relations). It is read, never
                           inferred: when the column is NULL the field is NULL.
    known_aliases        <- entity_aliases, ordered deterministically

What this module must never do (phase brief §5): guess an alias, infer a parent
by name similarity, back-fill from the legacy Mirror/candidate tables, or send
anything the seed does not actually declare. A missing optional field is a
``None``/``[]``, because an absent fact is information the model is allowed to
lack — an invented one is a defect the model cannot detect.
"""
from __future__ import annotations

from typing import Any, Mapping

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.llm_discovery import LlmDiscoveryInput
from app.services.knowledge_production_brain_region_service import get_seed_region

#: Bounds the alias block in the prompt. Preferred aliases sort first, so a
#: truncation drops the least-important ones rather than an arbitrary slice.
_MAX_ALIASES = 12

_CONTEXT_SQL = text(
    """
    SELECT b.hierarchy_depth, parent_e.name_en AS parent_name_en
    FROM brain_regions b
    JOIN kg_entities e ON e.entity_pk = b.entity_pk
    LEFT JOIN brain_regions parent_b ON parent_b.entity_pk = b.parent_region_pk
    LEFT JOIN kg_entities parent_e ON parent_e.entity_pk = parent_b.entity_pk
    WHERE e.entity_id = :entity_id
    """
)

# An alias equal to a name already present in the seed block is dropped: it
# would repeat a declared value without adding one. That is de-duplication,
# not inference.
_ALIAS_SQL = text(
    """
    SELECT a.alias_text
    FROM entity_aliases a
    JOIN kg_entities e ON e.entity_pk = a.entity_pk
    WHERE e.entity_id = :entity_id
      AND a.alias_text IS NOT NULL
      AND btrim(a.alias_text) <> ''
      AND btrim(a.alias_text) IS DISTINCT FROM btrim(COALESCE(e.name_en, ''))
      AND btrim(a.alias_text) IS DISTINCT FROM btrim(COALESCE(e.name_zh, ''))
    ORDER BY a.is_preferred DESC, a.alias_pk
    LIMIT :limit
    """
)


def build_hierarchy_context(row: Mapping[str, Any]) -> str | None:
    """Render declared hierarchy facts. Pure function (unit-testable).

    Only fields that are actually present are rendered — the context string is
    a faithful restatement of stored values, never an inference about them.
    """
    parts = [f"granularity_level={row['granularity_level']}"] if row["granularity_level"] else []
    if row["hemisphere"]:
        parts.append(f"hemisphere={row['hemisphere']}")
    if row["hierarchy_depth"] is not None:
        parts.append(f"hierarchy_depth={row['hierarchy_depth']}")
    return "; ".join(parts) or None


async def build_discovery_input(
    session: AsyncSession, entity_id: str
) -> LlmDiscoveryInput | None:
    """Load one BrainRegion seed. ``None`` when the BrainRegion does not exist.

    SELECT only. Deterministic: the same seed always produces the same input.
    """
    detail = await get_seed_region(session, entity_id)
    if detail is None:
        return None

    context = (
        await session.execute(_CONTEXT_SQL, {"entity_id": entity_id})
    ).mappings().one_or_none()
    aliases = (
        await session.execute(
            _ALIAS_SQL, {"entity_id": entity_id, "limit": _MAX_ALIASES}
        )
    ).scalars().all()

    # LlmDiscoveryInput itself rejects a seed with no usable name; that
    # ValidationError is the honest signal that this region cannot seed a
    # discovery, and it is raised before any run is created.
    return LlmDiscoveryInput(
        seed_entity_id=detail.entity_id,
        seed_name_en=detail.name_en,
        seed_name_zh=detail.name_zh,
        seed_granularity_level=detail.granularity_level,
        seed_hemisphere=detail.hemisphere,
        species_taxon_id=detail.species_taxon_id,
        source_atlas_names=list(detail.atlas_names or []),
        parent_region_name=(context or {}).get("parent_name_en"),
        hierarchy_context=build_hierarchy_context(
            {
                "granularity_level": detail.granularity_level,
                "hemisphere": detail.hemisphere,
                "hierarchy_depth": (context or {}).get("hierarchy_depth"),
            }
        ),
        known_aliases=[a for a in aliases if a],
    )
