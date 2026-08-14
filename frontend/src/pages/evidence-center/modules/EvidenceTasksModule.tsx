import { useEffect, useMemo, useState } from 'react'
import { Inbox } from 'lucide-react'
import {
  listPaperEvidenceTasks,
  type PaperEvidenceTask,
} from '../../../api/endpoints'
import { useGlobalGranularity } from '../../../hooks/useGlobalGranularity'
import { useEvidenceCenter } from '../EvidenceCenterContext'
import { CreateBatchTaskDialog } from '../components/CreateBatchTaskDialog'
import { EmptyState } from '../components/EmptyState'
import { TARGET_TYPE_LABELS, TASK_STATUS_LABELS, taskDisplayName, taskStatusTone } from '../components/taskStatus'
import { isUnfinishedItem, sortByConfidenceAsc } from '../components/taskItemQueueUtils'
import { useEvidenceTaskItems, type EvidenceQueueItem } from '../components/useEvidenceTaskItems'
import { EvidenceCandidatesModule } from './EvidenceCandidatesModule'

/** 任务对象卡片:名称/类型/置信度大字/状态/任务徽章(全局模式) */
function ObjectCard({ item, taskName, selected, onOpen }: {
  item: EvidenceQueueItem
  taskName?: string | null
  selected: boolean
  onOpen: () => void
}) {
  const conf = item.current_confidence
  return (
    <div
      className={`evidence-conn-card${selected ? ' evidence-conn-card-selected' : ''}`}
      data-testid={`evidence-task-object-${item.target_id}`}
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

/** 佐证任务中栏:直接显示对象列表(无 taskId = 全局;有 taskId = 该任务),点对象就地打开证据候选工作区 */
export function EvidenceTasksModule() {
  const { state, openTask, closeTask, openTarget } = useEvidenceCenter()
  const { granularity } = useGlobalGranularity()
  const { items, taskNames, loading, error, reload } = useEvidenceTaskItems()
  const [createOpen, setCreateOpen] = useState(false)
  const [task, setTask] = useState<PaperEvidenceTask | null>(null)

  // 任务模式时取任务对象展示名(中间栏标题用)
  useEffect(() => {
    if (!state.taskId) { setTask(null); return }
    let cancelled = false
    listPaperEvidenceTasks({ limit: 200 })
      .then(r => {
        if (cancelled) return
        const t = r.items.find(x => x.id === state.taskId)
        if (t) setTask(t)
      })
      .catch(() => {})
    return () => { cancelled = true }
  }, [state.taskId])

  const targetResolved = Boolean(
    state.targetType && state.targetId
    && items.some(it => it.target_type === state.targetType && it.target_id === state.targetId),
  )
  const unfinished = useMemo<EvidenceQueueItem[]>(
    () => sortByConfidenceAsc(items.filter(isUnfinishedItem)) as EvidenceQueueItem[],
    [items],
  )

  // 点对象 → 全局模式先选中来源任务,再打开对象工作区
  const handleOpenObject = (item: EvidenceQueueItem) => {
    if (item.__taskId) openTask(item.__taskId)
    openTarget(item.target_type, item.target_id, 'tasks')
  }

  const taskLabel = task ? taskDisplayName(task) : '任务详情'

  return (
    <div className="evidence-task-module">
      <div className="evidence-task-toolbar">
        <div className="evidence-task-toolbar-title">
          <h3>{state.taskId ? taskLabel : '佐证任务'}</h3>
          <p className="evidence-module-hint">
            {state.taskId
              ? '该任务的对象列表;点击对象进入证据佐证工作区。'
              : '所有进行中任务的待处理对象(按置信度优先级);点击对象进入证据佐证工作区。'}
          </p>
        </div>
        <div className="evidence-task-toolbar-actions">
          <button type="button" className="btn btn-sm" onClick={reload}>刷新</button>
          <button type="button" className="btn btn-sm" onClick={() => setCreateOpen(true)}>创建批量预处理</button>
        </div>
      </div>

      {state.taskId && (
        <div className="evidence-task-middle-bar">
          <button type="button" className="btn btn-xs" data-testid="evidence-task-middle-back" onClick={closeTask}>← 对象列表</button>
          {task && (
            <span className="ew-meta">
              已处理 {task.processed_items} / {task.total_items} · 待审核 {task.awaiting_review_items}
              {task.failed_items > 0 ? ` · 失败 ${task.failed_items}` : ''}
            </span>
          )}
        </div>
      )}

      {loading && <div className="evidence-task-loading">加载中…</div>}
      {!loading && error && (
        <div className="evidence-task-error">
          <p>对象列表加载失败:{error}</p>
          <button type="button" className="btn btn-sm" onClick={reload}>重试</button>
        </div>
      )}
      {!loading && !error && targetResolved && <EvidenceCandidatesModule />}
      {!loading && !error && !targetResolved && unfinished.length > 0 && (
        <div className="evidence-conn-list" data-testid="evidence-task-object-list">
          {unfinished.map(item => (
            <ObjectCard
              key={item.id}
              item={item}
              taskName={item.__taskId ? (taskNames[item.__taskId] ?? null) : null}
              selected={state.targetType === item.target_type && state.targetId === item.target_id}
              onOpen={() => handleOpenObject(item)}
            />
          ))}
          {items.length >= 100 && <div className="ew-meta">仅显示前 100 条(按优先级截断)</div>}
        </div>
      )}
      {!loading && !error && !targetResolved && unfinished.length === 0 && (
        <EmptyState
          icon={<Inbox size={24} />}
          title="全部处理完成"
          description="没有待处理对象。可在右栏已完成区回退对象重新审查。"
          testId="evidence-tasks-all-done"
        />
      )}

      <CreateBatchTaskDialog
        open={createOpen}
        granularity={granularity}
        onClose={() => setCreateOpen(false)}
        onCreated={() => { setCreateOpen(false); reload() }}
      />
    </div>
  )
}
