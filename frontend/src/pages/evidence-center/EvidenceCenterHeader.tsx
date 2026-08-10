import type { ModuleKey } from './EvidenceCenterContext'
import { useEvidenceCenter } from './EvidenceCenterContext'

export function EvidenceCenterHeader({ moduleTitles }: { moduleTitles: Record<ModuleKey, string> }) {
  const { state, gotoModule } = useEvidenceCenter()
  const MODULES: ModuleKey[] = ['tasks', 'papers', 'candidates', 'review', 'promotion']
  return (
    <div className="evidence-center-header">
      <div className="evidence-module-nav">
        {MODULES.map(m => (
          <button key={m} type="button"
            className={`evidence-module-btn${state.module === m ? ' active' : ''}`}
            onClick={() => gotoModule(m)}>
            {moduleTitles[m]}
          </button>
        ))}
      </div>
      <button type="button" className="btn btn-sm" onClick={() => { window.location.hash = '#/data-center' }}>返回数据中心</button>
    </div>
  )
}
