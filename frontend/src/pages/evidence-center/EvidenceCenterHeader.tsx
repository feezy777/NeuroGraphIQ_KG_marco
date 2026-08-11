import type { ModuleKey } from './EvidenceCenterContext'
import { EvidenceModuleNav } from './components/EvidenceModuleNav'

/** 页面顶部白卡:承载五模块导航胶囊 */
export function EvidenceCenterHeader({ moduleTitles }: { moduleTitles: Record<ModuleKey, string> }) {
  return (
    <div className="evidence-center-header">
      <EvidenceModuleNav moduleTitles={moduleTitles} />
    </div>
  )
}
