import { useCallback, useEffect, useState } from 'react'
import { listPaperEvidenceTasks, type PaperEvidenceTask } from '../../../api/endpoints'
import { useGlobalGranularity } from '../../../hooks/useGlobalGranularity'
import { useEvidenceCenter } from '../EvidenceCenterContext'
import { CreateBatchTaskDialog } from '../components/CreateBatchTaskDialog'

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

const STATUS_LABELS: Record<string, string> = {
  pending: '待预处理',
  running: '运行中',
  paused: '已暂停',
  completed: '预处理完成',
  failed: '预处理失败',
}

const REVIEW_LABELS: Record<string, string> = {
  not_started: '未开始审核',
  processing: '审核中',
  in_progress: '审核中',
  completed: '审核完成',
}

function statusTone(status: string): string {
  switch (status) {
    case 'completed': return 'ok'
    case 'failed': return 'bad'
    case 'paused': return 'warn'
    case 'running': return 'info'
    default: return 'muted'
  }
}

function reviewTone(reviewStatus: string | null): string {
  if (reviewStatus === 'completed') return 'ok'
  if (reviewStatus === 'processing' || reviewStatus === 'in_progress') return 'info'
  return 'muted'
}

function TaskRow({ task, onStartReview, onOpen }: {
  task: PaperEvidenceTask
  onStartReview: () => void
  onOpen: () => void
}) {
  const statusLabel = STATUS_LABELS[task.status] ?? task.status
  const reviewLabel = REVIEW_LABELS[task.review_status ?? ''] ?? task.review_status ?? '—'
  const evidenceCount = task.awaiting_review_items + task.processed_items
  return (
    <div className="evidence-task-row">
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
        <span className={`evidence-task-chip evidence-task-chip-${statusTone(task.status)}`}>预处理 · {statusLabel}</span>
        <span className={`evidence-task-chip evidence-task-chip-${reviewTone(task.review_status)}`}>审核 · {reviewLabel}</span>
      </div>
      <div className="evidence-task-actions">
        <button type="button" className="btn btn-xs btn-primary" onClick={onStartReview}>开始人工处理</button>
        {task.awaiting_review_items > 0 && (
          <button type="button" className="btn btn-xs" onClick={onOpen}>跳转待审核</button>
        )}
        <button type="button" className="btn btn-xs" onClick={onOpen}>打开任务</button>
      </div>
    </div>
  )
}

export function EvidenceTasksModule() {
  const { openTask } = useEvidenceCenter()
  const { granularity } = useGlobalGranularity()
  const [tasks, setTasks] = useState<PaperEvidenceTask[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [createOpen, setCreateOpen] = useState(false)

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

  // 进入证据候选模块,由该模块加载 task 的候选论文
  const handleStartReview = useCallback((task: PaperEvidenceTask) => {
    openTask(task.id)
  }, [openTask])

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
          <button type="button" className="btn btn-sm btn-primary" onClick={() => setCreateOpen(true)}>创建批量预处理</button>
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
        <div className="evidence-task-empty">暂无佐证任务,点击右上角「创建批量预处理」创建第一个任务。</div>
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
