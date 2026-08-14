import { useCallback, useMemo, useState } from 'react'
import { Inbox } from 'lucide-react'
import { reopenPaperEvidenceTaskItem } from '../../../api/endpoints'
import { useEvidenceCenter } from '../EvidenceCenterContext'
import { EmptyState } from './EmptyState'
import { TARGET_TYPE_LABELS, TASK_STATUS_LABELS, taskStatusTone } from './taskStatus'
import { useEvidenceTaskItems, type EvidenceQueueItem } from './useEvidenceTaskItems'

/** 已处理(终态)对象集合:completed/skipped/failed */
const PROCESSED_STATUSES = ['completed', 'skipped', 'failed']

/** 右栏已处理数据面板:按完成时间倒序;completed 可两步确认回退重审;点击条目可打开工作区查看 */
export function TaskProcessedPanel() {
  const { state, openTarget, openTask } = useEvidenceCenter()
  const taskId = state.taskId
  const { items, taskNames, loading, error, reload } = useEvidenceTaskItems()
  const [reopeningId, setReopeningId] = useState<string | null>(null)
  const [confirmId, setConfirmId] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)

  const processed = useMemo<EvidenceQueueItem[]>(
    () => items
      .filter(it => PROCESSED_STATUSES.includes(it.status))
      .sort((a, b) => (b.updated_at ?? '').localeCompare(a.updated_at ?? '')),
    [items],
  )

  const handleReopen = useCallback(async (item: EvidenceQueueItem) => {
    if (confirmId !== item.id) {
      setConfirmId(item.id)
      window.setTimeout(() => {
        setConfirmId(prev => (prev === item.id ? null : prev))
      }, 3000)
      return
    }
    setConfirmId(null)
    setReopeningId(item.id)
    setActionError(null)
    try {
      await reopenPaperEvidenceTaskItem(item.__taskId ?? taskId ?? '', item.id)
      reload()
    } catch (err) {
      setActionError(err instanceof Error ? err.message : String(err))
    } finally {
      setReopeningId(null)
    }
  }, [confirmId, taskId, reload])

  const handleOpen = (item: EvidenceQueueItem) => {
    if (item.__taskId) openTask(item.__taskId)
    openTarget(item.target_type, item.target_id, 'tasks')
  }

  return (
    <div className="evidence-task-queue" data-testid="evidence-processed-panel">
      <div className="evidence-task-queue-head">
        <h4>已处理数据</h4>
        <button type="button" className="btn btn-xs" onClick={reload}>刷新</button>
      </div>

      {loading && <div className="evidence-task-loading">加载中…</div>}
      {!loading && error && (
        <div className="evidence-task-error">
          <p>已处理列表加载失败:{error}</p>
          <button type="button" className="btn btn-sm" onClick={reload}>重试</button>
        </div>
      )}
      {!loading && !error && processed.length === 0 && (
        <EmptyState
          compact
          icon={<Inbox size={20} />}
          title="暂无已处理对象"
          description="处理完成的对象会出现在这里,可回退重新审查。"
          testId="evidence-processed-empty"
        />
      )}
      {!loading && !error && processed.length > 0 && (
        <div className="evidence-queue-done" data-testid="evidence-processed-list">
          {actionError && <div className="ew-meta" style={{ color: 'var(--danger)' }}>回退失败:{actionError}</div>}
          {processed.map(item => (
            <div
              key={item.id}
              className="evidence-queue-done-item"
              data-testid={`evidence-processed-item-${item.target_id}`}
              onClick={() => handleOpen(item)}
            >
              <div className="evidence-queue-done-main">
                <span className="evidence-conn-card-label">{item.label || item.target_id}</span>
                <span className="evidence-conn-card-type">{TARGET_TYPE_LABELS[item.target_type] ?? item.target_type}</span>
                <span style={{ display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
                  <span className={`evidence-task-chip evidence-task-chip-${taskStatusTone(item.status)}`}>
                    {TASK_STATUS_LABELS[item.status] ?? item.status}
                  </span>
                  {item.__taskId && (
                    <span className="evidence-queue-task-badge">{taskNames[item.__taskId] ?? item.__taskId}</span>
                  )}
                </span>
              </div>
              {item.status === 'completed' && (
                <button
                  type="button"
                  className="btn btn-xs"
                  data-testid={`evidence-queue-reopen-${item.target_id}`}
                  disabled={reopeningId === item.id}
                  onClick={e => { e.stopPropagation(); void handleReopen(item) }}
                >
                  {reopeningId === item.id ? '回退中…' : (confirmId === item.id ? '确认回退?' : '回退重新审查')}
                </button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
