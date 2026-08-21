import { useEffect, useMemo, useState } from 'react'
import type { EvidenceReviewItem } from '../../../api/endpoints'
import { ConfirmDialog } from '../../../components/ConfirmDialog'

const REVIEW_CONCLUSION_LABEL: Record<string, string> = {
  approved: '已审核通过',
  rejected: '已驳回',
  awaiting_review: '待审核',
}

interface RollbackRescoreDialogProps {
  open: boolean
  review: EvidenceReviewItem | null
  objectName: string
  busy: boolean
  error: string | null
  onClose: () => void
  /** reason 已 trim 非空;idempotencyKey 每次操作生成 */
  onConfirm: (reason: string, idempotencyKey: string) => void
}

/**
 * S7B:回退并重新评分确认弹窗。
 * - 必填回退原因(trim 后为空不能提交);
 * - 展示对象名/版本/结论/评分/晋升状态与影响;
 * - 请求期间禁用关闭与重复提交;每次操作生成 idempotency_key。
 */
export function RollbackRescoreDialog({
  open,
  review,
  objectName,
  busy,
  error,
  onClose,
  onConfirm,
}: RollbackRescoreDialogProps) {
  const [reason, setReason] = useState('')
  const [reasonTouched, setReasonTouched] = useState(false)
  const idempotencyKey = useMemo(
    () => (typeof crypto !== 'undefined' && crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`),
    // 每次打开生成一次
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [open],
  )

  useEffect(() => {
    if (open) {
      setReason('')
      setReasonTouched(false)
    }
  }, [open])

  const reasonEmpty = reason.trim().length === 0

  const handleConfirm = () => {
    setReasonTouched(true)
    if (reasonEmpty || busy) return
    onConfirm(reason.trim(), idempotencyKey)
  }

  const handleClose = () => {
    if (busy) return
    onClose()
  }

  return (
    <ConfirmDialog
      open={open}
      title="回退并重新评分"
      confirmLabel="回退并重新评分"
      danger
      loading={busy}
      testId="rollback-rescore-dialog"
      onConfirm={handleConfirm}
      onCancel={handleClose}
    >
      <div className="ew-rollback-body">
        <p className="dialog-msg">
          <b>{objectName}</b>
        </p>
        <div className="ew-rollback-facts">
          <span>第 {review?.revision_no ?? '—'} 次评分</span>
          <span>结论:{review ? (REVIEW_CONCLUSION_LABEL[review.review_status] ?? review.review_status) : '—'}</span>
          <span>评分:{review?.reviewer_confidence != null ? review.reviewer_confidence.toFixed(2) : '—'}</span>
          {review?.promotion_status === 'promoted' && (
            review.effective_promotion_status === 'active'
              ? <span className="ew-ok">已晋升为正式证据(当前有效)</span>
              : <span className="ew-bad">曾晋升，现已撤销</span>
          )}
        </div>
        <p className="ew-rollback-impact">
          {review?.promotion_status === 'promoted' && review.effective_promotion_status === 'active'
            ? '回退后将撤销当前生效的正式证据,对象重新进入待验证流程,可重新评分。'
            : '回退后对象将重新进入待验证流程,可重新评分;原审核结论与评分保留为历史。'}
        </p>
        <label className="ew-field">
          回退原因(必填)
          <textarea
            className="filter-input"
            rows={3}
            value={reason}
            placeholder="说明为什么要重新评分"
            data-testid="rollback-reason-input"
            onChange={e => setReason(e.target.value)}
          />
        </label>
        {reasonTouched && reasonEmpty && (
          <div className="ew-bad" data-testid="rollback-reason-error">请填写回退原因</div>
        )}
        {error && <div className="ew-bad" data-testid="rollback-submit-error">{error}</div>}
      </div>
    </ConfirmDialog>
  )
}
