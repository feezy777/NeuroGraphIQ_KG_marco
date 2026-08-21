"""Pydantic schemas for Canonical Connection (CN1.2-1)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

CONNECTION_CODE_PATTERN = r"^ng:cn:[a-z0-9_]+$"

_CONNECTION_TYPES = {"structural", "functional", "projection", "association", "coactivation", "uncertain"}
_DIRECTIONALITY_POLICIES = {"directed", "bidirectional", "undirected", "unspecified"}
_SPECIES = {"human", "mouse", "unknown"}
_STATUSES = {"proposed", "active", "deprecated"}
_GRANULARITY_LEVELS = {"whole_brain", "macro", "clinical", "research", "fine", "ultra_fine"}


class CanonicalConnectionCreate(BaseModel):
    source_region_id: uuid.UUID
    target_region_id: uuid.UUID
    connection_type: str
    # Optional: when omitted the service auto-generates ng:cn:<slug>.
    connection_code: str | None = Field(default=None, pattern=CONNECTION_CODE_PATTERN)
    directionality_policy: str = "unspecified"
    species: str = "human"
    granularity_level: str = "clinical"
    status: str = "proposed"
    confidence: float | None = Field(default=None, ge=0, le=1)
    source_summary: dict[str, Any] = Field(default_factory=dict)
    evidence_summary: dict[str, Any] = Field(default_factory=dict)
    provenance_json: dict[str, Any] = Field(default_factory=dict)

    @field_validator("connection_type")
    @classmethod
    def _valid_type(cls, v: str) -> str:
        if v not in _CONNECTION_TYPES:
            raise ValueError(f"invalid connection_type: {v}")
        return v

    @field_validator("directionality_policy")
    @classmethod
    def _valid_directionality(cls, v: str) -> str:
        if v not in _DIRECTIONALITY_POLICIES:
            raise ValueError(f"invalid directionality_policy: {v}")
        return v

    @field_validator("species")
    @classmethod
    def _valid_species(cls, v: str) -> str:
        if v not in _SPECIES:
            raise ValueError(f"invalid species: {v}")
        return v

    @field_validator("status")
    @classmethod
    def _valid_status(cls, v: str) -> str:
        if v not in _STATUSES:
            raise ValueError(f"invalid status: {v}")
        return v

    @field_validator("granularity_level")
    @classmethod
    def _valid_granularity(cls, v: str) -> str:
        if v not in _GRANULARITY_LEVELS:
            raise ValueError(f"invalid granularity_level: {v}")
        return v


class CanonicalConnectionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    connection_code: str
    source_region_id: uuid.UUID
    target_region_id: uuid.UUID
    connection_type: str
    directionality_policy: str
    species: str
    granularity_level: str
    status: str
    confidence: float | None
    source_summary: dict[str, Any]
    evidence_summary: dict[str, Any]
    provenance_json: dict[str, Any]
    replaced_by_connection_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
