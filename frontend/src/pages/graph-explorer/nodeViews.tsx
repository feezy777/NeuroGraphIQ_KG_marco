/**
 * Canonical KG Explorer V3 节点视觉（科研级脑网络探索器风格）：
 * - brain_region：白色圆角胶囊卡（细蓝色描边 + 柔和阴影 + 脑区 icon +
 *   名称优先 + type 小字 + granularity 徽章 + confidence 微字）
 * - connection（若曾作为节点出现）：小型弱化圆形（数据上连接已折叠为边,此视图仅兜底）
 * - circuit：紫系胶囊；function：琥珀橙胶囊；circuit_step/evidence：纸灰系
 * - 数据展示原则：名称优先；不显示 uuid / 数据库 id
 * - 选中：放大 1.06 + 光环 halo（box-shadow 双层）+ 高亮边框（网络核心效果）
 * - hover：tooltip（Name / Type / Granularity / Connection count / Evidence count；
 *   计数来自 toXyflowNodes 派生的 nodeStats,不触碰后端）
 */
import type { NodeProps } from '@xyflow/react'
import { Brain, CircuitBoard, FileText, Link2, ListOrdered, Sigma } from 'lucide-react'
import {
  CANONICAL_NODE_TYPE_LABELS,
  type CanonicalNode,
} from './adapters/finalKgAdapter'
import { canonicalNodeOf } from './graphToXyflow'
import { NODE_TYPE_COLORS } from './graphTheme'

// ── 字段提取（防御式）：统一次级信息行 ────────────────────────────────────────────

function strOf(raw: Record<string, unknown>, key: string): string | null {
  const v = raw[key]
  return typeof v === 'string' && v.trim() ? v : null
}

function connectionLabelOf(data: Record<string, unknown>): string | null {
  const v = data?.connectionLabel
  return typeof v === 'string' && v.trim() ? v : null
}

/** confidence 0.92 → "confidence 0.92"；缺失 → null（不渲染） */
function confidenceText(value: number | null): string | null {
  if (value == null || !Number.isFinite(value)) return null
  return `confidence ${Math.round(value * 100) / 100}`
}

/** tooltip 统计（toXyflowNodes 派生；缺失时诚实降级为 null） */
interface NodeStats {
  connectionCount: number | null
  evidenceCount: number | null
}

function statsOf(data: Record<string, unknown>): NodeStats {
  const s = data?.nodeStats as NodeStats | undefined
  return {
    connectionCount: s?.connectionCount ?? null,
    evidenceCount: s?.evidenceCount ?? null,
  }
}

// ── 知识卡片通用骨架：icon 徽章 + 主体（名称/类型/徽章/置信度）+ tooltip ─────────

function NodeCard({
  type,
  label,
  raw,
  data,
  icon,
  accent,
  granularity,
}: {
  type: CanonicalNode
  label: string
  raw: Record<string, unknown>
  data: Record<string, unknown>
  icon: React.ReactNode
  accent: string
  granularity: string | null
}) {
  const stats = statsOf(data)
  const conf = confidenceText(type.metadata.confidence)
  const cnName = strOf(raw, 'cn_name')
  return (
    <>
      <span className="kg-node-icon" style={{ color: accent, background: `${accent}14` }}>
        {icon}
      </span>
      <span className="kg-node-body">
        <span className="kg-node-primary">{label}</span>
        <span className="kg-node-type">{CANONICAL_NODE_TYPE_LABELS[type.type]}</span>
        <span className="kg-node-badges">
          {granularity && <span className="kg-node-badge">{granularity}</span>}
          {conf && <span className="kg-node-conf">{conf}</span>}
        </span>
      </span>
      <span className="kg-node-tooltip">
        <span className="kg-node-tooltip-name">{label}</span>
        <span className="kg-node-tooltip-row">
          <span>Type</span>
          <strong>{CANONICAL_NODE_TYPE_LABELS[type.type]}</strong>
        </span>
        {granularity && (
          <span className="kg-node-tooltip-row">
            <span>Granularity</span>
            <strong>{granularity}</strong>
          </span>
        )}
        {stats.connectionCount != null && (
          <span className="kg-node-tooltip-row">
            <span>Connections</span>
            <strong>{stats.connectionCount}</strong>
          </span>
        )}
        {stats.evidenceCount != null && (
          <span className="kg-node-tooltip-row">
            <span>Evidence</span>
            <strong>{stats.evidenceCount}</strong>
          </span>
        )}
        {cnName && cnName !== label && (
          <span className="kg-node-tooltip-cn">{cnName}</span>
        )}
      </span>
    </>
  )
}

// ── 各类型节点视图 ──────────────────────────────────────────────────────────────

function RegionNodeView({ node, data }: { node: CanonicalNode; data: Record<string, unknown> }) {
  const raw = node.metadata.raw
  const cnName = strOf(raw, 'cn_name')
  const enName = strOf(raw, 'en_name')
  // 名称优先：后端 label(std/en/raw) → 中文名回退
  const primary = node.label || cnName || enName || 'NaN'
  const granularity = node.metadata.granularity ?? strOf(raw, 'granularity_level')
  return (
    <NodeCard
      type={node}
      label={primary}
      raw={raw}
      data={data}
      icon={<Brain size={15} />}
      accent={NODE_TYPE_COLORS.brain_region}
      granularity={granularity}
    />
  )
}

function ConnectionNodeView({ node, data }: { node: CanonicalNode; data: Record<string, unknown> }) {
  const label = connectionLabelOf(data) ?? node.label
  // 数据已折叠为边；此圆形弱化视图仅兜底（旧图或遗留数据）
  return (
    <>
      <span className="kg-node-icon" style={{ color: NODE_TYPE_COLORS.connection, background: '#f0fdfa' }}>
        <Link2 size={13} />
      </span>
      <span className="kg-node-body">
        <span className="kg-node-primary">{label}</span>
        <span className="kg-node-type">{CANONICAL_NODE_TYPE_LABELS[node.type]}</span>
      </span>
    </>
  )
}

function CircuitNodeView({ node, data }: { node: CanonicalNode; data: Record<string, unknown> }) {
  return (
    <NodeCard
      type={node}
      label={node.label}
      raw={node.metadata.raw}
      data={data}
      icon={<CircuitBoard size={14} />}
      accent={NODE_TYPE_COLORS.circuit}
      granularity={node.metadata.granularity ?? null}
    />
  )
}

function FunctionNodeView({ node, data }: { node: CanonicalNode; data: Record<string, unknown> }) {
  return (
    <NodeCard
      type={node}
      label={node.label}
      raw={node.metadata.raw}
      data={data}
      icon={<Sigma size={14} />}
      accent={NODE_TYPE_COLORS.function}
      granularity={node.metadata.granularity ?? null}
    />
  )
}

function CircuitStepNodeView({ node, data }: { node: CanonicalNode; data: Record<string, unknown> }) {
  return (
    <NodeCard
      type={node}
      label={node.label}
      raw={node.metadata.raw}
      data={data}
      icon={<ListOrdered size={13} />}
      accent={NODE_TYPE_COLORS.circuit_step}
      granularity={node.metadata.granularity ?? null}
    />
  )
}

function EvidenceNodeView({ node, data }: { node: CanonicalNode; data: Record<string, unknown> }) {
  return (
    <NodeCard
      type={node}
      label={node.label}
      raw={node.metadata.raw}
      data={data}
      icon={<FileText size={13} />}
      accent={NODE_TYPE_COLORS.evidence}
      granularity={node.metadata.granularity ?? null}
    />
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
      className={`kg-node kg-node-${node.type}${selected ? ' kg-node-selected' : ''}`}
      style={{ '--kg-node-accent': color } as React.CSSProperties}
      title={`${node.label} (${CANONICAL_NODE_TYPE_LABELS[node.type]})`}
    >
      {node.type === 'brain_region' && <RegionNodeView node={node} data={rawData} />}
      {node.type === 'connection' && <ConnectionNodeView node={node} data={rawData} />}
      {node.type === 'circuit' && <CircuitNodeView node={node} data={rawData} />}
      {node.type === 'function' && <FunctionNodeView node={node} data={rawData} />}
      {node.type === 'circuit_step' && <CircuitStepNodeView node={node} data={rawData} />}
      {node.type === 'evidence' && <EvidenceNodeView node={node} data={rawData} />}
    </div>
  )
}

export const nodeTypes = { canonical: CanonicalNodeView }
