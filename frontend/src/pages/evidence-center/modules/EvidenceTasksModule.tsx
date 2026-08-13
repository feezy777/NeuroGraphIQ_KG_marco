import { useCallback, useEffect, useState } from 'react'
import { Inbox } from 'lucide-react'
import {
  listPaperEvidenceTasks,
  listPaperEvidenceTaskItems,
  type PaperEvidenceTask,
  type PaperEvidenceTaskItem,
} from '../../../api/endpoints'
import { useGlobalGranularity } from '../../../hooks/useGlobalGranularity'
import { useEvidenceCenter } from '../EvidenceCenterContext'
import { CreateBatchTaskDialog } from '../components/CreateBatchTaskDialog'
import { EmptyState } from '../components/EmptyState'
import { TASK_STATUS_LABELS, taskSortRank, taskStatusTone } from '../components/taskStatus'
import { isUnfinishedItem, sortByConfidenceAsc } from '../components/taskItemQueueUtils'
import { EvidenceCandidatesModule } from './EvidenceCandidatesModule'

function fmtDate(v: string | null): string {
  if (!v) return ''
  try {
    return new Date(v).toLocaleString('zh-CN', { hour12: false })
  } catch {
    return v
  }
}

/** 任务卡片:基本信息 + 点击进入任务详情 */
function TaskCard({ task, onOpen }: { task: PaperEvidenceTask; onOpen: () => void }) {
  const inProgress = ['pending', 'running', 'paused'].includes(task.status)
  return (
    <button
      type="button"
      className="evidence-task-card"
      data-testid={`evidence-task-card-${task.id}`}
      onClick={onOpen}
    >
      <div className="evidence-task-card-head">
        <span className="evidence-task-card-name">{task.name || task.target_type}</span>
        <span className={`evidence-task-chip evidence-task-chip-${taskStatusTone(task.status)}${inProgress ? ' evidence-task-chip-live' : ''}`}>
          {TASK_STATUS_LABELS[task.status] ?? task.status}
        </span>
      </div>
      <div className="evidence-task-card-type">{task.target_type}</div>
      <div className="evidence-task-card-stats">
        <span>已处理 <b>{task.processed_items}</b> / <b>{task.total_items}</b></span>
        <span className={task.awaiting_review_items > 0 ? 'evidence-task-card-awaiting' : undefined}>
          待审核 <b>{task.awaiting_review_items}</b>
        </span>
        {task.failed_items > 0 && (
          <span className="evidence-task-card-failed">失败 <b>{task.failed_items}</b></span>
        )}
      </div>
      {task.created_at && <div className="ew-meta">{fmtDate(task.created_at)}</div>}
    </button>
  )
}

export function EvidenceTasksModule() {
  const { state, openTask, openTarget } = useEvidenceCenter()
  const { granularity } = useGlobalGranularity()
  const [tasks, setTasks] = useState<PaperEvidenceTask[]>([])
  const [tasksLoading, setTasksLoading] = useState(true)
  const [tasksError, setTasksError] = useState<string | null>(null)
  const [createOpen, setCreateOpen] = useState(false)
  const [items, setItems] = useState<PaperEvidenceTaskItem[]>([])
  const [itemsLoading, setItemsLoading] = useState(true)
  const [itemsError, setItemsError] = useState<string | null>(null)

  const loadTasks = useCallback(async () => {
    setTasksLoading(true)
    setTasksError(null)
    try {
      const r = await listPaperEvidenceTasks()
      setTasks(r.items)
    } catch (err) {
      setTasksError(err instanceof Error ? err.message : String(err))
    } finally {
      setTasksLoading(false)
    }
  }, [])

  useEffect(() => { void loadTasks() }, [loadTasks])

  const loadItems = useCallback(async () => {
    if (!state.taskId) { setItems([]); return }
    setItemsLoading(true)
    setItemsError(null)
    setItems([])
    try {
      const r = await listPaperEvidenceTaskItems(state.taskId, { limit: 200 })
      setItems(r.items)
    } catch (err) {
      setItems([])
      setItemsError(err instanceof Error ? err.message : String(err))
    } finally {
      setItemsLoading(false)
    }
  }, [state.taskId])

  useEffect(() => { void loadItems() }, [loadItems])

  // 进入详情自动选中队列首位(未完成、置信度最低):URL 无 target 或 target 不在本任务未完成集合时纠正
  useEffect(() => {
    if (!state.taskId) return
    const unfinished = sortByConfidenceAsc(items.filter(isUnfinishedItem))
    if (unfinished.length === 0) return
    const matched = unfinished.find(it => it.target_type === state.targetType && it.target_id === state.targetId)
    if (!matched) openTarget(unfinished[0].target_type, unfinished[0].target_id, 'tasks')
  }, [state.taskId, items, state.targetType, state.targetId, openTarget])

  // ── 任务列表视图(无 taskId) ──
  if (!state.taskId) {
    const sorted = [...tasks].sort((a, b) => {
      const ra = taskSortRank(a)
      const rb = taskSortRank(b)
      if (ra !== rb) return ra - rb
      return (b.created_at ?? '').localeCompare(a.created_at ?? '')
    })
    return (
      <div className="evidence-task-module">
        <div className="evidence-task-toolbar">
          <div className="evidence-task-toolbar-title">
            <h3>佐证任务</h3>
            <p className="evidence-module-hint">当前正在处理的证据佐证任务,点击任务卡片进入处理工作台。</p>
          </div>
          <div className="evidence-task-toolbar-actions">
            <button type="button" className="btn btn-sm" onClick={() => void loadTasks()}>刷新</button>
            <button type="button" className="btn btn-sm" onClick={() => setCreateOpen(true)}>创建批量预处理</button>
          </div>
        </div>

        {tasksLoading && <div className="evidence-task-loading">加载中…</div>}
        {!tasksLoading && tasksError && (
          <div className="evidence-task-error">
            <p>任务列表加载失败:{tasksError}</p>
            <button type="button" className="btn btn-sm" onClick={() => void loadTasks()}>重试</button>
          </div>
        )}
        {!tasksLoading && !tasksError && sorted.length === 0 && (
          <EmptyState
            icon={<Inbox size={24} />}
            title="暂无佐证任务"
            description="点击右上角「创建批量预处理」创建第一个任务。"
            actionLabel="创建批量预处理"
            onAction={() => setCreateOpen(true)}
          />
        )}
        {!tasksLoading && !tasksError && sorted.length > 0 && (
          <div className="evidence-task-card-grid" data-testid="evidence-task-card-grid">
            {sorted.map(task => (
              <TaskCard key={task.id} task={task} onOpen={() => openTask(task.id)} />
            ))}
          </div>
        )}

        <CreateBatchTaskDialog
          open={createOpen}
          granularity={granularity}
          onClose={() => setCreateOpen(false)}
          onCreated={() => { setCreateOpen(false); void loadTasks() }}
        />
      </div>
    )
  }

  // ── 任务详情视图 ──
  const task = tasks.find(t => t.id === state.taskId) ?? null
  // 候选组件门控:仅当 URL target 已解析为本任务某个 item 时才挂载,
  // 避免其「target 不符则回写 module=candidates」的同步副作用在自动选中提交前把模块切走
  const targetResolved = Boolean(
    state.targetType && state.targetId
    && items.some(it => it.target_type === state.targetType && it.target_id === state.targetId),
  )
  return (
    <div className="evidence-task-module">
      <div className="evidence-task-detail-bar" data-testid="evidence-task-detail-bar">
        <h3>{task?.name || task?.target_type || '任务详情'}</h3>
        {task && (
          <>
            <span className={`evidence-task-chip evidence-task-chip-${taskStatusTone(task.status)}`}>
              {TASK_STATUS_LABELS[task.status] ?? task.status}
            </span>
            <span className="ew-meta">
              已处理 {task.processed_items} / {task.total_items} · 待审核 {task.awaiting_review_items}
              {task.failed_items > 0 ? ` · 失败 ${task.failed_items}` : ''}
            </span>
          </>
        )}
      </div>
      {itemsLoading && <div className="evidence-task-loading">加载中…</div>}
      {!itemsLoading && itemsError && (
        <div className="evidence-task-error">
          <p>连接列表加载失败:{itemsError}</p>
          <button type="button" className="btn btn-sm" onClick={() => void loadItems()}>重试</button>
        </div>
      )}
      {!itemsLoading && !itemsError && targetResolved && <EvidenceCandidatesModule />}
      {!itemsLoading && !itemsError && !targetResolved && items.some(isUnfinishedItem) && (
        <div className="evidence-task-loading">加载中…</div>
      )}
      {!itemsLoading && !itemsError && !targetResolved && !items.some(isUnfinishedItem) && (
        <EmptyState
          icon={<Inbox size={24} />}
          title="全部处理完成"
          description="该任务没有待处理对象。可在右栏已完成区回退对象重新审查。"
          testId="evidence-tasks-all-done"
        />
      )}
      <CreateBatchTaskDialog
        open={createOpen}
        granularity={granularity}
        onClose={() => setCreateOpen(false)}
        onCreated={() => { setCreateOpen(false); void loadItems() }}
      />
    </div>
  )
}
