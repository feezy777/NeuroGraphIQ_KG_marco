"""Frozen LLM model policy — the single authority for which model is called.

DEEPSEEK MODEL POLICY (frozen):

    Every DeepSeek runtime call in NeuroGraphIQ uses exactly one model:

        deepseek-flash

There is no per-task, per-caller, per-request, environment or settings
override. A caller decides the PROVIDER ("deepseek"); this module decides the
MODEL. That keeps the choice out of ~40 business call sites and gives
provenance a single truthful value.

This module deliberately imports nothing (no httpx, no SQLAlchemy) so that
schemas, models and services can all share the constant without pulling the
provider transport into their import graph.
"""
from __future__ import annotations

DEEPSEEK_PROVIDER = "deepseek"

#: The one allowed DeepSeek model. Do not add alternatives.
DEEPSEEK_MODEL = "deepseek-flash"

#: Retired DeepSeek model names. They must never reach the API again; the
#: provider normalizes anything here (or anything else) to DEEPSEEK_MODEL.
LEGACY_DEEPSEEK_MODELS: tuple[str, ...] = (
    "deepseek-v4-flash",
    "deepseek-v4-pro",
    "deepseek-chat",
    "deepseek-reasoner",
)

#: Providers whose model list is NOT governed by this registry.
OTHER_PROVIDER_MODELS: dict[str, tuple[str, ...]] = {
    "kimi": ("moonshot-v1-auto", "moonshot-v1-8k", "moonshot-v1-32k", "moonshot-v1-128k"),
}


def effective_deepseek_model(requested: str | None) -> str:
    """Return the model DeepSeek will actually be called with.

    Any requested value — legacy, misspelled, empty or None — resolves to
    DEEPSEEK_MODEL. Callers cannot select a different DeepSeek model.
    """
    return DEEPSEEK_MODEL


def is_legacy_deepseek_model(value: str | None) -> bool:
    """True when `value` is a retired DeepSeek model name."""
    return (value or "").strip().lower() in LEGACY_DEEPSEEK_MODELS


def available_models(provider: str) -> list[str]:
    """The model list to expose for a provider (settings UI / API).

    DeepSeek exposes exactly one model. Other providers are untouched.
    """
    key = (provider or "").strip().lower()
    if key == DEEPSEEK_PROVIDER:
        return [DEEPSEEK_MODEL]
    return list(OTHER_PROVIDER_MODELS.get(key, ()))
