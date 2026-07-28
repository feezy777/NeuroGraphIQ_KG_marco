import { useState, useEffect } from 'react'
import { listCircuitValidationRuns, type CircuitValidationRun } from '../../../api/endpoints'

interface Props { granularityLevel?: string }
export function ValidationOverviewPanel({ granularityLevel }: Props) {
  const [runs, setRuns] = useState<CircuitValidationRun[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    listCircuitValidationRuns({ limit: 10 })
      .then(r => { setRuns(r.items as CircuitValidationRun[]); setLoading(false) })
      .catch(() => setLoading(false))
  }, [granularityLevel])

  return (
    <div style={{ padding: 20 }}>
      <h3>最近验证运行</h3>
      {loading ? <p>加载中…</p> : runs.length === 0 ? <p>暂无验证运行</p> : (
        <table className="vr-table">
          <thead><tr><th>ID</th><th>状态</th><th>规则</th><th>双模型</th><th>时间</th></tr></thead>
          <tbody>
            {runs.map(r => (
              <tr key={r.id}>
                <td>{r.id.slice(0, 8)}</td>
                <td>{r.status}</td>
                <td>{r.rule_passed_count}/{r.rule_total_count}</td>
                <td>{r.dual_review_agreement_count}/{r.dual_review_total_count || '-'}</td>
                <td>{r.created_at?.slice(0, 16)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}
