import { useState, useEffect } from 'react'
import { useI18n } from '../../../i18n-context'

interface RunItem { id: string; status: string; granularity_level: string; rule_total_count: number; rule_passed_count: number; rule_failed_count: number; rule_blocked_count: number; dual_review_agreement_count: number; dual_review_total_count: number; created_at?: string }

interface Props { granularityLevel?: string }
export function ValidationOverviewPanel({ granularityLevel }: Props) {
  const { t } = useI18n()
  const [runs, setRuns] = useState<RunItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setLoading(true)
    const params = new URLSearchParams()
    if (granularityLevel) params.set('granularity_level', granularityLevel)
    params.set('limit', '20')
    fetch(`/api/validation/circuit/runs?${params}`)
      .then(r => { if (!r.ok) throw new Error('API error'); return r.json() })
      .then(d => { setRuns(d.items || []); setLoading(false) })
      .catch(e => { setError(e.message); setLoading(false) })
  }, [granularityLevel])

  if (loading) return <div style={{ padding: 20 }}><p>加载中…</p></div>
  if (error) return <div style={{ padding: 20 }}><p>加载失败: {error}</p></div>

  return (
    <div style={{ padding: 20 }}>
      <h3>验证运行列表</h3>
      {runs.length === 0 ? (
        <div style={{ padding: '40px 0', textAlign: 'center', color: '#86909c' }}>
          <p>当前没有验证任务。</p>
          <p style={{ fontSize: 13 }}>请先创建验证任务。后端端点: POST /api/validation/circuit/runs</p>
        </div>
      ) : (
        <table className="vr-table">
          <thead><tr><th>ID</th><th>粒度</th><th>状态</th><th>规则 (通过/总数)</th><th>双模型 (一致/总数)</th><th>阻塞</th><th>时间</th></tr></thead>
          <tbody>{runs.map(r => (
            <tr key={r.id}>
              <td><code>{r.id.slice(0, 8)}</code></td>
              <td>{r.granularity_level}</td>
              <td><span className="badge">{r.status}</span></td>
              <td>{r.rule_passed_count}/{r.rule_total_count}</td>
              <td>{r.dual_review_agreement_count}/{r.dual_review_total_count || '-'}</td>
              <td>{r.rule_blocked_count > 0 ? <span style={{color:'#ff4d4f'}}>{r.rule_blocked_count}</span> : '0'}</td>
              <td>{r.created_at?.slice(0, 16)}</td>
            </tr>
          ))}</tbody></table>
      )}
      <div style={{ marginTop: 16, padding: 12, background: '#f0f5ff', borderRadius: 6, fontSize: 13 }}>
        <strong>数据源:</strong> mirror_region_circuits (53,112 分子 + 450 宏观)。创建运行: POST /api/validation/circuit/runs，启动: POST /runs/{'{id}'}/start
      </div>
    </div>
  )
}
