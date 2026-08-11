import { useMemo, useState } from 'react'
import { QueueListItem } from './QueueListItem'
import { DONE_STATUSES, PENDING_STATUSES, type QueueEntry } from './types'

type QueueTab = 'pending' | 'done' | 'failed' | 'all'

interface EvidenceQueuePanelProps {
  queue: QueueEntry[]
  /** 当前对象下标;无匹配传 -1 */
  currentIndex: number
  onSelect: (entry: QueueEntry) => void
}

/**
 * 待处理对象队列(视觉稿版):标题 + 数量徽标 + 状态 Tabs(待审核/已完成/失败)+ ☐只看未处理 +
 * 紧凑条目(当前项浅蓝高亮)+ 空态(收件箱图标/队列为空/当前没有待处理的对象 + 底部 [查看全部对象])。
 * 默认停在「待审核」Tab(即面板主题「待处理对象」);空态按钮重置回全部条目。
 */
export function EvidenceQueuePanel({ queue, currentIndex, onSelect }: EvidenceQueuePanelProps) {
  const [activeTab, setActiveTab] = useState<QueueTab>('pending')
  const [onlyPending, setOnlyPending] = useState(false)

  const counts = useMemo(() => ({
    pending: queue.filter(e => PENDING_STATUSES.includes(e.status)).length,
    done: queue.filter(e => DONE_STATUSES.includes(e.status)).length,
    failed: queue.filter(e => e.status === 'failed').length,
  }), [queue])

  const visible = useMemo(() => {
    let out = queue
    if (activeTab === 'pending') out = out.filter(e => PENDING_STATUSES.includes(e.status))
    else if (activeTab === 'done') out = out.filter(e => DONE_STATUSES.includes(e.status))
    else if (activeTab === 'failed') out = out.filter(e => e.status === 'failed')
    if (onlyPending) out = out.filter(e => PENDING_STATUSES.includes(e.status))
    return out
  }, [queue, activeTab, onlyPending])

  const tabs: Array<{ key: QueueTab; label: string; count: number }> = [
    { key: 'pending', label: '待审核', count: counts.pending },
    { key: 'done', label: '已完成', count: counts.done },
    { key: 'failed', label: '失败', count: counts.failed },
  ]

  return (
    <aside className="evidence-queue-panel" data-testid="evidence-queue-panel">
      <div className="evidence-queue-head">
        <h4 className="evidence-queue-title">待处理对象</h4>
        <span className="evidence-queue-count" data-testid="evidence-queue-count">{queue.length}</span>
      </div>
      <div className="evidence-queue-panel-tabs" role="tablist" aria-label="对象状态">
        {tabs.map(t => (
          <button
            key={t.key}
            type="button"
            role="tab"
            aria-selected={activeTab === t.key}
            className={`evidence-queue-panel-tab${activeTab === t.key ? ' active' : ''}`}
            onClick={() => setActiveTab(t.key)}
          >
            {t.label} <b className="evidence-queue-panel-tab-count">{t.count}</b>
          </button>
        ))}
      </div>
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
        {visible.length === 0 && (
          <div className="evidence-queue-panel-empty" data-testid="evidence-queue-empty">
            <div className="evidence-queue-panel-empty-icon">📥</div>
            <div className="evidence-queue-panel-empty-title">队列为空</div>
            <div className="evidence-queue-panel-empty-hint">当前没有待处理的对象</div>
            <button
              type="button"
              className="btn btn-primary btn-sm evidence-queue-panel-view-all"
              data-testid="evidence-queue-view-all"
              onClick={() => { setActiveTab('all'); setOnlyPending(false) }}
            >
              查看全部对象
            </button>
          </div>
        )}
      </div>
    </aside>
  )
}
