/**
 * Canonical KG Explorer Canvas 壳（图可视化引擎升级）：
 * 图计算/布局/渲染/交互全部委托给 GraphVisualizationAdapter（Cytoscape.js）。
 * 本文件只负责：数据传递 + loading/error/hint + 图例浮层 + 回调上抛。
 *
 * 接口（与页面约定,保持不变）：
 *   graph / loading / error / fitKey / selectedNodeId / dataSource /
 *   onNodeClick / onEdgeClick / onExpandNode
 * → FinalKgGraphPage / Inspector / Sidebar / PathExplorer 零改动。
 */
import { useState } from 'react'
import type { CanonicalEdge, CanonicalGraph, CanonicalNode } from './adapters/finalKgAdapter'
import { GraphVisualizationAdapter } from './GraphVisualizationAdapter'
import { ENTITY_LEGEND_ORDER, entityStyleOf } from './entityStyleConfig'
import { RELATION_LEGEND_ORDER, relationStyleOf } from './relationStyleConfig'

// ── 图例浮层数据 ────────────────────────────────────────────────────────────────

/** 图例数据 —— 与节点/边渲染共同引用 entityStyleConfig / relationStyleConfig（唯一事实源） */
const LEGEND_NODE_TYPES = ENTITY_LEGEND_ORDER
const LEGEND_EDGE_GROUPS = RELATION_LEGEND_ORDER.map(group => ({ group, label: relationStyleOf(group).label }))

interface FinalKgGraphCanvasProps {
  graph: {
    nodes: CanonicalNode[]
    edges: CanonicalEdge[]
    centerNodeId: string | null
    warnings: string[]
  }
  loading: boolean
  error: string | null
  /** 每次成功加载 +1（适配器内以 graph 变化驱动重建+auto-fit,此值保留接口兼容） */
  fitKey: number
  /** 当前选中节点 id（由页面持有；用于图重载后保持高亮） */
  selectedNodeId: string | null
  /** 数据源：mirror / final */
  dataSource?: 'mirror' | 'final'
  onNodeClick: (nodeId: string | null) => void
  /** 点击连接边（折叠边 → Inspector 连接详情） */
  onEdgeClick: (edgeId: string | null) => void
  onExpandNode: (nodeId: string) => void
}

export function FinalKgGraphCanvas({
  graph,
  loading,
  error,
  fitKey,
  selectedNodeId,
  onNodeClick,
  onEdgeClick,
  onExpandNode,
}: FinalKgGraphCanvasProps) {
  const [legendOpen, setLegendOpen] = useState(true)

  return (
    <div className="cg-canvas">
      {/* adapter 常驻：默认全景模式自动加载 Mirror 全局网络（无需先搜索）;
          探索模式数据为空时由 adapter 内部显示引导提示 */}
      <GraphVisualizationAdapter
        graph={graph as CanonicalGraph}
        selectedNodeId={selectedNodeId}
        onNodeSelect={onNodeClick}
        onEdgeSelect={onEdgeClick}
        onExpandNode={onExpandNode}
      />

      {loading && (
        <div className="cg-canvas-overlay">
          <div className="cg-spinner" />
          <span>加载图谱数据…</span>
        </div>
      )}
      {!loading && error && (
        <div className="cg-error-banner">
          <strong>加载失败：</strong>
          <span>{error}</span>
        </div>
      )}

      {/* ── 左下角图例浮层（可折叠；数据全部派生自主题常量） ── */}
      <div className="cg-canvas-legend">
        <button
          type="button"
          className="cg-canvas-legend-toggle"
          onClick={() => setLegendOpen(o => !o)}
          aria-expanded={legendOpen}
        >
          {legendOpen ? '图例 ▾' : '图例 ▸'}
        </button>
        {legendOpen && (
          <div className="cg-canvas-legend-body">
            <div className="cg-canvas-legend-group">
              {LEGEND_NODE_TYPES.map(type => (
                <div key={type} className="cg-legend-row">
                  <span className="cg-legend-swatch" style={{ background: entityStyleOf(type).color }} />
                  <span className="cg-legend-text">{entityStyleOf(type).icon} {entityStyleOf(type).label}</span>
                </div>
              ))}
            </div>
            <div className="cg-canvas-legend-group">
              {LEGEND_EDGE_GROUPS.map(({ group, label }) => (
                <div key={group} className="cg-legend-row">
                  <span
                    className="cg-legend-line"
                    style={{
                      borderTopColor: relationStyleOf(group).color,
                      borderTopStyle: relationStyleOf(group).dashed ? 'dashed' : 'solid',
                    }}
                  />
                  <span className="cg-legend-text">{label}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

// fitKey 保留兼容导出（页面传参不变）
export type { FinalKgGraphCanvasProps }
export const CANVAS_FITKEY_DEFAULT = 0
