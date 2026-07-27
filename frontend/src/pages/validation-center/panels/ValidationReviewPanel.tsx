import { useCallback, useEffect, useState } from 'react'
import { useI18n } from '../../../i18n-context'
import { StatusBadge } from '../../../components/StatusBadge'
import {
  listMirrorReviewQueue,
  getMirrorReviewDetail,
  submitMirrorReviewAction,
} from '../../../api/endpoints'
import type { MirrorReviewQueueItem, MirrorReviewDetail } from '../../../api/endpoints'
import { Check, X, Eye, RefreshCw } from 'lucide-react'

const PAGE_SIZE = 25

// ── Group definitions ──────────────────────────────────────────────────────
const GROUPS = [
  {
    key: 'connections',
    label: '连接与功能',
    targetTypes: ['projection', 'projection_function'],
  },
  {
    key: 'circuits',
    label: '回路与步骤',
    targetTypes: ['circuit', 'circuit_function', 'circuit_step'],
  },
] as const

const TYPE_CN: Record<string, string> = {
  projection: '连接', projection_function: '连接功能',
  circuit: '回路', circuit_function: '回路功能', circuit_step: '回路步骤',
}

// ── Component ──────────────────────────────────────────────────────────────
interface Props { granularityLevel?: string }
export function ValidationReviewPanel({ granularityLevel }: Props) {
  const { t } = useI18n()
  const [groupKey, setGroupKey] = useState('connections')
  const [items, setItems] = useState<MirrorReviewQueueItem[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Selection
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [actionLoading, setActionLoading] = useState(false)

  // Modal
  const [modal, setModal] = useState<{ open: boolean; loading: boolean; item: MirrorReviewQueueItem | null; detail: MirrorReviewDetail | null }>({
    open: false, loading: false, item: null, detail: null,
  })

  const group = GROUPS.find(g => g.key === groupKey)!

  // ── Load queue ──────────────────────────────────────────────────────────
  const load = useCallback(async (pg?: number) => {
    const p = pg ?? page
    setLoading(true); setError(null)
    try {
      const res = await listMirrorReviewQueue({
        limit: PAGE_SIZE,
        offset: (p - 1) * PAGE_SIZE,
        target_types: group.targetTypes as any,
        review_status: ['pending', 'manual_review_pending'],
        granularity_level: granularityLevel || undefined,
      })
      setItems(res.items as MirrorReviewQueueItem[])
      setTotal(res.total)
      setPage(p)
      setSelectedIds(new Set())
    } catch (e: any) { setError(e?.message || '加载失败') }
    finally { setLoading(false) }
  }, [page, groupKey, granularityLevel])

  useEffect(() => { load(1) }, [groupKey])

  // ── Open detail modal ───────────────────────────────────────────────────
  const openDetail = useCallback(async (item: MirrorReviewQueueItem) => {
    setModal({ open: true, loading: true, item, detail: null })
    try {
      const detail = await getMirrorReviewDetail(item.target_type, item.target_id)
      setModal(d => ({ ...d, loading: false, detail }))
    } catch {
      setModal(d => ({ ...d, loading: false, detail: null }))
    }
  }, [])

  const closeModal = () => setModal({ open: false, loading: false, item: null, detail: null })

  // ── Submit action (single & batch) ──────────────────────────────────────
  const doAction = useCallback(async (action: 'approve' | 'reject', ids: string[]) => {
    setActionLoading(true)
    for (const id of ids) {
      const item = items.find(i => i.target_id === id)
      if (!item) continue
      try {
        await submitMirrorReviewAction({ target_type: item.target_type, target_id: id, action, reviewer: 'admin' })
      } catch { /* continue */ }
    }
    setSelectedIds(new Set())
    closeModal()
    await load(page)
    setActionLoading(false)
  }, [items, load, page])

  // ── Selection ───────────────────────────────────────────────────────────
  const toggleRow = (id: string) => setSelectedIds(prev => {
    const next = new Set(prev); next.has(id) ? next.delete(id) : next.add(id); return next
  })
  const toggleAll = () => {
    if (items.every(i => selectedIds.has(i.target_id))) {
      setSelectedIds(new Set())
    } else {
      setSelectedIds(new Set(items.map(i => i.target_id)))
    }
  }
  const clearSelection = () => setSelectedIds(new Set())

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))

  return (
    <div className="vr-panel">
      {/* Header */}
      <div className="vr-header">
        <div className="vr-tabs">
          {GROUPS.map(g => (
            <button key={g.key} type="button"
              className={`vr-tab${groupKey === g.key ? ' active' : ''}`}
              onClick={() => { setGroupKey(g.key); setPage(1) }}
            >
              {g.label}
            </button>
          ))}
        </div>
        <div className="vr-header-right">
          <span className="vr-total">共 {total} 条</span>
          <button type="button" className="btn btn-sm btn-ghost" onClick={() => load(page)} disabled={loading}>
            <RefreshCw size={14} className={loading ? 'spin' : ''} />
          </button>
        </div>
      </div>

      {/* Error */}
      {error && <div className="vr-error">{error} <button className="btn btn-xs" onClick={() => load(page)}>重试</button></div>}

      {/* Table */}
      <div className="vr-table-wrap">
        <table className="vr-table">
          <thead>
            <tr>
              <th className="vr-th-check">
                <input type="checkbox" checked={items.length > 0 && items.every(i => selectedIds.has(i.target_id))}
                  onChange={toggleAll} />
              </th>
              <th className="vr-th-type">类型</th>
              <th className="vr-th-label">名称</th>
              <th className="vr-th-status">审核状态</th>
              <th className="vr-th-conf">置信度</th>
              <th className="vr-th-issues">问题</th>
              <th className="vr-th-act"></th>
            </tr>
          </thead>
          <tbody>
            {loading && items.length === 0 && (
              <tr><td colSpan={7} className="vr-empty">加载中…</td></tr>
            )}
            {!loading && items.length === 0 && !error && (
              <tr><td colSpan={7} className="vr-empty">暂无待审核数据</td></tr>
            )}
            {items.map((item, idx) => {
              const sel = selectedIds.has(item.target_id)
              return (
                <tr key={`${item.target_type}:${item.target_id}`}
                  className={`vr-row${sel ? ' selected' : ''}${idx % 2 === 0 ? ' even' : ''}`}
                  onClick={() => toggleRow(item.target_id)}
                >
                  <td className="vr-td-check" onClick={e => e.stopPropagation()}>
                    <input type="checkbox" checked={sel} onChange={() => toggleRow(item.target_id)} />
                  </td>
                  <td className="vr-td-type">
                    <span className="vr-badge">{TYPE_CN[item.target_type] || item.target_type}</span>
                  </td>
                  <td className="vr-td-label" title={item.display_label || item.target_id}>
                    {item.display_label || item.target_label || item.target_id.slice(0, 16)}
                  </td>
                  <td className="vr-td-status">
                    <StatusBadge status={item.review_status} />
                  </td>
                  <td className="vr-td-conf">
                    {item.confidence != null ? item.confidence.toFixed(2) : '—'}
                  </td>
                  <td className="vr-td-issues">
                    {item.blocker_count ? <span className="vr-issue b">B:{item.blocker_count}</span> : null}
                    {item.error_count ? <span className="vr-issue e">E:{item.error_count}</span> : null}
                    {item.warning_count ? <span className="vr-issue w">W:{item.warning_count}</span> : null}
                    {!item.blocker_count && !item.error_count && !item.warning_count && (
                      <span className="vr-clean">✓</span>
                    )}
                  </td>
                  <td className="vr-td-act">
                    <button type="button" className="btn btn-xs btn-ghost"
                      onClick={e => { e.stopPropagation(); openDetail(item) }}
                      title="查看详情"
                    >
                      <Eye size={14} />
                    </button>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      <div className="vr-pagination">
        <button disabled={page <= 1} onClick={() => load(page - 1)}>上一页</button>
        <span>第 {page}/{totalPages} 页</span>
        <button disabled={page >= totalPages} onClick={() => load(page + 1)}>下一页</button>
      </div>

      {/* Action Bar */}
      {selectedIds.size > 0 && (
        <div className="vr-action-bar">
          <span>已选 <strong>{selectedIds.size}</strong> 项</span>
          <button type="button" className="btn btn-xs btn-ghost" onClick={clearSelection}>清空</button>
          <div className="vr-action-sep" />
          <button type="button" className="btn btn-sm btn-primary"
            disabled={actionLoading}
            onClick={() => doAction('approve', [...selectedIds])}
          >
            <Check size={14} /> 批量批准
          </button>
          <button type="button" className="btn btn-sm btn-danger"
            disabled={actionLoading}
            onClick={() => doAction('reject', [...selectedIds])}
          >
            <X size={14} /> 批量拒绝
          </button>
        </div>
      )}

      {/* ── Detail Modal ─────────────────────────────────────────────────── */}
      {modal.open && (
        <div className="vr-modal-overlay" onClick={closeModal}>
          <div className="vr-modal" onClick={e => e.stopPropagation()}>
            <div className="vr-modal-hd">
              <h3>{modal.item?.display_label || modal.item?.target_label || '对象详情'}</h3>
              <span className="vr-modal-meta">
                {TYPE_CN[modal.item?.target_type || ''] || modal.item?.target_type}
                {' · '}{modal.item?.target_id?.slice(0, 8)}…
              </span>
              <button className="vr-modal-close" onClick={closeModal}>✕</button>
            </div>

            <div className="vr-modal-body">
              {modal.loading ? (
                <div className="vr-modal-loading">加载中…</div>
              ) : modal.detail ? (
                <>
                  {/* Object data */}
                  <section className="vr-section">
                    <h4>对象数据</h4>
                    <pre className="vr-json">{JSON.stringify(modal.detail.object_json, null, 2)}</pre>
                  </section>

                  {/* Evidence */}
                  {modal.detail.evidence_records?.length > 0 && (
                    <section className="vr-section">
                      <h4>证据记录 ({modal.detail.evidence_records.length})</h4>
                      <div className="vr-evidence-list">
                        {modal.detail.evidence_records.map((ev: any, i: number) => (
                          <div key={i} className="vr-evidence-item">
                            <span className="vr-evidence-type">{ev.evidence_type || ev.type || '—'}</span>
                            <span className="vr-evidence-text">{(ev.evidence_text || ev.text || '').slice(0, 200)}</span>
                          </div>
                        ))}
                      </div>
                    </section>
                  )}

                  {/* Validation */}
                  {modal.detail.validation_results?.length > 0 && (
                    <section className="vr-section">
                      <h4>校验结果 ({modal.detail.validation_results.length})</h4>
                      {modal.detail.validation_results.map((r: any, i: number) => (
                        <div key={i} className="vr-result-row">
                          <span className={`vr-result-badge vr-result-${r.severity || r.status || 'info'}`}>
                            {r.severity || r.status || '—'}
                          </span>
                          <span>{r.message || r.rule_name || ''}</span>
                        </div>
                      ))}
                    </section>
                  )}

                  {/* Review history */}
                  {modal.detail.review_records?.length > 0 && (
                    <section className="vr-section">
                      <h4>审核历史 ({modal.detail.review_records.length})</h4>
                      {modal.detail.review_records.map((r: any, i: number) => (
                        <div key={i} className="vr-history-row">
                          <span className={`vr-history-action vr-action-${r.action || 'unknown'}`}>{r.action || '—'}</span>
                          <span className="vr-history-reviewer">{r.reviewer || '—'}</span>
                          <span className="vr-history-note">{(r.reviewer_note || r.note || '').slice(0, 100)}</span>
                          {r.created_at && <span className="vr-history-time">{r.created_at.slice(0, 16)}</span>}
                        </div>
                      ))}
                    </section>
                  )}

                  {/* Related objects */}
                  {modal.detail.related_objects && Object.keys(modal.detail.related_objects).length > 0 && (
                    <section className="vr-section">
                      <h4>关联对象</h4>
                      <pre className="vr-json">{JSON.stringify(modal.detail.related_objects, null, 2)}</pre>
                    </section>
                  )}
                </>
              ) : (
                <div className="vr-modal-error">无法加载详情</div>
              )}
            </div>

            {/* Modal footer actions */}
            {modal.detail && (
              <div className="vr-modal-ft">
                {modal.detail.allowed_actions.includes('approve') && (
                  <button type="button" className="btn btn-primary"
                    disabled={actionLoading}
                    onClick={() => doAction('approve', [modal.item!.target_id])}
                  >
                    <Check size={14} /> 批准
                  </button>
                )}
                {modal.detail.allowed_actions.includes('reject') && (
                  <button type="button" className="btn btn-danger"
                    disabled={actionLoading}
                    onClick={() => doAction('reject', [modal.item!.target_id])}
                  >
                    <X size={14} /> 拒绝
                  </button>
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
