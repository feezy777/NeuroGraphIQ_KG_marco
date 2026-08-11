import { useMemo } from 'react'
import { useEvidenceCenter, type ModuleKey } from '../EvidenceCenterContext'
import { EvidenceQueuePanel } from './EvidenceQueuePanel'
import { ObjectQueue } from './ObjectQueue'
import { PromotionImpact } from './PromotionImpact'
import { ReviewerDecisionPanel } from './ReviewerDecisionPanel'
import { TaskSummary } from './TaskSummary'

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
    taskSummary,
    taskSummaryActions,
    reviewDecision,
    promotionImpact,
    openTarget,
    openTask,
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
    // 候选模块右栏 = 待处理对象队列(视觉稿版:状态 Tabs + 数量徽标 + 空态;队列已从页面左栏移到右栏,左栏改渲染 ClaimSummaryPanel)
    return (
      <aside className="evidence-right-panel" data-testid="evidence-right-panel">
        <EvidenceQueuePanel
          queue={queue}
          currentIndex={candidateQueueIndex}
          onSelect={e => openTarget(e.target_type, e.target_id, 'candidates')}
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
