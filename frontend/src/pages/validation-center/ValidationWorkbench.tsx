import { useState } from 'react'
import { useI18n } from '../../i18n-context'
import { ValidationStatsBar } from './components/ValidationStatsBar'
import { CandidateCircuitTable } from './components/CandidateCircuitTable'

interface Props { granularityLevel?: string }
export function ValidationWorkbench({ granularityLevel }: Props) {
  const { t } = useI18n()

  return (
    <div className="vw-root">
      <ValidationStatsBar granularityLevel={granularityLevel} />
      <div style={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
        <CandidateCircuitTable granularityLevel={granularityLevel} />
      </div>
    </div>
  )
}
