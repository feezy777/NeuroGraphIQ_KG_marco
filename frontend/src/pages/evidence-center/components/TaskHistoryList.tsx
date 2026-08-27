import { useCallback, useEffect, useState } from 'react'
import {
  listEvidenceTaskHistory,
  rollbackReviewForRescore,
  type EvidenceHistoryItem,
} from '../../../api/endpoints'
import { ConfirmDialog } from '../../../components/ConfirmDialog'

/** 回退原因枚举(PRD: Evidence insufficient / Wrong judgement / New contradictory evidence / Ontology update / Other) */
const ROLLBACK_REASONS = [
  'Evidence insufficient',
  'Wrong judgement',
  'New contradictory evidence',
  'Ontology update',
  'Other',
]

const PROMOTION_LABEL: Record<string, string> = {
  promoted: '已晋升 Final KG',
  awaiting_promotion: '待晋升',
  not_promoted: '未晋升',
}

/** 终态任务 → 展示状态(最终状态/Final KG 状态) */
function finalState(item: EvidenceHistoryItem): string {
  const rb = item.review_brief
  if (!rb) return item.status
  if (rb.has_superseded || (rb.review_status === 'approved' && rb.review_count > 1 && rb.promotion_status === 'awaiting_promotion')) {
    return '已回退'
  }
  if (rb.review_status === 'rejected') return '已拒绝'
  if (rb.promotion_status === 'promoted') return '已晋升'
  if (rb.review_status === 'approved') return '已审核'
  return item.status
}

function fmtTime(v: string | null | undefined): string {
  if (!v) return '—'
  try { return new Date(v).toLocaleString('zh-CN', { hour12: false }) } catch { return v }
}

/**
 * 任务中心历史视图:终态任务(已审核/已拒绝/已晋升/已回退)列表。
 * 回退复用 S7B rollback-for-rescore(保留历史,supersede 新版本,重开任务项 → 可重新审核)。
 */
export function TaskHistoryList() {
  const [items, setItems] = useState<EvidenceHistoryItem[]>([])
  const [loading, setLoading] = useState(true)
  const [rollbackTarget, setRollbackTarget] = useState<EvidenceHistoryItem | null>(null)
  const [reason, setReason] = useState<string>(ROLLBACK_REASONS[0])
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<string | null>(null)

  const refresh = useCallback(() => {
    setLoading(true)
    listEvidenceTaskHistory({ limit: 100 })
      .then(r => setItems(r.items))
      .catch(() => setItems([]))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => { refresh() }, [refresh])

  const handleRollback = async () => {
    if (!rollbackTarget?.review_brief?.latest_review_id) return
    setBusy(true)
    setMessage(null)
    try {
      await rollbackReviewForRescore(rollbackTarget.review_brief.latest_review_id, { reason })
      setMessage(`已回退:「${rollbackTarget.name ?? rollbackTarget.target_type}」重新进入人工审核流程`)
      setRollbackTarget(null)
      refresh()
    } catch (err) {
      setMessage(`回退失败：${err instanceof Error ? err.message : String(err)}`)
      setRollbackTarget(null)
    } finally {
      setBusy(false)
    }
  }

  if (loading) return <div className="evidence-task-loading">加载历史任务…</div>

  return (
    <div className="evidence-task-history" data-testid="task-history-list">
      {message && <div className="ontology-page-message">{message}</div>}
      {items.length === 0 && (
        <p className="evidence-module-hint">暂无已完成任务(审核/晋升/回退后的任务将出现在此)。</p>
      )}
      <div className="evidence-history-table">
        <table>
          <thead>
            <tr>
              <th>知识对象</th>
              <th>最终状态</th>
              <th>审核时间</th>
              <th>审核人</th>
              <th>审核次数</th>
              <th>Final KG 状态</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            {items.map(item => {
              const rb = item.review_brief
              return (
                <tr key={item.task_id} data-testid={`history-row-${item.task_id.slice(0, 8)}`}>
                  <td>
                    <b>{item.name ?? item.target_type}</b>
                    <span className="ew-meta">（{item.target_type}）</span>
                  </td>
                  <td><span className="govw-chip">{finalState(item)}</span></td>
                  <td>{fmtTime(rb?.last_reviewed_at)}</td>
                  <td>{rb?.reviewer_id ?? '—'}</td>
                  <td>{rb?.review_count ?? 0}</td>
                  <td>{rb?.promotion_status ? PROMOTION_LABEL[rb.promotion_status] ?? rb.promotion_status : '—'}</td>
                  <td>
                    <button
                      type="button"
                      className="btn btn-xs"
                      data-testid={`history-rollback-${item.task_id.slice(0, 8)}`}
                      disabled={!rb?.latest_review_id}
                      onClick={() => setRollbackTarget(item)}
                    >
                      Rollback
                    </button>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      <ConfirmDialog
        open={rollbackTarget !== null}
        title="Rollback 回退"
        message={`确认回退「${rollbackTarget?.name ?? rollbackTarget?.target_type ?? ''}」？回退后将：保留全部历史审核记录、新增一条回退记录、任务重新进入人工审核流程。(不覆盖历史状态)`}
        confirmLabel="确认回退"
        danger
        loading={busy}
        onConfirm={() => void handleRollback()}
        onCancel={() => setRollbackTarget(null)}
      >
        <label className="ew-meta" style={{ display: 'block', margin: '6px 0 4px' }}>Rollback Reason:</label>
        <select
          className="filter-input"
          style={{ width: '100%', padding: '6px 8px' }}
          value={reason}
          onChange={e => setReason(e.target.value)}
          aria-label="回退原因"
        >
          {ROLLBACK_REASONS.map(r => <option key={r} value={r}>{r}</option>)}
        </select>
      </ConfirmDialog>
    </div>
  )
}
