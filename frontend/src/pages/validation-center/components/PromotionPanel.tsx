import { useState, useEffect, useCallback } from 'react'

interface PromotionCandidate {
  id: string
  circuit_name: string
  circuit_type: string
  confidence?: number
  review_status?: string
  mirror_status?: string
}

interface Props {
  granularityLevel?: string
}

function statusStyle(status: string | null | undefined): { color: string; label: string } {
  const s = status ?? 'unknown'
  const colors: Record<string, string> = {
    pending: '#faad14', approved: '#52c41a', rejected: '#ff4d4f',
    not_promoted: '#86909c', promoted_to_final: '#2f54eb',
    llm_suggested: '#2f54eb',
  }
  const labels: Record<string, string> = {
    pending: '待审核', approved: '已通过', rejected: '已拒绝',
    not_promoted: '未晋升', promoted_to_final: '已晋升',
    llm_suggested: 'LLM建议',
  }
  return { color: colors[s] || '#86909c', label: labels[s] || s }
}

function badgeHtml(status: string | null | undefined): React.ReactNode {
  const { color, label } = statusStyle(status)
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

function formatConfidence(v: number | undefined | null): string {
  if (v === null || v === undefined || v === 0) return '—'
  return (v * 100).toFixed(0) + '%'
}

export function PromotionPanel({ granularityLevel }: Props) {
  const [items, setItems] = useState<PromotionCandidate[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [actionLoading, setActionLoading] = useState(false)
  const [actionMessage, setActionMessage] = useState<string | null>(null)
  const [showPreview, setShowPreview] = useState(false)
  const [previewData, setPreviewData] = useState<Record<string, any> | null>(null)
  const [previewLoading, setPreviewLoading] = useState(false)
  const [previewError, setPreviewError] = useState<string | null>(null)
  const [dryRunResult, setDryRunResult] = useState<Record<string, any> | null>(null)
  const [dryRunLoading, setDryRunLoading] = useState(false)

  const fetchData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const params = new URLSearchParams()
      params.set('limit', '50')
      if (granularityLevel) params.set('granularity_level', granularityLevel)
      const res = await fetch(`/api/validation/circuit/promotion/queue?${params}`)
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
      setActionMessage(`${label} 已完成 (已处理 ${data.eligible_count || data.processed_count || '?'} 项)`)
      setTimeout(() => setActionMessage(null), 5000)
      fetchData()
    } catch (e: unknown) {
      setActionMessage(e instanceof Error ? e.message : '操作失败')
      setTimeout(() => setActionMessage(null), 5000)
    } finally {
      setActionLoading(false)
    }
  }, [selected, fetchData])

  const handlePreview = useCallback(async () => {
    if (selected.size === 0) return
    setPreviewLoading(true)
    setPreviewError(null)
    setPreviewData(null)
    try {
      // Preview the first selected item
      const id = Array.from(selected)[0]
      const res = await fetch(`/api/validation/circuit/promotion/${id}/preview`)
      if (!res.ok) throw new Error(`API错误: ${res.status}`)
      const data = await res.json()
      setPreviewData(data)
    } catch (e: unknown) {
      setPreviewError(e instanceof Error ? e.message : '预览失败')
    } finally {
      setPreviewLoading(false)
      setShowPreview(true)
    }
  }, [selected])

  const handleDryRunPromote = useCallback(async () => {
    if (selected.size === 0) return
    setDryRunLoading(true)
    setDryRunResult(null)
    try {
      const id = Array.from(selected)[0]
      const res = await fetch(`/api/validation/circuit/promotion/${id}/execute`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ dry_run: true }),
      })
      if (!res.ok) throw new Error(`API错误: ${res.status}`)
      const data = await res.json()
      setDryRunResult(data)
    } catch (e: unknown) {
      setDryRunResult({error: e instanceof Error ? e.message : '操作失败'})
    } finally {
      setDryRunLoading(false)
    }
  }, [selected])

  if (loading && items.length === 0) {
    return <div className="vr-panel"><div className="vr-empty">加载中...</div></div>
  }
  if (error) return <div className="vr-panel"><div className="vr-error">{error}</div></div>

  return (
    <div className="vr-panel">
      <div className="vr-header">
        <h3 style={{ margin: 0, fontSize: 15, fontWeight: 600 }}>晋升管理</h3>
        <span className="vr-total">共 {total} 条可晋升</span>
      </div>

      {actionMessage && (
        <div style={{
          margin: '8px 20px 0', padding: '6px 12px', borderRadius: 'var(--radius)',
          fontSize: 13,
          background: actionMessage.includes('失败') || actionMessage.includes('错误')
            ? '#fff2f0' : '#f6ffed',
          color: actionMessage.includes('失败') || actionMessage.includes('错误')
            ? 'var(--danger)' : 'var(--success)',
        }}>
          {actionMessage}
        </div>
      )}

      <div className="vr-table-wrap">
        <table className="vr-table">
          <thead>
            <tr>
              <th className="vr-th-check">
                <input
                  type="checkbox"
                  checked={selected.size === items.length && items.length > 0}
                  onChange={() => {
                    if (selected.size === items.length) setSelected(new Set())
                    else setSelected(new Set(items.map(i => i.id)))
                  }}
                />
              </th>
              <th>名称</th>
              <th className="vr-th-type">类型</th>
              <th className="vr-th-conf">置信度</th>
              <th className="vr-th-status">审核状态</th>
              <th className="vr-th-status">Mirror 状态</th>
            </tr>
          </thead>
          <tbody>
            {items.length === 0 ? (
              <tr><td colSpan={6} className="vr-empty">
                <p>当前没有可晋升的回路</p>
              </td></tr>
            ) : items.map((item, i) => (
              <tr key={item.id}
                className={`vr-row${i % 2 === 1 ? ' even' : ''}${selected.has(item.id) ? ' selected' : ''}`}
                onClick={() => toggleSelect(item.id)}
              >
                <td className="vr-td-check" onClick={e => e.stopPropagation()}>
                  <input type="checkbox" checked={selected.has(item.id)} onChange={() => toggleSelect(item.id)} />
                </td>
                <td className="vr-td-label">{item.circuit_name?.slice(0, 60) || item.id.slice(0, 12)}</td>
                <td><span className="vr-badge">{item.circuit_type || '?'}</span></td>
                <td>{formatConfidence(item.confidence)}</td>
                <td>{badgeHtml(item.review_status)}</td>
                <td>{badgeHtml(item.mirror_status)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {selected.size > 0 && (
        <div className="vr-action-bar">
          <span>已选 {selected.size} 项</span>
          <div className="vr-action-sep" />
          <button
            className="btn btn-sm btn-outline"
            onClick={handlePreview}
            disabled={actionLoading || previewLoading}
          >
            {previewLoading ? '加载中...' : '晋升预览'}
          </button>
          <button
            className="btn btn-sm btn-outline"
            onClick={handleDryRunPromote}
            disabled={actionLoading || dryRunLoading}
          >
            {dryRunLoading ? '模拟中...' : '晋升模拟(Dry Run)'}
          </button>
          <button
            className="btn btn-sm btn-primary"
            onClick={() => doAction('/api/validation/circuit/selection/promote', '晋升')}
            disabled={actionLoading}
          >
            执行晋升
          </button>
          <button
            className="btn btn-sm btn-outline"
            onClick={() => setSelected(new Set())}
            disabled={actionLoading}
          >
            清除选择
          </button>
        </div>
      )}

      {showPreview && (
        <div className="vr-modal-overlay" onClick={() => setShowPreview(false)}>
          <div className="vr-modal" style={{ width: 560 }} onClick={e => e.stopPropagation()}>
            <div className="vr-modal-hd">
              <h3>晋升预览</h3>
              <span className="vr-modal-meta">已选 {selected.size} 项</span>
              <button className="vr-modal-close" onClick={() => setShowPreview(false)}>✕</button>
            </div>
            <div className="vr-modal-body">
              {previewError ? (
                <div style={{color: 'var(--danger)', padding: 12, fontSize: 13}}>{previewError}</div>
              ) : previewData ? (
                <>
                  <div className="vr-section">
                    <h4>回路详情</h4>
                    <table style={{width: '100%', fontSize: 13, borderCollapse: 'collapse'}}>
                      <tbody>
                        <tr><td style={{padding: '4px 8px', color: 'var(--text-muted)'}}>名称</td>
                            <td style={{padding: '4px 8px'}}>{previewData.circuit_name}</td></tr>
                        <tr><td style={{padding: '4px 8px', color: 'var(--text-muted)'}}>审核状态</td>
                            <td style={{padding: '4px 8px'}}>{badgeHtml(previewData.review_status)}</td></tr>
                        <tr><td style={{padding: '4px 8px', color: 'var(--text-muted)'}}>晋升状态</td>
                            <td style={{padding: '4px 8px'}}>{badgeHtml(previewData.promotion_status)}</td></tr>
                        <tr><td style={{padding: '4px 8px', color: 'var(--text-muted)'}}>是否可晋升</td>
                            <td style={{padding: '4px 8px'}}>{previewData.eligible ? '是' : '否'}</td></tr>
                      </tbody>
                    </table>
                    {previewData.blockers && previewData.blockers.length > 0 && (
                      <div style={{marginTop: 8}}>
                        <h5 style={{fontSize: 12, color: 'var(--danger)', margin: '4px 0'}}>阻塞原因:</h5>
                        <ul style={{margin: 0, paddingLeft: 16, fontSize: 12, color: 'var(--danger)'}}>
                          {previewData.blockers.map((b: string, i: number) => <li key={i}>{b}</li>)}
                        </ul>
                      </div>
                    )}
                    {previewData.details?.circuit_record && (
                      <div style={{marginTop: 8, padding: 8, background: '#f5f5f5', borderRadius: 6, fontSize: 12}}>
                        <strong>目标记录:</strong>
                        <pre style={{margin: '4px 0 0', whiteSpace: 'pre-wrap', fontSize: 11}}>
                          {JSON.stringify(previewData.details.circuit_record, null, 2)}
                        </pre>
                      </div>
                    )}
                  </div>
                  <div className="vr-section" style={{marginTop: 12}}>
                    <h4>操作说明</h4>
                    <p style={{fontSize: 12, color: 'var(--text-muted)', lineHeight: 1.6}}>
                      晋升后，选中的回路将从 Mirror KG 复制到 Final KG，
                      并记录晋升审计日志。此操作不可逆转。
                    </p>
                  </div>
                </>
              ) : (
                <div style={{padding: 20, textAlign: 'center', color: 'var(--text-muted)'}}>加载中...</div>
              )}
            </div>
            <div className="vr-modal-ft">
              <button className="btn btn-sm btn-outline" onClick={() => setShowPreview(false)}>关闭</button>
              {previewData?.eligible && (
                <button
                  className="btn btn-sm btn-primary"
                  onClick={() => {
                    setShowPreview(false)
                    doAction('/api/validation/circuit/selection/promote', '晋升')
                  }}
                >
                  确认晋升
                </button>
              )}
            </div>
          </div>
        </div>
      )}

      {dryRunResult && (
        <div className="vr-modal-overlay" onClick={() => setDryRunResult(null)}>
          <div className="vr-modal" style={{ width: 520 }} onClick={e => e.stopPropagation()}>
            <div className="vr-modal-hd">
              <h3>晋升模拟结果 (Dry Run)</h3>
              <button className="vr-modal-close" onClick={() => setDryRunResult(null)}>✕</button>
            </div>
            <div className="vr-modal-body">
              {dryRunResult.error ? (
                <div style={{color: 'var(--danger)', padding: 12}}>{dryRunResult.error}</div>
              ) : (
                <>
                  <table style={{width: '100%', fontSize: 13, borderCollapse: 'collapse'}}>
                    <tbody>
                      <tr><td style={{padding: '4px 8px', color: 'var(--text-muted)'}}>状态</td>
                          <td style={{padding: '4px 8px'}}>{dryRunResult.status}</td></tr>
                      <tr><td style={{padding: '4px 8px', color: 'var(--text-muted)'}}>可晋升</td>
                          <td style={{padding: '4px 8px'}}>{dryRunResult.eligible ? '是' : '否'}</td></tr>
                      <tr><td style={{padding: '4px 8px', color: 'var(--text-muted)'}}>幂等键</td>
                          <td style={{padding: '4px 8px', fontSize: 11}}>{dryRunResult.idempotency_key}</td></tr>
                    </tbody>
                  </table>
                  {dryRunResult.target_records?.circuit && (
                    <div style={{marginTop: 8, padding: 8, background: '#f5f5f5', borderRadius: 6, fontSize: 12}}>
                      <strong>目标记录:</strong>
                      <pre style={{margin: '4px 0 0', whiteSpace: 'pre-wrap', fontSize: 11}}>
                        {JSON.stringify(dryRunResult.target_records.circuit, null, 2)}
                      </pre>
                    </div>
                  )}
                  {dryRunResult.warnings && dryRunResult.warnings.length > 0 && (
                    <div style={{marginTop: 8}}>
                      {dryRunResult.warnings.map((w: string, i: number) => (
                        <div key={i} style={{padding: '4px 8px', background: '#fffbe6', borderRadius: 4, fontSize: 12, marginTop: 4}}>
                          ⚠ {w}
                        </div>
                      ))}
                    </div>
                  )}
                </>
              )}
            </div>
            <div className="vr-modal-ft">
              <button className="btn btn-sm btn-outline" onClick={() => setDryRunResult(null)}>关闭</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
