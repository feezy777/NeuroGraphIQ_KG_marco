/**
 * 右侧 Inspector（Phase 5）：
 * 复用 Ontology Center 设计组件（SectionCard / RelationCard / EntityChip / EmptyState，
 * 样式为全局 styles.css 的 oc-* 类）。
 * 四段式：Basic Information / Hierarchy / Relations / Provenance。
 *
 * 数据来源：
 * - Relations 由当前已加载图派生（CanonicalNode/Edge 纯函数），不新增后端调用；
 * - Hierarchy 图响应未携带 → 诚实空态（遵循「不展示假数据」原则）。
 * 关系卡片点击 → onNavigateNode 在图内选中对应节点。
 *
 * Phase 8：头部「Open in Ontology Center」——brain_region 先解析 candidate → canonical，
 * 成功直达实体详情，失败按名称搜索降级；circuit/function/connection 按名称搜索；
 * circuit_step/evidence 无本体对应 → 不渲染按钮。
 */
import { useCallback, useState } from 'react'
import {
  resolveCandidateToCanonicalRegion,
  type CandidateCanonicalResolution,
} from '../../api/endpoints'
import { EmptyState } from '../ontology-center/ui/EmptyState'
import { RelationCard } from '../ontology-center/ui/RelationCard'
import { SectionCard } from '../ontology-center/ui/SectionCard'
import type { OntologyEntityType } from '../ontology-center/browser/tree/OntologyTreeNode'
import type { DetailRow, EntityRef, RelationItem } from '../ontology-center/detail/types'
import {
  CANONICAL_NODE_TYPE_LABELS,
  type CanonicalGraph,
  type CanonicalNode,
  type CanonicalNodeType,
} from './adapters/finalKgAdapter'
import { NODE_TYPE_COLORS } from './graphTheme'
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

// ── 关系派生（纯函数：Canonical 图 → 关系条目）──────────────────────────────────

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

/** Connection 方向性（由两侧边的存在性判断） */
export function directionalityOf(graph: CanonicalGraph, node: CanonicalNode): string {
  const hasSource = edgesTouching(graph, node.id, 'projection_source').some(e => e.target === node.id)
  const hasTarget = edgesTouching(graph, node.id, 'projection_target').some(e => e.source === node.id)
  if (hasSource && hasTarget) return 'Directed（source → target）'
  if (hasSource) return 'Partial（仅 source）'
  if (hasTarget) return 'Partial（仅 target）'
  return 'Undirected'
}

// ── 四段式渲染 ───────────────────────────────────────────────────────────────────

interface FinalKgInspectorProps {
  node: CanonicalNode | null
  graph: CanonicalGraph
  /** 关系卡片点击 → 在图内选中对应节点 */
  onNavigateNode: (nodeId: string) => void
}

export function FinalKgInspector({ node, graph, onNavigateNode }: FinalKgInspectorProps) {
  const [resolving, setResolving] = useState(false)

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

  if (!node) {
    return (
      <aside className="cg-inspector">
        <div className="cg-inspector-empty">
          <span className="cg-inspector-empty-icon">◎</span>
          <p>未选择节点</p>
          <span>在画布中点击节点查看详情</span>
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
  if (node.type === 'connection') {
    basicRows.push({ label: '投射类型', value: node.label })
    basicRows.push({ label: '方向性', value: directionalityOf(graph, node) })
  }

  const provenanceRows: DetailRow[] = Object.entries(node.metadata.raw).map(([key, value]) => ({
    label: key,
    value: typeof value === 'object' ? JSON.stringify(value) : String(value),
  }))

  const sections = relationSectionsOf(graph, node)
  const hasHierarchySection = node.type === 'brain_region' || node.type === 'function'

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

      <SectionCard title="Basic Information">
        <RowList rows={basicRows} />
      </SectionCard>

      {hasHierarchySection && (
        <SectionCard title="Hierarchy">
          <span className="oc-muted">图中未携带层级数据（父/子脑区需接入层级端点）</span>
        </SectionCard>
      )}

      {sections.map(section => (
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
      ))}

      <SectionCard title="Provenance">
        {provenanceRows.length > 0 ? <RowList rows={provenanceRows} /> : <EmptyState title="No provenance on record" />}
      </SectionCard>
    </aside>
  )
}
