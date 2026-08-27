/**
 * 关系类型样式配置（唯一事实源）。
 * 边渲染（GraphVisualizationAdapter）、图例（FinalKgGraphCanvas）、graphTheme.ts
 * 兼容导出的**共同引用** —— 保证边样式与 Legend 永远一致。
 *
 * 语义（用户规格）：
 *   structural_connects_to(connection)   → 蓝色实线
 *   associated_with_function             → 橙色虚线
 *   participates_in / projection         → 紫色实线
 *   supports (evidence)                  → 灰色虚线
 */
export interface RelationStyleDef {
  /** 线色 */
  color: string
  /** 虚线 */
  dashed: boolean
  /** 曲线（投影/参与类,减少平行线） */
  curved: boolean
  /** 线宽 */
  width: number
  /** 图例/边 label 语义名 */
  label: string
}

export type RelationGroupKey = 'structural' | 'has_function' | 'participates_in' | 'evidence'

export const RELATION_STYLE_CONFIG: Record<RelationGroupKey, RelationStyleDef> = {
  structural: { color: '#3b82f6', dashed: false, curved: false, width: 1.8, label: 'Structural' },
  has_function: { color: '#f59e0b', dashed: true, curved: false, width: 1.5, label: 'Functional' },
  participates_in: { color: '#8b5cf6', dashed: false, curved: true, width: 1.5, label: 'Projection' },
  evidence: { color: '#94a3b8', dashed: true, curved: false, width: 1.2, label: 'Evidence' },
}

export const RELATION_LEGEND_ORDER: RelationGroupKey[] = [
  'structural',
  'has_function',
  'participates_in',
  'evidence',
]

export function relationStyleOf(group: RelationGroupKey): RelationStyleDef {
  return RELATION_STYLE_CONFIG[group]
}
