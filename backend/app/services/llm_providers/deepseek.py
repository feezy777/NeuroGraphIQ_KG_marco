"""DeepSeek LLM provider (OpenAI-compatible chat completions)."""

from __future__ import annotations

import json
import logging
import time
from typing import Any

import httpx

from app.services.llm_json_utils import raw_response_preview
from app.services.llm_providers.base import (
    LlmProviderResponse,
    LlmProviderTextResult,
    LlmProviderUsage,
    ProviderNotConfiguredError,
)
from app.llm_model_policy import effective_deepseek_model
from app.services.settings_service import get_deepseek_runtime_config

logger = logging.getLogger(__name__)


#: Minimum timeout for the one allowed model. A single value is correct now
#: that the model cannot vary; see app.llm_model_policy.
_MODEL_MIN_TIMEOUT = 120


def supports_json_object_mode() -> bool:
    """DeepSeek chat completions support OpenAI-style JSON object mode."""
    return True


def _resolve_model(requested_model: str | None, config_default: str | None) -> str:
    """THE single model decision site for every DeepSeek request.

    Model authority is global and frozen: whatever a caller, the config or a
    fallback asked for, DeepSeek is called with the one allowed model. Keeping
    that in ONE function makes it a fact rather than a convention — and it is
    why adding the Responses path could not introduce a second policy.
    """
    requested = requested_model or config_default
    use_model = effective_deepseek_model(requested)
    if (requested or "") != use_model:
        logger.info(
            "[deepseek] model normalized requested_model=%s effective_model=%s",
            requested,
            use_model,
        )
    return use_model


def _try_parse_json(raw: str) -> dict[str, Any] | None:
    from app.services.llm_json_utils import parse_llm_json_response

    try:
        return parse_llm_json_response(raw)
    except (json.JSONDecodeError, ValueError):
        return None


#: Provider-side schema identifier for the Responses API structured-output
#: format. Three different version-ish names exist and must not be conflated:
#:   schema_version 1.0            -> the SCIENTIFIC contract
#:   PROMPT_VERSION  1.2.0         -> the prompt TEXT
#:   this name                     -> which schema the provider enforces
RESPONSES_SCHEMA_NAME = "neurographiq_llm_discovery_v1"


def extract_responses_output(body: Any) -> tuple[str, dict[str, Any]]:
    """Final assistant text from a Responses-API payload.

    Only ``message`` items carry the answer. ``reasoning`` items are the
    model's deliberation and are NEVER read as text — the same boundary as
    ``reasoning_content`` on the chat path. Returns ``(text, diagnostics)``.
    """
    diagnostics: dict[str, Any] = {"item_types": [], "content_types": []}
    if not isinstance(body, dict):
        return "", diagnostics

    output = body.get("output")
    if not isinstance(output, list):
        # some deployments return a bare string field; accept it only when it
        # is unambiguous, and record that the rich shape was absent
        for key in ("output_text", "text"):
            value = body.get(key)
            if isinstance(value, str) and value.strip():
                diagnostics["shape"] = f"flat:{key}"
                return value, diagnostics
        diagnostics["shape"] = "unknown"
        return "", diagnostics

    chunks: list[str] = []
    for item in output:
        if not isinstance(item, dict):
            continue
        item_type = item.get("type")
        diagnostics["item_types"].append(item_type)
        if item_type != "message":
            continue  # reasoning / tool items are not the answer
        content = item.get("content")
        if not isinstance(content, list):
            continue
        for part in content:
            if not isinstance(part, dict):
                continue
            diagnostics["content_types"].append(part.get("type"))
            if part.get("type") == "output_text" and isinstance(part.get("text"), str):
                chunks.append(part["text"])
    diagnostics["shape"] = "responses"
    return "".join(chunks), diagnostics


def extract_raw_text_from_response(body: Any, *, http_text: str = "") -> tuple[str, bool]:
    """Extract assistant text from DeepSeek/OpenAI-style chat completion payloads.

    ``message.content`` is the ONLY authoritative final answer. Some DeepSeek
    models also return ``message.reasoning_content`` (the model's private
    chain of thought); that is reasoning METADATA, never the answer, and it is
    deliberately NOT promoted to content here. Returning it would feed
    unstructured deliberation into a structured parser and let it be mistaken
    for a result. If content is empty, the caller sees an empty response and
    reports a failure instead.
    """
    fallback_used = False
    if isinstance(body, dict):
        choices = body.get("choices")
        if isinstance(choices, list) and choices:
            first = choices[0] or {}
            if isinstance(first, dict):
                message = first.get("message")
                if isinstance(message, dict):
                    content = message.get("content")
                    if isinstance(content, str) and content.strip():
                        return content, False
                    # reasoning_content is intentionally ignored (see docstring)
                delta = first.get("delta")
                if isinstance(delta, dict):
                    content = delta.get("content")
                    if isinstance(content, str) and content.strip():
                        return content, False
        message = body.get("message")
        if isinstance(message, dict):
            content = message.get("content")
            if isinstance(content, str) and content.strip():
                return content, False
        for key in ("content", "text"):
            val = body.get(key)
            if isinstance(val, str) and val.strip():
                return val, False
    if http_text.strip():
        return http_text[:8000], True
    if body is not None:
        return str(body)[:8000], True
    return "", fallback_used


class DeepSeekProvider:
    name = "deepseek"

    async def complete_text(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.2,
        max_tokens: int = 2000,
        timeout_seconds: int = 60,
        json_mode: bool = False,
    ) -> LlmProviderTextResult:
        text_result, _parsed = await self._complete_chat(
            model=model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout_seconds=timeout_seconds,
            json_mode=json_mode,
            parse_json=False,
        )
        return text_result

    async def complete_json(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.2,
        max_tokens: int = 2000,
        response_schema: dict[str, Any] | None = None,
        timeout_seconds: int = 60,
        thinking_enabled: bool | None = None,
        reasoning_effort: str | None = None,
    ) -> LlmProviderResponse:
        """DeepSeek completion. ``thinking_enabled`` / ``reasoning_effort`` are
        DeepSeek-specific runtime controls.

        They default to None, and None means "send nothing" — the server's own
        default then applies, exactly as before. Only a caller that states its
        reasoning profile gets one sent, so adopting an explicit profile for
        knowledge production cannot silently change legacy workloads.
        """
        text_result, parsed_json = await self._complete_chat(
            model=model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout_seconds=timeout_seconds,
            json_mode=supports_json_object_mode(),
            parse_json=True,
            thinking_enabled=thinking_enabled,
            reasoning_effort=reasoning_effort,
        )
        return LlmProviderResponse(
            provider=text_result.provider,
            model=text_result.model,
            raw_text=text_result.raw_text or "",
            parsed_json=parsed_json,
            usage=text_result.usage,
            finish_reason=text_result.finish_reason,
            request_payload_redacted=text_result.request_payload_redacted,
            response_payload={
                **text_result.response_payload,
                **({"fallback_raw_response_used": True} if text_result.fallback_raw_response_used else {}),
            },
            latency_ms=text_result.latency_ms,
            error_message=text_result.error,
            transport_ok=text_result.transport_ok,
            response_format=text_result.response_format,
        )

    async def complete_structured_response(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        json_schema: dict[str, Any],
        schema_name: str = RESPONSES_SCHEMA_NAME,
        reasoning_effort: str | None = None,
        max_output_tokens: int | None = None,
        timeout_seconds: int = 60,
        strict: bool = True,
    ) -> LlmProviderResponse:
        """EXPERIMENTAL: Responses API with provider-side JSON Schema.

        Feasibility path only — nothing in production calls this, and
        ``complete_json`` (Chat Completions) is untouched, so legacy behaviour
        cannot change by accident.
        """
        config = get_deepseek_runtime_config()
        if not config.enabled:
            raise ProviderNotConfiguredError("DeepSeek provider is disabled in Settings.")
        api_key = (config.api_key or "").strip()
        if not api_key:
            raise ProviderNotConfiguredError(
                "DeepSeek API key is not configured; set it in Settings before extracting."
            )
        use_model = _resolve_model(model, config.default_model)
        base_url = config.base_url.rstrip("/")
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        # Responses-API shape. Field names are NOT the chat ones: `instructions`
        # / `input` / `text.format` / `reasoning` / `max_output_tokens`. Copying
        # `max_tokens` or `thinking` across would be silently ignored at best.
        payload: dict[str, Any] = {
            "model": use_model,
            "instructions": system_prompt,
            "input": user_prompt,
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": schema_name,
                    "schema": json_schema,
                    "strict": strict,
                }
            },
        }
        if reasoning_effort is not None:
            payload["reasoning"] = {"effort": reasoning_effort}
        if max_output_tokens is not None:
            payload["max_output_tokens"] = max_output_tokens

        resolved_timeout = max(
            timeout_seconds or config.timeout_seconds or 120, _MODEL_MIN_TIMEOUT
        )
        started = time.monotonic()
        logger.info(
            "[deepseek][responses] POST responses model=%s schema=%s reasoning=%s"
            " max_output_tokens=%s timeout=%ss",
            use_model,
            schema_name,
            reasoning_effort,
            max_output_tokens,
            resolved_timeout,
        )

        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(resolved_timeout, connect=15.0), trust_env=False
            ) as client:
                resp = await client.post(f"{base_url}/responses", json=payload, headers=headers)
        except httpx.HTTPError as exc:
            return LlmProviderResponse(
                provider=self.name,
                model=use_model,
                raw_text="",
                parsed_json=None,
                usage=LlmProviderUsage(),
                finish_reason=None,
                request_payload_redacted={
                    "model": use_model,
                    "schema_name": schema_name,
                    "endpoint": "/responses",
                },
                response_payload={"endpoint": "/responses"},
                latency_ms=int((time.monotonic() - started) * 1000),
                error_message=f"DeepSeek Responses request failed: {type(exc).__name__}",
                transport_ok=False,
            )

        latency_ms = int((time.monotonic() - started) * 1000)
        try:
            body = resp.json()
        except ValueError:
            body = None

        if resp.status_code >= 400:
            # Concise provider error only: no key, no headers, no echo of input.
            error_code = None
            error_message = None
            if isinstance(body, dict):
                error = body.get("error")
                if isinstance(error, dict):
                    error_code = error.get("code") or error.get("type")
                    error_message = error.get("message")
                elif isinstance(error, str):
                    error_message = error
            return LlmProviderResponse(
                provider=self.name,
                model=use_model,
                raw_text="",
                parsed_json=None,
                usage=LlmProviderUsage(),
                finish_reason=None,
                request_payload_redacted={
                    "model": use_model,
                    "schema_name": schema_name,
                    "endpoint": "/responses",
                },
                response_payload={
                    "endpoint": "/responses",
                    "status_code": resp.status_code,
                    "error_code": error_code,
                    "error_message": (error_message or "")[:300] or None,
                },
                latency_ms=latency_ms,
                error_message=f"DeepSeek Responses returned HTTP {resp.status_code}",
                transport_ok=False,
            )

        text, diagnostics = extract_responses_output(body)
        usage_raw = body.get("usage") if isinstance(body, dict) else None
        usage_raw = usage_raw if isinstance(usage_raw, dict) else {}
        details = usage_raw.get("output_tokens_details")
        usage = LlmProviderUsage(
            prompt_tokens=usage_raw.get("input_tokens"),
            completion_tokens=usage_raw.get("output_tokens"),
            total_tokens=usage_raw.get("total_tokens"),
            reasoning_tokens=details.get("reasoning_tokens") if isinstance(details, dict) else None,
        )
        return LlmProviderResponse(
            provider=self.name,
            model=use_model,
            raw_text=text,
            parsed_json=None,
            usage=usage,
            finish_reason=body.get("status") if isinstance(body, dict) else None,
            request_payload_redacted={
                "model": use_model,
                "schema_name": schema_name,
                "endpoint": "/responses",
                "reasoning_effort": reasoning_effort,
                "max_output_tokens": max_output_tokens,
            },
            response_payload={
                "endpoint": "/responses",
                "model": body.get("model") if isinstance(body, dict) else None,
                "status": body.get("status") if isinstance(body, dict) else None,
                "incomplete_details": body.get("incomplete_details") if isinstance(body, dict) else None,
                "extraction": diagnostics,
                "usage": usage.as_dict(),
            },
            latency_ms=latency_ms,
            error_message=None if text.strip() else "DeepSeek Responses returned no message text",
            transport_ok=True,
            response_format="json_schema",
        )

    async def _complete_chat(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        max_tokens: int,
        timeout_seconds: int,
        json_mode: bool,
        parse_json: bool,
        thinking_enabled: bool | None = None,
        reasoning_effort: str | None = None,
    ) -> tuple[LlmProviderTextResult, dict[str, Any] | None]:
        config = get_deepseek_runtime_config()
        if not config.enabled:
            raise ProviderNotConfiguredError("DeepSeek provider is disabled in Settings.")
        api_key = (config.api_key or "").strip()
        if not api_key:
            raise ProviderNotConfiguredError(
                "DeepSeek API key is not configured; set it in Settings before extracting."
            )

        # MODEL AUTHORITY. Whatever the caller (or config, or fallback) asked
        # for, DeepSeek is called with the single allowed model — resolved in
        # one place, so no business layer can select a different DeepSeek model,
        # and provenance below records what actually ran, not what was asked.
        use_model = _resolve_model(model, config.default_model)
        base_url = config.base_url.rstrip("/")
        redacted = {
            "model": use_model,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "message_roles": ["system", "user"],
            "thinking_enabled": thinking_enabled,
            "reasoning_effort": reasoning_effort,
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        json_mode_enabled = bool(json_mode and supports_json_object_mode())
        json_mode_warning: str | None = None

        async def _post(client: httpx.AsyncClient, *, use_json_mode: bool) -> httpx.Response:
            payload: dict[str, Any] = {
                "model": use_model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": temperature,
                "max_tokens": max_tokens,
                "stream": False,
            }
            if use_json_mode:
                payload["response_format"] = {"type": "json_object"}
            # REASONING PROFILE. Sent only when the caller asked for one, so
            # relying on the server default and stating the profile explicitly
            # are distinguishable — and the payload records which was chosen.
            if thinking_enabled is not None:
                payload["thinking"] = {
                    "type": "enabled" if thinking_enabled else "disabled"
                }
            if reasoning_effort is not None:
                payload["reasoning_effort"] = reasoning_effort
            return await client.post(
                f"{base_url}/chat/completions",
                json=payload,
                headers=headers,
            )

        # Unified timeout. Only DEEPSEEK_MODEL can reach here (see above), so a
        # single floor is enough — the retired per-model table is gone.
        resolved_timeout = max(
            timeout_seconds or config.timeout_seconds or 120, _MODEL_MIN_TIMEOUT
        )
        started = time.monotonic()
        logger.info(
            "[deepseek] POST chat/completions model=%s user_chars=%s json_mode=%s timeout=%ss",
            use_model,
            len(user_prompt),
            json_mode_enabled,
            resolved_timeout,
        )
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(resolved_timeout, connect=15.0),
            trust_env=False,
        ) as client:
            try:
                resp = await _post(client, use_json_mode=json_mode_enabled)
                if json_mode_enabled and resp.status_code >= 400:
                    body_text = resp.text[:500].lower()
                    if "response_format" in body_text or resp.status_code == 400:
                        logger.warning(
                            "[deepseek] JSON mode rejected (HTTP %s); retrying without response_format",
                            resp.status_code,
                        )
                        json_mode_warning = (
                            f"DeepSeek JSON mode unavailable (HTTP {resp.status_code}); "
                            "retried without response_format."
                        )
                        json_mode_enabled = False
                        resp = await _post(client, use_json_mode=False)
            except httpx.HTTPError as exc:
                latency_ms = int((time.monotonic() - started) * 1000)
                return LlmProviderTextResult(
                    provider=self.name,
                    model=use_model,
                    raw_text=None,
                    usage=LlmProviderUsage(),
                    finish_reason=None,
                    transport_ok=False,
                    error=f"DeepSeek request failed: {exc}",
                    request_payload_redacted={**redacted, "json_mode_enabled": json_mode_enabled},
                    response_payload={"json_mode_enabled": json_mode_enabled},
                    latency_ms=latency_ms,
                ), None

        latency_ms = int((time.monotonic() - started) * 1000)
        if resp.status_code >= 400:
            raw_text, fallback_used = extract_raw_text_from_response(None, http_text=resp.text)
            return LlmProviderTextResult(
                provider=self.name,
                model=use_model,
                raw_text=raw_text or resp.text[:2000] or None,
                usage=LlmProviderUsage(),
                finish_reason=None,
                transport_ok=False,
                error=f"DeepSeek returned HTTP {resp.status_code}",
                raw_response_preview=raw_response_preview(raw_text or resp.text[:2000]),
                request_payload_redacted={**redacted, "json_mode_enabled": json_mode_enabled},
                response_payload={
                    "status_code": resp.status_code,
                    "json_mode_enabled": json_mode_enabled,
                },
                latency_ms=latency_ms,
                fallback_raw_response_used=fallback_used,
            ), None

        try:
            body = resp.json()
        except ValueError:
            raw_text, fallback_used = extract_raw_text_from_response(None, http_text=resp.text)
            return LlmProviderTextResult(
                provider=self.name,
                model=use_model,
                raw_text=raw_text or resp.text[:2000] or None,
                usage=LlmProviderUsage(),
                finish_reason=None,
                transport_ok=True,
                error="DeepSeek response was not valid JSON",
                raw_response_preview=raw_response_preview(raw_text or resp.text[:2000]),
                request_payload_redacted={**redacted, "json_mode_enabled": json_mode_enabled},
                response_payload={"json_mode_enabled": json_mode_enabled},
                latency_ms=latency_ms,
                fallback_raw_response_used=fallback_used,
            ), None

        raw_text, fallback_used = extract_raw_text_from_response(body, http_text=resp.text)
        finish = None
        choices = body.get("choices") if isinstance(body, dict) else None
        if isinstance(choices, list) and choices and isinstance(choices[0], dict):
            finish = choices[0].get("finish_reason")

        usage_raw = body.get("usage") or {} if isinstance(body, dict) else {}
        # Reasoning is reported as a COUNT where the provider reports it at all.
        # The reasoning TEXT is never read here: `message.content` remains the
        # only answer, and deliberation never becomes a candidate.
        details = usage_raw.get("completion_tokens_details")
        reasoning_tokens = (
            details.get("reasoning_tokens") if isinstance(details, dict) else None
        )
        usage = LlmProviderUsage(
            prompt_tokens=usage_raw.get("prompt_tokens"),
            completion_tokens=usage_raw.get("completion_tokens"),
            total_tokens=usage_raw.get("total_tokens"),
            reasoning_tokens=reasoning_tokens,
        )
        response_payload: dict[str, Any] = {
            "model": body.get("model") if isinstance(body, dict) else None,
            "usage": usage.as_dict(),
            "json_mode_enabled": json_mode_enabled,
        }
        if isinstance(usage_raw, dict) and usage_raw.get("reasoning_tokens") is not None:
            response_payload["usage_reasoning_tokens"] = usage_raw.get("reasoning_tokens")
        if isinstance(body, dict):
            response_payload["raw_response_keys"] = list(body.keys())
        if json_mode_warning:
            response_payload["json_mode_warning"] = json_mode_warning
        if fallback_used:
            response_payload["fallback_raw_response_used"] = True

        parsed_json = _try_parse_json(raw_text) if parse_json and raw_text else None
        preview = raw_response_preview(raw_text) if raw_text else None
        return LlmProviderTextResult(
            provider=self.name,
            model=use_model,
            raw_text=raw_text or None,
            usage=usage,
            finish_reason=finish,
            transport_ok=True,
            error=None if raw_text else "DeepSeek response missing content",
            raw_response_preview=preview,
            response_format="json_object" if json_mode_enabled else None,
            request_payload_redacted={**redacted, "json_mode_enabled": json_mode_enabled},
            response_payload=response_payload,
            latency_ms=latency_ms,
            fallback_raw_response_used=fallback_used,
        ), parsed_json
