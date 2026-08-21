/**
 * Canonical KG 图谱主题（Phase 3/4）：
 * 节点类型 / 边关系分组 → 颜色映射。
 * Canvas / Sidebar / Inspector 共享，避免组件间互相 import。
 */
import type { CanonicalNodeType } from './adapters/finalKgAdapter'

export const NODE_TYPE_COLORS: Record<CanonicalNodeType, string> = {
  brain_region: '#3b82f6',
  connection: '#10b981',
  circuit: '#8b5cf6',
  circuit_step: '#64748b',
  function: '#f59e0b',
  evidence: '#9ca3af',
}

export const EDGE_GROUP_COLORS: Record<string, string> = {
  structural: '#64748b',
  has_function: '#f59e0b',
  participates_in: '#8b5cf6',
  evidence: '#9ca3af',
}

/** 未知关系组兜底色 */
export const EDGE_FALLBACK_COLOR = '#94a3b8'
