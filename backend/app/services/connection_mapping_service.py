"""Connection mapping service (CN1.2-2A: frozen mirror → canonical mapping rules).

Pure functions used by the Macro96 batch generation (CN1.2-2B) to convert
mirror_region_connections rows into canonical_connections concepts.
No DB access, no writes to canonical_connections, and mirror_region_connections
is never modified — this module only fixes the mapping rules.

Frozen rules (validated against the real mirror value space on 2026-08-20):
- connection_type: projection/structural_connection → structural;
  functional_connectivity/effective_connectivity → functional;
  coactivation → coactivation; association → association;
  uncertain_connection/unknown → uncertain.
- directionality: directed/source_to_target → directed; bidirectional →
  bidirectional; undirected → undirected; unknown → unspecified.
"""

from __future__ import annotations

import uuid
from typing import Any

_MIRROR_TO_CANONICAL_TYPE: dict[str, str] = {
    "structural_connection": "structural",
    "projection": "structural",
    "functional_connectivity": "functional",
    "effective_connectivity": "functional",
    "coactivation": "coactivation",
    "association": "association",
    "uncertain_connection": "uncertain",
    "unknown": "uncertain",
}

_CANONICAL_TYPES = {"structural", "functional", "projection", "association", "coactivation", "uncertain"}

_DIRECTION_TO_POLICY: dict[str, str] = {
    "directed": "directed",
    "source_to_target": "directed",
    "bidirectional": "bidirectional",
    "undirected": "undirected",
    "unknown": "unspecified",
}

DEFAULT_MAPPING_METHOD = "macro96_canonical_connection_v1"


class ConnectionMappingError(ValueError):
    """Domain error for connection mapping rules."""


def map_connection_type(raw_type: str | None) -> str:
    """Map a mirror connection_type to the canonical enum.

    structural_connection/projection → structural;
    functional_connectivity/effective_connectivity → functional;
    coactivation → coactivation; association → association;
    uncertain_connection/unknown → uncertain.

    ``None``/empty is treated as ``unknown``. Unmapped values raise
    ``ConnectionMappingError`` so the batch fails fast instead of silently
    misclassifying new values.
    """
    if raw_type is None or raw_type == "":
        raw_type = "unknown"
    mapped = _MIRROR_TO_CANONICAL_TYPE.get(raw_type)
    if mapped is None:
        raise ConnectionMappingError(f"unmapped mirror connection_type: {raw_type!r}")
    return mapped


def map_directionality_policy(raw_direction: str | None) -> str:
    """Map a mirror directionality value to the canonical policy.

    directed/source_to_target → directed; bidirectional → bidirectional;
    undirected → undirected; unknown → unspecified.

    ``None``/empty is treated as ``unknown``. Unmapped values raise
    ``ConnectionMappingError`` (fail fast in the batch).
    """
    if raw_direction is None or raw_direction == "":
        raw_direction = "unknown"
    mapped = _DIRECTION_TO_POLICY.get(raw_direction)
    if mapped is None:
        raise ConnectionMappingError(f"unmapped mirror directionality: {raw_direction!r}")
    return mapped


def normalize_macro_connection_key(
    source_canonical_region_id: uuid.UUID | str,
    target_canonical_region_id: uuid.UUID | str,
    connection_type: str,
) -> tuple[str, str, str]:
    """Unique identity for Macro96 batch merging (confidence NOT included).

    Key = ``(source canonical id, target canonical id, connection_type)``
    in the CANONICAL type space — map the mirror value with
    ``map_connection_type`` first (mirror raw values are rejected here, so
    structural_connection/projection collapse into one key space).

    The key is directional: A→B and B→A are different keys and never
    auto-merge. Confidence is deliberately absent — it participates in
    merge selection, never in identity.
    """
    if connection_type not in _CANONICAL_TYPES:
        raise ConnectionMappingError(
            f"normalize_macro_connection_key expects a canonical connection_type, "
            f"got {connection_type!r} (map the mirror value first)"
        )
    return (
        str(source_canonical_region_id),
        str(target_canonical_region_id),
        connection_type,
    )


def build_connection_provenance(
    original_connection_ids: list[uuid.UUID | str],
    original_relation_types: list[str],
    original_confidence: list[float | None],
    mapping_method: str = DEFAULT_MAPPING_METHOD,
    endpoint_grounding: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Provenance block for a canonical connection built from mirror rows.

    Preserves full traceability to the original mirror_region_connections
    rows (which are never modified): their ids, relation types and per-row
    confidence, plus the mapping method used. Lists must be non-empty and
    of equal length; ids are stringified.

    ``endpoint_grounding`` (CI1.3-2) documents WHY the rows were eligible:
    both endpoint candidates carry a canonical_region_id (eligibility is
    endpoint grounding, never the source_atlas label). When provided it is
    written verbatim under the ``endpoint_grounding`` key.
    """
    if not original_connection_ids:
        raise ConnectionMappingError("original_connection_ids must not be empty")
    if not (
        len(original_connection_ids)
        == len(original_relation_types)
        == len(original_confidence)
    ):
        raise ConnectionMappingError(
            "original_connection_ids / original_relation_types / original_confidence "
            "must have the same length"
        )
    provenance = {
        "original_connection_ids": [str(i) for i in original_connection_ids],
        "original_relation_types": list(original_relation_types),
        "original_confidence": list(original_confidence),
        "mapping_method": mapping_method,
    }
    if endpoint_grounding is not None:
        provenance["endpoint_grounding"] = endpoint_grounding
    return provenance
