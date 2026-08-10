import { useEvidenceCenter, type ModuleKey } from '../EvidenceCenterContext'
import { CandidateSummary } from './CandidateSummary'
import { ReviewerDecisionPanel } from './ReviewerDecisionPanel'

const RIGHT_TITLES: Record<ModuleKey, string> = {
  tasks: '任务与队列概览',
  papers: '论文详情',
  candidates: '检索与候选',
  review: '人工审核',
  promotion: '晋升确认',
}

/** 右栏插槽:候选模块渲染 CandidateSummary,审核模块渲染 ReviewerDecisionPanel,其余模块暂为占位标题 */
export function RightPanel({ module }: { module: ModuleKey }) {
  const { state, candidateSummary, reviewDecision, openTarget } = useEvidenceCenter()

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

  if (module === 'review') {
    return (
      <aside className="evidence-right-panel" data-testid="evidence-right-panel">
        {reviewDecision ? (
          <ReviewerDecisionPanel {...reviewDecision} />
        ) : (
          <>
            <h4>人工审核</h4>
            <p className="evidence-module-hint">进入目标对象后，此处显示人工审核决策面板。</p>
          </>
        )}
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
