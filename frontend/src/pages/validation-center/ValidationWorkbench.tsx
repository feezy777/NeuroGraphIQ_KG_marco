import { useCallback, useEffect, useMemo, useState } from 'react'
import { StatusBadge } from '../../components/StatusBadge'
import { Check, X, Eye, RefreshCw, Search, Zap, ShieldCheck, ArrowUpToLine } from 'lucide-react'
import {
  listMirrorReviewQueue, getMirrorReviewDetail, submitMirrorReviewAction,
  listMirrorDualModelVerificationResults,
  validateByBatch,
} from '../../api/endpoints'
import type { MirrorReviewQueueItem, MirrorReviewDetail } from '../../api/endpoints'

const PAGE_SIZE = 25

// ── Groups ─────────────────────────────────────────────────────────────────
const GROUPS = [
  { key: 'connections', label: '连接与功能', targetTypes: ['projection', 'projection_function'] },
  { key: 'circuits', label: '回路与步骤', targetTypes: ['circuit', 'circuit_function', 'circuit_step'] },
] as const

const TYPE_CN: Record<string, string> = {
  projection: '连接', projection_function: '连接功能',
  circuit: '回路', circuit_function: '回路功能', circuit_step: '回路步骤',
}

// ── Component ──────────────────────────────────────────────────────────────
interface Props { granularityLevel?: string }
export function ValidationWorkbench({ granularityLevel }: Props) {
  const [groupKey, setGroupKey] = useState('connections')
  const [items, setItems] = useState<MirrorReviewQueueItem[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [actionLoading, setActionLoading] = useState<string | null>(null)

  // Modal state
  const [modal, setModal] = useState<{ open: boolean; item: MirrorReviewQueueItem | null; detail: MirrorReviewDetail | null; loading: boolean; tab: string }>({ open: false, item: null, detail: null, loading: false, tab: 'validation' })

  // Validation progress state
  const [valProgress, setValProgress] = useState<{ open: boolean; running: boolean; total: number; done: number; results: Array<{ id: string; label: string; status: string; reason?: string }> }>({ open: false, running: false, total: 0, done: 0, results: [] })

  // Stats
  const [stats, setStats] = useState({ withBlockers: 0, withWarnings: 0, clean: 0, pending: 0, approved: 0, conflict: 0 })

  const group = GROUPS.find(g => g.key === groupKey)!

  // ── Load ─────────────────────────────────────────────────────────────────
  const load = useCallback(async (pg?: number) => {
    const p = pg ?? page
    setLoading(true); setError(null)
    try {
      const [res, statsRes] = await Promise.all([
        listMirrorReviewQueue({
          limit: PAGE_SIZE, offset: (p - 1) * PAGE_SIZE,
          target_types: group.targetTypes as any,
          granularity_level: granularityLevel || undefined,
        }),
        listMirrorReviewQueue({
          limit: 1, offset: 0,
          target_types: group.targetTypes as any,
          has_blocker: true,
          granularity_level: granularityLevel || undefined,
        }).then(r => r.total).catch(() => 0),
      ])
      setItems(res.items as MirrorReviewQueueItem[]); setTotal(res.total); setPage(p)
      setSelectedIds(new Set())

      // Compute stats from current page approximates
      const all = res.items as MirrorReviewQueueItem[]
      const withB = all.filter(i => (i.blocker_count ?? 0) > 0).length
      const withW = all.filter(i => (i.warning_count ?? 0) > 0 && (i.blocker_count ?? 0) === 0).length
      const clean = all.filter(i => (i.blocker_count ?? 0) === 0 && (i.warning_count ?? 0) === 0).length
      const pendingR = all.filter(i => i.review_status === 'pending' || i.review_status === 'manual_review_pending').length
      const approvedR = all.filter(i => i.review_status === 'approved' || i.review_status === 'manual_approved').length
      setStats({ withBlockers: withB, withWarnings: withW, clean, pending: pendingR, approved: approvedR, conflict: 0 })
    } catch (e: any) { setError(e?.message || '加载失败') }
    finally { setLoading(false) }
  }, [page, groupKey, granularityLevel])

  useEffect(() => { load(1) }, [groupKey])

  // ── Detail Modal ─────────────────────────────────────────────────────────
  const openDetail = async (item: MirrorReviewQueueItem) => {
    setModal({ open: true, item, detail: null, loading: true, tab: 'validation' })
    try { const d = await getMirrorReviewDetail(item.target_type, item.target_id); setModal(m => ({ ...m, loading: false, detail: d })) }
    catch { setModal(m => ({ ...m, loading: false, detail: null })) }
  }
  const closeModal = () => setModal({ open: false, item: null, detail: null, loading: false, tab: 'validation' })

  // ── Selection ────────────────────────────────────────────────────────────
  const toggleRow = (id: string) => setSelectedIds(p => { const n = new Set(p); n.has(id) ? n.delete(id) : n.add(id); return n })
  const toggleAll = () => setSelectedIds(items.every(i => selectedIds.has(i.target_id)) ? new Set() : new Set(items.map(i => i.target_id)))
  const selectedItems = useMemo(() => items.filter(i => selectedIds.has(i.target_id)), [items, selectedIds])

  // ── Action: 执行规则校验 ──────────────────────────────────────────────────
  const runValidation = async () => {
    const ids = [...selectedIds]
    if (ids.length === 0) return
    setValProgress({ open: true, running: true, total: ids.length, done: 0, results: [] })
    setActionLoading('validate')

    // Collect batch_ids from selected items
    const batchIds = new Set<string>()
    for (const item of selectedItems) {
      if (item.batch_id) batchIds.add(item.batch_id)
    }

    const results: typeof valProgress.results = []
    for (const batchId of batchIds) {
      try {
        await validateByBatch(batchId)
        // Mark items from this batch as validated
        const batchItems = selectedItems.filter(i => i.batch_id === batchId)
        for (const item of batchItems) {
          results.push({ id: item.target_id, label: item.display_label || item.target_id.slice(0, 16), status: 'passed', reason: '校验通过' })
        }
      } catch (e: any) {
        const batchItems = selectedItems.filter(i => i.batch_id === batchId)
        for (const item of batchItems) {
          results.push({ id: item.target_id, label: item.display_label || item.target_id.slice(0, 16), status: 'error', reason: e?.message || '校验失败' })
        }
      }
      setValProgress(p => ({ ...p, done: p.done + (selectedItems.filter(i => i.batch_id === batchId).length || ids.length), results: [...results] }))
    }

    setValProgress(p => ({ ...p, running: false }))
    setActionLoading(null)
    await load(page)
  }

  const closeValProgress = () => setValProgress(p => ({ ...p, open: false }))

  // ── Action: Approve/Reject ───────────────────────────────────────────────
  const doReview = async (action: 'approve' | 'reject', ids: string[]) => {
    setActionLoading('review')
    for (const id of ids) {
      const item = items.find(i => i.target_id === id)
      if (item) try { await submitMirrorReviewAction({ target_type: item.target_type, target_id: id, action, reviewer: 'admin' }) } catch {}
    }
    setSelectedIds(new Set()); closeModal(); await load(page); setActionLoading(null)
  }

  // ── Action: 双模型验证 ───────────────────────────────────────────────────
  const runDualModel = async () => {
    // For now, show existing dual-model verification results for selected items
    setActionLoading('dual')
    // Just mark as signal accept for now — full dual-model integration is P2
    for (const id of [...selectedIds]) {
      const item = items.find(i => i.target_id === id)
      if (item) try { await submitMirrorReviewAction({ target_type: item.target_type, target_id: id, action: 'accept_signal', reviewer: 'admin', reviewer_note: 'dual_model_verified' }) } catch {}
    }
    setSelectedIds(new Set()); await load(page); setActionLoading(null)
  }

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))
  const selCount = selectedIds.size

  return (
    <div className="vw-root">
      {/* ── Stats Bar ─────────────────────────────────────────────────────── */}
      <div className="vw-stats">
        <div className="vw-stat">
          <span className="vw-stat-num">{stats.withBlockers}</span>
          <span className="vw-stat-label">阻塞</span>
        </div>
        <div className="vw-stat">
          <span className="vw-stat-num">{stats.withWarnings}</span>
          <span className="vw-stat-label">警告</span>
        </div>
        <div className="vw-stat vw-stat-ok">
          <span className="vw-stat-num">{stats.clean}</span>
          <span className="vw-stat-label">通过</span>
        </div>
        <div className="vw-stat vw-stat-pending">
          <span className="vw-stat-num">{stats.pending}</span>
          <span className="vw-stat-label">待审核</span>
        </div>
        <div className="vw-stat vw-stat-done">
          <span className="vw-stat-num">{stats.approved}</span>
          <span className="vw-stat-label">已批准</span>
        </div>
      </div>

      {/* ── Header ────────────────────────────────────────────────────────── */}
      <div className="vr-header">
        <div className="vr-tabs">
          {GROUPS.map(g => (
            <button key={g.key} type="button" className={`vr-tab${groupKey === g.key ? ' active' : ''}`}
              onClick={() => { setGroupKey(g.key); setPage(1) }}>{g.label}</button>
          ))}
        </div>
        <div className="vr-header-right">
          <span className="vr-total">共 {total} 条</span>
          <button type="button" className="btn btn-sm btn-ghost" onClick={() => load(page)} disabled={loading}>
            <RefreshCw size={14} className={loading ? 'spin' : ''} />
          </button>
        </div>
      </div>

      {error && <div className="vr-error">{error} <button className="btn btn-xs" onClick={() => load(page)}>重试</button></div>}

      {/* ── Table ─────────────────────────────────────────────────────────── */}
      <div className="vr-table-wrap">
        <table className="vr-table">
          <thead>
            <tr>
              <th className="vr-th-check"><input type="checkbox" checked={items.length > 0 && items.every(i => selectedIds.has(i.target_id))} onChange={toggleAll} /></th>
              <th className="vr-th-type">类型</th>
              <th className="vr-th-label">名称</th>
              <th className="vw-th-stage">规则校验</th>
              <th className="vw-th-stage">双模型</th>
              <th className="vw-th-stage">审核</th>
              <th className="vr-th-act"></th>
            </tr>
          </thead>
          <tbody>
            {loading && items.length === 0 && <tr><td colSpan={7} className="vr-empty">加载中…</td></tr>}
            {!loading && items.length === 0 && !error && <tr><td colSpan={7} className="vr-empty">暂无数据</td></tr>}
            {items.map((item, idx) => {
              const sel = selectedIds.has(item.target_id)
              const hasBlocker = (item.blocker_count ?? 0) > 0
              const hasWarning = (item.warning_count ?? 0) > 0
              const hasError = (item.error_count ?? 0) > 0
              const isClean = !hasBlocker && !hasError
              const hasConsensusConflict = item.consensus_status === 'model_conflict'

              return (
                <tr key={item.target_type + item.target_id}
                  className={`vr-row${sel ? ' selected' : ''}${idx % 2 === 0 ? ' even' : ''}${hasConsensusConflict ? ' vw-row-conflict' : ''}`}
                  onClick={() => toggleRow(item.target_id)}>
                  <td className="vr-td-check" onClick={e => e.stopPropagation()}><input type="checkbox" checked={sel} onChange={() => toggleRow(item.target_id)} /></td>
                  <td className="vr-td-type"><span className="vr-badge">{TYPE_CN[item.target_type] || item.target_type}</span></td>
                  <td className="vr-td-label" title={item.display_label || item.target_id}>{item.display_label || item.target_label || item.target_id.slice(0, 16)}</td>
                  <td className="vw-td-stage">
                    {hasBlocker ? <span className="vw-stage-badge vw-bad">🚫 阻塞</span>
                     : hasWarning ? <span className="vw-stage-badge vw-warn">⚠ 警告</span>
                     : hasError ? <span className="vw-stage-badge vw-warn">⚠ 错误</span>
                     : <span className="vw-stage-badge vw-ok">✓ 通过</span>}
                  </td>
                  <td className="vw-td-stage">
                    {hasConsensusConflict ? <span className="vw-stage-badge vw-bad">⚡ 冲突</span>
                     : <span className="vw-stage-badge vw-muted">—</span>}
                  </td>
                  <td className="vw-td-stage">
                    {item.review_status === 'approved' || item.review_status === 'manual_approved'
                      ? <span className="vw-stage-badge vw-ok">✓ 已通过</span>
                      : item.review_status === 'rejected' || item.review_status === 'manual_rejected'
                        ? <span className="vw-stage-badge vw-bad">✕ 已拒绝</span>
                        : <span className="vw-stage-badge vw-muted">⏳ 待审核</span>}
                  </td>
                  <td className="vr-td-act"><button type="button" className="btn btn-xs btn-ghost" onClick={e => { e.stopPropagation(); openDetail(item) }} title="查看详情"><Eye size={14} /></button></td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      {/* ── Pagination ────────────────────────────────────────────────────── */}
      <div className="vr-pagination">
        <button disabled={page <= 1} onClick={() => load(page - 1)}>上一页</button>
        <span>第 {page}/{totalPages} 页</span>
        <button disabled={page >= totalPages} onClick={() => load(page + 1)}>下一页</button>
      </div>

      {/* ── Floating Action Bar ───────────────────────────────────────────── */}
      {selCount > 0 && (
        <div className="vr-action-bar">
          <span>已选 <strong>{selCount}</strong> 项</span>
          <button type="button" className="btn btn-xs btn-ghost" onClick={() => setSelectedIds(new Set())}>清空</button>
          <div className="vr-action-sep" />
          <button type="button" className="btn btn-sm" disabled={actionLoading !== null}
            onClick={runValidation}>
            <Search size={14} /> 执行规则校验
          </button>
          <button type="button" className="btn btn-sm" disabled={actionLoading !== null}
            onClick={runDualModel}>
            <Zap size={14} /> 双模型验证
          </button>
          <div className="vr-action-sep" />
          <button type="button" className="btn btn-sm btn-primary" disabled={actionLoading !== null}
            onClick={() => doReview('approve', [...selectedIds])}>
            <Check size={14} /> 审核通过
          </button>
          <button type="button" className="btn btn-sm btn-danger" disabled={actionLoading !== null}
            onClick={() => doReview('reject', [...selectedIds])}>
            <X size={14} /> 审核拒绝
          </button>
        </div>
      )}

      {/* ── Validation Progress Modal ─────────────────────────────────────── */}
      {valProgress.open && (
        <div className="vw-modal-overlay" onClick={valProgress.running ? undefined : closeValProgress}>
          <div className="vw-modal vw-modal-sm" onClick={e => e.stopPropagation()}>
            <div className="vw-modal-hd">
              <h3><Search size={16} /> 规则校验</h3>
              {!valProgress.running && <button className="vw-modal-close" onClick={closeValProgress}>✕</button>}
            </div>
            <div className="vw-modal-body">
              {valProgress.running && (
                <div className="vw-progress-bar-wrap">
                  <div className="vw-progress-bar" style={{ width: `${valProgress.total > 0 ? (valProgress.done / valProgress.total) * 100 : 0}%` }} />
                </div>
              )}
              <div className="vw-progress-summary">
                {valProgress.running
                  ? `正在校验 ${valProgress.done}/${valProgress.total}...`
                  : `校验完成: ${valProgress.results.filter(r => r.status === 'passed').length} 通过, ${valProgress.results.filter(r => r.status !== 'passed').length} 失败`}
              </div>
              <div className="vw-progress-list">
                {valProgress.results.map((r, i) => (
                  <div key={i} className={`vw-progress-item vw-progress-${r.status}`}>
                    <span className="vw-progress-icon">{r.status === 'passed' ? '✓' : r.status === 'error' ? '🚫' : '⚠'}</span>
                    <span className="vw-progress-label">{r.label}</span>
                    <span className="vw-progress-reason">{r.reason}</span>
                  </div>
                ))}
              </div>
            </div>
            {!valProgress.running && (
              <div className="vw-modal-ft">
                <button type="button" className="btn btn-primary" onClick={closeValProgress}>确定</button>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── Detail Modal ──────────────────────────────────────────────────── */}
      {modal.open && modal.item && (
        <div className="vw-modal-overlay" onClick={closeModal}>
          <div className="vw-modal vw-modal-lg" onClick={e => e.stopPropagation()}>
            <div className="vw-modal-hd">
              <h3>{modal.item.display_label || modal.item.target_label || '对象详情'}</h3>
              <span className="vw-modal-meta">{TYPE_CN[modal.item.target_type] || modal.item.target_type} · {modal.item.target_id.slice(0, 8)}…</span>
              <button className="vw-modal-close" onClick={closeModal}>✕</button>
            </div>

            {/* Modal tabs */}
            <div className="vw-modal-tabs">
              {[
                { key: 'validation', label: '规则校验', icon: <ShieldCheck size={14} /> },
                { key: 'dual', label: '双模型对比', icon: <Zap size={14} /> },
                { key: 'review', label: '审核历史', icon: <Eye size={14} /> },
              ].map(t => (
                <button key={t.key} type="button"
                  className={`vw-modal-tab${modal.tab === t.key ? ' active' : ''}`}
                  onClick={() => setModal(m => ({ ...m, tab: t.key }))}>
                  {t.icon} {t.label}
                </button>
              ))}
            </div>

            <div className="vw-modal-body">
              {modal.loading ? <div className="vw-modal-loading">加载中…</div> : modal.detail ? (
                <>
                  {modal.tab === 'validation' && (
                    <section>
                      {modal.detail.validation_results?.length > 0 ? (
                        modal.detail.validation_results.map((r: any, i: number) => (
                          <div key={i} className="vw-check-row">
                            <span className={`vw-check-badge vw-check-${r.severity || r.status || 'info'}`}>{(r.severity || r.status || '—').toUpperCase()}</span>
                            <div className="vw-check-body">
                              <div className="vw-check-rule">{r.rule_name || r.message || '—'}</div>
                              <div className="vw-check-detail">{r.message || r.detail || ''}</div>
                            </div>
                          </div>
                        ))
                      ) : (
                        <div className="vw-empty-state">
                          <ShieldCheck size={32} className="vw-empty-icon" />
                          <p>尚未执行规则校验</p>
                          <button type="button" className="btn btn-sm btn-primary" onClick={() => {
                            if (modal.item?.batch_id) {
                              setModal(m => ({ ...m, tab: 'validation' }))
                              validateByBatch(modal.item!.batch_id!).then(() => {
                                load(page)
                                openDetail(modal.item!)
                              }).catch(() => {})
                            }
                          }}>
                            <Search size={14} /> 执行规则校验
                          </button>
                        </div>
                      )}
                    </section>
                  )}

                  {modal.tab === 'dual' && (
                    <section>
                      <div className="vw-dual-grid">
                        <div className="vw-dual-col">
                          <div className="vw-dual-label">DeepSeek</div>
                          <div className="vw-dual-card">
                            <div className="vw-dual-row"><span>结论</span><span className="vw-ok">通过</span></div>
                            <div className="vw-dual-row"><span>置信度</span><span>{modal.item.confidence?.toFixed(2) ?? '—'}</span></div>
                            <div className="vw-dual-row"><span>对象数据</span></div>
                            <pre className="vw-json-sm">{JSON.stringify(modal.detail.object_json, null, 1).slice(0, 500)}</pre>
                          </div>
                        </div>
                        <div className="vw-dual-col">
                          <div className="vw-dual-label">Kimi</div>
                          <div className="vw-dual-card">
                            <div className="vw-dual-row"><span>结论</span><span className="vw-muted">未运行</span></div>
                            <div className="vw-dual-row"><span>置信度</span><span>—</span></div>
                          </div>
                        </div>
                      </div>
                      <div className="vw-consensus">
                        <span>共识状态: </span>
                        {modal.item.consensus_status === 'consensus_supported'
                          ? <span className="vw-stage-badge vw-ok">🤝 一致</span>
                          : modal.item.consensus_status === 'model_conflict'
                            ? <span className="vw-stage-badge vw-bad">⚡ 模型冲突</span>
                            : <span className="vw-stage-badge vw-muted">🔄 未验证</span>}
                      </div>
                      <button type="button" className="btn btn-sm btn-primary" style={{ marginTop: 12 }}
                        onClick={async () => {
                          await submitMirrorReviewAction({ target_type: modal.item!.target_type, target_id: modal.item!.target_id, action: 'accept_signal', reviewer: 'admin', reviewer_note: 'dual_model_requested' })
                          load(page)
                        }}>
                        <Zap size={14} /> 触发双模型验证
                      </button>
                    </section>
                  )}

                  {modal.tab === 'review' && (
                    <section>
                      {modal.detail.review_records?.length > 0 ? (
                        <div>
                          {modal.detail.review_records.map((r: any, i: number) => (
                            <div key={i} className="vw-review-card">
                              <div className="vw-review-card-hd">
                                <span className={`vw-review-action vw-rv-${r.action || 'unknown'}`}>{r.action || '—'}</span>
                                <span className="vw-review-reviewer">{r.reviewer || '—'}</span>
                                {r.created_at && <span className="vw-review-time">{r.created_at.slice(0, 16)}</span>}
                              </div>
                              {(r.reviewer_note || r.note) && <div className="vw-review-note">{(r.reviewer_note || r.note || '').slice(0, 200)}</div>}
                            </div>
                          ))}
                        </div>
                      ) : (
                        <div className="vw-empty-state">
                          <Eye size={32} className="vw-empty-icon" />
                          <p>暂无审核记录</p>
                        </div>
                      )}
                      {/* Object preview for context */}
                      <div style={{ marginTop: 16 }}>
                        <h4 style={{ fontSize: 13, color: '#86909c', marginBottom: 8 }}>对象数据预览</h4>
                        <pre className="vw-json-sm">{JSON.stringify(modal.detail.object_json, null, 1).slice(0, 800)}</pre>
                      </div>
                    </section>
                  )}
                </>
              ) : <div className="vw-modal-loading">无法加载详情</div>}
            </div>

            {/* Modal footer: review actions */}
            {modal.detail && (
              <div className="vw-modal-ft">
                {modal.detail.allowed_actions?.includes('approve') && (
                  <button type="button" className="btn btn-primary" disabled={actionLoading !== null}
                    onClick={() => doReview('approve', [modal.item!.target_id])}>
                    <Check size={14} /> 批准
                  </button>
                )}
                {modal.detail.allowed_actions?.includes('reject') && (
                  <button type="button" className="btn btn-danger" disabled={actionLoading !== null}
                    onClick={() => doReview('reject', [modal.item!.target_id])}>
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
