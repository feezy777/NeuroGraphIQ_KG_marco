/**
 * Canonical KG Explorer 节点视觉（Phase 4）：
 * - brain_region：蓝色圆角矩形（名称 + 粒度/图谱徽标）
 * - connection：绿色链接卡片（"source → target"，由 Canonical 边派生）
 * - circuit：紫色六边形
 * - function：橙色标签
 * - circuit_step / evidence：灰色小节点
 * 悬浮阴影 + 选中高亮（.cg-node-selected）。
 * 只消费 CanonicalNode / data.connectionLabel，不直接处理后端字段。
 */
import type { NodeProps } from '@xyflow/react'
import {
  CANONICAL_NODE_TYPE_LABELS,
  type CanonicalNode,
} from './adapters/finalKgAdapter'
import { canonicalNodeOf } from './graphToXyflow'
import { NODE_TYPE_COLORS } from './graphTheme'

// ── 字段提取（防御式：后端图节点目前只携带 label，字段缺失时降级）──────────────

function strOf(raw: Record<string, unknown>, key: string): string | null {
  const v = raw[key]
  return typeof v === 'string' && v.trim() ? v : null
}

function connectionLabelOf(data: Record<string, unknown>): string | null {
  const v = data?.connectionLabel
  return typeof v === 'string' && v.trim() ? v : null
}

// ── 各类型节点视图 ──────────────────────────────────────────────────────────────

function RegionNodeView({ node }: { node: CanonicalNode }) {
  const raw = node.metadata.raw
  const cnName = strOf(raw, 'cn_name')
  const enName = strOf(raw, 'en_name')
  // 后端仅下发一个 label（std/en/raw 名）；若 raw 含中英文名则分两行展示
  const primary = cnName ?? node.label
  const secondary = cnName && enName ? enName : null
  const granularity = node.metadata.granularity ?? strOf(raw, 'granularity_level')
  const atlas = strOf(raw, 'source_atlas')
  return (
    <>
      <span className="cg-node-primary">{primary}</span>
      {secondary && <span className="cg-node-secondary">{secondary}</span>}
      {(granularity || atlas) && (
        <span className="cg-node-badges">
          {atlas && <span className="cg-node-badge">{atlas}</span>}
          {granularity && <span className="cg-node-badge">{granularity}</span>}
        </span>
      )}
    </>
  )
}

function ConnectionNodeView({ node, data }: { node: CanonicalNode; data: Record<string, unknown> }) {
  const label = connectionLabelOf(data) ?? node.label
  return (
    <>
      <span className="cg-node-arrow">→</span>
      <span className="cg-node-label">{label}</span>
    </>
  )
}

function CircuitNodeView({ node }: { node: CanonicalNode }) {
  return (
    <span className="cg-node-circuit-inner">
      <span className="cg-node-primary">{node.label}</span>
    </span>
  )
}

function FunctionNodeView({ node }: { node: CanonicalNode }) {
  return (
    <>
      <span className="cg-node-function-icon">ƒ</span>
      <span className="cg-node-label">{node.label}</span>
    </>
  )
}

function CircuitStepNodeView({ node }: { node: CanonicalNode }) {
  return (
    <>
      <span className="cg-node-step-index">▸</span>
      <span className="cg-node-label">{node.label}</span>
    </>
  )
}

function EvidenceNodeView({ node }: { node: CanonicalNode }) {
  return (
    <>
      <span className="cg-node-evidence-icon">⚑</span>
      <span className="cg-node-label">{node.label}</span>
    </>
  )
}

// ── 统一入口 ────────────────────────────────────────────────────────────────────

export function CanonicalNodeView({ data, selected }: NodeProps) {
  const node = canonicalNodeOf(data as Record<string, unknown>)
  if (!node) return null
  const rawData = data as Record<string, unknown>
  const color = NODE_TYPE_COLORS[node.type]
  return (
    <div
      className={`cg-node cg-node-${node.type}${selected ? ' cg-node-selected' : ''}`}
      style={node.type !== 'circuit' ? { borderColor: color } : undefined}
      title={`${node.label} (${CANONICAL_NODE_TYPE_LABELS[node.type]})`}
    >
      {node.type === 'brain_region' && <RegionNodeView node={node} />}
      {node.type === 'connection' && <ConnectionNodeView node={node} data={rawData} />}
      {node.type === 'circuit' && <CircuitNodeView node={node} />}
      {node.type === 'function' && <FunctionNodeView node={node} />}
      {node.type === 'circuit_step' && <CircuitStepNodeView node={node} />}
      {node.type === 'evidence' && <EvidenceNodeView node={node} />}
    </div>
  )
}

export const nodeTypes = { canonical: CanonicalNodeView }
