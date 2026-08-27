/**
 * Final KG 图数据适配层（Phase 2）：
 * 将 final_macro_clinical browser 后端图响应统一为 Canonical 图模型。
 *
 * 设计目标：
 * 1. Canvas / Inspector / 过滤器只消费 CanonicalNode / CanonicalEdge，
 *    不允许直接处理后端字段（FinalGraphNode.type 等）。
 * 2. 后端节点类型统一映射：
 *      region → brain_region
 *      region_function / circuit_function / projection_function → function
 *      circuit → circuit
 *      circuit_step → circuit_step
 *      projection → connection
 *      evidence → evidence
 * 3. 节点 metadata 预留未来推理所需字段（Phase 9）：
 *      canonical_id / source_id / provenance / granularity / confidence
 *    边 metadata 预留：predicate / source / confidence
 */
import type { FinalGraphEdge, FinalGraphNode, FinalGraphResponse } from '../../../api/endpoints'

// ── 统一节点类型 ──────────────────────────────────────────────────────────────

export type CanonicalNodeType = 'brain_region' | 'connection' | 'circuit' | 'circuit_step' | 'function' | 'evidence'

/** 后端节点类型 → 统一节点类型 */
const BACKEND_NODE_TYPE_MAP: Record<string, CanonicalNodeType> = {
  region: 'brain_region',
  region_function: 'function',
  circuit: 'circuit',
  circuit_step: 'circuit_step',
  projection: 'connection',
  projection_function: 'function',
  circuit_function: 'function',
  evidence: 'evidence',
}

export const CANONICAL_NODE_TYPE_LABELS: Record<CanonicalNodeType, string> = {
  brain_region: 'Brain Region',
  connection: 'Connection',
  circuit: 'Circuit',
  circuit_step: 'Circuit Step',
  function: 'Function',
  evidence: 'Evidence',
}

// ── 统一图模型 ────────────────────────────────────────────────────────────────

/** 节点 metadata：含 Phase 9 推理预留字段 */
export interface CanonicalNodeMetadata {
  /** 正式对象 id（final_* 表主键）；推理时用作全局实体引用 */
  canonical_id: string | null
  /** 溯源 id：镜像对象 id（source_mirror_id） */
  source_id: string | null
  /** 溯源信息（source_atlas / granularity_family / 镜像链接等） */
  provenance: Record<string, unknown>
  /** 粒度层级（macro / meso / sub_connectivity / fine_cyto / molecular_attr） */
  granularity: string | null
  /** 置信度 0-1 */
  confidence: number | null
  /** 后端原始 metadata 透传（调试/扩展用） */
  raw: Record<string, unknown>
}

export interface CanonicalNode {
  id: string
  type: CanonicalNodeType
  label: string
  metadata: CanonicalNodeMetadata
  /** 后端节点 id（`{type}:{key}`）中的实体 id 部分 */
  entityId: string
}

/** 边 metadata：含 Phase 9 推理预留字段 */
export interface CanonicalEdgeMetadata {
  /** 语义谓词（后端 predicate ?? type） */
  predicate: string
  /** 溯源：晋升后正式 id（final_id） */
  source: string | null
  /** 置信度 0-1 */
  confidence: number | null
  raw: Record<string, unknown>
}

export interface CanonicalEdge {
  id: string
  /** 拓扑源节点 id */
  source: string
  /** 拓扑目标节点 id */
  target: string
  /** 后端边类型（has_function / participates_in / contains_step / ...） */
  type: string
  label: string | null
  metadata: CanonicalEdgeMetadata
}

export interface CanonicalGraph {
  nodes: CanonicalNode[]
  edges: CanonicalEdge[]
  centerNodeId: string | null
  warnings: string[]
}

// ── 工具函数 ──────────────────────────────────────────────────────────────────

function toConfidence(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value === 'string') {
    const n = Number(value)
    return Number.isFinite(n) ? n : null
  }
  return null
}

/** 解析后端节点 id `{type}:{key}` → 后端类型 + 实体 id；无冒号时返回 null */
export function parseNodeId(nodeId: string): { backendType: string; entityId: string } | null {
  const idx = nodeId.indexOf(':')
  if (idx <= 0) return null
  const backendType = nodeId.slice(0, idx)
  const entityId = nodeId.slice(idx + 1)
  if (!backendType || !entityId) return null
  return { backendType, entityId }
}

/** 节点 id 前缀即后端节点类型（Canvas 侧据此判断可展开性，无需触碰后端字段） */
export function nodeBackendType(node: CanonicalNode): string {
  return parseNodeId(node.id)?.backendType ?? ''
}

// ── 展开支持 ──────────────────────────────────────────────────────────────────

/**
 * 后端图 API 支持的 center_type（get_final_graph dispatch）：
 * region / circuit / projection / circuit_step / projection_function。
 * region_function / circuit_function / evidence 无独立中心类型 → 不可展开。
 */
const EXPAND_CENTER_TYPES: Record<string, string> = {
  region: 'region',
  circuit: 'circuit',
  projection: 'projection',
  circuit_step: 'circuit_step',
  projection_function: 'projection_function',
}

/** 图 API 支持的 center_type 选项（侧栏手动加载入口用） */
export const GRAPH_CENTER_TYPES: { value: string; label: string }[] = [
  { value: 'region', label: 'Region（canonical id）' },
  { value: 'circuit', label: 'Circuit（final_id）' },
  { value: 'projection', label: 'Projection（final_id）' },
  { value: 'circuit_step', label: 'Circuit Step（final_id）' },
  { value: 'projection_function', label: 'Projection Function（final_id）' },
]

export interface ExpandRequest {
  center_type: string
  center_id: string
}

/** 节点是否可展开（增量扩展以该节点为中心请求邻居） */
export function canExpandNode(node: CanonicalNode): boolean {
  return nodeBackendType(node) in EXPAND_CENTER_TYPES
}

/** 生成以该节点为中心的图请求参数；不可展开时返回 null */
export function expandRequestForNode(node: CanonicalNode): ExpandRequest | null {
  const backendType = nodeBackendType(node)
  const centerType = EXPAND_CENTER_TYPES[backendType]
  if (!centerType) return null
  return { center_type: centerType, center_id: node.entityId }
}

// ── 关系分组（Phase 7 过滤用）────────────────────────────────────────────────

export interface RelationGroupDef {
  value: string
  label: string
  edgeTypes: string[]
}

export const RELATION_GROUPS: RelationGroupDef[] = [
  {
    value: 'structural',
    label: 'Structural',
    edgeTypes: [
      'connection', // Data Adapter V1：Final KG 连接折叠边（region--region）
      'projection_source',
      'projection_target',
      'contains_projection',
      'circuit_contains_projection',
      'contains_step',
      'step_region',
      'circuit_contains',
    ],
  },
  { value: 'has_function', label: 'Has Function', edgeTypes: ['has_function'] },
  { value: 'participates_in', label: 'Participates In', edgeTypes: ['participates_in'] },
  { value: 'evidence', label: 'Evidence', edgeTypes: ['has_evidence'] },
]

/** 后端边类型 → 关系分组值（未知类型归入 structural 兜底） */
const EDGE_TYPE_TO_GROUP: Record<string, string> = {}
for (const group of RELATION_GROUPS) {
  for (const edgeType of group.edgeTypes) {
    EDGE_TYPE_TO_GROUP[edgeType] = group.value
  }
}

export function relationGroupOf(edge: CanonicalEdge): string {
  return EDGE_TYPE_TO_GROUP[edge.type] ?? 'structural'
}

// ── 适配主函数 ────────────────────────────────────────────────────────────────

function adaptNode(n: FinalGraphNode): CanonicalNode {
  const raw = n.metadata ?? {}
  const provenance: Record<string, unknown> = {}
  if (n.source_mirror_id) provenance.source_mirror_id = n.source_mirror_id
  if (raw.source_atlas != null) provenance.source_atlas = raw.source_atlas
  if (raw.granularity_family != null) provenance.granularity_family = raw.granularity_family
  return {
    id: n.id,
    type: BACKEND_NODE_TYPE_MAP[n.type] ?? 'brain_region',
    label: n.label || n.id,
    metadata: {
      canonical_id: n.final_id ?? null,
      source_id: n.source_mirror_id ?? null,
      provenance,
      granularity: typeof raw.granularity_level === 'string' ? raw.granularity_level : null,
      confidence: toConfidence(raw.confidence),
      raw,
    },
    entityId: parseNodeId(n.id)?.entityId ?? n.id,
  }
}

function adaptEdge(e: FinalGraphEdge): CanonicalEdge {
  const raw = e.metadata ?? {}
  return {
    id: e.id,
    source: e.source,
    target: e.target,
    type: e.type || 'unknown',
    label: e.label ?? null,
    metadata: {
      predicate: e.predicate ?? e.type ?? 'unknown',
      source: e.final_id ?? null,
      confidence: toConfidence(raw.confidence),
      raw,
    },
  }
}

/** 后端图响应 → 统一 Canonical 图（纯函数，不修改输入） */
export function adaptFinalGraphResponse(res: FinalGraphResponse): CanonicalGraph {
  const nodes = (res.nodes ?? []).map(adaptNode)
  const nodeIds = new Set(nodes.map(n => n.id))
  const edges = (res.edges ?? [])
    .filter(e => nodeIds.has(e.source) && nodeIds.has(e.target))
    .map(adaptEdge)
  return {
    nodes,
    edges,
    centerNodeId: res.center_node_id ?? null,
    warnings: res.warnings ?? [],
  }
}

// ── 增量展开合并（Phase 6）──────────────────────────────────────────────────────

/**
 * 将新拉取的子图合并进已有图（增量展开，禁止清空已有图）：
 * - 节点/边按 id 去重合并，已存在节点保留原数据（不覆盖）
 * - centerNodeId 保留原图中心（布局锚点不变，保证每次展开位置稳定）
 * - warnings 合并去重
 * 纯函数，不修改输入。
 */
export function mergeCanonicalGraphs(base: CanonicalGraph, incoming: CanonicalGraph): CanonicalGraph {
  const nodeById = new Map(base.nodes.map(n => [n.id, n]))
  for (const n of incoming.nodes) {
    if (!nodeById.has(n.id)) nodeById.set(n.id, n)
  }
  const edgeById = new Map(base.edges.map(e => [e.id, e]))
  for (const e of incoming.edges) {
    if (!edgeById.has(e.id)) edgeById.set(e.id, e)
  }
  const warnings = [...base.warnings]
  for (const w of incoming.warnings) {
    if (!warnings.includes(w)) warnings.push(w)
  }
  return {
    nodes: [...nodeById.values()],
    edges: [...edgeById.values()],
    centerNodeId: base.centerNodeId,
    warnings,
  }
}
