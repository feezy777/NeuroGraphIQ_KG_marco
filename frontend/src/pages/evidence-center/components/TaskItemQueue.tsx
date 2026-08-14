import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { ChevronDown, ChevronRight, Inbox } from 'lucide-react'
import {
  listPaperEvidenceTaskItems,
  listPaperEvidenceTasks,
  reopenPaperEvidenceTaskItem,
  type PaperEvidenceTaskItem,
} from '../../../api/endpoints'
import { useEvidenceCenter } from '../EvidenceCenterContext'
import { EmptyState } from './EmptyState'
import { TASK_STATUS_LABELS, taskStatusTone } from './taskStatus'
import { TARGET_TYPE_GROUPS, groupOf, isUnfinishedItem, sortByConfidenceAsc } from './taskItemQueueUtils'

/** 队列条目卡片(待处理区):名称/类型/置信度大字/状态/AI 方向;当前对象高亮 */
function QueueItemCard({ item, selected, onOpen, taskName }: {
  item: PaperEvidenceTaskItem
  selected: boolean
  onOpen: () => void
  taskName?: string | null
}) {
  const conf = item.current_confidence
  const srcTaskId = (item as unknown as { __taskId?: string }).__taskId
  return (
    <div
      className={`evidence-conn-card${selected ? ' evidence-conn-card-selected' : ''}`}
      data-testid={`evidence-queue-item-${item.target_id}`}
      onClick={onOpen}
    >
      <div className="evidence-conn-card-main">
        <span className="evidence-conn-card-label">{item.label || item.target_id}</span>
        <span className="evidence-conn-card-type">{item.target_type}</span>
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
          <span className="evidence-queue-task-badge" data-testid={`evidence-queue-task-badge-${srcTaskId}`}>{taskName}</span>
        )}
        {item.preprocess_outcome === 'no_evidence_found' && <span className="ew-meta">未找到有效证据</span>}
        {item.model_direction && <span className="ew-meta">AI:{item.model_direction}</span>}
      </div>
    </div>
  )
}

/** 右栏待处理队列:置信度升序 + 回路/连接/功能筛选(已完成折叠区在 Task 6 追加) */
export function TaskItemQueue() {
  const { state, openTarget } = useEvidenceCenter()
  const taskId = state.taskId
  const [items, setItems] = useState<PaperEvidenceTaskItem[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [group, setGroup] = useState<string>('all')
  const [doneOpen, setDoneOpen] = useState(false)
  const [reopeningId, setReopeningId] = useState<string | null>(null)
  const [confirmId, setConfirmId] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [taskNames, setTaskNames] = useState<Record<string, string>>({})
  // 最新 taskId 引用:切任务时丢弃乱序返回的陈旧响应
  const latestTaskIdRef = useRef(taskId)
  useEffect(() => { latestTaskIdRef.current = taskId }, [taskId])

  const loadItems = useCallback(async () => {
    if (!taskId) {
      // 全局模式:拉取所有进行中任务 → 并行拉各自 items → 合并(单任务失败静默跳过)
      setLoading(true)
      setError(null)
      setItems([])
      setTaskNames({})
      try {
        const r = await listPaperEvidenceTasks({ limit: 200 })
        const active = r.items.filter(t => ['pending', 'running', 'paused'].includes(t.status))
        setTaskNames(Object.fromEntries(active.map(t => [t.id, t.name || t.target_type])))
        const settled = await Promise.allSettled(
          active.map(t => listPaperEvidenceTaskItems(t.id, { limit: 100 })),
        )
        // 陈旧响应守卫:全局拉取期间用户选中了任务,则丢弃本次全局结果
        if (latestTaskIdRef.current !== null) return
        const merged = settled.flatMap((s, i) =>
          s.status === 'fulfilled'
            ? s.value.items.map(it => ({ ...it, __taskId: active[i].id }))
            : [],
        )
        setItems(merged as PaperEvidenceTaskItem[])
      } catch (err) {
        if (latestTaskIdRef.current !== null) return
        setError(err instanceof Error ? err.message : String(err))
      } finally {
        if (latestTaskIdRef.current === null) setLoading(false)
      }
      return
    }
    // 任务模式(原逻辑,保留 latestTaskIdRef 守卫)
    const requestedTaskId = taskId
    setLoading(true)
    setError(null)
    setItems([])
    setTaskNames({})
    try {
      const r = await listPaperEvidenceTaskItems(requestedTaskId, { limit: 100 })
      if (latestTaskIdRef.current !== requestedTaskId) return
      setItems(r.items)
    } catch (err) {
      if (latestTaskIdRef.current !== requestedTaskId) return
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      if (latestTaskIdRef.current === requestedTaskId) setLoading(false)
    }
  }, [taskId])

  useEffect(() => { void loadItems() }, [loadItems])

  const unfinished = useMemo(() => sortByConfidenceAsc(items.filter(isUnfinishedItem)), [items])
  const filtered = useMemo(
    () => (group === 'all' ? unfinished : unfinished.filter(it => groupOf(it.target_type) === group)),
    [unfinished, group],
  )

  const doneItems = useMemo(
    () => items.filter(it => it.status === 'completed').sort((a, b) => (b.updated_at ?? '').localeCompare(a.updated_at ?? '')),
    [items],
  )

  const handleReopen = useCallback(async (item: PaperEvidenceTaskItem) => {
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
      await reopenPaperEvidenceTaskItem(
        (item as unknown as { __taskId?: string }).__taskId ?? taskId ?? '',
        item.id,
      )
      await loadItems()
    } catch (err) {
      setActionError(err instanceof Error ? err.message : String(err))
    } finally {
      setReopeningId(null)
    }
  }, [confirmId, taskId, loadItems])

  return (
    <div className="evidence-task-queue" data-testid="evidence-task-queue">
      <div className="evidence-task-queue-head">
        <h4>待处理队列</h4>
        <button type="button" className="btn btn-xs" onClick={() => void loadItems()}>刷新</button>
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
          <button type="button" className="btn btn-sm" onClick={() => void loadItems()}>重试</button>
        </div>
      )}
      {!loading && !error && filtered.length === 0 && (
        <EmptyState
          compact
          icon={<Inbox size={20} />}
          title={unfinished.length === 0 ? '全部处理完成' : '该类型下暂无待处理对象'}
          description={unfinished.length === 0 ? '该任务没有待处理对象。' : '切换筛选分组查看其他类型。'}
          testId="evidence-queue-empty"
        />
      )}
      {!loading && !error && filtered.length > 0 && (
        <div className="evidence-queue-list" data-testid="evidence-queue-list">
          {filtered.map(item => (
            <QueueItemCard
              key={item.id}
              item={item}
              selected={state.targetType === item.target_type && state.targetId === item.target_id}
              taskName={(() => {
                const srcTaskId = (item as unknown as { __taskId?: string }).__taskId
                return srcTaskId ? (taskNames[srcTaskId] ?? null) : null
              })()}
              onOpen={() => openTarget(item.target_type, item.target_id, 'tasks')}
            />
          ))}
          {items.length >= 100 && <div className="ew-meta">仅显示前 100 条(按优先级截断)</div>}
        </div>
      )}
      <div className="evidence-queue-done" data-testid="evidence-queue-done">
        <button
          type="button"
          className="evidence-queue-done-toggle"
          data-testid="evidence-queue-done-toggle"
          onClick={() => setDoneOpen(o => !o)}
        >
          <span>已完成 {doneItems.length}</span>
          {doneOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        </button>
        {doneOpen && (
          <>
            {actionError && <div className="ew-meta" style={{ color: 'var(--danger)' }}>回退失败:{actionError}</div>}
            {doneItems.length === 0 && <span className="ew-meta">暂无已完成对象</span>}
            {doneItems.map(item => (
              <div key={item.id} className="evidence-queue-done-item" data-testid={`evidence-queue-done-item-${item.target_id}`}>
                <div className="evidence-queue-done-main">
                  <span className="evidence-conn-card-label">{item.label || item.target_id}</span>
                  <span className="evidence-conn-card-type">{item.target_type}</span>
                  <span className="evidence-task-chip evidence-task-chip-ok">已完成</span>
                </div>
                <button
                  type="button"
                  className="btn btn-xs"
                  data-testid={`evidence-queue-reopen-${item.target_id}`}
                  disabled={reopeningId === item.id}
                  onClick={() => void handleReopen(item)}
                >
                  {reopeningId === item.id ? '回退中…' : (confirmId === item.id ? '确认回退?' : '回退重新审查')}
                </button>
              </div>
            ))}
          </>
        )}
      </div>
    </div>
  )
}
