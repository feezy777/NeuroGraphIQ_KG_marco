import { useMemo } from 'react'
import { useEvidenceCenter, type ModuleKey } from '../EvidenceCenterContext'
import { EvidenceQueuePanel } from './EvidenceQueuePanel'
import { ObjectQueue } from './ObjectQueue'
import { PassageSummary } from './PassageSummary'
import { PromotionImpact } from './PromotionImpact'
import { ReviewerDecisionPanel } from './ReviewerDecisionPanel'
import { TaskProcessedPanel } from './TaskProcessedPanel'

const RIGHT_TITLES: Record<ModuleKey, string> = {
  tasks: '任务与队列概览',
  papers: '论文详情',
  candidates: '待处理对象队列',
  review: '人工审核',
  promotion: '晋升确认',
}

/** 右栏插槽:佐证任务渲染 TaskSummary,候选模块渲染 ObjectQueue(队列),审核模块渲染 ReviewerDecisionPanel,晋升模块渲染 PromotionImpact */
export function RightPanel({ module }: { module: ModuleKey }) {
  const {
    state,
    queue,
    reviewDecision,
    promotionImpact,
    candidatePassages,
    viewCandidatePaper,
    candidateSelectedHashes,
    toggleCandidatePassage,
    selectAllCandidatePassages,
    enterReviewFromPassages,
    openTarget,
  } = useEvidenceCenter()

  // 候选模块右栏队列的当前对象下标(与页面左栏队列同逻辑;仅 candidates 分支使用)
  const candidateQueueIndex = useMemo(() => {
    if (queue.length === 0) return -1
    const idx = queue.findIndex(q => q.target_type === state.targetType && q.target_id === state.targetId)
    return idx >= 0 ? idx : 0
  }, [queue, state.targetType, state.targetId])

  if (module === 'tasks') {
    return (
      <aside className="evidence-right-panel" data-testid="evidence-right-panel">
        <TaskProcessedPanel />
      </aside>
    )
  }

  if (module === 'candidates') {
    // 候选模块右栏 = 待处理对象队列(Top) + 候选佐证原文片段聚合(Bottom)
    return (
      <aside className="evidence-right-panel" data-testid="evidence-right-panel">
        <EvidenceQueuePanel
          queue={queue}
          currentIndex={candidateQueueIndex}
          onSelect={e => openTarget(e.target_type, e.target_id, 'candidates')}
        />
        <PassageSummary
          passages={candidatePassages}
          onViewPaper={viewCandidatePaper}
          selectedHashes={candidateSelectedHashes}
          onToggleSelect={toggleCandidatePassage}
          onSelectAll={selectAllCandidatePassages}
          onEnterReview={enterReviewFromPassages}
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
