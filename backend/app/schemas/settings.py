"""Schemas for local Workbench runtime settings.

Settings are local operational configuration only. They never write candidate,
final_*, or kg_* data, and public response models never expose API keys.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from app.llm_model_policy import DEEPSEEK_MODEL

#: DeepSeek reasoning effort levels. `high` is the model's own default; naming
#: it here makes the adopted profile explicit instead of implicit.
ReasoningEffort = Literal["low", "medium", "high", "max"]


class DeepSeekRuntimeSettings(BaseModel):
    enabled: bool = True
    base_url: str = "https://api.deepseek.com/v1"
    default_model: str = DEEPSEEK_MODEL
    api_key: str = ""
    #: 64K generation can legitimately take minutes; 120s was sized for the old
    #: 2K budget. Still bounded, so a hung request cannot occupy a worker.
    timeout_seconds: int = Field(default=300, ge=5, le=600)
    max_batch_size: int = Field(default=20, ge=1, le=20)
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    # THINKING MODE. Left to the server, this was implicitly ON with `high`
    # effort — an invisible 8K of the budget went to reasoning before any answer
    # existed. The runtime now states it, so the profile is a decision rather
    # than a default. Values are sent ONLY when a caller supplies them, so
    # legacy DeepSeek workloads keep whatever the server does today.
    thinking_enabled: bool = True
    reasoning_effort: ReasoningEffort = "high"
    # RUNTIME CONFIGURATION, not knowledge semantics. DeepSeek knowledge-
    # production workloads are QUALITY-FIRST: a complete structured answer must
    # be reachable. Truncation is a correctness failure, not a saving —
    # `finish_reason = "length"` means the model never produced an answer.
    # The model's own ceiling is far higher; this is the project's chosen
    # first-stage budget, and `le` is the diagnostic headroom (§7 / §22).
    # This is the ONLY authority for a DeepSeek request's max_tokens: no
    # business layer may lower it to save tokens. See §16 of
    # docs/KNOWLEDGE_PRODUCTION_ARCHITECTURE.md.
    max_tokens: int = Field(default=65536, ge=256, le=131072)


class KimiRuntimeSettings(BaseModel):
    enabled: bool = True
    base_url: str = "https://api.moonshot.cn/v1"
    default_model: str = "moonshot-v1-8k"
    api_key: str = ""
    timeout_seconds: int = Field(default=60, ge=5, le=120)
    max_batch_size: int = Field(default=20, ge=1, le=20)
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    max_tokens: int = Field(default=2000, ge=256, le=8192)


class ApiProviderRuntimeSettings(BaseModel):
    deepseek: DeepSeekRuntimeSettings = Field(default_factory=DeepSeekRuntimeSettings)
    kimi: KimiRuntimeSettings = Field(default_factory=KimiRuntimeSettings)


class BasicRuntimeSettings(BaseModel):
    default_page_size: int = Field(default=50, ge=10, le=200)
    max_page_size: int = Field(default=500, ge=50, le=500)
    show_debug_panels: bool = True

    @model_validator(mode="after")
    def validate_page_sizes(self):
        if self.max_page_size < self.default_page_size:
            raise ValueError("max_page_size must be greater than or equal to default_page_size")
        return self


class OntologyQueryRuntimeSettings(BaseModel):
    """Phase Q4 — Ontology Query LLM 解释层模型配置（不硬编码，低温度保证医学回答稳定）。"""

    enabled: bool = True
    provider: str = "deepseek"
    model: str = DEEPSEEK_MODEL
    temperature: float = Field(default=0.1, ge=0.0, le=1.0)


class RuntimeSettings(BaseModel):
    api_providers: ApiProviderRuntimeSettings = Field(
        default_factory=ApiProviderRuntimeSettings
    )
    basic: BasicRuntimeSettings = Field(default_factory=BasicRuntimeSettings)
    ontology_query: OntologyQueryRuntimeSettings = Field(
        default_factory=OntologyQueryRuntimeSettings
    )


class PublicDeepSeekRuntimeSettings(BaseModel):
    enabled: bool
    base_url: str
    default_model: str
    api_key_configured: bool
    api_key_masked: str | None
    timeout_seconds: int
    max_batch_size: int
    temperature: float = 0.2
    max_tokens: int = 2000
    # The adopted reasoning profile is part of the runtime contract, so the UI
    # can show it rather than leaving it invisible.
    thinking_enabled: bool = True
    reasoning_effort: ReasoningEffort = "high"


class PublicKimiRuntimeSettings(BaseModel):
    enabled: bool
    base_url: str
    default_model: str
    api_key_configured: bool
    api_key_masked: str | None
    timeout_seconds: int
    max_batch_size: int
    temperature: float = 0.2
    max_tokens: int = 2000


class PublicApiProviderRuntimeSettings(BaseModel):
    deepseek: PublicDeepSeekRuntimeSettings
    kimi: PublicKimiRuntimeSettings


class PublicRuntimeSettings(BaseModel):
    api_providers: PublicApiProviderRuntimeSettings
    basic: BasicRuntimeSettings
    ontology_query: OntologyQueryRuntimeSettings


class DeepSeekRuntimeSettingsPatch(BaseModel):
    enabled: bool | None = None
    base_url: str | None = None
    default_model: str | None = None
    api_key: str | None = None
    explicit_clear_api_key: bool = False
    timeout_seconds: int | None = Field(default=None, ge=5, le=600)
    max_batch_size: int | None = Field(default=None, ge=1, le=20)
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    thinking_enabled: bool | None = None
    reasoning_effort: ReasoningEffort | None = None
    max_tokens: int | None = Field(default=None, ge=256, le=131072)


class KimiRuntimeSettingsPatch(BaseModel):
    enabled: bool | None = None
    base_url: str | None = None
    default_model: str | None = None
    api_key: str | None = None
    explicit_clear_api_key: bool = False
    timeout_seconds: int | None = Field(default=None, ge=5, le=120)
    max_batch_size: int | None = Field(default=None, ge=1, le=20)
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    max_tokens: int | None = Field(default=None, ge=256, le=8192)


class ApiProviderRuntimeSettingsPatch(BaseModel):
    deepseek: DeepSeekRuntimeSettingsPatch | None = None
    kimi: KimiRuntimeSettingsPatch | None = None


class BasicRuntimeSettingsPatch(BaseModel):
    default_page_size: int | None = Field(default=None, ge=10, le=200)
    max_page_size: int | None = Field(default=None, ge=50, le=500)
    show_debug_panels: bool | None = None


class OntologyQueryRuntimeSettingsPatch(BaseModel):
    enabled: bool | None = None
    provider: str | None = None
    model: str | None = None
    temperature: float | None = Field(default=None, ge=0.0, le=1.0)


class RuntimeSettingsPatch(BaseModel):
    api_providers: ApiProviderRuntimeSettingsPatch | None = None
    basic: BasicRuntimeSettingsPatch | None = None
    ontology_query: OntologyQueryRuntimeSettingsPatch | None = None


class SettingsLanguageOption(BaseModel):
    value: str
    label: str


class SettingsProviderOption(BaseModel):
    value: str
    label: str
    disabled: bool = False


class SettingsOptions(BaseModel):
    languages: list[SettingsLanguageOption]
    api_providers: list[SettingsProviderOption]
    default_models: dict[str, list[str]]


class DeepSeekConnectionTestRequest(BaseModel):
    base_url: str | None = None
    default_model: str | None = None
    api_key: str | None = None


class DeepSeekConnectionTestResponse(BaseModel):
    ok: bool
    provider: str = "deepseek"
    model: str | None = None
    latency_ms: int | None = None
    error_message: str | None = None


class DeepSeekRuntimeConfig(BaseModel):
    """Resolved internal DeepSeek config; may contain a secret."""

    model_config = ConfigDict(frozen=True)

    enabled: bool
    base_url: str
    default_model: str
    api_key: str
    timeout_seconds: int
    max_batch_size: int
    temperature: float = 0.2
    max_tokens: int = 2000
    # Reasoning controls the DISCOVERY path sends explicitly. A caller that
    # omits them leaves the server's own behaviour untouched, which is why the
    # legacy DeepSeek workloads are unaffected by adopting this profile.
    thinking_enabled: bool | None = None
    reasoning_effort: ReasoningEffort | None = None


class KimiRuntimeConfig(BaseModel):
    """Resolved internal Kimi config; may contain a secret."""

    model_config = ConfigDict(frozen=True)

    enabled: bool
    base_url: str
    default_model: str
    api_key: str
    timeout_seconds: int
    max_batch_size: int
    temperature: float = 0.2
    max_tokens: int = 2000
