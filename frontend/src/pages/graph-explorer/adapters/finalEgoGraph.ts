/**
 * Graph Explorer Data Adapter V1 —— Canonical/Final KG Ego Graph 适配层。
 *
 * 背景（检查结论，全部实测验证）：
 * - final_macro_clinical 层浏览器图 API（FinalProjection / FinalCircuit /
 *   FinalEvidenceRecord 表）当前为空(0 行)——不能用；
 * - final_region_connections（/api/final-kg/connections）为空 —— 不能用；
 * - 有数据的前端可达数据源 = **_canonical 层_**：
 *     canonical_connections（2500 行,含 evidence_count / evidence_summary /
 *       confidence_statistics / evidence_quality_score,证据来自 mirror 聚合）
 *     canonical_brain_regions（686 行）
 *   ——与 final_canonical_connections（2485 行,review 晋升层）构型一致;
 * - 论文文献链（final_canonical_connections.evidence_reference →
 *   paper_sources → connection_paper_evidence）**后端无任何前端访问端点**
 *   （routers/schemas 零暴露）→ evidence_count 用 canonical 层真实计数
 *   （LLM 提取聚合,服务端文档明确 mirror 无 paper 字段）,literature 引用
 *   以 CitationPaperInfo 接口预留,不伪造。
 *
 * 本适配器实现知识图谱目标模型：
 *   Region ——(connection edge, 带 metadata) —— Region
 * edge metadata: connection_id / connection_type / direction / confidence /
 * evidence_count / evidence_quality_score。
 * 查询模式：Ego Graph —— 中心区域 + 1-hop 邻居（后端按 region 查询即 1-hop）。
 * 全景模式（Panorama）：listCanonicalConnections 全量（既有 API,零 mock）。
 */
import { getJson } from '../../../api/client'
import {
  listCanonicalConnections,
  listCanonicalRegions,
  listMirrorConnections,
  listMirrorEvidence,
  listMirrorFunctions,
  type CanonicalConnection,
  type CanonicalRegion,
  type MirrorRegionConnection,
} from '../../../api/endpoints'
import type { CanonicalEdge, CanonicalGraph, CanonicalNode } from './finalKgAdapter'

// ── 端点响应模型（适配层内声明,不改 endpoints.ts） ─────────────────────────────

/** GET /api/canonical-connections/evidence/by-region 单连接摘要 */
export interface CanonicalConnectionSummary {
  canonical_connection_id: string
  connection_code: string
  source_region: string | null
  target_region: string | null
  connection_type: string
  directionality_policy: string
  evidence_count: number
  confidence: { min: number | null; max: number | null; mean: number | null }
  evidence_quality_score: string | null
}

/** GET /api/canonical-connections/{id}/evidence 单连接证据详情 */
export interface ConnectionEvidenceDetail {
  canonical_connection_id: string
  connection_code: string
  source_region: string | null
  target_region: string | null
  connection_type: string
  directionality_policy: string
  evidence_summary: Record<string, unknown>
  supporting_records: {
    mirror_connection_id: string
    cluster_id: number | null
    evidence_text: string
    confidence: number | null
    directionality: string | null
    modality: string | null
    llm_run_id: string
  }[]
  confidence: { min: number | null; max: number | null; mean: number | null }
  evidence_quality_score: string | null
  evidence_quality_factors: Record<string, unknown>
}

/**
 * Connection edge 元数据（edge.data.connection）。
 * evidence_count 为 canonical 层真实计数（LLM 提取聚合）;
 * literature 引用链（evidence_reference→paper_sources→connection_paper_evidence）
 * 后端无端点 → CitationPaperInfo 预留,不伪造。
 */
export interface ConnectionEdgeMeta {
  connection_id: string
  connection_code: string
  connection_type: string
  direction: string
  confidence: number | null
  evidence_count: number
  evidence_quality_score: string | null
}

/** 论文引用（Evidence tab 模型;后端接入后由 fetchConnectionPapers 回填） */
export interface CitationPaperInfo {
  title: string
  authors: string | null
  year: number | null
  doi: string | null
  pmid: string | null
}

const BY_REGION_LIMIT = 500
const CONNECTION_EDGE_TYPE = 'connection'

// ── region 目录（缓存一次,686 区） ───────────────────────────────────────────────

let directoryCache: CanonicalRegion[] | null = null

export async function getCanonicalRegionDirectory(): Promise<CanonicalRegion[]> {
  if (!directoryCache) {
    directoryCache = await listCanonicalRegions()
  }
  return directoryCache
}

/** 本地名称搜索（686 区全量内存过滤,确定性;大小写不敏感子串） */
export function searchCanonicalRegions(
  directory: CanonicalRegion[],
  term: string,
  limit = 10,
): CanonicalRegion[] {
  const q = term.trim().toLowerCase()
  if (!q) return []
  return directory
    .filter(r => (r.canonical_name_en ?? '').toLowerCase().includes(q))
    .slice(0, limit)
}

// ── 数据获取 ────────────────────────────────────────────────────────────────────

async function fetchConnectionsByRegion(regionName: string): Promise<{
  total: number
  connections: CanonicalConnectionSummary[]
}> {
  const res = await getJson<{ region: string; total: number; connections: CanonicalConnectionSummary[] }>(
    '/api/canonical-connections/evidence/by-region',
    { region: regionName, limit: BY_REGION_LIMIT },
  )
  return {
    total: res.total ?? res.connections?.length ?? 0,
    connections: res.connections ?? [],
  }
}

/** 单连接证据详情（Inspector Evidence tab;真实数据） */
export async function fetchConnectionEvidenceDetail(
  connectionId: string,
): Promise<ConnectionEvidenceDetail | null> {
  try {
    return await getJson<ConnectionEvidenceDetail>(
      `/api/canonical-connections/${connectionId}/evidence`,
    )
  } catch {
    return null
  }
}

// ── 纯函数：连接列表 → Ego 图 ───────────────────────────────────────────────────

function regionNodeId(name: string): string {
  return `region:${name}`
}

function regionNode(name: string, granularity: string | null): CanonicalNode {
  return {
    id: regionNodeId(name),
    type: 'brain_region',
    label: name,
    metadata: {
      canonical_id: null,
      source_id: null,
      provenance: { region_name: name },
      granularity,
      confidence: null,
      raw: { region_name: name },
    },
    entityId: name,
  }
}

export interface EgoBuildInput {
  centerName: string
  connections: CanonicalConnectionSummary[]
  /** region 名 → granularity（可选,未提供则 null） */
  granularityOf?: (name: string) => string | null
  warnings?: string[]
}

/**
 * 连接摘要列表 → Ego Canonical 图：
 * 节点 = 中心精确名 + 两端名称（去重、排除与中心同名邻居）;
 * 边 = 每条连接一条 region--region edge（metadata 见 ConnectionEdgeMeta）。
 * 纯函数,不修改输入。
 */
export function buildFinalEgoGraph(input: EgoBuildInput): CanonicalGraph {
  const { centerName, connections, granularityOf } = input
  const granularityOfSafe: (name: string) => string | null = granularityOf ?? (() => null)

  const nodeByName = new Map<string, CanonicalNode>()
  const addNode = (name: string | null) => {
    if (!name || name === centerName) return
    const key = regionNodeId(name)
    if (!nodeByName.has(key)) nodeByName.set(key, regionNode(name, granularityOfSafe(name)))
  }

  const warnings = [...(input.warnings ?? [])]

  const edges: CanonicalEdge[] = []
  let skippedMissingEndpoint = 0
  for (const conn of connections) {
    const srcName = conn.source_region ?? null
    const tgtName = conn.target_region ?? null
    if (!srcName || !tgtName) {
      skippedMissingEndpoint += 1
      continue
    }
    // 中心锚定（中心必须是源或目标之一——by-region 检索语义;不锚定的连接由后端 ILIKE
    // 造成（如名称子串命中其他区域）→ 保留在图边缘,端点标注）
    const isCenterAnchored = srcName === centerName || tgtName === centerName
    addNode(srcName)
    addNode(tgtName)
    const meta: ConnectionEdgeMeta = {
      connection_id: conn.canonical_connection_id,
      connection_code: conn.connection_code,
      connection_type: conn.connection_type,
      direction: conn.directionality_policy,
      confidence: conn.confidence?.mean ?? null,
      evidence_count: conn.evidence_count ?? 0,
      evidence_quality_score: conn.evidence_quality_score ?? null,
    }
    edges.push({
      id: `connection:${conn.canonical_connection_id}`,
      source: regionNodeId(srcName),
      target: regionNodeId(tgtName),
      type: CONNECTION_EDGE_TYPE,
      label: conn.connection_type,
      metadata: {
        predicate: conn.connection_type,
        source: conn.canonical_connection_id,
        confidence: conn.confidence?.mean ?? null,
        raw: {
          connection: meta,
          directionality: conn.directionality_policy,
          connection_code: conn.connection_code,
          center_anchored: isCenterAnchored,
          quality: conn.evidence_quality_score,
        },
      },
    })
  }

  const centerNode = regionNode(centerName, granularityOfSafe(centerName))
  const partial = connections.filter(c => !c.source_region || !c.target_region).length
  if (partial > 0) warnings.push(`${partial} 条连接仅单端缺失(无法确定完整方向,不参与拓扑)`)
  warnings.push(
    'evidence_count 为 canonical 层真实计数(LLM 提取聚合);literature 引用链(evidence_reference→papers)后端无端点,待接入',
  )

  return {
    nodes: [centerNode, ...nodeByName.values()],
    edges,
    centerNodeId: regionNodeId(centerName),
    warnings,
  }
}


// ── 入口 ────────────────────────────────────────────────────────────────────────

export interface FetchFinalEgoParams {
  /** canonical 脑区 id（搜索窗选择结果） */
  centerRegionId: string
}

/**
 * Final/Canonical 源 Ego 图谱（适配层入口）：
 * canonical region id → 名称 → /evidence/by-region（1-hop）→ Ego 图。
 */
export async function fetchFinalEgoGraph(params: FetchFinalEgoParams): Promise<CanonicalGraph> {
  const directory = await getCanonicalRegionDirectory()
  const center = directory.find(r => r.id === params.centerRegionId)
  const centerName = center?.canonical_name_en ?? params.centerRegionId
  const granularityOf = (name: string) =>
    directory.find(r => r.canonical_name_en === name)?.granularity_level ?? null
  const { total, connections } = await fetchConnectionsByRegion(centerName)
  const warnings: string[] = []
  if (total > connections.length) {
    warnings.push(`连接按 limit=${BY_REGION_LIMIT} 截断（共 ${total} 条）`)
  }
  return buildFinalEgoGraph({ centerName, connections, granularityOf, warnings })
}

/**
 * Evidence 论文列表（接口预留——后端 literature 证据链端点接入后实现）:
 * final_connection → evidence_reference → paper_sources → connection_paper_evidence。
 * 当前无端点 → 返回空数组（不伪造）。
 */
export async function fetchConnectionPapers(_connectionId: string): Promise<CitationPaperInfo[]> {
  return []
}

// ── 全景模式（Panorama）：既有 API 全量,零 mock ─────────────────────────────────

/** canonical-connections 全量行（端点实际字段,front-end 类型收窄） */
export interface PanoramaConnection extends CanonicalConnection {
  source_region_id: string
  target_region_id: string
  connection_type: string
  directionality_policy: string
  confidence: number | null
}

/**
 * 全量连接 + region 目录 → 全景 CanonicalGraph（纯函数,不修改输入）：
 * - 节点：连接两端 canonical region（目录名,未命中目录时 id 兜底）
 * - 边：每条连接一条折叠边（metadata 同 Ego 结构）
 * - centerNodeId: null（全景无单中心）
 */
export function buildCanonicalPanoramaGraph(
  connections: PanoramaConnection[],
  directory: CanonicalRegion[],
): CanonicalGraph {
  const infoByRegionId = new Map(directory.map(r => [r.id, r]))
  const nameById = new Map<string, string>()
  const granularityById = new Map<string, string | null>()
  for (const r of directory) {
    nameById.set(r.id, r.canonical_name_en)
    granularityById.set(r.id, r.granularity_level)
  }

  const nodeIds = new Set<string>()
  const nodes = new Map<string, CanonicalNode>()
  const ensureNode = (regionId: string | null) => {
    if (!regionId) return
    const id = `region:${nameById.get(regionId) ?? regionId}`
    if (nodeIds.has(id)) return
    nodeIds.add(id)
    nodes.set(id, regionNode(nameById.get(regionId) ?? regionId, granularityById.get(regionId) ?? null))
  }

  const edges: CanonicalEdge[] = []
  for (const c of connections) {
    if (!c.source_region_id || !c.target_region_id) continue
    ensureNode(c.source_region_id)
    ensureNode(c.target_region_id)
    const srcName = nameById.get(c.source_region_id) ?? c.source_region_id
    const tgtName = nameById.get(c.target_region_id) ?? c.target_region_id
    const meta: ConnectionEdgeMeta = {
      connection_id: c.id,
      connection_code: c.connection_code,
      connection_type: c.connection_type,
      direction: c.directionality_policy,
      confidence: c.confidence ?? null,
      evidence_count: 0, // 列表行不携带 evidence_count（详情端点才能给）
      evidence_quality_score: null,
    }
    const edge: CanonicalEdge = {
      id: `connection:${c.id}`,
      source: regionNodeId(srcName),
      target: regionNodeId(tgtName),
      type: CONNECTION_EDGE_TYPE,
      label: c.connection_type,
      metadata: {
        predicate: c.connection_type,
        source: c.id,
        confidence: c.confidence ?? null,
        raw: { connection: meta, directionality: c.directionality_policy, connection_code: c.connection_code },
      },
    }
    if (edge.source !== edge.target) edges.push(edge)
  }

  void infoByRegionId
  return { nodes: [...nodes.values()], edges, centerNodeId: null, warnings: [] }
}

/** 全景数据（既有 API）：全量 canonical 连接 + region 目录 → 全景图。零 mock。 */
export async function fetchCanonicalPanoramaGraph(): Promise<CanonicalGraph> {
  const [connections, directory] = await Promise.all([
    listCanonicalConnections(),
    getCanonicalRegionDirectory(),
  ])
  return buildCanonicalPanoramaGraph(
    connections as unknown as PanoramaConnection[],
    directory,
  )
}


// ── Mirror 全景模式（Panorama）：全部端点 region 节点 + 连接折叠为边,窗口化诚实标注 ──

/** 镜像 connection_type → 关系组（颜色分组依据,与 relationStyleConfig 四组对齐） */
export const MIRROR_CONNECTION_GROUP: Record<string, string> = {
  structural: 'structural',
  functional: 'has_function',
  association: 'has_function',
  functional_connectivity: 'has_function',
  projection: 'participates_in',
  trace: 'participates_in',
  uncertain: 'evidence',
  unknown: 'evidence',
}

/** Mirror 全景窗口（粒度=macro：连接 5,720 全量 / 区域 96 端点全量;功能 142 全量;
    回路不建独立节点——以脑区+连接呈现(回路聚合的成员与连接已入图)） */
export const MIRROR_PANORAMA_WINDOW = {
  connections: 10000,
  functions: 500,
  evidence: 300,
}

export interface MirrorPanoramaInput {
  connections: MirrorRegionConnection[]
  /** 回路：不建独立节点（以脑区+连接呈现）—— 保留字段仅为窗口说明兼容 */
  circuits: unknown[]
  functions: { id: string; function_term?: string | null }[]
  evidence?: { id: string; label?: string | null }[]
}

function mirrorRegionNameOf(candidateId: string | null, cn: string | null, en: string | null): string | null {
  if (en) return en
  if (cn) return cn
  return candidateId ? `cand:${candidateId.slice(0, 8)}` : null
}

/**
 * Mirror 全景图（纯函数）：
 * - region 节点 = 连接两端候选（670 个,名称字段直取,零目录请求）
 * - Connection 不作为节点 —— 折叠为 region--region 边（label=connection_type）
 * - circuit 节点（前 window.circuits 条）+ function 节点
 * - evidence 节点（默认隐藏层;开关开启时最外层）
 * - warnings 明确说明全量规模与窗口化原因（前端布局性能限制,不伪装全量）
 */
export function buildMirrorPanoramaGraph(input: MirrorPanoramaInput): CanonicalGraph {
  const { connections } = input
  const warnings: string[] = []

  const nodeByName = new Map<string, CanonicalNode>()
  const nameByCandidate = new Map<string, string>()
  const ensureRegion = (cid: string | null, cn: string | null, en: string | null): string | null => {
    const name = mirrorRegionNameOf(cid, cn, en)
    if (!name) return null
    const id = name.startsWith('type:') ? `region:${name}` : `region:${name}`
    if (cid) nameByCandidate.set(cid, name)
    if (!nodeByName.has(id)) nodeByName.set(id, regionNode(name, null))
    return id
  }

  const edges: CanonicalEdge[] = []
  const seenEdge = new Set<string>()
  for (const c of connections) {
    const s = ensureRegion(c.source_region_candidate_id, c.source_region_name_cn, c.source_region_name_en)
    const t = ensureRegion(c.target_region_candidate_id, c.target_region_name_cn, c.target_region_name_en)
    if (!s || !t || s === t) continue
    const key = `${s}->${t}:${c.id}`
    if (seenEdge.has(key)) continue
    seenEdge.add(key)
    const meta: ConnectionEdgeMeta = {
      connection_id: String(c.id),
      connection_code: `ng:mirror:${String(c.id).slice(0, 8)}`,
      connection_type: c.connection_type ?? 'unknown',
      direction: c.directionality ?? 'unknown',
      confidence: c.confidence ?? null,
      evidence_count: 0, // mirror 列表不携带 evidence 计数
      evidence_quality_score: null,
    }
    const groupPredicate = MIRROR_CONNECTION_GROUP[c.connection_type ?? ''] ?? 'structural'
    edges.push({
      id: `connection:${c.id}`,
      source: s,
      target: t,
      type: 'connection',
      label: c.connection_type ?? 'connection',
      metadata: {
        // group predicate 映射（structural/has_function/participates_in/evidence）
        predicate: groupPredicate,
        source: String(c.id),
        confidence: c.confidence ?? null,
        raw: { connection: meta, directionality: c.directionality, center_anchored: false },
      },
    })
  }

  // circuit：不建独立节点 —— 用户规格「回路用脑区和连接显示」
  // （回路成员/连接已作为 region 节点与连接边聚合入图;circuit 参数仅用于窗口说明）
  void input.circuits
  // function 节点（外层）
  const addFuncNode = (id: string, label: string, cnName?: string | null) => {
    const name = label || cnName || `function:${id.slice(0, 8)}`
    nodeByName.set(`function:${id}`, {
      id: `function:${id}`,
      type: 'function',
      label: name,
      metadata: { canonical_id: null, source_id: id, provenance: { mirror: true }, granularity: null, confidence: null, raw: { mirror: true } },
      entityId: id,
    })
  }
  for (const f of input.functions) addFuncNode(String(f.id), f.function_term ?? 'function')

  // evidence 节点（默认独立层,开关开启后展示）
  for (const ev of input.evidence ?? []) {
    const name = ev.label ?? `evidence:${String(ev.id).slice(0, 8)}`
    nodeByName.set(`evidence:${ev.id}`, {
      id: `evidence:${ev.id}`,
      type: 'evidence',
      label: name,
      metadata: { canonical_id: null, source_id: String(ev.id), provenance: { mirror: true }, granularity: null, confidence: null, raw: { mirror: true } },
      entityId: String(ev.id),
    })
  }

  warnings.push(
    `Macro 粒度全景：连接 ${edges.length.toLocaleString()}/${'5,720 全量'} · 脑区 ${nodeByName.size - input.functions.length - (input.evidence ?? []).length} 端点 · ` +
      `回路以脑区+连接呈现(53,562 条回路聚合,不建独立节点) · 功能 ${input.functions.length}/${'142'}`, 
  )
  return { nodes: [...nodeByName.values()], edges, centerNodeId: null, warnings }
}

/** Mirror 全景数据（既有 API,真全局窗口,零 mock） */
export async function fetchMirrorPanoramaGraph(
  includeEvidence = false,
): Promise<CanonicalGraph> {
  const [connRes, fnRes, evRes] = await Promise.all([
    // 粒度=macro（用户规格：当前全景做 macro 层;连接 5,720 全量 < 窗口 → 无截断）
    listMirrorConnections({ granularity_level: 'macro', limit: MIRROR_PANORAMA_WINDOW.connections }),
    listMirrorFunctions({ granularity_level: 'macro', limit: MIRROR_PANORAMA_WINDOW.functions }),
    includeEvidence
      ? listMirrorEvidence({ granularity_level: 'macro', limit: MIRROR_PANORAMA_WINDOW.evidence })
      : Promise.resolve({ items: [], total: 0 }),
  ])
  const connections = (connRes.items ?? []) as unknown as MirrorRegionConnection[]
  const evidenceRows = ((evRes as { items?: unknown[] }).items ?? []) as { id: string; evidence_text?: string | null }[]
  return buildMirrorPanoramaGraph({
    connections,
    circuits: [], // 回路以脑区+连接呈现（成员/连接已入图）
    functions: (fnRes.items ?? []).map(f => ({ id: String(f.id), function_term: f.function_term })),
    evidence: evidenceRows.map(e => ({ id: String(e.id), label: e.evidence_text?.slice(0, 80) ?? null })),
  })
}
