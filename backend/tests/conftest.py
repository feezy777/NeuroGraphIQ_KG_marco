"""Shared pytest fixtures (test-environment compatibility for the ontology cache)."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.services import llm_function_extraction_service as fes
from app.services import llm_projection_function_extraction_service as pfes
from app.services import mirror_macro_clinical_service as mmcs
from app.services import ontology_vocab_cache as vc


@pytest.fixture(autouse=True)
def _seed_ontology_vocab_cache(monkeypatch):
    """Seed the in-process vocabulary cache from legacy defaults for tests.

    Production extraction paths refresh the cache from the registry at run
    start; this fixture only keeps deterministic unit tests green without a
    database.
    """
    vc.seed_vocab_cache("category", fes.DEFAULT_ALLOWED_FUNCTION_CATEGORIES)
    vc.seed_vocab_cache("relation_type", fes.DEFAULT_ALLOWED_RELATION_TYPES)
    # Unit tests run without a live DB; extraction services refresh the cache
    # from the registry at run start in production.
    monkeypatch.setattr(fes, "refresh_vocab_cache", AsyncMock())
    monkeypatch.setattr(pfes, "refresh_vocab_cache", AsyncMock())
    monkeypatch.setattr(fes, "ground_written_records", AsyncMock())
    monkeypatch.setattr(pfes, "ground_written_records", AsyncMock())
    monkeypatch.setattr(mmcs, "ground_written_records", AsyncMock())
    yield
    vc.invalidate_vocab_cache()
