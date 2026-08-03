import { useState, useEffect, useCallback, useRef } from 'react'
import { RefreshCw, FileText, Zap } from 'lucide-react'
import { CircuitSelector } from './CircuitSelector'

// ── Types ──────────────────────────────────────────────────────────────────

interface DualReviewCandidate {
  id: string
  circuit_name: string
  circuit_type: string
  rule_overall_status?: string
  reviewer_a_decision?: string
  reviewer_b_decision?: string
  adjudication_status?: string
}

interface RunSummary {
  id: string
  granularity_level: string
  status: string
  rule_validation_status: string
  dual_review_status: string
  adjudication_status: string
  rule_total_count: number
  rule_passed_count: number
  rule_blocked_count: number
  dual_review_agreement_count: number
  dual_review_conflict_count: number
  created_at?: string
  started_at?: string
  completed_at?: string
}

interface Props {
  granularityLevel?: string
}

const STATUS_LABELS: Record<string, string> = {
  created: '已创建', queued: '排队中', running: '运行中',
  completed: '已完成', failed: '失败', cancelled: '已取消',
}

const RUNS_PAGE_SIZE = 20

type SubTab = 'history' | 'start'

function statusBadge(status: string): { color: string; label: string } {
  const colors: Record<string, string> = {
    created: '#86909c', queued: '#2f54eb', running: '#2f54eb',
    completed: '#52c41a', failed: '#ff4d4f', cancelled: '#86909c',
    passed: '#52c41a', blocked: '#faad14',
    pending: '#faad14', support: '#52c41a', reject: '#ff4d4f',
    conflict: '#faad14', agreement: '#52c41a',
    consensus_supported: '#52c41a', model_conflict: '#faad14',
    confidence_divergence: '#2f54eb', low_evidence: '#86909c',
  }
  const labels: Record<string, string> = {
    created: '已创建', queued: '排队中', running: '运行中',
    completed: '已完成', failed: '失败', cancelled: '已取消',
    passed: '通过', blocked: '阻塞',
    pending: '待审', support: '支持', reject: '拒绝',
    conflict: '冲突', agreement: '一致',
    consensus_supported: '共识通过', model_conflict: '模型冲突',
    confidence_divergence: '置信度分歧', low_evidence: '证据不足',
  }
  return { color: colors[status] || '#86909c', label: labels[status] || status }
}

function badgeHtml(status: string | null | undefined): React.ReactNode {
  if (!status) return <span style={{ color: 'var(--text-muted)', fontSize: 12 }}>—</span>
  const { color, label } = statusBadge(status)
  return (
    <span style={{
      display: 'inline-block', padding: '1px 8px', borderRadius: 10,
      fontSize: 11, fontWeight: 600,
      background: color + '1a', color, border: `1px solid ${color}44`,
    }}>
      {label}
    </span>
  )
}

// ── Sub-tab: Run History ───────────────────────────────────────────────────

function DualReviewHistory({
  granularityLevel,
}: {
  granularityLevel?: string
}) {
  const [runs, setRuns] = useState<RunSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(0)
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null)
  const [runDetail, setRunDetail] = useState<any>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const totalPages = Math.max(1, Math.ceil(total / RUNS_PAGE_SIZE))

  const fetchRuns = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const params = new URLSearchParams()
      params.set('limit', String(RUNS_PAGE_SIZE))
      params.set('offset', String(page * RUNS_PAGE_SIZE))
      if (granularityLevel) params.set('granularity_level', granularityLevel)
      const res = await fetch(`/api/validation/circuit/runs?${params}`)
      if (!res.ok) throw new Error(`API错误: ${res.status}`)
      const data = await res.json()
      const runList = (Array.isArray(data) ? data : data.items || [])
        .filter((r: RunSummary) => r.dual_review_status && r.dual_review_status !== 'pending')
      setRuns(runList)
      setTotal(runList.length)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : '加载失败')
    } finally {
      setLoading(false)
    }
  }, [granularityLevel, page])

  useEffect(() => { fetchRuns() }, [fetchRuns])

  useEffect(() => {
    return () => { if (pollRef.current) clearInterval(pollRef.current) }
  }, [])

  const handleRunClick = async (runId: string) => {
    setSelectedRunId(runId)
    setDetailLoading(true)
    try {
      const res = await fetch(`/api/validation/circuit/runs/${runId}`)
      if (!res.ok) throw new Error(`API错误: ${res.status}`)
      const data = await res.json()
      setRunDetail(data)
    } catch {
      setRunDetail(null)
    } finally {
      setDetailLoading(false)
    }
  }

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'row', overflow: 'hidden' }}>
      {/* Runs list */}
      <div style={{ width: 340, borderRight: '1px solid var(--border)', overflow: 'hidden', display: 'flex', flexDirection: 'column', flexShrink: 0 }}>
        <div className="vr-header" style={{ flexShrink: 0 }}>
          <span className="vr-total">共 {total} 条记录</span>
          <button className="btn btn-sm btn-outline" onClick={fetchRuns} disabled={loading} style={{ marginLeft: 8 }}>
            <RefreshCw size={12} style={{ marginRight: 4 }} />
            刷新
          </button>
        </div>

        {error && (
          <div className="vw-error" style={{ flexShrink: 0 }}>
            {error}
            <button className="btn btn-sm btn-outline" onClick={fetchRuns} style={{ marginLeft: 8 }}>重试</button>
          </div>
        )}

        <div style={{ flex: 1, overflow: 'auto' }}>
          {loading && runs.length === 0 ? (
            <div className="vw-empty-state" style={{ padding: 24, textAlign: 'center' }}><p>加载中...</p></div>
          ) : runs.length === 0 ? (
            <div className="vw-empty-state" style={{ padding: 24, textAlign: 'center' }}>
              <p style={{ color: 'var(--text-muted)', fontSize: 13 }}>暂无双模型盲审运行记录。</p>
            </div>
          ) : (
            runs.map(run => {
              const { color: sc } = statusBadge(run.status)
              return (
                <div
                  key={run.id}
                  className={`vr-row${selectedRunId === run.id ? ' selected' : ''}`}
                  onClick={() => handleRunClick(run.id)}
                  style={{
                    padding: '10px 16px', cursor: 'pointer', borderBottom: '1px solid var(--border)',
                    display: 'flex', flexDirection: 'column', gap: 4,
                    background: selectedRunId === run.id ? 'var(--bg-active, #e6f4ff)' : undefined,
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <FileText size={14} color="var(--text-muted)" />
                    <span style={{ fontSize: 13, fontWeight: 600 }}>Run {run.id.slice(0, 8)}</span>
                    <span style={{ display: 'inline-block', width: 8, height: 8, borderRadius: '50%', background: sc }} />
                    <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>{STATUS_LABELS[run.status] || run.status}</span>
                  </div>
                  <div style={{ display: 'flex', gap: 12, fontSize: 12, color: 'var(--text-muted)' }}>
                    <span>一致: {run.dual_review_agreement_count}</span>
                    <span>冲突: {run.dual_review_conflict_count}</span>
                    <span>{run.granularity_level}</span>
                  </div>
                  <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                    {run.created_at ? new Date(run.created_at).toLocaleString('zh-CN') : '—'}
                  </div>
                </div>
              )
            })
          )}
        </div>

        {totalPages > 1 && (
          <div style={{ display: 'flex', gap: 8, alignItems: 'center', justifyContent: 'center', padding: '6px 0', borderTop: '1px solid var(--border)', fontSize: 12, flexShrink: 0 }}>
            <button className="btn btn-sm btn-outline" disabled={page === 0} onClick={() => setPage(Math.max(0, page - 1))}>上一页</button>
            <span style={{ color: 'var(--text-muted)' }}>{page + 1} / {totalPages}</span>
            <button className="btn btn-sm btn-outline" disabled={page >= totalPages - 1} onClick={() => setPage(page + 1)}>下一页</button>
          </div>
        )}
      </div>

      {/* Detail panel */}
      <div style={{ flex: 1, overflow: 'auto', padding: 16 }}>
        {!selectedRunId ? (
          <div className="vw-empty-state" style={{ textAlign: 'center', paddingTop: 60 }}>
            <p style={{ color: 'var(--text-muted)' }}>选择左侧运行记录查看详情</p>
          </div>
        ) : detailLoading ? (
          <div className="vw-empty-state" style={{ textAlign: 'center', paddingTop: 60 }}><p>加载中...</p></div>
        ) : runDetail ? (
          <div>
            <h4 style={{ fontSize: 14, marginBottom: 12 }}>
              Run {runDetail.id?.slice(0, 8)} — 双模型盲审结果
            </h4>
            <div className="vpm-cards">
              <div className="vpm-card vpm-card-green"><span className="vpm-card-num">{runDetail.dual_review_agreement_count || 0}</span><span>一致</span></div>
              <div className="vpm-card vpm-card-amber"><span className="vpm-card-num">{runDetail.dual_review_conflict_count || 0}</span><span>冲突</span></div>
              <div className="vpm-card vpm-card-red"><span className="vpm-card-num">{runDetail.dual_review_rejection_count || 0}</span><span>拒绝</span></div>
              <div className="vpm-card"><span className="vpm-card-num">{runDetail.dual_review_uncertain_count || 0}</span><span>不确定</span></div>
            </div>
            {(runDetail.results || []).length > 0 && (
              <div className="vpm-table-wrap" style={{ marginTop: 12 }}>
                <table className="vr-table" style={{ fontSize: 13 }}>
                  <thead>
                    <tr>
                      <th>回路</th><th>审 A</th><th>审 B</th><th>裁决</th><th>优先级</th>
                    </tr>
                  </thead>
                  <tbody>
                    {runDetail.results.map((r: any, i: number) => (
                      <tr key={r.id || i}>
                        <td style={{ fontSize: 12, maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis' }}>
                          {r.object_label || r.target_id?.slice(0, 12)}
                        </td>
                        <td>{badgeHtml(r.reviewer_a_decision)}</td>
                        <td>{badgeHtml(r.reviewer_b_decision)}</td>
                        <td>{badgeHtml(r.adjudication_status)}</td>
                        <td style={{ fontSize: 12 }}>{r.recommended_review_priority || '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        ) : (
          <div className="vw-empty-state" style={{ textAlign: 'center', paddingTop: 60 }}>
            <p style={{ color: 'var(--text-muted)' }}>无法加载详情</p>
          </div>
        )}
      </div>
    </div>
  )
}

// ── Sub-tab: Start Review ──────────────────────────────────────────────────

function StartDualReview({
  granularityLevel,
}: {
  granularityLevel?: string
}) {
  const [items, setItems] = useState<DualReviewCandidate[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [actionLoading, setActionLoading] = useState(false)
  const [actionMessage, setActionMessage] = useState<string | null>(null)
  const [reviewProgress, setReviewProgress] = useState<{open: boolean; runId: string; status: string; done: number; total: number} | null>(null)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const pollCountRef = useRef(0)
  const MAX_POLL = 150

  useEffect(() => {
    return () => { if (pollRef.current) clearInterval(pollRef.current) }
  }, [])

  const fetchData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const params = new URLSearchParams()
      params.set('limit', '50')
      if (granularityLevel) params.set('granularity_level', granularityLevel)
      const res = await fetch(`/api/validation/circuit/review-queue?${params}`)
      if (!res.ok) throw new Error(`API错误: ${res.status}`)
      const data = await res.json()
      setItems(data.items || [])
      setTotal(data.total || data.items?.length || 0)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : '加载失败')
    } finally {
      setLoading(false)
    }
  }, [granularityLevel])

  useEffect(() => { fetchData() }, [fetchData])

  const toggleSelect = (id: string) => {
    const next = new Set(selected)
    if (next.has(id)) next.delete(id); else next.add(id)
    setSelected(next)
  }

  const doAction = useCallback(async (endpoint: string, label: string) => {
    if (selected.size === 0) return
    setActionLoading(true)
    setActionMessage(null)
    try {
      const res = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ circuit_ids: Array.from(selected) }),
      })
      if (!res.ok) throw new Error(`API错误: ${res.status}`)
      const data = await res.json()
      setSelected(new Set())

      const runId = data.internal_run_id || ''
      if (endpoint.includes('dual-review') && runId) {
        setReviewProgress({open: true, runId, status: 'running', done: 0, total: data.eligible_count || 0})
        if (pollRef.current) clearInterval(pollRef.current)
        pollCountRef.current = 0
        pollRef.current = setInterval(async () => {
          pollCountRef.current++
          if (pollCountRef.current > MAX_POLL) { clearInterval(pollRef.current!); pollRef.current = null; return }
          try {
            const prRes = await fetch(`/api/validation/circuit/runs/${runId}/progress`)
            if (!prRes.ok) { clearInterval(pollRef.current!); pollRef.current = null; return }
            const pr = await prRes.json()
            setReviewProgress(p => p ? {
              ...p,
              done: (pr.dual_review_agreement_count || 0) + (pr.dual_review_conflict_count || 0) + (pr.dual_review_rejection_count || 0) + (pr.dual_review_uncertain_count || 0),
              total: pr.dual_review_total_count || p.total,
              status: pr.status || p.status,
            } : null)
            if (pr.status === 'completed' || pr.status === 'failed' || pr.status === 'cancelled') {
              clearInterval(pollRef.current!); pollRef.current = null
              setReviewProgress(p => p ? {...p, status: pr.status} : null)
              fetchData()
            }
          } catch { clearInterval(pollRef.current!); pollRef.current = null }
        }, 2000)
      } else {
        setActionMessage(`${label} 已完成`)
        setTimeout(() => setActionMessage(null), 5000)
        fetchData()
      }
    } catch (e: unknown) {
      setActionMessage(e instanceof Error ? e.message : '操作失败')
      setTimeout(() => setActionMessage(null), 5000)
    } finally {
      setActionLoading(false)
    }
  }, [selected, fetchData])

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      {actionMessage && (
        <div style={{
          margin: '8px 16px 0', padding: '6px 12px', borderRadius: 'var(--radius)', fontSize: 13, flexShrink: 0,
          background: actionMessage.includes('失败') ? '#fff2f0' : '#f6ffed',
          color: actionMessage.includes('失败') ? 'var(--danger)' : 'var(--success)',
        }}>
          {actionMessage}
        </div>
      )}

      {error && (
        <div className="vw-error" style={{ margin: '8px 16px 0', flexShrink: 0 }}>
          {error}
          <button className="btn btn-sm btn-outline" onClick={fetchData} style={{ marginLeft: 8 }}>重试</button>
        </div>
      )}

      <div style={{ flex: 1, overflow: 'auto', padding: '0 16px' }}>
        <div className="vr-table-wrap">
          <table className="vr-table">
            <thead>
              <tr>
                <th className="vr-th-check">
                  <input type="checkbox"
                    checked={selected.size === items.length && items.length > 0}
                    onChange={() => {
                      if (selected.size === items.length) setSelected(new Set())
                      else setSelected(new Set(items.map(i => i.id)))
                    }}
                  />
                </th>
                <th>名称</th>
                <th className="vr-th-type">类型</th>
                <th className="vr-th-status">规则</th>
                <th className="vr-th-status">审 A</th>
                <th className="vr-th-status">审 B</th>
                <th className="vr-th-status">裁决</th>
              </tr>
            </thead>
            <tbody>
              {items.length === 0 ? (
                <tr><td colSpan={7} className="vr-empty">
                  <p style={{ color: 'var(--text-muted)' }}>暂无可送入双模型盲审的回路</p>
                </td></tr>
              ) : items.map((item, i) => (
                <tr key={item.id}
                  className={`vr-row${i % 2 === 1 ? ' even' : ''}${selected.has(item.id) ? ' selected' : ''}`}
                  onClick={() => toggleSelect(item.id)}
                >
                  <td className="vr-td-check" onClick={e => e.stopPropagation()}>
                    <input type="checkbox" checked={selected.has(item.id)} onChange={() => toggleSelect(item.id)} />
                  </td>
                  <td className="vr-td-label" style={{ maxWidth: 280, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {item.circuit_name?.slice(0, 60) || item.id.slice(0, 12)}
                  </td>
                  <td><span className="vr-badge">{item.circuit_type || '?'}</span></td>
                  <td>{badgeHtml(item.rule_overall_status)}</td>
                  <td>{badgeHtml(item.reviewer_a_decision)}</td>
                  <td>{badgeHtml(item.reviewer_b_decision)}</td>
                  <td>{badgeHtml(item.adjudication_status)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {selected.size > 0 && (
        <div className="vr-action-bar" style={{ flexShrink: 0 }}>
          <span>已选 {selected.size} 项</span>
          <div className="vr-action-sep" />
          <button className="btn btn-sm btn-primary" onClick={() => doAction('/api/validation/circuit/selection/dual-review', '双模型审核')} disabled={actionLoading}>
            <Zap size={14} style={{ marginRight: 4 }} />
            送入双模型审核
          </button>
          <button className="btn btn-sm btn-outline" onClick={() => doAction('/api/validation/circuit/selection/retry-reviewer-a', '重试 Reviewer A')} disabled={actionLoading}>
            重试 Reviewer A
          </button>
          <button className="btn btn-sm btn-outline" onClick={() => doAction('/api/validation/circuit/selection/retry-reviewer-b', '重试 Reviewer B')} disabled={actionLoading}>
            重试 Reviewer B
          </button>
          <button className="btn btn-sm btn-outline" onClick={() => setSelected(new Set())} disabled={actionLoading}>
            清除选择
          </button>
        </div>
      )}

      {reviewProgress?.open && (
        <div className="vw-modal-overlay">
          <div className="vw-modal vw-modal-sm">
            <div className="vw-modal-hd"><h3>双模型盲审中</h3></div>
            <div className="vw-modal-body">
              <div className="vw-progress-bar-wrap">
                <div className="vw-progress-bar" style={{ width: `${reviewProgress.total > 0 ? (reviewProgress.done / reviewProgress.total) * 100 : 0}%` }} />
              </div>
              <p>已完成 {reviewProgress.done}/{reviewProgress.total} 项</p>
              <p>状态: {reviewProgress.status === 'completed' ? '已完成' : reviewProgress.status === 'failed' ? '失败' : reviewProgress.status === 'cancelled' ? '已取消' : '运行中...'}</p>
            </div>
            {reviewProgress.status !== 'running' && (
              <div className="vw-modal-ft">
                <button className="btn btn-primary" onClick={() => setReviewProgress(null)}>确定</button>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

// ── Main Component ─────────────────────────────────────────────────────────

export function DualReviewPanel({ granularityLevel }: Props) {
  const [subTab, setSubTab] = useState<SubTab>('start')

  return (
    <div className="vr-panel" style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      {/* Sub-tabs */}
      <div className="vr-header" style={{ flexShrink: 0 }}>
        <div className="vr-tabs">
          <button
            className={`vr-tab${subTab === 'history' ? ' active' : ''}`}
            onClick={() => setSubTab('history')}
          >
            运行记录
          </button>
          <button
            className={`vr-tab${subTab === 'start' ? ' active' : ''}`}
            onClick={() => setSubTab('start')}
          >
            开始盲审
          </button>
        </div>
      </div>

      {/* Sub-tab content */}
      <div style={{ flex: 1, overflow: 'hidden' }}>
        {subTab === 'history' && (
          <DualReviewHistory granularityLevel={granularityLevel} />
        )}
        {subTab === 'start' && (
          <StartDualReview granularityLevel={granularityLevel} />
        )}
      </div>
    </div>
  )
}
