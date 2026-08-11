import { useState } from 'react'
import type { ClaimComponent } from './types'
import { COMPONENT_LABEL } from './types'

interface Props {
  claimText: string
  components: ClaimComponent[]
  targetType: string
}

/** Claim 区:当前需要验证的事实 + Claim 单行突出 + Component Chips(紧凑排布,可折叠) */
export function ClaimView({ claimText, components, targetType }: Props) {
  const [chipsCollapsed, setChipsCollapsed] = useState(false)
  return (
    <div className="evidence-claim" data-testid="evidence-claim">
      <div className="evidence-claim-head">
        <h4>当前需要验证的事实</h4>
        <div className="evidence-claim-head-actions">
          {components.length > 0 && (
            <button
              type="button"
              className="btn btn-xs"
              data-testid="evidence-claim-chips-toggle"
              onClick={() => setChipsCollapsed(c => !c)}
            >
              {chipsCollapsed ? `展开组件（${components.length}）` : '收起组件'}
            </button>
          )}
          <span className="ew-meta">{targetType}</span>
        </div>
      </div>
      <p className="evidence-claim-text" data-testid="evidence-claim-text">{claimText || '—'}</p>
      {!chipsCollapsed && components.length > 0 && (
        <div className="evidence-claim-chips">
          {components.map(c => (
            <span
              key={c.component_type}
              data-testid="evidence-claim-chip"
              className={`evidence-claim-chip${c.required ? '' : ' evidence-claim-chip-optional'}`}
            >
              <b>{COMPONENT_LABEL[c.component_type] ?? c.component_type}</b>
              <span>{c.statement}</span>
            </span>
          ))}
        </div>
      )}
    </div>
  )
}
