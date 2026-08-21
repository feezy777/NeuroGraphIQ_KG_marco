import type { ModuleKey } from './EvidenceCenterContext'

export interface EvidenceCenterState {
  module: ModuleKey
  taskId: string | null
  taskItemId: string | null
  targetType: string | null
  targetId: string | null
  paperId: string | null
}

const MODULES: ModuleKey[] = ['tasks', 'papers', 'candidates', 'review', 'promotion']

const EMPTY_STATE: EvidenceCenterState = {
  module: 'tasks',
  taskId: null,
  taskItemId: null,
  targetType: null,
  targetId: null,
  paperId: null,
}

export function parseEvidenceUrl(hash: string): EvidenceCenterState {
  const raw = hash.replace(/^#/, '')
  const [path, query = ''] = raw.split('?')
  const params = new URLSearchParams(query)
  const parse = (): EvidenceCenterState => {
    const module = MODULES.includes(params.get('module') as ModuleKey)
      ? (params.get('module') as ModuleKey)
      : 'tasks'
    return {
      module,
      taskId: params.get('task_id'),
      taskItemId: params.get('task_item_id'),
      targetType: params.get('target_type'),
      targetId: params.get('target_id'),
      paperId: params.get('paper_id'),
    }
  }
  // 统一解析:验证中心(embedded,需 tab=paper_evidence)与证据中心(standalone)共用同一套参数
  if (path === '/validation-center') {
    if (params.get('tab') !== 'paper_evidence') return EMPTY_STATE
    return parse()
  }
  if (path !== '/evidence-center') return EMPTY_STATE
  return parse()
}

/** 与本模块状态相关的 URL 参数键(embedded 构建时全量重建,其余无关参数保留) */
const STATE_PARAM_KEYS = ['module', 'task_id', 'task_item_id', 'target_type', 'target_id', 'paper_id']

/**
 * embedded(验证中心)URL 构建:
 * - base 固定 #/validation-center 且始终带 tab=paper_evidence;
 * - 保留当前 URL 中与本模块状态无关的 query 参数;
 * - 空值参数不写入(不产生 task_id= 等空段)。
 */
export function buildEmbeddedUrl(s: EvidenceCenterState, currentHash?: string): string {
  const params = new URLSearchParams()
  const raw = (currentHash ?? '').replace(/^#/, '')
  const [, query = ''] = raw.split('?')
  const existing = new URLSearchParams(query)
  for (const [k, v] of existing.entries()) {
    if (!STATE_PARAM_KEYS.includes(k)) params.set(k, v)
  }
  params.set('tab', 'paper_evidence')
  if (s.module !== 'tasks') params.set('module', s.module)
  if (s.taskId) params.set('task_id', s.taskId)
  if (s.taskItemId) params.set('task_item_id', s.taskItemId)
  if (s.targetType) params.set('target_type', s.targetType)
  if (s.targetId) params.set('target_id', s.targetId)
  if (s.paperId) params.set('paper_id', s.paperId)
  const q = params.toString()
  return `#/validation-center${q ? `?${q}` : ''}`
}

export function buildEvidenceUrl(s: EvidenceCenterState): string {
  const params = new URLSearchParams()
  if (s.module !== 'tasks') params.set('module', s.module)
  if (s.taskId) params.set('task_id', s.taskId)
  if (s.taskItemId) params.set('task_item_id', s.taskItemId)
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
 * - standalone 候选队列无任务上下文 → 不写 task_item_id(三.4)
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
  const params = new URLSearchParams()
  params.set('tab', 'paper_evidence')
  params.set('module', 'candidates')
  if (taskId) params.set('task_id', taskId)
  if (first?.target_type) params.set('target_type', first.target_type)
  if (first?.target_id) params.set('target_id', first.target_id)
  window.location.hash = `#/validation-center?${params.toString()}`
}
