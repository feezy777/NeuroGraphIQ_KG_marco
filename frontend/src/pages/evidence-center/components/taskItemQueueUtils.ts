import type { PaperEvidenceTaskItem } from '../../../api/endpoints'

/** 未完成(仍待处理)的任务项状态集合 —— 进入待处理队列 */
export const UNFINISHED_ITEM_STATUSES = [
  'pending', 'searching', 'fetching', 'retrieving', 'extracting', 'verifying', 'awaiting_review',
]

export function isUnfinishedItem(item: PaperEvidenceTaskItem): boolean {
  return UNFINISHED_ITEM_STATUSES.includes(item.status)
}

/** 待处理队列排序:置信度升序(低置信度最优先),null 置信度排最前,同置信度按 label(兜底 target_id)稳定排序 */
export function sortByConfidenceAsc(items: PaperEvidenceTaskItem[]): PaperEvidenceTaskItem[] {
  return [...items].sort((a, b) => {
    const ca = a.current_confidence
    const cb = b.current_confidence
    const labelA = a.label || a.target_id
    const labelB = b.label || b.target_id
    if (ca == null && cb == null) return labelA.localeCompare(labelB)
    if (ca == null) return -1
    if (cb == null) return 1
    if (ca !== cb) return ca - cb
    return labelA.localeCompare(labelB)
  })
}

export type TargetTypeGroup = 'circuit' | 'connection' | 'function' | 'other'

/** 队列类型筛选分组:回路 / 连接 / 功能(PRD R4 映射) */
export const TARGET_TYPE_GROUPS: { key: 'circuit' | 'connection' | 'function'; label: string; types: string[] }[] = [
  { key: 'circuit', label: '回路', types: ['circuit', 'circuit_step', 'circuit_function'] },
  { key: 'connection', label: '连接', types: ['connection', 'projection'] },
  { key: 'function', label: '功能', types: ['region_function', 'projection_function'] },
]

export function groupOf(targetType: string): TargetTypeGroup {
  const g = TARGET_TYPE_GROUPS.find(x => x.types.includes(targetType))
  return g ? g.key : 'other'
}
