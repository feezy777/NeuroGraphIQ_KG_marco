import { useState, useEffect, useCallback } from 'react'
import { QualityScoreBadge } from './QualityScoreBadge'

// ── Types ──────────────────────────────────────────────────────────────────

export interface CircuitItem {
  id: string
  circuit_name: string
  granularity_level: string
  circuit_type: string
  step_count: number
  confidence: number
  quality_score?: number
  review_status: string
  promotion_status: string
  rule_overall_status?: string
  reviewer_a_decision?: string
  reviewer_b_decision?: string
  adjudication_status?: string
}

interface Props {
  granularityLevel?: string
  selected: Set<string>
  onSelectionChange: (selected: Set<string>) => void
  /** Optional filter presets */
  onlyBlocked?: boolean
  onlyPassed?: boolean
}

// ── Helpers ────────────────────────────────────────────────────────────────

const PAGE_SIZE = 25

function formatConfidence(v: number): string {
  if (!v) return '—'
  return (v * 100).toFixed(0) + '%'
}

function statusBadge(status: string): { color: string; label: string } {
  const colors: Record<string, string> = {
    pending: '#faad14', approved: '#52c41a', rejected: '#ff4d4f',
    not_promoted: '#86909c', promoted_to_final: '#2f54eb',
    passed: '#52c41a', failed: '#ff4d4f', blocked: '#faad14',
  }
  const labels: Record<string, string> = {
    pending: '待审核', approved: '已通过', rejected: '已拒绝',
    not_promoted: '未晋升', promoted_to_final: '已晋升',
    passed: '通过', failed: '失败', blocked: '阻塞',
  }
  return { color: colors[status] || '#86909c', label: labels[status] || status }
}

// ── Component ──────────────────────────────────────────────────────────────

export function CircuitSelector({
  granularityLevel, selected, onSelectionChange, onlyBlocked, onlyPassed,
}: Props) {
  const [items, setItems] = useState<CircuitItem[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [page, setPage] = useState(0)
  const [search, setSearch] = useState('')
  const [error, setError] = useState<string | null>(null)

  const fetchData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const params = new URLSearchParams()
      const gran = granularityLevel && granularityLevel !== 'all' ? granularityLevel : undefined
      if (gran) params.set('granularity_level', gran)
      if (search) params.set('search', search)
      if (onlyBlocked) params.set('rule_status', 'blocked')
      if (onlyPassed) params.set('rule_status', 'passed')
      params.set('limit', String(PAGE_SIZE))
      params.set('offset', String(page * PAGE_SIZE))
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
  }, [granularityLevel, search, page, onlyBlocked, onlyPassed])

  useEffect(() => { fetchData() }, [fetchData])

  const toggleSelect = (id: string) => {
    const next = new Set(selected)
    if (next.has(id)) next.delete(id); else next.add(id)
    onSelectionChange(next)
  }

  const toggleSelectAll = () => {
    if (selected.size === items.length && items.length > 0) {
      onSelectionChange(new Set())
    } else {
      onSelectionChange(new Set(items.map(i => i.id)))
    }
  }

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {/* Filter bar */}
      <div style={{
        display: 'flex', gap: 8, alignItems: 'center', padding: '8px 0',
        flexShrink: 0,
      }}>
        <input
          type="text"
          placeholder="搜索回路名称…"
          value={search}
          onChange={e => { setSearch(e.target.value); setPage(0) }}
          style={{
            padding: '4px 10px', borderRadius: 'var(--radius)',
            border: '1px solid var(--border)', fontSize: 13, width: 220, outline: 'none',
          }}
          onKeyDown={e => { if (e.key === 'Enter') fetchData() }}
        />
        <button className="btn btn-sm btn-outline" onClick={fetchData} disabled={loading}>
          {loading ? '加载中…' : '查询'}
        </button>
        <span className="vr-total">共 {total} 条</span>
        <span style={{ fontSize: 13, color: 'var(--text-muted)' }}>
          已选 {selected.size} 项
        </span>
      </div>

      {error && (
        <div className="vr-error" style={{ flexShrink: 0, padding: '4px 12px', fontSize: 13 }}>
          {error}
          <button className="btn btn-sm btn-outline" onClick={fetchData} style={{ marginLeft: 8 }}>重试</button>
        </div>
      )}

      {/* Table */}
      <div style={{ flex: 1, overflow: 'auto', border: '1px solid var(--border)', borderRadius: 'var(--radius)' }}>
        {loading ? (
          <div className="vw-empty-state" style={{ padding: 40, textAlign: 'center' }}>
            <p>加载中...</p>
          </div>
        ) : items.length === 0 ? (
          <div className="vw-empty-state" style={{ padding: 40, textAlign: 'center' }}>
            <p style={{ color: 'var(--text-muted)' }}>暂无匹配的候选回路</p>
          </div>
        ) : (
          <table className="vr-table" style={{ fontSize: 13 }}>
            <thead>
              <tr>
                <th className="vr-th-check">
                  <input
                    type="checkbox"
                    checked={selected.size === items.length && items.length > 0}
                    onChange={toggleSelectAll}
                  />
                </th>
                <th style={{ minWidth: 160 }}>回路名称</th>
                <th style={{ width: 80 }}>类型</th>
                <th style={{ width: 48, textAlign: 'center' }}>步骤</th>
                <th style={{ width: 56 }}>置信度</th>
                <th style={{ width: 52 }}>质量</th>
                <th style={{ width: 56 }}>规则</th>
                <th style={{ width: 64 }}>审核</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item, i) => {
                const ruleBadge = statusBadge(item.rule_overall_status || '')
                const reviewBadge = statusBadge(item.review_status)
                return (
                  <tr
                    key={item.id}
                    className={`vr-row${i % 2 === 1 ? ' even' : ''}${selected.has(item.id) ? ' selected' : ''}`}
                    onClick={() => toggleSelect(item.id)}
                  >
                    <td className="vr-td-check" onClick={e => e.stopPropagation()}>
                      <input
                        type="checkbox"
                        checked={selected.has(item.id)}
                        onChange={() => toggleSelect(item.id)}
                      />
                    </td>
                    <td
                      className="vr-td-label"
                      title={item.circuit_name}
                      style={{ maxWidth: 280, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
                    >
                      {item.circuit_name?.slice(0, 60) || item.id.slice(0, 12)}
                    </td>
                    <td><span className="vr-badge" style={{ fontSize: 11 }}>{item.circuit_type}</span></td>
                    <td style={{ textAlign: 'center', fontSize: 13 }}>{item.step_count}</td>
                    <td style={{ fontSize: 12 }}>{formatConfidence(item.confidence)}</td>
                    <td style={{ fontSize: 12 }}>
                      <QualityScoreBadge score={item.quality_score || 0} />
                    </td>
                    <td>
                      <span style={{
                        display: 'inline-block', padding: '1px 6px', borderRadius: 8,
                        fontSize: 11, fontWeight: 600,
                        background: ruleBadge.color + '1a', color: ruleBadge.color,
                        border: `1px solid ${ruleBadge.color}44`,
                      }}>
                        {ruleBadge.label}
                      </span>
                    </td>
                    <td>
                      <span style={{
                        display: 'inline-block', padding: '1px 6px', borderRadius: 8,
                        fontSize: 11, fontWeight: 600,
                        background: reviewBadge.color + '1a', color: reviewBadge.color,
                        border: `1px solid ${reviewBadge.color}44`,
                      }}>
                        {reviewBadge.label}
                      </span>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div style={{
          display: 'flex', gap: 12, alignItems: 'center', justifyContent: 'center',
          padding: '8px 0', flexShrink: 0, fontSize: 13,
        }}>
          <button
            className="btn btn-sm btn-outline"
            disabled={page === 0}
            onClick={() => setPage(p => Math.max(0, p - 1))}
          >
            上一页
          </button>
          <span style={{ color: 'var(--text-muted)' }}>
            第 {page + 1} / {totalPages} 页
          </span>
          <button
            className="btn btn-sm btn-outline"
            disabled={page >= totalPages - 1}
            onClick={() => setPage(p => p + 1)}
          >
            下一页
          </button>
        </div>
      )}
    </div>
  )
}
