"""Pydantic schemas for Canonical Circuit (CI1.1)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

CIRCUIT_CODE_PATTERN = r"^ng:ci:[a-z0-9_]+$"

_CIRCUIT_TYPES = {"network", "pathway", "reflex", "functional_loop", "uncertain"}
_REGION_ROLES = {"core_region", "input", "output", "intermediate"}
_CONNECTION_ROLES = {"feedforward", "feedback", "supporting"}
_RELATION_TYPES = {
    "involved_in",
    "associated_with",
    "necessary_for",
    "modulates",
    "participates_in",
    "uncertain_association",
    "unknown",
}
_SPECIES = {"human", "mouse", "unknown"}
_STATUSES = {"proposed", "active", "deprecated"}
_GRANULARITY_LEVELS = {"whole_brain", "macro", "clinical", "research", "fine", "ultra_fine"}


class CanonicalCircuitCreate(BaseModel):
    canonical_name_en: str
    canonical_name_cn: str | None = None
    circuit_type: str
    # Optional: when omitted the service auto-generates ng:ci:<slug>.
    circuit_code: str | None = Field(default=None, pattern=CIRCUIT_CODE_PATTERN)
    species: str = "human"
    granularity_level: str = "clinical"
    status: str = "proposed"
    description: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    source_summary: dict[str, Any] = Field(default_factory=dict)
    provenance_json: dict[str, Any] = Field(default_factory=dict)
    created_by: str | None = None

    @field_validator("circuit_type")
    @classmethod
    def _valid_type(cls, v: str) -> str:
        if v not in _CIRCUIT_TYPES:
            raise ValueError(f"invalid circuit_type: {v}")
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


class CanonicalCircuitRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    circuit_code: str
    canonical_name_en: str
    canonical_name_cn: str | None
    species: str
    granularity_level: str
    circuit_type: str
    status: str
    description: str | None
    confidence: float | None
    source_summary: dict[str, Any]
    provenance_json: dict[str, Any]
    replaced_by_circuit_id: uuid.UUID | None
    created_by: str | None
    created_at: datetime
    updated_at: datetime


class CanonicalCircuitRegionCreate(BaseModel):
    region_id: uuid.UUID
    role: str = "core_region"
    order_index: int = 0
    confidence: float | None = Field(default=None, ge=0, le=1)
    provenance_json: dict[str, Any] = Field(default_factory=dict)

    @field_validator("role")
    @classmethod
    def _valid_role(cls, v: str) -> str:
        if v not in _REGION_ROLES:
            raise ValueError(f"invalid region role: {v}")
        return v


class CanonicalCircuitRegionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    circuit_id: uuid.UUID
    region_id: uuid.UUID
    role: str
    order_index: int
    confidence: float | None
    provenance_json: dict[str, Any]
    created_at: datetime


class CanonicalCircuitConnectionCreate(BaseModel):
    connection_id: uuid.UUID
    role: str = "supporting"
    confidence: float | None = Field(default=None, ge=0, le=1)
    provenance_json: dict[str, Any] = Field(default_factory=dict)

    @field_validator("role")
    @classmethod
    def _valid_role(cls, v: str) -> str:
        if v not in _CONNECTION_ROLES:
            raise ValueError(f"invalid connection role: {v}")
        return v


class CanonicalCircuitConnectionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    circuit_id: uuid.UUID
    connection_id: uuid.UUID
    role: str
    confidence: float | None
    provenance_json: dict[str, Any]
    created_at: datetime


class CanonicalCircuitFunctionCreate(BaseModel):
    function_term_id: uuid.UUID
    relation_type: str = "associated_with"
    confidence: float | None = Field(default=None, ge=0, le=1)
    provenance_json: dict[str, Any] = Field(default_factory=dict)

    @field_validator("relation_type")
    @classmethod
    def _valid_relation(cls, v: str) -> str:
        if v not in _RELATION_TYPES:
            raise ValueError(f"invalid relation_type: {v}")
        return v


class CanonicalCircuitFunctionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    circuit_id: uuid.UUID
    function_term_id: uuid.UUID
    relation_type: str
    confidence: float | None
    provenance_json: dict[str, Any]
    created_at: datetime


class CanonicalCircuitMergeRequest(BaseModel):
    deprecated_circuit_id: uuid.UUID
    active_circuit_id: uuid.UUID
