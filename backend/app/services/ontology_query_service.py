"""NeuroGraphIQ Ontology Query Phase 1 — 可控、可解释的图谱自然语言查询。

设计约束（对齐项目治理链与用户规格）：
- 不重新设计数据模型、不修改已有 ontology 数据、不引入不可控 LLM 推理（纯规则分类）。
- 禁止重复写 SQL：全部查询复用 canonical_region_service / canonical_multiscale_service。
- 禁止自动猜测：实体解析七级链全部基于精确匹配；多候选/模糊只返回候选不自动选择。
- 所有结果携带 provenance（来源表 + 匹配层级），实体一律返回 canonical id。

查询流程：
    question → normalize → intent classify（5 意图规则）→ entity extract
    → resolve（Phase Q1.5 七级：cn → en → canonical_region_aliases → atlas 名
      → ontology synonym → fuzzy 候选 → unresolved）
    → handler（复用 canonical service）
    → {intent, entity, results, confidence, warnings, source_entities, entity_match_detail}
"""

from __future__ import annotations

import re
import unicodedata
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.candidate import CandidateBrainRegion
from app.models.canonical_region import CanonicalBrainRegion
from app.models.canonical_region_alias import CanonicalRegionAlias
from app.models.multiscale import AtlasRegionMapping, AtlasRegionResource
from app.models.ontology import OntologyTerm, OntologyTermSynonym
from app.services import canonical_multiscale_service as cms
from app.services import canonical_region_service as crs

# --------------------------------------------------------------------------- #
# 意图定义（规则分类，不调用 LLM）
# --------------------------------------------------------------------------- #

INTENT_REGION_CHILDREN = "region_children"
INTENT_REGION_CONNECTIONS = "region_connections"
INTENT_REGION_CIRCUITS = "region_circuits"
INTENT_REGION_FUNCTIONS = "region_functions"
INTENT_REGION_MULTISCALE = "region_multiscale"
INTENT_UNRESOLVED = "unresolved"

# 顺序即优先级：越具体的名词性意图越靠前（circuits 最具体），
# 命中即停止；多意图关键词同时出现时取首个命中的意图。
_INTENT_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (INTENT_REGION_CIRCUITS, ("回路", "环路", "环", "circuit")),
    (INTENT_REGION_MULTISCALE, ("细胞", "分子", "基因", "蛋白", "受体", "神经递质", "神经元类型")),
    (INTENT_REGION_CONNECTIONS, ("连接", "投射", "纤维", "传出", "传入", "输入", "输出", "联系", "connect")),
    (INTENT_REGION_CHILDREN, ("亚区", "子区", "子区域", "分区", "组成部分", "包含", "包括", "分为", "划分", "构成")),
    (INTENT_REGION_FUNCTIONS, ("功能", "作用")),
)

# 疑问词 / 类型名词 / 通用动词（实体名提取时剥离；顺序无关，替换为空格）
_STOP_WORDS: tuple[str, ...] = (
    "有哪些", "哪些", "是什么", "什么", "哪个", "请问", "帮我", "一下",
    "参与", "属于", "是否", "是否包含", "列出", "列举", "说说",
    "脑区", "区域", "部位", "的", "呢", "吗", "有", "是",
    "和", "与", "及", "、", "，", ",", "在", "中", "里",
)

# --------------------------------------------------------------------------- #
# Normalizer（全角→半角、空白归一、去句末标点）
# --------------------------------------------------------------------------- #


def normalize_question(question: str) -> str:
    text = unicodedata.normalize("NFKC", question)
    for full, half in (("！", "!"), ("？", "?"), ("。", "."), ("．", "."), ("…", "..")):
        text = text.replace(full, half)
    text = re.sub(r"\s+", " ", text)
    return text.strip(" \t\r\n!?.,;:。？！，、")

# --------------------------------------------------------------------------- #
# Intent Classifier（规则，无 LLM）
# --------------------------------------------------------------------------- #


def classify_intent(question: str) -> tuple[str, tuple[str, ...]]:
    """返回 (intent, 命中的关键词)。无命中 → (unresolved, ())。"""
    lowered = question.lower()
    for intent, keywords in _INTENT_RULES:
        for kw in keywords:
            if kw.lower() in lowered:
                return intent, keywords
    return INTENT_UNRESOLVED, ()


def extract_entity_name(question: str, intent_keywords: tuple[str, ...]) -> str | None:
    """剥离意图关键词 + 停用词，剩余文本作为实体名（规范化后全等匹配，不模糊猜测）。"""
    text = question
    for kw in intent_keywords:
        text = text.replace(kw, " ")
    for word in _STOP_WORDS:
        text = text.replace(word, " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip(" \t.·") or None

# --------------------------------------------------------------------------- #
# Entity Resolver（Phase Q1.5 七级链；全部全等匹配，无命中 → 模糊候选 → None）
#   1 canonical_name_cn exact → 2 canonical_name_en exact
#   → 3 canonical_region_aliases exact（含已对齐 candidate 名称）
#   → 4 atlas 原生名称 exact → 5 ontology synonym exact
#   → 6 fuzzy 候选（多候选不自动选择）→ 7 unresolved
# --------------------------------------------------------------------------- #


def _norm_name(value: str) -> str:
    """名称规范化：小写 + 去掉下划线/连字符/空格（用于全等比较）。"""
    return re.sub(r"[\s_\-/]+", "", value).lower()


# 精确命中统一为 (region, alias_text, source, confidence) 四元组，供去重/候选统一处理
Hit = tuple[CanonicalBrainRegion, str, str, float]


class RegionResolution:
    __slots__ = ("region", "matched_by", "matched_name", "alias", "source", "confidence", "candidates")

    def __init__(
        self,
        region: CanonicalBrainRegion | None,
        matched_by: str,
        matched_name: str,
        *,
        alias: str | None = None,
        source: str | None = None,
        confidence: float | None = None,
        candidates: list[dict[str, Any]] | None = None,
    ):
        self.region = region
        self.matched_by = matched_by  # canonical_name_cn | canonical_name_en | alias | synonym | fuzzy
        self.matched_name = matched_name
        self.alias = alias  # 命中的别名文本（alias/synonym 匹配时）
        self.source = source  # canonical_region | manual_curated | atlas | candidate_pool | ontology_synonym
        self.confidence = confidence  # 本次匹配置信度（None → 用 _CONFIDENCE_BY_MATCH 兜底）
        self.candidates = candidates or []  # 多候选/模糊时 [{candidate, confidence}]


async def _resolve_by_canonical_names(
    regions: list[CanonicalBrainRegion], norm: str
) -> tuple[CanonicalBrainRegion | None, str, str]:
    """优先级 1/2：canonical_name_cn → canonical_name_en 全等匹配。"""
    for r in regions:
        if r.canonical_name_cn and _norm_name(r.canonical_name_cn) == norm:
            return r, "canonical_name_cn", r.canonical_name_cn
    for r in regions:
        if r.canonical_name_en and _norm_name(r.canonical_name_en) == norm:
            return r, "canonical_name_en", r.canonical_name_en
    return None, "", ""


async def _resolve_by_region_aliases(session: AsyncSession, norm: str) -> list[Hit]:
    """优先级 3a：canonical_region_aliases（手工/本体同义词来源，source != 'atlas'）。"""
    rows = (
        await session.execute(
            select(CanonicalRegionAlias, CanonicalBrainRegion)
            .join(CanonicalBrainRegion, CanonicalBrainRegion.id == CanonicalRegionAlias.region_id)
            .where(CanonicalRegionAlias.source != "atlas")
            .where(CanonicalBrainRegion.status == "active")
        )
    ).all()
    hits: list[Hit] = []
    for alias, region in rows:
        if _norm_name(alias.alias) == norm:
            confidence = alias.confidence if alias.confidence is not None else 0.9
            hits.append((region, alias.alias, alias.source, confidence))
    return hits


async def _resolve_by_candidate_names(session: AsyncSession, norm: str) -> list[Hit]:
    """优先级 3b：已对齐 canonical 的 candidate 名称（raw/std/en/cn，可追溯才计入）。"""
    rows = (
        await session.execute(
            select(CandidateBrainRegion).where(CandidateBrainRegion.canonical_region_id.is_not(None))
        )
    ).scalars().all()
    hits: list[Hit] = []
    for row in rows:
        for field in ("raw_name", "std_name", "en_name", "cn_name"):
            value = getattr(row, field, None)
            if value and _norm_name(str(value)) == norm:
                region = await crs.get_canonical_region(session, row.canonical_region_id)
                if region is not None and region.status == "active":
                    hits.append((region, str(value), "candidate_pool", 0.9))
                break
    return hits


async def _resolve_by_atlas_alias(session: AsyncSession, norm: str) -> list[Hit]:
    """优先级 4：atlas 原生名称（实时 join atlas_region_resources + mappings，映射新增立即可查）。

    跨物种 homology 映射不参与查找（未经人工确认的异种名不成为别名）。
    """
    rows = (
        await session.execute(
            select(AtlasRegionResource, AtlasRegionMapping, CanonicalBrainRegion)
            .join(AtlasRegionMapping, AtlasRegionMapping.atlas_region_id == AtlasRegionResource.id)
            .join(CanonicalBrainRegion, CanonicalBrainRegion.id == AtlasRegionMapping.canonical_region_id)
            .where(AtlasRegionMapping.status == "active")
            .where(AtlasRegionResource.status == "active")
            .where(AtlasRegionMapping.species_relation == "same_species")
            .where(CanonicalBrainRegion.status == "active")
        )
    ).all()
    hits: list[Hit] = []
    for res, _mapping, region in rows:
        if res.region_name and _norm_name(res.region_name) == norm:
            hits.append((region, res.region_name, "atlas", 0.9))
        elif res.region_acronym and _norm_name(res.region_acronym) == norm:
            hits.append((region, res.region_acronym, "atlas", 0.9))
    return hits


async def _resolve_by_synonym(
    session: AsyncSession, norm: str, regions: list[CanonicalBrainRegion]
) -> tuple[CanonicalBrainRegion | None, str]:
    """优先级 5：ontology_term_synonyms（term_type='region'）→ 术语名称回链 canonical region。

    ontology_terms 与 canonical_brain_regions 无直接外键，回链方式：
    命中 synonym_text 后，用该术语的 canonical_term_en/cn 与 canonical 名称做全等匹配；
    回链失败视为未命中（宁缺毋滥，不模糊猜测）。
    """
    rows = (
        await session.execute(
            select(OntologyTermSynonym, OntologyTerm)
            .join(OntologyTerm, OntologyTerm.id == OntologyTermSynonym.term_id)
            .where(OntologyTerm.term_type == "region")
            .where(OntologyTermSynonym.status == "active")
        )
    ).all()
    region_by_norm: dict[str, CanonicalBrainRegion] = {}
    for r in regions:
        for field in ("canonical_name_cn", "canonical_name_en"):
            value = getattr(r, field, None)
            if value:
                region_by_norm.setdefault(_norm_name(str(value)), r)
    for syn, term in rows:
        if _norm_name(syn.synonym_text) != norm:
            continue
        for field in ("canonical_term_cn", "canonical_term_en"):
            value = getattr(term, field, None)
            if value:
                region = region_by_norm.get(_norm_name(str(value)))
                if region is not None:
                    return region, syn.synonym_text
        return None, syn.synonym_text  # 名称回链失败 → 未命中
    return None, ""


def _single_or_candidates(hits: list[Hit]) -> RegionResolution | None:
    """精确命中归约：同区去重（取高 confidence）→ 单区解析 / 多区返回候选（不自动选择）。"""
    if not hits:
        return None
    hits = sorted(hits, key=lambda h: h[3], reverse=True)
    seen: set[uuid.UUID] = set()
    unique: list[Hit] = []
    for hit in hits:
        if hit[0].id in seen:
            continue
        seen.add(hit[0].id)
        unique.append(hit)
    if len(unique) == 1:
        region, alias_text, source, confidence = unique[0]
        return RegionResolution(
            region, "alias", alias_text, alias=alias_text, source=source, confidence=confidence
        )
    return RegionResolution(
        None,
        "fuzzy",
        "",
        candidates=[
            {"candidate": r.canonical_name_cn or r.canonical_name_en, "confidence": confidence}
            for r, _text, _source, confidence in unique
        ],
    )


def _prefix_score(query_norm: str, candidate_norm: str) -> float:
    """模糊相似度（仅 fallback）：共享前缀占比 = shared_prefix / max(len(query), len(candidate))。"""
    shared = 0
    for a, b in zip(query_norm, candidate_norm):
        if a != b:
            break
        shared += 1
    if shared < 2:  # 至少两个字符共享，避免单字噪声
        return 0.0
    return round(shared / max(len(query_norm), len(candidate_norm)), 2)


async def _fuzzy_candidates(session: AsyncSession, norm: str) -> list[dict[str, Any]]:
    """优先级 6（仅 fallback）：canonical cn/en + 全部别名文本的相似候选，多候选不自动选择。

    打分基于共享前缀占比；按脑区去重取最高分；返回 top5（confidence >= 0.5）。
    """
    regions = await crs.list_canonical_regions(session, status="active")
    texts: list[tuple[CanonicalBrainRegion, str]] = []
    for r in regions:
        for field in ("canonical_name_cn", "canonical_name_en"):
            value = getattr(r, field, None)
            if value:
                texts.append((r, str(value)))
    alias_rows = (
        await session.execute(
            select(CanonicalRegionAlias, CanonicalBrainRegion)
            .join(CanonicalBrainRegion, CanonicalBrainRegion.id == CanonicalRegionAlias.region_id)
            .where(CanonicalBrainRegion.status == "active")
        )
    ).all()
    texts.extend((region, alias.alias) for alias, region in alias_rows)

    best: dict[uuid.UUID, float] = {}
    for region, text in texts:
        candidate_norm = _norm_name(text)
        if not candidate_norm or candidate_norm == norm:
            continue
        score = _prefix_score(norm, candidate_norm)
        if score < 0.5:
            continue
        prev = best.get(region.id)
        if prev is None or score > prev:
            best[region.id] = score
    ranked = sorted(best.items(), key=lambda kv: kv[1], reverse=True)
    candidates: list[dict[str, Any]] = []
    for rid, score in ranked[:5]:
        region = await crs.get_canonical_region(session, rid)
        if region is None:
            continue
        candidates.append(
            {"candidate": region.canonical_name_cn or region.canonical_name_en, "confidence": score}
        )
    return candidates


async def resolve_region(session: AsyncSession, name: str) -> RegionResolution | None:
    """七级解析（cn → en → 别名表/候选库 → atlas 名 → 同义词 → 模糊候选 → 未解析）。"""
    norm = _norm_name(name)
    if not norm:
        return None
    regions = await crs.list_canonical_regions(session)

    # 1/2：canonical 名称
    region, matched_by, matched_name = await _resolve_by_canonical_names(regions, norm)
    if region is not None:
        return RegionResolution(
            region, matched_by, matched_name, source="canonical_region",
            confidence=_CONFIDENCE_BY_MATCH[matched_by],
        )

    # 3：canonical_region_aliases（手工/本体）+ 已对齐 candidate 名称
    hits = await _resolve_by_region_aliases(session, norm)
    hits.extend(await _resolve_by_candidate_names(session, norm))
    resolution = _single_or_candidates(hits)
    if resolution is not None:
        return resolution

    # 4：atlas 原生名称
    resolution = _single_or_candidates(await _resolve_by_atlas_alias(session, norm))
    if resolution is not None:
        return resolution

    # 5：ontology synonym
    region, synonym_text = await _resolve_by_synonym(session, norm, regions)
    if region is not None:
        return RegionResolution(
            region, "synonym", synonym_text, alias=synonym_text,
            source="ontology_synonym", confidence=_CONFIDENCE_BY_MATCH["synonym"],
        )

    # 6：模糊候选（仅 fallback，不自动选择）
    candidates = await _fuzzy_candidates(session, norm)
    if candidates:
        return RegionResolution(None, "fuzzy", name, candidates=candidates)

    # 7：未解析
    return None

# --------------------------------------------------------------------------- #
# Handlers（复用 canonical service，禁止重复写 SQL；输出统一结果条目）
# --------------------------------------------------------------------------- #


def _item(
    *,
    entity_id: Any,
    code: str | None,
    name: str,
    category: str,
    detail: dict[str, Any],
    confidence: float | None,
    provenance: str,
) -> dict[str, Any]:
    return {
        "id": str(entity_id),
        "code": code,
        "name": name,
        "category": category,
        "detail": detail,
        "confidence": confidence,
        "provenance": provenance,
    }


async def _handle_children(session: AsyncSession, region: CanonicalBrainRegion) -> list[dict[str, Any]]:
    rows = await crs.get_children(session, region.id)
    return [
        _item(
            entity_id=child.id,
            code=child.region_code,
            name=child.canonical_name_cn or child.canonical_name_en,
            category="children",
            detail={
                "canonical_name_en": child.canonical_name_en,
                "granularity_level": child.granularity_level,
                "status": child.status,
            },
            confidence=float(child.confidence) if child.confidence is not None else None,
            provenance="canonical_region_hierarchy.part_of",
        )
        for child in rows
    ]


async def _handle_connections(session: AsyncSession, region: CanonicalBrainRegion) -> list[dict[str, Any]]:
    rows = await crs.get_region_connections(session, region.id)
    items: list[dict[str, Any]] = []
    for row in rows:
        endpoint = row.get("endpoint_region") or {}
        items.append(
            _item(
                entity_id=row.get("connection_id"),
                code=row.get("connection_code"),
                name=row.get("connection_code") or endpoint.get("canonical_name_en"),
                category="connection",
                detail={
                    "direction": row.get("direction"),
                    "connection_type": row.get("connection_type"),
                    "endpoint_region": endpoint,
                },
                confidence=row.get("confidence"),
                provenance="canonical_connections(source_region_id|target_region_id)",
            )
        )
    return items


async def _handle_circuits(session: AsyncSession, region: CanonicalBrainRegion) -> list[dict[str, Any]]:
    rows = await crs.get_region_circuits(session, region.id)
    return [
        _item(
            entity_id=row.get("circuit_id"),
            code=row.get("circuit_code"),
            name=row.get("canonical_name_en"),
            category="circuit",
            detail={
                "circuit_type": row.get("circuit_type"),
                "role": row.get("role"),
                "order_index": row.get("order_index"),
                "status": row.get("status"),
            },
            confidence=row.get("confidence"),
            provenance="canonical_circuit_regions(region_id)",
        )
        for row in rows
    ]


async def _handle_functions(session: AsyncSession, region: CanonicalBrainRegion) -> list[dict[str, Any]]:
    rows = await crs.get_region_functions(session, region.id)
    return [
        _item(
            entity_id=row.get("function_term_id"),
            code=row.get("term_code"),
            name=row.get("canonical_term_cn") or row.get("canonical_term_en"),
            category="function",
            detail={
                "canonical_term_en": row.get("canonical_term_en"),
                "relation_type": row.get("relation_type"),
                "circuit_code": row.get("circuit_code"),
                "circuit_name": row.get("circuit_name"),
            },
            confidence=row.get("confidence"),
            provenance="ontology_terms via canonical_circuit_functions",
        )
        for row in rows
    ]


async def _handle_multiscale(session: AsyncSession, region: CanonicalBrainRegion) -> list[dict[str, Any]]:
    view = await cms.get_multiscale_region_view(session, region.id)
    if view is None:
        return []
    items: list[dict[str, Any]] = []
    for cell in view.get("cell_types") or []:
        items.append(
            _item(
                entity_id=cell.get("cell_type_id"),
                code=cell.get("cell_type_code"),
                name=cell.get("canonical_name_cn") or cell.get("canonical_name_en"),
                category="cell_type",
                detail={
                    "canonical_name_en": cell.get("canonical_name_en"),
                    "taxonomy_source": cell.get("taxonomy_source"),
                    "mapping_type": cell.get("mapping_type"),
                },
                confidence=cell.get("confidence"),
                provenance="region_cell_alignment",
            )
        )
    for molecule in view.get("molecules") or []:
        items.append(
            _item(
                entity_id=molecule.get("molecular_entity_id"),
                code=molecule.get("entity_code"),
                name=molecule.get("canonical_name_en"),
                category="molecule",
                detail={
                    "entity_type": molecule.get("entity_type"),
                    "evidence_type": molecule.get("evidence_type"),
                    "source": molecule.get("source"),
                },
                confidence=molecule.get("confidence"),
                provenance="region_molecular_alignment",
            )
        )
    return items


_HANDLERS: dict[str, Any] = {
    INTENT_REGION_CHILDREN: _handle_children,
    INTENT_REGION_CONNECTIONS: _handle_connections,
    INTENT_REGION_CIRCUITS: _handle_circuits,
    INTENT_REGION_FUNCTIONS: _handle_functions,
    INTENT_REGION_MULTISCALE: _handle_multiscale,
}

_CONFIDENCE_BY_MATCH: dict[str, float] = {
    "canonical_name_cn": 0.95,
    "canonical_name_en": 0.95,
    "alias": 0.9,
    "synonym": 0.85,
}

# --------------------------------------------------------------------------- #
# 顶层入口
# --------------------------------------------------------------------------- #


def _entity_dict(resolution: RegionResolution) -> dict[str, Any]:
    region = resolution.region
    return {
        "type": "region",
        "id": str(region.id),
        "code": region.region_code,
        "name": region.canonical_name_cn or region.canonical_name_en,
        "matched_by": resolution.matched_by,
    }


def _unresolved(warnings: list[str], source_entities: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "intent": INTENT_UNRESOLVED,
        "entity": None,
        "results": [],
        "confidence": 0.0,
        "warnings": warnings,
        "source_entities": source_entities or [],
        "entity_match_detail": None,
    }


def _match_detail(resolution: RegionResolution) -> dict[str, Any]:
    """解析溯源详情：matched_by + 命中别名文本/来源/置信度（Phase Q1.5）。"""
    detail: dict[str, Any] = {"matched_by": resolution.matched_by}
    if resolution.alias:
        detail["alias"] = resolution.alias
    if resolution.source:
        detail["source"] = resolution.source
    if resolution.confidence is not None:
        detail["confidence"] = resolution.confidence
    else:
        detail["confidence"] = _CONFIDENCE_BY_MATCH.get(resolution.matched_by)
    return detail


async def handle_ontology_query(session: AsyncSession, question: str) -> dict[str, Any]:
    """POST /api/ontology-query 的主逻辑。返回可 JSON 序列化的响应 dict。"""
    normalized = normalize_question(question)
    if not normalized:
        return _unresolved(["问题为空或仅包含标点符号。"])

    intent, intent_keywords = classify_intent(normalized)
    if intent == INTENT_UNRESOLVED:
        return _unresolved(
            [
                f"无法识别查询意图（当前支持：亚区/连接/回路/功能/细胞与分子）。问题：「{normalized}」"
            ]
        )

    name = extract_entity_name(normalized, intent_keywords)
    if not name:
        return _unresolved([f"无法从问题中提取实体名称。问题：「{normalized}」"])

    resolution = await resolve_region(session, name)
    if resolution is None:
        return _unresolved(
            [
                f"未找到与「{name}」完全匹配的脑区（已按 canonical 名称/别名/Atlas 名称/同义词"
                f"精确匹配，并做过模糊候选；仍无结果，请尝试更标准的名称）。"
            ]
        )

    if resolution.region is None:
        # 多候选/模糊：不自动选择，候选随 source_entities 返回供前端未来消歧
        candidates = resolution.candidates
        names = "、".join(c["candidate"] for c in candidates)
        return _unresolved(
            [
                f"「{name}」未与标准脑区完全匹配，找到 {len(candidates)} 个候选（未自动选择，"
                f"供消歧）：{names}。"
            ],
            source_entities=candidates,
        )

    handler = _HANDLERS[intent]
    results = await handler(session, resolution.region)

    warnings: list[str] = []
    if not results:
        warnings.append(
            f"「{resolution.matched_name}」暂无{_intent_label(intent)}记录（结果为空，属正常情况）。"
        )

    confidence = (
        resolution.confidence
        if resolution.confidence is not None
        else _CONFIDENCE_BY_MATCH.get(resolution.matched_by, 0.9)
    )
    return {
        "intent": intent,
        "entity": _entity_dict(resolution),
        "results": results,
        "confidence": confidence,
        "warnings": warnings,
        "source_entities": [_entity_dict(resolution)],
        "entity_match_detail": _match_detail(resolution),
    }


def _intent_label(intent: str) -> str:
    return {
        INTENT_REGION_CHILDREN: "亚区",
        INTENT_REGION_CONNECTIONS: "连接",
        INTENT_REGION_CIRCUITS: "回路",
        INTENT_REGION_FUNCTIONS: "功能",
        INTENT_REGION_MULTISCALE: "细胞与分子",
    }.get(intent, "相关")
