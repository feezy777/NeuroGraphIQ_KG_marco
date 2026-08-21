/**
 * Mirror KG 图数据适配层（数据源切换：先用镜像库数据，晋升后再用 Final 数据）：
 * 将以 candidate 为中心的镜像对象（connections / functions / circuits）统一为
 * Canonical 图模型，使 Canvas / Inspector / 过滤器无需感知数据来源。
 *
 * 节点 id 约定与 finalKgAdapter 保持一致（前缀 = 后端类型，实体 id = 镜像/候选 id）：
 *   region:{candidate_id}          → brain_region
 *   projection:{connection_id}     → connection
 *   region_function:{function_id}  → function
 *   circuit:{circuit_id}           → circuit
 * 边语义与 Final 图完全一致（projection_source / projection_target / has_function /
 * participates_in），因此 graphToXyflow 的 "source → target" 标签派生自动生效。
 *
 * 镜像模式展开限制：仅 brain_region（candidate）可展开 —— 连接/回路/功能
 * 无独立中心查询链（回路查询端点仅支持 candidate_id 成员过滤）。
 */
import type {
  CandidateBrainRegion,
  MirrorRegionCircuit,
  MirrorRegionConnection,
  MirrorRegionFunction,
} from '../../../api/endpoints'
import type { CanonicalEdge, CanonicalGraph, CanonicalNode, CanonicalNodeMetadata } from './finalKgAdapter'

/** 镜像图数据源：以 center candidate 为中心查询到的全部镜像对象 */
export interface MirrorGraphSourceData {
  center: CandidateBrainRegion
  connections: MirrorRegionConnection[]
  functions: MirrorRegionFunction[]
  circuits: MirrorRegionCircuit[]
}

// ── 工具 ──────────────────────────────────────────────────────────────────────

function regionLabelOf(candidate: CandidateBrainRegion): string {
  return candidate.en_name || candidate.std_name || candidate.cn_name || candidate.raw_name || candidate.id
}

function mirrorProvenance(
  row: { source_atlas: string; granularity_family: string | null; mirror_status: string; review_status: string },
): Record<string, unknown> {
  const provenance: Record<string, unknown> = {
    source: 'mirror',
    source_atlas: row.source_atlas,
    mirror_status: row.mirror_status,
    review_status: row.review_status,
  }
  if (row.granularity_family != null) provenance.granularity_family = row.granularity_family
  return provenance
}

function baseMetadata(
  canonicalId: string | null,
  sourceId: string | null,
  granularity: string | null,
  confidence: number | null,
  provenance: Record<string, unknown>,
  raw: Record<string, unknown>,
): CanonicalNodeMetadata {
  return { canonical_id: canonicalId, source_id: sourceId, provenance, granularity, confidence, raw }
}

function regionNode(candidate: CandidateBrainRegion, extraProvenance: Record<string, unknown> = {}): CanonicalNode {
  return {
    id: `region:${candidate.id}`,
    type: 'brain_region',
    label: regionLabelOf(candidate),
    metadata: baseMetadata(
      null,
      null,
      candidate.granularity_level,
      null,
      { source: 'mirror', candidate_status: candidate.candidate_status, ...extraProvenance },
      { ...candidate },
    ),
    entityId: candidate.id,
  }
}

/** 由连接行派生远端脑区节点（可能为 center 自身，调用方按 id 去重） */
function remoteRegionNodeOf(
  candidateId: string | null,
  nameEn: string | null,
  nameCn: string | null,
  row: MirrorRegionConnection,
): CanonicalNode | null {
  if (!candidateId) return null
  const label = nameEn || nameCn || candidateId
  return {
    id: `region:${candidateId}`,
    type: 'brain_region',
    label,
    metadata: baseMetadata(
      null,
      null,
      row.granularity_level,
      null,
      mirrorProvenance(row),
      { source: 'mirror', region_name_en: nameEn, region_name_cn: nameCn },
    ),
    entityId: candidateId,
  }
}

function edgeOf(
  id: string,
  type: string,
  source: string,
  target: string,
  mirrorObjectId: string,
  confidence: number | null,
): CanonicalEdge {
  return {
    id,
    source,
    target,
    type,
    label: null,
    metadata: { predicate: type, source: mirrorObjectId, confidence, raw: {} },
  }
}

// ── 适配主函数 ────────────────────────────────────────────────────────────────

/**
 * 镜像对象集合 → Canonical 图（纯函数，不修改输入）。
 * 悬空边（端点候选缺失）在构建时即跳过，不会进入图中。
 */
export function adaptMirrorGraphResponse(source: MirrorGraphSourceData): CanonicalGraph {
  const { center } = source
  const nodeById = new Map<string, CanonicalNode>()
  const edgeById = new Map<string, CanonicalEdge>()
  const warnings: string[] = []

  // 中心脑区始终存在（即使无任何关系）
  nodeById.set(`region:${center.id}`, regionNode(center))

  for (const conn of source.connections) {
    const srcNode = remoteRegionNodeOf(
      conn.source_region_candidate_id,
      conn.source_region_name_en,
      conn.source_region_name_cn,
      conn,
    )
    const tgtNode = remoteRegionNodeOf(
      conn.target_region_candidate_id,
      conn.target_region_name_en,
      conn.target_region_name_cn,
      conn,
    )
    if (!srcNode || !tgtNode) {
      warnings.push(`connection ${conn.id} 缺少源/目标候选 id，已跳过`)
      continue
    }
    if (!nodeById.has(srcNode.id)) nodeById.set(srcNode.id, srcNode)
    if (!nodeById.has(tgtNode.id)) nodeById.set(tgtNode.id, tgtNode)

    const connNode: CanonicalNode = {
      id: `projection:${conn.id}`,
      type: 'connection',
      label: conn.connection_type,
      metadata: baseMetadata(
        conn.canonical_id,
        conn.id,
        conn.granularity_level,
        conn.confidence,
        mirrorProvenance(conn),
        { ...conn },
      ),
      entityId: conn.id,
    }
    nodeById.set(connNode.id, connNode)

    edgeById.set(`edge:${conn.id}:ps`, edgeOf(`edge:${conn.id}:ps`, 'projection_source', srcNode.id, connNode.id, conn.id, conn.confidence))
    edgeById.set(`edge:${conn.id}:pt`, edgeOf(`edge:${conn.id}:pt`, 'projection_target', connNode.id, tgtNode.id, conn.id, conn.confidence))
  }

  for (const fn of source.functions) {
    const fnNode: CanonicalNode = {
      id: `region_function:${fn.id}`,
      type: 'function',
      label: fn.function_term,
      metadata: baseMetadata(
        fn.canonical_id,
        fn.id,
        fn.granularity_level,
        fn.confidence,
        mirrorProvenance(fn),
        { ...fn },
      ),
      entityId: fn.id,
    }
    nodeById.set(fnNode.id, fnNode)
    edgeById.set(
      `edge:${fn.id}:hf`,
      edgeOf(`edge:${fn.id}:hf`, 'has_function', `region:${center.id}`, fnNode.id, fn.id, fn.confidence),
    )
  }

  for (const circuit of source.circuits) {
    const circuitNode: CanonicalNode = {
      id: `circuit:${circuit.id}`,
      type: 'circuit',
      label: circuit.name_cn || circuit.circuit_name,
      metadata: baseMetadata(
        circuit.canonical_id,
        circuit.id,
        circuit.granularity_level,
        circuit.confidence,
        mirrorProvenance(circuit),
        { ...circuit },
      ),
      entityId: circuit.id,
    }
    nodeById.set(circuitNode.id, circuitNode)
    edgeById.set(
      `edge:${circuit.id}:pi`,
      edgeOf(
        `edge:${circuit.id}:pi`,
        'participates_in',
        `region:${center.id}`,
        circuitNode.id,
        circuit.id,
        circuit.confidence,
      ),
    )
  }

  return {
    nodes: [...nodeById.values()],
    edges: [...edgeById.values()],
    centerNodeId: `region:${center.id}`,
    warnings,
  }
}

// ── 镜像模式展开（仅 brain_region）────────────────────────────────────────────

/** 镜像模式节点是否可展开：仅候选脑区（connection/circuit/function 无独立中心查询） */
export function canExpandMirrorNode(node: CanonicalNode): boolean {
  return node.type === 'brain_region'
}

/** 镜像模式展开请求（entityId 即 candidate_id） */
export function expandRequestForMirrorNode(node: CanonicalNode): { candidate_id: string } | null {
  if (!canExpandMirrorNode(node)) return null
  return { candidate_id: node.entityId }
}
