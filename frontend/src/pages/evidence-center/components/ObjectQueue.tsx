import { useMemo, useState } from 'react'
import { QUEUE_STATUS_LABEL, queueStatusTone, type QueueEntry, type QueueStatus } from './types'

const PENDING_STATUSES: QueueStatus[] = ['pending', 'searching', 'extracting', 'awaiting_review']
const DONE_STATUSES: QueueStatus[] = ['completed', 'skipped']

interface ObjectQueueProps {
  queue: QueueEntry[]
  /** 当前对象下标;无匹配传 -1 */
  currentIndex: number
  onSelect: (entry: QueueEntry) => void
  showStats?: boolean
}

/** 统一左栏对象队列:统计 + 只看未处理 + 紧凑对象卡,当前对象浅背景左边强调 */
export function ObjectQueue({ queue, currentIndex, onSelect, showStats = true }: ObjectQueueProps) {
  const [onlyPending, setOnlyPending] = useState(false)

  const stats = useMemo(() => ({
    pending: queue.filter(e => PENDING_STATUSES.includes(e.status)).length,
    done: queue.filter(e => DONE_STATUSES.includes(e.status)).length,
    failed: queue.filter(e => e.status === 'failed').length,
  }), [queue])

  const visible = useMemo(
    () => (onlyPending ? queue.filter(e => PENDING_STATUSES.includes(e.status)) : queue),
    [queue, onlyPending],
  )

  return (
    <aside className="evidence-queue" data-testid="evidence-queue">
      <div className="evidence-queue-head">
        <h4 className="evidence-queue-title">待处理对象</h4>
        <span className="evidence-queue-count">{queue.length}</span>
      </div>
      {showStats && (
        <div className="evidence-queue-stats">
          <span className="evidence-queue-stat">待审核 {stats.pending}</span>
          <span className="evidence-queue-stat">已完成 {stats.done}</span>
          <span className="evidence-queue-stat">失败 {stats.failed}</span>
        </div>
      )}
      <label className="evidence-queue-filter">
        <input
          type="checkbox"
          checked={onlyPending}
          onChange={e => setOnlyPending(e.target.checked)}
        />
        只看未处理
      </label>
      <div className="evidence-queue-list">
        {visible.map((e, i) => {
          const originalIndex = onlyPending ? queue.indexOf(e) : i
          const active = originalIndex === currentIndex
          const tone = queueStatusTone(e.status)
          return (
            <div
              key={`${e.target_type}:${e.target_id}`}
              className={`evidence-queue-item${active ? ' evidence-queue-item-active' : ''}`}
              data-testid="evidence-queue-item"
              onClick={() => onSelect(e)}
            >
              <div className="evidence-queue-item-label">{e.label}</div>
              <div className="evidence-queue-item-meta">
                {e.target_type} · 置信度 {e.confidence == null ? '—' : `${Math.round(e.confidence * 100)}%`}
              </div>
              <div className="evidence-queue-item-foot">
                <span className={`evidence-queue-status evidence-queue-status-${tone}`}>
                  {QUEUE_STATUS_LABEL[e.status] ?? e.status}
                </span>
                <span className="evidence-queue-evidence">{e.evidenceCount} 证据</span>
              </div>
            </div>
          )
        })}
        {visible.length === 0 && <div className="evidence-queue-empty">队列为空</div>}
      </div>
    </aside>
  )
}
