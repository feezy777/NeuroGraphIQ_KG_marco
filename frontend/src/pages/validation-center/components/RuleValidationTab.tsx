import { useState, useEffect, useCallback, useRef } from 'react'
import { RefreshCw, FileText, Play, Zap, Sparkles } from 'lucide-react'
import { CircuitSelector } from './CircuitSelector'

// ── Types ──────────────────────────────────────────────────────────────────

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

interface CandidateProgressItem {
  circuit_id: string
  circuit_name: string
  completed_rule_count: number
  enabled_rule_count: number
  pass_count: number
  warning_count: number
  hard_fail_count: number
  status: string
  eligible_for_dual_review: boolean
  blocked_reasons?: Array<{ rule_code: string; message: string }>
}

interface RunProgress {
  run_id: string
  status: string
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
  failed_candidate_count: number
  candidate_progress: CandidateProgressItem[]
  started_at?: string
  elapsed_seconds: number
  original_run_id?: string
  original_hard_fails?: number
}

const STATUS_LABELS: Record<string, string> = {
  created: '已创建', queued: '排队中', running: '运行中',
  completed: '已完成', failed: '失败', cancelled: '已取消',
}

const PHASE_LABELS: Record<string, string> = {
  running: '运行中', completed: '已完成', failed: '失败',
  cancelled: '已取消', rule_validation: '规则校验', dual_review: '双审',
}

const RUNS_PAGE_SIZE = 20

function statusBadge(status: string): { color: string; label: string } {
  const colors: Record<string, string> = {
    created: '#86909c', queued: '#2f54eb', running: '#2f54eb',
    completed: '#52c41a', failed: '#ff4d4f', cancelled: '#86909c',
  }
  return { color: colors[status] || '#86909c', label: STATUS_LABELS[status] || status }
}

function safeApiResponse<T extends Record<string, any>>(data: any, defaults: T): T {
  if (!data || typeof data !== 'object') return defaults
  const result = { ...defaults }
  for (const key of Object.keys(defaults)) {
    if (key in data && data[key] !== undefined && data[key] !== null) {
      (result as any)[key] = data[key]
    }
  }
  return result
}

const EMPTY_PROGRESS: RunProgress = {
  run_id: '', status: '', phase: '',
  selected_candidate_count: 0, completed_candidate_count: 0,
  enabled_rule_count: 0, expected_rule_execution_count: 0,
  completed_rule_execution_count: 0,
  pass_count: 0, warning_count: 0, hard_fail_count: 0,
  eligible_for_dual_review_count: 0,
  blocked_candidate_count: 0, failed_candidate_count: 0,
  candidate_progress: [],
  elapsed_seconds: 0,
}

// ── Props ──────────────────────────────────────────────────────────────────

interface Props {
  granularityLevel?: string
}

// ── Sub-tab: Run History ───────────────────────────────────────────────────

function RunHistory({
  granularityLevel, runs, runsLoading, runsError, runsTotal, runsPage,
  runsTotalPages, onRunsPageChange, fetchRuns, selectedRunId, onRunClick,
  runProgress, progressLoading, onRetryProgress,
}: {
  granularityLevel?: string
  runs: RunSummary[]
  runsLoading: boolean; runsError: string | null; runsTotal: number
  runsPage: number; runsTotalPages: number
  onRunsPageChange: (page: number) => void
  fetchRuns: () => void
  selectedRunId: string | null; onRunClick: (id: string) => void
  runProgress: RunProgress | null; progressLoading: boolean
  onRetryProgress: () => void
}) {
  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'row', overflow: 'hidden' }}>
      {/* Runs list */}
      <div style={{ width: 340, borderRight: '1px solid var(--border)', overflow: 'hidden', display: 'flex', flexDirection: 'column', flexShrink: 0 }}>
        <div className="vr-header" style={{ flexShrink: 0 }}>
          <span className="vr-total">共 {runsTotal} 条记录</span>
          <button className="btn btn-sm btn-outline" onClick={fetchRuns} disabled={runsLoading} style={{ marginLeft: 8 }}>
            <RefreshCw size={12} style={{ marginRight: 4 }} />
            刷新
          </button>
        </div>

        {runsError && (
          <div className="vw-error" style={{ flexShrink: 0 }}>
            {runsError}
            <button className="btn btn-sm btn-outline" onClick={fetchRuns} style={{ marginLeft: 8 }}>重试</button>
          </div>
        )}

        <div style={{ flex: 1, overflow: 'auto' }}>
          {runsLoading && runs.length === 0 ? (
            <div className="vw-empty-state" style={{ padding: 24, textAlign: 'center' }}>
              <p>加载中...</p>
            </div>
          ) : runs.length === 0 ? (
            <div className="vw-empty-state" style={{ padding: 24, textAlign: 'center' }}>
              <p style={{ color: 'var(--text-muted)', fontSize: 13 }}>暂无规则校验运行记录。</p>
              <p style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 4 }}>
                请在「开始校验」Tab 中发起新的校验。
              </p>
            </div>
          ) : (
            runs.map(run => {
              const { color: statusColor } = statusBadge(run.status)
              return (
                <div
                  key={run.id}
                  className={`vr-row${selectedRunId === run.id ? ' selected' : ''}`}
                  onClick={() => onRunClick(run.id)}
                  style={{
                    padding: '10px 16px', cursor: 'pointer', borderBottom: '1px solid var(--border)',
                    display: 'flex', flexDirection: 'column', gap: 4,
                    background: selectedRunId === run.id ? 'var(--bg-active, #e6f4ff)' : undefined,
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <FileText size={14} color="var(--text-muted)" />
                    <span style={{ fontSize: 13, fontWeight: 600 }}>Run {run.id.slice(0, 8)}</span>
                    <span
                      style={{
                        display: 'inline-block', width: 8, height: 8, borderRadius: '50%',
                        background: statusColor,
                      }}
                    />
                    <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>{STATUS_LABELS[run.status] || run.status}</span>
                  </div>
                  <div style={{ display: 'flex', gap: 12, fontSize: 12, color: 'var(--text-muted)' }}>
                    <span>通过: {run.rule_passed_count}</span>
                    <span>阻塞: {run.rule_blocked_count}</span>
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

        {/* Run pagination */}
        {runsTotalPages > 1 && (
          <div style={{ display: 'flex', gap: 8, alignItems: 'center', justifyContent: 'center', padding: '6px 0', borderTop: '1px solid var(--border)', fontSize: 12, flexShrink: 0 }}>
            <button className="btn btn-sm btn-outline" disabled={runsPage === 0} onClick={() => onRunsPageChange(Math.max(0, runsPage - 1))}>
              上一页
            </button>
            <span style={{ color: 'var(--text-muted)' }}>{runsPage + 1} / {runsTotalPages}</span>
            <button className="btn btn-sm btn-outline" disabled={runsPage >= runsTotalPages - 1} onClick={() => onRunsPageChange(runsPage + 1)}>
              下一页
            </button>
          </div>
        )}
      </div>

      {/* Progress detail */}
      <div style={{ flex: 1, overflow: 'auto', padding: 16 }}>
        {!selectedRunId ? (
          <div className="vw-empty-state" style={{ textAlign: 'center', paddingTop: 60 }}>
            <p style={{ color: 'var(--text-muted)' }}>选择左侧运行记录查看详情</p>
          </div>
        ) : progressLoading ? (
          <div className="vw-empty-state" style={{ textAlign: 'center', paddingTop: 60 }}>
            <p>加载中...</p>
          </div>
        ) : runProgress ? (
          <div>
            {/* Summary cards */}
            <div className="vpm-cards">
              <div className="vpm-card"><span className="vpm-card-num">{runProgress.selected_candidate_count}</span><span>候选回路</span></div>
              <div className="vpm-card vpm-card-green"><span className="vpm-card-num">{runProgress.pass_count}</span><span>通过</span></div>
              <div className="vpm-card vpm-card-amber"><span className="vpm-card-num">{runProgress.warning_count}</span><span>警告</span></div>
              <div className="vpm-card vpm-card-red"><span className="vpm-card-num">{runProgress.hard_fail_count}</span><span>阻塞</span></div>
              <div className="vpm-card vpm-card-blue"><span className="vpm-card-num">{runProgress.eligible_for_dual_review_count}</span><span>可双审</span></div>
            </div>

            {/* Progress bar */}
            <div className="vpm-progress-section" style={{ marginTop: 8 }}>
              <span>回路: {runProgress.completed_candidate_count}/{runProgress.selected_candidate_count}</span>
              <div className="vpm-bar">
                <div className="vpm-bar-fill" style={{ width: `${runProgress.selected_candidate_count > 0 ? (runProgress.completed_candidate_count / runProgress.selected_candidate_count) * 100 : 0}%` }} />
              </div>
              <span className="vpm-progress-detail">
                规则执行: {runProgress.completed_rule_execution_count}/{runProgress.expected_rule_execution_count}
                {' | '}启用规则: {runProgress.enabled_rule_count}条
                {' | '}耗时: {Math.round(runProgress.elapsed_seconds)}s
                {' | '}状态: {PHASE_LABELS[runProgress.phase] || runProgress.phase}
              </span>
            </div>

            {/* Before/After comparison */}
            {runProgress.original_run_id && runProgress.original_hard_fails !== undefined && (
              <div style={{ marginTop: 12, padding: 12, borderRadius: 8, border: '1px solid var(--border)', background: 'var(--bg-muted)' }}>
                <h4 style={{ fontSize: 13, fontWeight: 600, marginBottom: 8 }}>重新校验结果对比</h4>
                <div style={{ fontSize: 13, marginBottom: 4 }}>
                  原阻塞数: <strong>{runProgress.original_hard_fails}</strong> → 当前: <strong>{runProgress.hard_fail_count}</strong>
                </div>
                <div style={{ fontSize: 13, color: 'var(--success)' }}>
                  已解决: <strong>{runProgress.original_hard_fails - runProgress.hard_fail_count}</strong>
                </div>
                {runProgress.hard_fail_count === 0 && (
                  <div style={{ marginTop: 8, fontSize: 13, color: 'var(--success)', fontWeight: 600 }}>
                    ✅ 全部阻塞已解决，可送入双模型审核
                  </div>
                )}
              </div>
            )}

            {/* Candidate table */}
            {runProgress.candidate_progress && runProgress.candidate_progress.length > 0 && (
              <div className="vpm-table-wrap" style={{ marginTop: 12 }}>
                <table className="vr-table" style={{ fontSize: 13 }}>
                  <thead><tr><th>#</th><th>回路名称</th><th>规则</th><th>通过</th><th>警告</th><th>阻塞</th><th>状态</th></tr></thead>
                  <tbody>
                    {runProgress.candidate_progress.map((cp, i) => (
                      <tr key={cp.circuit_id} className={`vr-row vpm-row-${cp.status}`}>
                        <td>{i + 1}</td>
                        <td title={cp.circuit_name}>{cp.circuit_name?.slice(0, 30) || cp.circuit_id.slice(0, 12)}</td>
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

            {runProgress.phase === 'running' && (
              <div style={{ marginTop: 12, textAlign: 'center' }}>
                <RefreshCw size={16} style={{ animation: 'spin 1s linear infinite', marginRight: 6, verticalAlign: 'middle' }} />
                <span style={{ fontSize: 13, color: 'var(--text-muted)' }}>运行中...</span>
              </div>
            )}
          </div>
        ) : (
          <div className="vw-empty-state" style={{ textAlign: 'center', paddingTop: 60 }}>
            <p style={{ color: 'var(--text-muted)' }}>无法加载运行详情。</p>
            <button className="btn btn-sm" onClick={onRetryProgress}>重试</button>
          </div>
        )}
      </div>
    </div>
  )
}

// ── Sub-tab: Start Validation ──────────────────────────────────────────────

interface ValidationProgressModal {
  open: boolean
  runId: string
  phase: string
  selected_candidate_count: number; completed_candidate_count: number
  enabled_rule_count: number; expected_rule_execution_count: number; completed_rule_execution_count: number
  pass_count: number; warning_count: number; hard_fail_count: number
  eligible_for_dual_review_count: number; blocked_candidate_count: number; failed_candidate_count: number
  candidate_progress: CandidateProgressItem[]
  elapsed_seconds: number; autoHandoff: boolean
  original_run_id?: string; original_hard_fails?: number
}

const EMPTY_VP: ValidationProgressModal = {
  open: true, runId: '', phase: 'running',
  selected_candidate_count: 0, completed_candidate_count: 0,
  enabled_rule_count: 0, expected_rule_execution_count: 0, completed_rule_execution_count: 0,
  pass_count: 0, warning_count: 0, hard_fail_count: 0,
  eligible_for_dual_review_count: 0, blocked_candidate_count: 0, failed_candidate_count: 0,
  candidate_progress: [], elapsed_seconds: 0, autoHandoff: false,
}

function StartValidation({ granularityLevel }: { granularityLevel?: string }) {
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const [vp, setVp] = useState<ValidationProgressModal | null>(null)
  const [autoHandoff, setAutoHandoff] = useState(false)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const autoRef = useRef(false)

  useEffect(() => { autoRef.current = autoHandoff }, [autoHandoff])
  useEffect(() => { return () => { if (pollRef.current) clearInterval(pollRef.current) } }, [])

  const handleStart = async () => {
    if (selected.size === 0) {
      setMessage('请先选择要校验的回路')
      setTimeout(() => setMessage(null), 3000)
      return
    }
    setLoading(true)
    setMessage(null)
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
      setVp({
        ...EMPTY_VP,
        open: true, runId,
        selected_candidate_count: data.eligible_count || 0,
      })

      // Start polling
      pollRef.current = setInterval(async () => {
        try {
          const prRes = await fetch(`/api/validation/circuit/runs/${runId}/progress`)
          if (!prRes.ok) { if (pollRef.current) clearInterval(pollRef.current); return }
          const pr = safeApiResponse(await prRes.json(), EMPTY_PROGRESS)
          if (pr.phase === 'completed') {
            if (pollRef.current) clearInterval(pollRef.current)
            pollRef.current = null
            setVp(p => p ? { ...p, phase: 'completed', pass_count: pr.pass_count, warning_count: pr.warning_count, hard_fail_count: pr.hard_fail_count, eligible_for_dual_review_count: pr.eligible_for_dual_review_count, blocked_candidate_count: pr.blocked_candidate_count, failed_candidate_count: pr.failed_candidate_count, candidate_progress: pr.candidate_progress, elapsed_seconds: pr.elapsed_seconds, completed_candidate_count: pr.completed_candidate_count, completed_rule_execution_count: pr.completed_rule_execution_count, expected_rule_execution_count: pr.expected_rule_execution_count, enabled_rule_count: pr.enabled_rule_count, original_run_id: pr.original_run_id, original_hard_fails: pr.original_hard_fails } : null)
            if (autoRef.current && (pr.eligible_for_dual_review_count || 0) > 0) {
              const eligible = (pr.candidate_progress || []).filter((cp: CandidateProgressItem) => cp.eligible_for_dual_review).map((cp: CandidateProgressItem) => cp.circuit_id)
              try {
                await fetch('/api/validation/circuit/selection/dual-review', {
                  method: 'POST', headers: { 'Content-Type': 'application/json' },
                  body: JSON.stringify({ circuit_ids: eligible, force_review: false }),
                })
              } catch { /* silent */ }
            }
          } else if (pr.phase === 'failed' || pr.status === 'failed' || pr.status === 'cancelled') {
            if (pollRef.current) clearInterval(pollRef.current)
            pollRef.current = null
            setVp(p => p ? { ...p, phase: 'failed', elapsed_seconds: pr.elapsed_seconds } : null)
          } else {
            setVp(p => p ? { ...p, completed_candidate_count: pr.completed_candidate_count, pass_count: pr.pass_count, warning_count: pr.warning_count, hard_fail_count: pr.hard_fail_count, eligible_for_dual_review_count: pr.eligible_for_dual_review_count, failed_candidate_count: pr.failed_candidate_count, candidate_progress: pr.candidate_progress, elapsed_seconds: pr.elapsed_seconds, completed_rule_execution_count: pr.completed_rule_execution_count, expected_rule_execution_count: pr.expected_rule_execution_count, enabled_rule_count: pr.enabled_rule_count, original_run_id: pr.original_run_id, original_hard_fails: pr.original_hard_fails } : null)
          }
        } catch { if (pollRef.current) clearInterval(pollRef.current); pollRef.current = null }
      }, 2000)
    } catch (e: unknown) {
      setMessage(e instanceof Error ? e.message : '提交失败')
      setTimeout(() => setMessage(null), 5000)
    } finally {
      setLoading(false)
    }
  }

  const handleSendDualReview = async (eligibleIds: string[]) => {
    try {
      setMessage('正在送入双模型审核...')
      await fetch('/api/validation/circuit/selection/dual-review', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ circuit_ids: eligibleIds, force_review: false }),
      })
      setMessage('已送入双模型审核')
      setTimeout(() => setMessage(null), 3000)
    } catch {
      setMessage('送入双审失败')
      setTimeout(() => setMessage(null), 3000)
    }
  }

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', padding: '0 8px' }}>
      {message && (
        <div style={{
          marginBottom: 8, padding: '8px 12px', borderRadius: 'var(--radius)',
          fontSize: 13, flexShrink: 0,
          background: message.includes('失败') ? '#fff2f0' : '#f6ffed',
          color: message.includes('失败') ? 'var(--danger)' : 'var(--success)',
          border: `1px solid ${message.includes('失败') ? '#ffccc7' : '#b7eb8f'}`,
        }}>
          {message}
        </div>
      )}

      <div style={{ flex: 1, overflow: 'hidden' }}>
        <CircuitSelector
          granularityLevel={granularityLevel}
          selected={selected}
          onSelectionChange={setSelected}
        />
      </div>

      <div className="vr-action-bar" style={{ flexShrink: 0, marginTop: 8 }}>
        <span>已选 {selected.size} 个回路</span>
        <div className="vr-action-sep" />
        <button
          className="btn btn-primary"
          onClick={handleStart}
          disabled={loading || selected.size === 0}
        >
          <Play size={14} style={{ marginRight: 4 }} />
          {loading ? '提交中...' : '启动规则校验'}
        </button>
        <button
          className="btn btn-sm btn-outline"
          onClick={() => setSelected(new Set())}
          disabled={loading}
        >
          清除选择
        </button>
      </div>

      {/* ── Progress modal ─────────────────────────────────────────────── */}
      {vp?.open && (
        <div className="vw-modal-overlay" onClick={() => { if (vp.phase !== 'running') setVp(null) }}>
          <div className="vw-modal vw-modal-wide" onClick={e => e.stopPropagation()}>
            <div className="vw-modal-hd">
              <h3>🛡 规则校验</h3>
              <span className="badge">{PHASE_LABELS[vp.phase] || vp.phase}</span>
              <span className="vw-modal-meta">Run: {vp.runId.slice(0, 8)}</span>
              {vp.phase !== 'running' && <button className="vw-modal-close" onClick={() => setVp(null)}>✕</button>}
            </div>

            <div className="vw-modal-body">
              <div className="vpm-cards">
                <div className="vpm-card"><span className="vpm-card-num">{vp.selected_candidate_count}</span><span>候选回路</span></div>
                <div className="vpm-card vpm-card-green"><span className="vpm-card-num">{vp.pass_count}</span><span>通过</span></div>
                <div className="vpm-card vpm-card-amber"><span className="vpm-card-num">{vp.warning_count}</span><span>警告</span></div>
                <div className="vpm-card vpm-card-red"><span className="vpm-card-num">{vp.hard_fail_count}</span><span>阻塞</span></div>
                <div className="vpm-card vpm-card-blue"><span className="vpm-card-num">{vp.eligible_for_dual_review_count}</span><span>可双审</span></div>
              </div>

              <div className="vpm-progress-section">
                <span>回路: {vp.completed_candidate_count}/{vp.selected_candidate_count}</span>
                <div className="vpm-bar">
                  <div className="vpm-bar-fill" style={{ width: `${vp.selected_candidate_count > 0 ? (vp.completed_candidate_count / vp.selected_candidate_count) * 100 : 0}%` }} />
                </div>
                <span className="vpm-progress-detail">
                  规则执行: {vp.completed_rule_execution_count}/{vp.expected_rule_execution_count} | 启用: {vp.enabled_rule_count}条 | 耗时: {Math.round(vp.elapsed_seconds)}s
                </span>
              </div>

              {vp.phase === 'running' && (
                <label className="vpm-checkbox">
                  <input type="checkbox" checked={autoHandoff} onChange={() => setAutoHandoff(!autoHandoff)} />
                  规则通过后自动送入双模型审核
                </label>
              )}

              {(vp.candidate_progress || []).length > 0 && (
                <div className="vpm-table-wrap">
                  <table className="vr-table">
                    <thead><tr><th>#</th><th>回路名称</th><th>规则</th><th>通过</th><th>警告</th><th>阻塞</th><th>状态</th></tr></thead>
                    <tbody>
                      {vp.candidate_progress.map((cp, i) => (
                        <tr key={cp.circuit_id} className={`vr-row vpm-row-${cp.status}`}>
                          <td>{i + 1}</td>
                          <td title={cp.circuit_name}>{cp.circuit_name?.slice(0, 30) || cp.circuit_id.slice(0, 12)}</td>
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

              {vp.original_run_id && vp.original_hard_fails !== undefined && (
                <div style={{ marginTop: 12, padding: 12, borderRadius: 8, border: '1px solid var(--border)', background: 'var(--bg-muted)' }}>
                  <h4 style={{ fontSize: 13, fontWeight: 600, marginBottom: 8 }}>重新校验结果对比</h4>
                  <div style={{ fontSize: 13, marginBottom: 4 }}>
                    原阻塞数: <strong>{vp.original_hard_fails}</strong> → 当前: <strong>{vp.hard_fail_count}</strong>
                  </div>
                  <div style={{ fontSize: 13, color: 'var(--success)' }}>
                    已解决: <strong>{vp.original_hard_fails - vp.hard_fail_count}</strong>
                  </div>
                </div>
              )}
            </div>

            <div className="vw-modal-ft">
              {vp.phase === 'running' && (
                <button className="btn btn-sm" onClick={() => {
                  if (pollRef.current) clearInterval(pollRef.current)
                  pollRef.current = null
                  setVp(null)
                }}>后台运行</button>
              )}
              {vp.phase === 'completed' && (
                <>
                  <span className="vpm-ft-info">
                    通过 {vp.pass_count} | 阻塞 {vp.hard_fail_count} | 可双审 {vp.eligible_for_dual_review_count}
                  </span>
                  {vp.eligible_for_dual_review_count > 0 && (
                    <button className="btn btn-sm btn-primary"
                      onClick={() => {
                        const eligible = vp.candidate_progress.filter(cp => cp.eligible_for_dual_review).map(c => c.circuit_id)
                        handleSendDualReview(eligible)
                      }}>
                      <Zap size={14} /> 送入双模型审核({vp.eligible_for_dual_review_count})
                    </button>
                  )}
                  {vp.failed_candidate_count > 0 && (
                    <button className="btn btn-sm btn-outline"
                      onClick={async () => {
                        const failed = vp.candidate_progress.filter(cp => cp.status === 'failed').map(cp => cp.circuit_id)
                        if (failed.length === 0) return
                        try {
                          await fetch('/api/validation/circuit/selection/rule-validate', {
                            method: 'POST', headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ circuit_ids: failed, force_revalidate: true }),
                          })
                          setVp(null)
                          setMessage('已重新提交失败项')
                          setTimeout(() => setMessage(null), 3000)
                        } catch { /* silent */ }
                      }}>
                      <RefreshCw size={14} /> 重试失败项({vp.failed_candidate_count})
                    </button>
                  )}
                  <button className="btn btn-sm btn-outline"
                    onClick={async () => {
                      const totalGaps = vp.candidate_progress.reduce(
                        (sum, cp) => sum + (12 - cp.completed_rule_count || 0), 0
                      )
                      const prevVp = { ...vp }
                      setVp(null)
                      setMessage(`正在启动数据增强 (${totalGaps} 个缺失字段)...`)
                      try {
                        const enhanceResp = await fetch('/api/validation/circuit/selection/enhance', {
                          method: 'POST',
                          headers: { 'Content-Type': 'application/json' },
                          body: JSON.stringify({ run_id: prevVp.runId, tier2_enabled: true }),
                        })
                        if (!enhanceResp.ok) throw new Error(`API: ${enhanceResp.status}`)
                        const enhanceData = await enhanceResp.json()
                        setMessage(`✅ 数据增强完成: 自动修复 ${enhanceData.tier1_fixes?.total || 0} 项, LLM建议 ${enhanceData.tier2_suggestions?.total || 0} 条`)
                        setTimeout(() => setMessage(null), 8000)
                      } catch (e: unknown) {
                        setMessage(`增强失败: ${e instanceof Error ? e.message : '未知错误'}`)
                        setTimeout(() => setMessage(null), 5000)
                      }
                    }}>
                    <Sparkles size={14} style={{ marginRight: 4 }} />
                    数据增强({vp.selected_candidate_count})
                  </button>
                  <button className="btn btn-sm" onClick={() => setVp(null)}>关闭</button>
                </>
              )}
              {vp.phase === 'failed' && (
                <>
                  <span className="vpm-ft-error">规则校验异常</span>
                  <button className="btn btn-sm" onClick={() => setVp(null)}>关闭</button>
                </>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

// ── Main Component ─────────────────────────────────────────────────────────

export function RuleValidationTab({ granularityLevel }: Props) {
  const [subTab, setSubTab] = useState<'history' | 'start'>('history')

  // ── History state ──────────────────────────────────────────────────────
  const [runs, setRuns] = useState<RunSummary[]>([])
  const [runsLoading, setRunsLoading] = useState(true)
  const [runsError, setRunsError] = useState<string | null>(null)
  const [runsTotal, setRunsTotal] = useState(0)
  const [runsPage, setRunsPage] = useState(0)
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null)
  const [runProgress, setRunProgress] = useState<RunProgress | null>(null)
  const [progressLoading, setProgressLoading] = useState(false)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const runsTotalPages = Math.max(1, Math.ceil(runsTotal / RUNS_PAGE_SIZE))

  const fetchRuns = useCallback(async () => {
    setRunsLoading(true)
    setRunsError(null)
    try {
      const params = new URLSearchParams()
      params.set('limit', String(RUNS_PAGE_SIZE))
      params.set('offset', String(runsPage * RUNS_PAGE_SIZE))
      if (granularityLevel) params.set('granularity_level', granularityLevel)
      const res = await fetch(`/api/validation/circuit/runs?${params}`)
      if (!res.ok) throw new Error(`API错误: ${res.status}`)
      const data = await res.json()
      const runList = Array.isArray(data) ? data : data.items || []
      setRuns(runList)
      setRunsTotal(Array.isArray(data) ? data.length : data.total || 0)
    } catch (e: unknown) {
      setRunsError(e instanceof Error ? e.message : '加载失败')
    } finally {
      setRunsLoading(false)
    }
  }, [granularityLevel, runsPage])

  useEffect(() => { fetchRuns() }, [fetchRuns])

  const fetchProgress = useCallback(async (runId: string) => {
    setProgressLoading(true)
    setRunProgress(null)
    try {
      const res = await fetch(`/api/validation/circuit/runs/${runId}/progress`)
      if (!res.ok) throw new Error(`API错误: ${res.status}`)
      const data = await res.json()
      const pr = safeApiResponse(data, EMPTY_PROGRESS)
      setRunProgress({ ...pr, run_id: runId })

      if (pr.phase === 'running' || pr.status === 'running') {
        if (pollRef.current) clearInterval(pollRef.current)
        pollRef.current = setInterval(async () => {
          try {
            const prRes = await fetch(`/api/validation/circuit/runs/${runId}/progress`)
            if (!prRes.ok) { if (pollRef.current) clearInterval(pollRef.current); return }
            const prRaw = await prRes.json()
            const pr2 = safeApiResponse(prRaw, EMPTY_PROGRESS)
            setRunProgress(prev => prev ? { ...prev, ...pr2, run_id: runId } : { ...pr2, run_id: runId })
            if (pr2.phase === 'completed' || pr2.phase === 'failed' || pr2.status === 'failed' || pr2.status === 'cancelled') {
              if (pollRef.current) clearInterval(pollRef.current)
              pollRef.current = null
              fetchRuns()
            }
          } catch { if (pollRef.current) clearInterval(pollRef.current); pollRef.current = null }
        }, 2000)
      }
    } catch (e: unknown) {
      setRunProgress(null)
    } finally {
      setProgressLoading(false)
    }
  }, [fetchRuns])

  useEffect(() => {
    return () => { if (pollRef.current) clearInterval(pollRef.current) }
  }, [])

  const handleRunClick = (runId: string) => {
    setSelectedRunId(runId)
    fetchProgress(runId)
  }

  // ── Render ─────────────────────────────────────────────────────────────

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
            开始校验
          </button>
        </div>
      </div>

      {/* Sub-tab content */}
      <div style={{ flex: 1, overflow: 'hidden' }}>
        {subTab === 'history' && (
          <RunHistory
            granularityLevel={granularityLevel}
            runs={runs} runsLoading={runsLoading} runsError={runsError}
            runsTotal={runsTotal} runsPage={runsPage} runsTotalPages={runsTotalPages}
            onRunsPageChange={setRunsPage} fetchRuns={fetchRuns}
            selectedRunId={selectedRunId} onRunClick={handleRunClick}
            runProgress={runProgress} progressLoading={progressLoading}
            onRetryProgress={() => selectedRunId && fetchProgress(selectedRunId)}
          />
        )}
        {subTab === 'start' && (
          <StartValidation granularityLevel={granularityLevel} />
        )}
      </div>
    </div>
  )
}
