"""Gate7B-native deterministic BrainRegion resolver (Phase 1 core).

Resolves a query string or an explicit identifier against the frozen 770 canonical
BrainRegions (G1_MACRO / G3_MESO_FINE / G4_MICROSTRUCTURAL_FINE) using ONLY the
Gate7B CURRENT tables:

    kg_entities, brain_regions, entity_aliases, entity_xrefs,
    external_regions, region_mappings, atlases, sources

Deterministic, fail-safe contract (no guesses, no fuzzy matching):

  * Only ACTIVE + APPROVED + species 9606 ``entity_type='brain_region'`` rows are
    valid resolution targets (never proposed / pending / deprecated / merged).
  * Identifier resolution (xref, atlas RegionMapping) requires an explicit
    namespace — a bare "1" / "17" is never auto-treated as an external id.
  * Free-text resolution runs a strict priority ladder and stops at the first
    priority that yields any candidate; 0 -> next priority, 1 -> RESOLVED,
    >1 -> AMBIGUOUS (never ``LIMIT 1``, never order-and-take-first).
  * Alias types ``narrow`` / ``broad`` / ``related`` and non-exact xref/mapping
    types never auto-resolve (semantic hints only).
  * Safe normalization is pure formatting (NFKC + trim + whitespace collapse +
    casefold); it never strips hemisphere / parentheses content / digits / codes.

This is a standalone sync service (psycopg3). It does NOT reuse the legacy
resolver stack (canonical_region_resolver / canonical_region_service /
ontology_query_service), which is bound to tables absent from production.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, asdict
from typing import Any

import psycopg

# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #

# Match types (resolver output vocabulary).
MATCH_EXACT_CANONICAL_NAME = "EXACT_CANONICAL_NAME"
MATCH_EXACT_SOURCE_NAME = "EXACT_SOURCE_NAME"
MATCH_EXACT_ALIAS = "EXACT_ALIAS"
MATCH_EXACT_XREF = "EXACT_XREF"
MATCH_ATLAS_REGION_MAPPING = "ATLAS_REGION_MAPPING"
MATCH_NORMALIZED_LEXICAL = "NORMALIZED_LEXICAL_MATCH"
MATCH_NONE = "NONE"

# Resolver status (the only three legal values).
STATUS_RESOLVED = "RESOLVED"
STATUS_AMBIGUOUS = "AMBIGUOUS"
STATUS_UNRESOLVED = "UNRESOLVED"

# Alias types eligible for deterministic exact resolution.
ALLOWED_ALIAS_TYPES = ("exact", "abbreviation", "historical", "atlas_label", "previous_name")
# Alias types that must NEVER auto-resolve (semantic hints only).
SEMANTIC_HINT_ALIAS_TYPES = ("narrow", "broad", "related")

# Legal hemisphere / granularity filter values (pass-through; not validated hard).
HEMISPHERE_VALUES = ("left", "right", "bilateral", "midline")
GRANULARITY_VALUES = (
    "G1_MACRO", "G2_MESO_ANATOMICAL", "G3_MESO_FINE", "G4_MICROSTRUCTURAL_FINE",
)

_SPECIES_HUMAN = "9606"

_BASE_REGION_SELECT = (
    "SELECT ke.entity_pk, ke.entity_id, ke.name_en, ke.name_zh,"
    " ke.source_name_original, br.granularity_level, br.hemisphere, br.species_taxon_id"
    " FROM kg_entities ke JOIN brain_regions br ON br.entity_pk = ke.entity_pk"
    " WHERE ke.entity_type='brain_region' AND ke.record_status='active'"
    " AND ke.review_status='approved' AND br.species_taxon_id='9606'"
)

_REGION_COLS = (
    "entity_pk", "entity_id", "name_en", "name_zh", "source_name_original",
    "granularity_level", "hemisphere", "species_taxon_id",
)


# --------------------------------------------------------------------------- #
# Request / response contracts
# --------------------------------------------------------------------------- #

@dataclass
class BrainRegionResolveRequest:
    """Resolver input. identifier fields and free-text are two distinct paths.

    A bare ``query_text`` (e.g. "1") is never treated as an external id; xref
    resolution only fires when ``source_database`` AND ``external_id`` are both set.
    """
    query_text: str | None = None
    language: str | None = None              # 'en' | 'zh' | None
    hemisphere: str | None = None            # left | right | bilateral | midline
    granularity_level: str | None = None     # G1_MACRO | G3_MESO_FINE | G4_MICROSTRUCTURAL_FINE
    source_database: str | None = None       # xref namespace (e.g. 'Brainnetome')
    external_id: str | None = None           # xref identifier
    atlas_family: str | None = None          # e.g. 'Julich-Brain'
    atlas_version: str | None = None         # e.g. '3.1.0'
    source_region_id: str | None = None      # external atlas parcel id


@dataclass
class ResolverCandidate:
    entity_id: str | None
    entity_pk: int | None
    name_en: str | None
    name_zh: str | None
    source_name_original: str | None
    granularity_level: str | None
    hemisphere: str | None
    species_taxon_id: str | None
    match_type: str
    matched_value: str | None
    match_provenance: str | None
    alias_type: str | None = None
    source_database: str | None = None
    external_id: str | None = None
    atlas_family: str | None = None
    mapping_type: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class BrainRegionResolveResult:
    status: str
    match_type: str
    query: dict[str, Any]
    candidate_count: int
    candidates: list[ResolverCandidate]

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "match_type": self.match_type,
            "query": self.query,
            "candidate_count": self.candidate_count,
            "candidates": [c.to_dict() for c in self.candidates],
        }


# --------------------------------------------------------------------------- #
# Safe normalization (format-only; never destructive)
# --------------------------------------------------------------------------- #

def safe_normalize(text: str | None) -> str:
    """NFKC + trim + whitespace collapse + casefold.

    Does NOT strip hemisphere, parentheses content, digits, area codes, or
    anatomical descriptors; does not stem/token-subset/fuzzy match.
    """
    if text is None:
        return ""
    s = unicodedata.normalize("NFKC", text)
    s = s.strip()
    s = re.sub(r"\s+", " ", s)
    s = s.casefold()
    return s


# --------------------------------------------------------------------------- #
# Candidate construction + decision
# --------------------------------------------------------------------------- #

def _make_candidate(region: dict[str, Any], match_type: str, matched_value: str | None,
                    provenance: str | None, **extra: Any) -> ResolverCandidate:
    return ResolverCandidate(
        entity_id=region.get("entity_id"),
        entity_pk=region.get("entity_pk"),
        name_en=region.get("name_en"),
        name_zh=region.get("name_zh"),
        source_name_original=region.get("source_name_original"),
        granularity_level=region.get("granularity_level"),
        hemisphere=region.get("hemisphere"),
        species_taxon_id=region.get("species_taxon_id"),
        match_type=match_type,
        matched_value=matched_value,
        match_provenance=provenance,
        **extra,
    )


def _result_from_candidates(request: BrainRegionResolveRequest,
                            candidates: list[ResolverCandidate],
                            match_type: str) -> BrainRegionResolveResult:
    n = len(candidates)
    if n == 0:
        return BrainRegionResolveResult(
            status=STATUS_UNRESOLVED, match_type=MATCH_NONE,
            query=asdict(request), candidate_count=0, candidates=[])
    if n == 1:
        return BrainRegionResolveResult(
            status=STATUS_RESOLVED, match_type=match_type,
            query=asdict(request), candidate_count=1, candidates=candidates)
    return BrainRegionResolveResult(
        status=STATUS_AMBIGUOUS, match_type=match_type,
        query=asdict(request), candidate_count=n, candidates=candidates)


# --------------------------------------------------------------------------- #
# Data fetchers (Gate7B tables, filtered to valid targets)
# --------------------------------------------------------------------------- #

def _fetch_regions(cur: psycopg.Cursor, hemisphere: str | None,
                   granularity_level: str | None) -> list[dict[str, Any]]:
    sql = _BASE_REGION_SELECT
    params: list[str] = []
    if hemisphere:
        sql += " AND br.hemisphere = %s"
        params.append(hemisphere)
    if granularity_level:
        sql += " AND br.granularity_level = %s"
        params.append(granularity_level)
    cur.execute(sql, tuple(params))
    return [dict(zip(_REGION_COLS, row)) for row in cur.fetchall()]


def _fetch_allowed_aliases(cur: psycopg.Cursor) -> list[dict[str, Any]]:
    cur.execute(
        "SELECT a.alias_text, a.alias_type, a.entity_pk"
        " FROM entity_aliases a"
        " JOIN kg_entities ke ON ke.entity_pk = a.entity_pk"
        " JOIN brain_regions br ON br.entity_pk = ke.entity_pk"
        " WHERE a.alias_type = ANY(%s)"
        " AND ke.entity_type='brain_region' AND ke.record_status='active'"
        " AND ke.review_status='approved' AND br.species_taxon_id='9606'",
        (list(ALLOWED_ALIAS_TYPES),))
    cols = ("alias_text", "alias_type", "entity_pk")
    return [dict(zip(cols, row)) for row in cur.fetchall()]


# --------------------------------------------------------------------------- #
# Identifier resolution paths
# --------------------------------------------------------------------------- #

def _resolve_xref(cur: psycopg.Cursor, request: BrainRegionResolveRequest) -> BrainRegionResolveResult:
    """source_database + external_id -> entity_xrefs (exact only)."""
    sql = (
        "SELECT ke.entity_pk, ke.entity_id, ke.name_en, ke.name_zh, ke.source_name_original,"
        " br.granularity_level, br.hemisphere, br.species_taxon_id,"
        " x.source_database, x.external_id"
        " FROM entity_xrefs x"
        " JOIN kg_entities ke ON ke.entity_pk = x.entity_pk"
        " JOIN brain_regions br ON br.entity_pk = ke.entity_pk"
        " WHERE x.source_database = %s AND x.external_id = %s AND x.match_type = 'exact'"
        " AND ke.entity_type='brain_region' AND ke.record_status='active'"
        " AND ke.review_status='approved' AND br.species_taxon_id='9606'"
    )
    params: list[str] = [request.source_database or "", request.external_id or ""]
    if request.hemisphere:
        sql += " AND br.hemisphere = %s"
        params.append(request.hemisphere)
    if request.granularity_level:
        sql += " AND br.granularity_level = %s"
        params.append(request.granularity_level)
    cur.execute(sql, tuple(params))
    rows = cur.fetchall()
    candidates = []
    for r in rows:
        region = dict(zip((*_REGION_COLS, "source_database", "external_id"), r))
        candidates.append(_make_candidate(
            region, MATCH_EXACT_XREF, request.external_id, "entity_xrefs",
            source_database=region["source_database"], external_id=region["external_id"]))
    return _result_from_candidates(request, candidates, MATCH_EXACT_XREF)


def _resolve_atlas_mapping(cur: psycopg.Cursor,
                           request: BrainRegionResolveRequest) -> BrainRegionResolveResult:
    """atlas_family/version + source_region_id -> ExternalRegion -> exact RegionMapping."""
    sql = (
        "SELECT ke.entity_pk, ke.entity_id, ke.name_en, ke.name_zh, ke.source_name_original,"
        " br.granularity_level, br.hemisphere, br.species_taxon_id,"
        " x.source_region_id, a.atlas_family, rm.mapping_type"
        " FROM region_mappings rm"
        " JOIN external_regions x ON x.entity_pk = rm.external_region_pk"
        " JOIN atlases a ON a.entity_pk = x.atlas_pk"
        " JOIN kg_entities km ON km.entity_pk = rm.entity_pk"
        " JOIN kg_entities ke ON ke.entity_pk = rm.brain_region_pk"
        " JOIN brain_regions br ON br.entity_pk = rm.brain_region_pk"
        " WHERE x.source_region_id = %s AND rm.mapping_type = 'exact'"
        " AND km.record_status='active' AND km.review_status='approved'"
        " AND ke.entity_type='brain_region' AND ke.record_status='active'"
        " AND ke.review_status='approved' AND br.species_taxon_id='9606'"
    )
    params: list[str] = [request.source_region_id or ""]
    if request.atlas_family:
        sql += " AND a.atlas_family = %s"
        params.append(request.atlas_family)
    if request.atlas_version:
        sql += " AND a.atlas_version = %s"
        params.append(request.atlas_version)
    if request.hemisphere:
        sql += " AND br.hemisphere = %s"
        params.append(request.hemisphere)
    if request.granularity_level:
        sql += " AND br.granularity_level = %s"
        params.append(request.granularity_level)
    cur.execute(sql, tuple(params))
    rows = cur.fetchall()
    candidates = []
    for r in rows:
        region = dict(zip((*_REGION_COLS, "source_region_id", "atlas_family", "mapping_type"), r))
        candidates.append(_make_candidate(
            region, MATCH_ATLAS_REGION_MAPPING, request.source_region_id,
            "region_mappings+external_regions",
            atlas_family=region["atlas_family"], mapping_type=region["mapping_type"]))
    return _result_from_candidates(request, candidates, MATCH_ATLAS_REGION_MAPPING)


# --------------------------------------------------------------------------- #
# Free-text resolution
# --------------------------------------------------------------------------- #

def _match_canonical_name(regions: list[dict[str, Any]], q: str,
                          language: str | None) -> list[ResolverCandidate]:
    out: list[ResolverCandidate] = []
    for r in regions:
        prov: str | None = None
        if language == "en":
            if r["name_en"] == q:
                prov = "kg_entities.name_en"
        elif language == "zh":
            if r["name_zh"] == q:
                prov = "kg_entities.name_zh"
        else:
            if r["name_en"] == q:
                prov = "kg_entities.name_en"
            elif r["name_zh"] == q:
                prov = "kg_entities.name_zh"
        if prov:
            out.append(_make_candidate(r, MATCH_EXACT_CANONICAL_NAME, q, prov))
    return out


def _match_source_name(regions: list[dict[str, Any]], q: str) -> list[ResolverCandidate]:
    return [
        _make_candidate(r, MATCH_EXACT_SOURCE_NAME, q, "kg_entities.source_name_original")
        for r in regions if r["source_name_original"] == q
    ]


def _match_alias(regions_by_pk: dict[int, dict[str, Any]],
                 aliases: list[dict[str, Any]], q: str) -> list[ResolverCandidate]:
    out: list[ResolverCandidate] = []
    for a in aliases:
        if a["alias_text"] != q:
            continue
        region = regions_by_pk.get(a["entity_pk"])
        if region is None:
            continue
        out.append(_make_candidate(region, MATCH_EXACT_ALIAS, q, "entity_aliases.alias_text",
                                   alias_type=a["alias_type"]))
    return out


def _match_normalized(regions: list[dict[str, Any]], q: str,
                      language: str | None) -> list[ResolverCandidate]:
    nq = safe_normalize(q)
    out: list[ResolverCandidate] = []
    for r in regions:
        prov: str | None = None
        if language != "zh" and r["name_en"] and safe_normalize(r["name_en"]) == nq:
            prov = "kg_entities.name_en (normalized)"
        elif language != "en" and r["name_zh"] and safe_normalize(r["name_zh"]) == nq:
            prov = "kg_entities.name_zh (normalized)"
        if prov:
            out.append(_make_candidate(r, MATCH_NORMALIZED_LEXICAL, q, prov))
    return out


def _resolve_free_text(cur: psycopg.Cursor,
                       request: BrainRegionResolveRequest) -> BrainRegionResolveResult:
    q = request.query_text or ""
    regions = _fetch_regions(cur, request.hemisphere, request.granularity_level)
    regions_by_pk = {r["entity_pk"]: r for r in regions}
    aliases = _fetch_allowed_aliases(cur)

    # Priority ladder: canonical name -> source name -> alias -> normalized lexical.
    # Stop at the first priority that yields any candidate (0 -> next, 1 -> RESOLVED,
    # >1 -> AMBIGUOUS). Ambiguity is never bypassed by a later priority.
    priority_calls = [
        (MATCH_EXACT_CANONICAL_NAME, lambda: _match_canonical_name(regions, q, request.language)),
        (MATCH_EXACT_SOURCE_NAME, lambda: _match_source_name(regions, q)),
        (MATCH_EXACT_ALIAS, lambda: _match_alias(regions_by_pk, aliases, q)),
        (MATCH_NORMALIZED_LEXICAL, lambda: _match_normalized(regions, q, request.language)),
    ]
    for match_type, fn in priority_calls:
        candidates = fn()
        if candidates:
            return _result_from_candidates(request, candidates, match_type)
    return _result_from_candidates(request, [], MATCH_NONE)


# --------------------------------------------------------------------------- #
# Public entry point
# --------------------------------------------------------------------------- #

def resolve_brain_region(conn: psycopg.Connection,
                         request: BrainRegionResolveRequest) -> BrainRegionResolveResult:
    """Resolve a query/identifier against the frozen Gate7B canonical registry.

    Identifier paths take precedence (they are explicit): xref when
    ``source_database`` + ``external_id`` are set, then atlas RegionMapping when
    ``source_region_id`` (+ ``atlas_family``/``atlas_version``) is set. Otherwise
    ``query_text`` goes through the free-text priority ladder.
    """
    cur = conn.cursor()
    try:
        if request.source_database and request.external_id:
            return _resolve_xref(cur, request)
        if request.source_region_id and (request.atlas_family or request.atlas_version):
            return _resolve_atlas_mapping(cur, request)
        if request.query_text:
            return _resolve_free_text(cur, request)
        return _result_from_candidates(request, [], MATCH_NONE)
    finally:
        cur.close()
