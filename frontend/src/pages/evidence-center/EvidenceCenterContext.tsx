import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import type { PromotionImpactState } from './components/PromotionImpact'
import type { ReviewDecisionState } from './components/ReviewerDecisionPanel'
import type { TaskSummaryActions, TaskSummaryData } from './components/TaskSummary'
import type { ClaimComponent, QueueEntry } from './components/types'
import { buildEvidenceUrl, parseEvidenceUrl, type EvidenceCenterState } from './evidenceCenterUrl'

export type ModuleKey = 'tasks' | 'papers' | 'candidates' | 'review' | 'promotion'

/** 对象实际处理进度(StepPills 数据源;对象级,openTask/openTarget 切换对象时重置为全 false) */
export interface ObjectProgress {
  searched: boolean
  extracted: boolean
  reviewed: boolean
  promoted: boolean
}

export const INITIAL_OBJECT_PROGRESS: ObjectProgress = {
  searched: false,
  extracted: false,
  reviewed: false,
  promoted: false,
}

interface EvidenceCenterContextValue {
  state: EvidenceCenterState
  queue: QueueEntry[]
  setQueue: (q: QueueEntry[]) => void
  /** 当前对象的处理进度(StepPills 由 module + progress 推导) */
  progress: ObjectProgress
  /** 推进当前对象进度(仅置位,永不回退;切换对象时由 openTask/openTarget 重置) */
  setProgress: (patch: Partial<ObjectProgress>) => void
  gotoModule: (m: ModuleKey) => void
  openTask: (taskId: string) => void
  openTarget: (targetType: string, targetId: string, module?: ModuleKey) => void
  selectPaper: (paperId: string | null) => void
  /** 候选模块推送的当前对象验证事实(仅 candidates 模块使用,页面左栏渲染 ClaimView) */
  candidateClaim: {
    claimText: string
    components: ClaimComponent[]
    granularity: string | null
    targetType: string
  } | null
  setCandidateClaim: (c: { claimText: string; components: ClaimComponent[]; granularity: string | null; targetType: string } | null) => void
  /** 审核模块推送的人工审核决策状态(仅 review 模块使用,RightPanel 渲染 ReviewerDecisionPanel) */
  reviewDecision: ReviewDecisionState | null
  setReviewDecision: (s: ReviewDecisionState | null) => void
  /** 晋升模块推送的晋升影响状态(仅 promotion 模块使用,RightPanel 渲染 PromotionImpact) */
  promotionImpact: PromotionImpactState | null
  setPromotionImpact: (s: PromotionImpactState | null) => void
  /** 佐证任务模块推送的选中任务摘要(仅 tasks 模块使用,RightPanel 渲染 TaskSummary) */
  taskSummary: TaskSummaryData | null
  setTaskSummary: (s: TaskSummaryData | null) => void
  /** 佐证任务模块注册的右栏操作(创建批量预处理/刷新;对话框与列表都在模块内) */
  taskSummaryActions: TaskSummaryActions
  setTaskSummaryActions: (a: TaskSummaryActions) => void
}

const EvidenceCenterContext = createContext<EvidenceCenterContextValue | null>(null)

export function EvidenceCenterProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<EvidenceCenterState>(() => parseEvidenceUrl(window.location.hash))
  const [queue, setQueue] = useState<QueueEntry[]>([])
  const [progress, setProgressState] = useState<ObjectProgress>(INITIAL_OBJECT_PROGRESS)
  const [candidateClaim, setCandidateClaim] = useState<{
    claimText: string
    components: ClaimComponent[]
    granularity: string | null
    targetType: string
  } | null>(null)
  const [reviewDecision, setReviewDecision] = useState<ReviewDecisionState | null>(null)
  const [promotionImpact, setPromotionImpact] = useState<PromotionImpactState | null>(null)
  const [taskSummary, setTaskSummary] = useState<TaskSummaryData | null>(null)
  const [taskSummaryActions, setTaskSummaryActions] = useState<TaskSummaryActions>({
    onCreateBatch: () => {},
    onRefresh: () => {},
  })

  useEffect(() => {
    const handler = () => setState(parseEvidenceUrl(window.location.hash))
    window.addEventListener('hashchange', handler)
    return () => window.removeEventListener('hashchange', handler)
  }, [])

  const apply = useCallback((patch: Partial<EvidenceCenterState>) => {
    setState(prev => {
      const next = { ...prev, ...patch }
      const url = buildEvidenceUrl(next)
      if (window.location.hash !== url) window.location.hash = url
      return next
    })
  }, [])

  // 导航回调必须 useCallback 稳定引用:消费方(如晋升模块)把 openTarget 放入 useCallback/memo 依赖,
  // 内联箭头会随 context value 每次重建 → 下游 memo 每渲染重建 → effect 推送 context → 无限循环
  const gotoModule = useCallback((m: ModuleKey) => apply({ module: m }), [apply])
  // 对象级进度:仅置位推进(模块各自 setProgress),切换对象时重置为全 false
  const setProgress = useCallback((patch: Partial<ObjectProgress>) => {
    setProgressState(prev => ({ ...prev, ...patch }))
  }, [])
  // 打开新任务必须清除上一任务的 target(否则 URL 残留陈旧 target,审核/晋升会打开错误对象)
  const openTask = useCallback(
    (taskId: string) => {
      apply({ taskId, targetType: null, targetId: null, module: 'candidates' })
      setProgressState(INITIAL_OBJECT_PROGRESS)
    },
    [apply],
  )
  const openTarget = useCallback(
    (targetType: string, targetId: string, module: ModuleKey = 'candidates') => {
      apply({ targetType, targetId, module })
      setProgressState(INITIAL_OBJECT_PROGRESS)
    },
    [apply],
  )
  const selectPaper = useCallback((paperId: string | null) => apply({ paperId }), [apply])

  const value = useMemo<EvidenceCenterContextValue>(() => ({
    state,
    queue,
    setQueue,
    progress,
    setProgress,
    gotoModule,
    openTask,
    openTarget,
    selectPaper,
    candidateClaim,
    setCandidateClaim,
    reviewDecision,
    setReviewDecision,
    promotionImpact,
    setPromotionImpact,
    taskSummary,
    setTaskSummary,
    taskSummaryActions,
    setTaskSummaryActions,
  }), [state, queue, progress, setProgress, gotoModule, openTask, openTarget, selectPaper, candidateClaim, reviewDecision, promotionImpact, taskSummary, taskSummaryActions])

  return <EvidenceCenterContext.Provider value={value}>{children}</EvidenceCenterContext.Provider>
}

export function useEvidenceCenter(): EvidenceCenterContextValue {
  const ctx = useContext(EvidenceCenterContext)
  if (!ctx) throw new Error('useEvidenceCenter must be used within EvidenceCenterProvider')
  return ctx
}
