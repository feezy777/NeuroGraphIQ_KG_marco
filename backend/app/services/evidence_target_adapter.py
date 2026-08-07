"""Unified Evidence Target Adapter.

Maps any supported knowledge object (connection / projection_function / circuit /
circuit_function / circuit_step / region_function) into a single Evidence Target DTO
that search, retrieval, and DeepSeek judgment consume. Nothing else in the evidence
chain should reach into raw object rows directly.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.mirror_kg import (
    MirrorRegionCircuit,
    MirrorRegionConnection,
    MirrorRegionFunction,
)
from app.models.mirror_macro_clinical import (
    MirrorCircuitFunction,
    MirrorCircuitStep,
    MirrorProjectionFunction,
)

CLAIM_VERSION = "claim_v1"

TARGET_MODELS = {
    "projection_function": MirrorProjectionFunction,
    "circuit_function": MirrorCircuitFunction,
    "region_function": MirrorRegionFunction,
    "projection": MirrorRegionConnection,
    "connection": MirrorRegionConnection,
    "circuit": MirrorRegionCircuit,
    "circuit_step": MirrorCircuitStep,
}


def _clean(value: object) -> str:
    if value is None:
        return ""
    s = str(value).strip()
    return "" if s.lower() == "unknown" else s


def _join(parts: list[str], limit: int = 3) -> list[str]:
    return [p for p in parts if p][:limit]


def _build_claim(target_type: str, dto: dict) -> str:
    if target_type in ("connection", "projection"):
        src = dto.get("source_region") or "?"
        tgt = dto.get("target_region") or "?"
        rel = dto.get("relation") or "连接"
        direction = dto.get("directionality") or ""
        base = f"{src} 到 {tgt} 存在{rel}"
        return f"{base}（方向性：{direction}）。" if direction else f"{base}。"
    if target_type == "projection_function":
        src = dto.get("source_region") or "?"
        tgt = dto.get("target_region") or "?"
        terms = dto.get("canonical_terms") or []
        return f"从 {src} 到 {tgt} 的投射具有功能「{terms[0] if terms else '?'}」。"
    if target_type == "region_function":
        region = dto.get("source_region") or dto.get("target_region") or "?"
        terms = dto.get("canonical_terms") or []
        return f"脑区「{region}」具有功能「{terms[0] if terms else '?'}」（{dto.get('relation') or 'associated_with'}）。"
    if target_type == "circuit":
        name = dto.get("display_name") or "?"
        return f"回路「{name}」（{dto.get('relation') or 'unknown'}）存在并参与相关神经功能。"
    if target_type == "circuit_function":
        circuit = dto.get("circuit_context") or "?"
        terms = dto.get("canonical_terms") or []
        return f"回路「{circuit}」具有功能「{terms[0] if terms else '?'}」（{dto.get('function_context') or ''}）。"
    if target_type == "circuit_step":
        name = dto.get("display_name") or "?"
        return f"回路步骤「{name}」（{dto.get('relation') or 'unknown'}）在回路中发挥作用。"
    return dto.get("display_name") or target_type


def _connection_dto(row: MirrorRegionConnection) -> dict:
    return {
        "granularity": _clean(getattr(row, "granularity_level", "")),
        "display_name": _join(
            [
                _clean(getattr(row, "source_region_name_en", "")),
                _clean(getattr(row, "target_region_name_en", "")),
                _clean(getattr(row, "connection_type", "")),
            ]
        ),
        "source_region": _clean(getattr(row, "source_region_name_en", "")),
        "target_region": _clean(getattr(row, "target_region_name_en", "")),
        "canonical_terms": _join(
            [
                _clean(getattr(row, "source_region_name_en", "")),
                _clean(getattr(row, "target_region_name_en", "")),
                _clean(getattr(row, "connection_type", "")),
            ]
        ),
        "relation": "投射连接" if getattr(row, "connection_type", "") else "连接",
        "directionality": _clean(getattr(row, "directionality", "")),
        "circuit_context": "",
        "function_context": "",
    }


def _region_function_dto(row: MirrorRegionFunction) -> dict:
    return {
        "granularity": _clean(getattr(row, "granularity_level", "")),
        "display_name": _join([_clean(getattr(row, "function_term", "")), _clean(getattr(row, "region_name_en", ""))]),
        "source_region": _clean(getattr(row, "region_name_en", "")),
        "target_region": "",
        "canonical_terms": _join([_clean(getattr(row, "function_term", ""))]),
        "relation": _clean(getattr(row, "relation_type", "")),
        "directionality": "",
        "circuit_context": "",
        "function_context": _clean(getattr(row, "function_category", "")),
    }


def _circuit_dto(row: MirrorRegionCircuit) -> dict:
    return {
        "granularity": _clean(getattr(row, "granularity_level", "")),
        "display_name": _join([_clean(getattr(row, "circuit_name", "")), _clean(getattr(row, "name_cn", ""))]),
        "source_region": "",
        "target_region": "",
        "canonical_terms": _join([_clean(getattr(row, "circuit_name", ""))]),
        "relation": _clean(getattr(row, "circuit_type", "")),
        "directionality": "",
        "circuit_context": _clean(getattr(row, "circuit_name", "")),
        "function_context": "",
    }


def _circuit_function_dto(row: MirrorCircuitFunction) -> dict:
    return {
        "granularity": _clean(getattr(row, "granularity_level", "")),
        "display_name": _join(
            [
                _clean(getattr(row, "function_term_en", "")),
                _clean(getattr(row, "function_term_cn", "")),
            ]
        ),
        "source_region": "",
        "target_region": "",
        "canonical_terms": _join(
            [
                _clean(getattr(row, "function_term_en", "")),
                _clean(getattr(row, "function_term_cn", "")),
            ]
        ),
        "relation": _clean(getattr(row, "function_role", "")),
        "directionality": "",
        "circuit_context": str(getattr(row, "circuit_id", "")),
        "function_context": _join(
            [
                _clean(getattr(row, "function_domain", "")),
                _clean(getattr(row, "function_role", "")),
                _clean(getattr(row, "effect_type", "")),
            ],
            limit=3,
        ),
    }


def _circuit_step_dto(row: MirrorCircuitStep) -> dict:
    return {
        "granularity": _clean(getattr(row, "granularity_level", "")),
        "display_name": _join([_clean(getattr(row, "step_name", "")), _clean(getattr(row, "role", ""))]),
        "source_region": "",
        "target_region": "",
        "canonical_terms": _join([_clean(getattr(row, "step_name", ""))]),
        "relation": _clean(getattr(row, "role", "")),
        "directionality": "",
        "circuit_context": str(getattr(row, "circuit_id", "")),
        "function_context": _clean(getattr(row, "step_type", "")),
    }


def _projection_function_dto(row: MirrorProjectionFunction) -> dict:
    return {
        "granularity": _clean(getattr(row, "granularity_level", "")),
        "display_name": _join([_clean(getattr(row, "function_term", ""))]),
        "source_region": "",
        "target_region": "",
        "canonical_terms": _join([_clean(getattr(row, "function_term", ""))]),
        "relation": _clean(getattr(row, "relation_type", "")),
        "directionality": "",
        "circuit_context": str(getattr(row, "projection_id", "")),
        "function_context": _join(
            [
                _clean(getattr(row, "function_domain", "")),
                _clean(getattr(row, "function_role", "")),
                _clean(getattr(row, "effect_type", "")),
            ],
            limit=3,
        ),
    }


_DTO_BUILDERS = {
    "connection": _connection_dto,
    "projection": _connection_dto,
    "region_function": _region_function_dto,
    "circuit": _circuit_dto,
    "circuit_function": _circuit_function_dto,
    "circuit_step": _circuit_step_dto,
    "projection_function": _projection_function_dto,
}


async def build_target_dto(
    session: AsyncSession, target_type: str, target_id: uuid.UUID
) -> dict:
    model = TARGET_MODELS.get(target_type)
    builder = _DTO_BUILDERS.get(target_type)
    if model is None or builder is None:
        raise ValueError(f"unsupported target_type: {target_type}")
    row = await session.get(model, target_id)
    if row is None:
        raise ValueError("target not found")
    dto = builder(row)
    confidence = getattr(row, "confidence", None)
    if confidence is None and target_type == "circuit_function":
        confidence = getattr(row, "confidence_score", None)
    dto.update(
        {
            "target_type": target_type,
            "target_id": str(target_id),
            "current_confidence": float(confidence) if confidence is not None else None,
            "display_name": " · ".join(dto["display_name"]) if isinstance(dto["display_name"], list) else dto["display_name"],
            "canonical_terms": dto["canonical_terms"] if isinstance(dto["canonical_terms"], list) else [dto["canonical_terms"]],
            "existing_evidence": await _count_evidence(session, target_type, target_id),
        }
    )
    dto["claim_text"] = _build_claim(target_type, dto)
    dto["structured_claim"] = {
        "target_type": target_type,
        "target_id": str(target_id),
        "source_region": dto.get("source_region") or None,
        "target_region": dto.get("target_region") or None,
        "relation": dto.get("relation") or None,
        "canonical_terms": dto.get("canonical_terms") or [],
    }
    dto["claim_version"] = CLAIM_VERSION
    return dto


async def _count_evidence(session: AsyncSession, target_type: str, target_id: uuid.UUID) -> int:
    return int(
        (
            await session.execute(
                text(
                    "SELECT COUNT(*) FROM mirror_evidence_records "
                    "WHERE evidence_target_type=:tt AND evidence_target_id=:oid "
                    "AND evidence_type='paper_verification' "
                    "AND verification_status IN ('human_verified','ai_extracted')"
                ),
                {"tt": target_type, "oid": target_id},
            )
        ).scalar_one()
    )


async def build_search_query(session: AsyncSession, target_type: str, target_id: uuid.UUID) -> str:
    dto = await build_target_dto(session, target_type, target_id)
    tokens = []
    for term in dto["canonical_terms"]:
        if term and len(term) <= 80:
            tokens.append(f'"{term}"')
    if not tokens:
        tokens = [f'"{dto.get("display_name", "")}"']
    return " AND ".join(tokens)
