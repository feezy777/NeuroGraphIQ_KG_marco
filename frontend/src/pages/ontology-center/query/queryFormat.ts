import type { OntologyQueryResultItem } from '../../../api/ontologyQueryApi'
import { QUERY_CATEGORY_LABELS } from './queryTypes'

/** 方向 → 中文标签（表格方向列） */
export const DIRECTION_LABELS: Record<string, string> = {
  incoming: '传入',
  outgoing: '传出',
}

/** 连接类型（Evidence Summary 统计维度） */
export type ConnectionKind = 'structural' | 'functional' | 'uncertain'

export const CONNECTION_KIND_LABELS: Record<ConnectionKind, string> = {
  structural: '结构连接',
  functional: '功能连接',
  uncertain: '不确定',
}

export function directionLabel(direction: unknown): string {
  return DIRECTION_LABELS[String(direction ?? '')] ?? ''
}

/** 连接类型判定：detail.connection_type 优先，connection_code 前缀兜底（functional_/structural_） */
export function connectionKind(item: OntologyQueryResultItem): ConnectionKind {
  const type = String(item.detail.connection_type ?? '').toLowerCase()
  if (type === 'structural' || type === 'functional') return type
  const code = item.code ?? ''
  if (code.includes('functional_')) return 'functional'
  if (code.includes('structural_')) return 'structural'
  return 'uncertain'
}

/** 表格「类型」列 */
export function categoryLabel(item: OntologyQueryResultItem): string {
  return QUERY_CATEGORY_LABELS[item.category] ?? '其他'
}

/** 表格「关系」列：按分类取 detail 中语义字段，缺失回退 '—' */
export function relationLabel(item: OntologyQueryResultItem): string {
  switch (item.category) {
    case 'connection':
      return String(item.detail.connection_type ?? '—')
    case 'circuit':
      return String(item.detail.circuit_type ?? '—')
    case 'function':
      return String(item.detail.relation_type ?? '—')
    case 'children':
      return '隶属'
    default:
      return String(item.detail.mapping_type ?? item.detail.entity_type ?? '—')
  }
}

interface ConnectionEndpoint {
  canonical_name_cn?: string | null
  canonical_name_en?: string | null
}

/** 表格「实体」列：连接项展示对端脑区（cn||en），其余展示条目名 */
export function displayName(item: OntologyQueryResultItem): string {
  if (item.category === 'connection') {
    const endpoint = (item.detail.endpoint_region ?? {}) as ConnectionEndpoint
    return endpoint.canonical_name_cn || endpoint.canonical_name_en || item.name
  }
  return item.name
}

/** provenance → 友好来源名（表格「来源」列 / Evidence Source 分组） */
export function provenanceLabel(provenance: string | null): string {
  if (!provenance) return '图谱数据'
  if (provenance.startsWith('canonical_connections')) return '连接组学数据'
  if (provenance.startsWith('canonical_region_hierarchy')) return '层级关系数据'
  if (provenance.startsWith('canonical_function')) return '功能注释数据'
  if (provenance.startsWith('canonical_circuit')) return '回路数据'
  if (provenance.startsWith('canonical_multiscale')) return '多尺度数据'
  return provenance
}

export interface ProvenanceGroup {
  label: string
  count: number
  examples: string[]
}

/** 结果按来源分组（数量降序；来源列同名合并） */
export function groupProvenances(items: OntologyQueryResultItem[]): ProvenanceGroup[] {
  const byLabel = new Map<string, ProvenanceGroup>()
  for (const item of items) {
    const label = provenanceLabel(item.provenance)
    let group = byLabel.get(label)
    if (!group) {
      group = { label, count: 0, examples: [] }
      byLabel.set(label, group)
    }
    group.count += 1
    if (item.code && group.examples.length < 2) group.examples.push(item.code)
  }
  return [...byLabel.values()].sort((a, b) => b.count - a.count)
}

/** 置信度 → 百分比展示（null 安全） */
export function confidencePercent(value: number | null): string {
  if (value == null) return '—'
  return `${Math.round(value * 100)}%`
}
