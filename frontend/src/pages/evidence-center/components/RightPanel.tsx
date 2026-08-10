import { useEvidenceCenter, type ModuleKey } from '../EvidenceCenterContext'
import { CandidateSummary } from './CandidateSummary'

const RIGHT_TITLES: Record<ModuleKey, string> = {
  tasks: '任务与队列概览',
  papers: '论文详情',
  candidates: '检索与候选',
  review: '审核决策',
  promotion: '晋升确认',
}

/** 右栏插槽:候选模块渲染 CandidateSummary,其余模块暂为占位标题 */
export function RightPanel({ module }: { module: ModuleKey }) {
  const { state, candidateSummary, openTarget } = useEvidenceCenter()

  if (module === 'candidates') {
    return (
      <aside className="evidence-right-panel" data-testid="evidence-right-panel">
        <CandidateSummary
          data={candidateSummary}
          onEnterReview={() => {
            if (state.targetType && state.targetId) openTarget(state.targetType, state.targetId, 'review')
          }}
        />
      </aside>
    )
  }

  const title = RIGHT_TITLES[module]
  return (
    <aside className="evidence-right-panel" data-testid="evidence-right-panel">
      <h4>{title}</h4>
      <p className="evidence-module-hint">该面板将在后续迭代提供「{title}」相关内容。</p>
    </aside>
  )
}
