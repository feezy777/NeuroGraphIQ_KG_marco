import { useState, useEffect, useCallback } from 'react'

interface DualReviewCandidate {
  id: string
  circuit_name: string
  circuit_type: string
  rule_overall_status?: string
  reviewer_a_decision?: string
  reviewer_b_decision?: string
  adjudication_status?: string
}

interface Props {
  granularityLevel?: string
}

function statusStyle(status: string | null | undefined): { color: string; label: string } {
  const s = status ?? 'unknown'
  const colors: Record<string, string> = {
    passed: '#52c41a', failed: '#ff4d4f', blocked: '#faad14',
    pending: '#faad14', support: '#52c41a', reject: '#ff4d4f',
    conflict: '#faad14', agreement: '#52c41a',
  }
  const labels: Record<string, string> = {
    passed: '通过', failed: '失败', blocked: '阻塞',
    pending: '待审', support: '支持', reject: '拒绝',
    conflict: '冲突', agreement: '一致',
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

export function DualReviewPanel({ granularityLevel }: Props) {
  const [items, setItems] = useState<DualReviewCandidate[]>([])
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
        <h3 style={{ margin: 0, fontSize: 15, fontWeight: 600 }}>双模型盲审</h3>
        <span className="vr-total">共 {total} 条</span>
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
              <th className="vr-th-status">规则</th>
              <th className="vr-th-status">Reviewer A</th>
              <th className="vr-th-status">Reviewer B</th>
              <th className="vr-th-status">裁决</th>
            </tr>
          </thead>
          <tbody>
            {items.length === 0 ? (
              <tr><td colSpan={7} className="vr-empty">
                <p>暂无可通过规则校验、可送入双模型审核的回路</p>
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
                <td>{badgeHtml(item.rule_overall_status)}</td>
                <td>{badgeHtml(item.reviewer_a_decision)}</td>
                <td>{badgeHtml(item.reviewer_b_decision)}</td>
                <td>{badgeHtml(item.adjudication_status)}</td>
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
            className="btn btn-sm btn-primary"
            onClick={() => doAction('/api/validation/circuit/selection/dual-review', '双模型审核')}
            disabled={actionLoading}
          >
            送入双模型审核
          </button>
          <button
            className="btn btn-sm btn-outline"
            onClick={() => doAction('/api/validation/circuit/selection/retry-reviewer-a', '重试 Reviewer A')}
            disabled={actionLoading}
          >
            重试 Reviewer A
          </button>
          <button
            className="btn btn-sm btn-outline"
            onClick={() => doAction('/api/validation/circuit/selection/retry-reviewer-b', '重试 Reviewer B')}
            disabled={actionLoading}
          >
            重试 Reviewer B
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
