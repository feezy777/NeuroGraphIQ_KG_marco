"""Unified Evidence Target Adapter.

Maps any supported knowledge object (connection / projection_function / circuit /
circuit_function / circuit_step / region_function) into a single Evidence Target DTO
that search, retrieval, and DeepSeek judgment consume. Nothing else in the evidence
chain should reach into raw object rows directly.
"""

from __future__ import annotations

import re
import uuid

from sqlalchemy import text
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


def _build_claim_components(target_type: str, dto: dict) -> list[dict]:
    """Unified claim components: what sub-facts must hold for this object."""
    source = dto.get("source_region") or ""
    target = dto.get("target_region") or ""
    relation = dto.get("relation") or ""
    direction = dto.get("directionality") or ""
    functions = dto.get("canonical_terms") or []
    function = functions[0] if functions else ""
    circuit = dto.get("circuit_context") or ""
    role = dto.get("relation") or ""

    def comp(component_type: str, statement: str, required: bool = True, metadata: dict | None = None) -> dict:
        return {
            "component_type": component_type,
            "statement": statement,
            "required": required,
            "metadata": metadata or {},
        }

    if target_type in ("connection", "projection"):
        src_cn = dto.get("source_region_cn") or ""
        tgt_cn = dto.get("target_region_cn") or ""
        components = [
            comp("source_region", f"源脑区为 {source}" if source else "存在确定的源脑区",
                 metadata={"name_en": source, "name_cn": src_cn} if source else {}),
            comp("target_region", f"靶脑区为 {target}" if target else "存在确定的靶脑区",
                 metadata={"name_en": target, "name_cn": tgt_cn} if target else {}),
            comp("relation", f"{source or '源'} 到 {target or '靶'} 存在 {relation or '连接'} 关系"),
        ]
        if direction:
            components.append(comp("direction", f"连接方向性为 {direction}"))
        # 功能为可选补充:有功能证据的片段标注 function,不影响连接存在性 coverage
        if function:
            components.append(
                comp("function", f"连接功能为「{function}」", required=False)
            )
        return components
    if target_type == "projection_function":
        components = [
            comp("source_region", f"源脑区为 {source}" if source else "存在确定的源脑区"),
            comp("target_region", f"靶脑区为 {target}" if target else "存在确定的靶脑区"),
            comp("relation", f"从 {source or '源'} 到 {target or '靶'} 存在投射"),
            comp("function", f"该投射具有功能「{function}」" if function else "该投射具有确定功能"),
        ]
        return [c for c in components if c["statement"]]
    if target_type == "region_function":
        return [
            comp("source_region", f"脑区为 {source}" if source else "存在确定的脑区"),
            comp("function", f"该脑区具有功能「{function}」" if function else "该脑区具有确定功能"),
        ]
    if target_type == "circuit":
        return [
            comp("circuit_identity", f"回路「{circuit or dto.get('display_name') or '?'}」存在"),
            comp(
                "context",
                f"回路类型为 {relation}" if relation else "回路类型确定",
                required=False,
            ),
        ]
    if target_type == "circuit_function":
        return [
            comp("circuit_identity", f"回路「{circuit or '?'}」存在"),
            comp("function", f"回路具有功能「{function}」" if function else "回路具有确定功能"),
        ]
    if target_type == "circuit_step":
        return [
            comp("circuit_identity", f"回路「{circuit or '?'}」存在"),
            comp("circuit_role", f"步骤角色为 {role}" if role else "步骤角色确定"),
            comp("step_order", f"步骤顺序确定", required=False),
        ]
    return []


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
        "source_region_cn": _clean(getattr(row, "source_region_name_cn", "")),
        "target_region_cn": _clean(getattr(row, "target_region_name_cn", "")),
        "canonical_terms": _join(
            [
                _clean(getattr(row, "source_region_name_en", "")),
                _clean(getattr(row, "target_region_name_en", "")),
                _clean(getattr(row, "connection_type", "")),
            ]
        ),
        "relation": "投射连接" if getattr(row, "connection_type", "") else "连接",
        "connection_type": _clean(getattr(row, "connection_type", "")),
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


async def _macro_review_target_dto(
    session: AsyncSession, target_type: str, target_id: uuid.UUID,
) -> dict | None:
    """Macro 治理审核目标 DTO(不落库,纯查询组装)。

    * existing_connection_evidence —— 证据增强任务:已有连接 + 论文新证据 + AI 判定
      (rule BLOCKED/duplicate)  ⇒ 审核语义「这篇论文能否作为该已有连接的新证据」
    * macro_candidate_connection  —— 新增连接候选人工审核
      (rule PASS + AI SUPPORTED) ⇒ 审核新增连接
    """
    ranking = (await session.execute(
        text("""\
SELECT rk.id, rk.paper_count, rk.evidence_count, rk.score, rk.priority_level,
       rs.canonical_name_en AS src, rt.canonical_name_en AS tgt,
       rk.source_region_id, rk.target_region_id, rk.candidate_pair_ids
FROM paper_connection_candidate_rankings rk
JOIN canonical_brain_regions rs ON rs.id = rk.source_region_id
JOIN canonical_brain_regions rt ON rt.id = rk.target_region_id
WHERE rk.id = :rid"""),
        {"rid": str(target_id)})).first()
    if ranking is None:
        return None
    review = (await session.execute(
        text("""SELECT decision, connection_type, direction, confidence,
                  evidence_strength, reasoning, model_name, created_at
           FROM macro_candidate_connection_llm_reviews WHERE ranking_id = :rid LIMIT 1"""),
        {"rid": str(target_id)})).first()
    rule = (await session.execute(
        text("""SELECT validation_status, duplicate_existing
           FROM macro_candidate_rule_validation_results WHERE ranking_id = :rid
           ORDER BY validation_timestamp DESC LIMIT 1"""),
        {"rid": str(target_id)})).first()
    a, b = sorted([str(ranking[7]), str(ranking[8])])
    existing = (await session.execute(
        text("""SELECT id, connection_code, confidence
           FROM final_canonical_connections
           WHERE (source_region_id = :a AND target_region_id = :b)
              OR (source_region_id = :b AND target_region_id = :a)
           LIMIT 1"""),
        {"a": a, "b": b})).first()

    dto = {
        "granularity": "macro_clinical",
        "display_name": f"{ranking[5]} → {ranking[6]}",
        "source_region": ranking[5],
        "target_region": ranking[6],
        "relation": "连接",
        "connection_type": None,
        "directionality": None,
        "existing_connection_id": str(existing[0]) if existing else None,
        "existing_connection_code": existing[1] if existing else None,
        "existing_connection_confidence": float(existing[2]) if existing and existing[2] is not None else None,
        "ranking_id": str(target_id),
        "ranking_score": float(ranking[3]) if ranking[3] is not None else None,
        "ranking_priority": ranking[4],
        "paper_count": ranking[1],
        "evidence_count": ranking[2],
        "ai_decision": review[0] if review else None,
        "ai_connection_type": review[1] if review else None,
        "ai_direction": review[2] if review else None,
        "ai_confidence": float(review[3]) if review and review[3] is not None else None,
        "ai_evidence_strength": review[4] if review else None,
        "ai_reasoning": review[5] if review else None,
        "ai_model": review[6] if review else None,
        "ai_reviewed_at": _fmt_ts(review[7]) if review else None,
        "rule_status": rule[0] if rule else None,
        "rule_duplicate_existing": rule[1] if rule else None,
        "review_kind": "enhancement" if target_type == "existing_connection_evidence" else "novel",
        "evidence_papers": [],  # 由下方 pair 查询填充
    }
    # 两端 canonical id(供前端 id 级上下文匹配)
    dto["source_region_canonical_id"] = str(ranking[7])
    dto["target_region_canonical_id"] = str(ranking[8])
    # 论文证据片段(ranking → candidate_pair_ids → paper_region_pair_candidates
    # → paper_sources;按共现质量 TOP 3;人工审核页直接展示)
    pair_ids = [str(x) for x in (ranking[9] or [])]
    if pair_ids:
        pair_rows = (await session.execute(
            text("""SELECT p.paper_id, p.evidence_sentence, p.section_name, p.cooccurrence
               FROM paper_region_pair_candidates p
               WHERE p.id = ANY(:ids)"""),
            {"ids": pair_ids})).all()
        paper_ids = list({str(r[0]) for r in pair_rows})
        paper_rows = (await session.execute(
            text("SELECT id, title, pmid FROM paper_sources WHERE id = ANY(:ids)"),
            {"ids": paper_ids})).all() if paper_ids else []
        paper_info = {str(p[0]): (p[1], p[2]) for p in paper_rows}
        q = {"same_sentence": 0, "same_section": 1, "same_paper": 2}
        evs = []
        for pid, sentence, section, cooc in pair_rows:
            evs.append({
                "paper_title": paper_info.get(str(pid), ("unknown", "unknown"))[0],
                "pmid": paper_info.get(str(pid), ("unknown", "unknown"))[1],
                "section": section or "",
                "sentence": sentence,
                "cooccurrence": cooc,
                "_q": q.get(cooc, 9),
            })
        evs.sort(key=lambda e: e["_q"])
        for e in evs:
            e.pop("_q", None)
        dto["evidence_papers"] = evs[:3]
    else:
        dto["evidence_papers"] = []
    return dto


def _fmt_ts(v) -> str | None:
    if v is None:
        return None
    if hasattr(v, "isoformat"):
        return v.isoformat()
    return str(v)


async def build_target_dto(
    session: AsyncSession, target_type: str, target_id: uuid.UUID
) -> dict:
    # Macro 治理审核目标(connection-like 组装,不落库)
    # 命名:enhancement=existing_connection_evidence;novel=macro_connection_candidate
    # (兼容历史别名 macro_candidate_connection / macro_candidate_evidence)
    if target_type in (
        "existing_connection_evidence", "macro_connection_candidate",
        "macro_candidate_connection", "macro_candidate_evidence",
    ):
        dto = await _macro_review_target_dto(session, target_type, target_id)
        if dto is None:
            raise ValueError("target not found")
        dto.update({
            "target_type": target_type,
            "target_id": str(target_id),
            "current_confidence": dto.get("existing_connection_confidence"),
            "existing_evidence": 0,
        })
        dto["claim_text"] = _build_claim("connection", dto)
        dto["structured_claim"] = {
            "target_type": target_type,
            "target_id": str(target_id),
            "source_region": dto.get("source_region") or None,
            "target_region": dto.get("target_region") or None,
            "relation": dto.get("relation") or None,
            "canonical_terms": [dto.get("source_region"), dto.get("target_region")],
        }
        dto["claim_components"] = _build_claim_components("connection", dto)
        dto["claim_version"] = CLAIM_VERSION
        return dto
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
    # Macro 治理匹配:connection 对象附带 canonical 区 id(既有 mirror→candidate→canonical FK)
    if target_type == "connection":
        await attach_canonical_region_ids(session, dto, row)
    # circuit_function / circuit_step carry circuit_id as circuit_context:
    # resolve it to the circuit name so claims read "回路「xxx」" not a UUID.
    if target_type in ("circuit_function", "circuit_step") and dto.get("circuit_context"):
        try:
            cid = uuid.UUID(str(dto["circuit_context"]))
        except (ValueError, TypeError):
            cid = None
        if cid is not None:
            circuit_row = await session.get(MirrorRegionCircuit, cid)
            if circuit_row is not None and getattr(circuit_row, "circuit_name", None):
                dto["circuit_context"] = circuit_row.circuit_name
    dto["claim_text"] = _build_claim(target_type, dto)
    dto["structured_claim"] = {
        "target_type": target_type,
        "target_id": str(target_id),
        "source_region": dto.get("source_region") or None,
        "target_region": dto.get("target_region") or None,
        "relation": dto.get("relation") or None,
        "canonical_terms": dto.get("canonical_terms") or [],
    }
    dto["claim_components"] = _build_claim_components(target_type, dto)
    dto["claim_version"] = CLAIM_VERSION
    return dto


async def attach_canonical_region_ids(
    session: AsyncSession, dto: dict, row: MirrorRegionConnection,
) -> None:
    """Macro 治理匹配:mirror connection → candidate → canonical 区 id(既有 FK 链路)。

    mirror_region_connections.source_region_candidate_id → candidate_brain_regions
    → candidate_brain_regions.canonical_region_id → canonical_brain_regions.id
    (= paper_connection_candidate_rankings 的 source/target_region_id)。

    仅命中已有 mapping(Macro96 池 96 行 candidate 有 canonical_region_id);
    未映射的对象两字段保持 null,由前端名称级回退继续。
    """
    src_cid = getattr(row, "source_region_candidate_id", None)
    tgt_cid = getattr(row, "target_region_candidate_id", None)
    from app.models.candidate import CandidateBrainRegion  # noqa: PLC0415
    from sqlalchemy import select  # noqa: PLC0415
    if src_cid is None and tgt_cid is None:
        return
    rows = (await session.execute(
        select(CandidateBrainRegion)
        .where(CandidateBrainRegion.id.in_([c for c in (src_cid, tgt_cid) if c is not None]))
    )).scalars().all()
    by_id = {str(r.id): r.canonical_region_id for r in rows}
    dto["source_region_canonical_id"] = (
        str(by_id[str(src_cid)]) if src_cid and str(src_cid) in by_id and by_id[str(src_cid)] else None
    )
    dto["target_region_canonical_id"] = (
        str(by_id[str(tgt_cid)]) if tgt_cid and str(tgt_cid) in by_id and by_id[str(tgt_cid)] else None
    )


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


async def load_synonyms_for_terms(session: AsyncSession, terms: list[str]) -> dict[str, list[str]]:
    """Load canonical term + active synonyms from the ontology registry.

    Source of truth is ontology_terms / ontology_term_synonyms — no hard-coded
    brain-region or function synonym tables are introduced.
    """
    clean = [t for t in terms if t and len(t) <= 120]
    if not clean:
        return {}
    rows = (
        await session.execute(
            text(
                "SELECT t.canonical_term_en, s.synonym_text FROM ontology_terms t "
                "JOIN ontology_term_synonyms s ON s.term_id = t.id "
                "WHERE t.status='active' AND s.status='active' "
                "AND (t.canonical_term_en = ANY(:terms) OR s.synonym_text = ANY(:terms))"
            ),
            {"terms": clean},
        )
    ).all()
    result: dict[str, list[str]] = {}
    for canonical, synonym in rows:
        result.setdefault(canonical, [canonical])
        if synonym and synonym not in result[canonical]:
            result[canonical].append(synonym)
    for term in clean:
        result.setdefault(term, [term])
    return result


async def _target_species(
    session: AsyncSession, target_type: str, target_id: uuid.UUID
) -> str | None:
    """Explicit species from atlas_resources metadata (BR1).

    Species source of truth is resource-level metadata; atlas-name string
    inference is banned (Allen_HBA is human and must never be labelled mouse).
    Returns None when the target row or its resource is missing.
    """
    model = TARGET_MODELS.get(target_type)
    if model is None:
        return None
    row = await session.get(model, target_id)
    if row is None:
        return None
    resource_id = getattr(row, "resource_id", None)
    if resource_id is None:
        return None
    species = (
        await session.execute(
            text("SELECT species FROM atlas_resources WHERE id = :rid"), {"rid": resource_id}
        )
    ).scalar_one_or_none()
    return str(species) if species else None


async def build_retrieval_context(
    session: AsyncSession,
    target_type: str,
    target_id: uuid.UUID,
    *,
    mode: str = "function",
) -> dict:
    """Build the unified retrieval context from an Evidence Target DTO + ontology.

    mode="existence" drops function terms from retrieval (regions/relation only):
    a paper may prove the object EXISTS (e.g. an anatomical projection) without
    mentioning any function. The claim itself stays unchanged.
    """
    dto = await build_target_dto(session, target_type, target_id)
    species = await _target_species(session, target_type, target_id)
    canonical = dto.get("canonical_terms") or []
    source = dto.get("source_region") or ""
    target = dto.get("target_region") or ""
    fn_terms = [t for t in canonical if t not in (source, target)]
    if mode == "existence":
        fn_terms = []
    # circuit-family rows carry no region fields: derive retrieval terms from the
    # circuit name itself (snake_case → words) minus generic words.
    if target_type in ("circuit", "circuit_function", "circuit_step"):
        name = dto.get("circuit_context") or dto.get("display_name") or ""
        name_words = [
            w for w in re.split(r"[_\-\s]+", name)
            if len(w) > 3 and w.lower() not in _GENERIC_CIRCUIT_WORDS
        ]
        fn_terms = list(dict.fromkeys(fn_terms + name_words))
    synonym_map = await load_synonyms_for_terms(
        session, [t for t in [source, target] + fn_terms if t]
    )

    def synonyms_for(term: str) -> list[str]:
        if not term:
            return []
        return [s for s in synonym_map.get(term, [term]) if s != term]

    relation = dto.get("relation") or ""
    relation_keywords: list[str] = []
    if relation:
        relation_keywords.append(relation)
    if dto.get("directionality") and dto["directionality"] not in ("unknown", ""):
        relation_keywords.append(dto["directionality"])
    connection_type = dto.get("connection_type") or ""
    if connection_type and connection_type not in ("unknown", ""):
        relation_keywords.append(connection_type)

    return {
        "claim_text": dto.get("claim_text") or "",
        "structured_claim": dto.get("structured_claim") or {},
        "claim_components": dto.get("claim_components") or [],
        "claim_version": dto.get("claim_version") or "claim_v1",
        "claim_mode": mode,
        "object_type": target_type,
        "granularity": dto.get("granularity") or "",
        "species": species,
        "source_region": source,
        "target_region": target,
        "source_region_synonyms": synonyms_for(source),
        "target_region_synonyms": synonyms_for(target),
        "function_terms": fn_terms,
        "function_synonyms": [s for t in fn_terms for s in synonyms_for(t)],
        "relation": relation,
        "relation_keywords": relation_keywords,
        "directionality": dto.get("directionality") or "",
        "circuit_context": dto.get("circuit_context") or "",
        "current_confidence": dto.get("current_confidence"),
        "existing_evidence": dto.get("existing_evidence", 0),
    }


# Connection-evidence vocabulary (mirrors paper_evidence_service.CONNECTION_EVIDENCE_TERMS):
# structural terms only — "connectivity" alone matches fMRI functional-connectivity
# papers, which are not evidence for an anatomical projection.
_CONNECTION_EVIDENCE_TERMS = [
    "projection",
    "tractography",
    "fiber",
    "tract",
    "DTI",
    "structural connectivity",
    "white matter",
    "thalamostriatal",
    "thalamo-striatal",
]

# Region synonyms papers actually use ("putamen" ⊂ striatum).
_REGION_SYNONYM_HINTS = {
    "putamen": ["striatum", "caudate putamen", "neostriatum"],
    "striatum": ["putamen"],
    "thalamus": ["thalamic"],
    "thalamic": ["thalamus"],
}


def _region_search_terms(region: str) -> list[str]:
    core = _core_region_term(region)
    terms = [region, core]
    hints = _REGION_SYNONYM_HINTS.get((core or "").lower(), [])
    return [t for t in dict.fromkeys(terms + hints) if t]

_REGION_MODIFIER_WORDS = {
    "right", "left", "proper", "superior", "inferior", "medial", "lateral",
    "anterior", "posterior", "dorsal", "ventral", "caudal", "rostral",
    "central", "deep", "superficial", "primary", "secondary", "bilateral",
    "motor", "related", "gray", "white", "intermediate",
}

_REGION_STRUCTURAL_WORDS = {
    "layer", "part", "area", "sublayer", "region", "sector", "division",
}

# Words too generic to retrieve on for circuit-name-based queries.
_GENERIC_CIRCUIT_WORDS = {
    "circuit", "pathway", "system", "sensory", "limbic", "motor",
    "medial", "lateral", "dorsal", "ventral", "related", "function",
    "area", "primary", "layer", "cortical", "posterior", "anterior",
}


def _core_region_term(region: str) -> str:
    """'right thalamus proper' → 'thalamus'; 'Agranular insular area, posterior
    part, layer 6b' → 'Agranular insular' (modifiers + structural suffixes stripped,
    numeric labels dropped, remainder trimmed to last 3 words)."""
    words = [
        w for w in re.split(r"[\s\-,\/]+", region or "")
        if w
        and len(w) > 1
        and not re.fullmatch(r"\d+[a-z]?|\d+", w)
        and w.lower() not in _REGION_MODIFIER_WORDS
        and w.lower() not in _REGION_STRUCTURAL_WORDS
    ]
    if not words:
        return (region or "").strip()
    core = " ".join(words).strip()
    parts = core.split()
    return " ".join(parts[-3:]) if len(parts) > 3 else core


async def build_search_query(
    session: AsyncSession,
    target_type: str,
    target_id: uuid.UUID,
    *,
    mode: str = "function",
    abstract_only: bool = True,
    negative: bool = False,
) -> str:
    dto = await build_target_dto(session, target_type, target_id)
    src = dto.get("source_region") or ""
    tgt = dto.get("target_region") or ""
    if mode == "existence":
        # regions only (canonical + core term + synonym hints) — no function terms
        terms = _region_search_terms(src) + _region_search_terms(tgt)
    else:
        terms = list(dto["canonical_terms"]) + _region_search_terms(src) + _region_search_terms(tgt)
        if target_type in ("connection", "projection"):
            terms += _CONNECTION_EVIDENCE_TERMS
    tokens = []
    seen: set[str] = set()
    for term in terms:
        term = (term or "").strip().strip('"')
        key = term.lower()
        if term and len(term) <= 80 and key not in seen:
            seen.add(key)
            tokens.append(f'ABSTRACT:"{term}"')
            if not abstract_only:
                tokens.append(f'BODY:"{term}"')
    # 否定向查询:否定短语用 OR 组(任一命中即可;AND 连接多个否定短语现实中无法命中)
    if negative:
        neg_group = "(" + " OR ".join(
            f'ABSTRACT:"{t}"' for t in (
                "no projection", "does not connect", "absence of connection",
                "not connected", "no connection",
            )
        ) + ")"
        tokens.append(neg_group)
    if not tokens:
        display = (dto.get("display_name") or "").strip().strip('"')
        if display:
            tokens = [f'(ABSTRACT:"{display}" OR BODY:"{display}")']
    return " AND ".join(tokens)
