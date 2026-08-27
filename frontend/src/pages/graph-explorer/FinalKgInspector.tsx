/**
 * 右侧 Entity Detail Panel（Phase 5；V2 知识图谱改造）：
 * 五 Tab：Overview / Relations / Functions / Evidence / Provenance（含计数徽章）。
 * - 数据来源：Relations/Functions/Evidence 均由当前已加载图派生（纯函数，不新增后端调用）；
 *   Hierarchy 通过真实端点解析：candidate → resolveCandidateToCanonicalRegion →
 *   listCanonicalRegionAncestors（失败诚实空态，不伪造数据）。
 * - 不同实体使用不同模板：brain_region（层级+统计）/ connection（Source→Target 头）/
 *   circuit（regions+steps+functions）/ function（层级+related）/ evidence（论文信息）。
 * - 关系卡片点击 → onNavigateNode 在图内选中对应节点；
 *   「Open in Ontology Center」保留（Phase 8 逻辑不变）。
 */
import { useCallback, useEffect, useState } from 'react'
import {
  getCanonicalRegion,
  listCanonicalRegionAncestors,
  resolveCandidateToCanonicalRegion,
  type CandidateCanonicalResolution,
  type RegionTreeItem,
} from '../../api/endpoints'
import { EmptyState } from '../ontology-center/ui/EmptyState'
import { RelationCard } from '../ontology-center/ui/RelationCard'
import { SectionCard } from '../ontology-center/ui/SectionCard'
import type { OntologyEntityType } from '../ontology-center/browser/tree/OntologyTreeNode'
import type { DetailRow, EntityRef, RelationItem } from '../ontology-center/detail/types'
import {
  CANONICAL_NODE_TYPE_LABELS,
  type CanonicalEdge,
  type CanonicalGraph,
  type CanonicalNode,
  type CanonicalNodeType,
} from './adapters/finalKgAdapter'
import type {
  CitationPaperInfo,
  ConnectionEdgeMeta,
  ConnectionEvidenceDetail,
} from './adapters/finalEgoGraph'
import { fetchConnectionEvidenceDetail, fetchConnectionPapers } from './adapters/finalEgoGraph'
import { NODE_TYPE_COLORS } from './graphTheme'
import { connectionLabelsOf } from './graphToXyflow'
import { ontologyNavigationUrlFor } from './ontologyNavigation'

// ── 工具 ─────────────────────────────────────────────────────────────────────────

function formatConfidence(value: number | null): string {
  if (value == null) return '—'
  return `${Math.round(value * 100)}%`
}

/** 长 id（uuid）截断显示 */
function formatId(value: string | null): string {
  if (!value) return '—'
  return value.length > 28 ? `${value.slice(0, 12)}…${value.slice(-12)}` : value
}

/** Canonical 节点类型 → 本体实体类型（circuit_step / evidence 无本体对应，返回 null） */
const ONTOLOGY_TYPE_OF: Partial<Record<CanonicalNodeType, OntologyEntityType>> = {
  brain_region: 'region',
  connection: 'connection',
  circuit: 'circuit',
  function: 'function',
}

function ontologyTypeOf(type: CanonicalNodeType): OntologyEntityType | null {
  return ONTOLOGY_TYPE_OF[type] ?? null
}

function RowList({ rows }: { rows: DetailRow[] }) {
  return (
    <dl className="oc-detail-list">
      {rows.map(row => (
        <div className="oc-detail-row" key={row.label}>
          <dt>{row.label}</dt>
          <dd>{row.value}</dd>
        </div>
      ))}
    </dl>
  )
}

// ── 关系派生（纯函数：Canonical 图 → 关系条目；V2 保留导出供测试）──────────────

function refOf(node: CanonicalNode): EntityRef | null {
  const entityType = ontologyTypeOf(node.type)
  if (!entityType) return null
  return { id: node.id, code: node.entityId, name: node.label, entityType }
}

function itemOf(node: CanonicalNode, meta: DetailRow[] = []): RelationItem | null {
  const ref = refOf(node)
  if (!ref) return null
  return { ref, meta }
}

/** 节点列表 → 关系条目（滤除无本体对应的类型） */
function compactItems(nodes: CanonicalNode[], meta?: DetailRow[]): RelationItem[] {
  return nodes.map(n => itemOf(n, meta)).filter((i): i is RelationItem => Boolean(i))
}

/** 去重合并（按节点 id），保留首个 meta */
function mergeItems(...lists: (RelationItem | null)[][]): RelationItem[] {
  const seen = new Set<string>()
  const out: RelationItem[] = []
  for (const list of lists) {
    for (const item of list) {
      if (!item || seen.has(item.ref.id)) continue
      seen.add(item.ref.id)
      out.push(item)
    }
  }
  return out
}

function neighborsOf(graph: CanonicalGraph, nodeId: string, edgeType: string, onSource: boolean): CanonicalNode[] {
  const out: CanonicalNode[] = []
  for (const e of graph.edges) {
    if (e.type !== edgeType) continue
    const otherId = onSource ? e.target : e.source
    const selfId = onSource ? e.source : e.target
    if (selfId !== nodeId) continue
    const n = graph.nodes.find(x => x.id === otherId)
    if (n) out.push(n)
  }
  return out
}

/** 与节点相连的某类边（任一方向） */
function edgesTouching(graph: CanonicalGraph, nodeId: string, edgeType: string) {
  return graph.edges.filter(e => e.type === edgeType && (e.source === nodeId || e.target === nodeId))
}

/** 每种节点类型的关系分组（title + 条目列表） */
export interface RelationSection {
  key: string
  title: string
  items: RelationItem[]
}

export function relationSectionsOf(graph: CanonicalGraph, node: CanonicalNode): RelationSection[] {
  const nodeById = new Map(graph.nodes.map(n => [n.id, n]))
  const sections: RelationSection[] = []

  if (node.type === 'brain_region') {
    // Connections：传出 / 传入投影（同一条投影可能两侧都有边 → 合并去重）
    const outgoing = neighborsOf(graph, node.id, 'projection_source', true).map(conn =>
      itemOf(conn, [
        { label: '方向', value: 'source' },
        { label: '投射类型', value: conn.label },
      ]),
    )
    const incoming = neighborsOf(graph, node.id, 'projection_target', false).map(conn =>
      itemOf(conn, [
        { label: '方向', value: 'target' },
        { label: '投射类型', value: conn.label },
      ]),
    )
    sections.push({ key: 'connections', title: 'Connections', items: mergeItems(outgoing, incoming) })
    sections.push({
      key: 'circuits',
      title: 'Circuits',
      items: compactItems(neighborsOf(graph, node.id, 'participates_in', true), [
        { label: '关系', value: 'participates_in' },
      ]),
    })
    sections.push({
      key: 'functions',
      title: 'Functions',
      items: compactItems(neighborsOf(graph, node.id, 'has_function', true), [
        { label: '关系', value: 'has_function' },
      ]),
    })
    return sections
  }

  if (node.type === 'connection') {
    const sourceNodes = neighborsOf(graph, node.id, 'projection_source', false)
    const targetNodes = neighborsOf(graph, node.id, 'projection_target', true)
    sections.push({ key: 'source', title: 'Source Region', items: compactItems(sourceNodes) })
    sections.push({ key: 'target', title: 'Target Region', items: compactItems(targetNodes) })
    return sections
  }

  if (node.type === 'circuit') {
    const steps = neighborsOf(graph, node.id, 'contains_step', true)
    const stepRegions: CanonicalNode[] = []
    for (const step of steps) {
      for (const e of graph.edges) {
        if (e.type === 'step_region' && e.source === step.id) {
          const r = nodeById.get(e.target)
          if (r) stepRegions.push(r)
        }
      }
    }
    sections.push({
      key: 'regions',
      title: 'Regions',
      items: mergeItems(
        neighborsOf(graph, node.id, 'participates_in', false).map(r => itemOf(r)),
        stepRegions.map(r => itemOf(r, [{ label: '来源', value: 'circuit_step' }])),
      ),
    })
    sections.push({
      key: 'connections',
      title: 'Connections',
      items: mergeItems(
        neighborsOf(graph, node.id, 'circuit_contains_projection', true).map(p => itemOf(p)),
        neighborsOf(graph, node.id, 'contains_projection', true).map(p => itemOf(p)),
      ),
    })
    sections.push({ key: 'functions', title: 'Functions', items: compactItems(neighborsOf(graph, node.id, 'has_function', true)) })
    return sections
  }

  if (node.type === 'function') {
    const owners = graph.edges
      .filter(e => e.type === 'has_function' && e.target === node.id)
      .map(e => nodeById.get(e.source))
      .filter((n): n is CanonicalNode => Boolean(n))
    sections.push({
      key: 'related',
      title: 'Related Entities',
      items: compactItems(owners, [
        { label: '关系', value: 'has_function' },
      ]),
    })
    return sections
  }

  if (node.type === 'circuit_step') {
    sections.push({ key: 'region', title: 'At Region', items: compactItems(neighborsOf(graph, node.id, 'step_region', true)) })
    return sections
  }

  return sections
}

/** Connection 方向性（由两侧边的存在性判断）；保留导出供测试 */
export function directionalityOf(graph: CanonicalGraph, node: CanonicalNode): string {
  const hasSource = edgesTouching(graph, node.id, 'projection_source').some(e => e.target === node.id)
  const hasTarget = edgesTouching(graph, node.id, 'projection_target').some(e => e.source === node.id)
  if (hasSource && hasTarget) return 'Directed（source → target）'
  if (hasSource) return 'Partial（仅 source）'
  if (hasTarget) return 'Partial（仅 target）'
  return 'Undirected'
}

// ── 图内统计（诚实计数，非 mock） ───────────────────────────────────────────────

interface EntityStats {
  connections: number
  circuits: number
  functions: number
  evidence: number
}

function statsOf(graph: CanonicalGraph, node: CanonicalNode): EntityStats {
  const connNodes = new Set<string>()
  const circuitNodes = new Set<string>()
  const functionNodes = new Set<string>()
  const evidenceNodes = new Set<string>()
  for (const e of graph.edges) {
    const touches = e.source === node.id || e.target === node.id
    if (!touches) continue
    const neighborId = e.source === node.id ? e.target : e.source
    if (e.type === 'projection_source' || e.type === 'projection_target') connNodes.add(neighborId)
    else if (e.type === 'participates_in') circuitNodes.add(neighborId)
    else if (e.type === 'has_function') functionNodes.add(neighborId)
    else if (e.type === 'has_evidence') evidenceNodes.add(neighborId)
  }
  // function 节点上 has_function 边的另一端是 owner（非 function 本身）——不计入 functions
  if (node.type === 'function') functionNodes.clear()
  return {
    connections: connNodes.size,
    circuits: circuitNodes.size,
    functions: functionNodes.size,
    evidence: evidenceNodes.size,
  }
}

// ── Function / Evidence 邻接（独立 Tab 用）─────────────────────────────────────

function functionItemsOf(graph: CanonicalGraph, node: CanonicalNode): RelationItem[] {
  const out = new Map<string, RelationItem>()
  for (const e of graph.edges) {
    if (e.type !== 'has_function') continue
    const fnId = e.target
    if (e.source === node.id) {
      const fn = graph.nodes.find(n => n.id === fnId)
      if (fn && fn.type === 'function') {
        const item = itemOf(fn, [{ label: '关系', value: 'has_function' }, { label: '方向', value: 'out' }])
        if (item) out.set(fnId, item)
      }
    } else if (e.target === node.id && node.type === 'function') {
      // function 自身：看它挂接的实体（owner）
      continue
    }
  }
  return [...out.values()]
}

interface EvidencePaperInfo {
  title: string | null
  journal: string | null
  year: string | null
  pmid: string | null
}

function paperInfoOf(node: CanonicalNode): EvidencePaperInfo {
  const raw = node.metadata.raw
  const str = (k: string) => (typeof raw[k] === 'string' && raw[k].trim() ? raw[k] : null)
  return { title: str('title'), journal: str('journal') ?? str('journal_name'), year: str('publish_year') ?? str('year'), pmid: str('pmid') }
}

function evidenceItemsOf(graph: CanonicalGraph, node: CanonicalNode): RelationItem[] {
  const out = new Map<string, RelationItem>()
  for (const e of graph.edges) {
    if (e.type !== 'has_evidence') continue
    const evId = e.source === node.id ? e.target : e.source
    const ev = graph.nodes.find(n => n.id === evId)
    if (ev && ev.type === 'evidence') {
      const item = itemOf(ev)
      if (item) out.set(evId, item)
    }
  }
  return [...out.values()]
}

// ── Hierarchy 真实解析（candidate → canonical → ancestors） ─────────────────────

interface HierarchyState {
  loading: boolean
  path: RegionTreeItem[] // 根 → 最深（不含自身）
  selfName: string | null
}

function useRegionHierarchy(node: CanonicalNode | null): HierarchyState {
  const [state, setState] = useState<HierarchyState>({ loading: false, path: [], selfName: null })

  useEffect(() => {
    if (!node || node.type !== 'brain_region') {
      setState({ loading: false, path: [], selfName: null })
      return
    }
    const controller = new AbortController()
    let cancelled = false
    setState(prev => ({ ...prev, loading: true, path: [], selfName: null }))
    ;(async () => {
      try {
        const resolution: CandidateCanonicalResolution = await resolveCandidateToCanonicalRegion(
          node.entityId,
          controller.signal,
        )
        if (cancelled) return
        if (!resolution.resolved || !resolution.canonical_region_id) {
          setState({ loading: false, path: [], selfName: null })
          return
        }
        const [ancestors, self] = await Promise.all([
          listCanonicalRegionAncestors(resolution.canonical_region_id, controller.signal),
          getCanonicalRegion(resolution.canonical_region_id, controller.signal),
        ])
        if (cancelled) return
        const sorted = [...ancestors].sort((a, b) => a.depth - b.depth)
        setState({
          loading: false,
          path: sorted,
          selfName: self?.canonical_name_en ?? resolution.canonical_name_en ?? null,
        })
      } catch {
        if (!cancelled) setState({ loading: false, path: [], selfName: null })
      }
    })()
    return () => {
      cancelled = true
      controller.abort()
    }
  }, [node])

  return state
}

function HierarchyChain({ state }: { state: HierarchyState }) {
  if (state.loading) {
    return (
      <div className="kg-inspector-loading">
        <span className="cg-spinner" />
        <span>解析层级中…</span>
      </div>
    )
  }
  if (state.path.length === 0) {
    return (
      <span className="oc-muted">
        图中未携带层级数据，且 canonical 解析不可用（父/子脑区需接入层级端点）
      </span>
    )
  }
  const steps = state.path
  return (
    <div className="kg-hierarchy-chain">
      {steps.map((item, i) => (
        <span key={item.id} className="kg-hierarchy-step-wrap">
          <span className="kg-hierarchy-step">
            {item.canonical_name_en}
            <span className="kg-hierarchy-step-detail">{item.granularity_level}</span>
          </span>
          {i < steps.length - 1 && <span className="kg-hierarchy-arrow">↓</span>}
        </span>
      ))}
      {steps.length > 0 && <span className="kg-hierarchy-arrow">↓</span>}
      <span className="kg-hierarchy-step kg-hierarchy-step-self">
        {state.selfName ?? '当前脑区'}
      </span>
    </div>
  )
}

// ── 主渲染 ──────────────────────────────────────────────────────────────────────

type InspectorTab = 'overview' | 'relations' | 'functions' | 'evidence' | 'provenance'

const INSPECTOR_TABS: { key: InspectorTab; label: string }[] = [
  { key: 'overview', label: '概览' },
  { key: 'relations', label: '关系' },
  { key: 'functions', label: '功能' },
  { key: 'evidence', label: '证据' },
  { key: 'provenance', label: '溯源' },
]

interface FinalKgInspectorProps {
  node: CanonicalNode | null
  /** 连接折叠边（Data Adapter V1：点击边 → 连接详情模板） */
  edge?: CanonicalEdge | null
  graph: CanonicalGraph
  /** 数据源（空态统计展示） */
  dataSource?: 'mirror' | 'final'
  /** 关系卡片点击 → 在图内选中对应节点 */
  onNavigateNode: (nodeId: string) => void
}

export function FinalKgInspector({ node, edge, graph, dataSource, onNavigateNode }: FinalKgInspectorProps) {
  const [resolving, setResolving] = useState(false)
  const [tab, setTab] = useState<InspectorTab>('overview')
  const hierarchy = useRegionHierarchy(node)

  // Edge 模式：单连接证据详情（canonical 层真实数据）+ 论文引用（链端点待接入）
  const [citationPapers, setCitationPapers] = useState<CitationPaperInfo[]>([])
  const [papersLoading, setPapersLoading] = useState(false)
  const [evidenceDetail, setEvidenceDetail] = useState<ConnectionEvidenceDetail | null>(null)
  const [evidenceLoading, setEvidenceLoading] = useState(false)
  useEffect(() => {
    if (!edge) {
      setCitationPapers([])
      setEvidenceDetail(null)
      return
    }
    const meta = (edge.metadata.raw?.connection as ConnectionEdgeMeta | undefined) ?? null
    if (!meta) {
      setEvidenceDetail(null)
      return
    }
    let cancelled = false
    setPapersLoading(true)
    setEvidenceLoading(true)
    fetchConnectionPapers(meta.connection_id)
      .then(papers => {
        if (!cancelled) setCitationPapers(papers)
      })
      .catch(() => {
        if (!cancelled) setCitationPapers([])
      })
      .finally(() => {
        if (!cancelled) setPapersLoading(false)
      })
    fetchConnectionEvidenceDetail(meta.connection_id)
      .then(detail => {
        if (!cancelled) setEvidenceDetail(detail)
      })
      .catch(() => {
        if (!cancelled) setEvidenceDetail(null)
      })
      .finally(() => {
        if (!cancelled) setEvidenceLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [edge])

  // Phase 8 方向 2：图节点 → 本体中心（region 先解析 canonical id，其余按名称搜索）
  const handleOpenOntology = useCallback(async () => {
    if (!node) return
    let resolution: CandidateCanonicalResolution | null = null
    if (node.type === 'brain_region') {
      setResolving(true)
      try {
        resolution = await resolveCandidateToCanonicalRegion(node.entityId)
      } catch {
        resolution = null // 解析失败 → 按名称搜索降级
      } finally {
        setResolving(false)
      }
    }
    const url = ontologyNavigationUrlFor(node, resolution)
    if (url) window.location.hash = url
  }, [node])

  if (edge) {
    return (
      <EdgeConnectionPanel
        edge={edge}
        graph={graph}
        onNavigateNode={onNavigateNode}
        papers={citationPapers}
        papersLoading={papersLoading}
        evidenceDetail={evidenceDetail}
        evidenceLoading={evidenceLoading}
      />
    )
  }

  if (!node) {
    return (
      <aside className="cg-inspector">
        <div className="cg-inspector-empty">
          <span className="cg-inspector-empty-icon">◎</span>
          <p>请选择节点查看详情</p>
          <span>在画布中点击节点或连接边,右侧将展示该实体的完整信息</span>
        </div>
      </aside>
    )
  }

  const basicRows: DetailRow[] = [
    { label: '类型', value: CANONICAL_NODE_TYPE_LABELS[node.type] },
    { label: '实体 id', value: formatId(node.entityId) },
    { label: 'canonical_id', value: formatId(node.metadata.canonical_id) },
    { label: 'source_id', value: formatId(node.metadata.source_id) },
    { label: '粒度', value: node.metadata.granularity ?? '—' },
    { label: '置信度', value: formatConfidence(node.metadata.confidence) },
  ]
  const connectionPairLabel = connectionLabelsOf(graph).get(node.id) ?? null

  if (node.type === 'connection') {
    basicRows.push({ label: '投射类型', value: node.label })
    basicRows.push({ label: '方向性', value: directionalityOf(graph, node) })
  }
  if (connectionPairLabel) {
    basicRows.unshift({ label: 'Source → Target', value: connectionPairLabel })
  }

  const provenanceRows: DetailRow[] = Object.entries(node.metadata.raw).map(([key, value]) => ({
    label: key,
    value: typeof value === 'object' ? JSON.stringify(value) : String(value),
  }))

  const sections = relationSectionsOf(graph, node)
  const stats = statsOf(graph, node)
  const functionItems = functionItemsOf(graph, node)
  const evidenceItems = evidenceItemsOf(graph, node)

  const tabCounts: Record<InspectorTab, number> = {
    overview: 0,
    relations: sections.reduce((sum, s) => sum + s.items.length, 0),
    functions: functionItems.length,
    evidence: evidenceItems.length,
    provenance: provenanceRows.length,
  }

  const renderTab = () => {
    if (tab === 'relations') {
      if (sections.length === 0) {
        return <EmptyState title="No relation in current graph" reason="当前加载图中无此关系记录" />
      }
      return sections.map(section => (
        <SectionCard key={section.key} title={section.title} count={section.items.length}>
          {section.items.length === 0 ? (
            <EmptyState title="No relation in current graph" reason="当前加载图中无此关系记录" />
          ) : (
            <div className="oc-inspector-relation-list">
              {section.items.map(item => (
                <RelationCard key={item.ref.id} item={item} navigable onNavigate={() => onNavigateNode(item.ref.id)} />
              ))}
            </div>
          )}
        </SectionCard>
      ))
    }

    if (tab === 'functions') {
      return (
        <SectionCard title="Functions" count={functionItems.length}>
          {functionItems.length === 0 ? (
            <EmptyState title="No function in current graph" reason="当前加载图中无功能关联（需在请求选项开启「包含功能节点」）" />
          ) : (
            <div className="oc-inspector-relation-list">
              {functionItems.map(item => (
                <RelationCard key={item.ref.id} item={item} navigable onNavigate={() => onNavigateNode(item.ref.id)} />
              ))}
            </div>
          )}
        </SectionCard>
      )
    }

    if (tab === 'evidence') {
      if (evidenceItems.length === 0) {
        return (
          <EmptyState
            title="No evidence in current graph"
            reason="镜像库暂无独立证据节点；切换到 Final KG 数据源并开启「包含证据节点」后可见"
          />
        )
      }
      return (
        <>
          <SectionCard title="Evidence" count={evidenceItems.length}>
            <div className="oc-inspector-relation-list">
              {evidenceItems.map(item => (
                <RelationCard key={item.ref.id} item={item} navigable onNavigate={() => onNavigateNode(item.ref.id)} />
              ))}
            </div>
          </SectionCard>
          {node.type === 'evidence' && <EvidencePaperCard node={node} />}
        </>
      )
    }

    if (tab === 'provenance') {
      return (
        <SectionCard title="Provenance">
          {provenanceRows.length > 0 ? (
            <RowList rows={provenanceRows} />
          ) : (
            <EmptyState title="No provenance on record" />
          )}
        </SectionCard>
      )
    }

    // Overview
    return (
      <>
        {/* 快速统计条（图内诚实计数） */}
        <div className="kg-inspector-stats">
          <span className="kg-inspector-stat">
            <strong>{stats.connections}</strong>
            连接
          </span>
          <span className="kg-inspector-stat">
            <strong>{stats.circuits}</strong>
            回路
          </span>
          <span className="kg-inspector-stat">
            <strong>{stats.functions}</strong>
            功能
          </span>
          <span className="kg-inspector-stat">
            <strong>{stats.evidence}</strong>
            证据
          </span>
        </div>

        <SectionCard title="Basic Information">
          <RowList rows={basicRows} />
        </SectionCard>

        {(node.type === 'brain_region' || node.type === 'function') && (
          <SectionCard title="Hierarchy">
            {node.type === 'brain_region' ? (
              <HierarchyChain state={hierarchy} />
            ) : (
              <span className="oc-muted">图中未携带级层数据（函数级层需接入术语级层端点）</span>
            )}
          </SectionCard>
        )}

        {node.type === 'circuit' && (
          <SectionCard title="Circuit Overview">
            <RowList
              rows={[
                { label: '参与脑区', value: String(sections.find(s => s.key === 'regions')?.items.length ?? 0) },
                { label: '回路连接', value: String(stats.connections) },
                { label: '回路功能', value: String(stats.functions) },
              ]}
            />
          </SectionCard>
        )}

        {node.type === 'evidence' && <EvidencePaperCard node={node} />}
      </>
    )
  }

  return (
    <aside className="cg-inspector">
      <div className="cg-inspector-head">
        <span className="cg-inspector-dot" style={{ background: NODE_TYPE_COLORS[node.type] }} />
        <div>
          <p className="cg-inspector-type">{CANONICAL_NODE_TYPE_LABELS[node.type]}</p>
          <h4 className="cg-inspector-title">{node.label}</h4>
        </div>
        {ontologyNavigationUrlFor(node, null) !== null && (
          <button
            type="button"
            className="btn btn-xs cg-open-ontology"
            onClick={handleOpenOntology}
            disabled={resolving}
            title="在本体中心查看该实体"
          >
            {resolving ? '解析中…' : 'Open in Ontology Center'}
          </button>
        )}
      </div>

      <div className="kg-inspector-tabs" role="tablist" aria-label="实体详情">
        {INSPECTOR_TABS.map(t => (
          <button
            key={t.key}
            type="button"
            role="tab"
            aria-selected={tab === t.key}
            className={`kg-inspector-tab${tab === t.key ? ' is-active' : ''}`}
            onClick={() => setTab(t.key)}
          >
            {t.label}
            {tabCounts[t.key] > 0 && <span className="kg-inspector-tab-count">{tabCounts[t.key]}</span>}
          </button>
        ))}
      </div>

      <div className="kg-inspector-body">{renderTab()}</div>
    </aside>
  )
}

/**
 * Connection 折叠边详情面板（Data Adapter V1）：
 * source region → target region / connection type / direction / confidence /
 * evidence_count；Evidence 区展示连接证据文本 + 论文引用（CitationPaperInfo 链
 * `final_connection → evidence_reference → paper_sources → connection_paper_evidence`
 * 当前后端无前端访问端点 → 诚实空态，不伪造）。
 */
function EdgeConnectionPanel({
  edge,
  graph,
  onNavigateNode,
  papers,
  papersLoading,
  evidenceDetail,
  evidenceLoading,
}: {
  edge: CanonicalEdge
  graph: CanonicalGraph
  onNavigateNode: (nodeId: string) => void
  papers: CitationPaperInfo[]
  papersLoading: boolean
  evidenceDetail: ConnectionEvidenceDetail | null
  evidenceLoading: boolean
}) {
  const meta = (edge.metadata.raw?.connection as ConnectionEdgeMeta | undefined) ?? null
  const labelOf = (nodeId: string) => graph.nodes.find(n => n.id === nodeId)?.label ?? nodeId

  const srcNode = graph.nodes.find(n => n.id === edge.source)
  const tgtNode = graph.nodes.find(n => n.id === edge.target)

  const rows: DetailRow[] = [
    { label: 'Source Region', value: labelOf(edge.source) },
    { label: 'Target Region', value: labelOf(edge.target) },
    { label: 'Connection Type', value: meta?.connection_type ?? edge.metadata.predicate ?? '—' },
    { label: 'Direction', value: meta?.direction ?? '—' },
    { label: 'Confidence', value: formatConfidence(meta?.confidence ?? null) },
    { label: 'Evidence Count', value: meta?.evidence_count == null ? '—（端点未接入）' : String(meta.evidence_count) },
    { label: 'Connection ID', value: formatId(meta?.connection_id ?? edge.metadata.source ?? null) },
  ]

  const provenanceRows: DetailRow[] = Object.entries(edge.metadata.raw).map(([key, value]) => ({
    label: key,
    value: typeof value === 'object' ? JSON.stringify(value) : String(value),
  }))

  return (
    <aside className="cg-inspector">
      <div className="cg-inspector-head">
        <span className="cg-inspector-dot" style={{ background: NODE_TYPE_COLORS.connection }} />
        <div>
          <p className="cg-inspector-type">Connection</p>
          <h4 className="cg-inspector-title">
            {labelOf(edge.source)} → {labelOf(edge.target)}
          </h4>
        </div>
      </div>

      <SectionCard title="Connection Overview">
        <RowList rows={rows} />
      </SectionCard>

      <SectionCard title={`Evidence（${meta?.evidence_count ?? 0} 条）`}>
        {evidenceLoading ? (
          <div className="kg-inspector-loading">
            <span className="cg-spinner" />
            <span>加载证据详情…</span>
          </div>
        ) : evidenceDetail && evidenceDetail.supporting_records.length > 0 ? (
          <>
            {evidenceDetail.evidence_quality_score && (
              <p className="kg-evidence-quality">
                质量：<strong>{evidenceDetail.evidence_quality_score}</strong>
                <span className="oc-muted">（canonical 证据聚合：LLM 提取记录，按来源/一致性评分）</span>
              </p>
            )}
            <div className="kg-inspector-records">
              {evidenceDetail.supporting_records.map((rec, i) => (
                <div key={`${rec.mirror_connection_id}-${i}`} className="kg-evidence-record">
                  <p className="kg-evidence-record-text">{rec.evidence_text || '（无证据文本）'}</p>
                  <p className="kg-evidence-record-meta">
                    {[
                      rec.confidence != null && `confidence ${rec.confidence}`,
                      rec.modality,
                      rec.directionality,
                      rec.llm_run_id && `source ${rec.llm_run_id.slice(0, 8)}`,
                    ]
                      .filter(Boolean)
                      .join(' · ')}
                  </p>
                </div>
              ))}
            </div>
          </>
        ) : (
          <span className="oc-muted">该连接无支撑证据记录（canonical 层）</span>
        )}
        <div className="kg-inspector-papers">
          <span className="cg-sidebar-label">论文引用（文献证据链）</span>
          {papersLoading ? (
            <div className="kg-inspector-loading">
              <span className="cg-spinner" />
              <span>加载论文引用…</span>
            </div>
          ) : papers.length === 0 ? (
            <span className="oc-muted">
              暂无接入：final_connection → evidence_reference → paper_sources →
              connection_paper_evidence 链当前无前端访问端点（后端接入后按 CitationPaperInfo
              模型回填 title / authors / year / doi / pmid）
            </span>
          ) : (
            papers.map(p => (
              <div key={p.doi ?? p.pmid ?? p.title} className="kg-paper-card">
                <p className="kg-paper-title">{p.title}</p>
                <p className="kg-paper-meta">
                  {[p.authors, p.year && String(p.year), p.pmid && `PMID ${p.pmid}`, p.doi && `DOI ${p.doi}`]
                    .filter(Boolean)
                    .join(' · ')}
                </p>
              </div>
            ))
          )}
        </div>
      </SectionCard>

      {srcNode && tgtNode && (
        <SectionCard title="Endpoints">
          <div className="oc-inspector-relation-list">
            {[
              { node: srcNode as CanonicalNode, meta: [{ label: '方向', value: 'source' }] as DetailRow[] },
              { node: tgtNode as CanonicalNode, meta: [{ label: '方向', value: 'target' }] as DetailRow[] },
            ].map(({ node: n, meta: m }) => {
              const item = itemOf(n, m)
              return item ? (
                <RelationCard key={item.ref.id} item={item} navigable onNavigate={() => onNavigateNode(item.ref.id)} />
              ) : null
            })}
          </div>
        </SectionCard>
      )}

      <SectionCard title="Provenance">
        {provenanceRows.length > 0 ? (
          <RowList rows={provenanceRows} />
        ) : (
          <EmptyState title="No provenance on record" />
        )}
      </SectionCard>
    </aside>
  )
}

/** Evidence 论文信息卡（evidence 节点 raw 字段可能携带的论文元数据；缺失诚实降级） */
function EvidencePaperCard({ node }: { node: CanonicalNode }) {
  const info = paperInfoOf(node)
  const hasAny = Boolean(info.title || info.journal || info.year || info.pmid)
  if (!hasAny) {
    return (
      <SectionCard title="Paper Information">
        <span className="oc-muted">当前 evidence 节点未携带论文元数据</span>
      </SectionCard>
    )
  }
  return (
    <SectionCard title="Paper Information">
      <RowList
        rows={[
          { label: '标题', value: info.title ?? '—' },
          { label: '期刊', value: info.journal ?? '—' },
          { label: '年份', value: info.year ?? '—' },
          { label: 'PMID', value: info.pmid ?? '—' },
        ]}
      />
    </SectionCard>
  )
}
