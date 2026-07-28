import { useState, useEffect, useCallback } from 'react'
import { Zap, CheckCircle, XCircle, AlertTriangle, RefreshCw, FileSearch } from 'lucide-react'

// ── Types ──────────────────────────────────────────────────────────────────

interface RuleDiagnostic {
  rule_result_id?: string
  rule_code: string
  problem_summary?: string
  root_cause?: string
  affected_fields?: string[]
  source_data_conflict?: string
  recommended_action?: string
  repairability?: string
  confidence?: number
  uncertainties?: string[]
}

interface SuggestedChange {
  id?: string
  rule_result_id?: string
  field_path: string
  original_value: unknown
  suggested_value: unknown
  reason?: string
  correction_type?: string
  repairability?: string
  authoritative_source?: string
  safe_to_apply_after_verification?: boolean
  confidence?: number
}

interface CorrectionItem {
  id: string
  circuit_id: string
  rule_code: string
  field_path: string
  original_value: unknown
  suggested_value: unknown
  approved_value: unknown
  correction_type: string
  repairability: string
  approval_status: string
  deterministic_validation_status: string
  suggestion_source: string
  suggestion_confidence?: number
  authoritative_source?: string
  revalidation_status: string
  created_at: string | null
}

interface CircuitDiagnosis {
  circuit_id: string
  circuit_name: string
  status: string
  overall_repairability: string
  rule_diagnostics: RuleDiagnostic[]
  suggested_changes: SuggestedChange[]
  revalidation_recommended: boolean
  reextraction_recommended: boolean
  rejection_recommended: boolean
  uncertainties?: string[]
  corrections_created?: number
  corrections?: Array<{ id: string; field_path: string; repairability: string; deterministic_status: string }>
}

interface DeepSeekFixResponse {
  total: number
  diagnosed_count: number
  diagnosed_circuit_ids: string[]
  total_corrections_created: number
  results: CircuitDiagnosis[]
}

interface Props {
  circuitIds: string[]
  circuitNames: string[]
  onClose: () => void
  onRevalidationComplete?: () => void
}

// ── Helpers ────────────────────────────────────────────────────────────────

const REPAIRABILITY_LABELS: Record<string, string> = {
  auto_safe: '可自动修复',
  manual_required: '需人工审核',
  reextract_required: '需重新提取',
  unrecoverable: '不可恢复',
}

const REPAIRABILITY_COLORS: Record<string, string> = {
  auto_safe: '#52c41a',
  manual_required: '#faad14',
  reextract_required: '#ff4d4f',
  unrecoverable: '#86909c',
}

const CORRECTION_TYPE_LABELS: Record<string, string> = {
  metadata: '元数据',
  structural: '结构性',
  reextract: '重新提取',
}

function repairabilityBadge(rep: string): React.ReactNode {
  const color = REPAIRABILITY_COLORS[rep] || '#86909c'
  const label = REPAIRABILITY_LABELS[rep] || rep
  return (
    <span style={{
      display: 'inline-block', padding: '1px 6px', borderRadius: 8,
      fontSize: 11, fontWeight: 600,
      background: color + '1a', color, border: `1px solid ${color}44`,
    }}>
      {label}
    </span>
  )
}

function statusBadge(status: string, activeLabel?: string): React.ReactNode {
  const colorMap: Record<string, string> = {
    proposed: '#faad14', approved: '#52c41a', rejected: '#ff4d4f',
    pending: '#faad14', verified: '#52c41a', pending_human: '#faad14',
    skipped: '#86909c', queued: '#2f54eb', not_started: '#86909c',
  }
  const labelMap: Record<string, string> = {
    proposed: '已提议', approved: '已批准', rejected: '已拒绝',
    pending: '待处理', verified: '已验证', pending_human: '待人工',
    skipped: '已跳过', queued: '排队中', not_started: '未开始',
  }
  const color = colorMap[status] || '#86909c'
  const label = activeLabel || labelMap[status] || status
  return (
    <span style={{
      display: 'inline-block', padding: '1px 6px', borderRadius: 8,
      fontSize: 11, fontWeight: 600,
      background: color + '1a', color, border: `1px solid ${color}44`,
    }}>
      {label}
    </span>
  )
}

function formatValue(val: unknown): string {
  if (val === null || val === undefined) return '—'
  if (typeof val === 'object') return JSON.stringify(val, null, 1)
  return String(val)
}

// ── Main Component ─────────────────────────────────────────────────────────

export function RepairModal({ circuitIds, circuitNames, onClose, onRevalidationComplete }: Props) {
  const safeCircuitIds = Array.isArray(circuitIds) ? circuitIds : []
  const safeCircuitNames = Array.isArray(circuitNames) ? circuitNames : []
  const [activeTab, setActiveTab] = useState<'diagnosis' | 'corrections' | 'revalidation'>('diagnosis')
  const [loading, setLoading] = useState(true)
  const [diagnosisData, setDiagnosisData] = useState<DeepSeekFixResponse | null>(null)
  const [correctionsMap, setCorrectionsMap] = useState<Record<string, CorrectionItem[]>>({})
  const [error, setError] = useState<string | null>(null)
  const [actionMsg, setActionMsg] = useState<string | null>(null)
  const [selectedCircuitIdx, setSelectedCircuitIdx] = useState(0)
  const [selectedCorrections, setSelectedCorrections] = useState<Set<string>>(new Set())
  const [revalidationStatus, setRevalidationStatus] = useState<string | null>(null)
  const [revalidationRunId, setRevalidationRunId] = useState<string | null>(null)

  if (safeCircuitIds.length === 0) return null
  const currentCircuitId = safeCircuitIds[selectedCircuitIdx]
  const currentCircuitName = safeCircuitNames[selectedCircuitIdx] || currentCircuitId?.slice(0, 12) || ''
  const currentDiagnosis = diagnosisData?.results?.find(r => r.circuit_id === currentCircuitId)
  const currentCorrections = correctionsMap[currentCircuitId] || []

  // ── Load diagnosis data ──────────────────────────────────────────────────

  const runDiagnosis = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const resp = await fetch('/api/validation/circuit/selection/deepseek-fix', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ circuit_ids: circuitIds, force_refresh: false }),
      })
      if (!resp.ok) throw new Error(`API错误: ${resp.status}`)
      const data: DeepSeekFixResponse = await resp.json()
      setDiagnosisData(data)
      return data
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : '诊断请求失败')
      return null
    } finally {
      setLoading(false)
    }
  }, [circuitIds])

  // ── Load corrections from DB ────────────────────────────────────────────

  const loadCorrections = useCallback(async (circuitId: string) => {
    try {
      const resp = await fetch(`/api/validation/circuit/candidates/${circuitId}/corrections`)
      if (!resp.ok) return
      const data = await resp.json()
      setCorrectionsMap(prev => ({ ...prev, [circuitId]: data.items || [] }))
    } catch { /* silent */ }
  }, [])

  // ── Init: load corrections for all circuits, run diagnosis ──────────────

  useEffect(() => {
    runDiagnosis()
    circuitIds.forEach(id => loadCorrections(id))
  }, [circuitIds, runDiagnosis, loadCorrections])

  // Reload corrections when switching circuit
  useEffect(() => {
    if (currentCircuitId && !correctionsMap[currentCircuitId]) {
      loadCorrections(currentCircuitId)
    }
  }, [currentCircuitId, correctionsMap, loadCorrections])

  // Refresh all corrections
  const refreshCorrections = useCallback(() => {
    circuitIds.forEach(id => loadCorrections(id))
  }, [circuitIds, loadCorrections])

  // ── Approve/Reject corrections ──────────────────────────────────────────

  const handleApproveCorrection = async (correctionId: string, suggestedValue?: unknown) => {
    setActionMsg('正在批准...')
    try {
      const resp = await fetch(`/api/validation/circuit/corrections/${correctionId}/approve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          approved_value: suggestedValue,
          reviewer: 'admin',
          reason: '已审核批准',
        }),
      })
      if (!resp.ok) throw new Error(`API错误: ${resp.status}`)
      setActionMsg('已批准')
      refreshCorrections()
      setTimeout(() => setActionMsg(null), 2000)
    } catch (e: unknown) {
      setActionMsg(e instanceof Error ? e.message : '批准失败')
      setTimeout(() => setActionMsg(null), 3000)
    }
  }

  const handleRejectCorrection = async (correctionId: string) => {
    setActionMsg('正在拒绝...')
    try {
      const resp = await fetch(`/api/validation/circuit/corrections/${correctionId}/reject`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      })
      if (!resp.ok) throw new Error(`API错误: ${resp.status}`)
      setActionMsg('已拒绝')
      refreshCorrections()
      setTimeout(() => setActionMsg(null), 2000)
    } catch (e: unknown) {
      setActionMsg(e instanceof Error ? e.message : '拒绝失败')
      setTimeout(() => setActionMsg(null), 3000)
    }
  }

  const handleBatchApprove = async () => {
    const toApprove = currentCorrections.filter(
      c => selectedCorrections.has(c.id) && c.approval_status === 'proposed',
    )
    if (toApprove.length === 0) {
      setActionMsg('没有可批准的提议修正')
      setTimeout(() => setActionMsg(null), 2000)
      return
    }
    setActionMsg(`正在批量批准 ${toApprove.length} 项...`)
    for (const c of toApprove) {
      await handleApproveCorrection(c.id, c.suggested_value)
    }
    setSelectedCorrections(new Set())
    setActionMsg(`已批准 ${toApprove.length} 项`)
    setTimeout(() => setActionMsg(null), 3000)
  }

  const handleBatchReject = async () => {
    const toReject = currentCorrections.filter(
      c => selectedCorrections.has(c.id) && c.approval_status === 'proposed',
    )
    if (toReject.length === 0) {
      setActionMsg('没有可拒绝的提议修正')
      setTimeout(() => setActionMsg(null), 2000)
      return
    }
    setActionMsg(`正在批量拒绝 ${toReject.length} 项...`)
    for (const c of toReject) {
      await handleRejectCorrection(c.id)
    }
    setSelectedCorrections(new Set())
    setActionMsg(`已拒绝 ${toReject.length} 项`)
    setTimeout(() => setActionMsg(null), 3000)
  }

  // ── Revalidation ────────────────────────────────────────────────────────

  const handleRevalidate = async () => {
    setRevalidationStatus('queued')
    try {
      const resp = await fetch(`/api/validation/circuit/candidates/${currentCircuitId}/revalidate`, {
        method: 'POST',
      })
      if (!resp.ok) throw new Error(`API错误: ${resp.status}`)
      const data = await resp.json()
      setRevalidationRunId(data.internal_run_id)
      setRevalidationStatus('running')
      onRevalidationComplete?.()

      // Poll for completion
      const pollInterval = setInterval(async () => {
        try {
          const prRes = await fetch(`/api/validation/circuit/runs/${data.internal_run_id}/progress`)
          if (!prRes.ok) {
            clearInterval(pollInterval)
            setRevalidationStatus('error')
            return
          }
          const pr = await prRes.json()
          if (pr.phase === 'completed') {
            clearInterval(pollInterval)
            setRevalidationStatus('completed')
          } else if (pr.phase === 'failed' || pr.status === 'failed' || pr.status === 'cancelled') {
            clearInterval(pollInterval)
            setRevalidationStatus('failed')
          }
        } catch {
          clearInterval(pollInterval)
          setRevalidationStatus('error')
        }
      }, 2000)
    } catch (e: unknown) {
      setRevalidationStatus('error')
      setActionMsg(e instanceof Error ? e.message : '重新验证失败')
      setTimeout(() => setActionMsg(null), 3000)
    }
  }

  // ── Toggle correction selection ─────────────────────────────────────────

  const toggleCorrection = (id: string) => {
    setSelectedCorrections(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id); else next.add(id)
      return next
    })
  }

  const toggleSelectAllCorrections = () => {
    const proposed = currentCorrections.filter(c => c.approval_status === 'proposed')
    if (selectedCorrections.size === proposed.length) {
      setSelectedCorrections(new Set())
    } else {
      setSelectedCorrections(new Set(proposed.map(c => c.id)))
    }
  }

  // ── Compute hard-fail count from diagnosis ──────────────────────────────

  const hardFailCount = diagnosisData?.results?.filter(r => r.status === 'analyzed')?.length || 0

  // ── Render ──────────────────────────────────────────────────────────────

  return (
    <div className="vw-modal-overlay" onClick={onClose}>
      <div className="vw-modal vw-modal-wide" onClick={e => e.stopPropagation()} style={{ maxHeight: '90vh' }}>
        {/* Header */}
        <div className="vw-modal-hd">
          <h3>
            <FileSearch size={18} style={{ marginRight: 6, verticalAlign: 'middle' }} />
            回路诊断与修复
          </h3>
          <span className="badge">DeepSeek</span>
          <span className="vw-modal-meta">
            {hardFailCount} 条阻塞 | 共计 {diagnosisData?.total_corrections_created || 0} 条修正建议
          </span>
          <button className="vw-modal-close" onClick={onClose}>✕</button>
        </div>

        {/* Circuit selector */}
        {safeCircuitIds.length > 1 && (
          <div style={{
            padding: '8px 24px', borderBottom: '1px solid var(--border)',
            display: 'flex', gap: 6, flexWrap: 'wrap', background: 'var(--bg-muted)',
          }}>
            {safeCircuitIds.map((id, i) => (
              <button
                key={id}
                className={`btn btn-sm ${i === selectedCircuitIdx ? 'btn-primary' : 'btn-outline'}`}
                onClick={() => { setSelectedCircuitIdx(i); setSelectedCorrections(new Set()); setRevalidationStatus(null) }}
              >
                {safeCircuitNames[i]?.slice(0, 20) || id.slice(0, 8)}
              </button>
            ))}
          </div>
        )}

        {/* Tabs */}
        <div className="vw-modal-body" style={{ padding: 0 }}>
          <div className="vr-header" style={{ padding: '8px 24px 0' }}>
            <div className="vr-tabs">
              <button
                className={`vr-tab${activeTab === 'diagnosis' ? ' active' : ''}`}
                onClick={() => setActiveTab('diagnosis')}
              >
                诊断分析 ({currentDiagnosis?.rule_diagnostics?.length || 0})
              </button>
              <button
                className={`vr-tab${activeTab === 'corrections' ? ' active' : ''}`}
                onClick={() => setActiveTab('corrections')}
              >
                修正建议 ({currentCorrections.length})
              </button>
              <button
                className={`vr-tab${activeTab === 'revalidation' ? ' active' : ''}`}
                onClick={() => setActiveTab('revalidation')}
              >
                重新验证
              </button>
            </div>
          </div>

          {/* Action message */}
          {actionMsg && (
            <div style={{
              padding: '6px 24px', fontSize: 13,
              color: actionMsg.includes('失败') ? 'var(--danger)' : 'var(--success)',
              background: actionMsg.includes('失败') ? '#fff2f0' : '#f6ffed',
              borderBottom: '1px solid var(--border)',
            }}>
              {actionMsg}
            </div>
          )}

          {/* Tab content */}
          <div style={{ padding: '16px 24px', overflow: 'auto', maxHeight: '55vh' }}>
            {/* ═══ Diagnosis Tab ═══ */}
            {activeTab === 'diagnosis' && (
              <div>
                {loading ? (
                  <div style={{ textAlign: 'center', padding: 40, color: 'var(--text-muted)' }}>
                    <RefreshCw size={24} style={{ animation: 'spin 1s linear infinite', marginBottom: 12 }} />
                    <p>DeepSeek 正在诊断阻塞原因...</p>
                  </div>
                ) : error ? (
                  <div style={{ textAlign: 'center', padding: 40 }}>
                    <AlertTriangle size={24} color="var(--danger)" style={{ marginBottom: 12 }} />
                    <p style={{ color: 'var(--danger)' }}>{error}</p>
                    <button className="btn btn-sm btn-primary" onClick={runDiagnosis} style={{ marginTop: 12 }}>
                      重试诊断
                    </button>
                  </div>
                ) : currentDiagnosis ? (
                  <div>
                    {/* Overall repairability */}
                    <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 16 }}>
                      <strong style={{ fontSize: 14 }}>整体可修复性:</strong>
                      {repairabilityBadge(currentDiagnosis.overall_repairability || 'manual_required')}
                      {currentDiagnosis.reextraction_recommended && (
                        <span className="badge badge-error">建议重新提取</span>
                      )}
                      {currentDiagnosis.rejection_recommended && (
                        <span className="badge badge-error">建议拒绝</span>
                      )}
                    </div>

                    {/* Overall diagnosis text if available */}
                    {currentDiagnosis.uncertainties && currentDiagnosis.uncertainties.length > 0 && (
                      <div style={{
                        marginBottom: 16, padding: 12, borderRadius: 8,
                        background: '#fffbe6', border: '1px solid #ffe58f', fontSize: 13,
                      }}>
                        <strong>不确定性:</strong>
                        <ul style={{ margin: '8px 0 0', paddingLeft: 20 }}>
                          {currentDiagnosis.uncertainties.map((u, i) => (
                            <li key={i}>{u}</li>
                          ))}
                        </ul>
                      </div>
                    )}

                    {/* Rule diagnostics */}
                    <h4 style={{ fontSize: 14, marginBottom: 12 }}>
                      规则诊断 ({currentDiagnosis.rule_diagnostics.length} 条)
                    </h4>
                    {currentDiagnosis.rule_diagnostics.length === 0 ? (
                      <p style={{ color: 'var(--text-muted)', fontSize: 13 }}>
                        暂无详细规则诊断信息
                      </p>
                    ) : (
                      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                        {currentDiagnosis.rule_diagnostics.map((rd, i) => (
                          <div key={i} style={{
                            padding: 12, borderRadius: 8,
                            border: '1px solid var(--border)',
                            background: 'var(--bg-card)',
                          }}>
                            <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 8 }}>
                              <span className="badge badge-blocked">{rd.rule_code}</span>
                              {repairabilityBadge(rd.repairability || 'manual_required')}
                              {rd.confidence !== undefined && (
                                <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                                  置信度: {(rd.confidence * 100).toFixed(0)}%
                                </span>
                              )}
                            </div>
                            {rd.problem_summary && (
                              <p style={{ fontSize: 13, marginBottom: 4 }}>
                                <strong>问题:</strong> {rd.problem_summary}
                              </p>
                            )}
                            {rd.root_cause && (
                              <p style={{ fontSize: 13, marginBottom: 4 }}>
                                <strong>根因:</strong> {rd.root_cause}
                              </p>
                            )}
                            {rd.affected_fields && rd.affected_fields.length > 0 && (
                              <p style={{ fontSize: 13, marginBottom: 4 }}>
                                <strong>影响字段:</strong> {rd.affected_fields.join(', ')}
                              </p>
                            )}
                            {rd.recommended_action && (
                              <p style={{ fontSize: 13, marginBottom: 4 }}>
                                <strong>推荐操作:</strong> {rd.recommended_action}
                              </p>
                            )}
                            {rd.source_data_conflict && (
                              <p style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 4 }}>
                                <strong>数据冲突:</strong> {rd.source_data_conflict}
                              </p>
                            )}
                          </div>
                        ))}
                      </div>
                    )}

                    {/* Suggested changes summary */}
                    {currentDiagnosis.suggested_changes && currentDiagnosis.suggested_changes.length > 0 && (
                      <div style={{ marginTop: 16 }}>
                        <h4 style={{ fontSize: 14, marginBottom: 8 }}>
                          修正建议摘要 ({currentDiagnosis.suggested_changes.length} 项)
                        </h4>
                        <table className="vr-table" style={{ fontSize: 13 }}>
                          <thead>
                            <tr>
                              <th>字段</th>
                              <th>类型</th>
                              <th>可修复性</th>
                              <th>原始值</th>
                              <th>建议值</th>
                            </tr>
                          </thead>
                          <tbody>
                            {currentDiagnosis.suggested_changes.map((sc, i) => (
                              <tr key={i}>
                                <td style={{ fontSize: 12 }}>{sc.field_path}</td>
                                <td>{CORRECTION_TYPE_LABELS[sc.correction_type || 'metadata'] || sc.correction_type}</td>
                                <td>{repairabilityBadge(sc.repairability || 'manual_required')}</td>
                                <td style={{ fontSize: 12, maxWidth: 150, overflow: 'hidden', textOverflow: 'ellipsis' }}>
                                  {formatValue(sc.original_value)}
                                </td>
                                <td style={{ fontSize: 12, maxWidth: 150, overflow: 'hidden', textOverflow: 'ellipsis' }}>
                                  {formatValue(sc.suggested_value)}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}

                    {/* Re-run diagnosis button */}
                    <div style={{ marginTop: 16, textAlign: 'right' }}>
                      <button className="btn btn-sm btn-outline" onClick={runDiagnosis} disabled={loading}>
                        <RefreshCw size={12} style={{ marginRight: 4 }} />
                        重新诊断
                      </button>
                    </div>
                  </div>
                ) : (
                  <div style={{ textAlign: 'center', padding: 40, color: 'var(--text-muted)' }}>
                    <p>暂未获取到诊断数据。</p>
                    <button className="btn btn-sm btn-primary" onClick={runDiagnosis} style={{ marginTop: 12 }}>
                      开始诊断
                    </button>
                  </div>
                )}
              </div>
            )}

            {/* ═══ Corrections Tab ═══ */}
            {activeTab === 'corrections' && (
              <div>
                {/* Batch action bar */}
                {currentCorrections.filter(c => c.approval_status === 'proposed').length > 0 && (
                  <div className="vr-action-bar" style={{ marginBottom: 12 }}>
                    <span>已选 {selectedCorrections.size} 项</span>
                    <div className="vr-action-sep" />
                    <button className="btn btn-sm btn-primary" onClick={handleBatchApprove}>
                      <CheckCircle size={14} style={{ marginRight: 4 }} />
                      批量批准
                    </button>
                    <button className="btn btn-sm btn-outline" onClick={handleBatchReject}>
                      <XCircle size={14} style={{ marginRight: 4 }} />
                      批量拒绝
                    </button>
                    <button className="btn btn-sm btn-outline" onClick={() => setSelectedCorrections(new Set())}>
                      清除选择
                    </button>
                  </div>
                )}

                {currentCorrections.length === 0 ? (
                  <div style={{ textAlign: 'center', padding: 40, color: 'var(--text-muted)' }}>
                    <p>暂无修正建议。</p>
                    <p style={{ fontSize: 12, marginTop: 4 }}>
                      请先在「诊断分析」Tab 中运行 DeepSeek 诊断。
                    </p>
                  </div>
                ) : (
                  <table className="vr-table" style={{ fontSize: 13 }}>
                    <thead>
                      <tr>
                        {currentCorrections.filter(c => c.approval_status === 'proposed').length > 0 && (
                          <th style={{ width: 32 }}>
                            <input
                              type="checkbox"
                              checked={
                                selectedCorrections.size === currentCorrections.filter(c => c.approval_status === 'proposed').length
                              }
                              onChange={toggleSelectAllCorrections}
                            />
                          </th>
                        )}
                        <th>规则</th>
                        <th>字段</th>
                        <th>类型</th>
                        <th>可修复性</th>
                        <th>原始值</th>
                        <th>建议值</th>
                        <th>确定性验证</th>
                        <th>状态</th>
                        <th style={{ width: 100 }}>操作</th>
                      </tr>
                    </thead>
                    <tbody>
                      {currentCorrections.map((c) => (
                        <tr key={c.id} className={c.approval_status === 'approved' ? 'vpm-row-pass' : c.approval_status === 'rejected' ? 'vpm-row-fail' : ''}>
                          {currentCorrections.filter(cc => cc.approval_status === 'proposed').length > 0 && (
                            <td onClick={e => e.stopPropagation()}>
                              <input
                                type="checkbox"
                                checked={selectedCorrections.has(c.id)}
                                onChange={() => toggleCorrection(c.id)}
                                disabled={c.approval_status !== 'proposed'}
                              />
                            </td>
                          )}
                          <td><span className="badge badge-blocked">{c.rule_code}</span></td>
                          <td style={{ fontSize: 12, maxWidth: 120 }} title={c.field_path}>{c.field_path}</td>
                          <td>{CORRECTION_TYPE_LABELS[c.correction_type] || c.correction_type}</td>
                          <td>{repairabilityBadge(c.repairability)}</td>
                          <td style={{ fontSize: 12, maxWidth: 100, overflow: 'hidden', textOverflow: 'ellipsis' }}>
                            {formatValue(c.original_value)}
                          </td>
                          <td style={{ fontSize: 12, maxWidth: 100, overflow: 'hidden', textOverflow: 'ellipsis' }}>
                            {formatValue(c.suggested_value)}
                          </td>
                          <td>{statusBadge(c.deterministic_validation_status)}</td>
                          <td>{statusBadge(c.approval_status)}</td>
                          <td>
                            <div style={{ display: 'flex', gap: 4 }}>
                              {c.approval_status === 'proposed' && (
                                <>
                                  <button
                                    className="btn btn-sm"
                                    title="批准"
                                    onClick={() => handleApproveCorrection(c.id, c.suggested_value)}
                                    style={{ padding: '2px 6px', fontSize: 12 }}
                                  >
                                    <CheckCircle size={14} color="var(--success)" />
                                  </button>
                                  <button
                                    className="btn btn-sm"
                                    title="拒绝"
                                    onClick={() => handleRejectCorrection(c.id)}
                                    style={{ padding: '2px 6px', fontSize: 12 }}
                                  >
                                    <XCircle size={14} color="var(--danger)" />
                                  </button>
                                </>
                              )}
                              {c.approval_status === 'approved' && (
                                <span style={{ fontSize: 12, color: 'var(--success)' }}>已批准</span>
                              )}
                              {c.approval_status === 'rejected' && (
                                <span style={{ fontSize: 12, color: 'var(--danger)' }}>已拒绝</span>
                              )}
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            )}

            {/* ═══ Revalidation Tab ═══ */}
            {activeTab === 'revalidation' && (
              <div>
                <div style={{ textAlign: 'center', padding: '20px 0' }}>
                  {/* Status indicators */}
                  <div className="vpm-cards" style={{ marginBottom: 20, justifyContent: 'center' }}>
                    <div className="vpm-card">
                      <span className="vpm-card-num">{currentCorrections.filter(c => c.approval_status === 'approved').length}</span>
                      <span>已批准修正</span>
                    </div>
                    <div className="vpm-card vpm-card-red">
                      <span className="vpm-card-num">{currentCorrections.filter(c => c.approval_status === 'rejected').length}</span>
                      <span>已拒绝修正</span>
                    </div>
                    <div className="vpm-card vpm-card-amber">
                      <span className="vpm-card-num">{currentCorrections.filter(c => c.approval_status === 'proposed').length}</span>
                      <span>待审批修正</span>
                    </div>
                  </div>

                  {revalidationStatus === null && (
                    <div>
                      <p style={{ fontSize: 13, color: 'var(--text-muted)', marginBottom: 16 }}>
                        批准修正建议后，点击下方按钮重新验证该回路。
                      </p>
                      <button
                        className="btn btn-primary"
                        onClick={handleRevalidate}
                        disabled={currentCorrections.filter(c => c.approval_status === 'approved').length === 0}
                      >
                        <RefreshCw size={16} style={{ marginRight: 6 }} />
                        开始重新验证
                      </button>
                      {currentCorrections.filter(c => c.approval_status === 'approved').length === 0 && (
                        <p style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 8 }}>
                          请先在「修正建议」Tab 中批准至少一项修正。
                        </p>
                      )}
                    </div>
                  )}

                  {revalidationStatus === 'queued' && (
                    <div>
                      <RefreshCw size={24} style={{ animation: 'spin 1s linear infinite', marginBottom: 12 }} />
                      <p>验证任务已创建，正在排队...</p>
                    </div>
                  )}

                  {revalidationStatus === 'running' && (
                    <div>
                      <RefreshCw size={24} style={{ animation: 'spin 1s linear infinite', marginBottom: 12 }} />
                      <p style={{ marginBottom: 8 }}>重新验证进行中...</p>
                      <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                        Run ID: {revalidationRunId?.slice(0, 8)}
                      </span>
                    </div>
                  )}

                  {revalidationStatus === 'completed' && (
                    <div>
                      <CheckCircle size={32} color="var(--success)" style={{ marginBottom: 12 }} />
                      <p style={{ color: 'var(--success)', fontWeight: 600, marginBottom: 8 }}>重新验证完成</p>
                      <p style={{ fontSize: 13, color: 'var(--text-muted)' }}>
                        验证结果可查看详细报告。
                      </p>
                      <div style={{ marginTop: 12, display: 'flex', gap: 8, justifyContent: 'center' }}>
                        <button className="btn btn-sm btn-primary" onClick={() => { setRevalidationStatus(null); onClose() }}>
                          完成
                        </button>
                        <button className="btn btn-sm btn-outline" onClick={() => setActiveTab('diagnosis')}>
                          查看诊断结果
                        </button>
                      </div>
                    </div>
                  )}

                  {revalidationStatus === 'failed' && (
                    <div>
                      <XCircle size={32} color="var(--danger)" style={{ marginBottom: 12 }} />
                      <p style={{ color: 'var(--danger)', fontWeight: 600, marginBottom: 8 }}>重新验证失败</p>
                      <button className="btn btn-sm btn-primary" onClick={handleRevalidate} style={{ marginTop: 8 }}>
                        重试
                      </button>
                    </div>
                  )}

                  {revalidationStatus === 'error' && (
                    <div>
                      <AlertTriangle size={32} color="var(--danger)" style={{ marginBottom: 12 }} />
                      <p style={{ color: 'var(--danger)', fontWeight: 600, marginBottom: 8 }}>请求异常</p>
                      <button className="btn btn-sm btn-primary" onClick={handleRevalidate} style={{ marginTop: 8 }}>
                        重试
                      </button>
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Footer */}
        <div className="vw-modal-ft">
          <span style={{ fontSize: 12, color: 'var(--text-muted)', flex: 1 }}>
            {currentCircuitName} | {currentCorrections.filter(c => c.approval_status === 'approved').length} 已批准 / {currentCorrections.length} 总计
          </span>
          <button className="btn btn-sm" onClick={onClose}>关闭</button>
        </div>
      </div>
    </div>
  )
}
