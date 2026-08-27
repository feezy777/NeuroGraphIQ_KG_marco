"""Ontology Query Phase 1 — 请求/响应 Schema。

响应结构（对齐规格）：
    {intent, entity{type,id,code,name,matched_by}, results[], confidence, warnings[], source_entities[]}
结果条目统一为 {id, code, name, category, detail, confidence, provenance}，
category 区分 children/connection/circuit/function/cell_type/molecule。
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class OntologyQueryRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=500, description="自然语言问题，如「海马有哪些亚区」")


class OntologyQueryEntity(BaseModel):
    """解析到的实体（一律返回 canonical id）。"""

    type: str = Field(default="region", description="实体类型（Phase 1 仅 region）")
    id: str = Field(..., description="canonical 实体 id")
    code: str | None = Field(default=None, description="canonical code（如 ng:br:hippocampus）")
    name: str = Field(..., description="展示名（中文优先）")
    matched_by: str | None = Field(
        default=None,
        description="匹配层级：canonical_name_cn | canonical_name_en | alias | synonym",
    )


class OntologyQueryResultItem(BaseModel):
    """统一结果条目（各意图的 handler 输出）。"""

    id: str = Field(..., description="canonical id（connection/circuit/function/cell_type/molecule）")
    code: str | None = Field(default=None)
    name: str = Field(..., description="展示名")
    category: str = Field(
        ...,
        description="children | connection | circuit | function | function_descendant | function_ancestor | cell_type | molecule",
    )
    detail: dict[str, Any] = Field(default_factory=dict, description="意图特定字段（direction/role 等）")
    confidence: float | None = Field(default=None)
    provenance: str | None = Field(default=None, description="数据来源表/关系")


class OntologyQueryCandidate(BaseModel):
    """模糊/多候选条目（Phase Q1.5）：候选名 + 置信度，不自动选择。"""

    candidate: str = Field(..., description="候选脑区展示名")
    confidence: float = Field(..., description="候选置信度 0..1")


class OntologyQueryMatchDetail(BaseModel):
    """实体解析溯源（Phase Q1.5）：命中的层级 + 别名文本 + 来源 + 置信度。"""

    matched_by: str = Field(
        ...,
        description="匹配层级：canonical_name_cn | canonical_name_en | alias | synonym",
    )
    alias: str | None = Field(default=None, description="命中的别名文本（alias/synonym 匹配时）")
    source: str | None = Field(
        default=None,
        description="别名来源：canonical_region | manual_curated | atlas | candidate_pool | ontology_synonym",
    )
    confidence: float | None = Field(default=None, description="本次匹配置信度 0..1")


class OntologyQueryResponse(BaseModel):
    intent: str = Field(..., description="region_children/region_connections/region_circuits/region_functions/region_multiscale/function_children/function_ancestors/unresolved")
    entity: OntologyQueryEntity | None = Field(default=None, description="解析到的实体；unresolved 时为 null")
    results: list[OntologyQueryResultItem] = Field(default_factory=list)
    confidence: float = Field(default=0.0, description="0..1；unresolved 恒为 0")
    warnings: list[str] = Field(default_factory=list, description="可解释性说明（未命中原因/空结果）")
    source_entities: list[OntologyQueryEntity | OntologyQueryCandidate] = Field(
        default_factory=list,
        description="命中实体（供消歧/溯源展示）；Phase Q1.5 起多候选时为 candidate 条目",
    )
    entity_match_detail: OntologyQueryMatchDetail | None = Field(
        default=None,
        description="实体解析溯源（Phase Q1.5）；unresolved 恒为 null",
    )
    hierarchy_analysis: dict[str, Any] | None = Field(
        default=None,
        description=(
            "function hierarchy 扩展分析（without/with 结果数对比 + 新增关联路径）；"
            "function 意图与 region_functions 增强时出现，其余意图为 null"
        ),
    )


class OntologyLLMResponse(BaseModel):
    """Phase Q4 — LLM 医学解释（只基于 Structured Query Result，不读库）。

    answer 是完整医学解释；summary 一句话摘要；key_points 要点列表；
    evidence_entities 由结构化结果确定性导出（LLM 自报不被采信）；
    hallucination_warning 是 response_validator 标记的不在 evidence 中的
    已知脑区名称（有则提示、不阻断展示）。
    """

    answer: str = Field(..., description="医学解释正文（中文，所有结论来自 evidence）")
    summary: str = Field(default="", description="一句话摘要")
    key_points: list[str] = Field(default_factory=list, description="要点列表")
    evidence_entities: list[str] = Field(
        default_factory=list, description="evidence 中的实体名称/code（结构化结果导出）"
    )
    confidence: float = Field(default=0.0, description="0..1；LLM 自报置信度或结构化置信度")
    hallucination_warning: list[str] = Field(
        default_factory=list,
        description="回答中出现但不在 evidence 中的已知脑区名称；空=未发现幻觉",
    )


class OntologyExplainRequest(BaseModel):
    """POST /api/ontology-query/explain 请求：与 /api/ontology-query 相同。"""

    question: str = Field(..., min_length=1, max_length=500, description="自然语言问题")


class OntologyExplainResponse(BaseModel):
    """结构化结果（Knowledge Graph Evidence）+ LLM 解释（AI Explanation）双轨响应。"""

    question: str = Field(..., description="原始问题回显")
    query_result: OntologyQueryResponse = Field(..., description="结构化查询结果（蓝色=图谱证据）")
    explanation: OntologyLLMResponse = Field(..., description="医学解释（灰色=AI 语言总结）")
