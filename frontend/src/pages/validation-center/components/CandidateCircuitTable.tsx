import { useState, useEffect, useCallback, useRef } from 'react'
import { Zap } from 'lucide-react'
import { CircuitDetailDrawer } from './CircuitDetailDrawer'

// ── Types ──────────────────────────────────────────────────────────────────
interface CandidateCircuit {
  id: string
  circuit_name: string
  granularity_level: string
  circuit_type: string
  topology_type: string
  closed_loop: boolean
  step_count: number
  confidence: number
  function_association: string
  evidence_text: string
  review_status: string
  promotion_status: string
  mirror_status: string
  source_atlas: string
  created_at: string | null
  rule_overall_status?: string
  reviewer_a_decision?: string
  reviewer_b_decision?: string
  adjudication_status?: string
}

interface Props {
  granularityLevel?: string
}

// ── Progress Types ──────────────────────────────────────────────────────────
interface CandidateProgress {
  circuit_id: string
  circuit_name: string
  path_summary: string
  completed_rule_count: number
  enabled_rule_count: number
  pass_count: number
  warning_count: number
  hard_fail_count: number
  status: string
  current_rule_code: string
  eligible_for_dual_review: boolean
}

interface ValidationProgress {
  open: boolean
  runId: string
  phase: string
  selected_candidate_count: number
  completed_candidate_count: number
  enabled_rule_count: number
  expected_rule_execution_count: number
  completed_rule_execution_count: number
  pass_count: number
  warning_count: number
  hard_fail_count: number
  eligible_for_dual_review_count: number
  blocked_candidate_count: number
  candidate_progress: CandidateProgress[]
  started_at: string
  elapsed_seconds: number
  autoHandoff: boolean
}

// ── Helpers ────────────────────────────────────────────────────────────────
const STATUS_COLORS: Record<string, string> = {
  pending: '#faad14',
  approved: '#52c41a',
  rejected: '#ff4d4f',
  not_promoted: '#86909c',
  promoted_to_final: '#2f54eb',
  llm_suggested: '#2f54eb',
  passed: '#52c41a',
  failed: '#ff4d4f',
  blocked: '#faad14',
  support: '#52c41a',
  reject: '#ff4d4f',
  conflict: '#faad14',
  agreement: '#52c41a',
}

const STATUS_LABELS: Record<string, string> = {
  pending: '待审核', approved: '已通过', rejected: '已拒绝',
  not_promoted: '未晋升', promoted_to_final: '已晋升',
  llm_suggested: 'LLM建议', passed: '通过', failed: '失败',
  blocked: '阻塞', support: '支持', reject: '拒绝',
  conflict: '冲突', agreement: '一致',
}

const PHASE_LABELS: Record<string, string> = {
  running: '运行中', completed: '已完成', failed: '失败',
  cancelled: '已取消', rule_validation: '规则校验', dual_review: '双审',
}

function statusBadge(status: string): { color: string; label: string } {
  const c = STATUS_COLORS[status] || '#86909c'
  return { color: c, label: STATUS_LABELS[status] || status }
}

function badgeHtml(status: string): React.ReactNode {
  const { color, label } = statusBadge(status)
  if (!status) return <span style={{ color: 'var(--text-muted)', fontSize: 12 }}>—</span>
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

function formatConfidence(v: number): string {
  if (v === 0) return '—'
  return (v * 100).toFixed(0) + '%'
}

// ── Main Component ─────────────────────────────────────────────────────────
export function CandidateCircuitTable({ granularityLevel }: Props) {
  const [items, setItems] = useState<CandidateCircuit[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [page, setPage] = useState(0)
  const [search, setSearch] = useState('')
  const [granFilter, setGranFilter] = useState(granularityLevel || 'all')
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [detailCircuitId, setDetailCircuitId] = useState<string | null>(null)
  const [batchLoading, setBatchLoading] = useState(false)
  const [batchMessage, setBatchMessage] = useState<string | null>(null)
  const [validationProgress, setValidationProgress] = useState<ValidationProgress | null>(null)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const autoHandoffRef = useRef(false)

  // Sync autoHandoffRef with state
  useEffect(() => {
    autoHandoffRef.current = validationProgress?.autoHandoff || false
  }, [validationProgress?.autoHandoff])

  const pageSize = 25

  // Update granFilter when granularityLevel prop changes
  useEffect(() => {
    setGranFilter(granularityLevel || 'all')
  }, [granularityLevel])

  // Fetch candidates
  const fetchData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const params = new URLSearchParams()
      if (granFilter && granFilter !== 'all') params.set('granularity_level', granFilter)
      if (search) params.set('search', search)
      params.set('only_not_promoted', 'true')
      params.set('limit', String(pageSize))
      params.set('offset', String(page * pageSize))
      const res = await fetch(`/api/validation/circuit/candidates?${params}`)
      if (!res.ok) throw new Error(`API错误: ${res.status}`)
      const data = await res.json()
      setItems(data.items || [])
      setTotal(data.total || 0)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : '加载失败')
    } finally {
      setLoading(false)
    }
  }, [granFilter, search, page, pageSize])

  useEffect(() => { fetchData() }, [fetchData])

  // Selection
  const toggleSelect = (id: string) => {
    const next = new Set(selected)
    if (next.has(id)) next.delete(id); else next.add(id)
    setSelected(next)
  }
  const toggleSelectAll = () => {
    if (selected.size === items.length) {
      setSelected(new Set())
    } else {
      setSelected(new Set(items.map(i => i.id)))
    }
  }

  // Batch action: send to rule validation
  const handleBatchValidate = useCallback(async () => {
    if (selected.size === 0) return
    setBatchLoading(true)
    setBatchMessage(null)
    try {
      const res = await fetch('/api/validation/circuit/selection/rule-validate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ circuit_ids: Array.from(selected) }),
      })
      if (!res.ok) throw new Error(`API错误: ${res.status}`)
      const data = await res.json()
      setSelected(new Set())
      const runId = data.internal_run_id || ''
      setBatchMessage(`验证任务已创建 (ID: ${runId.slice(0, 8) || '—'}) 已处理 ${data.eligible_count || 0}/${data.selected_count || 0} 个回路`)
      // Show progress modal and start polling
      if (runId) {
        setValidationProgress({
          open: true, runId, phase: 'running',
          selected_candidate_count: data.eligible_count || 0,
          completed_candidate_count: 0,
          enabled_rule_count: 0,
          expected_rule_execution_count: 0,
          completed_rule_execution_count: 0,
          pass_count: 0, warning_count: 0, hard_fail_count: 0,
          eligible_for_dual_review_count: 0, blocked_candidate_count: 0,
          candidate_progress: [],
          started_at: '', elapsed_seconds: 0,
          autoHandoff: false,
        })
        pollRef.current = setInterval(async () => {
          try {
            const prRes = await fetch(`/api/validation/circuit/runs/${runId}/progress`)
            if (!prRes.ok) { if (pollRef.current) clearInterval(pollRef.current); return }
            const pr = await prRes.json()
            // After completion
            if (pr.phase === 'completed') {
              if (pollRef.current) clearInterval(pollRef.current)
              pollRef.current = null
              setValidationProgress(p => p ? {
                ...p,
                phase: 'completed',
                completed_candidate_count: pr.completed_candidate_count || 0,
                pass_count: pr.pass_count || 0,
                warning_count: pr.warning_count || 0,
                hard_fail_count: pr.hard_fail_count || 0,
                eligible_for_dual_review_count: pr.eligible_for_dual_review_count || 0,
                blocked_candidate_count: pr.blocked_candidate_count || 0,
                candidate_progress: pr.candidate_progress || [],
                elapsed_seconds: pr.elapsed_seconds || 0,
              } : null)
              // Auto-handoff if enabled (read from ref to avoid stale closure)
              if (autoHandoffRef.current && (pr.eligible_for_dual_review_count || 0) > 0) {
                const eligible = (pr.candidate_progress || []).filter((cp: CandidateProgress) => cp.eligible_for_dual_review).map((cp: CandidateProgress) => cp.circuit_id)
                try {
                  await fetch('/api/validation/circuit/selection/dual-review', {
                    method: 'POST', headers: {'Content-Type':'application/json'},
                    body: JSON.stringify({circuit_ids: eligible, force_review: false})
                  })
                } catch { /* silent */ }
              }
              fetchData()
            } else if (pr.phase === 'failed' || pr.status === 'failed' || pr.status === 'cancelled') {
              if (pollRef.current) clearInterval(pollRef.current)
              pollRef.current = null
              setValidationProgress(p => p ? { ...p, phase: 'failed', elapsed_seconds: pr.elapsed_seconds || 0 } : null)
              fetchData()
            } else {
              // Mid-run update
              setValidationProgress(p => p ? {
                ...p,
                completed_candidate_count: pr.completed_candidate_count || 0,
                pass_count: pr.pass_count || 0,
                warning_count: pr.warning_count || 0,
                hard_fail_count: pr.hard_fail_count || 0,
                eligible_for_dual_review_count: pr.eligible_for_dual_review_count || 0,
                candidate_progress: pr.candidate_progress || [],
                elapsed_seconds: pr.elapsed_seconds || 0,
              } : null)
            }
          } catch { if (pollRef.current) clearInterval(pollRef.current); pollRef.current = null }
        }, 2000)
      }
      setTimeout(() => setBatchMessage(null), 5000)
    } catch (e: unknown) {
      setBatchMessage(e instanceof Error ? e.message : '提交失败')
      setTimeout(() => setBatchMessage(null), 5000)
    } finally {
      setBatchLoading(false)
    }
  }, [selected, fetchData])

  // Detail drawer
  const handleRowClick = (item: CandidateCircuit) => {
    setDetailCircuitId(item.id)
  }

  const totalPages = Math.ceil(total / pageSize)

  // ── Render ───────────────────────────────────────────────────────────────
  return (
    <div className="vr-panel" style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      {/* Filter bar */}
      <div className="vr-header" style={{ flexShrink: 0 }}>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flex: 1, flexWrap: 'wrap' }}>
          <select
            className="form-select"
            value={granFilter}
            onChange={e => { setGranFilter(e.target.value); setPage(0); setSelected(new Set()) }}
            style={{ padding: '4px 8px', borderRadius: 'var(--radius)', border: '1px solid var(--border)', fontSize: 13 }}
          >
            <option value="all">全部粒度</option>
            <option value="macro_clinical">宏观临床</option>
            <option value="molecular_attr">分子属性</option>
            <option value="meso_anatomical">中观解剖</option>
          </select>

          <input
            type="text"
            placeholder="搜索回路名称…"
            value={search}
            onChange={e => { setSearch(e.target.value); setPage(0) }}
            style={{
              padding: '4px 10px', borderRadius: 'var(--radius)', border: '1px solid var(--border)',
              fontSize: 13, width: 200, outline: 'none',
            }}
            onKeyDown={e => { if (e.key === 'Enter') fetchData() }}
          />
          <button className="btn btn-sm btn-outline" onClick={fetchData} disabled={loading}>
            {loading ? '加载中…' : '查询'}
          </button>

          <span className="vr-total" style={{ marginLeft: 8 }}>共 {total} 条</span>
        </div>
      </div>

      {/* Batch action bar */}
      {selected.size > 0 && (
        <div className="vr-action-bar">
          <span>已选 {selected.size} 项</span>
          <div className="vr-action-sep" />
          <button
            className="btn btn-sm btn-primary"
            onClick={handleBatchValidate}
            disabled={batchLoading}
          >
            {batchLoading ? '提交中…' : '送入规则校验'}
          </button>
          <button
            className="btn btn-sm btn-outline"
            onClick={() => setSelected(new Set())}
            disabled={batchLoading}
          >
            清除选择
          </button>
          {batchMessage && (
            <span style={{
              fontSize: 13, color: batchMessage.includes('失败') ? 'var(--danger)' : 'var(--success)',
              marginLeft: 8,
            }}>
              {batchMessage}
            </span>
          )}
        </div>
      )}

      {/* Error */}
      {error && <div className="vr-error">{error}</div>}

      {/* Table area */}
      <div className="vr-table-wrap" style={{ flex: 1, overflow: 'auto' }}>
        {loading ? (
          <div className="vr-empty">加载中…</div>
        ) : items.length === 0 ? (
          <div className="vr-empty">
            <p>暂无候选回路。</p>
            <p style={{ fontSize: 12, color: '#86909c', marginTop: 4 }}>
              请先在数据中心生成回路数据，或调整筛选条件。
            </p>
          </div>
        ) : (
          <table className="vr-table">
            <thead>
              <tr>
                <th className="vr-th-check">
                  <input type="checkbox" checked={selected.size === items.length && items.length > 0} onChange={toggleSelectAll} />
                </th>
                <th style={{ minWidth: 140 }}>回路名称</th>
                <th className="vr-th-type">类型</th>
                <th style={{ width: 72 }}>粒度</th>
                <th style={{ width: 48, textAlign: 'center' }}>步骤</th>
                <th className="vr-th-conf">置信度</th>
                <th className="vr-th-status">规则</th>
                <th className="vr-th-status">审 A</th>
                <th className="vr-th-status">审 B</th>
                <th className="vr-th-status">裁决</th>
                <th className="vr-th-status">审核</th>
                <th className="vr-th-status">晋升</th>
                <th style={{ width: 100 }}>数据源</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item, i) => {
                const reviewBadge = statusBadge(item.review_status)
                const promoBadge = statusBadge(item.promotion_status)
                return (
                  <tr key={item.id}
                    className={`vr-row${i % 2 === 1 ? ' even' : ''}${selected.has(item.id) ? ' selected' : ''}`}
                    onClick={() => handleRowClick(item)}
                  >
                    <td className="vr-td-check" onClick={e => e.stopPropagation()}>
                      <input type="checkbox" checked={selected.has(item.id)} onChange={() => toggleSelect(item.id)} />
                    </td>
                    <td className="vr-td-label">{item.circuit_name}</td>
                    <td><span className="vr-badge">{item.circuit_type}</span></td>
                    <td style={{ fontSize: 12 }}>{item.granularity_level}</td>
                    <td style={{ textAlign: 'center', fontSize: 13 }}>{item.step_count}</td>
                    <td>{formatConfidence(item.confidence)}</td>
                    <td>{badgeHtml(item.rule_overall_status || '')}</td>
                    <td style={{ fontSize: 12, color: 'var(--text-muted)' }}>{item.reviewer_a_decision || '—'}</td>
                    <td style={{ fontSize: 12, color: 'var(--text-muted)' }}>{item.reviewer_b_decision || '—'}</td>
                    <td style={{ fontSize: 12, color: 'var(--text-muted)' }}>{item.adjudication_status || '—'}</td>
                    <td>
                      <span style={{
                        display: 'inline-block', padding: '1px 8px', borderRadius: 10,
                        fontSize: 11, fontWeight: 600,
                        background: reviewBadge.color + '1a',
                        color: reviewBadge.color,
                        border: `1px solid ${reviewBadge.color}44`,
                      }}>
                        {reviewBadge.label}
                      </span>
                    </td>
                    <td>
                      <span style={{
                        display: 'inline-block', padding: '1px 8px', borderRadius: 10,
                        fontSize: 11, fontWeight: 600,
                        background: promoBadge.color + '1a',
                        color: promoBadge.color,
                        border: `1px solid ${promoBadge.color}44`,
                      }}>
                        {promoBadge.label}
                      </span>
                    </td>
                    <td style={{ fontSize: 12, color: 'var(--text-muted)' }}>{item.source_atlas || '—'}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="vr-pagination">
          <button disabled={page === 0} onClick={() => setPage(p => Math.max(0, p - 1))}>上一页</button>
          <span>第 {page + 1} / {totalPages} 页</span>
          <button disabled={page >= totalPages - 1} onClick={() => setPage(p => p + 1)}>下一页</button>
        </div>
      )}

      {/* Detail drawer */}
      <CircuitDetailDrawer circuitId={detailCircuitId} onClose={() => setDetailCircuitId(null)} />

      {/* Validation progress modal */}
      {validationProgress?.open && (
        <div className="vw-modal-overlay" onClick={() => { if (validationProgress.phase !== 'running') setValidationProgress(null) }}>
          <div className="vw-modal vw-modal-wide" onClick={e => e.stopPropagation()}>
            {/* Header */}
            <div className="vw-modal-hd">
              <h3>🛡 规则校验</h3>
              <span className="badge">{PHASE_LABELS[validationProgress.phase] || validationProgress.phase}</span>
              <span className="vw-modal-meta">Run: {validationProgress.runId.slice(0,8)}</span>
              {validationProgress.phase !== 'running' && <button className="vw-modal-close" onClick={() => setValidationProgress(null)}>✕</button>}
            </div>

            <div className="vw-modal-body">
              {/* Summary cards */}
              <div className="vpm-cards">
                <div className="vpm-card"><span className="vpm-card-num">{validationProgress.selected_candidate_count}</span><span>候选回路</span></div>
                <div className="vpm-card vpm-card-green"><span className="vpm-card-num">{validationProgress.pass_count}</span><span>通过</span></div>
                <div className="vpm-card vpm-card-amber"><span className="vpm-card-num">{validationProgress.warning_count}</span><span>警告</span></div>
                <div className="vpm-card vpm-card-red"><span className="vpm-card-num">{validationProgress.hard_fail_count}</span><span>阻塞</span></div>
                <div className="vpm-card vpm-card-blue"><span className="vpm-card-num">{validationProgress.eligible_for_dual_review_count}</span><span>可双审</span></div>
              </div>

              {/* Two-level progress */}
              <div className="vpm-progress-section">
                <span>回路: {validationProgress.completed_candidate_count}/{validationProgress.selected_candidate_count}</span>
                <div className="vpm-bar">
                  <div className="vpm-bar-fill" style={{width:`${validationProgress.selected_candidate_count>0?(validationProgress.completed_candidate_count/validationProgress.selected_candidate_count)*100:0}%`}}/>
                </div>
                <span className="vpm-progress-detail">规则执行: {validationProgress.completed_rule_execution_count}/{validationProgress.expected_rule_execution_count} | 启用规则: {validationProgress.enabled_rule_count}条 | 耗时: {Math.round(validationProgress.elapsed_seconds)}s</span>
              </div>

              {/* Auto-handoff checkbox (before completion) */}
              {validationProgress.phase === 'running' && (
                <label className="vpm-checkbox">
                  <input type="checkbox" checked={validationProgress.autoHandoff}
                    onChange={() => setValidationProgress(p => p ? {...p, autoHandoff: !p.autoHandoff} : null)}/>
                  规则通过后自动送入双模型审核
                </label>
              )}

              {/* Candidate result table */}
              {validationProgress.candidate_progress.length > 0 && (
                <div className="vpm-table-wrap">
                  <table className="vr-table">
                    <thead><tr><th>#</th><th>回路名称</th><th>规则</th><th>通过</th><th>警告</th><th>阻塞</th><th>状态</th></tr></thead>
                    <tbody>
                      {validationProgress.candidate_progress.map((cp, i) => (
                        <tr key={cp.circuit_id} className={`vr-row vpm-row-${cp.status}`}>
                          <td>{i+1}</td>
                          <td title={cp.circuit_name}>{cp.circuit_name.slice(0,30)}</td>
                          <td>{cp.completed_rule_count}/{cp.enabled_rule_count}</td>
                          <td className="vpm-green">{cp.pass_count}</td>
                          <td className="vpm-amber">{cp.warning_count}</td>
                          <td className="vpm-red">{cp.hard_fail_count}</td>
                          <td><span className={`badge badge-${cp.status}`}>{cp.status}</span></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>

            {/* Footer actions */}
            <div className="vw-modal-ft">
              {validationProgress.phase === 'running' && (
                <button className="btn btn-sm" onClick={() => {
                  if (pollRef.current) clearInterval(pollRef.current)
                  pollRef.current = null
                  setValidationProgress(null)
                }}>后台运行</button>
              )}
              {validationProgress.phase === 'completed' && (
                <>
                  <span className="vpm-ft-info">已完成: {validationProgress.pass_count} 通过, {validationProgress.hard_fail_count} 阻塞 | 可双审: {validationProgress.eligible_for_dual_review_count}</span>
                  <button className="btn btn-sm btn-primary" disabled={validationProgress.eligible_for_dual_review_count === 0}
                    onClick={async () => {
                      const eligible = validationProgress.candidate_progress.filter(cp => cp.eligible_for_dual_review).map(cp => cp.circuit_id)
                      if (eligible.length === 0) return
                      if (!confirm(`送入 ${eligible.length} 条回路到双模型审核？`)) return
                      await fetch('/api/validation/circuit/selection/dual-review', {
                        method: 'POST', headers: {'Content-Type':'application/json'},
                        body: JSON.stringify({circuit_ids: eligible, force_review: false})
                      })
                      setValidationProgress(null)
                      fetchData()
                    }}>
                    <Zap size={14}/> 送入双模型审核({validationProgress.eligible_for_dual_review_count})
                  </button>
                  <button className="btn btn-sm" onClick={() => setValidationProgress(null)}>关闭</button>
                </>
              )}
              {validationProgress.phase === 'failed' && (
                <>
                  <span className="vpm-ft-error">任务失败</span>
                  <button className="btn btn-sm btn-primary" onClick={async () => {
                    const eligible = validationProgress.candidate_progress.filter(cp => cp.status === 'failed').map(cp => cp.circuit_id)
                    await fetch('/api/validation/circuit/selection/rule-validate', {
                      method: 'POST', headers: {'Content-Type':'application/json'},
                      body: JSON.stringify({circuit_ids: eligible, force_revalidate: true})
                    })
                    setValidationProgress(null)
                    fetchData()
                  }}>重试失败项</button>
                  <button className="btn btn-sm" onClick={() => setValidationProgress(null)}>关闭</button>
                </>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
