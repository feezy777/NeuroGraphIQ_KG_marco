import type { ClaimComponent } from './types'
import { COMPONENT_LABEL } from './types'

interface Props {
  claimText: string
  components: ClaimComponent[]
  confidence: number | null
  evidenceCount: number
  targetType: string
  granularity: string
}

export function ClaimPanel({ claimText, components, confidence, evidenceCount, targetType, granularity }: Props) {
  return (
    <div className="ew-section ew-claim-panel" data-testid="ew-claim-panel">
      <h4>当前需要验证的事实</h4>
      <p className="ew-claim-text">{claimText || '—'}</p>
      <div className="ew-claim-meta">
        <span className="ew-meta">{targetType} · {granularity || '—'}</span>
        <span className="ew-meta">当前置信度 {confidence ?? '—'}</span>
        <span className="ew-meta">已有论文证据 {evidenceCount}</span>
      </div>
      <div className="ew-components">
        {components.map(c => (
          <span key={c.component_type} className={`ew-component-chip${c.required ? '' : ' ew-component-optional'}`}>
            <b>{COMPONENT_LABEL[c.component_type] ?? c.component_type}</b>
            <span>{c.statement}</span>
            {!c.required && <em>辅助上下文</em>}
          </span>
        ))}
      </div>
    </div>
  )
}
