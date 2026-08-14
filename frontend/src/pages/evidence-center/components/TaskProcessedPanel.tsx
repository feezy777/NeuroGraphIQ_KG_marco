import { useCallback, useEffect, useMemo, useState } from 'react'
import { Inbox } from 'lucide-react'
import {
  listEvidenceReviews,
  reopenPaperEvidenceTaskItem,
  type EvidenceReviewItem,
} from '../../../api/endpoints'
import { useEvidenceCenter } from '../EvidenceCenterContext'
import { EmptyState } from './EmptyState'
import { itemDisplayLabel, TARGET_TYPE_LABELS, TASK_STATUS_LABELS, taskStatusTone } from './taskStatus'
import { useEvidenceTaskItems, type EvidenceQueueItem } from './useEvidenceTaskItems'

/** 已处理(终态)对象集合:completed/skipped/failed */
const PROCESSED_STATUSES = ['completed', 'skipped', 'failed']

const REVIEW_STATUS_LABELS: Record<string, string> = {
  approved: '已审核',
  rejected: '已驳回',
  pending: '待审核',
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

/** 右栏已处理数据面板:终态对象 + 已有审核记录的对象(按处理时间倒序);
 * completed 可两步确认回退重审;点击条目打开工作区查看 */
export function TaskProcessedPanel() {
  const { state, openTarget, openTask } = useEvidenceCenter()
  const taskId = state.taskId
  const { items, taskNames, loading, error, reload } = useEvidenceTaskItems()
  const [reviews, setReviews] = useState<Map<string, EvidenceReviewItem>>(new Map())
  const [reopeningId, setReopeningId] = useState<string | null>(null)
  const [confirmId, setConfirmId] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)

  // 审核记录按 target 建索引:历史审核/晋升走 review 流程,任务对象状态可能仍停留在 awaiting_review
  useEffect(() => {
    let cancelled = false
    listEvidenceReviews({ page_size: 200 })
      .then(r => {
        if (cancelled) return
        setReviews(new Map(r.items.map(rv => [`${rv.target_type}|${rv.target_id}`, rv])))
      })
      .catch(() => {})
    return () => { cancelled = true }
  }, [])

  const processed = useMemo<{ item: EvidenceQueueItem; review: EvidenceReviewItem | null }[]>(() => {
    const seen = new Set<string>()
    const rows: { item: EvidenceQueueItem; review: EvidenceReviewItem | null }[] = []
    for (const it of items) {
      const review = reviews.get(`${it.target_type}|${it.target_id}`) ?? null
      if (PROCESSED_STATUSES.includes(it.status) || review) {
        rows.push({ item: it, review })
        seen.add(`${it.target_type}|${it.target_id}`)
      }
    }
    rows.sort((a, b) => (b.item.updated_at ?? '').localeCompare(a.item.updated_at ?? ''))
    return rows
  }, [items, reviews])

  const handleReopen = useCallback(async (item: EvidenceQueueItem) => {
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
      await reopenPaperEvidenceTaskItem(item.__taskId ?? taskId ?? '', item.id)
      reload()
    } catch (err) {
      setActionError(err instanceof Error ? err.message : String(err))
    } finally {
      setReopeningId(null)
    }
  }, [confirmId, taskId, reload])

  const handleOpen = (item: EvidenceQueueItem) => {
    if (item.__taskId) openTask(item.__taskId)
    openTarget(item.target_type, item.target_id, 'tasks')
  }

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
          description="处理完成或已审核的对象会出现在这里,可回退重新审查。"
          testId="evidence-processed-empty"
        />
      )}
      {!loading && !error && processed.length > 0 && (
        <div className="evidence-queue-done" data-testid="evidence-processed-list">
          {actionError && <div className="ew-meta" style={{ color: 'var(--danger)' }}>回退失败:{actionError}</div>}
          {processed.map(({ item, review }) => (
            <div
              key={item.id}
              className="evidence-queue-done-item"
              data-testid={`evidence-processed-item-${item.target_id}`}
              onClick={() => handleOpen(item)}
            >
              <div className="evidence-queue-done-main">
                <span className="evidence-conn-card-label">{review ? (reviewTargetLabel(review) ?? itemDisplayLabel(item)) : itemDisplayLabel(item)}</span>
                <span className="evidence-conn-card-type">{TARGET_TYPE_LABELS[item.target_type] ?? item.target_type}</span>
                <span style={{ display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
                  <span className={`evidence-task-chip evidence-task-chip-${taskStatusTone(item.status)}`}>
                    {TASK_STATUS_LABELS[item.status] ?? item.status}
                  </span>
                  {review && (
                    <span className={`evidence-task-chip evidence-task-chip-${review.promotion_status === 'promoted' ? 'ok' : 'info'}`}>
                      {review.promotion_status === 'promoted'
                        ? '已晋升'
                        : (REVIEW_STATUS_LABELS[review.review_status] ?? review.review_status)}
                    </span>
                  )}
                  {item.__taskId && (
                    <span className="evidence-queue-task-badge">{taskNames[item.__taskId] ?? item.__taskId}</span>
                  )}
                </span>
              </div>
              {item.status === 'completed' && (
                <button
                  type="button"
                  className="btn btn-xs"
                  data-testid={`evidence-queue-reopen-${item.target_id}`}
                  disabled={reopeningId === item.id}
                  onClick={e => { e.stopPropagation(); void handleReopen(item) }}
                >
                  {reopeningId === item.id ? '回退中…' : (confirmId === item.id ? '确认回退?' : '回退重新审查')}
                </button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
