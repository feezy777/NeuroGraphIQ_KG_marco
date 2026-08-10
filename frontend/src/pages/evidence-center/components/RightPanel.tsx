import { useEvidenceCenter, type ModuleKey } from '../EvidenceCenterContext'
import { CandidateSummary } from './CandidateSummary'
import { PromotionImpact } from './PromotionImpact'
import { ReviewerDecisionPanel } from './ReviewerDecisionPanel'
import { TaskSummary } from './TaskSummary'

const RIGHT_TITLES: Record<ModuleKey, string> = {
  tasks: '任务与队列概览',
  papers: '论文详情',
  candidates: '检索与候选',
  review: '人工审核',
  promotion: '晋升确认',
}

/** 右栏插槽:佐证任务渲染 TaskSummary,候选模块渲染 CandidateSummary,审核模块渲染 ReviewerDecisionPanel,晋升模块渲染 PromotionImpact */
export function RightPanel({ module }: { module: ModuleKey }) {
  const {
    state,
    taskSummary,
    taskSummaryActions,
    candidateSummary,
    reviewDecision,
    promotionImpact,
    openTarget,
    openTask,
  } = useEvidenceCenter()

  if (module === 'tasks') {
    return (
      <aside className="evidence-right-panel" data-testid="evidence-right-panel">
        <TaskSummary
          data={taskSummary}
          onStartReview={() => {
            if (taskSummary) openTask(taskSummary.id)
          }}
          onCreateBatch={taskSummaryActions.onCreateBatch}
          onRefresh={taskSummaryActions.onRefresh}
        />
      </aside>
    )
  }

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

  if (module === 'promotion') {
    return (
      <aside className="evidence-right-panel" data-testid="evidence-right-panel">
        {promotionImpact ? (
          <PromotionImpact {...promotionImpact} />
        ) : (
          <>
            <h4>晋升确认</h4>
            <p className="evidence-module-hint">进入目标对象后，此处显示晋升影响与确认操作。</p>
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
