import { QUEUE_STATUS_LABEL, queueStatusTone, type QueueEntry } from './types'

interface QueueListItemProps {
  entry: QueueEntry
  /** 是否当前选中对象(浅蓝背景 + 左侧强调条) */
  active: boolean
  onSelect: (entry: QueueEntry) => void
}

/** 统一队列紧凑条目(名称/类型·置信度/状态徽章/证据数;preprocess 无证据时附加灰色提示)—— ObjectQueue 与 EvidenceQueuePanel 共用 */
export function QueueListItem({ entry, active, onSelect }: QueueListItemProps) {
  const tone = queueStatusTone(entry.status)
  return (
    <div
      className={`evidence-queue-item${active ? ' evidence-queue-item-active' : ''}`}
      data-testid="evidence-queue-item"
      onClick={() => onSelect(entry)}
    >
      <div className="evidence-queue-item-label">{entry.label}</div>
      <div className="evidence-queue-item-meta">
        {entry.target_type} · 置信度 {entry.confidence == null ? '—' : `${Math.round(entry.confidence * 100)}%`}
      </div>
      <div className="evidence-queue-item-foot">
        <span className={`evidence-queue-status evidence-queue-status-${tone}`}>
          {QUEUE_STATUS_LABEL[entry.status] ?? entry.status}
        </span>
        <span className="evidence-queue-evidence">{entry.evidenceCount} 证据</span>
      </div>
      {entry.preprocessOutcome === 'no_evidence_found' && (
        <div className="evidence-queue-item-hint" data-testid="evidence-queue-item-hint">
          该对象预处理未找到有效证据片段
        </div>
      )}
    </div>
  )
}
