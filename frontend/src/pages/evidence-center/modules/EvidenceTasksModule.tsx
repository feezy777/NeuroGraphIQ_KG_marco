import { useEffect, useMemo, useState } from 'react'
import { Inbox } from 'lucide-react'
import {
  listPaperEvidenceTaskItems,
  pausePaperEvidenceTask,
  resumePaperEvidenceTask,
  retryPaperEvidenceTask,
  type PaperEvidenceTask,
} from '../../../api/endpoints'
import { ApiError } from '../../../api/client'
import { useGlobalGranularity } from '../../../hooks/useGlobalGranularity'
import { useEvidenceCenter } from '../EvidenceCenterContext'
import { navigateToEvidenceCandidates } from '../evidenceCenterUrl'
import { CreateBatchTaskDialog } from '../components/CreateBatchTaskDialog'
import { EmptyState } from '../components/EmptyState'
import { ConfirmDialog } from '../../../components/ConfirmDialog'
import {
  TARGET_TYPE_LABELS,
  WORK_STATUS_LABELS,
  formatConfidencePercent,
  objectCardTitle,
  workStatusTone,
} from '../components/taskStatus'
import { useEvidenceTaskItems } from '../components/useEvidenceTaskItems'
import { useTaskItemsRefresh } from '../components/taskItemsRefreshContext'

type CardAction = 'resume' | 'pause' | 'retry' | 'continue' | 'view'

const BUSY_LABELS: Record<string, string> = {
  resume: '正在恢复…',
  pause: '正在暂停…',
  retry: '正在重试…',
  continue: '正在查找…',
}

/** 中栏排序:处理中 → 已暂停 → 待验证 → 已完成 → 部分失败 → 失败;组内置信度升序(null 最前) */
const STATUS_GROUP_ORDER: Record<string, number> = {
  processing: 0, paused: 1, awaiting_review: 2, completed: 3, partially_failed: 4, failed: 5,
}

const GROUP_FILTERS: { key: string; label: string; types: string[] | null }[] = [
  { key: 'all', label: '全部', types: null },
  { key: 'connection', label: '连接', types: ['connection', 'projection'] },
  { key: 'circuit', label: '回路', types: ['circuit', 'circuit_step', 'circuit_function'] },
  { key: 'function', label: '功能', types: ['region_function', 'projection_function'] },
]

/** 对象级任务卡片:标题=对象中英文名;整卡点击跳转证据佐证页(与数据中心入口一致) */
function TaskCard({ task, busy, onJump, onResume, onPause, onRetry }: {
  task: PaperEvidenceTask
  busy: CardAction | null
  onJump: () => void
  onResume: () => void
  onPause: () => void
  onRetry: () => void
}) {
  const ws = task.work_status
  const cap = task.capabilities ?? {
    can_continue_review: false, can_pause: false, can_resume: false, can_retry_failed: false, can_view_results: false,
  }
  const typeLabel = TARGET_TYPE_LABELS[task.target_type] ?? task.target_type
  const fallback = `${typeLabel} #${(task.target_id ?? task.id).slice(0, 8)}`
  const title = objectCardTitle(task.display_name_cn, task.display_name_en, fallback)

  let primary: { key: CardAction; label: string; handler: () => void } | null = null
  let secondary: { key: CardAction; label: string; handler: () => void } | null = null
  if (ws === 'paused') {
    primary = { key: 'resume', label: '继续任务', handler: onResume }
  } else if (ws === 'awaiting_review' || (cap.can_continue_review && ws === 'partially_failed')) {
    primary = { key: 'continue', label: '继续验证', handler: onJump }
    if (ws === 'partially_failed' && cap.can_retry_failed) {
      secondary = { key: 'retry', label: '重试失败项', handler: onRetry }
    }
  } else if (ws === 'processing') {
    primary = { key: 'view', label: '查看进度', handler: onJump }
    if (cap.can_pause) secondary = { key: 'pause', label: '暂停', handler: onPause }
  } else if (ws === 'partially_failed' || ws === 'failed') {
    primary = { key: 'retry', label: '重试失败项', handler: onRetry }
  } else if (ws === 'completed') {
    primary = { key: 'view', label: '查看结果', handler: onJump }
  }

  const button = (a: { key: CardAction; label: string; handler: () => void }) => (
    <button
      type="button"
      className="btn btn-xs"
      data-testid={`evidence-task-action-${a.key}-${task.id}`}
      disabled={busy !== null}
      onClick={e => {
        e.stopPropagation()
        if (busy === null) a.handler()
      }}
    >
      {busy === a.key ? BUSY_LABELS[a.key] : a.label}
    </button>
  )

  return (
    <div
      role="button"
      tabIndex={0}
      className="evidence-task-card evidence-task-card-clickable"
      data-testid={`evidence-task-card-${task.id}`}
      onClick={onJump}
      onKeyDown={e => {
        if (e.target !== e.currentTarget) return
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          onJump()
        }
      }}
    >
      <div className="evidence-task-card-head">
        <span className="evidence-task-card-title">{title}</span>
        <span className={`evidence-task-chip evidence-task-chip-${workStatusTone(ws)}`}>
          {WORK_STATUS_LABELS[ws] ?? ws}
        </span>
      </div>
      <div className="evidence-task-card-meta">
        <span className="evidence-task-card-type">{typeLabel}</span>
        <span className="evidence-task-card-confidence">{formatConfidencePercent(task.display_confidence)}</span>
      </div>
      {task.name && <div className="evidence-task-card-remark">{task.name}</div>}
      {(primary || secondary) && (
        <div className="evidence-task-card-actions">
          {primary && button(primary)}
          {secondary && button(secondary)}
        </div>
      )}
    </div>
  )
}

/** 佐证任务中栏:对象级任务卡列表(整卡跳转证据佐证页) */
export function EvidenceTasksModule() {
  const { granularity } = useGlobalGranularity()
  const { state } = useEvidenceCenter()
  const { tasks, loading, error, reload } = useEvidenceTaskItems()
  const { refresh } = useTaskItemsRefresh()
  const [createOpen, setCreateOpen] = useState(false)
  const [busy, setBusy] = useState<{ taskId: string; action: CardAction } | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [retryTarget, setRetryTarget] = useState<PaperEvidenceTask | null>(null)
  const [group, setGroup] = useState('all')

  // 深链/右栏点击兼容:module=tasks 携带 target 参数时直接跳转佐证页(与卡片点击一致)
  useEffect(() => {
    if (state.module !== 'tasks' || !state.targetType || !state.targetId) return
    const t = tasks.find(x => x.id === state.taskId)
    navigateToEvidenceCandidates({
      items: [{
        target_type: state.targetType,
        target_id: state.targetId,
        label: t?.display_name_cn ?? t?.display_name_en ?? '',
        confidence: t?.display_confidence ?? null,
      }],
      taskId: state.taskId,
    })
  }, [state.module, state.targetType, state.targetId, state.taskId, tasks])

  const sortedTasks = useMemo(() => {
    const groupTypes = GROUP_FILTERS.find(g => g.key === group)?.types ?? null
    return [...tasks]
      .filter(t => t.work_status !== 'cancelled' && t.work_status !== 'empty')
      .filter(t => !groupTypes || groupTypes.includes(t.target_type))
      .sort((a, b) => {
        const ga = STATUS_GROUP_ORDER[a.work_status] ?? 9
        const gb = STATUS_GROUP_ORDER[b.work_status] ?? 9
        if (ga !== gb) return ga - gb
        const ca = a.display_confidence
        const cb = b.display_confidence
        if (ca === null && cb === null) return 0
        if (ca === null) return -1
        if (cb === null) return 1
        return ca - cb
      })
  }, [tasks, group])

  const jumpToCandidates = (task: PaperEvidenceTask) => {
    if (!task.target_id) return
    navigateToEvidenceCandidates({
      items: [{
        target_type: task.target_type,
        target_id: task.target_id,
        label: task.display_name_cn ?? task.display_name_en ?? '',
        confidence: task.display_confidence ?? null,
      }],
      taskId: task.id,
    })
  }

  const handleOpError = (err: unknown, action: string) => {
    if (err instanceof ApiError) {
      if (err.status === 403) {
        setMessage(`操作失败(${action}):无权限`)
        return
      }
      if (err.status === 400 || err.status === 409) {
        setMessage('任务状态已变化,已刷新。')
        reload()
        return
      }
    }
    setMessage(`操作失败(${action}):${err instanceof Error ? err.message : String(err)}`)
  }

  const handleResume = async (task: PaperEvidenceTask) => {
    setBusy({ taskId: task.id, action: 'resume' })
    setMessage(null)
    try {
      await resumePaperEvidenceTask(task.id)
      setMessage('任务已恢复。')
      refresh()
    } catch (err) {
      handleOpError(err, '恢复')
    } finally {
      setBusy(null)
    }
  }

  const handlePause = async (task: PaperEvidenceTask) => {
    setBusy({ taskId: task.id, action: 'pause' })
    setMessage(null)
    try {
      await pausePaperEvidenceTask(task.id)
      setMessage('任务已暂停。')
      refresh()
    } catch (err) {
      handleOpError(err, '暂停')
    } finally {
      setBusy(null)
    }
  }

  const handleRetry = async (task: PaperEvidenceTask) => {
    setRetryTarget(null)
    setBusy({ taskId: task.id, action: 'retry' })
    setMessage(null)
    try {
      await retryPaperEvidenceTask(task.id)
      setMessage('失败项已重新进入处理队列。')
      refresh()
    } catch (err) {
      handleOpError(err, '重试')
    } finally {
      setBusy(null)
    }
  }

  const handleContinueReview = async (task: PaperEvidenceTask) => {
    if (task.target_id) {
      jumpToCandidates(task)
      return
    }
    // 旧任务兜底:查一条待验证对象再跳转
    setBusy({ taskId: task.id, action: 'continue' })
    setMessage(null)
    try {
      const r = await listPaperEvidenceTaskItems(task.id, {
        status: 'awaiting_review', limit: 1, sort: 'confidence',
      })
      const item = r.items[0]
      if (item && item.target_id) {
        navigateToEvidenceCandidates({
          items: [{
            target_type: item.target_type,
            target_id: item.target_id,
            label: item.display_name ?? '',
            confidence: item.display_confidence ?? null,
          }],
          taskId: task.id,
        })
      } else {
        reload()
        setMessage('当前没有待验证对象。')
      }
    } catch (err) {
      handleOpError(err, '继续验证')
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="evidence-task-module">
      <div className="evidence-task-toolbar">
        <div className="evidence-task-toolbar-title">
          <h3>佐证任务</h3>
          <p className="evidence-module-hint">
            一个任务 = 一个知识对象;点击卡片进入证据佐证页,卡片按钮执行对应操作。
          </p>
        </div>
        <div className="evidence-task-toolbar-actions">
          <button type="button" className="btn btn-sm" onClick={reload}>刷新</button>
          <button type="button" className="btn btn-sm" onClick={() => setCreateOpen(true)}>创建批量预处理</button>
        </div>
      </div>

      <div className="evidence-task-filter-chips" data-testid="evidence-task-filter-chips">
        {GROUP_FILTERS.map(g => (
          <button
            key={g.key}
            type="button"
            className={`btn btn-xs${group === g.key ? ' btn-primary' : ''}`}
            onClick={() => setGroup(g.key)}
          >
            {g.label}
          </button>
        ))}
      </div>

      {message && <div className="ontology-page-message" data-testid="evidence-task-message">{message}</div>}

      {loading && <div className="evidence-task-loading">加载中…</div>}
      {!loading && error && (
        <div className="evidence-task-error">
          <p>{error}</p>
          <button type="button" className="btn btn-sm" onClick={reload}>重试</button>
        </div>
      )}
      {!loading && !error && sortedTasks.length === 0 && (
        <EmptyState
          icon={<Inbox size={24} />}
          title="暂无佐证任务"
          description="点击右上角「创建批量预处理」创建第一个任务。"
          actionLabel="创建批量预处理"
          onAction={() => setCreateOpen(true)}
        />
      )}
      {!loading && !error && sortedTasks.length > 0 && (
        <div className="evidence-task-card-grid" data-testid="evidence-task-card-grid">
          {sortedTasks.map(t => (
            <TaskCard
              key={t.id}
              task={t}
              busy={busy && busy.taskId === t.id ? busy.action : null}
              onJump={() => {
                if (t.target_id) jumpToCandidates(t)
                else void handleContinueReview(t)
              }}
              onResume={() => void handleResume(t)}
              onPause={() => void handlePause(t)}
              onRetry={() => setRetryTarget(t)}
            />
          ))}
        </div>
      )}

      <ConfirmDialog
        open={retryTarget !== null}
        title="重试失败项"
        message={retryTarget ? `将重新处理 ${retryTarget.item_counts?.failed ?? 0} 个失败对象。` : undefined}
        confirmLabel="确认重试"
        danger
        loading={busy?.action === 'retry'}
        onConfirm={() => retryTarget && void handleRetry(retryTarget)}
        onCancel={() => setRetryTarget(null)}
      />

      <CreateBatchTaskDialog
        open={createOpen}
        granularity={granularity}
        onClose={() => setCreateOpen(false)}
        onCreated={() => { setCreateOpen(false); reload() }}
      />
    </div>
  )
}
