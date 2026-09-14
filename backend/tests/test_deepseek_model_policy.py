"""DeepSeek model policy — one provider, one model, no override.

The frozen rule: every DeepSeek runtime call uses `deepseek-flash`. A caller
may choose the PROVIDER; it may not choose the MODEL. These tests prove the
provider normalizes, so a stale selector value, an old saved form, an
environment override or a legacy default cannot change what is actually sent.

No network: the HTTP client is replaced by a recorder.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

import pytest

from app.llm_model_policy import (
    DEEPSEEK_MODEL,
    DEEPSEEK_PROVIDER,
    LEGACY_DEEPSEEK_MODELS,
    available_models,
    effective_deepseek_model,
    is_legacy_deepseek_model,
)
from app.services.llm_providers import deepseek as deepseek_mod
from app.services.llm_providers.factory import get_llm_provider

PROVIDER_PATH = Path(deepseek_mod.__file__)
APP_DIR = Path(deepseek_mod.__file__).resolve().parent.parent.parent


# ---------------------------------------------------------------------------
# 1 / 2 — the policy itself
# ---------------------------------------------------------------------------
def test_1_deepseek_default_model_is_deepseek_flash():
    assert DEEPSEEK_MODEL == "deepseek-flash"
    assert DEEPSEEK_MODEL != "deepseek-v4-flash"
    assert effective_deepseek_model(None) == "deepseek-flash"


def test_2_available_model_list_contains_only_deepseek_flash():
    assert available_models(DEEPSEEK_PROVIDER) == ["deepseek-flash"]
    for legacy in LEGACY_DEEPSEEK_MODELS:
        assert legacy not in available_models(DEEPSEEK_PROVIDER)


def test_9_other_providers_are_unaffected():
    """The policy is DeepSeek-only; Kimi keeps its own models."""
    assert available_models("kimi") == [
        "moonshot-v1-auto",
        "moonshot-v1-8k",
        "moonshot-v1-32k",
        "moonshot-v1-128k",
    ]
    assert available_models("openai") == []
    # an unknown provider is not silently given DeepSeek's model
    assert DEEPSEEK_MODEL not in available_models("kimi")


@pytest.mark.parametrize(
    "requested",
    [None, "", "deepseek-flash", *LEGACY_DEEPSEEK_MODELS, "gpt-4o", "deepseek-typo"],
)
def test_3_4_5_every_requested_model_normalizes_to_deepseek_flash(requested):
    assert effective_deepseek_model(requested) == "deepseek-flash"


def test_legacy_names_are_recognized():
    for legacy in LEGACY_DEEPSEEK_MODELS:
        assert is_legacy_deepseek_model(legacy)
    assert not is_legacy_deepseek_model("deepseek-flash")
    assert not is_legacy_deepseek_model(None)


# ---------------------------------------------------------------------------
# 3 / 4 / 5 — the actual API request carries the effective model
# ---------------------------------------------------------------------------
class _Recorder:
    """Captures the JSON body that would be POSTed to DeepSeek."""

    def __init__(self) -> None:
        self.payload: dict[str, Any] | None = None

    async def post(self, _url: str, *, json: dict[str, Any], headers: dict[str, str]) -> Any:
        self.payload = json
        return _Response()


class _Response:
    status_code = 200
    text = json.dumps(
        {
            "choices": [{"message": {"content": "{\"ok\": true}"}}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }
    )

    def json(self) -> dict[str, Any]:
        return json.loads(self.text)


class _Client:
    """Stands in for httpx.AsyncClient (async context manager + post)."""

    def __init__(self, recorder: _Recorder) -> None:
        self._recorder = recorder

    async def __aenter__(self) -> "_Client":
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False

    async def post(self, url: str, *, json: dict[str, Any], headers: dict[str, str]) -> Any:
        return await self._recorder.post(url, json=json, headers=headers)


@pytest.fixture()
def sent(monkeypatch) -> _Recorder:
    recorder = _Recorder()
    monkeypatch.setattr(
        deepseek_mod.httpx, "AsyncClient", lambda **kwargs: _Client(recorder)
    )
    cfg = type(
        "Cfg",
        (),
        {
            "enabled": True,
            "api_key": "test-key-not-a-secret",
            "base_url": "https://api.deepseek.com/v1",
            "default_model": "deepseek-flash",
            "timeout_seconds": 30,
        },
    )()
    monkeypatch.setattr(deepseek_mod, "get_deepseek_runtime_config", lambda: cfg)
    return recorder


@pytest.mark.parametrize("requested", [None, "deepseek-flash", *LEGACY_DEEPSEEK_MODELS])
def test_the_request_body_always_carries_deepseek_flash(sent, requested):
    provider = get_llm_provider("deepseek")
    import asyncio

    asyncio.run(
        provider.complete_json(
            model=requested,
            system_prompt="s",
            user_prompt="u",
        )
    )
    assert sent.payload is not None, "no request was sent"
    assert sent.payload["model"] == "deepseek-flash"


def test_6_provider_response_reports_the_effective_model(sent):
    """Provenance must record what RAN, not what was requested."""
    provider = get_llm_provider("deepseek")
    import asyncio

    response = asyncio.run(
        provider.complete_json(model="deepseek-v4-pro", system_prompt="s", user_prompt="u")
    )
    assert response.model == "deepseek-flash"
    assert response.provider == "deepseek"
    # the redacted request echo agrees with the response metadata
    assert response.request_payload_redacted["model"] == "deepseek-flash"


def test_a_legacy_default_in_config_cannot_leak_through(sent, monkeypatch):
    """Even if config still defaults to a legacy name, the request does not."""
    cfg = type(
        "Cfg",
        (),
        {
            "enabled": True,
            "api_key": "test-key-not-a-secret",
            "base_url": "https://api.deepseek.com/v1",
            "default_model": "deepseek-v4-pro",
            "timeout_seconds": 30,
        },
    )()
    monkeypatch.setattr(deepseek_mod, "get_deepseek_runtime_config", lambda: cfg)
    provider = get_llm_provider("deepseek")
    import asyncio

    asyncio.run(provider.complete_json(model="", system_prompt="s", user_prompt="u"))
    assert sent.payload is not None
    assert sent.payload["model"] == "deepseek-flash"


# ---------------------------------------------------------------------------
# 7 — settings API
# ---------------------------------------------------------------------------
def test_7_settings_api_exposes_only_deepseek_flash():
    from fastapi.testclient import TestClient

    from app.main import app

    body = TestClient(app).get("/api/settings/options").json()
    assert body["default_models"]["deepseek"] == ["deepseek-flash"]
    # the provider itself is still offered
    assert any(p["value"] == "deepseek" for p in body["api_providers"])


def test_7b_runtime_settings_default_model_is_deepseek_flash():
    from app.config import get_settings

    assert get_settings().deepseek_default_model == "deepseek-flash"
    assert get_settings().ontology_residual_model == "deepseek-flash"


# ---------------------------------------------------------------------------
# 15 — no legacy model name survives in production code
# ---------------------------------------------------------------------------
def _code_strings(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    return [
        n.value
        for n in ast.walk(tree)
        if isinstance(n, ast.Constant) and isinstance(n.value, str)
    ]


def test_15_no_legacy_deepseek_model_literal_in_production_code():
    """The only place a retired name may appear is the policy deny-list."""
    offenders: dict[str, list[str]] = {}
    for path in sorted(APP_DIR.rglob("*.py")):
        if "__pycache__" in str(path):
            continue
        try:
            strings = _code_strings(path)
        except SyntaxError:  # pragma: no cover - defensive
            continue
        hits = sorted({s for s in strings if s in LEGACY_DEEPSEEK_MODELS})
        if hits:
            offenders[str(path.relative_to(APP_DIR))] = hits
    assert offenders == {"llm_model_policy.py": sorted(LEGACY_DEEPSEEK_MODELS)}, offenders


def test_no_business_layer_hardcodes_the_model_anymore():
    """Call sites reference the constant, not a string."""
    config = Path("app/config.py")
    assert "deepseek-v4" not in config.read_text(encoding="utf-8")
    assert "DEEPSEEK_MODEL" in config.read_text(encoding="utf-8")


def test_provider_module_declares_the_normalization_point():
    src = PROVIDER_PATH.read_text(encoding="utf-8")
    assert "effective_deepseek_model(" in src
    # normalization happens exactly once, at the single decision site
    assert src.count("use_model = effective_deepseek_model(") == 1


# ===========================================================================
# §8 — Settings normalization (display / persist must agree with runtime)
# ===========================================================================
@pytest.fixture()
def runtime_settings(tmp_path, monkeypatch):
    """Point the runtime settings file at a temp path."""
    from app.services import settings_service

    path = tmp_path / "settings.local.json"
    monkeypatch.setattr(settings_service, "RUNTIME_SETTINGS_PATH", path)
    return settings_service, path


def _seed_stored_model(path, model: str) -> None:
    """Simulate a value persisted before the DeepSeek policy was frozen."""
    path.write_text(
        json.dumps({"api_providers": {"deepseek": {"default_model": model}}}),
        encoding="utf-8",
    )


@pytest.mark.parametrize("stored", LEGACY_DEEPSEEK_MODELS)
def test_8_1_2_settings_read_normalizes_a_legacy_stored_model(runtime_settings, stored):
    """A legacy stored value is never DISPLAYED — 1 and 2 of §8."""
    service, path = runtime_settings
    _seed_stored_model(path, stored)

    public = service.to_public_runtime_settings(service.load_runtime_settings())
    assert public.api_providers.deepseek.default_model == "deepseek-flash"
    # and the raw file is untouched by a read (reads do not rewrite config)
    assert json.loads(path.read_text(encoding="utf-8"))["api_providers"]["deepseek"][
        "default_model"
    ] == stored


def test_8_1b_deepseek_runtime_config_reports_the_effective_model(runtime_settings):
    service, path = runtime_settings
    _seed_stored_model(path, "deepseek-v4-pro")
    assert service.get_deepseek_runtime_config().default_model == "deepseek-flash"


@pytest.mark.parametrize("patched", LEGACY_DEEPSEEK_MODELS)
def test_8_3_settings_patch_persists_only_deepseek_flash(runtime_settings, patched):
    """A legacy PATCH is normalized, not stored — the value is HEALED."""
    service, path = runtime_settings
    public = service.update_runtime_settings(
        {"api_providers": {"deepseek": {"default_model": patched}}}
    )
    assert public.api_providers.deepseek.default_model == "deepseek-flash"
    stored = json.loads(path.read_text(encoding="utf-8"))
    assert stored["api_providers"]["deepseek"]["default_model"] == "deepseek-flash"


def test_8_3b_patch_without_a_model_also_heals_an_already_stale_file(runtime_settings):
    """Any write re-normalizes, so an old file cannot stay stale forever."""
    service, path = runtime_settings
    _seed_stored_model(path, "deepseek-chat")
    public = service.update_runtime_settings({"basic": {"default_page_size": 42}})
    assert public.api_providers.deepseek.default_model == "deepseek-flash"
    stored = json.loads(path.read_text(encoding="utf-8"))
    assert stored["api_providers"]["deepseek"]["default_model"] == "deepseek-flash"


def test_8_4_frontend_receives_only_deepseek_flash(runtime_settings):
    """Both the options endpoint and the runtime-read endpoint agree."""
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    assert client.get("/api/settings/options").json()["default_models"]["deepseek"] == [
        "deepseek-flash"
    ]
    runtime = client.get("/api/settings/runtime").json()
    assert runtime["api_providers"]["deepseek"]["default_model"] == "deepseek-flash"


def test_8_5_provider_still_normalizes_even_if_settings_were_bypassed(sent):
    """Defence in depth: the provider does not trust settings to be clean."""
    provider = get_llm_provider("deepseek")
    import asyncio

    asyncio.run(
        provider.complete_json(
            model="deepseek-v4-flash", system_prompt="s", user_prompt="u"
        )
    )
    assert sent.payload is not None
    assert sent.payload["model"] == "deepseek-flash"


def test_8_6_kimi_settings_are_untouched(runtime_settings):
    service, path = runtime_settings
    public = service.update_runtime_settings(
        {"api_providers": {"kimi": {"default_model": "moonshot-v1-8k"}}}
    )
    assert public.api_providers.kimi.default_model == "moonshot-v1-8k"
    stored = json.loads(path.read_text(encoding="utf-8"))
    assert stored["api_providers"]["kimi"]["default_model"] == "moonshot-v1-8k"
