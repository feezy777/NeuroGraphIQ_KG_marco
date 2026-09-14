"""Phase 3B.5 — DeepSeek Responses API + JSON Schema (feasibility layer).

No network: the HTTP client is replaced by a recorder, so what is asserted is
the payload that would actually leave the process.

This is an EXPERIMENTAL path. Nothing in production calls it, and the suite
also pins the legacy Chat Completions behaviour so adding it cannot have
changed anything that already worked.
"""
from __future__ import annotations

import ast
import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from app.llm_model_policy import LEGACY_DEEPSEEK_MODELS
from app.schemas.llm_discovery import LlmDiscoveryResponse
from app.services.llm_providers import deepseek as ds
from app.services.llm_providers.factory import get_llm_provider

PROVIDER_PATH = Path(ds.__file__)
CANDIDATE_DEFS = ("RegionCandidate", "ConnectionCandidate", "FunctionCandidate", "CircuitCandidate")
MINIMAL_SCHEMA = {
    "type": "object",
    "properties": {"ok": {"type": "boolean"}},
    "required": ["ok"],
    "additionalProperties": False,
}


# ---------------------------------------------------------------------------
# HTTP boundary recorder
# ---------------------------------------------------------------------------
class _Recorder:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.response_body: dict[str, Any] = {}
        self.status_code = 200

    async def post(self, url: str, *, json: dict[str, Any], headers: dict[str, str]) -> Any:
        self.calls.append({"url": url, "body": json, "headers": sorted(headers)})
        return _Response(self.status_code, self.response_body)


class _Response:
    def __init__(self, status_code: int, body: dict[str, Any]) -> None:
        self.status_code = status_code
        self._body = body
        self.text = json.dumps(body)

    def json(self) -> dict[str, Any]:
        return self._body


class _Client:
    def __init__(self, recorder: _Recorder) -> None:
        self._recorder = recorder

    async def __aenter__(self) -> "_Client":
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False

    async def post(self, url: str, *, json: dict[str, Any], headers: dict[str, str]) -> Any:
        return await self._recorder.post(url, json=json, headers=headers)


@pytest.fixture()
def recorder(monkeypatch) -> _Recorder:
    rec = _Recorder()
    rec.response_body = {
        "model": "deepseek-flash",
        "status": "completed",
        "output": [
            {"type": "reasoning", "summary": []},
            {"type": "message", "content": [{"type": "output_text", "text": '{"ok": true}'}]},
        ],
        "usage": {
            "input_tokens": 11,
            "output_tokens": 22,
            "total_tokens": 33,
            "output_tokens_details": {"reasoning_tokens": 7},
        },
    }
    monkeypatch.setattr(ds.httpx, "AsyncClient", lambda **kw: _Client(rec))
    monkeypatch.setattr(
        ds,
        "get_deepseek_runtime_config",
        lambda: type(
            "Cfg",
            (),
            {
                "enabled": True,
                "api_key": "test-key-not-a-secret",
                "base_url": "https://api.deepseek.com/v1",
                "default_model": "deepseek-flash",
                "timeout_seconds": 300,
            },
        )(),
    )
    return rec


def _call(schema: dict[str, Any] | None = None, **over: Any):
    kwargs: dict[str, Any] = {
        "model": "deepseek-flash",
        "system_prompt": "S",
        "user_prompt": "U",
        "json_schema": schema if schema is not None else MINIMAL_SCHEMA,
        "schema_name": ds.RESPONSES_SCHEMA_NAME,
        "reasoning_effort": "high",
        "max_output_tokens": 65536,
        "timeout_seconds": 300,
    }
    kwargs.update(over)
    return asyncio.run(get_llm_provider("deepseek").complete_structured_response(**kwargs))


# ===========================================================================
# §5 / §28.1 — the frozen model policy is not bypassed
# ===========================================================================
def test_1_the_request_uses_the_frozen_model(recorder):
    _call()
    assert recorder.calls[0]["body"]["model"] == "deepseek-flash"


def test_15_no_call_can_fall_back_to_another_deepseek_model(recorder):
    """A caller asking for a retired name still gets the policy model."""
    for legacy in LEGACY_DEEPSEEK_MODELS:
        _call(model=legacy)
    for call in recorder.calls:
        assert call["body"]["model"] == "deepseek-flash", call["body"]["model"]
    blob = json.dumps([c["body"] for c in recorder.calls])
    for legacy in LEGACY_DEEPSEEK_MODELS:
        assert legacy not in blob


# ===========================================================================
# §4 / §8 — endpoint and request shape
# ===========================================================================
def test_2_the_request_goes_to_the_responses_endpoint(recorder):
    _call()
    assert recorder.calls[0]["url"].endswith("/responses")
    assert recorder.calls[0]["url"] == "https://api.deepseek.com/v1/responses"


def test_3_the_text_format_asks_for_json_schema(recorder):
    _call()
    fmt = recorder.calls[0]["body"]["text"]["format"]
    assert fmt["type"] == "json_schema"
    assert fmt["strict"] is True


def test_4_the_schema_name_is_stable_and_distinct_from_the_other_versions(recorder):
    _call()
    fmt = recorder.calls[0]["body"]["text"]["format"]
    assert fmt["name"] == "neurographiq_llm_discovery_v1"
    assert fmt["name"] == ds.RESPONSES_SCHEMA_NAME
    # three version-ish names, three different jobs — must not be conflated
    from app.prompts.llm_discovery_prompt import PROMPT_VERSION
    from app.schemas.llm_discovery import SCHEMA_VERSION

    assert fmt["name"] != SCHEMA_VERSION
    assert fmt["name"] != PROMPT_VERSION


def test_8b_reasoning_and_budget_use_responses_field_names(recorder):
    """Chat Completions names would be silently ignored here."""
    _call()
    body = recorder.calls[0]["body"]
    assert body["reasoning"] == {"effort": "high"}
    assert body["max_output_tokens"] == 65536
    assert "max_tokens" not in body
    assert "thinking" not in body
    assert "response_format" not in body
    # instructions/input, not messages
    assert body["instructions"] == "S"
    assert body["input"] == "U"
    assert "messages" not in body


def test_headers_carry_no_secret_names_beyond_authorization(recorder):
    _call()
    assert recorder.calls[0]["headers"] == ["Authorization", "Content-Type"]


# ===========================================================================
# §6 / §13 — the schema authority is the typed contract
# ===========================================================================
def test_5_the_schema_is_generated_from_the_typed_contract(recorder):
    module_source = PROVIDER_PATH.read_text(encoding="utf-8")
    # no hand-written discovery schema anywhere in the provider
    assert '"local_id"' not in module_source
    assert '"species_context"' not in module_source
    assert "'local_id'" not in module_source
    generated = LlmDiscoveryResponse.model_json_schema()
    _call(schema=generated)
    sent = recorder.calls[0]["body"]["text"]["format"]["schema"]
    assert sent == generated
    assert sent["title"] == "LlmDiscoveryResponse"
    assert set(sent["$defs"]) >= set(CANDIDATE_DEFS)


def test_6_confidence_is_required_in_every_candidate_definition():
    schema = LlmDiscoveryResponse.model_json_schema()
    for name in CANDIDATE_DEFS:
        assert "confidence" in schema["$defs"][name]["required"], name


def test_7_confidence_bounds_survive_the_projection():
    schema = LlmDiscoveryResponse.model_json_schema()
    for name in CANDIDATE_DEFS:
        conf = schema["$defs"][name]["properties"]["confidence"]
        assert conf["minimum"] == 0.0 and conf["maximum"] == 1.0, name
        assert conf["type"] == "number", name


def test_9_species_context_is_required_where_the_contract_requires_it():
    schema = LlmDiscoveryResponse.model_json_schema()
    for name in ("ConnectionCandidate", "FunctionCandidate", "CircuitCandidate"):
        assert "species_context" in schema["$defs"][name]["required"], name
    assert "$ref" in schema["$defs"]["ConnectionCandidate"]["properties"]["species_context"]
    assert "SpeciesContext" in schema["$defs"]


def test_10_extra_fields_are_forbidden_everywhere():
    schema = LlmDiscoveryResponse.model_json_schema()
    assert schema["additionalProperties"] is False
    for name, definition in schema["$defs"].items():
        assert definition["additionalProperties"] is False, name


def test_8_local_id_pattern_cannot_be_projected_and_that_is_a_known_gap():
    """KNOWN PROJECTION GAP — reported, not papered over.

    `local_id` is validated by a `@field_validator`, and Pydantic cannot express
    a validator as JSON Schema. Provider-side enforcement therefore does NOT
    cover local-ID naming (Phase 3B.4 fixed that in the PROMPT). The Phase 3A
    parser stays the only gate for it.

    If `local_id` ever gains a real `pattern`, this test must change on purpose.
    """
    schema = LlmDiscoveryResponse.model_json_schema()
    for name in CANDIDATE_DEFS:
        assert "pattern" not in schema["$defs"][name]["properties"]["local_id"], name


def test_8c_the_same_gap_applies_to_the_species_representation_validator():
    """`_representation_sanity` is also a model_validator: not expressible."""
    schema = LlmDiscoveryResponse.model_json_schema()
    species = schema["$defs"]["SpeciesContext"]
    assert "required" not in species or species.get("required") is None
    assert "allOf" not in species and "anyOf" not in species


# ===========================================================================
# §19 — reasoning is never the answer
# ===========================================================================
def test_11_reasoning_items_are_never_returned_as_text(recorder):
    _, diagnostics = ds.extract_responses_output(recorder.response_body)
    assert diagnostics["item_types"] == ["reasoning", "message"]
    assert diagnostics["content_types"] == ["output_text"]
    response = _call()
    assert response.raw_text == '{"ok": true}'


def test_11b_a_reasoning_only_response_yields_no_text(recorder):
    text, diagnostics = ds.extract_responses_output(
        {"output": [{"type": "reasoning", "summary": ["thinking..."]}]}
    )
    assert text == ""
    assert diagnostics["item_types"] == ["reasoning"]


def test_11c_reasoning_tokens_are_recorded_as_a_count_only(recorder):
    response = _call()
    assert response.usage.reasoning_tokens == 7
    assert "thinking..." not in json.dumps(response.response_payload)


# ===========================================================================
# §25 / §28.12 — legacy Chat Completions is untouched
# ===========================================================================
def test_12a_the_chat_completions_path_still_uses_response_format(recorder):
    recorder.response_body = {
        "choices": [{"message": {"content": '{"ok": true}'}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3},
    }
    response = asyncio.run(
        get_llm_provider("deepseek").complete_json(
            model="deepseek-flash", system_prompt="s", user_prompt="u"
        )
    )
    body = recorder.calls[0]["body"]
    assert recorder.calls[0]["url"].endswith("/chat/completions")
    assert body["response_format"] == {"type": "json_object"}
    assert "text" not in body and "instructions" not in body and "input" not in body
    # `thinking` is only sent when a caller asks for it
    assert "thinking" not in body
    assert response.raw_text == '{"ok": true}'


def test_12b_adding_the_responses_path_did_not_change_the_chat_signature(recorder):
    """The experimental method is additive; existing callers are untouched."""
    tree = ast.parse(PROVIDER_PATH.read_text(encoding="utf-8-sig"))
    provider = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef) and node.name == "DeepSeekProvider"
    )
    methods = {
        n.name: n for n in provider.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert "complete_structured_response" in methods
    for existing in ("complete_text", "complete_json", "_complete_chat"):
        assert existing in methods, existing
    # complete_json still declares response_format on the wire, never json_schema
    assert "response_schema" in ast.unparse(methods["complete_json"])


def test_12c_no_production_module_calls_the_experimental_path():
    """A feasibility method must not have been wired into execution."""
    app_dir = PROVIDER_PATH.resolve().parents[2]
    offenders = []
    for path in app_dir.rglob("*.py"):
        if path.name == "deepseek.py" or "__pycache__" in str(path):
            continue
        if "complete_structured_response" in path.read_text(encoding="utf-8"):
            offenders.append(path.name)
    assert offenders == [], offenders


# ===========================================================================
# §28.13 / §28.14 — no persistence, no database
# ===========================================================================
def test_13_the_experimental_path_persists_nothing():
    source = PROVIDER_PATH.read_text(encoding="utf-8")
    for forbidden in ("INSERT INTO", "UPDATE ", "DELETE FROM", "commit(", "session"):
        assert forbidden not in source, forbidden


def test_14_the_suite_needs_no_database():
    """Everything here runs on a stub session: there is no DB fixture at all."""
    import inspect
    import sys

    module = sys.modules[__name__]
    for name, obj in vars(module).items():
        if inspect.isfunction(obj) and name.startswith("test_"):
            params = inspect.signature(obj).parameters
            assert not any(p in params for p in ("db", "session", "client")), name
