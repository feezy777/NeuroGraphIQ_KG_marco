import { useCallback, useEffect, useRef, useState } from 'react'
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

/** 任务卡片:基本信息 + 点击进入任务(态①) */
function TaskCard({ task, selected, onOpen }: { task: PaperEvidenceTask; selected: boolean; onOpen: () => void }) {
  const inProgress = ['pending', 'running', 'paused'].includes(task.status)
  return (
    <button
      type="button"
      className={`evidence-task-card${selected ? ' evidence-task-card-selected' : ''}`}
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

/** 任务对象卡片(态②):未完成优先 + 置信度升序 */
function ObjectCard({ item, selected, onOpen }: { item: PaperEvidenceTaskItem; selected: boolean; onOpen: () => void }) {
  const conf = item.current_confidence
  return (
    <div
      className={`evidence-conn-card${selected ? ' evidence-conn-card-selected' : ''}`}
      data-testid={`evidence-task-object-${item.target_id}`}
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
        {item.preprocess_outcome === 'no_evidence_found' && <span className="ew-meta">未找到有效证据</span>}
        {item.model_direction && <span className="ew-meta">AI:{item.model_direction}</span>}
      </div>
    </div>
  )
}

/** 中栏对象排序:未完成优先(置信度升序),已完成/其他按状态排后 */
function sortObjects(items: PaperEvidenceTaskItem[]): PaperEvidenceTaskItem[] {
  const unfinished = sortByConfidenceAsc(items.filter(isUnfinishedItem))
  const rest = items.filter(it => !isUnfinishedItem(it))
  return [...unfinished, ...rest]
}

export function EvidenceTasksModule() {
  const { state, openTask, closeTask, openTarget } = useEvidenceCenter()
  const { granularity } = useGlobalGranularity()
  const [tasks, setTasks] = useState<PaperEvidenceTask[]>([])
  const [tasksLoading, setTasksLoading] = useState(true)
  const [tasksError, setTasksError] = useState<string | null>(null)
  const [createOpen, setCreateOpen] = useState(false)
  const [items, setItems] = useState<PaperEvidenceTaskItem[]>([])
  const [itemsLoading, setItemsLoading] = useState(true)
  const [itemsError, setItemsError] = useState<string | null>(null)
  const latestTaskIdRef = useRef(state.taskId)
  useEffect(() => { latestTaskIdRef.current = state.taskId }, [state.taskId])

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
    const requestedTaskId = state.taskId
    setItemsLoading(true)
    setItemsError(null)
    setItems([])
    try {
      const r = await listPaperEvidenceTaskItems(requestedTaskId, { limit: 100 })
      if (latestTaskIdRef.current !== requestedTaskId) return
      setItems(r.items)
    } catch (err) {
      if (latestTaskIdRef.current !== requestedTaskId) return
      setItems([])
      setItemsError(err instanceof Error ? err.message : String(err))
    } finally {
      if (latestTaskIdRef.current === requestedTaskId) setItemsLoading(false)
    }
  }, [state.taskId])

  useEffect(() => { void loadItems() }, [loadItems])

  // 选中任务自动选中队列首位(未完成、置信度最低):deps 不含 target(防点击/回退后旧快照抢回)
  useEffect(() => {
    if (!state.taskId) return
    const unfinished = sortByConfidenceAsc(items.filter(isUnfinishedItem))
    if (unfinished.length === 0) return
    const matched = unfinished.find(it => it.target_type === state.targetType && it.target_id === state.targetId)
    if (!matched) openTarget(unfinished[0].target_type, unfinished[0].target_id, 'tasks')
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.taskId, items, openTarget])

  const task = tasks.find(t => t.id === state.taskId) ?? null
  const targetResolved = Boolean(
    state.targetType && state.targetId
    && items.some(it => it.target_type === state.targetType && it.target_id === state.targetId),
  )

  // ── 态①:任务卡片网格 ──
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
            <p className="evidence-module-hint">当前正在处理的证据佐证任务;右栏为全局置信度优先级队列。</p>
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
            {sorted.map(t => (
              <TaskCard key={t.id} task={t} selected={false} onOpen={() => openTask(t.id)} />
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

  // ── 态②/③:任务对象卡片 ⇄ 就地证据工作区 ──
  const sortedObjects = sortObjects(items)
  return (
    <div className="evidence-task-module">
      <div className="evidence-task-middle-bar">
        <button type="button" className="btn btn-xs" data-testid="evidence-task-middle-back" onClick={closeTask}>← 任务列表</button>
        <h3>{task?.name || task?.target_type || '任务详情'}</h3>
        {task && (
          <span className="ew-meta">
            已处理 {task.processed_items} / {task.total_items} · 待审核 {task.awaiting_review_items}
            {task.failed_items > 0 ? ` · 失败 ${task.failed_items}` : ''}
          </span>
        )}
        <span style={{ marginLeft: 'auto' }}>
          <button type="button" className="btn btn-xs" onClick={() => void loadItems()}>刷新</button>
        </span>
      </div>

      {itemsLoading && <div className="evidence-task-loading">加载中…</div>}
      {!itemsLoading && itemsError && (
        <div className="evidence-task-error">
          <p>对象列表加载失败:{itemsError}</p>
          <button type="button" className="btn btn-sm" onClick={() => void loadItems()}>重试</button>
        </div>
      )}
      {!itemsLoading && !itemsError && targetResolved && <EvidenceCandidatesModule />}
      {!itemsLoading && !itemsError && !targetResolved && sortedObjects.length > 0 && (
        <div className="evidence-conn-list" data-testid="evidence-task-object-list">
          {sortedObjects.map(item => (
            <ObjectCard
              key={item.id}
              item={item}
              selected={state.targetType === item.target_type && state.targetId === item.target_id}
              onOpen={() => openTarget(item.target_type, item.target_id, 'tasks')}
            />
          ))}
        </div>
      )}
      {!itemsLoading && !itemsError && !targetResolved && sortedObjects.length === 0 && (
        <EmptyState
          icon={<Inbox size={24} />}
          title={items.length > 0 && (task?.failed_items ?? 0) > 0 ? '无待处理对象' : '全部处理完成'}
          description={items.length > 0 && (task?.failed_items ?? 0) > 0
            ? '该任务存在失败对象,可回到任务列表查看或重试失败项。'
            : '该任务没有待处理对象。可在右栏已完成区回退对象重新审查。'}
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
