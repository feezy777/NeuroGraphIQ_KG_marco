import { useState } from 'react'
import { useI18n } from '../../../i18n-context'

interface Props {
  open: boolean
  title: string
  targetType: string
  targetId: string | null
  loading: boolean
  objectJson: Record<string, unknown> | null
  evidenceRecords: Record<string, unknown>[]
  validationResults?: Record<string, unknown>[]
  reviewRecords?: Record<string, unknown>[]
  relatedObjects?: Record<string, unknown>
  allowedActions: string[]
  gatingReasons?: string[]
  onClose: () => void
  onAction: (action: string, note?: string) => Promise<void>
}

export function ValidationObjectDrawer({
  open, title, targetType, targetId, loading,
  objectJson, evidenceRecords, validationResults,
  reviewRecords, relatedObjects,
  allowedActions, gatingReasons, onClose, onAction,
}: Props) {
  const { t } = useI18n()
  const [actionLoading, setActionLoading] = useState<string | null>(null)
  const [note, setNote] = useState('')

  if (!open) return null

  const handleAction = async (action: string) => {
    setActionLoading(action)
    try {
      await onAction(action, note || undefined)
      setNote('')
    } finally {
      setActionLoading(null)
    }
  }

  const canApprove = allowedActions.includes('approve')
  const canReject = allowedActions.includes('reject')

  return (
    <div className="validation-drawer-overlay" onClick={onClose}>
      <div className="validation-drawer" onClick={e => e.stopPropagation()}>
        <div className="validation-drawer-header">
          <h3>{title}</h3>
          <span className="validation-drawer-meta">
            {targetType} · {targetId?.slice(0, 8)}…
          </span>
          <button type="button" className="btn-close" onClick={onClose}>✕</button>
        </div>

        <div className="validation-drawer-body">
          {loading ? (
            <div className="loading">{t('common.loading')}</div>
          ) : (
            <>
              <section className="validation-drawer-section">
                <h4>对象数据</h4>
                <pre className="validation-json">{JSON.stringify(objectJson, null, 2)}</pre>
              </section>

              {evidenceRecords.length > 0 && (
                <section className="validation-drawer-section">
                  <h4>证据记录 ({evidenceRecords.length})</h4>
                  <pre className="validation-json">{JSON.stringify(evidenceRecords, null, 2)}</pre>
                </section>
              )}

              {validationResults && validationResults.length > 0 && (
                <section className="validation-drawer-section">
                  <h4>校验结果 ({validationResults.length})</h4>
                  {validationResults.map((r: Record<string, unknown>, i: number) => (
                    <div key={i} className="validation-result-item">
                      <span className={`badge badge-${r.status || 'info'}`}>{String(r.status || '-')}</span>
                      <span>{String(r.message || '')}</span>
                    </div>
                  ))}
                </section>
              )}

              {reviewRecords && reviewRecords.length > 0 && (
                <section className="validation-drawer-section">
                  <h4>审核记录 ({reviewRecords.length})</h4>
                  {reviewRecords.map((r: Record<string, unknown>, i: number) => (
                    <div key={i} className="validation-review-record">
                      <span className="text-muted">{String(r.action || '')}</span>
                      <span>{String(r.reviewer || '')}</span>
                      <span className="text-xs">{String(r.reviewer_note || r.note || '')}</span>
                    </div>
                  ))}
                </section>
              )}

              {gatingReasons && gatingReasons.length > 0 && (
                <section className="validation-drawer-section">
                  <h4>限制原因</h4>
                  <ul className="validation-gating-list">
                    {gatingReasons.map((r, i) => <li key={i}>{r}</li>)}
                  </ul>
                </section>
              )}
            </>
          )}
        </div>

        <div className="validation-drawer-footer">
          <textarea
            className="input"
            placeholder="审核备注（可选）…"
            value={note}
            onChange={e => setNote(e.target.value)}
            rows={2}
          />
          <div className="validation-drawer-actions">
            {canApprove && (
              <button type="button" className="btn btn-primary"
                disabled={actionLoading !== null}
                onClick={() => handleAction('approve')}>
                {actionLoading === 'approve' ? '…' : '✓ 批准'}
              </button>
            )}
            {canReject && (
              <button type="button" className="btn btn-danger"
                disabled={actionLoading !== null}
                onClick={() => handleAction('reject')}>
                {actionLoading === 'reject' ? '…' : '✕ 拒绝'}
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
