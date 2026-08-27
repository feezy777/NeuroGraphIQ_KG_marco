import { useEffect, useMemo, useState } from 'react'
import { listPaperEvidenceTasks } from '../../api/endpoints'
import { EvidenceCenterProvider, useEvidenceCenter, type ModuleKey } from './EvidenceCenterContext'
import { SelectedValidationTaskProvider, useSelectedValidationTask } from './SelectedValidationTaskContext'
import { EvidenceCenterHeader } from './EvidenceCenterHeader'
import { ClaimSummaryPanel } from './components/ClaimSummaryPanel'
import { composeClaimSentence, ContextBar } from './components/ContextBar'
import { ObjectQueue } from './components/ObjectQueue'
import { RightPanel } from './components/RightPanel'
import { TaskItemsRefreshProvider } from './components/taskItemsRefreshContext'
import { StepPills } from './components/StepPills'
import { QUEUE_STATUS_LABEL } from './components/types'
import { TaskFilterPreviewPanel } from './components/TaskFilterPreviewPanel'
import { EvidenceCandidatesModule } from './modules/EvidenceCandidatesModule'
import { EvidencePromotionModule } from './modules/EvidencePromotionModule'
import { EvidenceReviewModule } from './modules/EvidenceReviewModule'
import { EvidenceTasksModule } from './modules/EvidenceTasksModule'
import { PaperLibraryModule } from './modules/PaperLibraryModule'
import { MacroCandidatesProvider } from '../validation-center/macro-governance/useMacroCandidates'

const MODULE_TITLE: Record<ModuleKey, string> = {
  tasks: '佐证任务',
  papers: '论文库',
  candidates: '证据候选',
  review: '人工审核',
  promotion: '证据晋升',
}
const MODULE_HINT: Record<ModuleKey, string> = {
  tasks: '哪些知识对象需要论文佐证，以及任务处理到哪里。',
  papers: '管理系统已经获取和解析的真实论文资源。',
  candidates: '查看 DeepSeek 从论文中提取出的候选佐证原文。',
  review: '人工确认候选原文是否足以证明当前知识事实。',
  promotion: '将审核通过的论文证据正式应用到知识图谱。',
}

function EvidenceCenterBody({ embedded }: { embedded?: boolean }) {
  const { state, queue, openTarget, progress, candidateClaim } = useEvidenceCenter()
  const { selectedTask } = useSelectedValidationTask()
  const [taskName, setTaskName] = useState<string | null>(null)

  // 任务名:从 tasks 列表按 state.taskId 推导(ContextBar 展示用)
  useEffect(() => {
    if (!state.taskId) {
      setTaskName(null)
      return
    }
    let cancelled = false
    listPaperEvidenceTasks({ limit: 50 })
      .then(r => {
        const t = r.items.find(x => x.id === state.taskId)
        if (!cancelled) setTaskName(t?.name || t?.target_type || null)
      })
      .catch(() => { if (!cancelled) setTaskName(null) })
    return () => { cancelled = true }
  }, [state.taskId])

  const currentIndex = useMemo(() => {
    if (queue.length === 0) return -1
    const idx = queue.findIndex(q => q.target_type === state.targetType && q.target_id === state.targetId)
    return idx >= 0 ? idx : 0
  }, [queue, state.targetType, state.targetId])

  const current = currentIndex >= 0 ? queue[currentIndex] : null
  const isPapers = state.module === 'papers'

  // ContextBar 完整事实句:优先候选模块推送的 claim(组件拼装),其余模块回退当前队列对象 label
  const claimSentence = useMemo(
    () => composeClaimSentence(candidateClaim?.claimText ?? '', candidateClaim?.components ?? [], current?.label ?? null),
    [candidateClaim, current],
  )

  return (
    <>
      {/* 嵌入模式下隐藏 ContextBar 和 StepPills,由验证中心 Tab 提供顶层导航 */}
      {!embedded && (
        <>
          <ContextBar
            targetLabel={current?.label ?? null}
            targetType={current?.target_type ?? null}
            granularity={current?.granularity ?? null}
            confidence={current?.confidence ?? null}
            evidenceCount={current?.evidenceCount ?? null}
            taskName={taskName}
            queueIndex={currentIndex}
            queueTotal={queue.length}
            taskStatus={current ? (QUEUE_STATUS_LABEL[current.status] ?? current.status) : null}
            claimSentence={claimSentence}
            onBackToDataCenter={() => { window.location.hash = '#/data-center' }}
            onRefresh={() => { window.location.reload() }}
          />
          <StepPills module={state.module} progress={progress} />
        </>
      )}
      <div
        className={
          'evidence-center-layout'
          + (isPapers ? ' evidence-center-layout-full' : '')
          + (state.module === 'candidates' && selectedTask?.sourceType === 'paper_discovery'
            ? ' evidence-center-layout-macro' : '')
        }
        data-testid="evidence-center-layout"
      >
        {!isPapers && (
          <aside className="evidence-left">
            {state.module === 'tasks' ? (
              <TaskFilterPreviewPanel />
            ) : state.module === 'review' || state.module === 'promotion' ? (
              <ObjectQueue
                queue={queue}
                currentIndex={currentIndex}
                onSelect={e => openTarget(
                  e.target_type,
                  e.target_id,
                  // 审核/晋升模块内切换队列项时留在当前模块,其余模块统一回候选视图
                  state.module === 'review' || state.module === 'promotion' ? state.module : 'candidates',
                )}
              />
            ) : (
              <ClaimSummaryPanel
                claimText={candidateClaim?.claimText ?? ''}
                components={candidateClaim?.components ?? []}
                targetType={candidateClaim?.targetType ?? ''}
                granularity={candidateClaim?.granularity ?? null}
              />
            )}
          </aside>
        )}
        <main className="evidence-main">
          <div className="evidence-module-hint">
            {state.module === 'candidates' && selectedTask?.sourceType === 'paper_discovery'
              ? '从论文发现线索到证据候选:论文检索 → 函数片段筛选 → AI 语义审核 → 候选证据。'
              : MODULE_HINT[state.module]}
          </div>
          {state.module === 'tasks' && <EvidenceTasksModule />}
          {state.module === 'papers' && <PaperLibraryModule />}
          {state.module === 'candidates' && <EvidenceCandidatesModule />}
          {state.module === 'review' && <EvidenceReviewModule />}
          {state.module === 'promotion' && <EvidencePromotionModule />}
        </main>
        {!isPapers && (
          <aside className="evidence-right">
            <RightPanel module={state.module} />
          </aside>
        )}
      </div>
    </>
  )
}

export function EvidenceCenterPage({ embedded }: { embedded?: boolean }) {
  return (
    <EvidenceCenterProvider embedded={embedded}>
      <SelectedValidationTaskProvider>
      <TaskItemsRefreshProvider>
      <div className="evidence-center" data-testid="evidence-center">
        {embedded ? (
          <MacroCandidatesProvider>
            <div className="evidence-module-nav" data-testid="evidence-module-nav" style={{ marginBottom: 12 }}>
              {(['tasks', 'papers', 'candidates', 'review', 'promotion'] as ModuleKey[]).map(m => (
                <EvidenceModuleNavButton key={m} moduleKey={m} />
              ))}
            </div>
            <EvidenceCenterBody embedded />
          </MacroCandidatesProvider>
        ) : (
          <>
            <EvidenceCenterHeader moduleTitles={MODULE_TITLE} />
            <EvidenceCenterBody />
          </>
        )}
      </div>
      </TaskItemsRefreshProvider>
      </SelectedValidationTaskProvider>
    </EvidenceCenterProvider>
  )
}

function EvidenceModuleNavButton({ moduleKey }: { moduleKey: ModuleKey }) {
  const { state, gotoModule } = useEvidenceCenter()
  return (
    <button
      type="button"
      className={`evidence-module-btn${state.module === moduleKey ? ' active' : ''}`}
      aria-current={state.module === moduleKey ? 'page' : undefined}
      onClick={() => gotoModule(moduleKey)}
    >
      {MODULE_TITLE[moduleKey]}
    </button>
  )
}

export default EvidenceCenterPage
