import { useCallback, useEffect, useMemo, useRef, useState, type MouseEvent } from 'react'
import {
  Background,
  BackgroundVariant,
  BaseEdge,
  Controls,
  MarkerType,
  MiniMap,
  ReactFlow,
  useEdgesState,
  useNodesState,
  useReactFlow,
  getStraightPath,
  type Edge,
  type EdgeProps,
  type Node,
  type OnSelectionChangeParams,
} from '@xyflow/react'
import {
  canExpandNode,
  relationGroupOf,
  type CanonicalEdge,
  type CanonicalNode,
  type CanonicalNodeType,
} from './adapters/finalKgAdapter'
import { canExpandMirrorNode } from './adapters/mirrorKgAdapter'
import { canonicalEdgeOf, toXyflowEdges, toXyflowNodes } from './graphToXyflow'
import { EDGE_FALLBACK_COLOR, EDGE_GROUP_COLORS, NODE_TYPE_COLORS } from './graphTheme'
import { layoutCanonicalGraph } from './layout/dagreLayout'
import { nodeTypes } from './nodeViews'

// ── 边渲染 ─────────────────────────────────────────────────────────────────────

function CanonicalEdgeView({ id, sourceX, sourceY, targetX, targetY, data }: EdgeProps) {
  const edge = canonicalEdgeOf(data as Record<string, unknown>)
  const color = edge ? (EDGE_GROUP_COLORS[relationGroupOf(edge)] ?? EDGE_GROUP_COLORS.structural) : EDGE_FALLBACK_COLOR
  const [path] = getStraightPath({ sourceX, sourceY, targetX, targetY })
  return (
    <BaseEdge
      id={id}
      path={path}
      style={{ stroke: color, strokeWidth: 1.5 }}
      markerEnd={MarkerType.ArrowClosed}
      interactionWidth={16}
    />
  )
}

const edgeTypes = { canonical: CanonicalEdgeView }

// ── 上下文菜单 ─────────────────────────────────────────────────────────────────

interface ContextMenuState {
  x: number
  y: number
  nodeId: string
}

interface FinalKgGraphCanvasProps {
  graph: {
    nodes: CanonicalNode[]
    edges: CanonicalEdge[]
    centerNodeId: string | null
    warnings: string[]
  }
  loading: boolean
  error: string | null
  /** 每次成功加载 +1 → 触发 fitView */
  fitKey: number
  /** 当前选中节点 id（由页面持有；用于图重载后保持高亮） */
  selectedNodeId: string | null
  /** 数据源：mirror 模式仅 brain_region 可展开 */
  dataSource?: 'mirror' | 'final'
  onNodeClick: (nodeId: string | null) => void
  onExpandNode: (nodeId: string) => void
}

export function FinalKgGraphCanvas({
  graph,
  loading,
  error,
  fitKey,
  selectedNodeId,
  dataSource = 'final',
  onNodeClick,
  onExpandNode,
}: FinalKgGraphCanvasProps) {
  const [rfNodes, setRfNodes, onNodesChange] = useNodesState<Node>([])
  const [rfEdges, setRfEdges, onEdgesChange] = useEdgesState<Edge>([])
  const [contextMenu, setContextMenu] = useState<ContextMenuState | null>(null)
  const { fitView } = useReactFlow()
  const selectedRef = useRef(selectedNodeId)
  selectedRef.current = selectedNodeId

  // 图数据变化 → 用确定性布局重置节点位置（加载时刻），保持先前选中态
  const nodesForGraph = useMemo(() => {
    const positions = layoutCanonicalGraph(graph.nodes, graph.edges, graph.centerNodeId)
    return toXyflowNodes(graph, positions)
  }, [graph])

  useEffect(() => {
    setRfNodes(nodesForGraph.map(n => ({ ...n, selected: n.id === selectedRef.current })))
  }, [nodesForGraph, setRfNodes])

  useEffect(() => {
    setRfEdges(toXyflowEdges(graph))
  }, [graph, setRfEdges])

  // 加载完成 → fitView（延迟一帧，等节点渲染）
  useEffect(() => {
    if (fitKey > 0 && rfNodes.length > 0) {
      const timer = setTimeout(() => fitView({ padding: 0.15, duration: 400 }), 50)
      return () => clearTimeout(timer)
    }
  }, [fitKey, rfNodes.length, fitView])

  const onSelectionChange = useCallback(
    ({ nodes }: OnSelectionChangeParams) => {
      onNodeClick(nodes.length > 0 ? nodes[0].id : null)
    },
    [onNodeClick],
  )

  const onNodeContextMenu = useCallback((event: MouseEvent, node: Node) => {
    event.preventDefault()
    setContextMenu({ x: event.clientX, y: event.clientY, nodeId: node.id })
  }, [])

  const handleExpand = useCallback(() => {
    if (contextMenu) {
      onExpandNode(contextMenu.nodeId)
      setContextMenu(null)
    }
  }, [contextMenu, onExpandNode])

  const handleHideDetails = useCallback(() => {
    onNodeClick(null)
    setContextMenu(null)
  }, [onNodeClick])

  // 点击空白处关闭菜单
  useEffect(() => {
    if (!contextMenu) return
    const close = () => setContextMenu(null)
    document.addEventListener('click', close)
    return () => document.removeEventListener('click', close)
  }, [contextMenu])

  const menuNode = contextMenu
    ? graph.nodes.find(n => n.id === contextMenu.nodeId)
    : null
  const menuExpandable = menuNode
    ? dataSource === 'mirror'
      ? canExpandMirrorNode(menuNode)
      : canExpandNode(menuNode)
    : false

  // MiniMap 节点配色：由 graph 派生 id → 类型映射（不直接访问后端字段）
  const nodeTypeById = useMemo(() => {
    const map = new Map<string, CanonicalNodeType>()
    for (const n of graph.nodes) map.set(n.id, n.type)
    return map
  }, [graph])

  if (loading) {
    return (
      <div className="cg-canvas">
        <div className="cg-canvas-overlay">
          <div className="cg-spinner" />
          <span>加载图谱数据…</span>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="cg-canvas">
        <div className="cg-error-banner">
          <strong>加载失败：</strong>
          <span>{error}</span>
        </div>
      </div>
    )
  }

  return (
    <div className="cg-canvas">
      {rfNodes.length === 0 && (
        <div className="cg-canvas-hint">
          <p>暂无图谱数据</p>
          <span>在左侧搜索脑区/回路/投射并加载，或右键节点增量展开。</span>
        </div>
      )}
      <ReactFlow
        nodes={rfNodes}
        edges={rfEdges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        onSelectionChange={onSelectionChange}
        onNodeContextMenu={onNodeContextMenu}
        onPaneClick={() => setContextMenu(null)}
        minZoom={0.02}
        fitView
        attributionPosition="bottom-left"
      >
        <Background variant={BackgroundVariant.Dots} gap={24} size={1} color="#e2e8f0" />
        <Controls showInteractive={false} />
        <MiniMap
          nodeStrokeWidth={3}
          nodeColor={n => {
            const type = nodeTypeById.get(n.id)
            return type ? NODE_TYPE_COLORS[type] : EDGE_FALLBACK_COLOR
          }}
          maskColor="rgba(0,0,0,0.08)"
        />
      </ReactFlow>

      {contextMenu && (
        <div className="cg-context-menu" style={{ left: contextMenu.x, top: contextMenu.y }}>
          <button type="button" className="cg-context-item" onClick={handleExpand} disabled={!menuExpandable}>
            Expand（增量展开）
          </button>
          <button type="button" className="cg-context-item" onClick={handleHideDetails}>
            Hide Details
          </button>
        </div>
      )}
    </div>
  )
}
