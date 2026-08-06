"""In-process ontology vocabulary cache (registry-backed, no silent fallback).

Extraction/completion services must read business enums (category, relation_type,
connection_type, ...) from ``ontology_vocabularies`` through this cache. The cache
is refreshed explicitly at extraction run start and may be seeded in tests. If the
registry is unavailable and the cache is empty, callers get
``OntologyRegistryUnavailableError`` instead of silently falling back to hardcoded
sets (production requirement).
"""

from __future__ import annotations

import threading
import time

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ontology import OntologyVocabulary

TTL_SECONDS = 300

_CACHE: dict[str, tuple[frozenset[str], float]] = {}
_LOCK = threading.Lock()


class OntologyRegistryUnavailableError(RuntimeError):
    """Raised when the vocabulary registry is unavailable and no cache exists."""


def get_vocab_codes(vocab_type: str) -> frozenset[str]:
    """Return active codes for a vocab type from the in-process cache."""
    entry = _CACHE.get(vocab_type)
    if entry is None:
        raise OntologyRegistryUnavailableError(
            f"ontology vocabulary cache is empty for {vocab_type}; "
            "registry refresh is required before extraction"
        )
    codes, _loaded_at = entry
    return codes


def seed_vocab_cache(vocab_type: str, codes: frozenset[str]) -> None:
    """Seed the cache (used by tests / bootstrap; not a production fallback)."""
    with _LOCK:
        _CACHE[vocab_type] = (frozenset(codes), time.time())


def invalidate_vocab_cache() -> None:
    with _LOCK:
        _CACHE.clear()


async def refresh_vocab_cache(
    session: AsyncSession,
    vocab_types: list[str] | None = None,
) -> None:
    """Reload active codes from the registry into the process cache."""
    rows = (
        await session.execute(
            select(OntologyVocabulary.code, OntologyVocabulary.vocab_type).where(
                OntologyVocabulary.status == "active"
            )
        )
    ).all()
    grouped: dict[str, set[str]] = {}
    for code, vocab_type in rows:
        grouped.setdefault(vocab_type, set()).add(code)
    now = time.time()
    with _LOCK:
        for vocab_type, codes in grouped.items():
            _CACHE[vocab_type] = (frozenset(codes), now)
        for vocab_type in vocab_types or []:
            _CACHE.setdefault(vocab_type, (frozenset(), now))
