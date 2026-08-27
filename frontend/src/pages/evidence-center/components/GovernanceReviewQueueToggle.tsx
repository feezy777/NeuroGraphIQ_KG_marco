import { useEffect, useRef, useState } from 'react'
import {
  listMacroCandidateReviewQueue,
  type MacroReviewQueueKind,
} from '../../../api/endpoints'
import { useEvidenceCenter } from '../EvidenceCenterContext'
import { useTaskItemsRefresh } from './taskItemsRefreshContext'
import type { QueueEntry } from './types'

export type ReviewQueueMode = 'task' | 'enhancement' | 'novel'

const MODE_LABEL: Record<ReviewQueueMode, string> = {
  task: '全部',
  enhancement: '已有连接证据增强',
  novel: '新增连接候选',
}

/**
 * 人工审核队列入口(Phase 4):
 *   task        —— 既有佐证任务队列(默认,行为不变)
 *   enhancement —— Macro 治理证据增强队列(rule BLOCKED duplicate_existing,已有连接)
 *   novel       —— Macro 治理新增连接候选队列(rule PASS + AI SUPPORTED)
 * 治理队列复用现有 HumanReviewPanel:目标对象类型 existing_connection_evidence /
 * macro_candidate_connection(后端 DTO 组装),审核批准/拒绝走既有 review 链路。
 */
export function GovernanceReviewQueueToggle() {
  const { setQueue, openTarget, state, gotoModule } = useEvidenceCenter()
  const { refresh } = useTaskItemsRefresh()
  const [mode, setMode] = useState<ReviewQueueMode>('task')
  const modeRef = useRef(mode)
  modeRef.current = mode

  // 治理队列加载 → 写入 EC queue(左栏 ObjectQueue 自动联动)+ 打开首项
  useEffect(() => {
    if (modeRef.current === 'task') return
    let cancelled = false
    const kind = modeRef.current as MacroReviewQueueKind
    listMacroCandidateReviewQueue(kind)
      .then(r => {
        if (cancelled) return
        const entries: QueueEntry[] = (r.items ?? []).map(it => ({
          target_type: it.target_type,
          target_id: it.target_id,
          label: it.label,
          confidence: it.confidence,
          status: 'awaiting_review' as const,
          evidenceCount: it.evidenceCount ?? 0,
        }))
        setQueue(entries)
        if (state.module !== 'review') gotoModule('review')
        if (entries[0]) openTarget(entries[0].target_type, entries[0].target_id, 'review')
      })
      .catch(() => undefined)
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode])

  // 切回任务队列:恢复既有任务加载(列表与 queue 由任务刷新重建)
  const handleMode = (next: ReviewQueueMode) => {
    setMode(next)
    if (next === 'task') {
      setQueue([])
      refresh()
    }
  }

  return (
    <div className="evidence-review-queue-toggle" data-testid="gov-review-queue-toggle"
      style={{ display: 'flex', gap: 6, marginTop: 8, flexWrap: 'wrap' }}>
      {(['task', 'enhancement', 'novel'] as ReviewQueueMode[]).map(m => (
        <button
          key={m}
          type="button"
          className={`evidence-module-btn${mode === m ? ' active' : ''}`}
          aria-current={mode === m ? 'page' : undefined}
          onClick={() => handleMode(m)}
        >
          {MODE_LABEL[m]}
        </button>
      ))}
    </div>
  )
}
