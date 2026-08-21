import { useCallback, useEffect, useState } from 'react'
import {
  batchAcceptExactCandidates,
  getAlignmentStats,
  getEntitySummary,
  listAlignmentCandidates,
  reviewAlignmentCandidate,
  type AlignmentCandidateItem,
  type AlignmentStats,
  type EntitySummary,
} from '../../../api/endpoints'

type EntityViewKey = 'regions' | 'connections' | 'circuits'

export function RegionsGovernance({ granularity, role }: { granularity: string; role: string }) {
  const [entityView, setEntityView] = useState<EntityViewKey>('regions')
  return (
    <div>
      <div className="ontology-subview-tabs">
        {(
          [
            ['regions', '脑区'],
            ['connections', '连接'],
            ['circuits', '回路'],
          ] as Array<[EntityViewKey, string]>
        ).map(([key, label]) => (
          <button key={key} type="button" className={`ontology-subview-tab ${entityView === key ? 'ontology-subview-tab-active' : ''}`} onClick={() => setEntityView(key)}>{label}</button>
        ))}
      </div>
      {entityView === 'regions' && <RegionCandidates granularity={granularity} role={role} />}
      {entityView === 'connections' && <EntityView entity="connection" />}
      {entityView === 'circuits' && <EntityView entity="circuit" />}
    </div>
  )
}

function RegionCandidates({ granularity, role }: { granularity: string; role: string }) {
  const [status, setStatus] = useState('pending')
  const [stats, setStats] = useState<AlignmentStats | null>(null)
  const [items, setItems] = useState<AlignmentCandidateItem[]>([])
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const [loading, setLoading] = useState(true)
  const [message, setMessage] = useState<string | null>(null)
  const pageSize = 30

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const [s, l] = await Promise.all([
        getAlignmentStats({ granularity_level: granularity }),
        listAlignmentCandidates({ status, granularity_level: granularity, limit: pageSize, offset }),
      ])
      setStats(s)
      setItems(l.items)
      setTotal(l.total)
    } catch {
      setStats(null)
      setItems([])
      setTotal(0)
    } finally {
      setLoading(false)
    }
  }, [granularity, status, offset])

  useEffect(() => {
    load()
  }, [load])

  const review = useCallback(async (candidateId: string, action: 'accept' | 'reject') => {
    setMessage(null)
    try {
      await reviewAlignmentCandidate(candidateId, { action })
      setMessage(action === 'accept' ? '已接受候选' : '已拒绝候选')
      await load()
    } catch (err) {
      setMessage(`操作失败：${err instanceof Error ? err.message : String(err)}`)
    }
  }, [load])

  const batchAccept = useCallback(async () => {
    setMessage(null)
    try {
      const r = await batchAcceptExactCandidates()
      setMessage(`已批量接受 ${r.accepted} 个 exact 候选`)
      await load()
    } catch (err) {
      setMessage(`操作失败：${err instanceof Error ? err.message : String(err)}`)
    }
  }, [load])

  return (
    <div className="card ontology-card">
      <div className="ontology-card-header">
        <span className="ontology-card-title">脑区外部标识对齐</span>
        <span className="ontology-card-sub">
          {stats ? `总数 ${stats.total} · 待确认 ${stats.by_status.pending ?? 0} · 已接受 ${stats.by_status.accepted ?? 0} · 已拒绝 ${stats.by_status.rejected ?? 0} · exact ${stats.by_match_type.exact ?? 0} / close ${stats.by_match_type.close ?? 0} / weak ${stats.by_match_type.weak ?? 0} / not_found ${stats.by_match_type.not_found ?? 0}` : ''}
        </span>
      </div>
      {message && <div className="ontology-page-message">{message}</div>}
      <div className="ontology-subview-tabs">
        {(['pending', 'accepted', 'rejected'] as const).map(key => (
          <button key={key} type="button" className={`ontology-subview-tab ${status === key ? 'ontology-subview-tab-active' : ''}`} onClick={() => { setStatus(key); setOffset(0) }}>
            {key === 'pending' ? '待确认' : key === 'accepted' ? '已对齐' : '已拒绝'}
          </button>
        ))}
        {role === 'ontology_admin' && <button type="button" className="btn btn-sm" onClick={batchAccept}>批量接受 exact</button>}
        <button type="button" className="btn btn-sm" onClick={load}>刷新</button>
      </div>
      <table className="data-table ontology-term-table">
        <thead>
          <tr><th>脑区</th><th>图谱</th><th>候选标签</th><th>IRI</th><th>匹配</th><th>得分</th><th>状态</th><th>操作</th></tr>
        </thead>
        <tbody>
          {loading && <tr><td colSpan={8} className="ontology-empty">加载中…</td></tr>}
          {!loading && items.length === 0 && <tr><td colSpan={8} className="ontology-empty">当前无候选</td></tr>}
          {items.map(c => (
            <tr key={c.candidate_id}>
              <td>{c.en_name}{c.cn_name ? <span className="ontology-term-meta">（{c.cn_name}）</span> : null}</td>
              <td>{c.source_atlas}</td>
              <td>{c.external_label ?? '—'}</td>
              <td><a href={c.external_iri} target="_blank" rel="noreferrer">{c.external_iri}</a></td>
              <td>{c.match_type}</td>
              <td>{c.match_score != null ? Math.round(c.match_score * 100) : '—'}%</td>
              <td><span className={`ontology-status ontology-status-${c.status}`}>{c.status}</span></td>
              <td className="ontology-term-actions">
                {c.status === 'pending' && role !== 'viewer' && (
                  <>
                    <button type="button" className="btn btn-xs" onClick={() => review(c.candidate_id, 'accept')}>接受</button>
                    <button type="button" className="btn btn-xs" onClick={() => review(c.candidate_id, 'reject')}>拒绝</button>
                  </>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="ontology-page-pager">
        <button type="button" className="btn btn-xs" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - pageSize))}>上一页</button>
        <span>{offset + 1}-{Math.min(offset + pageSize, total)} / {total}</span>
        <button type="button" className="btn btn-xs" disabled={offset + pageSize >= total} onClick={() => setOffset(offset + pageSize)}>下一页</button>
      </div>
    </div>
  )
}

function EntityView({ entity }: { entity: 'connection' | 'circuit' }) {
  const [data, setData] = useState<EntitySummary | null>(null)
  useEffect(() => {
    getEntitySummary(entity).then(setData).catch(() => setData(null))
  }, [entity])
  const distributions: Array<[string, Array<{ value: string; count: number }> | undefined]> =
    entity === 'connection'
      ? [['连接类型', data?.by_type], ['方向性', data?.by_direction]]
      : [['回路类型', data?.by_type], ['步骤类型', data?.by_step_type], ['步骤角色', data?.by_step_role]]
  return (
    <div className="card ontology-card">
      <div className="ontology-card-header">
        <span className="ontology-card-title">{entity === 'connection' ? '连接本体视图' : '回路本体视图'}</span>
        <span className="ontology-card-sub">类型与角色分布（只读）</span>
      </div>
      {!data && <div className="ontology-empty">加载中…</div>}
      {data && (
        <div>
          <div className="ontology-overview-grid" style={{ marginBottom: 12 }}>
            <div className="ontology-stat-card"><span className="ontology-stat-label">总数</span><span className="ontology-stat-value">{data.total}</span></div>
            <div className="ontology-stat-card"><span className="ontology-stat-label">枚举异常</span><span className="ontology-stat-value">{data.anomalies}</span></div>
          </div>
          {distributions.map(([label, rows]) => (
            <details key={label} className="ontology-vocab-group" open>
              <summary>{label}（{rows?.length ?? 0}）</summary>
              <table className="data-table ontology-term-table">
                <thead><tr><th>值</th><th>数量</th></tr></thead>
                <tbody>
                  {(rows ?? []).map(row => (
                    <tr key={row.value}><td>{row.value}</td><td>{row.count}</td></tr>
                  ))}
                  {(rows ?? []).length === 0 && <tr><td colSpan={2} className="ontology-empty">暂无数据</td></tr>}
                </tbody>
              </table>
            </details>
          ))}
        </div>
      )}
    </div>
  )
}
