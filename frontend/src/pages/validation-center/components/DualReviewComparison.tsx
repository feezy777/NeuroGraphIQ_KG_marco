import type { CircuitValidationResult } from '../validationCenterTypes'

interface Props { result: CircuitValidationResult }
export function DualReviewComparison({ result }: Props) {
  return (
    <div className="vw-dual-grid">
      <div className="vw-dual-col">
        <div className="vw-dual-label">Reviewer A ({result.reviewer_a_decision || '—'})</div>
        <div className="vw-dual-card">
          <div className="vw-dual-row">
            <span>决策</span>
            <span className={result.reviewer_a_decision === 'support' ? 'vw-c-green' : 'vw-c-red'}>
              {result.reviewer_a_decision || '—'}
            </span>
          </div>
          <div className="vw-dual-row">
            <span>置信度</span>
            <span>{result.reviewer_a_confidence?.toFixed(2) ?? '—'}</span>
          </div>
        </div>
      </div>
      <div className="vw-dual-col">
        <div className="vw-dual-label">Reviewer B ({result.reviewer_b_decision || '—'})</div>
        <div className="vw-dual-card">
          <div className="vw-dual-row">
            <span>决策</span>
            <span className={result.reviewer_b_decision === 'support' ? 'vw-c-green' : 'vw-c-red'}>
              {result.reviewer_b_decision || '—'}
            </span>
          </div>
          <div className="vw-dual-row">
            <span>置信度</span>
            <span>{result.reviewer_b_confidence?.toFixed(2) ?? '—'}</span>
          </div>
        </div>
      </div>
    </div>
  )
}
