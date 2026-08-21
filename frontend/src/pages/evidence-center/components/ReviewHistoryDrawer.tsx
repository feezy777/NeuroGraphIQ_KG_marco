import { useEffect, useState } from 'react'
import { getReviewHistory, type ReviewHistoryItem } from '../../../api/endpoints'

const CONCLUSION_LABEL: Record<string, string> = {
  approved: '已审核通过',
  rejected: '已驳回',
  awaiting_review: '待审核',
  draft: '草稿',
}

interface ReviewHistoryDrawerProps {
  open: boolean
  reviewId: string | null
  onClose: () => void
}

/**
 * S7B:版本历史抽屉(只读,不可编辑、不可从旧版本回退)。
 * - 按版本号稳定排序;当前版本明确标识;
 * - 已回退版本显示回退人/时间/原因;
 * - 曾晋升已撤销显示「曾晋升，现已撤销」。
 */
export function ReviewHistoryDrawer({ open, reviewId, onClose }: ReviewHistoryDrawerProps) {
  const [items, setItems] = useState<ReviewHistoryItem[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!open || !reviewId) {
      setItems([])
      return
    }
    let cancelled = false
    setLoading(true)
    setError(null)
    getReviewHistory(reviewId)
      .then(r => { if (!cancelled) setItems(r.items) })
      .catch(err => { if (!cancelled) setError(err instanceof Error ? err.message : String(err)) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [open, reviewId])

  if (!open) return null

  return (
    <div className="dialog-overlay" onClick={e => { if (e.target === e.currentTarget) onClose() }}>
      <div className="dialog-box" data-testid="review-history-drawer">
        <div className="dialog-title">审核历史(只读)</div>
        {loading && <div className="ew-meta">加载中…</div>}
        {!loading && error && <div className="ew-bad">历史加载失败:{error}</div>}
        {!loading && !error && items.length === 0 && <div className="ew-meta">暂无历史版本</div>}
        {!loading && !error && items.length > 0 && (
          <div className="ew-history-list" data-testid="review-history-list">
            {items.map(h => (
              <div
                key={h.review_id}
                className={`ew-history-item${h.is_current ? ' ew-history-item-current' : ''}`}
                data-testid={`review-history-item-${h.review_id}`}
              >
                <div className="ew-history-head">
                  <b>第 {h.revision_no} 次评分</b>
                  {h.is_current && <span className="ew-ok">当前版本</span>}
                  {!h.is_current && <span className="ew-meta">已回退</span>}
                  {h.effective_promotion_status === 'rolled_back' && (
                    <span className="ew-bad">曾晋升，现已撤销</span>
                  )}
                </div>
                <div className="ew-meta">
                  {CONCLUSION_LABEL[h.review_status] ?? h.review_status}
                  {' · '}评分 {h.reviewer_confidence != null ? h.reviewer_confidence.toFixed(2) : '—'}
                  {' · '}{h.approved_at ?? h.rejected_at ?? h.reviewed_at ?? '—'}
                </div>
                {!h.is_current && h.superseded_at && (
                  <div className="ew-meta">
                    回退于 {h.superseded_at}
                    {h.superseded_by ? ` · 操作人 ${h.superseded_by}` : ''}
                  </div>
                )}
                {h.rollback_reason && (
                  <div className="ew-meta">回退原因:{h.rollback_reason}</div>
                )}
              </div>
            ))}
          </div>
        )}
        <div className="dialog-footer">
          <button className="btn" onClick={onClose}>关闭</button>
        </div>
      </div>
    </div>
  )
}
