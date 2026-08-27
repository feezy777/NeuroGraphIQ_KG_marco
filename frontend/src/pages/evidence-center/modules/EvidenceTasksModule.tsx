import { useCallback, useEffect, useMemo, useState } from 'react'
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
import { TaskHistoryList } from '../components/TaskHistoryList'
import { useMacroCandidates } from '../../validation-center/macro-governance/useMacroCandidates'
import { evidenceSelectedTask, macroSelectedTask, useSelectedValidationTask } from '../SelectedValidationTaskContext'
import {
  STAGE_FILTERS,
  SOURCE_FILTERS,
  STAGE_LABELS,
  computeTaskCenterStats,
  filterTaskCenterItems,
  mergeTaskCenterItems,
  paginateTaskCenterItems,
  TASK_CENTER_PAGE_SIZE,
  type TaskCenterItem,
  type TaskSourceType,
} from './taskCenterAdapter'
import { buildEmbeddedUrl } from '../evidenceCenterUrl'
import { deletePaperEvidenceTask } from '../../../api/endpoints'

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

/** 异常结果短标签(长文案 hover 展示,防撑开卡片) */
const OUTCOME_SHORT_LABELS: Record<string, string> = {
  non_neural_target: '⚠ 非神经结构',
  evidence_negated: '⚠ 无证据',
}

/**
 * 对象级任务卡片(布局版本:统一高度 + Footer 固定)
 * 结构: Header(标题2行/Badge) → Meta → 固定信息区(类型/状态/置信度/证据)
 *      → 进度条 → Footer(主按钮 + ⋯菜单,始终贴底)
 * 标签超限一律短标签 + title hover 全文;不因内容改变卡片高度。
 */
function TaskCard({ task, selected, busy, onSelect, onResume, onPause, onContinue, onRetry, onDelete }: {
  task: PaperEvidenceTask
  selected: boolean
  busy: CardAction | null
  onSelect: () => void
  onResume: () => void
  onPause: () => void
  onContinue: () => void
  onRetry: () => void
  onDelete?: () => void
}) {
  const [menuOpen, setMenuOpen] = useState(false)
  const ws = task.work_status
  const cap = task.capabilities ?? {
    can_continue_review: false, can_pause: false, can_resume: false, can_retry_failed: false, can_view_results: false,
  }
  const typeLabel = TARGET_TYPE_LABELS[task.target_type] ?? task.target_type
  // 主标题:中文优先,英文自动提升;副标题:另一语言(单语时隐藏,单行截断)
  const titleCn = task.display_name_cn?.trim()
  const titleEn = task.display_name_en?.trim()
  const title = titleCn || titleEn || `${typeLabel} #${(task.target_id ?? task.id).slice(0, 8)}`
  const subtitle = titleCn && titleEn && titleEn !== titleCn ? titleEn : null
  const { done, total } = taskEvidenceProgress(task)
  const pct = total > 0 ? Math.round((done / total) * 100) : 0
  const isDone = ws === 'completed'
  const primaryLabel = isDone ? '查看结果' : '继续验证'
  const outcome = task.preprocess_outcome === 'non_neural_target' || task.preprocess_outcome === 'evidence_negated'
    ? task.preprocess_outcome
    : null

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
      className={`evidence-task-card evidence-task-card-clickable evidence-task-card-iso${selected ? ' evidence-task-card-selected' : ''}`}
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
        <span className="evidence-task-card-title" title={title}>{title}</span>
        <span className={`evidence-task-chip evidence-task-chip-${workStatusTone(ws)}`}>
          {WORK_STATUS_LABELS[ws] ?? ws}
        </span>
      </div>
      {subtitle && <div className="evidence-task-card-subtitle" title={subtitle}>{subtitle}</div>}

      {/* 固定信息区:类型 / 当前状态 / 置信度 / 证据(不因字段多少变高) */}
      <div className="evidence-task-card-meta">
        <span className="evidence-task-card-type">{typeLabel}</span>
        {outcome && (
          <span
            className="evidence-task-chip evidence-task-chip-bad evidence-task-outcome-short"
            data-testid={`evidence-task-outcome-${task.id}`}
            title={PREPROCESS_OUTCOME_LABELS[outcome]}
          >
            {OUTCOME_SHORT_LABELS[outcome] ?? PREPROCESS_OUTCOME_LABELS[outcome]}
          </span>
        )}
      </div>
      <div className="evidence-task-card-info-row">
        <span className="evidence-task-card-info-label">当前状态</span>
        <span className="evidence-task-card-evidence">{WORK_STATUS_LABELS[ws] ?? ws}</span>
      </div>
      <div className="evidence-task-card-info-row">
        <span className="evidence-task-card-info-label">当前置信度</span>
        <span className="evidence-task-card-confidence" data-unscored={task.display_confidence == null ? 'true' : 'false'}>
          {formatConfidencePercent(task.display_confidence)}
        </span>
      </div>
      <div className="evidence-task-card-info-row">
        <span className="evidence-task-card-info-label">证据</span>
        <span className="evidence-task-card-evidence">{done} / {total}</span>
      </div>
      <div className="evidence-task-card-progress" data-testid={`evidence-task-progress-${task.id}`}>
        <div className="evidence-task-card-progress-bar" style={{ width: `${pct}%` }} />
      </div>

      {/* Footer 固定:主按钮左侧 + ⋯ 菜单右侧(菜单上弹) */}
      <div className="evidence-task-card-footer">
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
        <span
          className="evidence-task-card-menu-btn"
          data-testid={`evidence-task-menu-${task.id}`}
          role="button"
          tabIndex={0}
          onClick={e => { e.stopPropagation(); setMenuOpen(o => !o) }}
          onKeyDown={e => { if (e.target !== e.currentTarget) return; if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setMenuOpen(o => !o) } }}
        >
          ⋯
        </span>
        {menuOpen && (
          <div className="evidence-task-card-menu" data-testid={`evidence-task-menu-list-${task.id}`}>
            <button type="button" className="btn btn-xs" onClick={e => { e.stopPropagation(); setMenuOpen(false); onSelect() }}>
              查看详情
            </button>
            {ws === 'paused' ? (
              <button type="button" className="btn btn-xs" disabled={busy !== null} onClick={e => { e.stopPropagation(); setMenuOpen(false); onResume() }}>恢复任务</button>
            ) : ws === 'processing' && cap.can_pause ? (
              <button type="button" className="btn btn-xs" disabled={busy !== null} onClick={e => { e.stopPropagation(); setMenuOpen(false); onPause() }}>暂停任务</button>
            ) : null}
            {onDelete && (
              <button type="button" className="btn btn-xs btn-danger" data-testid={`evidence-task-menu-delete-${task.id}`}
                onClick={e => { e.stopPropagation(); setMenuOpen(false); onDelete() }}>
                删除任务
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  )
}


/** Macro Paper Discovery 统一卡片（与 EvidenceTaskCard 同视觉;字段映射专用） */
function MacroTaskCard({ item, onOpen }: { item: TaskCenterItem; onOpen: (it: TaskCenterItem) => void }) {
  const stageLabel = STAGE_LABELS[item.workflowStage] ?? item.workflowStage
  const decideTone =
    item.aiDecision === 'supported' ? 'ok' : item.aiDecision === 'uncertain' ? 'warn' : item.aiDecision === 'not_supported' ? 'bad' : ''
  const ruleTone = item.ruleStatus === 'PASS' ? 'ok' : item.ruleStatus === 'BLOCKED' ? 'bad' : ''
  const canContinue = item.aiDecision !== 'not_supported'
  return (
    <div
      role="button"
      tabIndex={0}
      className="evidence-task-card evidence-task-card-clickable evidence-task-card-iso"
      data-testid={`macro-task-card-${item.sourceId ?? item.taskKey}`}
      onClick={() => onOpen(item)}
      onKeyDown={e => {
        if (e.target !== e.currentTarget) return
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onOpen(item) }
      }}
    >
      <div className="evidence-task-card-head">
        <span className="evidence-task-card-title" title={item.title}>{item.title}</span>
        <span className={`evidence-task-chip evidence-task-chip-${stageTone(item.workflowStage)}`}>
          {stageLabel}
        </span>
      </div>
      <div className="evidence-task-card-meta">
        <span className="evidence-task-card-type">{item.sourceLabel} · {item.relationType ?? 'Connection'}</span>
      </div>
      <div className="evidence-task-card-info-row">
        <span className="evidence-task-card-info-label">Ranking</span>
        <span className="evidence-task-card-confidence">{item.rankingScore != null ? item.rankingScore.toFixed(1) : '—'}</span>
      </div>
      <div className="evidence-task-card-info-row">
        <span className="evidence-task-card-info-label">论文 / 证据</span>
        <span className="evidence-task-card-evidence">{item.paperCount ?? '—'} / {item.evidenceCount ?? '—'}</span>
      </div>
      <div className="evidence-task-card-info-row">
        <span className="evidence-task-card-info-label">AI</span>
        <span className={`evidence-task-chip evidence-task-chip-${decideTone || 'neutral'}`}>
          {item.aiDecision
            ? `AI：${AI_DECISION_LABELS[item.aiDecision]}${item.aiConfidence != null ? ` ${Math.round(item.aiConfidence * 100)}%` : ''}`
            : '待AI审核'}
        </span>
      </div>
      <div className="evidence-task-card-info-row">
        <span className="evidence-task-card-info-label">Rule</span>
        <span className={`evidence-task-chip evidence-task-chip-${ruleTone || 'neutral'}`}>
          {item.ruleStatus === 'PASS' ? 'Rule PASS' : item.ruleStatus === 'BLOCKED' ? 'Rule BLOCKED' : 'Rule 待验证'}
        </span>
      </div>
      <div className="evidence-task-card-footer">
        <div className="evidence-task-card-actions">
          <button
            type="button"
            className="btn btn-xs btn-primary"
            disabled={!canContinue}
            title={canContinue ? '按阶段进入验证流程' : 'AI 未支持（不直接进入人工审核）'}
            data-testid={`macro-task-continue-${item.sourceId ?? item.taskKey}`}
            onClick={e => { e.stopPropagation(); if (canContinue) onOpen(item) }}
          >
            {item.aiDecision === null ? '待AI审核' : item.ruleStatus === 'BLOCKED' ? '规则已阻断' : '继续验证'}
          </button>
        </div>
      </div>
    </div>
  )
}

const AI_DECISION_LABELS: Record<string, string> = {
  supported: 'SUPPORTED',
  uncertain: 'UNCERTAIN',
  not_supported: '未支持',
}

/** 宏阶段 → 徽章色调（与原 workStatusTone 对齐语义色） */
function stageTone(stage: string): string {
  if (stage === 'completed') return 'ok'
  if (stage === 'blocked' || stage === 'rule_pending') return 'bad'
  if (stage === 'ai_reviewed' || stage === 'rule_passed') return 'warn'
  if (stage === 'promotion') return 'ok'
  return 'neutral'
}

/** 佐证任务中栏:对象级任务卡(点击=选中预览,「继续验证/查看结果」才跳转) */
export function EvidenceTasksModule() {
  const { granularity } = useGlobalGranularity()
  const { state, selectedTaskId, setSelectedTaskId, taskFilterGroup, setTaskFilterGroup } = useEvidenceCenter()
  const { tasks, loading, error, reload } = useEvidenceTaskItems()
  const { refresh } = useTaskItemsRefresh()
  // Macro Paper Discovery 母集合(1129 rankings,来自统一 MacroCandidatesProvider)
  const { candidates: macroViews } = useMacroCandidates()
  const { setSelectedTask } = useSelectedValidationTask()
  const [sourceFilter, setSourceFilter] = useState<TaskSourceType | 'all'>('all')
  const [stageFilter, setStageFilter] = useState('all')
  const [page, setPage] = useState(1)

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
  // 任务中心视图:当前任务 | 历史任务(最小侵入,三栏结构不变)
  const [view, setView] = useState<'current' | 'history'>('current')
  const [deleteTarget, setDeleteTarget] = useState<PaperEvidenceTask | null>(null)
  const [deleteBusy, setDeleteBusy] = useState(false)

  // 软删除(不物理删除;历史数据保留)
  const handleDeleteTask = useCallback(async () => {
    if (!deleteTarget) return
    setDeleteBusy(true)
    try {
      await deletePaperEvidenceTask(deleteTarget.id)
      setMessage(`任务已删除:「${deleteTarget.display_name_cn ?? deleteTarget.name ?? deleteTarget.target_type}」(软删除,历史保留)`)
      setDeleteTarget(null)
      reload()
    } catch (err) {
      setMessage(`删除失败：${err instanceof Error ? err.message : String(err)}`)
      setDeleteTarget(null)
    } finally {
      setDeleteBusy(false)
    }
  }, [deleteTarget, reload])

  const groupTypes = GROUP_TYPES[taskFilterGroup]

  /** 统一任务中心列表：证据任务 + 1129 Macro（来源字段区分,非独立区块） */
  const allItems = useMemo(() => mergeTaskCenterItems(tasks, macroViews), [tasks, macroViews])
  const filteredItems = useMemo(() => {
    const kw = search.trim().toLowerCase()
    const base = filterTaskCenterItems(allItems, {
      sourceType: sourceFilter,
      stage: stageFilter,
      group: '',
      keyword: kw,
    }).filter(it => {
      // 原分组语义:连接/回路/功能;Macro 均为连接组
      if (!groupTypes) return true
      if (it.evidenceTask) return groupTypes.includes(it.evidenceTask.target_type)
      return groupTypes.includes('connection') || groupTypes.includes('projection')
    }).filter(it => !it.evidenceTask || (it.evidenceTask.work_status !== 'cancelled' && it.evidenceTask.work_status !== 'empty'))
    // 原排序语义保留：Evidence 任务（处理中→暂停→待验证→已完成→部分失败→失败;组内置信度升序）
    const evidence = base.filter(it => it.evidenceTask)
    const macro = base.filter(it => !it.evidenceTask)
    const sortedEvidence = evidence.sort((a, b) => {
      const ta = a.evidenceTask!, tb = b.evidenceTask!
      const ga = STATUS_GROUP_ORDER[ta.work_status] ?? 9
      const gb = STATUS_GROUP_ORDER[tb.work_status] ?? 9
      if (ga !== gb) return ga - gb
      const ca = ta.display_confidence
      const cb = tb.display_confidence
      if (ca === null && cb === null) return 0
      if (ca === null) return -1
      if (cb === null) return 1
      return ca - cb
    })
    // Macro 后置：按 ranking score 降序（稳定）
    macro.sort((a, b) => (b.rankingScore ?? 0) - (a.rankingScore ?? 0))
    return [...sortedEvidence, ...macro]
  }, [allItems, sourceFilter, stageFilter, search, groupTypes])
  const stats = useMemo(() => computeTaskCenterStats(allItems), [allItems])
  const pageCount = Math.max(1, Math.ceil(filteredItems.length / TASK_CENTER_PAGE_SIZE))
  const safePage = Math.min(Math.max(page, 1), pageCount)
  const pageItems = useMemo(() => paginateTaskCenterItems(filteredItems, safePage), [filteredItems, safePage])
  // 翻页重置选择
  useEffect(() => { setSelectedTaskId(null) }, [safePage])

  // 轻量摘要:待处理 / 进行中 / 已完成
  const summary = useMemo(() => {
    let pending = 0, processing = 0, completed = 0
    for (const it of filteredItems) {
      const t = it.evidenceTask
      if (!t) continue
      if (ACTIVE_STATUSES.has(t.work_status)) pending += 1
      if (t.work_status === 'processing') processing += 1
      if (t.work_status === 'completed') completed += 1
    }
    return { pending, processing, completed }
  }, [filteredItems])

  /** Macro 任务「继续验证/规则已阻断」：①先设置统一 SelectedValidationTask
   *  （sourceId=ranking_id,workflowMode 按 duplicate_existing）②再导航（顺序不可反）。
   *  任务身份仅用 ranking_id;URL 深链 stask/ssrc/smode 支持刷新恢复。 */
  const handleMacroContinue = useCallback((it: TaskCenterItem) => {
    if (it.aiDecision === 'not_supported') return
    const rankingId = it.macroView?.ranking?.id ?? it.sourceId ?? ''
    if (!rankingId) return
    const dup = Boolean(it.macroView?.ruleResult?.duplicate_existing)
    const mode = dup ? 'evidence_enhancement' : 'new_knowledge'
    // ① 设置上下文
    setSelectedTask(macroSelectedTask(rankingId, { workflowMode: mode, title: it.title }))
    // ② 再切换 Tab（hash 附带深链参数,刷新可恢复）
    const targetModule = it.workflowStage === 'human_review' ? 'review' : 'candidates'
    const base = buildEmbeddedUrl({ ...state, module: targetModule })
    const extra = `stask=${encodeURIComponent(rankingId)}&ssrc=paper_discovery&smode=${mode}`
    window.location.hash = `${base}${base.includes('?') ? '&' : '?'}${extra}`
  }, [state, setSelectedTask])

  const jumpToCandidates = (task: PaperEvidenceTask) => {
    if (!task.target_id) return
    // 同步统一上下文（旧 navigateToEvidenceCandidates 流程保持原行为）
    setSelectedTask(evidenceSelectedTask(task.id))
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
          <div className="evidence-task-tabs" data-testid="evidence-task-tabs">
            <button
              type="button"
              className={`evidence-module-btn${view === 'current' ? ' active' : ''}`}
              aria-current={view === 'current' ? 'page' : undefined}
              onClick={() => setView('current')}
            >
              当前任务
            </button>
            <button
              type="button"
              className={`evidence-module-btn${view === 'history' ? ' active' : ''}`}
              aria-current={view === 'history' ? 'page' : undefined}
              onClick={() => setView('history')}
            >
              历史任务
            </button>
          </div>
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
                onClick={() => { setTaskFilterGroup(g.key); setPage(1) }}
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
        <div className="evidence-task-toolbar-row evidence-task-toolbar-row-second">
          <span className="evidence-task-toolbar-label">来源</span>
          <div className="evidence-task-filter-chips" data-testid="evidence-task-source-chips" style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
            {SOURCE_FILTERS.map(s => (
              <button
                key={s.key}
                type="button"
                className={`btn btn-xs${sourceFilter === s.key ? ' btn-primary' : ''}`}
                onClick={() => { setSourceFilter(s.key); setPage(1) }}
              >
                {s.label}
              </button>
            ))}
          </div>
        </div>
        <div className="evidence-task-toolbar-row evidence-task-toolbar-row-second">
          <span className="evidence-task-toolbar-label">阶段</span>
          <div className="evidence-task-filter-chips" data-testid="evidence-task-stage-chips" style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
            {STAGE_FILTERS.map(s => (
              <button
                key={s.key}
                type="button"
                className={`btn btn-xs${stageFilter === s.key ? ' btn-primary' : ''}`}
                onClick={() => { setStageFilter(s.key); setPage(1) }}
              >
                {s.label}
              </button>
            ))}
          </div>
        </div>
        <div className="evidence-task-toolbar-row evidence-task-toolbar-row-second evidence-task-toolbar-stats" data-testid="evidence-task-total-stats">
          <span>总任务 <strong>{stats.total}</strong></span>
          <span className="evidence-task-condensed">
            论文发现 <strong>{stats.macroTotal}</strong>
          </span>
          <span className="evidence-task-condensed">AI 审核 <strong>{stats.aiReviewed}</strong>/{stats.macroTotal}</span>
          <span className="evidence-task-condensed">AI 待审核 {stats.aiPending}</span>
          <span className="evidence-task-condensed" title="SUPPORTED / UNCERTAIN / NOT_SUPPORTED">
            SUPPORTED {stats.supported} · UNCERTAIN {stats.uncertain} · 未支持 {stats.notSupported}
          </span>
          <span className="evidence-task-condensed" title="规则状态真实统计">
            Rule PASS {stats.rulePass} · BLOCKED {stats.ruleBlocked} · 待验证 {stats.rulePending}
          </span>
        </div>
      </div>

      {message && <div className="ontology-page-message" data-testid="evidence-task-message">{message}</div>}

      {view === 'history' ? (
        <TaskHistoryList />
      ) : (
        <>
          {loading && <div className="evidence-task-loading">加载中…</div>}
          {!loading && error && (
            <div className="evidence-task-error">
              <p>{error}</p>
              <button type="button" className="btn btn-sm" onClick={reload}>重试</button>
            </div>
          )}
          {!loading && !error && filteredItems.length === 0 && (
            <EmptyState
              icon={<Inbox size={24} />}
              title="暂无佐证任务"
              description="点击右上角「创建批量预处理」创建第一个任务。"
              actionLabel="创建批量预处理"
              onAction={() => setCreateOpen(true)}
            />
          )}
          {!loading && !error && pageItems.length > 0 && (
            <div className="evidence-task-card-grid" data-testid="evidence-task-card-grid">
              {pageItems.map(it => (it.evidenceTask && it.evidenceTask.id ? (
                <TaskCard
                  key={it.taskKey}
                  task={it.evidenceTask}
                  selected={selectedTaskId === it.evidenceTask.id}
                  busy={busy && busy.taskId === it.evidenceTask.id ? busy.action : null}
                  onSelect={() => setSelectedTaskId(it.evidenceTask!.id)}
                  onResume={() => void handleResume(it.evidenceTask!)}
                  onPause={() => void handlePause(it.evidenceTask!)}
                  onContinue={() => void handleContinueReview(it.evidenceTask!)}
                  onRetry={() => setRetryTarget(it.evidenceTask!)}
                  onDelete={() => setDeleteTarget(it.evidenceTask!)}
                />
              ) : (
                <MacroTaskCard item={it} onOpen={handleMacroContinue} />
              )))}
            </div>
          )}

          {!loading && !error && pageItems.length > 0 && (
            <div className="evidence-task-pagination" data-testid="evidence-task-pagination">
              <button type="button" className="btn btn-xs" disabled={safePage <= 1} onClick={() => setPage(p => p - 1)}>
                上一页
              </button>
              <span className="evidence-task-pagination-info">
                第 {safePage} / {pageCount} 页（共 {filteredItems.length} 条 · 每页 {TASK_CENTER_PAGE_SIZE}）
              </span>
              <button type="button" className="btn btn-xs" disabled={safePage >= pageCount} onClick={() => setPage(p => p + 1)}>
                下一页
              </button>
            </div>
          )}
        </>
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

      {/* 软删除确认(不物理删除;历史数据保留) */}
      <ConfirmDialog
        open={deleteTarget !== null}
        title="删除任务"
        message={deleteTarget
          ? `确认删除「${deleteTarget.display_name_cn ?? deleteTarget.name ?? deleteTarget.target_type}」？删除为软删除,历史审核/证据数据全部保留。`
          : undefined}
        confirmLabel="删除"
        danger
        loading={deleteBusy}
        onConfirm={() => void handleDeleteTask()}
        onCancel={() => setDeleteTarget(null)}
      />
    </div>
  )
}
