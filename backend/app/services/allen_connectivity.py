"""Allen Mouse Brain Connectivity API client with caching and retry.

Provides async methods to query Allen Brain Map REST API for:
- Structure metadata (id, name, acronym, structure_id_path)
- Injection experiments via ProjectionStructureUnionize
- Projection signal for target structures

Key insight: ProjectionStructureUnionize has structure_id (where injection was made
when is_injection=true) and section_data_set_id (experiment). To trace connectivity
from A->B, find all SectionDataSets where A was injected, then find projection
entries where target structure_id = B (or descendants).

All results are cached in module-level dicts for the session lifetime.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

ALLEN_API_BASE = "https://api.brain-map.org/api/v2/data"

REQUEST_TIMEOUT = 30.0
RETRY_DELAYS = (1.0, 2.0, 4.0)
MAX_RETRIES = 3

_log = logging.getLogger(__name__)

# ---- Module-level caches (session-lifetime, single-run PoC) ----

_structure_cache: dict[int, dict[str, Any]] = {}
# Cache: structure_id -> set of section_data_set_ids that injected this structure
_injection_sds_cache: dict[int, set[int]] = {}
# Cache: (target_structure_id, frozenset_of_sds_ids) -> projection entries
# We use structure_id as key + store per-SDS projection data
_projection_by_sds_cache: dict[int, list[dict[str, Any]]] = {}
# Cache: structure_id -> projection entries where target matches
_target_projection_cache: dict[tuple[int, int], list[dict[str, Any]]] = {}

# Stats
_api_requests: int = 0
_cache_hits: int = 0


def reset_stats() -> None:
    """Reset API request and cache hit counters."""
    global _api_requests, _cache_hits
    _api_requests = 0
    _cache_hits = 0


def get_stats() -> dict[str, int]:
    """Return current API stats."""
    return {"api_requests": _api_requests, "cache_hits": _cache_hits}


async def _get_json(
    client: httpx.AsyncClient, url: str, params: dict[str, Any]
) -> dict[str, Any]:
    """GET JSON with retry on 429/5xx."""
    global _api_requests
    last_exc: Exception | None = None
    for attempt in range(MAX_RETRIES):
        try:
            _api_requests += 1
            resp = await client.get(url, params=params)
            if resp.status_code in (429, 500, 502, 503, 504) and attempt < MAX_RETRIES - 1:
                delay = RETRY_DELAYS[min(attempt, len(RETRY_DELAYS) - 1)]
                _log.warning("Allen API %s returned %d, retrying in %.1fs (attempt %d/%d)",
                             url, resp.status_code, delay, attempt + 1, MAX_RETRIES)
                await asyncio.sleep(delay)
                continue
            resp.raise_for_status()
            return resp.json()
        except (httpx.HTTPStatusError, httpx.TransportError) as exc:
            last_exc = exc
            if attempt < MAX_RETRIES - 1:
                delay = RETRY_DELAYS[min(attempt, len(RETRY_DELAYS) - 1)]
                _log.warning("Allen API request failed: %s, retrying in %.1fs", exc, delay)
                await asyncio.sleep(delay)
    raise last_exc or RuntimeError("Allen API request failed after retries")


async def get_structures(
    client: httpx.AsyncClient, allen_ids: list[int]
) -> dict[int, dict[str, Any]]:
    """Batch query Structure metadata for a list of allen_ids.

    Returns dict mapping allen_id -> {id, name, acronym, structure_id_path, ...}
    Uncached ids are fetched from API; cached ones are returned immediately.
    """
    global _cache_hits
    missing = [aid for aid in allen_ids if aid not in _structure_cache]
    if not missing:
        _cache_hits += len(allen_ids)
        return {aid: _structure_cache[aid] for aid in allen_ids}

    hits = len(allen_ids) - len(missing)
    _cache_hits += hits

    batch_size = 50
    for i in range(0, len(missing), batch_size):
        batch = missing[i:i + batch_size]
        id_list = ",".join(str(aid) for aid in batch)
        params = {
            "criteria": (
                f"model::Structure,"
                f"rma::criteria,[id$in{id_list}]"
            ),
        }
        url = f"{ALLEN_API_BASE}/query.json"
        data = await _get_json(client, url, params)
        if data.get("success") and "msg" in data:
            for item in data["msg"]:
                sid = item.get("id")
                if sid is not None:
                    _structure_cache[sid] = item

    return {aid: _structure_cache.get(aid, {}) for aid in allen_ids}


async def _get_injection_sds_for_structure(
    client: httpx.AsyncClient, structure_id: int
) -> set[int]:
    """Get SectionDataSet IDs where the given structure was injected.

    Queries ProjectionStructureUnionize with is_injection=true.
    """
    global _cache_hits
    if structure_id in _injection_sds_cache:
        _cache_hits += 1
        return _injection_sds_cache[structure_id]

    criteria = (
        f"model::ProjectionStructureUnionize,"
        f"rma::criteria,[structure_id$eq{structure_id}],"
        f"[is_injection$eqtrue]"
    )
    params = {"criteria": criteria}
    url = f"{ALLEN_API_BASE}/query.json"
    data = await _get_json(client, url, params)

    sds_ids: set[int] = set()
    if data.get("success") and "msg" in data:
        for item in data["msg"]:
            sds_id = item.get("section_data_set_id")
            if sds_id is not None:
                sds_ids.add(int(sds_id))

    _injection_sds_cache[structure_id] = sds_ids
    return sds_ids


async def find_injection_experiments(
    client: httpx.AsyncClient,
    source_allen_id: int,
) -> tuple[set[int], str, int | None]:
    """Find SectionDataSet IDs where the source structure (or ancestor) was injected.

    Walks up structure hierarchy if no exact match is found.

    Returns (section_data_set_ids, match_type, matched_structure_id)
    where match_type is one of:
      - 'exact_primary': injection found at exact structure_id
      - 'ancestor_N_levels_up': ancestor N levels up the hierarchy
      - 'no_match': no injection experiments found at any level
    """
    # Try exact match
    sds_ids = await _get_injection_sds_for_structure(client, source_allen_id)
    if sds_ids:
        return sds_ids, "exact_primary", source_allen_id

    # Walk up hierarchy
    structures = await get_structures(client, [source_allen_id])
    struct = structures.get(source_allen_id, {})
    path = struct.get("structure_id_path", "")

    if not path:
        return set(), "no_match", None

    path_ids = [int(x) for x in str(path).split("/") if x]
    # Reverse to walk from nearest ancestor to root
    ancestors = list(reversed(path_ids))

    for level, ancestor_id in enumerate(ancestors):
        if ancestor_id == source_allen_id:
            continue
        ancestor_sds = await _get_injection_sds_for_structure(client, ancestor_id)
        if ancestor_sds:
            return ancestor_sds, f"ancestor_{level}_levels_up", ancestor_id

    return set(), "no_match", None


async def get_projections_to_target(
    client: httpx.AsyncClient,
    sds_ids: set[int],
    target_structure_id: int,
) -> list[dict[str, Any]]:
    """Get projection entries for target structure from given experiments.

    Returns list of ProjectionStructureUnionize entries where
    structure_id == target_structure_id (or descendant) and is_injection=false.
    """
    global _cache_hits
    cache_key = (target_structure_id, frozenset(sds_ids))
    if cache_key in _target_projection_cache:
        _cache_hits += 1
        return _target_projection_cache[cache_key]

    if not sds_ids:
        return []

    results: list[dict[str, Any]] = []

    # Query in batches
    sds_list = list(sds_ids)
    batch_size = 50
    for i in range(0, len(sds_list), batch_size):
        batch = sds_list[i:i + batch_size]
        id_list = ",".join(str(eid) for eid in batch)
        criteria = (
            f"model::ProjectionStructureUnionize,"
            f"rma::criteria,[section_data_set_id$in{id_list}],"
            f"[structure_id$eq{target_structure_id}],"
            f"[is_injection$eqfalse]"
        )
        params = {"criteria": criteria}
        url = f"{ALLEN_API_BASE}/query.json"
        data = await _get_json(client, url, params)
        if data.get("success") and "msg" in data:
            results.extend(data["msg"])

    _target_projection_cache[cache_key] = results
    return results


async def get_all_projections_for_experiments(
    client: httpx.AsyncClient,
    sds_ids: set[int],
) -> list[dict[str, Any]]:
    """Get ALL projection entries (non-injection) for given experiments.

    Useful for checking all projection targets (for "not_observed" classification).
    Returns combined list of ProjectionStructureUnionize entries.
    """
    global _cache_hits

    if not sds_ids:
        return []

    # Use cache: fetch missing experiments
    missing = [eid for eid in sds_ids if eid not in _projection_by_sds_cache]
    hits = len(sds_ids) - len(missing)
    _cache_hits += hits

    # Fetch missing in batches
    batch_size = 50
    for i in range(0, len(missing), batch_size):
        batch = missing[i:i + batch_size]
        id_list = ",".join(str(eid) for eid in batch)
        criteria = (
            f"model::ProjectionStructureUnionize,"
            f"rma::criteria,[section_data_set_id$in{id_list}],"
            f"[is_injection$eqfalse]"
        )
        params = {"criteria": criteria}
        url = f"{ALLEN_API_BASE}/query.json"
        data = await _get_json(client, url, params)
        if data.get("success") and "msg" in data:
            for item in data["msg"]:
                eid = item.get("section_data_set_id")
                if eid is not None:
                    eid_int = int(eid)
                    _projection_by_sds_cache.setdefault(eid_int, []).append(item)

    results: list[dict[str, Any]] = []
    for eid in sds_ids:
        results.extend(_projection_by_sds_cache.get(eid, []))
    return results


async def build_http_client() -> httpx.AsyncClient:
    """Build a configured httpx AsyncClient for Allen API."""
    return httpx.AsyncClient(timeout=REQUEST_TIMEOUT, trust_env=False)
