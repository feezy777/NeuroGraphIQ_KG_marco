import type { ModuleKey } from './EvidenceCenterContext'

export interface EvidenceCenterState {
  module: ModuleKey
  taskId: string | null
  targetType: string | null
  targetId: string | null
  paperId: string | null
}

const MODULES: ModuleKey[] = ['tasks', 'papers', 'candidates', 'review', 'promotion']

export function parseEvidenceUrl(hash: string): EvidenceCenterState {
  const raw = hash.replace(/^#/, '')
  const [path, query = ''] = raw.split('?')
  if (path !== '/evidence-center') return { module: 'tasks', taskId: null, targetType: null, targetId: null, paperId: null }
  const params = new URLSearchParams(query)
  const module = MODULES.includes(params.get('module') as ModuleKey) ? (params.get('module') as ModuleKey) : 'tasks'
  return {
    module,
    taskId: params.get('task_id'),
    targetType: params.get('target_type'),
    targetId: params.get('target_id'),
    paperId: params.get('paper_id'),
  }
}

export function buildEvidenceUrl(s: EvidenceCenterState): string {
  const params = new URLSearchParams()
  if (s.module !== 'tasks') params.set('module', s.module)
  if (s.taskId) params.set('task_id', s.taskId)
  if (s.targetType) params.set('target_type', s.targetType)
  if (s.targetId) params.set('target_id', s.targetId)
  if (s.paperId) params.set('paper_id', s.paperId)
  const q = params.toString()
  return `#/evidence-center${q ? `?${q}` : ''}`
}

/** 数据中心 → Evidence Center 候选模块的一次性队列交接 key */
export const INITIAL_QUEUE_KEY = 'evidence-center.initial-queue'

export interface EvidenceQueueHandoffItem {
  target_type: string
  target_id: string
  label: string
  confidence: number | null
}

/**
 * 数据中心入口跳转 Evidence Center 候选模块:
 * - 有 items 时写入 sessionStorage initial-queue(候选模块挂载时恢复队列,一次性消费)
 * - hash 跳转到 candidates,并带首个对象的 target/task 参数
 */
export function navigateToEvidenceCandidates(opts: {
  items?: EvidenceQueueHandoffItem[]
  taskId?: string | null
}): void {
  const { items, taskId } = opts
  if (items?.length) {
    sessionStorage.setItem(INITIAL_QUEUE_KEY, JSON.stringify({ items, taskId: taskId ?? null }))
  }
  const first = items?.[0]
  window.location.hash = buildEvidenceUrl({
    module: 'candidates',
    taskId: taskId ?? null,
    targetType: first?.target_type ?? null,
    targetId: first?.target_id ?? null,
    paperId: null,
  })
}
