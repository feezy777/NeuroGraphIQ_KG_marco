import { useEffect, useState } from 'react'
import { useData } from '../../../hooks/useData'

interface Props { granularityLevel?: string }

interface CountsResponse {
  mirrorConnections: number; mirrorFunctions: number; mirrorCircuits: number; mirrorTriples: number
  macroCircuitSteps: number; macroProjectionFunctions: number; macroMemberships: number
  macroCrossResults: number; macroDualResults: number
  finalCircuits: number; finalProjections: number; finalSteps: number; finalFunctions: number; finalTriples: number
  pendingReview: number; ruleChecked: number; promotionReady: number
  hasApiError: boolean; warnings: string[]
}

export function ValidationStatsBar({ granularityLevel }: Props) {
  const [counts, setCounts] = useState<CountsResponse | null>(null)
  const { data, loading } = useData<CountsResponse>(
    () => fetch('/api/validation/circuit/counts').then(r => r.json()),
    [granularityLevel],
  )

  useEffect(() => {
    if (data) setCounts(data)
  }, [data])

  const items = [
    { label: 'Mirror Connections', value: counts?.mirrorConnections ?? '-' },
    { label: 'Mirror Circuits', value: counts?.mirrorCircuits ?? '-' },
    { label: 'Final Circuits', value: counts?.finalCircuits ?? '-' },
    { label: 'Pending Review', value: counts?.pendingReview ?? '-' },
    { label: 'Promotion Ready', value: counts?.promotionReady ?? '-' },
  ]

  return (
    <div className="vw-stats-bar">
      {loading && <span className="vw-stats-loading">Loading...</span>}
      {!loading && items.map(item => (
        <div key={item.label} className="vw-stat-item">
          <span className="vw-stat-value">{item.value}</span>
          <span className="vw-stat-label">{item.label}</span>
        </div>
      ))}
    </div>
  )
}
