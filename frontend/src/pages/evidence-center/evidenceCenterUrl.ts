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
