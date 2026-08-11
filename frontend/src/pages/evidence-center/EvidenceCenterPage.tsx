import { useEffect, useMemo, useState } from 'react'
import { listPaperEvidenceTasks } from '../../api/endpoints'
import { EvidenceCenterProvider, useEvidenceCenter, type ModuleKey } from './EvidenceCenterContext'
import { EvidenceCenterHeader } from './EvidenceCenterHeader'
import { ClaimView } from './components/ClaimView'
import { ContextBar } from './components/ContextBar'
import { ObjectQueue } from './components/ObjectQueue'
import { RightPanel } from './components/RightPanel'
import { StepPills } from './components/StepPills'
import { QUEUE_STATUS_LABEL } from './components/types'
import { EvidenceCandidatesModule } from './modules/EvidenceCandidatesModule'
import { EvidencePromotionModule } from './modules/EvidencePromotionModule'
import { EvidenceReviewModule } from './modules/EvidenceReviewModule'
import { EvidenceTasksModule } from './modules/EvidenceTasksModule'
import { PaperLibraryModule } from './modules/PaperLibraryModule'

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

function EvidenceCenterBody() {
  const { state, queue, openTarget, progress, candidateClaim } = useEvidenceCenter()
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

  return (
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
        onBackToDataCenter={() => { window.location.hash = '#/data-center' }}
        onRefresh={() => { window.location.reload() }}
      />
      <StepPills module={state.module} progress={progress} />
      <div className={`evidence-center-layout${isPapers ? ' evidence-center-layout-full' : ''}`} data-testid="evidence-center-layout">
        {!isPapers && (
          <aside className="evidence-left">
            {state.module === 'candidates' ? (
              // 候选模块左栏 = 当前对象验证事实(ClaimView);队列移到右栏
              <ClaimView
                claimText={candidateClaim?.claimText ?? ''}
                components={candidateClaim?.components ?? []}
                targetType={candidateClaim?.targetType ?? ''}
              />
            ) : (
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
            )}
          </aside>
        )}
        <main className="evidence-main">
          <div className="evidence-module-hint">{MODULE_HINT[state.module]}</div>
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

export function EvidenceCenterPage() {
  return (
    <EvidenceCenterProvider>
      <div className="evidence-center" data-testid="evidence-center">
        <EvidenceCenterHeader moduleTitles={MODULE_TITLE} />
        <EvidenceCenterBody />
      </div>
    </EvidenceCenterProvider>
  )
}

export default EvidenceCenterPage
