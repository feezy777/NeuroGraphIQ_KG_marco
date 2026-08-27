/**
 * Graph Visualization Adapter —— Canonical KG 图谱可视化引擎（Cytoscape.js）。
 *
 * 目标架构：
 *   FinalKgGraphPage
 *     └ FinalKgGraphCanvas（壳：loading/error/hint/legend/右键菜单,接口 props 不变）
 *         └ GraphVisualizationAdapter（本文件：elements 转换 + 布局 + 交互 + 样式）
 *             └ Cytoscape.js（Canvas 渲染器,天然适合大规模图）
 *
 * 职责划分（严格）：
 *   - 本组件**只做图计算与渲染**：CanonicalGraph → cytoscape elements → 布局 → 样式 → 交互;
 *   - 不触碰后端/数据流（useGraphData/adapters/graphFilter 均在外层）;
 *   - selection 经回调上抛（onNodeSelect/onEdgeSelect/onExpandNode）,Inspector 逻辑不受影响。
 *
 * 核心设计：
 *   - 节点：region 圆形（白底细蓝描边）→ connection 圆角胶囊（弱化淡青）→ function 橙圆 →
 *     circuit 紫六边形 → evidence 灰八边形 → step 小灰圆（科研脑网络,非流程图）;
 *   - 边按 relation 分组多态：structural 蓝实线箭头 / has_function 紫虚线 / participates_in(投影)
 *     青绿曲线 / evidence 灰虚线;边 label 默认隐藏,**hover 显示**;
 *   - 布局：radial 确定性布局（中心突出,复用 dagreLayout.hub 分组弧段）;>120 节点自动切
 *     fcose draft（分散/降交叉/速度快）;大图边透明度 0.5 + 二跳节点折叠视觉（lazy expand 语义）;
 *   - 交互：tap 节点/边/空白、dbltap 展开、框选、拖拽、滚轮缩放、hover tooltip
 *     （Entity type / Name / Confidence / Evidence count —— 由 graph 派生,不触碰后端）。
 */
import { useEffect, useMemo, useRef, useState } from 'react'
import cytoscape, { type ElementDefinition, type LayoutOptions, type NodeSingular, type EdgeSingular } from 'cytoscape'
import fcose from 'cytoscape-fcose'
import dagre from 'cytoscape-dagre'
import {
  CANONICAL_NODE_TYPE_LABELS,
  relationGroupOf,
  type CanonicalEdge,
  type CanonicalGraph,
  type CanonicalNode,
  type CanonicalNodeType,
} from './adapters/finalKgAdapter'
import { ENTITY_STYLE_CONFIG } from './entityStyleConfig'
import { RELATION_STYLE_CONFIG } from './relationStyleConfig'
import { fetchMirrorPanoramaGraph } from './adapters/finalEgoGraph'
import './GraphVisualizationAdapter.css'

cytoscape.use(fcose)
cytoscape.use(dagre)

// ── 常量 ─────────────────────────────────────────────────────────────────────────

/** 布局阈值：超过则切换 fcose draft（规模图自动分散） */
export const FCOSE_THRESHOLD = 120
/** 二跳折叠视觉阈值（expand 后 2-hop 节点淡出） */
export const FOLD_THRESHOLD = 140
/** 边 label hover 类名 */
export const EDGE_LABEL_ON = 'edge-label-on'

interface AdapterProps {
  graph: CanonicalGraph
  selectedNodeId: string | null
  dataSource?: 'mirror' | 'final'
  onNodeSelect: (nodeId: string | null) => void
  onEdgeSelect: (edgeId: string | null) => void
  onExpandNode: (nodeId: string) => void
}

// ── elements 转换（纯函数,导出供测试） ──────────────────────────────────────────

/** edge 分组 → cytoscape class（供样式选择器） */
export function relationClassOf(edge: CanonicalEdge): string {
  // 镜像折叠边（type='connection'）：predicate 已映射为统一关系组
  // （structural/has_function/participates_in/evidence）——多色分组,替代全蓝;
  // 其它边沿用既有 relationGroupOf（type 语义）。
  const predicate = edge.metadata.predicate ?? ''
  const isMappedConnection = edge.type === 'connection' &&
    (predicate === 'structural' || predicate === 'has_function' ||
      predicate === 'participates_in' || predicate === 'evidence')
  const group = isMappedConnection ? predicate : relationGroupOf(edge)
  if (group === 'structural') return 'e-structural'
  if (group === 'has_function') return 'e-function'
  if (group === 'participates_in') return 'e-projection'
  return 'e-evidence'
}

export function nodeClassOf(type: CanonicalNodeType): string {
  switch (type) {
    case 'brain_region': return 'n-region'
    case 'connection': return 'n-connection'
    case 'circuit': return 'n-circuit'
    case 'circuit_step': return 'n-step'
    case 'function': return 'n-function'
    case 'evidence': return 'n-evidence'
    default: return 'n-region'
  }
}

/** 可展开判定（与既有 canExpandNode 语义对齐,region 类即中心可扩展） */
export function canExpandAdapter(node: CanonicalNode): boolean {
  return node.type === 'brain_region' || node.type === 'circuit'
}

export interface CyNodeData {
  id: string
  type: CanonicalNodeType
  label: string
  /** 卡片主显示（icon + 名称 + 类型/粒度 --> 多行） */
  show: string
  /** 展示名（名称优先,绝不展示 uuid/数据库 id） */
  name: string
  granularity: string | null
  confidence: number | null
  connectionCount: number
  evidenceCount: number
  /** 中心节点标记（radial 布局 anchor + 视觉突出） */
  isCenter: boolean
  /** 二跳折叠标记（expand 后淡出） */
  folded: boolean
}

export interface CyEdgeData {
  id: string
  source: string
  target: string
  relation: string
  label: string
  direction: string | null
  isConnection: boolean
  confidence: number | null
  evidenceCount: number | null
}

/** 展示名（优先名称,回退 label,绝不落 uuid —— 用户规格） */
export function displayNameOf(node: CanonicalNode): string {
  const cn = typeof node.metadata.raw?.cn_name === 'string' ? node.metadata.raw.cn_name : null
  if (cn && cn !== node.label) return cn
  return node.label || String(node.entityId ?? '')
}

/** CanonicalGraph → cytoscape ElementDefinition[]（纯函数,不修改输入） */
export function toCyElements(graph: CanonicalGraph, centerNodeId: string | null): ElementDefinition[] {
  const nodes: ElementDefinition[] = graph.nodes.map((n, i) => {
    const raw = n.metadata.raw as Record<string, unknown>
    const cn = typeof raw.cn_name === 'string' ? raw.cn_name : null
    return {
      group: 'nodes',
      position: {
        // 确定性 grid 初始位（fcose randomize:false 需要基础位置,防 undefined 崩溃）
        x: (i % 24) * 92,
        y: Math.floor(i / 24) * 92,
      },
      data: {
        id: n.id,
        type: n.type,
        label: n.label,
        show: (ENTITY_STYLE_CONFIG[n.type]?.icon ?? '') + ' ' + (cn || n.label || '—') + '\n' + CANONICAL_NODE_TYPE_LABELS[n.type] + (n.metadata.granularity ? ' · ' + n.metadata.granularity : ''),
        name: cn || n.label || '—',
        granularity: n.metadata.granularity ?? null,
        confidence: n.metadata.confidence ?? null,
        connectionCount: 0,
        evidenceCount: 0,
        isCenter: centerNodeId ? n.id === centerNodeId : false,
        folded: false,
      } satisfies CyNodeData,
      classes: nodeClassOf(n.type),
    }
  })

  const byId = new Map(graph.nodes.map(n => [n.id, n]))
  const edges: ElementDefinition[] = []
  for (const e of graph.edges) {
    if (!byId.has(e.source) || !byId.has(e.target)) continue
    const meta = e.metadata.raw?.connection as
      | { connection_type?: string; direction?: string; confidence?: number | null; evidence_count?: number | null }
      | undefined
    edges.push({
      group: 'edges',
      data: {
        id: e.id,
        source: e.source,
        target: e.target,
        relation: relationGroupOf(e),
        label: meta?.connection_type ?? e.metadata.predicate ?? e.label ?? '',
        direction: meta?.direction ?? null,
        isConnection: e.type === 'connection',
        confidence: meta?.confidence ?? null,
        evidenceCount: meta?.evidence_count ?? null,
      } satisfies CyEdgeData,
      classes: relationClassOf(e),
    })
  }
  // z-order 约定：edges 先创建（lower）、nodes 后创建（upper）→ 节点 tap 优先于
  // 穿过节点中央的放射边（cytoscape 上层元素先命中）
  return [...edges, ...nodes]
}

// ── 样式（科研级脑网络;单一风格函数） ─────────────────────────────────────────────

type CyStyleProps = Record<string, unknown>

/** 节点基础样式（科研级：白底 + 细描边 + 柔和阴影 + 底部名称） */
function nodeStyle(color: string, background: string, size: number): CyStyleProps {
  return {
    'background-color': background,
    'border-color': color,
    'border-width': 2,
    width: size,
    height: size,
    shape: 'ellipse',
    // 节点文字：默认隐藏（防密集区遮挡）;hover 显示名称/类型/粒度
    'label': '',
    'font-size': 7.5,
    'color': '#0f172a',
    'text-valign': 'center',
    'text-halign': 'center',
    'text-margin-y': 8,
    'text-wrap': 'wrap',
    'text-max-width': 72,
    'overlay-opacity': 0,
    'text-outline-color': '#ffffff',
    'text-outline-width': 2.4,
    'text-outline-opacity': 1,
    'shadow-blur': 8,
    'shadow-color': 'rgba(15,23,42,0.14)',
    'shadow-offset-y': 2,
    'shadow-opacity': 1,
  }
}

export function buildStyle(): cytoscape.StylesheetStyle[] {
  return [
    {
      selector: 'node',
      style: {
        'overlay-opacity': 0,
        'transition-property': 'opacity',
        'transition-duration': 100,
        // 节点显式高于边：渲染与命中顺序一致 → tap 节点优先（放射边不再截获）
        'z-index': 10,
      },
    },
    { selector: 'node.n-region', style: nodeStyle(ENTITY_STYLE_CONFIG.brain_region.color, ENTITY_STYLE_CONFIG.brain_region.background, ENTITY_STYLE_CONFIG.brain_region.size) },
    {
      selector: 'node.n-connection',
      style: {
        ...nodeStyle(ENTITY_STYLE_CONFIG.connection.color, ENTITY_STYLE_CONFIG.connection.background, ENTITY_STYLE_CONFIG.connection.size),
        shape: 'round-rectangle',
        'text-max-width': 60,
        'border-style': 'dashed',
      },
    },
    {
      selector: 'node.n-function',
      style: nodeStyle(ENTITY_STYLE_CONFIG.function.color, ENTITY_STYLE_CONFIG.function.background, ENTITY_STYLE_CONFIG.function.size),
    },
    {
      selector: 'node.n-circuit',
      style: {
        ...nodeStyle(ENTITY_STYLE_CONFIG.circuit.color, ENTITY_STYLE_CONFIG.circuit.background, ENTITY_STYLE_CONFIG.circuit.size),
        shape: 'hexagon',
      },
    },
    {
      selector: 'node.n-step',
      style: nodeStyle(ENTITY_STYLE_CONFIG.circuit_step.color, ENTITY_STYLE_CONFIG.circuit_step.background, ENTITY_STYLE_CONFIG.circuit_step.size),
    },
    {
      selector: 'node.n-evidence',
      style: {
        ...nodeStyle(ENTITY_STYLE_CONFIG.evidence.color, ENTITY_STYLE_CONFIG.evidence.background, ENTITY_STYLE_CONFIG.evidence.size),
        shape: 'octagon',
        'border-style': 'dashed',
      },
    },
    { selector: 'node.folded', style: { opacity: 0.42, 'label': '' } },
    {
      selector: 'node.isCenter',
      style: {
        'border-width': 2.8,
        'shadow-blur': 16,
        'shadow-color': 'rgba(59,130,246,0.34)',
        'shadow-offset-y': 2,
        'shadow-opacity': 1,
        width: ENTITY_STYLE_CONFIG.brain_region.size * 1.22,
        height: ENTITY_STYLE_CONFIG.brain_region.size * 1.22,
      },
    },
    /* focus 模式：无关节点/边整体降低透明度（点击节点后由交互动态加类） */
    { selector: 'node.dim', style: { opacity: 0.24 } },
    { selector: 'edge.dim', style: { opacity: 0.1 } },
    {
      selector: 'node:selected',
      style: { 'border-width': 3, 'overlay-color': 'rgba(59,130,246,0.16)', 'overlay-opacity': 1 },
    },

    // ── 边（多态 + hover label） ──
    {
      selector: 'edge',
      style: {
        'z-index': 1,
        'width': 1.4,
        'curve-style': 'bezier',
        'target-arrow-shape': 'triangle',
        'arrow-scale': 0.75,
        'target-arrow-color': '#94a3b8',
        'line-color': '#94a3b8',
        'opacity': 0.82,
        'label': '',
        'font-size': 8,
        'color': '#334155',
        'text-background-color': '#ffffff',
        'text-background-opacity': 0.9,
        'text-background-padding': 2,
        'text-rotation': 'autorotate',
        'overlay-opacity': 0,
      },
    },
    {
      selector: 'edge.e-structural',
      style: { 'line-color': RELATION_STYLE_CONFIG.structural.color, 'target-arrow-color': RELATION_STYLE_CONFIG.structural.color, width: RELATION_STYLE_CONFIG.structural.width + 0.2 },
    },
    {
      selector: 'edge.e-function',
      style: {
        'line-color': RELATION_STYLE_CONFIG.has_function.color,
        'target-arrow-color': RELATION_STYLE_CONFIG.has_function.color,
        'line-style': 'dashed',
      },
    },
    {
      selector: 'edge.e-projection',
      style: {
        'line-color': RELATION_STYLE_CONFIG.participates_in.color,
        'target-arrow-color': RELATION_STYLE_CONFIG.participates_in.color,
        'curve-style': 'bezier',
      },
    },
    {
      selector: 'edge.e-evidence',
      style: {
        'line-color': RELATION_STYLE_CONFIG.evidence.color,
        'target-arrow-color': RELATION_STYLE_CONFIG.evidence.color,
        'line-style': 'dashed',
        opacity: 0.6,
      },
    },
    { selector: `edge.${EDGE_LABEL_ON}`, style: { 'label': 'data(label)' } },
    { selector: 'edge:selected', style: { 'line-opacity': 1, width: 2.4 } },
    { selector: 'edge.hovered', style: { opacity: 1, width: 3.2 } },
  ]
}

// ── 布局 ─────────────────────────────────────────────────────────────────────────


/**
 * 全景布局种子（层级簇）：供 fcose randomize:false 作为初始位——
 *   region      中心层（半径 ~420,随数自适应）
 *   circuit/step 外层第一层
 *   function    外层第二层
 *   evidence    最外层（默认隐藏层）
 * 层间大间隔（防换层重叠）,组内确定性排序等分;节点尺寸防碰撞（弧长自适配半径）。
 */
export function seedPositionsByType(graph: CanonicalGraph): Map<string, { x: number; y: number }> {
  const out = new Map<string, { x: number; y: number }>()

  const rings: { type: CanonicalNodeType; radius: number }[] = [
    { type: 'brain_region', radius: 500 },
    { type: 'circuit', radius: 900 },
    { type: 'circuit_step', radius: 900 },
    { type: 'function', radius: 1000 },
    { type: 'evidence', radius: 1250 },
  ]

  for (const ring of rings) {
    const members = graph.nodes
      .filter(n => n.type === ring.type)
      .sort((a, b) => (keyOf(a) < keyOf(b) ? -1 : 1))
    const n = members.length
    if (n === 0) continue
    const size = ENTITY_STYLE_CONFIG[ring.type]?.size ?? 44
    // 防碰撞：弧长不足以容纳时扩半径（保持整层间距比例）
    const gap = size + 22
    const radius = Math.max(ring.radius, (gap * n) / (2 * Math.PI * 0.94) + 60)
    const gapA = 0.04
    const span = 2 * Math.PI - gapA * n
    members.forEach((node, i) => {
      const angle = -Math.PI / 2 + gapA / 2 + (span * i) / Math.max(n, 1)
      out.set(node.id, {
        x: radius * Math.cos(angle) - size / 2,
        y: radius * Math.sin(angle) - size / 2,
      })
    })
  }

  const unknown = graph.nodes.filter(n => !out.has(n.id))
  unknown.sort((a, b) => (keyOf(a) < keyOf(b) ? -1 : 1)).forEach((node, i) => {
    out.set(node.id, { x: (i % 12) * 90 - 495, y: 0 })
  })
  return out
}

/**
 * 语义分层布局（semantic layered layout）：
 *   Layer 0 —— 中心实体（画布中心原点）
 *   Layer 1 —— Connection + 与中心直接相关的 BrainRegion（内环）
 *   Layer 2 —— Circuit / Function（中外环）
 *   Layer 3 —— Evidence（外环）
 * 环内按实体类型分连续弧段（减少交叉,同类型聚团）,确定性排序（label+id）。
 * 中心通过 id == centerNodeId 锚定（此函数接受 centerId 参数,测试可注入）。
 */
export function semanticLayeredPositions(
  graph: CanonicalGraph,
  centerId: string,
): Map<string, { x: number; y: number }> {
  const out = new Map<string, { x: number; y: number }>()
  const byId = new Map(graph.nodes.map(n => [n.id, n]))

  // ── 与中心直连的节点（1-hop） ──
  const direct = new Set<string>()
  for (const e of graph.edges) {
    if (e.source === centerId) direct.add(e.target)
    if (e.target === centerId) direct.add(e.source)
  }

  const layerOf = (n: CanonicalNode): number => {
    if (n.id === centerId) return 0
    if (n.type === 'brain_region' || n.type === 'connection' || direct.has(n.id)) return 1
    if (n.type === 'circuit' || n.type === 'function' || n.type === 'circuit_step') return 2
    return 3
  }

  // ── 同心环半径（随各环数量微调,8pt 网格） ──
  const counts = [0, 0, 0, 0]
  for (const n of graph.nodes) counts[layerOf(n)] += 1
  // 用户规格：层级间距放大 ×2 / ×2.5 / ×3（节点距离明显增加,减少中心堆叠）
  const base1 = 200 + 22 * Math.sqrt(Math.max(counts[1], 1))
  const base2 = base1 + 180 + 22 * Math.sqrt(Math.max(counts[2], 1))
  const base3 = base2 + 170 + 20 * Math.sqrt(Math.max(counts[3], 1))
  const r1 = base1 * 2
  const r2 = base2 * 2.5
  const r3 = base3 * 3
  // collision avoidance：环弧长不足以容纳 (size+gap)*n 个节点时,自动扩半径防重叠
  const avoidOverlap = (radius: number, n: number) => {
    if (n <= 0) return radius
    const needed = ((ENTITY_STYLE_CONFIG.brain_region.size + 18) * n) / (2 * Math.PI * 0.92)
    return Math.max(radius, needed)
  }
  const radiusOf = (layer: number) => {
    const raw = layer === 1 ? r1 : layer === 2 ? r2 : r3
    return avoidOverlap(raw, counts[layer] ?? 0)
  }

  // center 固定画布中心
  out.set(centerId, { x: 0, y: 0 })

  // ── 每层:按类型分段弧（类型序来自实体配置图例顺序,段内按确定性键排序） ──
  const typeOrder: CanonicalNodeType[] = ['brain_region', 'connection', 'circuit', 'circuit_step', 'function', 'evidence']
  for (let layer = 1; layer <= 3; layer++) {
    const members = graph.nodes.filter(n => layerOf(n) === layer)
    if (members.length === 0) continue
    const groups: { type: CanonicalNodeType; items: CanonicalNode[] }[] = []
    for (const t of typeOrder) {
      const items = members
        .filter(n => n.type === t)
        .sort((a, b) => (keyOf(a) < keyOf(b) ? -1 : 1))
      if (items.length > 0) groups.push({ type: t, items })
    }
    const total = groups.reduce((s, g) => s + g.items.length, 0)
    const radius = radiusOf(layer)
    const gap = 0.05
    let cursor = -Math.PI / 2
    for (const g of groups) {
      const span = (2 * Math.PI) * (g.items.length / total)
      const usable = span - gap * (groups.length > 1 ? 1 : 0)
      const start = cursor + gap / 2
      g.items.forEach((n, i) => {
        const angle = start + (usable * (i + 0.5)) / g.items.length
        const half = (ENTITY_STYLE_CONFIG[n.type]?.size ?? 44) / 2
        out.set(n.id, {
          x: radius * Math.cos(angle) - half,
          y: radius * Math.sin(angle) - half,
        })
      })
      cursor += span
    }
    void byId
  }
  return out
}

function keyOf(n: CanonicalNode): string {
  return `${n.type}|${n.label}|${n.id}`
}

interface FcoseOptions {
  name?: string
  quality?: string
  randomize?: boolean
  animate?: boolean
  nodeRepulsion?: number
  idealEdgeLength?: number
  gravity?: number
  numIter?: number
  nodeSeparation?: number
}

/** fcose 参数（中小图：高质量放射/凝聚网络形） */
function fcoseOptions(n: number): FcoseOptions {
  return {
    name: 'fcose',
    quality: 'default',
    randomize: false,
    animate: false,
    nodeRepulsion: 6000,
    idealEdgeLength: 84,
    gravity: 0.28,
    numIter: 2600,
    nodeSeparation: 90,
  }
}

/** 内置 cose 参数（规模图：稳定快,不卡主线程;实测 1000/5000 ≈1.5s） */
function coseOptions(): LayoutOptions {
  return {
    name: 'cose',
    randomize: false,
    animate: false,
    nodeRepulsion: 8000,
    nodeOverlap: 24,
    idealEdgeLength: 70,
    gravity: 0.6,
    numIter: 1200,
    coolingFactor: 0.95,
  }
}

/**
 * 布局选择（导出供测试/基准共用同构）：
 * - ≤FCOSE_THRESHOLD 节点：fcose default（质量优先,中心凝聚好）
 * - 更大规模：内置 cose（稳定 + 快;避开 fcose 'draft' 的 headless 崩溃路径）
 *   另:>400 边自动边降透明（组件内处理）。
 */
export function layoutOptionsOf(graph: CanonicalGraph): LayoutOptions {
  if (graph.nodes.length > FCOSE_THRESHOLD) return coseOptions()
  return fcoseOptions(graph.nodes.length) as unknown as LayoutOptions
}

// ── 组件 ─────────────────────────────────────────────────────────────────────────

export function GraphVisualizationAdapter({
  graph,
  selectedNodeId,
  onNodeSelect,
  onEdgeSelect,
  onExpandNode,
}: AdapterProps) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const cyRef = useRef<cytoscape.Core | null>(null)
  const tooltipRef = useRef<HTMLDivElement | null>(null)
  const miniRef = useRef<HTMLCanvasElement | null>(null)
  const [tooltip, setTooltip] = useState<{ x: number; y: number; rows: [string, string][] } | null>(null)
  const cbRef = useRef({ onNodeSelect, onEdgeSelect, onExpandNode })
  cbRef.current = { onNodeSelect, onEdgeSelect, onExpandNode }

  // ── 浏览模式：探索（Ego 1-hop 语义分层）/ 全景（全量图,fcose 大图布局） ──
  const [mode, setMode] = useState<'explore' | 'panorama'>('panorama')
  const [panoramaGraph, setPanoramaGraph] = useState<CanonicalGraph | null>(null)
  const [panoramaLoading, setPanoramaLoading] = useState(false)
  const [magnifier, setMagnifier] = useState(false)
  /** Evidence 层显示开关（默认隐藏,开启后拉取 mirror evidence 并置于最外环） */
  const [showEvidence, setShowEvidence] = useState(false)
  const evidenceWantedRef = useRef(false)
  /** 重新布局：+1 触发 cy 重建（重跑当前模式布局） */
  const [layoutTick, setLayoutTick] = useState(0)

  // 全景数据：Mirror KG 全局窗口（真全局网络,非局部查询;零 mock;窗口化诚实标注）
  useEffect(() => {
    if (mode !== 'panorama') return
    const needRefetch = panoramaGraph === null || evidenceWantedRef.current !== showEvidence
    if (!needRefetch) return
    evidenceWantedRef.current = showEvidence
    let cancelled = false
    setPanoramaLoading(true)
    fetchMirrorPanoramaGraph(showEvidence)
      .then(g => { if (!cancelled) setPanoramaGraph(g) })
      .catch(() => { if (!cancelled) setPanoramaGraph({ nodes: [], edges: [], centerNodeId: null, warnings: ['Mirror 全景数据加载失败'] }) })
      .finally(() => { if (!cancelled) setPanoramaLoading(false) })
    return () => { cancelled = true }
  }, [mode, panoramaGraph, showEvidence])

  const dataGraph = mode === 'panorama' ? (panoramaGraph ?? graph) : graph

  // elements（纯转换 + 派生 stat）
  const elements = useMemo(() => {
    const els = toCyElements(dataGraph, dataGraph.centerNodeId)
    const nodes = els.filter(e => e.group === 'nodes') as ElementDefinition[]
    const stats = new Map<string, { c: number; ev: number }>()
    for (const e of els) {
      if (e.group !== 'edges') continue
      const d = e.data as unknown as CyEdgeData
      for (const id of [d.source, d.target]) {
        const cur = stats.get(id) ?? { c: 0, ev: 0 }
        if (d.isConnection) cur.c += 1
        else if (d.relation === 'evidence') cur.ev += 1
        stats.set(id, cur)
      }
    }
    for (const n of nodes) {
      const d = n.data as unknown as CyNodeData
      const s = stats.get(d.id) ?? { c: 0, ev: 0 }
      d.connectionCount = s.c
      d.evidenceCount = s.ev
    }
    return els
  }, [dataGraph])

  // 布局：探索 → semantic layered;
  // 全景 → fcose（region 中心层 / circuit·function 外层 / evidence 最外 ——
  // 以类型分层簇为种子初值,randomize:false 保留层意同时铺开）;
  // 规模图（explore 且 >阈值）→ 内置 cose。
  const layoutMode = useMemo(() => {
    const centerId = dataGraph.centerNodeId ?? dataGraph.nodes[0]?.id ?? ''
    if (centerId && mode === 'explore' && dataGraph.nodes.length <= FCOSE_THRESHOLD) {
      return { kind: 'radial' as const, positions: semanticLayeredPositions(dataGraph, centerId) }
    }
    if (mode === 'panorama') {
      return { kind: 'panorama' as const, positions: seedPositionsByType(dataGraph) }
    }
    return { kind: 'force' as const, positions: null }
  }, [dataGraph, mode])

  /** fit padding 按规模动态（<50:80 / 50-200:150 / >200:250） */
  const fitPadding = useMemo(() => {
    const n = dataGraph.nodes.length
    if (n < 50) return 80
    if (n <= 200) return 150
    return 250
  }, [dataGraph])

  // 初始化 / 数据变化 → 重建 cy（幂等销毁,防泄漏）
  useEffect(() => {
    const container = containerRef.current
    if (!container) return

    const cy = cytoscape({
      container,
      elements,
      style: buildStyle(),
      boxSelectionEnabled: true,
      selectionType: 'additive',
      minZoom: 0.03,
      maxZoom: 3,
      wheelSensitivity: 0.12,
    })
    cyRef.current = cy

    // 布局
    if (layoutMode.kind === 'radial') {
      cy.layout({
        name: 'preset',
        positions: (node: NodeSingular) => layoutMode.positions.get(node.id()) ?? { x: 0, y: 0 },
        fit: true,
        padding: fitPadding,
      } as unknown as LayoutOptions).run()
    } else if (layoutMode.kind === 'panorama') {
      // cose 系力导向（cose-bilkent 同族）：nodeRepulsion 3-5x(6000→24000) /
      // idealEdgeLength 240 / gravity 0.1 / nodeSeparation 120;以类型分层簇为种子
      // （randomize:false 保留层界：region 中心·circuit 外1·function 外2·evidence 最外）。
      // 实测 1112 节点/10000 边 = 889ms;fcose(默认质量)该规模实测 ~39s,故采用 cose 参数族。
      cy.layout({
        name: 'cose',
        randomize: false,
        animate: false,
        nodeRepulsion: 60000,
        nodeSeparation: 150,
        idealEdgeLength: 260,
        gravity: 0.06,
        numIter: 2000,
        coolingFactor: 0.9,
        positions: (node: NodeSingular) => layoutMode.positions.get(node.id()) ?? { x: 0, y: 0 },
      } as unknown as LayoutOptions).run()
      // 全景 fit：聚焦核心网络（hub 蓝网清晰;function 橙环比邻视野）
      // 5,720 边全连 hub 在整图 scale 下呈高密度雾状——默认放大至 hub 可视区
      cy.fit(cy.elements(), 120)
      // 缩放锚 = region hub 几何中心（蓝网清晰,function 橙环比邻视野;而非画布中心）
      const hubBox = cy.$('node.n-region').boundingBox()
      if (hubBox.w > 0) {
        cy.zoom({
          level: cy.zoom() * 2.4,
          position: { x: (hubBox.x1 + hubBox.x2) / 2, y: (hubBox.y1 + hubBox.y2) / 2 },
        })
      }
    } else {
      cy.layout({ ...(layoutOptionsOf(dataGraph) as object), fit: true, padding: fitPadding } as LayoutOptions).run()
    }

    // 大图透明度（减少视觉噪声;hover 恢复全彩）与默认边 label（≤150 常显）
    if (dataGraph.edges.length > 400) {
      cy.elements('edge').style('opacity', 0.88)
    }
    if (dataGraph.edges.length <= 150 && dataGraph.edges.length > 0) {
      cy.elements('edge').addClass(EDGE_LABEL_ON)
    }

    // ── 交互 ──
    const cb = cbRef.current
    const applyFocus = (nodeId: string) => {
      if (mode !== 'explore') return
      const node = cy.$(`node[id="${nodeId}"]`)
      if (node.empty()) return
      const neighbors = new Set<string>([nodeId])
      node.neighborhood('node').forEach((n: NodeSingular) => { neighbors.add(n.id()) })
      cy.elements('node').removeClass('dim')
      cy.nodes().forEach((n: NodeSingular) => { if (!neighbors.has(n.id())) n.addClass('dim') })
      cy.elements('edge').removeClass('dim')
      cy.edges().forEach((e: EdgeSingular) => {
        if (!neighbors.has(e.source().id()) && !neighbors.has(e.target().id())) e.addClass('dim')
      })
    }
    const clearFocus = () => { cy.elements().removeClass('dim') }

    cy.on('tap', (evt: cytoscape.EventObject) => {
      const rp = evt.renderedPosition
      if (!rp) {
        if (evt.target === cy) { cb.onNodeSelect(null); cb.onEdgeSelect(null); clearFocus() }
        return
      }
      const near = cy.$(`node:near(${rp.x}, ${rp.y}, 24, true)`)
      if (near.nonempty()) {
        const id = (near[0] as NodeSingular).id()
        cb.onNodeSelect(id)
        applyFocus(id)
        return
      }
      const t = evt.target as cytoscape.SingularElementArgument
      if (t.isEdge()) { cb.onEdgeSelect((t as EdgeSingular).id()); return }
    })
    cy.on('dblclick', 'node', (evt: cytoscape.EventObject) => {
      cb.onExpandNode((evt.target as NodeSingular).id())
    })
    cy.on('mouseover', 'node', (evt: cytoscape.EventObject) => {
      const node = evt.target as NodeSingular
      node.addClass('label-on')
      const d = node.data() as unknown as CyNodeData
      const pos = node.renderedPosition()
      setTooltip({
        x: pos.x, y: pos.y,
        rows: [
          ['Entity type', CANONICAL_NODE_TYPE_LABELS[d.type]],
          ['Name', d.name],
          ['Confidence', d.confidence != null ? String(Math.round(d.confidence * 100) / 100) : '—'],
          ['Evidence', String(d.evidenceCount)],
          ...(d.granularity ? [['Granularity', d.granularity] as [string, string]] : []),
        ],
      })
    })
    cy.on('mouseout', 'node', (evt: cytoscape.EventObject) => {
      ;(evt.target as NodeSingular).removeClass('label-on')
      setTooltip(null)
    })
    cy.on('mouseover', 'edge', (evt: cytoscape.EventObject) => {
      const edge = evt.target as EdgeSingular
      edge.addClass(EDGE_LABEL_ON)
      edge.addClass('hovered')
      const d = edge.data() as unknown as CyEdgeData
      const mid = edge.midpoint()
      setTooltip({
        x: mid.x, y: mid.y,
        rows: [
          ['Relation', d.label || d.relation],
          ['Direction', d.direction ?? '—'],
          ['Confidence', d.confidence != null ? String(Math.round(d.confidence * 100) / 100) : '—'],
          ['Evidence', d.evidenceCount != null ? String(d.evidenceCount) : '—'],
        ],
      })
    })
    cy.on('mouseout', 'edge', (evt: cytoscape.EventObject) => {
      ;(evt.target as EdgeSingular).removeClass(EDGE_LABEL_ON)
      ;(evt.target as EdgeSingular).removeClass('hovered')
      setTooltip(null)
    })

    // ── MiniMap（右下角：全节点分布 + 当前视口框;render 节流） ──
    const drawMini = () => {
      const mini = miniRef.current
      if (!mini) return
      const ctx = mini.getContext('2d')
      if (!ctx) return
      const w = mini.width
      const h = mini.height
      ctx.clearRect(0, 0, w, h)
      const nodes = cy.nodes()
      if (nodes.length === 0) return
      const bb = cy.elements().boundingBox({ includeLabels: false })
      const bw = Math.max(bb.w, 1)
      const bh = Math.max(bb.h, 1)
      const pad = 8
      const sx = (w - pad * 2) / bw
      const sy = (h - pad * 2) / bh
      const s = Math.min(sx, sy)
      const ox = pad + (w - pad * 2 - bw * s) / 2 - bb.x1 * s
      const oy = pad + (h - pad * 2 - bh * s) / 2 - bb.y1 * s
      ctx.fillStyle = 'rgba(59,130,246,0.55)'
      nodes.forEach((n: NodeSingular) => {
        const p = n.position()
        const size = Math.max(2, Math.min(6, s * (n.width() || 40) * 0.4))
        ctx.beginPath()
        ctx.arc(p.x * s + ox, p.y * s + oy, size, 0, Math.PI * 2)
        ctx.fill()
      })
      // 视口框
      const vp = {
        x1: (0 - cy.pan().x) / cy.zoom(),
        y1: (0 - cy.pan().y) / cy.zoom(),
        x2: (cy.width() - cy.pan().x) / cy.zoom(),
        y2: (cy.height() - cy.pan().y) / cy.zoom(),
      }
      ctx.strokeStyle = 'rgba(15,23,42,0.35)'
      ctx.lineWidth = 1
      ctx.strokeRect(
        vp.x1 * s + ox, vp.y1 * s + oy,
        (vp.x2 - vp.x1) * s, (vp.y2 - vp.y1) * s,
      )
    }
    let miniTimer: ReturnType<typeof setTimeout> | null = null
    const scheduleMini = () => {
      if (miniTimer) return
      miniTimer = setTimeout(() => {
        miniTimer = null
        drawMini()
      }, 90)
    }
    cy.on('render', scheduleMini)
    cy.on('pan zoom end', scheduleMini)
    drawMini()

    return () => {
      if (miniTimer) clearTimeout(miniTimer)
      cy.destroy()
      cyRef.current = null
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- elements/layoutMode 变化即重建
  }, [elements, layoutMode, fitPadding, mode, layoutTick])

  // 选中同步（外部 Inspector 双向）
  useEffect(() => {
    const cy = cyRef.current
    if (!cy) return
    if (selectedNodeId) {
      cy.elements('node').unselect()
      cy.$(`node[id="${selectedNodeId}"]`).select()
      const n = cy.$(`node[id="${selectedNodeId}"]`)
      if (n.nonempty()) cy.animate({ center: { eles: n }, duration: 380 })
    } else {
      cy.elements('node').unselect()
      cy.elements('edge').unselect()
    }
  }, [selectedNodeId])

  // ── 工具栏控制器 ──
  const cyZoomBy = (factor: number) => {
    const cy = cyRef.current
    if (!cy) return
    const z = Math.min(3, Math.max(0.03, cy.zoom() * factor))
    cy.zoom({ level: z, renderedPosition: { x: cy.width() / 2, y: cy.height() / 2 } })
  }
  const cyFit = () => {
    const cy = cyRef.current
    if (!cy) return
    cy.animate({ fit: { eles: cy.elements(), padding: fitPadding } }, { duration: 300 })
  }
  const cyReset = () => {
    const cy = cyRef.current
    if (!cy) return
    cy.animate({ zoom: 1, pan: { x: 0, y: 0 } }, { duration: 260 })
  }
  const cyFullscreen = async () => {
    const el = containerRef.current
    if (!el) return
    try {
      if (document.fullscreenElement) await document.exitFullscreen()
      else await el.requestFullscreen()
    } catch {
      // 权限受限时忽略(iframe)
    }
  }
  const switchMode = (next: 'explore' | 'panorama') => {
    setMode(next)
    setTooltip(null)
  }

  // 放大镜：激活后 mousemove 更新位置 + 局部放大绘制
  const magnifierCanvasRef = useRef<HTMLCanvasElement | null>(null)
  const magnifierDivRef = useRef<HTMLDivElement | null>(null)
  /** 放大镜：命令式渲染（state 链在密集 mousemove 下不可靠） */
  const handleMagnifierMove = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!magnifier) return
    const lens = magnifierDivRef.current
    const canvas = magnifierCanvasRef.current
    const container = containerRef.current
    if (!lens || !canvas || !container) return
    const rect = container.getBoundingClientRect()
    const x = e.clientX - rect.left
    const y = e.clientY - rect.top
    lens.style.left = `${e.clientX - 125}px`
    lens.style.top = `${e.clientY - 125}px`
    const srcCanvas = container.querySelector('canvas') as HTMLCanvasElement | null
    if (!srcCanvas) return
    try {
      const ctx = canvas.getContext('2d')
      if (!ctx) return
      const scale = srcCanvas.width / Math.max(rect.width, 1)
      const view = 83 // 250px 窗口 / 3x
      const sw = view * scale
      const sx = Math.max(0, x * scale - sw / 2)
      const sy = Math.max(0, y * scale - sw / 2)
      ctx.clearRect(0, 0, canvas.width, canvas.height)
      ctx.imageSmoothingEnabled = true
      ctx.drawImage(srcCanvas, sx, sy, sw, sw, 0, 0, canvas.width, canvas.height)
    } catch {
      // 画布像素读取受限时静默（位置仍跟随）
    }
  }

  return (
    <div className="kg-cy-wrap">
      {/* 探索模式且无数据 → 引导（全景模式首次自动加载,无需搜索） */}
      {mode === 'explore' && dataGraph.nodes.length === 0 && (
        <div className="cg-canvas-hint">
          <p>暂无图谱数据</p>
          <span>在左侧搜索脑区/回路并加载，或双击节点增量展开。</span>
        </div>
      )}
      {/* 全景加载中（Mirror 全局网络:首拉 1 万连接+670 区域+回路/功能） */}
      {mode === 'panorama' && panoramaLoading && (
        <div className="cg-canvas-overlay">
          <div className="cg-spinner" />
          <span>加载 Mirror 全景网络…</span>
        </div>
      )}
      <div
        ref={containerRef}
        className="kg-cy-container"
        onMouseMove={handleMagnifierMove}
      />

      {/* ── 探索模式：「展开更多关系」（加载下一层;数据层 1-hop 起步;全景模式隐藏） ── */}
      {mode === 'explore' && graph.centerNodeId && (
        <div className="kg-expand-slot">
          <button
            type="button"
            className="btn btn-sm btn-primary kg-expand-btn"
            onClick={() => cbRef.current.onExpandNode(graph.centerNodeId ?? '')}
            title="以当前中心加载下一层关系"
          >
            展开更多关系
          </button>
        </div>
      )}

      {/* ── 模式切换（探索 / 全景） ── */}
      <div className="kg-cy-modes" role="tablist" aria-label="图谱浏览模式">
        <button
          type="button"
          role="tab"
          aria-selected={mode === 'explore'}
          className={`kg-cy-mode${mode === 'explore' ? ' is-active' : ''}`}
          onClick={() => switchMode('explore')}
        >
          探索模式
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={mode === 'panorama'}
          className={`kg-cy-mode${mode === 'panorama' ? ' is-active' : ''}`}
          onClick={() => switchMode('panorama')}
        >
          全景模式
        </button>
        {mode === 'panorama' && (
          <>
            <span className="kg-cy-mode-note">
              {panoramaLoading
                ? '加载 Mirror 全景…'
                : panoramaGraph
                  ? `${panoramaGraph.nodes.length.toLocaleString()} 节点 · ${panoramaGraph.edges.length.toLocaleString()} 边`
                  : ''}
            </span>
            <span className="kg-cy-mode-note">{panoramaGraph?.warnings?.[0] ?? ''}</span>
          </>
        )}
      </div>
      {mode === 'panorama' && (
        <label className="kg-evidence-toggle">
          <input
            type="checkbox"
            checked={showEvidence}
            onChange={e => setShowEvidence(e.target.checked)}
          />
          显示 Evidence
        </label>
      )}

      {/* ── 完整工具栏（右上角固定） ── */}
      <div className="kg-cy-toolbar">
        <button type="button" className={`kg-cy-tool${magnifier ? ' is-active' : ''}`} title="放大镜" onClick={() => setMagnifier(v => !v)}>
          🔍<span className="kg-cy-tool-label">放大镜</span>
        </button>
        <button type="button" className="kg-cy-tool" title="放大" onClick={() => cyZoomBy(1.3)}>＋<span className="kg-cy-tool-label">放大</span></button>
        <button type="button" className="kg-cy-tool" title="缩小" onClick={() => cyZoomBy(1 / 1.3)}>－<span className="kg-cy-tool-label">缩小</span></button>
        <button type="button" className="kg-cy-tool" title="适应画布（按规模动态 padding）" onClick={cyFit}>⤢<span className="kg-cy-tool-label">fit</span></button>
        <button type="button" className="kg-cy-tool" title="恢复 100%" onClick={cyReset}>100%<span className="kg-cy-tool-label">恢复</span></button>
        <button type="button" className="kg-cy-tool" title="全屏" onClick={cyFullscreen}>⛶<span className="kg-cy-tool-label">全屏</span></button>
        <button type="button" className="kg-cy-tool kg-cy-tool-expand" title="查看全部关系（全景）" onClick={() => switchMode('panorama')}>
          ⊞<span className="kg-cy-tool-label">全部展开</span>
        </button>
        <button type="button" className="kg-cy-tool" title="重新布局（恢复大图可读性）" onClick={() => setLayoutTick(t => t + 1)}>
          ⟳<span className="kg-cy-tool-label">重新布局</span>
        </button>
      </div>

      {tooltip && (
        <div ref={tooltipRef} className="kg-cy-tooltip" style={{ left: tooltip.x, top: tooltip.y }}>
          {tooltip.rows.map(([k, v], i) => (
            <span key={i} className="kg-cy-tooltip-row"><span>{k}</span><strong>{v}</strong></span>
          ))}
        </div>
      )}

      {/* 放大镜（跟随鼠标;2.5x 局部放大;不改变节点位置;命令式定位） */}
      {magnifier && (
        <div ref={magnifierDivRef} className="kg-cy-magnifier" style={{ left: -400, top: -400 }}>
          <canvas ref={magnifierCanvasRef} width={250} height={250} className="kg-cy-magnifier-canvas" />
          <span className="kg-cy-magnifier-badge">3×</span>
        </div>
      )}

      {/* MiniMap（右下角;全节点分布 + viewport） */}
      <div className="kg-cy-minimap">
        <canvas ref={miniRef} width={176} height={118} />
      </div>
    </div>
  )
}
