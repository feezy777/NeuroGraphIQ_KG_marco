import { useCallback, useEffect, useMemo, useState } from 'react'
import { Inbox } from 'lucide-react'
import {
  listEvidenceReviews,
  reopenPaperEvidenceTaskItem,
  rollbackReviewForRescore,
  type EvidenceReviewItem,
  type PaperEvidenceTask,
} from '../../../api/endpoints'
import { ApiError } from '../../../api/client'
import { useEvidenceCenter } from '../EvidenceCenterContext'
import { EmptyState } from './EmptyState'
import { TARGET_TYPE_LABELS, WORK_STATUS_LABELS } from './taskStatus'
import { useEvidenceTaskItems } from './useEvidenceTaskItems'
import { useTaskItemsRefresh } from './taskItemsRefreshContext'
import { RollbackRescoreDialog } from './RollbackRescoreDialog'
import { ReviewHistoryDrawer } from './ReviewHistoryDrawer'

/** 已处理(终态)任务工作状态:一对一后任务 = 对象 */
const PROCESSED_WORK_STATUSES = new Set(['completed', 'partially_failed', 'failed'])

/** review 终态集合(approve/reject 后) */
const TERMINAL_REVIEW_STATUSES = new Set(['approved', 'rejected'])

const REVIEW_STATUS_LABELS: Record<string, string> = {
  approved: '已审核',
  rejected: '已驳回',
  awaiting_review: '待审核',
  draft: '草稿',
  pending: '待审核',
}

/** 关联类型中文标签(九.7) */
const LINK_KIND_LABELS: Record<string, string> = {
  linked: '任务审核',
  legacy: '历史未关联',
  standalone: '独立审核',
}

/** S7B:回退 block reason 中文文案 */
const BLOCK_REASON_LABELS: Record<string, string> = {
  ALREADY_SUPERSEDED: '已回退(历史版本)',
  REJECTED: '已驳回的审核不支持回退',
  NOT_APPROVED: '当前审核状态不支持回退',
  TASK_CANCELLED: '所属任务已取消',
  NO_TASK_ITEM: '找不到关联的任务项',
  AMBIGUOUS_TASK_ITEM: '任务项关联存在歧义',
  ORPHAN_TASK_CONTEXT: '任务关联已失效',
  TARGET_MISSING: '知识对象已不存在',
}

/** 从 review 的 claim 组件取「源脑区 → 靶脑区」中文名(存量对象 label 为 UUID 时的真实名称) */
function reviewTargetLabel(r: EvidenceReviewItem): string | null {
  const comps = r.claim_components_snapshot ?? []
  const nameOf = (type: string): string | undefined => {
    const c = comps.find(x => x.component_type === type)
    const meta = c?.metadata as { name_cn?: string; name_en?: string } | undefined
    return meta?.name_cn || meta?.name_en
  }
  const src = nameOf('source_region')
  const tgt = nameOf('target_region')
  if (src && tgt) return `${src} → ${tgt}`
  return null
}

function reviewTime(r: EvidenceReviewItem): string {
  return r.approved_at ?? r.rejected_at ?? r.reviewed_at ?? r.created_at ?? ''
}

function isTerminalReview(r: EvidenceReviewItem): boolean {
  return TERMINAL_REVIEW_STATUSES.has(r.review_status)
}

/** 同 item/target 多条 review:优先最新终态,否则最新一条(九.6) */
function pickPrimary(reviews: EvidenceReviewItem[]): EvidenceReviewItem {
  const terminal = reviews.filter(isTerminalReview)
  const pool = terminal.length > 0 ? terminal : reviews
  return [...pool].sort((a, b) => reviewTime(b).localeCompare(reviewTime(a)))[0]
}

type RowLink =
  | { kind: 'linked'; review: EvidenceReviewItem; count: number }
  | { kind: 'legacy'; review: EvidenceReviewItem; count: number }

interface ProcessedRow {
  key: string
  /** 一对一:任务即对象(null = standalone review 行) */
  task: PaperEvidenceTask | null
  review: EvidenceReviewItem | null
  linkKind: 'linked' | 'legacy' | 'standalone' | 'none'
  reviewCount: number
  /** 该行关联 review 中是否存在终态(决定旧 reopen 入口是否隐藏,十一.3) */
  hasTerminalReview: boolean
}

/**
 * 右栏已处理数据面板(九):
 * - 一对一模型:已处理对象 = 终态任务(work_status completed/partially_failed/failed),直接来自任务列表
 *   (display/item_id 字段由列表接口批量返回,不再逐任务拉 items——避免任务数=对象数时的并发风暴);
 * - review 关联:精确 task_item_id → 兼容 task_id+target(历史未关联)→ standalone(仅全局视图);
 * - 旧 reopen 入口仅对「无终态 review 的 completed 任务」开放,文案「重新打开任务项」(十一.4)。
 */
export function TaskProcessedPanel() {
  const { state, openTaskTarget, openTarget } = useEvidenceCenter()
  const taskId = state.taskId
  const { tasks, loading, error, reload } = useEvidenceTaskItems()
  const { version, refresh } = useTaskItemsRefresh()
  const [reviews, setReviews] = useState<EvidenceReviewItem[]>([])
  const [reopeningId, setReopeningId] = useState<string | null>(null)
  const [confirmId, setConfirmId] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  // S7B:回退并重新评分
  const [rollbackTarget, setRollbackTarget] = useState<{ review: EvidenceReviewItem; name: string } | null>(null)
  const [rollbackBusy, setRollbackBusy] = useState(false)
  const [rollbackError, setRollbackError] = useState<string | null>(null)
  const [historyReviewId, setHistoryReviewId] = useState<string | null>(null)

  // 审核记录整体拉取;共享刷新版本变化时重取(八:approve/reject 后右栏同步)
  useEffect(() => {
    let cancelled = false
    listEvidenceReviews({ page_size: 200 })
      .then(r => { if (!cancelled) setReviews(r.items) })
      .catch(() => {})
    return () => { cancelled = true }
  }, [version])

  const processed = useMemo<ProcessedRow[]>(() => {
    // 分组:精确 task_item_id / 兼容 task_id+target(仅缺 task_item_id 的 review)/ standalone
    const byItem = new Map<string, EvidenceReviewItem[]>()
    const byTaskTarget = new Map<string, EvidenceReviewItem[]>()
    const standalone: EvidenceReviewItem[] = []
    for (const rv of reviews) {
      if (rv.task_item_id) {
        const arr = byItem.get(rv.task_item_id) ?? []
        arr.push(rv)
        byItem.set(rv.task_item_id, arr)
      } else if (rv.task_id) {
        const k = `${rv.task_id}|${rv.target_type}|${rv.target_id}`
        const arr = byTaskTarget.get(k) ?? []
        arr.push(rv)
        byTaskTarget.set(k, arr)
      } else {
        standalone.push(rv)
      }
    }

    const rows: ProcessedRow[] = []
    for (const t of tasks) {
      if (!PROCESSED_WORK_STATUSES.has(t.work_status)) continue
      if (!t.item_id) continue // 旧任务无 item(迁移后应已回填)
      const linked = byItem.get(t.item_id)
      let link: RowLink | null = null
      if (linked?.length) {
        link = { kind: 'linked', review: pickPrimary(linked), count: linked.length }
      } else {
        // 兼容关联(九.2):review 缺 task_item_id 但有可靠 task_id
        const taskKey = `${t.id}|${t.target_type}|${t.target_id ?? t.id}`
        const legacy = byTaskTarget.get(taskKey)
        if (legacy?.length) {
          link = { kind: 'legacy', review: pickPrimary(legacy), count: legacy.length }
        }
      }
      const terminal = Boolean(link && isTerminalReview(link.review))
      rows.push({
        key: `item:${t.item_id}`,
        task: t,
        review: link?.review ?? null,
        linkKind: link?.kind ?? 'none',
        reviewCount: link?.count ?? 0,
        hasTerminalReview: terminal,
      })
    }

    // standalone review 仅在全局视图出现,以 review.id 为记录身份(九.3/4)
    if (!taskId) {
      for (const rv of standalone) {
        rows.push({
          key: `review:${rv.id}`,
          task: null,
          review: rv,
          linkKind: 'standalone',
          reviewCount: 1,
          hasTerminalReview: isTerminalReview(rv),
        })
      }
    }

    const timeOf = (row: ProcessedRow): string =>
      (row.review ? reviewTime(row.review) : row.task?.finished_at) ?? ''
    rows.sort((a, b) => timeOf(b).localeCompare(timeOf(a)))
    return rows
  }, [tasks, reviews, taskId])

  const handleReopen = useCallback(async (row: ProcessedRow) => {
    const task = row.task
    if (!task || !task.item_id) return
    if (confirmId !== task.item_id) {
      setConfirmId(task.item_id)
      window.setTimeout(() => {
        setConfirmId(prev => (prev === task.item_id ? null : prev))
      }, 3000)
      return
    }
    setConfirmId(null)
    setReopeningId(task.item_id)
    setActionError(null)
    try {
      await reopenPaperEvidenceTaskItem(task.id, task.item_id)
      reload()
    } catch (err) {
      setActionError(err instanceof Error ? err.message : String(err))
    } finally {
      setReopeningId(null)
    }
  }, [confirmId, reload])

  const handleOpenItem = (row: ProcessedRow) => {
    const t = row.task
    if (!t) return
    // 原子导航;真实任务 item 传真实 id(三.3);深链会由 tasks 模块跳转佐证页
    openTaskTarget(t.id, t.target_type, t.target_id ?? t.id, t.item_id)
  }

  const handleOpenStandalone = (rv: EvidenceReviewItem) => {
    // standalone 不得归属到任意任务 → 以 candidates 打开对象(九.3)
    openTarget(rv.target_type, rv.target_id, 'candidates')
  }

  // ─── S7B:回退并重新评分 ───
  const handleRollbackConfirm = useCallback(async (reason: string, idempotencyKey: string) => {
    if (!rollbackTarget) return
    setRollbackBusy(true)
    setRollbackError(null)
    try {
      const resp = await rollbackReviewForRescore(rollbackTarget.review.id, { reason, idempotency_key: idempotencyKey })
      // 成功:共享刷新(任务/items/reviews/左右栏)+ 按 navigation 原子导航
      setRollbackTarget(null)
      refresh()
      openTaskTarget(
        resp.navigation.task_id,
        resp.navigation.target_type,
        resp.navigation.target_id,
        resp.navigation.task_item_id,
      )
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 403) {
          setRollbackError('没有权限执行回退重评')
          return
        }
        if (err.status === 409) {
          // 已被他人回退/状态已变化 → 刷新展示最新状态
          setRollbackTarget(null)
          refresh()
          setActionError('状态已变化(可能已被其他用户回退),列表已刷新')
          return
        }
        setRollbackError(`回退失败:${err.message}`)
        return
      }
      setRollbackError(`回退失败(网络错误):${err instanceof Error ? err.message : String(err)}`)
    } finally {
      setRollbackBusy(false)
    }
  }, [rollbackTarget, refresh, openTaskTarget])

  const rowName = (row: ProcessedRow): string => {
    if (row.review) {
      const label = reviewTargetLabel(row.review)
      if (label) return label
    }
    const t = row.task
    if (t) {
      return t.display_name_cn ?? t.display_name_en
        ?? `${TARGET_TYPE_LABELS[t.target_type] ?? t.target_type} #${(t.target_id ?? t.id).slice(0, 8)}`
    }
    return `${row.review ? TARGET_TYPE_LABELS[row.review.target_type] ?? row.review.target_type : ''} ${row.review ? row.review.target_id.slice(0, 8) : ''}`
  }

  const reviewChip = (row: ProcessedRow): string | null => {
    const rv = row.review
    if (!rv) return null
    if (rv.promotion_status === 'promoted') return '已晋升'
    return REVIEW_STATUS_LABELS[rv.review_status] ?? rv.review_status
  }

  const reviewChipTone = (row: ProcessedRow): string => {
    const rv = row.review
    if (!rv) return 'muted'
    if (rv.promotion_status === 'promoted') return 'ok'
    if (rv.review_status === 'approved') return 'ok'
    if (rv.review_status === 'rejected') return 'bad'
    return 'info'
  }

  const reopenVisible = (row: ProcessedRow): boolean =>
    row.task !== null && row.task.work_status === 'completed' && !row.hasTerminalReview

  return (
    <div className="evidence-task-queue" data-testid="evidence-processed-panel">
      <div className="evidence-task-queue-head">
        <h4>已处理数据</h4>
        <button type="button" className="btn btn-xs" onClick={reload}>刷新</button>
      </div>

      {loading && <div className="evidence-task-loading">加载中…</div>}
      {!loading && error && (
        <div className="evidence-task-error">
          <p>已处理列表加载失败:{error}</p>
          <button type="button" className="btn btn-sm" onClick={reload}>重试</button>
        </div>
      )}
      {!loading && !error && processed.length === 0 && (
        <EmptyState
          compact
          icon={<Inbox size={20} />}
          title="暂无已处理对象"
          description="处理完成或已审核的对象会出现在这里,可重新打开任务项再次处理。"
          testId="evidence-processed-empty"
        />
      )}
      {!loading && !error && processed.length > 0 && (
        <div className="evidence-queue-done" data-testid="evidence-processed-list">
          {actionError && <div className="ew-meta" style={{ color: 'var(--danger)' }}>重新打开失败:{actionError}</div>}
          {processed.map(row => {
            const testId = row.task
              ? `evidence-processed-item-${row.task.target_id ?? row.task.id}`
              : `evidence-standalone-review-${row.review?.id}`
            return (
              <div
                key={row.key}
                role="button"
                tabIndex={0}
                className="evidence-queue-done-item evidence-queue-done-item-clickable"
                data-testid={testId}
                onClick={() => (row.task ? handleOpenItem(row) : row.review && handleOpenStandalone(row.review))}
                onKeyDown={e => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault()
                    if (row.task) handleOpenItem(row)
                    else if (row.review) handleOpenStandalone(row.review)
                  }
                }}
              >
                <div className="evidence-queue-done-main">
                  <span className="evidence-conn-card-label">{rowName(row)}</span>
                  <span className="evidence-conn-card-type">
                    {TARGET_TYPE_LABELS[row.task?.target_type ?? row.review?.target_type ?? ''] ?? row.task?.target_type ?? row.review?.target_type}
                  </span>
                  <span style={{ display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
                    {row.task && (
                      <span className={`evidence-task-chip evidence-task-chip-${row.task.work_status === 'completed' ? 'ok' : 'bad'}`}>
                        {WORK_STATUS_LABELS[row.task.work_status] ?? row.task.work_status}
                      </span>
                    )}
                    {row.review && (
                      <span
                        className={`evidence-task-chip evidence-task-chip-${reviewChipTone(row)}`}
                        data-testid={`${testId}-review-status`}
                      >
                        {reviewChip(row)}
                      </span>
                    )}
                    {row.review?.effective_promotion_status === 'rolled_back' && (
                      <span className="evidence-task-chip evidence-task-chip-bad" data-testid={`${testId}-rolled-back`}>
                        曾晋升，现已撤销
                      </span>
                    )}
                    {row.review && row.review.revision_no > 1 && (
                      <span className="evidence-task-chip evidence-task-chip-muted" data-testid={`${testId}-revision`}>
                        第 {row.review.revision_no} 次评分
                      </span>
                    )}
                    {row.linkKind !== 'none' && (
                      <span className="evidence-task-chip evidence-task-chip-muted" data-testid={`${testId}-link-kind`}>
                        {LINK_KIND_LABELS[row.linkKind]}
                      </span>
                    )}
                  </span>
                  {(row.review || row.reviewCount > 1) && (
                    <span className="ew-meta" data-testid={`${testId}-review-time`}>
                      审核时间 {row.review ? new Date(reviewTime(row.review)).toLocaleString() : '—'}
                      {row.reviewCount > 1 ? ` · 另有 ${row.reviewCount - 1} 条历史审核` : ''}
                    </span>
                  )}
                </div>
                {reopenVisible(row) && row.task && (
                  <button
                    type="button"
                    className="btn btn-xs"
                    data-testid={`evidence-queue-reopen-${row.task.target_id ?? row.task.id}`}
                    disabled={reopeningId === row.task.item_id}
                    onClick={e => { e.stopPropagation(); void handleReopen(row) }}
                  >
                    {reopeningId === row.task.item_id ? '重新打开中…' : (confirmId === row.task.item_id ? '确认重新打开?' : '重新打开任务项')}
                  </button>
                )}
                {/* S7B:仅后端 capability=true 显示回退按钮(前端不按字符串状态自行开放) */}
                {row.review?.can_rollback_rescore === true && (
                  <button
                    type="button"
                    className="btn btn-xs"
                    data-testid={`evidence-rollback-rescore-${row.review.id}`}
                    disabled={rollbackBusy}
                    onClick={e => {
                      e.stopPropagation()
                      setRollbackError(null)
                      setRollbackTarget({ review: row.review!, name: rowName(row) })
                    }}
                  >
                    回退并重新评分
                  </button>
                )}
                {row.review && (
                  <button
                    type="button"
                    className="btn btn-xs"
                    data-testid={`evidence-review-history-${row.review.id}`}
                    onClick={e => { e.stopPropagation(); setHistoryReviewId(row.review!.id) }}
                  >
                    查看审核历史
                  </button>
                )}
                {row.task && row.task.work_status === 'completed' && row.hasTerminalReview && row.review && !row.review.can_rollback_rescore && (
                  <span className="ew-meta" data-testid={`${testId}-rollback-hint`}>
                    {row.review.superseded_at
                      ? '已回退(历史版本),等待重新评分'
                      : `回退重评不可用:${BLOCK_REASON_LABELS[row.review.rollback_block_reason ?? ''] ?? '回退重评功能将在审核版本关联完成后开放'}`}
                  </span>
                )}
              </div>
            )
          })}
        </div>
      )}

      <RollbackRescoreDialog
        open={rollbackTarget !== null}
        review={rollbackTarget?.review ?? null}
        objectName={rollbackTarget?.name ?? ''}
        busy={rollbackBusy}
        error={rollbackError}
        onClose={() => { if (!rollbackBusy) { setRollbackTarget(null); setRollbackError(null) } }}
        onConfirm={(reason, key) => void handleRollbackConfirm(reason, key)}
      />
      <ReviewHistoryDrawer
        open={historyReviewId !== null}
        reviewId={historyReviewId}
        onClose={() => setHistoryReviewId(null)}
      />
      {processed.length > 0 && (
        <button type="button" className="evidence-processed-view-all" data-testid="evidence-processed-view-all">
          查看全部 &gt;
        </button>
      )}
    </div>
  )
}
