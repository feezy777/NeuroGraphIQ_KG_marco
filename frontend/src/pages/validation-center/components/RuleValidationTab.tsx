import { useState, useEffect, useCallback, useRef } from 'react'
import { RefreshCw, Zap, ChevronRight, FileText } from 'lucide-react'

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

function statusBadge(status: string): { color: string; label: string } {
  const colors: Record<string, string> = {
    created: '#86909c', queued: '#2f54eb', running: '#2f54eb',
    completed: '#52c41a', failed: '#ff4d4f', cancelled: '#86909c',
  }
  return { color: colors[status] || '#86909c', label: STATUS_LABELS[status] || status }
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

// ── Main Component ─────────────────────────────────────────────────────────

export function RuleValidationTab({ granularityLevel }: Props) {
  const [runs, setRuns] = useState<RunSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null)
  const [runProgress, setRunProgress] = useState<RunProgress | null>(null)
  const [progressLoading, setProgressLoading] = useState(false)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // Fetch runs on mount
  const fetchRuns = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const params = new URLSearchParams()
      params.set('limit', '50')
      if (granularityLevel) params.set('granularity_level', granularityLevel)
      const res = await fetch(`/api/validation/circuit/runs?${params}`)
      if (!res.ok) throw new Error(`API错误: ${res.status}`)
      const data = await res.json()
      const runList = Array.isArray(data) ? data : data.items || []
      setRuns(runList)

      // Auto-select running run
      const activeRun = runList.find((r: RunSummary) => r.status === 'running' || r.rule_validation_status === 'running')
      if (activeRun) {
        setSelectedRunId(activeRun.id)
        fetchProgress(activeRun.id)
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : '加载失败')
    } finally {
      setLoading(false)
    }
  }, [granularityLevel])

  useEffect(() => { fetchRuns() }, [fetchRuns])

  // Fetch progress for a run
  const fetchProgress = useCallback(async (runId: string) => {
    setProgressLoading(true)
    setRunProgress(null)
    try {
      const res = await fetch(`/api/validation/circuit/runs/${runId}/progress`)
      if (!res.ok) throw new Error(`API错误: ${res.status}`)
      const data = await res.json()
      const pr = safeApiResponse(data, EMPTY_PROGRESS)
      setRunProgress({ ...pr, run_id: runId })

      // Start polling if running
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
              fetchRuns() // Refresh run list on completion
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
    return () => {
      if (pollRef.current) clearInterval(pollRef.current)
    }
  }, [])

  // Handle run click
  const handleRunClick = (runId: string) => {
    setSelectedRunId(runId)
    fetchProgress(runId)
  }

  // ── Render ───────────────────────────────────────────────────────────────

  if (loading && runs.length === 0) {
    return <div className="vr-panel"><div className="vw-empty-state"><p>加载中...</p></div></div>
  }
  if (error) {
    return (
      <div className="vr-panel">
        <div className="vw-error">{error}</div>
        <button className="btn btn-sm" onClick={fetchRuns} style={{ margin: 8 }}>重试</button>
      </div>
    )
  }

  return (
    <div className="vr-panel" style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      {/* Header */}
      <div className="vr-header">
        <h3 style={{ margin: 0, fontSize: 15, fontWeight: 600 }}>规则校验运行记录</h3>
        <span className="vr-total">共 {runs.length} 条</span>
        <button className="btn btn-sm btn-outline" onClick={fetchRuns} disabled={loading} style={{ marginLeft: 8 }}>
          <RefreshCw size={12} style={{ marginRight: 4 }} />
          刷新
        </button>
      </div>

      <div style={{ flex: 1, display: 'flex', flexDirection: 'row', overflow: 'hidden' }}>
        {/* Runs list */}
        <div style={{ width: 320, borderRight: '1px solid var(--border)', overflow: 'auto', flexShrink: 0 }}>
          {runs.length === 0 ? (
            <div className="vw-empty-state" style={{ padding: 24, textAlign: 'center' }}>
              <p style={{ color: 'var(--text-muted)', fontSize: 13 }}>暂无规则校验运行记录。</p>
            </div>
          ) : (
            runs.map(run => {
              const { color: statusColor } = statusBadge(run.status)
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

              {/* Before/After comparison for revalidation */}
              {runProgress.original_run_id && runProgress.original_hard_fails !== undefined && (
                <div style={{
                  marginTop: 12, padding: 12, borderRadius: 8,
                  border: '1px solid var(--border)', background: 'var(--bg-muted)',
                }}>
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

              {/* Candidate result table */}
              {runProgress.candidate_progress && runProgress.candidate_progress.length > 0 && (
                <div className="vpm-table-wrap" style={{ marginTop: 12 }}>
                  <table className="vr-table">
                    <thead>
                      <tr>
                        <th>#</th><th>回路名称</th><th>规则</th><th>通过</th><th>警告</th><th>阻塞</th><th>状态</th>
                      </tr>
                    </thead>
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

              {/* Phase indicator */}
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
              <button className="btn btn-sm" onClick={() => selectedRunId && fetchProgress(selectedRunId)}>重试</button>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
