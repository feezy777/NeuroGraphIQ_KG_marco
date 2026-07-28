import { useState, useEffect, useCallback } from 'react'

interface HumanReviewCandidate {
  id: string
  circuit_name: string
  circuit_type: string
  adjudication_status?: string
  recommended_review_priority?: string | number
  rule_overall_status?: string
}

interface Props {
  granularityLevel?: string
}

function statusStyle(status: string | null | undefined): { color: string; label: string } {
  const s = status ?? 'unknown'
  const colors: Record<string, string> = {
    passed: '#52c41a', failed: '#ff4d4f', blocked: '#faad14',
    pending: '#faad14', conflict: '#faad14', agreement: '#52c41a',
    approved: '#52c41a', rejected: '#ff4d4f',
    high: '#ff4d4f', medium: '#faad14', low: '#86909c',
  }
  const labels: Record<string, string> = {
    passed: '通过', failed: '失败', blocked: '阻塞',
    pending: '待审', conflict: '冲突', agreement: '一致',
    approved: '已通过', rejected: '已拒绝',
    high: '高', medium: '中', low: '低',
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

function priorityHtml(priority: string | number | undefined): React.ReactNode {
  const { color, label } = statusStyle(String(priority ?? 'low'))
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

export function HumanReviewPanel({ granularityLevel }: Props) {
  const [items, setItems] = useState<HumanReviewCandidate[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [actionLoading, setActionLoading] = useState(false)
  const [actionMessage, setActionMessage] = useState<string | null>(null)

  const fetchData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const params = new URLSearchParams()
      params.set('limit', '50')
      if (granularityLevel) params.set('granularity_level', granularityLevel)
      const res = await fetch(`/api/validation/circuit/human-review/queue?${params}`)
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

  if (loading && items.length === 0) {
    return <div className="vr-panel"><div className="vr-empty">加载中...</div></div>
  }
  if (error) return <div className="vr-panel"><div className="vr-error">{error}</div></div>

  return (
    <div className="vr-panel">
      <div className="vr-header">
        <h3 style={{ margin: 0, fontSize: 15, fontWeight: 600 }}>人工审核</h3>
        <span className="vr-total">共 {total} 条待审核</span>
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
              <th className="vr-th-status">裁决状态</th>
              <th className="vr-th-status">优先级</th>
              <th className="vr-th-status">规则状态</th>
            </tr>
          </thead>
          <tbody>
            {items.length === 0 ? (
              <tr><td colSpan={6} className="vr-empty">
                <p>当前没有待人工审核的回路</p>
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
                <td>{badgeHtml(item.adjudication_status)}</td>
                <td>{priorityHtml(item.recommended_review_priority)}</td>
                <td>{badgeHtml(item.rule_overall_status)}</td>
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
            className="btn btn-sm btn-success"
            onClick={() => doAction('/api/validation/circuit/selection/approve', '通过')}
            disabled={actionLoading}
            style={{ background: '#52c41a', color: '#fff', borderColor: '#52c41a' }}
          >
            通过
          </button>
          <button
            className="btn btn-sm btn-outline-danger"
            onClick={() => doAction('/api/validation/circuit/selection/reject', '拒绝')}
            disabled={actionLoading}
            style={{ color: '#ff4d4f', borderColor: '#ff4d4f' }}
          >
            拒绝
          </button>
          <button
            className="btn btn-sm btn-outline"
            onClick={() => doAction('/api/validation/circuit/selection/keep-candidate', '保留候选')}
            disabled={actionLoading}
          >
            保留候选
          </button>
          <button
            className="btn btn-sm btn-outline"
            onClick={() => doAction('/api/validation/circuit/selection/reopen', '退回重审')}
            disabled={actionLoading}
          >
            退回重审
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
    </div>
  )
}
