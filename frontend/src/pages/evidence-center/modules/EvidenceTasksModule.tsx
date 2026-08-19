import { useEffect, useMemo, useState } from 'react'
import { Inbox, Search } from 'lucide-react'
import {
  listPaperEvidenceTaskItems,
  pausePaperEvidenceTask,
  resumePaperEvidenceTask,
  retryPaperEvidenceTask,
  type PaperEvidenceTask,
} from '../../../api/endpoints'
import { ApiError } from '../../../api/client'
import { useGlobalGranularity } from '../../../hooks/useGlobalGranularity'
import { useEvidenceCenter, type TaskFilterGroup } from '../EvidenceCenterContext'
import { navigateToEvidenceCandidates } from '../evidenceCenterUrl'
import { CreateBatchTaskDialog } from '../components/CreateBatchTaskDialog'
import { EmptyState } from '../components/EmptyState'
import { ConfirmDialog } from '../../../components/ConfirmDialog'
import { GROUP_TYPES, taskEvidenceProgress } from '../components/TaskFilterPreviewPanel'
import {
  PREPROCESS_OUTCOME_LABELS,
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

const FILTER_CHIPS: { key: TaskFilterGroup; label: string }[] = [
  { key: 'all', label: '全部' },
  { key: 'connection', label: '连接' },
  { key: 'circuit', label: '回路' },
  { key: 'function', label: '功能' },
]

/** 中栏排序:处理中 → 已暂停 → 待验证 → 已完成 → 部分失败 → 失败;组内置信度升序(null 最前) */
const STATUS_GROUP_ORDER: Record<string, number> = {
  processing: 0, paused: 1, awaiting_review: 2, completed: 3, partially_failed: 4, failed: 5,
}

/** 待处理(未完成)状态集合 */
const ACTIVE_STATUSES = new Set(['processing', 'paused', 'awaiting_review', 'partially_failed'])

/** 对象级任务卡片:信息层级统一(标题/Badge → 类型 → 置信度 → 证据进度 → 进度条 → 操作) */
function TaskCard({ task, selected, busy, onSelect, onResume, onPause, onContinue, onRetry }: {
  task: PaperEvidenceTask
  selected: boolean
  busy: CardAction | null
  onSelect: () => void
  onResume: () => void
  onPause: () => void
  onContinue: () => void
  onRetry: () => void
}) {
  const ws = task.work_status
  const cap = task.capabilities ?? {
    can_continue_review: false, can_pause: false, can_resume: false, can_retry_failed: false, can_view_results: false,
  }
  const typeLabel = TARGET_TYPE_LABELS[task.target_type] ?? task.target_type
  // 主标题:中文优先,英文自动提升;副标题:另一语言(单语时隐藏)
  const titleCn = task.display_name_cn?.trim()
  const titleEn = task.display_name_en?.trim()
  const title = titleCn || titleEn || `${typeLabel} #${(task.target_id ?? task.id).slice(0, 8)}`
  const subtitle = titleCn && titleEn && titleEn !== titleCn ? titleEn : null
  const { done, total } = taskEvidenceProgress(task)
  const pct = total > 0 ? Math.round((done / total) * 100) : 0
  const isDone = ws === 'completed'
  const primaryLabel = isDone ? '查看结果' : '继续验证'

  const button = (key: CardAction, label: string, handler: () => void) => (
    <button
      type="button"
      className={`btn btn-xs${key === 'continue' || key === 'view' ? ' btn-primary' : ''}`}
      data-testid={`evidence-task-action-${key}-${task.id}`}
      disabled={busy !== null}
      onClick={e => {
        e.stopPropagation()
        if (busy === null) handler()
      }}
    >
      {busy === key ? BUSY_LABELS[key] : label}
    </button>
  )

  return (
    <div
      role="button"
      tabIndex={0}
      className={`evidence-task-card evidence-task-card-clickable${selected ? ' evidence-task-card-selected' : ''}`}
      data-testid={`evidence-task-card-${task.id}`}
      onClick={onSelect}
      onKeyDown={e => {
        if (e.target !== e.currentTarget) return
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          onSelect()
        }
      }}
    >
      <div className="evidence-task-card-head">
        <span className="evidence-task-card-title">{title}</span>
        <span className={`evidence-task-chip evidence-task-chip-${workStatusTone(ws)}`}>
          {WORK_STATUS_LABELS[ws] ?? ws}
        </span>
      </div>
      {subtitle && <div className="evidence-task-card-subtitle">{subtitle}</div>}
      <div className="evidence-task-card-meta">
        <span className="evidence-task-card-type">{typeLabel}</span>
        {(task.preprocess_outcome === 'non_neural_target' || task.preprocess_outcome === 'evidence_negated') && (
          <span className="evidence-task-chip evidence-task-chip-bad" data-testid={`evidence-task-outcome-${task.id}`}>
            {PREPROCESS_OUTCOME_LABELS[task.preprocess_outcome]}
          </span>
        )}
      </div>
      <div className="evidence-task-card-info-row">
        <span className="evidence-task-card-info-label">当前置信度</span>
        <span className="evidence-task-card-confidence" data-unscored={task.display_confidence == null ? 'true' : 'false'}>
          {formatConfidencePercent(task.display_confidence)}
        </span>
      </div>
      <div className="evidence-task-card-info-row">
        <span className="evidence-task-card-info-label">证据进度</span>
        <span className="evidence-task-card-evidence">{done} / {total}</span>
      </div>
      <div className="evidence-task-card-progress" data-testid={`evidence-task-progress-${task.id}`}>
        <div className="evidence-task-card-progress-bar" style={{ width: `${pct}%` }} />
      </div>
      <div className="evidence-task-card-actions">
        {ws === 'paused' ? (
          button('resume', '继续任务', onResume)
        ) : ws === 'awaiting_review' || ws === 'partially_failed' || ws === 'processing' ? (
          <>
            {button('continue', primaryLabel, onContinue)}
            {ws === 'processing' && cap.can_pause && button('pause', '暂停', onPause)}
            {ws === 'partially_failed' && cap.can_retry_failed && button('retry', '重试失败项', onRetry)}
          </>
        ) : isDone ? (
          button('view', '查看结果', onContinue)
        ) : ws === 'failed' || ws === 'partially_failed' ? (
          button('retry', '重试失败项', onRetry)
        ) : null}
      </div>
    </div>
  )
}

/** 佐证任务中栏:对象级任务卡(点击=选中预览,「继续验证/查看结果」才跳转) */
export function EvidenceTasksModule() {
  const { granularity } = useGlobalGranularity()
  const { state, selectedTaskId, setSelectedTaskId, taskFilterGroup, setTaskFilterGroup } = useEvidenceCenter()
  const { tasks, loading, error, reload } = useEvidenceTaskItems()
  const { refresh } = useTaskItemsRefresh()

  // 深链/右栏点击兼容:module=tasks 携带 target 参数时直接跳转佐证页(与卡片「继续验证」一致)
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
  const [createOpen, setCreateOpen] = useState(false)
  const [busy, setBusy] = useState<{ taskId: string; action: CardAction } | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [retryTarget, setRetryTarget] = useState<PaperEvidenceTask | null>(null)
  const [search, setSearch] = useState('')

  const groupTypes = GROUP_TYPES[taskFilterGroup]

  const filteredTasks = useMemo(() => {
    const kw = search.trim().toLowerCase()
    return [...tasks]
      .filter(t => t.work_status !== 'cancelled' && t.work_status !== 'empty')
      .filter(t => !groupTypes || groupTypes.includes(t.target_type))
      .filter(t => {
        if (!kw) return true
        const title = `${t.display_name_cn ?? ''} ${t.display_name_en ?? ''} ${t.name ?? ''}`.toLowerCase()
        return title.includes(kw)
      })
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
  }, [tasks, groupTypes, search])

  // 轻量摘要:待处理 / 进行中 / 已完成
  const summary = useMemo(() => {
    let pending = 0, processing = 0, completed = 0
    for (const t of filteredTasks) {
      if (ACTIVE_STATUSES.has(t.work_status)) pending += 1
      if (t.work_status === 'processing') processing += 1
      if (t.work_status === 'completed') completed += 1
    }
    return { pending, processing, completed }
  }, [filteredTasks])

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
        <div className="evidence-task-toolbar-row">
          <div className="evidence-task-search">
            <Search size={14} className="evidence-task-search-icon" />
            <input
              className="filter-input evidence-task-search-input"
              placeholder="搜索任务…"
              value={search}
              onChange={e => setSearch(e.target.value)}
              data-testid="evidence-task-search"
            />
          </div>
          <div className="evidence-task-toolbar-spacer" />
          <button type="button" className="btn btn-sm" onClick={reload} data-testid="evidence-task-refresh">刷新</button>
          <button type="button" className="btn btn-sm evidence-task-create-btn" onClick={() => setCreateOpen(true)}>创建批量预处理</button>
        </div>
        <div className="evidence-task-toolbar-row evidence-task-toolbar-row-second">
          <div className="evidence-task-filter-chips" data-testid="evidence-task-filter-chips">
            {FILTER_CHIPS.map(g => (
              <button
                key={g.key}
                type="button"
                className={`btn btn-xs${taskFilterGroup === g.key ? ' btn-primary' : ''}`}
                onClick={() => setTaskFilterGroup(g.key)}
              >
                {g.label}
              </button>
            ))}
          </div>
          <div className="evidence-task-toolbar-spacer" />
          <div className="evidence-task-summary" data-testid="evidence-task-summary">
            待处理 {summary.pending} · 进行中 {summary.processing} · 已完成 {summary.completed}
          </div>
        </div>
      </div>

      {message && <div className="ontology-page-message" data-testid="evidence-task-message">{message}</div>}

      {loading && <div className="evidence-task-loading">加载中…</div>}
      {!loading && error && (
        <div className="evidence-task-error">
          <p>{error}</p>
          <button type="button" className="btn btn-sm" onClick={reload}>重试</button>
        </div>
      )}
      {!loading && !error && filteredTasks.length === 0 && (
        <EmptyState
          icon={<Inbox size={24} />}
          title="暂无佐证任务"
          description="点击右上角「创建批量预处理」创建第一个任务。"
          actionLabel="创建批量预处理"
          onAction={() => setCreateOpen(true)}
        />
      )}
      {!loading && !error && filteredTasks.length > 0 && (
        <div className="evidence-task-card-grid" data-testid="evidence-task-card-grid">
          {filteredTasks.map(t => (
            <TaskCard
              key={t.id}
              task={t}
              selected={selectedTaskId === t.id}
              busy={busy && busy.taskId === t.id ? busy.action : null}
              onSelect={() => setSelectedTaskId(t.id)}
              onResume={() => void handleResume(t)}
              onPause={() => void handlePause(t)}
              onContinue={() => void handleContinueReview(t)}
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
