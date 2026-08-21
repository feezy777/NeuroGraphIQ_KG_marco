/**
 * 确定性图布局（Phase 3）：
 * 基于 @dagrejs/dagre 的分层布局，同一输入 → 同一输出（每次打开位置一致）。
 * 禁止随机布局（不使用 Math.random）。
 *
 * 布局策略（三段带组合）：
 *   Function / Evidence 带   → 上方
 *   中心带（中心节点 + Region / Connection / Circuit Step）→ 居中
 *   Circuit 带               → 下方
 * 各带内部由 dagre LR 排布，节点互不重叠；带间间距 BAND_GAP。
 *
 * 性能护栏（2026-08-21）：dagre 网络单纯形法在大型图上主线程耗时随规模
 * 快速上升（实测 ~600 节点 ≈0.5s、~1600 节点 ≈3.5s）。节点数超过
 * DAGRE_MAX_NODES 时改用确定性网格布局（O(n)，无主线程卡顿），
 * 三段带语义保持一致。
 */
import dagre from '@dagrejs/dagre'
import type { CanonicalEdge, CanonicalNode, CanonicalNodeType } from '../adapters/finalKgAdapter'

export interface Point {
  x: number
  y: number
}

interface Bounds {
  x: number
  y: number
  width: number
  height: number
}

/** 各节点类型的固定尺寸（8pt 网格） */
export const NODE_MEASURES: Record<CanonicalNodeType, { width: number; height: number }> = {
  brain_region: { width: 176, height: 64 },
  connection: { width: 208, height: 52 },
  circuit: { width: 192, height: 96 },
  circuit_step: { width: 136, height: 36 },
  function: { width: 152, height: 40 },
  evidence: { width: 128, height: 32 },
}

/** 带之间的垂直间距 */
export const BAND_GAP = 176

/** dagre 布局的节点数上限：超过则改用确定性网格布局（防大图主线程卡顿） */
export const DAGRE_MAX_NODES = 350

/** 网格布局参数（8pt 网格）：列间距 / 单元格间距 / 每行网格列数 / 行内边距 */
const GRID_COL_GAP = 128
const GRID_CELL_GAP = 48
const GRID_COLS = 6
const GRID_ROW_PADDING = 32

/** 按标签长度估算节点宽度（上限 340px） */
export function measureNode(node: CanonicalNode): { width: number; height: number } {
  const base = NODE_MEASURES[node.type]
  const width = Math.min(340, Math.max(base.width, node.label.length * 9 + 48))
  return { width, height: base.height }
}

/** 单带内 dagre LR 布局；返回节点左上角坐标（xyflow 约定） */
function layoutBand(nodes: CanonicalNode[], edges: CanonicalEdge[]): Map<string, Point> {
  const g = new dagre.graphlib.Graph()
  g.setGraph({ rankdir: 'LR', nodesep: 48, ranksep: 96, marginx: 8, marginy: 8 })
  g.setDefaultEdgeLabel(() => ({}))
  for (const n of nodes) {
    const { width, height } = measureNode(n)
    g.setNode(n.id, { width, height })
  }
  const ids = new Set(nodes.map(n => n.id))
  for (const e of edges) {
    if (ids.has(e.source) && ids.has(e.target)) g.setEdge(e.source, e.target)
  }
  dagre.layout(g)

  const out = new Map<string, Point>()
  for (const n of nodes) {
    const pos = g.node(n.id) as { x: number; y: number } | undefined
    if (!pos) continue
    const { width, height } = measureNode(n)
    // dagre 的 x/y 是节点中心，xyflow 需要左上角
    out.set(n.id, { x: pos.x - width / 2, y: pos.y - height / 2 })
  }
  return out
}

function bandBounds(nodes: CanonicalNode[], positions: Map<string, Point>): Bounds {
  let minX = Infinity
  let minY = Infinity
  let maxX = -Infinity
  let maxY = -Infinity
  for (const n of nodes) {
    const p = positions.get(n.id)
    if (!p) continue
    const { width, height } = measureNode(n)
    minX = Math.min(minX, p.x)
    maxX = Math.max(maxX, p.x + width)
    minY = Math.min(minY, p.y)
    maxY = Math.max(maxY, p.y + height)
  }
  if (!Number.isFinite(minX)) return { x: 0, y: 0, width: 0, height: 0 }
  return { x: minX, y: minY, width: maxX - minX, height: maxY - minY }
}

function shift(positions: Map<string, Point>, dx: number, dy: number): Map<string, Point> {
  const out = new Map<string, Point>()
  for (const [id, p] of positions) out.set(id, { x: p.x + dx, y: p.y + dy })
  return out
}

/**
 * 全图确定性布局：
 * - 中心节点（centerNodeId）永远落在中心带（无论类型）
 * - Function / Evidence 在中心带上方，Circuit 在下方
 * - 各带水平居中对齐
 * - 节点数 > DAGRE_MAX_NODES 时走确定性网格布局（防大图卡顿）
 */
export function layoutCanonicalGraph(
  nodes: CanonicalNode[],
  edges: CanonicalEdge[],
  centerNodeId?: string | null,
): Map<string, Point> {
  if (nodes.length === 0) return new Map()

  if (nodes.length > DAGRE_MAX_NODES) return layoutCanonicalGraphGrid(nodes, centerNodeId)

  const isCenterBand = (n: CanonicalNode): boolean =>
    n.id === centerNodeId || (n.type !== 'function' && n.type !== 'evidence' && n.type !== 'circuit')

  const fnNodes = nodes.filter(n => n.type === 'function' || n.type === 'evidence')
  const circuitNodes = nodes.filter(n => n.type === 'circuit' && n.id !== centerNodeId)
  const centerNodes = nodes.filter(isCenterBand)

  const centerPos = layoutBand(centerNodes, edges)
  const fnPos = layoutBand(fnNodes, edges)
  const circuitPos = layoutBand(circuitNodes, edges)

  const centerBounds = bandBounds(centerNodes, centerPos)
  const fnBounds = bandBounds(fnNodes, fnPos)
  const circuitBounds = bandBounds(circuitNodes, circuitPos)

  const out = new Map<string, Point>()

  // 中心带归一化到原点 (0, 0) 起始
  for (const [id, p] of centerPos) out.set(id, { x: p.x - centerBounds.x, y: p.y - centerBounds.y })

  const centerCX = centerBounds.width / 2

  // Function / Evidence 带：置于中心带上方，水平居中对齐
  if (fnNodes.length > 0) {
    const dx = centerCX - (fnBounds.x + fnBounds.width / 2)
    const dy = -(fnBounds.height + BAND_GAP) - fnBounds.y
    for (const [id, p] of shift(fnPos, dx, dy)) out.set(id, p)
  }

  // Circuit 带：置于中心带下方，水平居中对齐
  if (circuitNodes.length > 0) {
    const dx = centerCX - (circuitBounds.x + circuitBounds.width / 2)
    const dy = centerBounds.height + BAND_GAP - circuitBounds.y
    for (const [id, p] of shift(circuitPos, dx, dy)) out.set(id, p)
  }

  return out
}

// ── 大图确定性网格布局（性能护栏）────────────────────────────────────────────────

/** 确定性排序键：类型 → 标签 → id（禁止随机） */
function gridSortKey(n: CanonicalNode): string {
  return `${n.type}|${n.label}|${n.id}`
}

/** 单列纵向排布（中心带列）：行距按带内最大节点高度自适应 */
function layoutGridColumn(
  items: CanonicalNode[],
  originX: number,
  originY: number,
): { positions: Map<string, Point>; bounds: Bounds } {
  const positions = new Map<string, Point>()
  if (items.length === 0) return { positions, bounds: { x: originX, y: originY, width: 0, height: 0 } }
  const maxW = Math.max(...items.map(n => measureNode(n).width))
  const maxH = Math.max(...items.map(n => measureNode(n).height))
  const rowGap = maxH + GRID_ROW_PADDING
  let maxX = originX
  let maxY = originY
  items.forEach((n, i) => {
    const { width, height } = measureNode(n)
    const x = originX
    const y = originY + i * rowGap
    positions.set(n.id, { x, y })
    maxX = Math.max(maxX, x + width)
    maxY = Math.max(maxY, y + height)
  })
  return { positions, bounds: { x: originX, y: originY, width: maxX - originX, height: maxY - originY } }
}

/** 多列网格排布（Function / Circuit 带） */
function layoutGridBand(
  items: CanonicalNode[],
  originX: number,
  originY: number,
  columns: number,
): { positions: Map<string, Point>; bounds: Bounds } {
  const positions = new Map<string, Point>()
  if (items.length === 0) return { positions, bounds: { x: originX, y: originY, width: 0, height: 0 } }
  const maxW = Math.max(...items.map(n => measureNode(n).width))
  const maxH = Math.max(...items.map(n => measureNode(n).height))
  const cellW = maxW + GRID_CELL_GAP
  const rowGap = maxH + GRID_ROW_PADDING
  let maxX = originX
  let maxY = originY
  items.forEach((n, i) => {
    const { width, height } = measureNode(n)
    const x = originX + (i % columns) * cellW
    const y = originY + Math.floor(i / columns) * rowGap
    positions.set(n.id, { x, y })
    maxX = Math.max(maxX, x + width)
    maxY = Math.max(maxY, y + height)
  })
  return { positions, bounds: { x: originX, y: originY, width: maxX - originX, height: maxY - originY } }
}

/**
 * 大图确定性网格布局（三段带语义与 dagre 路径一致）：
 * - 中心带两列：脑区列（中心节点置顶）| 连接/步骤列，均按确定性排序纵向排布
 * - Function / Evidence 带在上方网格、Circuit 带在下方网格，相对中心带水平居中
 * O(n log n)（仅排序），任意规模不在主线程做迭代求解，不产生卡顿。
 */
function layoutCanonicalGraphGrid(
  nodes: CanonicalNode[],
  centerNodeId?: string | null,
): Map<string, Point> {
  const sorted = [...nodes].sort((a, b) =>
    gridSortKey(a) < gridSortKey(b) ? -1 : gridSortKey(a) > gridSortKey(b) ? 1 : 0,
  )

  const fnNodes = sorted.filter(n => n.type === 'function' || n.type === 'evidence')
  const circuitNodes = sorted.filter(n => n.type === 'circuit' && n.id !== centerNodeId)
  const centerNodes = sorted.filter(
    n => n.id === centerNodeId || (n.type !== 'function' && n.type !== 'evidence' && n.type !== 'circuit'),
  )

  // 中心节点置顶；其余按确定性排序分列（脑区列 | 其他列）
  const centerNode = centerNodes.find(n => n.id === centerNodeId) ?? null
  const rest = centerNodes.filter(n => n.id !== centerNodeId)
  const regionCol = [
    ...(centerNode && centerNode.type === 'brain_region' ? [centerNode] : []),
    ...rest.filter(n => n.type === 'brain_region'),
  ]
  const otherCol = [
    ...(centerNode && centerNode.type !== 'brain_region' ? [centerNode] : []),
    ...rest.filter(n => n.type !== 'brain_region'),
  ]

  const regionBand = layoutGridColumn(regionCol, 0, 0)
  const otherBand = layoutGridColumn(
    otherCol,
    regionBand.bounds.width > 0 ? regionBand.bounds.width + GRID_COL_GAP : 0,
    0,
  )
  const centerBounds: Bounds = {
    x: 0,
    y: 0,
    width: Math.max(
      regionBand.bounds.x + regionBand.bounds.width,
      otherBand.bounds.x + otherBand.bounds.width,
    ),
    height: Math.max(regionBand.bounds.height, otherBand.bounds.height),
  }

  const fnBand = layoutGridBand(fnNodes, 0, 0, GRID_COLS)
  const circuitBand = layoutGridBand(circuitNodes, 0, 0, GRID_COLS)

  const out = new Map<string, Point>(regionBand.positions)
  for (const [id, p] of otherBand.positions) out.set(id, p)

  const centerCX = centerBounds.width / 2

  // Function / Evidence 带：中心带上方，水平居中对齐
  if (fnNodes.length > 0) {
    const dx = centerCX - fnBand.bounds.width / 2
    const dy = -(fnBand.bounds.height + BAND_GAP)
    for (const [id, p] of fnBand.positions) out.set(id, { x: p.x + dx, y: p.y + dy })
  }

  // Circuit 带：中心带下方，水平居中对齐
  if (circuitNodes.length > 0) {
    const dx = centerCX - circuitBand.bounds.width / 2
    const dy = centerBounds.height + BAND_GAP
    for (const [id, p] of circuitBand.positions) out.set(id, { x: p.x + dx, y: p.y + dy })
  }

  return out
}
