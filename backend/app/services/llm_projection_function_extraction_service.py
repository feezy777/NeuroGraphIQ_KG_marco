"""Projection-to-functions extraction — LLM run/item + mirror_projection_functions (Step 8.9).

Derives mirror_projection_functions from mirror_region_connections (projection semantics).
Does NOT write final_*/kg_*; does NOT auto approve/promote.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.candidate import CandidateBrainRegion
from app.models.llm_extraction import LlmExtractionItem, LlmExtractionRun
from app.models.mirror_kg import MirrorRegionCircuit, MirrorRegionConnection
from app.models.mirror_macro_clinical import MirrorCircuitProjectionMembership, MirrorCircuitStep, MirrorProjectionFunction
from app.schemas.llm_extraction import LlmItemStatus, LlmRunStatus, LlmScopeType, LlmTaskType
from app.schemas.mirror_kg import (
    FunctionCategory,
    FunctionRelationType,
    MirrorKgTripleCreate,
    MirrorPromotionStatus,
    MirrorReviewStatus,
    MirrorStatus,
    TripleObjectType,
    TripleScope,
    TripleSubjectType,
)
from app.schemas.mirror_macro_clinical import MirrorProjectionFunctionCreate
from app.services import mirror_kg_service, mirror_macro_clinical_service
from app.services.llm_extraction_prompt_engineering import prompt_display_name
from app.services.llm_extraction_service import ProviderNotConfiguredServiceError
from app.services.llm_function_extraction_service import RELATION_TO_PREDICATE
from app.services.llm_json_utils import (
    LlmJsonParseError,
    parse_llm_json_response,
    raw_response_preview,
)
from app.services.llm_prompt_defaults import DEFAULT_TEMPLATES, render_user_prompt
from app.services.ontology_vocab_cache import (
    get_vocab_codes,
    refresh_vocab_cache,
)
from app.services.ontology_service import ground_written_records
from app.services.llm_providers import LlmProviderResponse, UnknownProviderError, get_llm_provider
from app.services.settings_service import get_deepseek_runtime_config, get_kimi_runtime_config
from app.services.llm_workflow_artifact_tagging import tag_raw_payload
from app.services.llm_status_utils import apply_persistent_run_status

logger = logging.getLogger(__name__)

PROJECTION_TO_FUNCTIONS_TEMPLATE_KEY = "projection_to_functions_v1"
MAX_PROJECTIONS = 50
DEFAULT_MAX_FUNCTIONS_PER_PROJECTION = 5

DEFAULT_ALLOWED_FUNCTION_CATEGORIES = frozenset({
    FunctionCategory.motor,
    FunctionCategory.sensory,
    FunctionCategory.visual,
    FunctionCategory.auditory,
    FunctionCategory.language,
    FunctionCategory.memory,
    FunctionCategory.emotion,
    FunctionCategory.executive_control,
    FunctionCategory.attention,
    FunctionCategory.autonomic,
    FunctionCategory.default_mode,
    FunctionCategory.salience,
    FunctionCategory.reward,
    FunctionCategory.cognitive,
    FunctionCategory.unknown,
})

DEFAULT_ALLOWED_RELATION_TYPES = frozenset({
    FunctionRelationType.involved_in,
    FunctionRelationType.associated_with,
    FunctionRelationType.necessary_for,
    FunctionRelationType.modulates,
    FunctionRelationType.participates_in,
    FunctionRelationType.uncertain_association,
    FunctionRelationType.unknown,
})

# Tolerant mapping for legacy/free-text LLM output (function_domain / function_role).
_FUNCTION_CATEGORY_ALIASES: dict[str, str] = {
    "motor_function": "motor",
    "sensorimotor": "motor",
    "sensory_processing": "sensory",
    "sensory_function": "sensory",
    "visual_processing": "visual",
    "visual_function": "visual",
    "auditory_processing": "auditory",
    "auditory_function": "auditory",
    "language_processing": "language",
    "language_function": "language",
    "memory_encoding": "memory",
    "memory_function": "memory",
    "memory-related": "memory",
    "emotional": "emotion",
    "emotion_processing": "emotion",
    "executive": "executive_control",
    "executive_function": "executive_control",
    "executive_control_function": "executive_control",
    "attention_control": "attention",
    "autonomic_function": "autonomic",
    "default_mode_network": "default_mode",
    "dmn": "default_mode",
    "salience_network": "salience",
    "reward_processing": "reward",
    "reward_function": "reward",
    "cognitive_control": "cognitive",
    "cognitive_function": "cognitive",
    "other": "unknown",
}

_FUNCTION_RELATION_ALIASES: dict[str, str] = {
    "execution": "participates_in",
    "integration": "participates_in",
    "modulation": "modulates",
    "modulating": "modulates",
    "regulates": "modulates",
    "facilitates": "modulates",
    "inhibition": "modulates",
    "gating": "modulates",
    "controls": "modulates",
    "supports": "associated_with",
    "role": "associated_with",
}


def _normalize_category(
    value: Any,
    allowed: frozenset[str] | None = None,
) -> tuple[str, bool]:
    allowed = get_vocab_codes("category") if allowed is None else allowed
    raw = str(value or "").strip()
    if not raw:
        return FunctionCategory.unknown, False
    key = raw.lower().replace(" ", "_")
    if key in allowed:
        return key, True
    mapped = _FUNCTION_CATEGORY_ALIASES.get(key)
    if mapped is not None:
        return mapped, True
    return FunctionCategory.unknown, False


def _normalize_relation(
    value: Any,
    allowed: frozenset[str] | None = None,
) -> tuple[str, bool]:
    allowed = get_vocab_codes("relation_type") if allowed is None else allowed
    raw = str(value or "").strip()
    if not raw:
        return FunctionRelationType.unknown, False
    key = raw.lower().replace(" ", "_")
    if key in allowed:
        return key, True
    mapped = _FUNCTION_RELATION_ALIASES.get(key)
    if mapped is not None:
        return mapped, True
    return FunctionRelationType.unknown, False


class EmptyProjectionsError(Exception):
    pass


class TooManyProjectionsError(Exception):
    def __init__(self, count: int, maximum: int):
        self.count = count
        self.maximum = maximum
        super().__init__(f"projection count {count} exceeds max {maximum}")


class ProjectionNotFoundError(Exception):
    def __init__(self, projection_id: str):
        self.projection_id = projection_id
        super().__init__(f"projection not found: {projection_id}")


class CrossAtlasProjectionError(Exception):
    def __init__(self, atlases: list[str]):
        self.atlases = atlases
        super().__init__("projections span multiple source_atlas values")


class CrossGranularityProjectionError(Exception):
    def __init__(self, field: str, values: list[str]):
        self.field = field
        self.values = values
        super().__init__(f"projections span multiple {field} values")


class InvalidProjectionError(Exception):
    pass


class MirrorProjectionFunctionTableMissingError(Exception):
    pass


class MirrorPersistError(Exception):
    pass


@dataclass
class ProjectionToFunctionsResult:
    run_id: uuid.UUID | None = None
    item_id: uuid.UUID | None = None
    task_type: str = LlmTaskType.projection_to_functions
    provider: str | None = None
    model_name: str | None = None
    status: str | None = None
    projection_count: int = 0
    skipped_projection_count: int = 0
    circuit_context_count: int = 0
    function_count: int = 0
    mirror_projection_function_created_count: int = 0
    mirror_projection_function_skipped_duplicate_count: int = 0
    triple_created_count: int = 0
    evidence_created_count: int = 0
    dry_run: bool = False
    system_prompt: str | None = None
    user_prompt: str | None = None
    warnings: list[str] = field(default_factory=list)


def _resolve_template(template_key: str):
    tpl = DEFAULT_TEMPLATES.get(template_key)
    if tpl is None:
        tpl = DEFAULT_TEMPLATES[PROJECTION_TO_FUNCTIONS_TEMPLATE_KEY]
    return tpl


def _clamp_confidence(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return None


def _region_label(c: CandidateBrainRegion | None, fallback_id: str | None = None) -> str:
    if c:
        return c.en_name or c.cn_name or c.std_name or c.raw_name or str(c.id)
    return fallback_id or "unknown"


def _homogeneous_field(projections: list[MirrorRegionConnection], attr: str) -> Any | None:
    values = {getattr(p, attr) for p in projections}
    if len(values) == 1:
        return next(iter(values))
    return None


def validate_projections_homogeneous(projections: list[MirrorRegionConnection]) -> None:
    if not projections:
        raise EmptyProjectionsError()

    for p in projections:
        if not p.source_atlas:
            raise InvalidProjectionError(f"projection {p.id} missing source_atlas")
        if not p.granularity_level:
            raise InvalidProjectionError(f"projection {p.id} missing granularity_level")

    atlases = {p.source_atlas for p in projections}
    if len(atlases) > 1:
        raise CrossAtlasProjectionError(sorted(atlases))

    levels = {p.granularity_level for p in projections}
    if len(levels) > 1:
        raise CrossGranularityProjectionError("granularity_level", sorted(levels))

    families = {p.granularity_family for p in projections}
    if len(families) > 1:
        raise CrossGranularityProjectionError("granularity_family", sorted(families))


def _serialize_projection(
    p: MirrorRegionConnection,
    candidate_map: dict[uuid.UUID, CandidateBrainRegion],
    *,
    include_region_context: bool,
) -> dict[str, Any]:
    src_id = p.source_region_candidate_id
    tgt_id = p.target_region_candidate_id
    src_c = candidate_map.get(src_id) if src_id else None
    tgt_c = candidate_map.get(tgt_id) if tgt_id else None
    row: dict[str, Any] = {
        "projection_id": str(p.id),
        "source_region_candidate_id": str(src_id) if src_id else None,
        "target_region_candidate_id": str(tgt_id) if tgt_id else None,
        "connection_type": p.connection_type,
        "projection_type": p.connection_type,
        "directionality": p.directionality,
        "strength": p.strength,
        "modality": p.modality,
        "confidence": float(p.confidence) if p.confidence is not None else None,
        "evidence_text": p.evidence_text,
        "uncertainty_reason": p.uncertainty_reason,
        "source_atlas": p.source_atlas,
        "granularity_level": p.granularity_level,
        "granularity_family": p.granularity_family,
    }
    if include_region_context:
        row["source_region_en_name"] = src_c.en_name if src_c else None
        row["source_region_cn_name"] = src_c.cn_name if src_c else None
        row["target_region_en_name"] = tgt_c.en_name if tgt_c else None
        row["target_region_cn_name"] = tgt_c.cn_name if tgt_c else None
    return row


async def load_region_map_for_projections(
    session: AsyncSession,
    projections: list[MirrorRegionConnection],
) -> dict[uuid.UUID, CandidateBrainRegion]:
    out: dict[uuid.UUID, CandidateBrainRegion] = {}
    for p in projections:
        for rid in (p.source_region_candidate_id, p.target_region_candidate_id):
            if rid and rid not in out:
                cand = await session.get(CandidateBrainRegion, rid)
                if cand:
                    out[rid] = cand
    return out


async def load_circuit_context(
    session: AsyncSession,
    projections: list[MirrorRegionConnection],
) -> list[dict[str, Any]]:
    first = projections[0]
    context_rows: list[dict[str, Any]] = []
    for p in projections:
        memberships, _ = await mirror_macro_clinical_service.list_circuit_projection_memberships(
            session,
            projection_id=p.id,
            source_atlas=first.source_atlas,
            granularity_level=first.granularity_level,
            granularity_family=first.granularity_family,
            limit=50,
            offset=0,
        )
        for m in memberships:
            circuit = await session.get(MirrorRegionCircuit, m.circuit_id)
            source_step = await session.get(MirrorCircuitStep, m.source_step_id) if m.source_step_id else None
            target_step = await session.get(MirrorCircuitStep, m.target_step_id) if m.target_step_id else None
            context_rows.append({
                "membership_id": str(m.id),
                "projection_id": str(p.id),
                "circuit_id": str(m.circuit_id),
                "circuit_name": circuit.circuit_name if circuit else None,
                "circuit_type": circuit.circuit_type if circuit else None,
                "function_association": circuit.function_association if circuit else None,
                "source_step_id": str(m.source_step_id) if m.source_step_id else None,
                "target_step_id": str(m.target_step_id) if m.target_step_id else None,
                "source_step_order": source_step.step_order if source_step else None,
                "target_step_order": target_step.step_order if target_step else None,
                "role_in_circuit": m.role_in_circuit,
                "verification_status": m.verification_status,
                "membership_confidence": float(m.confidence) if m.confidence is not None else None,
            })
    return context_rows


def build_projection_to_functions_prompt(
    projections: list[MirrorRegionConnection],
    candidate_map: dict[uuid.UUID, CandidateBrainRegion],
    circuit_context: list[dict[str, Any]],
    *,
    template_key: str = PROJECTION_TO_FUNCTIONS_TEMPLATE_KEY,
    max_functions_per_projection: int = DEFAULT_MAX_FUNCTIONS_PER_PROJECTION,
    include_region_context: bool = True,
) -> tuple[str, str, dict[str, Any]]:
    tpl = _resolve_template(template_key)
    first = projections[0]
    projections_payload = [
        _serialize_projection(p, candidate_map, include_region_context=include_region_context)
        for p in projections
    ]
    projections_json = json.dumps(projections_payload, ensure_ascii=False, indent=2)
    circuit_context_json = json.dumps(circuit_context, ensure_ascii=False, indent=2)
    values = {
        "source_atlas": first.source_atlas,
        "granularity_level": first.granularity_level,
        "granularity_family": first.granularity_family or "",
        "max_functions_per_projection": str(max_functions_per_projection),
        "projections_json": projections_json,
        "circuit_context_json": circuit_context_json,
    }
    user_prompt = render_user_prompt(tpl, values)
    prompt_json = {
        "template_key": tpl.template_key,
        "prompt_display_name": prompt_display_name(tpl.template_key),
        "version": tpl.version,
        "system_prompt": tpl.system_prompt,
        "user_prompt": user_prompt,
        "projections_json": projections_json,
        "circuit_context_json": circuit_context_json,
        "max_functions_per_projection": max_functions_per_projection,
    }
    return tpl.system_prompt, user_prompt, prompt_json


def parse_projection_to_functions_response(raw_text: str) -> dict[str, Any]:
    return parse_llm_json_response(raw_text)


def normalize_projection_function_candidates(
    parsed: dict[str, Any],
    *,
    allowed_projection_ids: set[uuid.UUID],
    max_functions_per_projection: int = DEFAULT_MAX_FUNCTIONS_PER_PROJECTION,
    allowed_categories: frozenset[str] | None = None,
    allowed_relation_types: frozenset[str] | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    categories = (
        allowed_categories
        if allowed_categories is not None
        else get_vocab_codes("category")
    )
    relations = (
        allowed_relation_types
        if allowed_relation_types is not None
        else get_vocab_codes("relation_type")
    )
    warnings: list[str] = []
    raw_functions = parsed.get("projection_functions")
    if raw_functions is None:
        return [], ["projection_functions array missing; treating as empty"]
    if not isinstance(raw_functions, list):
        raise ValueError("projection_functions must be an array")

    per_projection_count: dict[str, int] = defaultdict(int)
    seen_keys: set[tuple[str, str, str, str]] = set()
    normalized: list[dict[str, Any]] = []

    for idx, fn in enumerate(raw_functions):
        if not isinstance(fn, dict):
            warnings.append(f"projection_function[{idx}] skipped: not an object")
            continue
        try:
            projection_id = uuid.UUID(str(fn.get("projection_id")))
        except (ValueError, TypeError, AttributeError):
            warnings.append(f"projection_function[{idx}] skipped: invalid projection_id")
            continue
        if projection_id not in allowed_projection_ids:
            warnings.append(f"projection_function[{idx}] skipped: projection not in input set")
            continue

        function_term = str(
            fn.get("function_term")
            or fn.get("function_term_en")
            or fn.get("function_term_cn")
            or ""
        ).strip()
        if not function_term:
            warnings.append(f"projection_function[{idx}] skipped: empty function_term")
            continue

        pid = str(projection_id)
        if per_projection_count[pid] >= max_functions_per_projection:
            warnings.append(
                f"projection_function[{idx}] note: exceeds max_functions_per_projection "
                f"({max_functions_per_projection}); still saving"
            )

        category_raw = fn.get("function_category") or fn.get("function_domain")
        category, category_ok = _normalize_category(category_raw, categories)
        if not category_ok and category_raw is not None and str(category_raw).strip():
            warnings.append(f"projection_function[{idx}] function_category coerced to unknown")

        relation_raw = fn.get("relation_type") or fn.get("function_role")
        relation, relation_ok = _normalize_relation(relation_raw, relations)
        if not relation_ok and relation_raw is not None and str(relation_raw).strip():
            warnings.append(f"projection_function[{idx}] relation_type coerced to unknown")

        term_key = function_term.lower().strip()
        dedup_key = (pid, term_key, category, relation)
        if dedup_key in seen_keys:
            warnings.append(f"projection_function[{idx}] skipped: duplicate within LLM output")
            continue
        seen_keys.add(dedup_key)

        evidence_text = fn.get("evidence_text")
        if not evidence_text:
            warnings.append(f"projection_function[{idx}] warning: evidence_text empty")

        per_projection_count[pid] += 1
        normalized.append({
            "projection_id": pid,
            "function_term": function_term,
            "function_term_key": term_key,
            "function_term_cn": fn.get("function_term_cn"),
            "function_domain": fn.get("function_domain") or fn.get("function_category"),
            "function_role": fn.get("function_role") or fn.get("relation_type"),
            "effect_type": fn.get("effect_type") or "unknown",
            "function_category": category,
            "relation_type": relation,
            "confidence": _clamp_confidence(fn.get("confidence") or fn.get("confidence_score")),
            "evidence_text": evidence_text,
            "uncertainty_reason": fn.get("uncertainty_reason"),
            "raw": fn,
            "normalized_payload_json": {
                "macro_clinical_semantic_type": "projection_function",
                "source_projection_id": pid,
            },
        })
    return normalized, warnings


def projection_function_dedup_key(
    projection_id: uuid.UUID,
    function_term_key: str,
    function_category: str,
    relation_type: str,
) -> tuple[str, str, str, str]:
    return str(projection_id), function_term_key, function_category, relation_type


async def _projection_function_exists(
    session: AsyncSession,
    *,
    projection_id: uuid.UUID,
    function_term_key: str,
    function_category: str,
    relation_type: str,
    resource_id: uuid.UUID | None,
    batch_id: uuid.UUID | None,
    source_atlas: str,
    granularity_level: str,
) -> bool:
    blocked = {MirrorPromotionStatus.failed, MirrorPromotionStatus.blocked}
    q = select(MirrorProjectionFunction.id).where(
        MirrorProjectionFunction.projection_id == projection_id,
        MirrorProjectionFunction.function_category == function_category,
        MirrorProjectionFunction.relation_type == relation_type,
        MirrorProjectionFunction.source_atlas == source_atlas,
        MirrorProjectionFunction.granularity_level == granularity_level,
        MirrorProjectionFunction.promotion_status.notin_(blocked),
        MirrorProjectionFunction.review_status != MirrorReviewStatus.rejected,
        MirrorProjectionFunction.mirror_status != MirrorStatus.superseded,
        func.lower(MirrorProjectionFunction.function_term) == function_term_key,
    )
    if resource_id:
        q = q.where(MirrorProjectionFunction.resource_id == resource_id)
    if batch_id:
        q = q.where(MirrorProjectionFunction.batch_id == batch_id)
    return (await session.execute(q.limit(1))).scalar_one_or_none() is not None


def _projection_label(
    projection: MirrorRegionConnection,
    candidate_map: dict[uuid.UUID, CandidateBrainRegion],
) -> str:
    src_c = candidate_map.get(projection.source_region_candidate_id) if projection.source_region_candidate_id else None
    tgt_c = candidate_map.get(projection.target_region_candidate_id) if projection.target_region_candidate_id else None
    src_l = _region_label(src_c, str(projection.source_region_candidate_id))
    tgt_l = _region_label(tgt_c, str(projection.target_region_candidate_id))
    return f"{src_l} -> {tgt_l} ({projection.connection_type})"


async def create_projection_function_triples(
    session: AsyncSession,
    *,
    run: LlmExtractionRun,
    item: LlmExtractionItem,
    projection: MirrorRegionConnection,
    projection_function: MirrorProjectionFunction,
    fn: dict[str, Any],
    candidate_map: dict[uuid.UUID, CandidateBrainRegion],
) -> int:
    relation = fn["relation_type"]
    predicate = RELATION_TO_PREDICATE.get(relation, "associated_with_function")
    label = _projection_label(projection, candidate_map)
    triple_payload = MirrorKgTripleCreate(
        subject_type=TripleSubjectType.connection,
        subject_id=projection.id,
        subject_label=label,
        predicate=predicate,
        object_type=TripleObjectType.function,
        object_id=None,
        object_label=fn["function_term"],
        triple_scope=TripleScope.same_granularity,
        resource_id=projection.resource_id,
        batch_id=projection.batch_id,
        llm_run_id=run.id,
        llm_item_id=item.id,
        source_mirror_connection_id=projection.id,
        granularity_level=projection.granularity_level,
        granularity_family=projection.granularity_family,
        source_atlas=projection.source_atlas,
        source_version=projection.source_version,
        confidence=fn.get("confidence"),
        evidence_text=fn.get("evidence_text"),
        uncertainty_reason=fn.get("uncertainty_reason"),
        mirror_status=MirrorStatus.llm_suggested,
        review_status=MirrorReviewStatus.pending,
        promotion_status=MirrorPromotionStatus.not_promoted,
        raw_payload_json={"projection_function": fn},
        normalized_payload_json={"predicate": predicate, "function_term": fn["function_term"]},
    )
    await mirror_kg_service.create_mirror_triple(session, triple_payload)
    return 1


async def create_projection_function_evidence(
    *,
    create_evidence: bool,
    fn: dict[str, Any],
    warnings: list[str],
) -> int:
    if not create_evidence:
        return 0
    if fn.get("evidence_text"):
        if "PROJECTION_FUNCTION_EVIDENCE_STORED_ON_OBJECT_ONLY" not in warnings:
            warnings.append("PROJECTION_FUNCTION_EVIDENCE_STORED_ON_OBJECT_ONLY")
    return 0


async def persist_projection_functions(
    session: AsyncSession,
    *,
    run: LlmExtractionRun,
    item: LlmExtractionItem,
    functions: list[dict[str, Any]],
    projection_map: dict[uuid.UUID, MirrorRegionConnection],
    candidate_map: dict[uuid.UUID, CandidateBrainRegion],
    create_triples: bool,
    create_evidence: bool,
    session_seen: set[tuple[str, str, str, str]] | None = None,
    composite_workflow_run_id: uuid.UUID | None = None,
    workflow_step_key: str | None = None,
) -> tuple[int, int, int, int, list[str]]:
    created = skipped = triples = evidence = 0
    warnings: list[str] = []
    seen = session_seen or set()
    created_pfs: list[MirrorProjectionFunction] = []

    for fn in functions:
        if composite_workflow_run_id and is_cancelling(composite_workflow_run_id):
            warnings.append("Mirror persist skipped — workflow cancelled")
            break
        projection_id = uuid.UUID(fn["projection_id"])
        projection = projection_map.get(projection_id)
        if projection is None:
            warnings.append(f"projection {projection_id} missing during persist; skipped")
            continue

        term_key = fn["function_term_key"]
        category = fn["function_category"]
        relation = fn["relation_type"]
        key = projection_function_dedup_key(projection_id, term_key, category, relation)
        if key in seen:
            skipped += 1
            warnings.append(f"EXISTING_PROJECTION_FUNCTION_SKIPPED: duplicate in session for {projection_id}")
            continue
        if await _projection_function_exists(
            session,
            projection_id=projection_id,
            function_term_key=term_key,
            function_category=category,
            relation_type=relation,
            resource_id=projection.resource_id,
            batch_id=projection.batch_id,
            source_atlas=projection.source_atlas,
            granularity_level=projection.granularity_level,
        ):
            skipped += 1
            seen.add(key)
            warnings.append(f"EXISTING_PROJECTION_FUNCTION_SKIPPED: {projection_id} / {fn['function_term']}")
            continue

        raw_payload = tag_raw_payload(
            fn.get("raw") or fn,
            workflow_run_id=composite_workflow_run_id,
            step_key=workflow_step_key,
        ) if composite_workflow_run_id else (fn.get("raw") or fn)
        normalized = fn.get("normalized_payload_json") or {
            "macro_clinical_semantic_type": "projection_function",
            "source_projection_id": str(projection_id),
        }
        if composite_workflow_run_id:
            normalized = tag_raw_payload(
                normalized,
                workflow_run_id=composite_workflow_run_id,
                step_key=workflow_step_key,
            )
        payload = MirrorProjectionFunctionCreate(
            projection_id=projection_id,
            resource_id=projection.resource_id,
            batch_id=projection.batch_id,
            llm_run_id=run.id,
            llm_item_id=item.id,
            granularity_level=projection.granularity_level,
            granularity_family=projection.granularity_family,
            source_atlas=projection.source_atlas,
            source_version=projection.source_version,
            function_term=fn["function_term"],
            function_term_cn=fn.get("function_term_cn"),
            function_domain=fn.get("function_domain"),
            function_role=fn.get("function_role"),
            effect_type=fn.get("effect_type") or "unknown",
            function_category=category,
            relation_type=relation,
            confidence=fn.get("confidence"),
            evidence_text=fn.get("evidence_text"),
            uncertainty_reason=fn.get("uncertainty_reason"),
            raw_payload_json=raw_payload,
            normalized_payload_json=normalized,
        )
        try:
            mirror_fn = await mirror_macro_clinical_service.create_projection_function(session, payload)
        except Exception as exc:
            raise MirrorPersistError(f"projection_function persist failed: {exc}") from exc
        created += 1
        created_pfs.append(mirror_fn)
        seen.add(key)

        if create_triples:
            triples += await create_projection_function_triples(
                session,
                run=run,
                item=item,
                projection=projection,
                projection_function=mirror_fn,
                fn=fn,
                candidate_map=candidate_map,
            )

        if create_evidence and fn.get("evidence_text"):
            evidence += await create_projection_function_evidence(
                create_evidence=create_evidence,
                fn=fn,
                warnings=warnings,
            )

    await ground_written_records(
        session,
        target_type="projection_function",
        rows=created_pfs,
        created_by="extraction",
    )
    return created, skipped, triples, evidence, warnings


async def run_projection_to_functions_extraction(
    session: AsyncSession,
    *,
    provider_name: str,
    model_name: str | None,
    projection_ids: list[uuid.UUID],
    prompt_template_key: str = PROJECTION_TO_FUNCTIONS_TEMPLATE_KEY,
    temperature: float = 0.2,
    max_tokens: int = 12000,
    dry_run: bool = False,
    max_functions_per_projection: int = DEFAULT_MAX_FUNCTIONS_PER_PROJECTION,
    include_circuit_context: bool = True,
    include_region_context: bool = True,
    create_mirror_records: bool = True,
    create_triples: bool = True,
    create_evidence: bool = True,
    composite_workflow_run_id: uuid.UUID | None = None,
    workflow_step_key: str | None = None,
) -> ProjectionToFunctionsResult:
    if not projection_ids:
        raise EmptyProjectionsError()
    if len(projection_ids) > MAX_PROJECTIONS:
        raise TooManyProjectionsError(len(projection_ids), MAX_PROJECTIONS)
    await refresh_vocab_cache(session, ["category", "relation_type"])

    provider_key = provider_name.lower()
    if provider_key == "deepseek":
        cfg = get_deepseek_runtime_config()
        resolved_model = model_name or cfg.default_model
    elif provider_key == "kimi":
        cfg = get_kimi_runtime_config()
        resolved_model = model_name or cfg.default_model
    else:
        raise UnknownProviderError(provider_name)

    if not dry_run and not cfg.api_key.strip():
        raise ProviderNotConfiguredServiceError(
            provider_key, f"provider is not configured: {provider_key}"
        )

    projections: list[MirrorRegionConnection] = []
    for pid in projection_ids:
        proj = await session.get(MirrorRegionConnection, pid)
        if proj is None:
            raise ProjectionNotFoundError(str(pid))
        projections.append(proj)

    validate_projections_homogeneous(projections)

    all_warnings: list[str] = []
    original_count = len(projections)
    existing_stmt = (
        select(MirrorProjectionFunction.projection_id).where(
            MirrorProjectionFunction.projection_id.in_([p.id for p in projections])
        )
    )
    existing_rows = (await session.execute(existing_stmt)).scalars().all()
    existing_ids = set(existing_rows)
    skipped_existing = original_count - len(projections)
    if existing_ids:
        projections = [p for p in projections if p.id not in existing_ids]
        skipped_existing = original_count - len(projections)
        all_warnings.append(
            f"{skipped_existing} projection(s) skipped: functions already exist"
        )
    if not projections:
        return ProjectionToFunctionsResult(
            task_type=LlmTaskType.projection_to_functions,
            projection_count=original_count,
            skipped_projection_count=original_count,
            status=LlmRunStatus.succeeded,
            warnings=list(all_warnings),
        )

    for p in projections:
        if not p.source_region_candidate_id or not p.target_region_candidate_id:
            all_warnings.append(
                f"projection {p.id} missing source/target region; LLM context may be incomplete"
            )

    candidate_map: dict[uuid.UUID, CandidateBrainRegion] = {}
    if include_region_context:
        candidate_map = await load_region_map_for_projections(session, projections)

    circuit_context: list[dict[str, Any]] = []
    if include_circuit_context:
        circuit_context = await load_circuit_context(session, projections)

    system_prompt, user_prompt, prompt_json = build_projection_to_functions_prompt(
        projections,
        candidate_map,
        circuit_context,
        template_key=prompt_template_key,
        max_functions_per_projection=max_functions_per_projection,
        include_region_context=include_region_context,
    )

    result = ProjectionToFunctionsResult(
        projection_count=len(projections),
        skipped_projection_count=skipped_existing,
        circuit_context_count=len(circuit_context),
        dry_run=dry_run,
        provider=provider_key,
        model_name=resolved_model,
        warnings=list(all_warnings),
    )

    if dry_run:
        result.system_prompt = system_prompt
        result.user_prompt = user_prompt
        return result

    first = projections[0]
    now = datetime.now(timezone.utc)
    run = LlmExtractionRun(
        task_type=LlmTaskType.projection_to_functions,
        provider=provider_key,
        model_name=resolved_model,
        prompt_template_key=prompt_template_key,
        prompt_version=_resolve_template(prompt_template_key).version,
        scope_type=LlmScopeType.manual_selection,
        scope_json={
            "projection_ids": [str(p.id) for p in projections],
            "max_functions_per_projection": max_functions_per_projection,
            "create_mirror_records": create_mirror_records,
            "create_triples": create_triples,
            "create_evidence": create_evidence,
            "include_circuit_context": include_circuit_context,
            "include_region_context": include_region_context,
            **({"composite_workflow_run_id": str(composite_workflow_run_id)} if composite_workflow_run_id else {}),
        },
        resource_id=_homogeneous_field(projections, "resource_id"),
        batch_id=_homogeneous_field(projections, "batch_id"),
        granularity_level=first.granularity_level,
        granularity_family=first.granularity_family,
        source_atlas=first.source_atlas,
        source_version=_homogeneous_field(projections, "source_version"),
        status=LlmRunStatus.running,
        input_count=len(projections),
        temperature=temperature,
        max_tokens=max_tokens,
        started_at=now,
    )
    session.add(run)
    await session.flush()

    item = LlmExtractionItem(
        run_id=run.id,
        candidate_id=None,
        resource_id=run.resource_id,
        batch_id=run.batch_id,
        task_type=LlmTaskType.projection_to_functions,
        item_index=0,
        input_json={
            "projections_json": prompt_json.get("projections_json"),
            "circuit_context_json": prompt_json.get("circuit_context_json"),
            "projection_ids": [str(p.id) for p in projections],
        },
        prompt_json=prompt_json,
        status=LlmItemStatus.running,
    )
    session.add(item)
    await session.flush()

    if composite_workflow_run_id and is_cancelling(composite_workflow_run_id):
        run.status = LlmRunStatus.cancelled
        item.status = LlmItemStatus.skipped
        result.status = LlmRunStatus.cancelled
        result.run_id = run.id
        result.item_id = item.id
        result.warnings.append("Workflow cancelled before provider call")
        await session.commit()
        return result

    provider = get_llm_provider(provider_key)
    # Retry once on transport/parse failure: flash sometimes returns reasoning
    # text instead of JSON. The retry drops json_mode and appends a hard
    # "JSON only" instruction to stop chain-of-thought output.
    max_provider_attempts = 2
    response = None
    for attempt in range(max_provider_attempts):
        if attempt == 0:
            response = await provider.complete_json(
                model=resolved_model,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        else:
            retry_user_prompt = (
                user_prompt
                + "\n\nIMPORTANT: Respond with ONLY the raw JSON object "
                + 'matching the schema. Do NOT include any reasoning, analysis, '
                + "explanation, or text outside the JSON."
            )
            text_result = await provider.complete_text(
                model=resolved_model,
                system_prompt=system_prompt,
                user_prompt=retry_user_prompt,
                temperature=temperature + 0.1,
                max_tokens=max_tokens,
                json_mode=False,
            )
            response = LlmProviderResponse(
                provider=text_result.provider,
                model=text_result.model,
                raw_text=text_result.raw_text or "",
                parsed_json=None,
                usage=text_result.usage,
                finish_reason=text_result.finish_reason,
                request_payload_redacted=text_result.request_payload_redacted,
                response_payload=text_result.response_payload,
                latency_ms=text_result.latency_ms,
                error_message=text_result.error,
                transport_ok=text_result.transport_ok,
                response_format=text_result.response_format,
            )
        raw_text = response.raw_text or ""
        if response.parsed_json is None and raw_text:
            try:
                response.parsed_json = parse_projection_to_functions_response(raw_text)
            except (LlmJsonParseError, ValueError):
                response.parsed_json = None
        retry_needed = (
            response.error_message is not None
            or response.parsed_json is None
            or not isinstance(response.parsed_json, dict)
            or not response.parsed_json.get("projection_functions")
        )
        if not retry_needed:
            break
        if attempt == 0:
            all_warnings.append(
                "retry after failed provider attempt: "
                f"{response.error_message or 'empty/no functions'}"
            )

    if composite_workflow_run_id and is_cancelling(composite_workflow_run_id):
        run.status = LlmRunStatus.cancelled
        item.status = LlmItemStatus.skipped
        result.status = LlmRunStatus.cancelled
        result.run_id = run.id
        result.item_id = item.id
        result.warnings.append("late_provider_response_ignored")
        await session.commit()
        return result

    item.raw_response_text = response.raw_text or None
    run.request_payload_redacted = response.request_payload_redacted
    run.usage_json = response.usage.as_dict() if response.usage else {}

    normalized_functions: list[dict[str, Any]] = []

    preview = raw_response_preview(response.raw_text or "")
    run.scope_json = {**(run.scope_json or {}), "raw_response_preview": preview}

    if response.error_message:
        # Transport-level failure (HTTP/timeout/network).
        item.status = LlmItemStatus.failed
        item.error_message = response.error_message
        apply_persistent_run_status(run, LlmRunStatus.failed_provider_error)
        run.error_count = 1
    elif response.parsed_json is None:
        try:
            parsed = parse_projection_to_functions_response(response.raw_text or "")
        except LlmJsonParseError as exc:
            item.status = LlmItemStatus.failed
            item.error_message = f"failed to parse model JSON: {exc}"
            apply_persistent_run_status(
                run,
                LlmRunStatus.failed_parse_error,
                extra_scope={"raw_response_preview": exc.preview or preview},
            )
            run.error_count = 1
            parsed = None
        except Exception as exc:  # noqa: BLE001 - any parser failure is a parse error, not transport
            item.status = LlmItemStatus.failed
            item.error_message = f"failed to parse model JSON: {exc}"
            apply_persistent_run_status(run, LlmRunStatus.failed_parse_error)
            run.error_count = 1
            parsed = None
        if parsed is not None:
            response.parsed_json = parsed

    if response.parsed_json is not None and item.status != LlmItemStatus.failed:
        item.parsed_response_json = response.parsed_json
        try:
            normalized_functions, norm_warnings = normalize_projection_function_candidates(
                response.parsed_json,
                allowed_projection_ids={p.id for p in projections},
                max_functions_per_projection=max_functions_per_projection,
            )
            all_warnings.extend(norm_warnings)
        except ValueError as exc:
            # JSON parsed but did not match schema → parse/schema error, not transport.
            item.status = LlmItemStatus.failed
            item.error_message = str(exc)
            apply_persistent_run_status(run, LlmRunStatus.failed_parse_error)
            run.error_count = 1
            normalized_functions = []

    if item.status != LlmItemStatus.failed:
        item.normalized_output_json = {"projection_functions": normalized_functions}
        confidences = [f["confidence"] for f in normalized_functions if f.get("confidence") is not None]
        if confidences:
            item.confidence = sum(confidences) / len(confidences)
        evidence_parts = [str(f["evidence_text"]) for f in normalized_functions if f.get("evidence_text")]
        if evidence_parts:
            item.evidence_text = "; ".join(evidence_parts[:5])
        item.status = LlmItemStatus.succeeded if normalized_functions else LlmItemStatus.needs_review
        run.output_count = len(normalized_functions)
        apply_persistent_run_status(run, LlmRunStatus.succeeded)

        projection_map = {p.id: p for p in projections}
        if create_mirror_records and normalized_functions:
            if composite_workflow_run_id and is_cancelling(composite_workflow_run_id):
                all_warnings.append("Mirror persist skipped — workflow cancelled")
            else:
                try:
                    pf, skip, tr, ev, pw = await persist_projection_functions(
                        session,
                        run=run,
                        item=item,
                        functions=normalized_functions,
                        projection_map=projection_map,
                        candidate_map=candidate_map,
                        create_triples=create_triples,
                        create_evidence=create_evidence,
                        composite_workflow_run_id=composite_workflow_run_id,
                        workflow_step_key=workflow_step_key,
                    )
                    result.mirror_projection_function_created_count = pf
                    result.mirror_projection_function_skipped_duplicate_count = skip
                    result.triple_created_count = tr
                    result.evidence_created_count = ev
                    all_warnings.extend(pw)
                except MirrorPersistError as exc:
                    run.status = LlmRunStatus.partially_succeeded
                    run.error_message = str(exc)
                    all_warnings.append(str(exc))
        elif normalized_functions and not create_mirror_records:
            pass

    run.finished_at = datetime.now(timezone.utc)
    result.run_id = run.id
    result.item_id = item.id
    result.status = (run.scope_json or {}).get("outcome") or run.status
    result.function_count = len(normalized_functions)
    result.warnings = all_warnings

    await session.commit()
    await session.refresh(run)
    await session.refresh(item)
    return result


async def run_projection_function_extraction_batch(
    *,
    projection_ids: list[uuid.UUID],
    provider_name: str,
    model_name: str | None,
    projections_per_pack: int = 50,
    concurrency: int = 4,
    **kwargs: Any,
) -> dict[str, Any]:
    """Chunked, concurrent projection-to-function extraction.

    Each chunk runs in its own DB session (safe for parallel asyncio tasks),
    calls the standard single-group service, and commits independently, so a
    failure in one chunk never rolls back completed chunks.
    """
    from app.database import AsyncSessionLocal

    if AsyncSessionLocal is None:
        raise RuntimeError("AsyncSessionLocal unavailable")
    if not projection_ids:
        raise EmptyProjectionsError()

    pack_size = max(1, min(200, projections_per_pack))
    workers = max(1, min(8, concurrency))
    chunks = [
        projection_ids[i : i + pack_size]
        for i in range(0, len(projection_ids), pack_size)
    ]
    semaphore = asyncio.Semaphore(workers)
    progress = {"done": 0, "created": 0, "failed": 0}

    async def _run_chunk(
        chunk: list[uuid.UUID],
    ) -> tuple[ProjectionToFunctionsResult | None, str | None]:
        async with semaphore:
            async with AsyncSessionLocal() as chunk_session:
                try:
                    res = await run_projection_to_functions_extraction(
                        chunk_session,
                        provider_name=provider_name,
                        model_name=model_name,
                        projection_ids=chunk,
                        **kwargs,
                    )
                except Exception as exc:  # noqa: BLE001 - one bad chunk must not kill the batch
                    progress["done"] += 1
                    progress["failed"] += 1
                    if progress["done"] % 25 == 0 or progress["done"] == len(chunks):
                        logger.info(
                            "[projection-batch] %s/%s chunks done, created=%s failed=%s",
                            progress["done"], len(chunks), progress["created"], progress["failed"],
                        )
                    return None, f"chunk failed ({len(chunk)} projections): {exc}"
                progress["done"] += 1
                progress["created"] += res.mirror_projection_function_created_count or 0
                if progress["done"] % 25 == 0 or progress["done"] == len(chunks):
                    logger.info(
                        "[projection-batch] %s/%s chunks done, created=%s failed=%s",
                        progress["done"], len(chunks), progress["created"], progress["failed"],
                    )
                return res, None

    results = await asyncio.gather(*(_run_chunk(c) for c in chunks))

    summary: dict[str, Any] = {
        "requested_projection_count": len(projection_ids),
        "chunk_count": len(chunks),
        "concurrency": workers,
        "projections_per_pack": pack_size,
        "created_count": 0,
        "skipped_duplicate_count": 0,
        "skipped_existing_count": 0,
        "triple_created_count": 0,
        "evidence_created_count": 0,
        "failed_chunk_count": 0,
        "errors": [],
        "warnings": [],
    }
    for res, err in results:
        if err is not None or res is None:
            summary["failed_chunk_count"] += 1
            if err:
                summary["errors"].append(err)
            continue
        summary["created_count"] += res.mirror_projection_function_created_count or 0
        summary["skipped_duplicate_count"] += (
            res.mirror_projection_function_skipped_duplicate_count or 0
        )
        summary["skipped_existing_count"] += res.skipped_projection_count or 0
        summary["triple_created_count"] += res.triple_created_count or 0
        summary["evidence_created_count"] += res.evidence_created_count or 0
        summary["warnings"].extend(res.warnings or [])
    return summary
