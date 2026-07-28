import { useState } from 'react'
import { useI18n } from '../../i18n-context'
import { ValidationStatsBar } from './components/ValidationStatsBar'
import { CandidateCircuitTable } from './components/CandidateCircuitTable'
import { DualReviewPanel } from './components/DualReviewPanel'
import { HumanReviewPanel } from './components/HumanReviewPanel'
import { PromotionPanel } from './components/PromotionPanel'

const TABS = [
  { key: 'candidates', label: '候选回路' },
  { key: 'dual_review', label: '双模型盲审' },
  { key: 'human_review', label: '人工审核' },
  { key: 'promotion', label: '晋升管理' },
]

interface Props { granularityLevel?: string }
export function ValidationWorkbench({ granularityLevel }: Props) {
  const { t } = useI18n()
  const [tab, setTab] = useState('candidates')

  return (
    <div className="vw-root">
      <ValidationStatsBar granularityLevel={granularityLevel} />
      <div className="vr-header">
        <div className="vr-tabs">
          {TABS.map(t => (
            <button
              key={t.key}
              className={`vr-tab${tab === t.key ? ' active' : ''}`}
              onClick={() => setTab(t.key)}
            >
              {t.label}
            </button>
          ))}
        </div>
      </div>
      <div style={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
        {tab === 'candidates' && <CandidateCircuitTable granularityLevel={granularityLevel} />}
        {tab === 'dual_review' && <DualReviewPanel granularityLevel={granularityLevel} />}
        {tab === 'human_review' && <HumanReviewPanel granularityLevel={granularityLevel} />}
        {tab === 'promotion' && <PromotionPanel granularityLevel={granularityLevel} />}
      </div>
    </div>
  )
}
