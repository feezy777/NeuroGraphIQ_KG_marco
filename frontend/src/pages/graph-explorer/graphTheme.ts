/**
 * Canonical KG 图谱主题 —— 配置兼容视图（唯一事实源见 entityStyleConfig /
 * relationStyleConfig）。本文件保留既有导出名（NODE_TYPE_COLORS /
 * EDGE_GROUP_* / NODE 尺寸等）供 Inspector/Sidebar/测试继续引用 ——
 * 全部值派生自统一配置,保证**节点、边、图例三处永远一致**。
 */
import { ENTITY_STYLE_CONFIG } from './entityStyleConfig'
import { RELATION_STYLE_CONFIG, type RelationGroupKey } from './relationStyleConfig'
import type { CanonicalNodeType } from './adapters/finalKgAdapter'

export const NODE_TYPE_COLORS: Record<CanonicalNodeType, string> = {
  brain_region: ENTITY_STYLE_CONFIG.brain_region.color,
  connection: ENTITY_STYLE_CONFIG.connection.color,
  circuit: ENTITY_STYLE_CONFIG.circuit.color,
  circuit_step: ENTITY_STYLE_CONFIG.circuit_step.color,
  function: ENTITY_STYLE_CONFIG.function.color,
  evidence: ENTITY_STYLE_CONFIG.evidence.color,
}

export const EDGE_GROUP_COLORS: Record<string, string> = Object.fromEntries(
  (Object.entries(RELATION_STYLE_CONFIG) as [RelationGroupKey, { color: string }][]).map(([k, v]) => [k, v.color]),
)

export const EDGE_GROUP_DASHED: Record<string, boolean> = Object.fromEntries(
  (Object.entries(RELATION_STYLE_CONFIG) as [RelationGroupKey, { dashed: boolean }][]).map(([k, v]) => [k, v.dashed]),
)

export const EDGE_GROUP_CURVED: Record<string, boolean> = Object.fromEntries(
  (Object.entries(RELATION_STYLE_CONFIG) as [RelationGroupKey, { curved: boolean }][]).map(([k, v]) => [k, v.curved]),
)

export const EDGE_GROUP_WIDTH: Record<string, number> = Object.fromEntries(
  (Object.entries(RELATION_STYLE_CONFIG) as [RelationGroupKey, { width: number }][]).map(([k, v]) => [k, v.width]),
)

/** 未知关系组兜底色 */
export const EDGE_FALLBACK_COLOR = '#94a3b8'

/** 未知关系组线型（默认实线） */
export const EDGE_FALLBACK_DASHED = false

/** 未知关系组曲线（默认直线） */
export const EDGE_FALLBACK_CURVED = false
