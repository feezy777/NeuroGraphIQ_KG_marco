import { useCallback, useEffect, useMemo, useState } from 'react'
import { Inbox } from 'lucide-react'
import { listPaperEvidenceTasks, type PaperEvidenceTask } from '../../../api/endpoints'
import { useGlobalGranularity } from '../../../hooks/useGlobalGranularity'
import { useEvidenceCenter } from '../EvidenceCenterContext'
import { CreateBatchTaskDialog } from '../components/CreateBatchTaskDialog'
import { EmptyState } from '../components/EmptyState'
import type { TaskSummaryActions, TaskSummaryData } from '../components/TaskSummary'
import { TASK_REVIEW_LABELS, TASK_STATUS_LABELS, taskReviewTone, taskStatusTone } from '../components/taskStatus'

interface StatusGroup {
  key: string
  label: string
  match: (t: PaperEvidenceTask) => boolean
}

/** 状态分组(任务只落入第一个命中的分组,避免重复展示) */
const STATUS_GROUPS: StatusGroup[] = [
  { key: 'pending', label: '待处理', match: t => t.status === 'pending' },
  { key: 'preprocessing', label: '预处理中', match: t => ['running', 'paused'].includes(t.status) },
  { key: 'awaiting', label: '待人工审核', match: t => t.awaiting_review_items > 0 },
  { key: 'reviewed', label: '已审核', match: t => t.review_status === 'completed' },
  { key: 'done', label: '已完成', match: t => t.status === 'completed' && t.awaiting_review_items === 0 },
  { key: 'failed', label: '失败', match: t => t.failed_items > 0 || t.status === 'failed' },
]

function TaskRow({ task, selected, onSelect, onStartReview, onOpen }: {
  task: PaperEvidenceTask
  selected: boolean
  onSelect: () => void
  onStartReview: () => void
  onOpen: () => void
}) {
  const statusLabel = TASK_STATUS_LABELS[task.status] ?? task.status
  const reviewLabel = TASK_REVIEW_LABELS[task.review_status ?? ''] ?? task.review_status ?? '—'
  const evidenceCount = task.awaiting_review_items + task.processed_items
  return (
    <div
      className={`evidence-task-row${selected ? ' evidence-task-row-selected' : ''}`}
      data-testid={`evidence-task-row-${task.id}`}
      onClick={onSelect}
    >
      <div className="evidence-task-main">
        <span className="evidence-task-name">{task.name || task.target_type}</span>
        <span className="evidence-task-type">{task.target_type}</span>
      </div>
      <div className="evidence-task-stats">
        <span className="evidence-task-stat">已处理 <b>{task.processed_items}</b></span>
        <span className="evidence-task-stat">待审 <b>{task.awaiting_review_items}</b></span>
        <span className="evidence-task-stat">失败数 <b>{task.failed_items}</b></span>
        <span className="evidence-task-stat">佐证数 <b>{evidenceCount}</b></span>
      </div>
      <div className="evidence-task-chips">
        <span className={`evidence-task-chip evidence-task-chip-${taskStatusTone(task.status)}`}>预处理 · {statusLabel}</span>
        <span className={`evidence-task-chip evidence-task-chip-${taskReviewTone(task.review_status)}`}>审核 · {reviewLabel}</span>
      </div>
      <div className="evidence-task-actions">
        <button type="button" className="btn btn-xs" onClick={onStartReview}>开始人工处理</button>
        {task.awaiting_review_items > 0 && (
          <button type="button" className="btn btn-xs" onClick={onOpen}>跳转待审核</button>
        )}
        <button type="button" className="btn btn-xs" onClick={onOpen}>打开任务</button>
      </div>
    </div>
  )
}

export function EvidenceTasksModule() {
  const { state, openTask, setTaskSummary, setTaskSummaryActions } = useEvidenceCenter()
  const { granularity } = useGlobalGranularity()
  const [tasks, setTasks] = useState<PaperEvidenceTask[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [createOpen, setCreateOpen] = useState(false)
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null)

  const loadTasks = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const r = await listPaperEvidenceTasks()
      setTasks(r.items)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { void loadTasks() }, [loadTasks])

  // 选中任务(点击任务行;URL 携带 task_id 时自动选中)
  const handleSelectTask = useCallback((taskId: string) => {
    setSelectedTaskId(prev => (prev === taskId ? prev : taskId))
  }, [])

  useEffect(() => {
    const tid = state.taskId
    if (tid && !selectedTaskId && tasks.some(t => t.id === tid)) setSelectedTaskId(tid)
  }, [state.taskId, selectedTaskId, tasks])

  // 进入证据候选模块,由该模块加载 task 的候选论文
  const handleStartReview = useCallback((task: PaperEvidenceTask) => {
    setSelectedTaskId(task.id)
    openTask(task.id)
  }, [openTask])

  // 选中任务 → Context 推送右栏 TaskSummary(与 S3 reviewDecision / S4 promotionImpact 同模式)
  const selectedTask = selectedTaskId ? tasks.find(t => t.id === selectedTaskId) ?? null : null
  const taskSummary = useMemo<TaskSummaryData | null>(() => {
    if (!selectedTask) return null
    return {
      id: selectedTask.id,
      name: selectedTask.name,
      targetType: selectedTask.target_type,
      mode: selectedTask.mode,
      granularity: selectedTask.granularity_level,
      status: selectedTask.status,
      reviewStatus: selectedTask.review_status,
      total: selectedTask.total_items,
      processed: selectedTask.processed_items,
      awaitingReview: selectedTask.awaiting_review_items,
      failed: selectedTask.failed_items,
      createdAt: selectedTask.created_at,
    }
  }, [selectedTask])

  useEffect(() => { setTaskSummary(taskSummary) }, [taskSummary, setTaskSummary])
  useEffect(() => () => { setTaskSummary(null) }, [setTaskSummary])

  // 右栏操作:创建批量预处理对话框与列表刷新都在本模块内,经 Context 回调暴露
  const handleCreateBatch = useCallback(() => setCreateOpen(true), [])
  useEffect(() => {
    const actions: TaskSummaryActions = { onCreateBatch: handleCreateBatch, onRefresh: loadTasks }
    setTaskSummaryActions(actions)
    return () => {
      setTaskSummaryActions({ onCreateBatch: () => {}, onRefresh: () => {} })
    }
  }, [setTaskSummaryActions, handleCreateBatch, loadTasks])

  // 每个任务只落入第一个命中的分组(按 STATUS_GROUPS 顺序优先)
  const assignedKeys = new Set<string>()
  const groups = STATUS_GROUPS
    .map(g => ({
      ...g,
      tasks: tasks.filter(t => {
        if (assignedKeys.has(t.id)) return false
        if (g.match(t)) { assignedKeys.add(t.id); return true }
        return false
      }),
    }))
    .filter(g => g.tasks.length > 0)

  return (
    <div className="evidence-task-module">
      <div className="evidence-task-toolbar">
        <div className="evidence-task-toolbar-title">
          <h3>任务列表</h3>
          <p className="evidence-module-hint">
            {tasks.length > 0 ? `共 ${tasks.length} 个任务,按处理状态分组展示。` : '按处理状态分组展示。'}
          </p>
        </div>
        <div className="evidence-task-toolbar-actions">
          <button type="button" className="btn btn-sm" onClick={() => void loadTasks()}>刷新</button>
          <button type="button" className="btn btn-sm" onClick={() => setCreateOpen(true)}>创建批量预处理</button>
        </div>
      </div>

      {loading && <div className="evidence-task-loading">加载中…</div>}
      {!loading && error && (
        <div className="evidence-task-error">
          <p>任务加载失败:{error}</p>
          <button type="button" className="btn btn-sm" onClick={() => void loadTasks()}>重试</button>
        </div>
      )}
      {!loading && !error && tasks.length === 0 && (
        <EmptyState
          icon={<Inbox size={24} />}
          title="暂无佐证任务"
          description="点击右上角「创建批量预处理」创建第一个任务。"
        />
      )}
      {!loading && !error && tasks.length > 0 && (
        <div className="evidence-task-groups">
          {groups.map(group => (
            <section key={group.key} className="evidence-task-group">
              <div className="evidence-task-group-head">
                <span className="evidence-task-group-title">{group.label}</span>
                <span className="evidence-task-group-count">{group.tasks.length}</span>
              </div>
              {group.tasks.map(task => (
                <TaskRow
                  key={task.id}
                  task={task}
                  selected={task.id === selectedTaskId}
                  onSelect={() => handleSelectTask(task.id)}
                  onStartReview={() => void handleStartReview(task)}
                  onOpen={() => openTask(task.id)}
                />
              ))}
            </section>
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
