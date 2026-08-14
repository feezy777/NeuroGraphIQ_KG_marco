import { useMemo, useState } from 'react'
import { Inbox } from 'lucide-react'
import { useEvidenceCenter } from '../EvidenceCenterContext'
import { EmptyState } from './EmptyState'
import { TARGET_TYPE_LABELS, TASK_STATUS_LABELS, taskStatusTone } from './taskStatus'
import { TARGET_TYPE_GROUPS, groupOf, isUnfinishedItem, sortByConfidenceAsc } from './taskItemQueueUtils'
import { useEvidenceTaskItems, type EvidenceQueueItem } from './useEvidenceTaskItems'

/** 待处理对象卡片:名称/类型中文/置信度大字/状态/任务徽章;当前对象高亮 */
function PendingCard({ item, taskName, selected, onOpen }: {
  item: EvidenceQueueItem
  taskName?: string | null
  selected: boolean
  onOpen: () => void
}) {
  const conf = item.current_confidence
  return (
    <div
      className={`evidence-conn-card${selected ? ' evidence-conn-card-selected' : ''}`}
      data-testid={`evidence-queue-item-${item.target_id}`}
      onClick={onOpen}
    >
      <div className="evidence-conn-card-main">
        <span className="evidence-conn-card-label">{item.label || item.target_id}</span>
        <span className="evidence-conn-card-type">{TARGET_TYPE_LABELS[item.target_type] ?? item.target_type}</span>
      </div>
      <div className="evidence-conn-card-meta">
        <div className="evidence-conn-card-conf">
          <span className="evidence-conn-card-conf-label">置信度</span>
          <b className="evidence-conn-card-conf-value">{conf != null ? conf.toFixed(2) : '—'}</b>
        </div>
        <span className={`evidence-task-chip evidence-task-chip-${taskStatusTone(item.status)}`}>
          {TASK_STATUS_LABELS[item.status] ?? item.status}
        </span>
        {taskName && (
          <span className="evidence-queue-task-badge" data-testid={`evidence-queue-task-badge-${item.__taskId}`}>{taskName}</span>
        )}
        {item.preprocess_outcome === 'no_evidence_found' && <span className="ew-meta">未找到有效证据</span>}
        {item.model_direction && <span className="ew-meta">AI:{item.model_direction}</span>}
      </div>
    </div>
  )
}

/** 左栏待处理队列:置信度升序 + 回路/连接/功能筛选(无 taskId = 全局,有 taskId = 该任务) */
export function TaskPendingQueue() {
  const { state, openTarget, openTask } = useEvidenceCenter()
  const { items, taskNames, loading, error, reload } = useEvidenceTaskItems()
  const [group, setGroup] = useState<string>('all')

  const unfinished = useMemo<EvidenceQueueItem[]>(
    () => sortByConfidenceAsc(items.filter(isUnfinishedItem)) as EvidenceQueueItem[],
    [items],
  )
  const filtered = useMemo(
    () => (group === 'all' ? unfinished : unfinished.filter(it => groupOf(it.target_type) === group)),
    [unfinished, group],
  )

  const handleOpen = (item: EvidenceQueueItem) => {
    if (item.__taskId) openTask(item.__taskId)
    openTarget(item.target_type, item.target_id, 'tasks')
  }

  return (
    <div className="evidence-task-queue" data-testid="evidence-task-queue">
      <div className="evidence-task-queue-head">
        <h4>待处理对象</h4>
        <button type="button" className="btn btn-xs" onClick={reload}>刷新</button>
      </div>

      <div className="evidence-queue-filter" data-testid="evidence-queue-filter">
        <button
          type="button"
          className={`evidence-queue-filter-btn${group === 'all' ? ' evidence-queue-filter-btn-active' : ''}`}
          onClick={() => setGroup('all')}
        >
          全部 {unfinished.length}
        </button>
        {TARGET_TYPE_GROUPS.map(g => (
          <button
            key={g.key}
            type="button"
            className={`evidence-queue-filter-btn${group === g.key ? ' evidence-queue-filter-btn-active' : ''}`}
            onClick={() => setGroup(g.key)}
          >
            {g.label} {unfinished.filter(it => groupOf(it.target_type) === g.key).length}
          </button>
        ))}
      </div>

      {loading && <div className="evidence-task-loading">加载中…</div>}
      {!loading && error && (
        <div className="evidence-task-error">
          <p>队列加载失败:{error}</p>
          <button type="button" className="btn btn-sm" onClick={reload}>重试</button>
        </div>
      )}
      {!loading && !error && filtered.length === 0 && (
        <EmptyState
          compact
          icon={<Inbox size={20} />}
          title={unfinished.length === 0 ? '全部处理完成' : '该类型下暂无待处理对象'}
          description={unfinished.length === 0 ? '没有待处理对象。可在右侧已处理区回退重新审查。' : '切换筛选分组查看其他类型。'}
          testId="evidence-queue-empty"
        />
      )}
      {!loading && !error && filtered.length > 0 && (
        <div className="evidence-queue-list" data-testid="evidence-queue-list">
          {filtered.map(item => (
            <PendingCard
              key={item.id}
              item={item}
              selected={state.targetType === item.target_type && state.targetId === item.target_id}
              taskName={item.__taskId ? (taskNames[item.__taskId] ?? null) : null}
              onOpen={() => handleOpen(item)}
            />
          ))}
          {items.length >= 100 && <div className="ew-meta">仅显示前 100 条(按优先级截断)</div>}
        </div>
      )}
    </div>
  )
}
