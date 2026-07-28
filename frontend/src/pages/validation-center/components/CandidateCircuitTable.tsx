import { useState, useEffect, useCallback, useRef } from 'react'

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
}

interface Props {
  granularityLevel?: string
}

// ── Helpers ────────────────────────────────────────────────────────────────
const STATUS_COLORS: Record<string, string> = {
  pending: '#faad14',
  approved: '#52c41a',
  rejected: '#ff4d4f',
  not_promoted: '#86909c',
  promoted_to_final: '#2f54eb',
  llm_suggested: '#2f54eb',
}

function statusBadge(status: string): { color: string; label: string } {
  const c = STATUS_COLORS[status] || '#86909c'
  const labels: Record<string, string> = {
    pending: '待审核', approved: '已通过', rejected: '已拒绝',
    not_promoted: '未晋升', promoted_to_final: '已晋升',
    llm_suggested: 'LLM建议',
  }
  return { color: c, label: labels[status] || status }
}

function formatConfidence(v: number): string {
  if (v === 0) return '—'
  return (v * 100).toFixed(0) + '%'
}

function formatTime(s: string | null): string {
  if (!s) return '—'
  try { return s.slice(0, 16).replace('T', ' ') } catch { return s }
}

// ── Side Detail Panel ──────────────────────────────────────────────────────
function CandidateDetail({ circuit, onClose }: { circuit: CandidateCircuit; onClose: () => void }) {
  return (
    <div className="vw-detail-panel">
      <div className="vw-detail-hd">
        <h4>{circuit.circuit_name}</h4>
        <button className="vr-modal-close" onClick={onClose}>✕</button>
      </div>
      <div className="vw-detail-bd">
        <DetailRow label="ID" value={<code>{circuit.id.slice(0, 12)}</code>} />
        <DetailRow label="粒度" value={circuit.granularity_level} />
        <DetailRow label="回路类型" value={circuit.circuit_type} />
        <DetailRow label="步骤数" value={String(circuit.step_count)} />
        <DetailRow label="置信度" value={formatConfidence(circuit.confidence)} />
        <DetailRow label="数据源" value={circuit.source_atlas || '—'} />
        <DetailRow label="功能关联" value={circuit.function_association || '—'} />
        <DetailRow label="创建时间" value={formatTime(circuit.created_at)} />
        <DetailRow label="审核状态" value={statusBadge(circuit.review_status).label} />
        <DetailRow label="晋升状态" value={statusBadge(circuit.promotion_status).label} />
        <DetailRow label="Mirror 状态" value={statusBadge(circuit.mirror_status).label} />
        {circuit.evidence_text && (
          <DetailRow label="证据" value={<span style={{ fontSize: 12, lineHeight: 1.5 }}>{circuit.evidence_text}</span>} />
        )}
      </div>
    </div>
  )
}

function DetailRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="vw-detail-row">
      <span className="vw-detail-label">{label}</span>
      <span className="vw-detail-value">{value}</span>
    </div>
  )
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
  const [detailItem, setDetailItem] = useState<CandidateCircuit | null>(null)
  const [batchLoading, setBatchLoading] = useState(false)
  const [batchMessage, setBatchMessage] = useState<string | null>(null)
  const detailRef = useRef<HTMLDivElement>(null)

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
      setBatchMessage(`验证任务已创建 (ID: ${data.internal_run_id?.slice(0, 8) || '—'}) 已处理 ${data.eligible_count || 0}/${data.selected_count || 0} 个回路`)
      setTimeout(() => setBatchMessage(null), 5000)
    } catch (e: unknown) {
      setBatchMessage(e instanceof Error ? e.message : '提交失败')
      setTimeout(() => setBatchMessage(null), 5000)
    } finally {
      setBatchLoading(false)
    }
  }, [selected])

  // Detail panel
  const handleRowClick = (item: CandidateCircuit) => {
    setDetailItem(item)
  }

  // Close detail panel by clicking outside
  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (detailRef.current && !detailRef.current.contains(e.target as Node)) {
        setDetailItem(null)
      }
    }
    if (detailItem) {
      setTimeout(() => document.addEventListener('click', handleClick), 0)
      return () => document.removeEventListener('click', handleClick)
    }
  }, [detailItem])

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
                <th style={{ minWidth: 160 }}>回路名称</th>
                <th className="vr-th-type">类型</th>
                <th style={{ width: 80 }}>粒度</th>
                <th style={{ width: 60, textAlign: 'center' }}>步骤</th>
                <th className="vr-th-conf">置信度</th>
                <th className="vr-th-status">审核状态</th>
                <th className="vr-th-status">晋升状态</th>
                <th style={{ width: 120 }}>数据源</th>
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

      {/* Detail side panel */}
      {detailItem && (
        <div ref={detailRef}>
          <CandidateDetail circuit={detailItem} onClose={() => setDetailItem(null)} />
        </div>
      )}
    </div>
  )
}
