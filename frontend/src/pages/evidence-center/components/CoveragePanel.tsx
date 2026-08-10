import type { CoverageSummary, Direction } from './types'
import { COMPONENT_LABEL, DIRECTION_LABEL } from './types'

interface Props {
  coverage: CoverageSummary
  direction: Direction
}

export function CoveragePanel({ coverage, direction }: Props) {
  const all = [...new Set([...coverage.required_components, ...coverage.supported_components, ...coverage.contradicted_components])]
  return (
    <div className="ew-section" data-testid="ew-coverage-panel">
      <h4>Claim 覆盖情况</h4>
      <div className="ew-coverage-list">
        {all.map(comp => {
          const supported = coverage.supported_components.includes(comp)
          const contradicted = coverage.contradicted_components.includes(comp)
          return (
            <div key={comp} className="ew-coverage-row">
              <span>{COMPONENT_LABEL[comp] ?? comp}</span>
              <span className={supported ? 'ew-ok' : contradicted ? 'ew-bad' : 'ew-meta'}>
                {supported ? '✓' : contradicted ? '✕ 存在反驳' : '○ 未覆盖'}
              </span>
            </div>
          )
        })}
      </div>
      <div className="ew-meta">{coverage.supported_components.length} / {coverage.required_components.length} 已覆盖</div>
      <div className="ew-overall">论文整体判断：{DIRECTION_LABEL[direction]}</div>
      {coverage.has_conflict && (
        <div className="ew-bad">
          论文中存在相互冲突或不同组件方向不一致的证据，系统不会自动提高置信度，需要人工确认。
        </div>
      )}
      {!coverage.full_claim_supported && !coverage.has_conflict && (
        <div className="ew-meta">尚未完整覆盖 Claim 的全部必需组件（{coverage.uncovered_components.join('、') || '—'}）。</div>
      )}
    </div>
  )
}
