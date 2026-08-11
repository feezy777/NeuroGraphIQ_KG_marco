import { useMemo, useState } from 'react'
import { QueueListItem } from './QueueListItem'
import { DONE_STATUSES, PENDING_STATUSES, type QueueEntry } from './types'

interface ObjectQueueProps {
  queue: QueueEntry[]
  /** 当前对象下标;无匹配传 -1 */
  currentIndex: number
  onSelect: (entry: QueueEntry) => void
  showStats?: boolean
}

/** 统一左栏对象队列(任务/审核/晋升模块):统计 + 只看未处理 + 紧凑对象卡,当前对象浅背景左边强调。
 * 候选模块右栏的视觉稿版队列见 EvidenceQueuePanel。 */
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
        {visible.map(e => (
          <QueueListItem
            key={`${e.target_type}:${e.target_id}`}
            entry={e}
            active={queue.indexOf(e) === currentIndex}
            onSelect={onSelect}
          />
        ))}
        {visible.length === 0 && <div className="evidence-queue-empty">队列为空</div>}
      </div>
    </aside>
  )
}
