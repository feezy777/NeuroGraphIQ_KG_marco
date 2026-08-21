/**
 * Canonical 图 → xyflow 渲染模型转换。
 * Canvas 只消费这里产出的 Node/Edge（data.node / data.edge 为 Canonical 模型），
 * 不允许直接处理后端字段。
 */
import type { Edge, Node } from '@xyflow/react'
import type { CanonicalEdge, CanonicalGraph, CanonicalNode } from './adapters/finalKgAdapter'
import type { Point } from './layout/dagreLayout'

export const XYFLOW_NODE_TYPE = 'canonical'
export const XYFLOW_EDGE_TYPE = 'canonical'

/**
 * 连接节点展示标签派生（Phase 4）：
 * 由 projection_source / projection_target 边的邻接脑区名组成 "source → target"。
 * 纯函数派生自 Canonical 图（不触碰后端字段）；缺一侧时用 '?' 占位，两侧都缺返回空。
 */
export function connectionLabelsOf(graph: CanonicalGraph): Map<string, string> {
  const labelById = new Map(graph.nodes.map(n => [n.id, n.label]))
  const srcOf = new Map<string, string>()
  const tgtOf = new Map<string, string>()
  for (const e of graph.edges) {
    if (e.type === 'projection_source') {
      const label = labelById.get(e.source)
      if (label) srcOf.set(e.target, label)
    } else if (e.type === 'projection_target') {
      const label = labelById.get(e.target)
      if (label) tgtOf.set(e.source, label)
    }
  }
  const out = new Map<string, string>()
  for (const n of graph.nodes) {
    if (n.type !== 'connection') continue
    const src = srcOf.get(n.id)
    const tgt = tgtOf.get(n.id)
    if (src && tgt) out.set(n.id, `${src} → ${tgt}`)
    else if (src || tgt) out.set(n.id, `${src ?? '?'} → ${tgt ?? '?'}`)
  }
  return out
}

export function toXyflowNodes(graph: CanonicalGraph, positions: Map<string, Point>): Node[] {
  const connectionLabels = connectionLabelsOf(graph)
  return graph.nodes.map(n => ({
    id: n.id,
    type: XYFLOW_NODE_TYPE,
    position: positions.get(n.id) ?? { x: 0, y: 0 },
    data: { node: n, connectionLabel: connectionLabels.get(n.id) },
  }))
}

export function toXyflowEdges(graph: CanonicalGraph): Edge[] {
  return graph.edges.map(e => ({
    id: e.id,
    source: e.source,
    target: e.target,
    type: XYFLOW_EDGE_TYPE,
    data: { edge: e },
  }))
}

/** 从 xyflow 节点 data 中还原 Canonical 节点（Canvas 事件回调用） */
export function canonicalNodeOf(data: Record<string, unknown>): CanonicalNode | null {
  const node = data?.node
  return node && typeof node === 'object' && typeof (node as CanonicalNode).id === 'string'
    ? (node as CanonicalNode)
    : null
}

/** 从 xyflow 边 data 中还原 Canonical 边 */
export function canonicalEdgeOf(data: Record<string, unknown>): CanonicalEdge | null {
  const edge = data?.edge
  return edge && typeof edge === 'object' && typeof (edge as CanonicalEdge).id === 'string'
    ? (edge as CanonicalEdge)
    : null
}
