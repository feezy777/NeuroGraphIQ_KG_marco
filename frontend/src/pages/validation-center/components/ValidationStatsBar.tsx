import { useEffect, useState } from 'react'

interface Counts {
  total_runs: number; completed_runs: number; pending_review: number
  rule_passed: number; dual_agreement: number; promoted: number
  total_circuits?: number; total_steps?: number; rule_checked?: number
}

interface Props { granularityLevel?: string }
export function ValidationStatsBar({ granularityLevel }: Props) {
  const [counts, setCounts] = useState<Counts | null>(null)
  const [error, setError] = useState(false)

  useEffect(() => {
    const params = granularityLevel ? `?granularity_level=${encodeURIComponent(granularityLevel)}` : ''
    fetch(`/api/validation/circuit/counts${params}`)
      .then(r => { if (!r.ok) throw new Error(); return r.json() })
      .then(setCounts).catch(() => setError(true))
  }, [granularityLevel])

  const items = [
    { label: '验证运行', value: counts?.total_runs ?? '-' },
    { label: '已完成', value: counts?.completed_runs ?? '-' },
    { label: '回路数', value: counts?.total_circuits ?? '-' },
    { label: '步骤数', value: counts?.total_steps ?? '-' },
    { label: '规则通过', value: counts?.rule_passed ?? '-' },
    { label: '已校验', value: counts?.rule_checked ?? '-' },
    { label: '待审核', value: counts?.pending_review ?? '-' },
  ]

  return (
    <div className="vw-stats">
      {items.map(item => (
        <div key={item.label} className="vw-stat">
          <span className="vw-stat-num">{error ? '!' : item.value}</span>
          <span className="vw-stat-label">{item.label}</span>
        </div>
      ))}
    </div>
  )
}
