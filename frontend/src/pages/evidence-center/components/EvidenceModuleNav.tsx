import type { ModuleKey } from '../EvidenceCenterContext'
import { useEvidenceCenter } from '../EvidenceCenterContext'

/** 五模块导航顺序(模块切换唯一入口) */
export const EVIDENCE_MODULES: ModuleKey[] = ['tasks', 'papers', 'candidates', 'review', 'promotion']

/**
 * 模块导航胶囊:选中 = 蓝色实底白字,未选 = 浅灰底深灰字。
 * 从 EvidenceCenterHeader 拆出,保持原 data-testid/className 契约。
 */
export function EvidenceModuleNav({ moduleTitles }: { moduleTitles: Record<ModuleKey, string> }) {
  const { state, gotoModule } = useEvidenceCenter()
  return (
    <div className="evidence-module-nav" data-testid="evidence-module-nav">
      {EVIDENCE_MODULES.map(m => (
        <button
          key={m}
          type="button"
          className={`evidence-module-btn${state.module === m ? ' active' : ''}`}
          aria-current={state.module === m ? 'page' : undefined}
          onClick={() => gotoModule(m)}
        >
          {moduleTitles[m]}
        </button>
      ))}
    </div>
  )
}
