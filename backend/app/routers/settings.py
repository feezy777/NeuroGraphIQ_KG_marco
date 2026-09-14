"""Workbench Settings API.

This router manages local runtime settings only. It never writes candidate,
final_*, or kg_* tables, and it never returns API keys in responses.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.schemas.settings import (
    DeepSeekConnectionTestRequest,
    DeepSeekConnectionTestResponse,
    RuntimeSettingsPatch,
    SettingsOptions,
    SettingsProviderOption,
    SettingsLanguageOption,
    PublicRuntimeSettings,
)
from app.services import settings_service
from app.llm_model_policy import (
    DEEPSEEK_PROVIDER,
    available_models,
)

router = APIRouter()


@router.get("/options", response_model=SettingsOptions)
async def get_settings_options():
    return SettingsOptions(
        languages=[
            SettingsLanguageOption(value="zh-CN", label="中文"),
            SettingsLanguageOption(value="en-US", label="English"),
        ],
        api_providers=[
            SettingsProviderOption(value="deepseek", label="DeepSeek"),
            SettingsProviderOption(value="openai", label="OpenAI", disabled=True),
            SettingsProviderOption(value="anthropic", label="Claude", disabled=True),
            SettingsProviderOption(value="local", label="Local Model", disabled=True),
        ],
        # DeepSeek exposes exactly ONE model; see model_registry for the frozen
        # policy. Other providers' model lists are untouched.
        default_models={"deepseek": available_models(DEEPSEEK_PROVIDER)},
    )


@router.get("/runtime", response_model=PublicRuntimeSettings)
async def get_runtime_settings():
    return settings_service.to_public_runtime_settings(
        settings_service.load_runtime_settings()
    )


@router.patch("/runtime", response_model=PublicRuntimeSettings)
async def patch_runtime_settings(body: RuntimeSettingsPatch):
    return settings_service.update_runtime_settings(body)


@router.post(
    "/api-providers/deepseek/test",
    response_model=DeepSeekConnectionTestResponse,
)
async def test_deepseek_connection(body: DeepSeekConnectionTestRequest):
    return await settings_service.test_deepseek_connection(body)
