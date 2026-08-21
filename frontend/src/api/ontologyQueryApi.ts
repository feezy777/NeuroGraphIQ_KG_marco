import { postJson } from './client'

// ── Ontology Query（Phase 1 后端：POST /api/ontology-query） ────────────────
// 纯规则分类 + 精确匹配，无 LLM；类型对齐后端 schemas/ontology_query.py。

export type OntologyQueryIntent =
  | 'region_children'
  | 'region_connections'
  | 'region_circuits'
  | 'region_functions'
  | 'region_multiscale'
  | 'unresolved'

export type OntologyQueryCategory =
  | 'children'
  | 'connection'
  | 'circuit'
  | 'function'
  | 'cell_type'
  | 'molecule'

/** 解析到的实体（一律 canonical id；matched_by 指示匹配层级） */
export interface OntologyQueryEntity {
  type: string
  id: string
  code: string | null
  name: string
  matched_by: string | null
}

/** fuzzy 候选（未自动选择，随 source_entities 返回供前端消歧） */
export interface OntologyQueryCandidate {
  candidate: string
  confidence?: number | null
}

/** source_entities 承载两种形状：标准实体，或 fuzzy 候选 */
export type OntologySourceEntity = OntologyQueryEntity | OntologyQueryCandidate

/** 统一结果条目（category 决定渲染形态；detail 为意图特定字段） */
export interface OntologyQueryResultItem {
  id: string
  code: string | null
  name: string
  category: OntologyQueryCategory
  detail: Record<string, unknown>
  confidence: number | null
  provenance: string | null
}

export interface OntologyQueryResponse {
  intent: OntologyQueryIntent
  entity: OntologyQueryEntity | null
  results: OntologyQueryResultItem[]
  confidence: number
  warnings: string[]
  source_entities: OntologySourceEntity[]
}

/** 自然语言图谱查询（无 LLM；unresolved 也返回 200，通过 warnings 说明原因） */
export function postOntologyQuery(
  question: string,
  signal?: AbortSignal,
): Promise<OntologyQueryResponse> {
  return postJson('/api/ontology-query', { question }, undefined, signal)
}

// ── Phase Q4：LLM 增强解释层（POST /api/ontology-query/explain） ────────────
// 结构化结果（Knowledge Graph Evidence，蓝色）+ LLM 医学解释（AI Explanation，灰色）。

export interface OntologyLLMResponse {
  answer: string
  summary: string
  key_points: string[]
  evidence_entities: string[]
  confidence: number
  hallucination_warning: string[]
}

export interface OntologyExplainResponse {
  question: string
  query_result: OntologyQueryResponse
  explanation: OntologyLLMResponse
}

/** 自然语言查询 + LLM 医学解释（LLM 只读取结构化结果，不自行查询数据库） */
export function postOntologyExplain(
  question: string,
  signal?: AbortSignal,
): Promise<OntologyExplainResponse> {
  return postJson('/api/ontology-query/explain', { question }, undefined, signal)
}
