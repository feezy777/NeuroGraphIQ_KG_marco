import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import type { CandidateSummaryData } from './components/CandidateSummary'
import type { PromotionImpactState } from './components/PromotionImpact'
import type { ReviewDecisionState } from './components/ReviewerDecisionPanel'
import type { QueueEntry } from './components/types'
import { buildEvidenceUrl, parseEvidenceUrl, type EvidenceCenterState } from './evidenceCenterUrl'

export type ModuleKey = 'tasks' | 'papers' | 'candidates' | 'review' | 'promotion'

interface EvidenceCenterContextValue {
  state: EvidenceCenterState
  queue: QueueEntry[]
  setQueue: (q: QueueEntry[]) => void
  gotoModule: (m: ModuleKey) => void
  openTask: (taskId: string) => void
  openTarget: (targetType: string, targetId: string, module?: ModuleKey) => void
  selectPaper: (paperId: string | null) => void
  /** 候选模块推送的右栏摘要(仅 candidates 模块使用) */
  candidateSummary: CandidateSummaryData | null
  setCandidateSummary: (s: CandidateSummaryData | null) => void
  /** 审核模块推送的人工审核决策状态(仅 review 模块使用,RightPanel 渲染 ReviewerDecisionPanel) */
  reviewDecision: ReviewDecisionState | null
  setReviewDecision: (s: ReviewDecisionState | null) => void
  /** 晋升模块推送的晋升影响状态(仅 promotion 模块使用,RightPanel 渲染 PromotionImpact) */
  promotionImpact: PromotionImpactState | null
  setPromotionImpact: (s: PromotionImpactState | null) => void
}

const EvidenceCenterContext = createContext<EvidenceCenterContextValue | null>(null)

export function EvidenceCenterProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<EvidenceCenterState>(() => parseEvidenceUrl(window.location.hash))
  const [queue, setQueue] = useState<QueueEntry[]>([])
  const [candidateSummary, setCandidateSummary] = useState<CandidateSummaryData | null>(null)
  const [reviewDecision, setReviewDecision] = useState<ReviewDecisionState | null>(null)
  const [promotionImpact, setPromotionImpact] = useState<PromotionImpactState | null>(null)

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
  const openTask = useCallback((taskId: string) => apply({ taskId, module: 'candidates' }), [apply])
  const openTarget = useCallback(
    (targetType: string, targetId: string, module: ModuleKey = 'candidates') => apply({ targetType, targetId, module }),
    [apply],
  )
  const selectPaper = useCallback((paperId: string | null) => apply({ paperId }), [apply])

  const value = useMemo<EvidenceCenterContextValue>(() => ({
    state,
    queue,
    setQueue,
    gotoModule,
    openTask,
    openTarget,
    selectPaper,
    candidateSummary,
    setCandidateSummary,
    reviewDecision,
    setReviewDecision,
    promotionImpact,
    setPromotionImpact,
  }), [state, queue, gotoModule, openTask, openTarget, selectPaper, candidateSummary, reviewDecision, promotionImpact])

  return <EvidenceCenterContext.Provider value={value}>{children}</EvidenceCenterContext.Provider>
}

export function useEvidenceCenter(): EvidenceCenterContextValue {
  const ctx = useContext(EvidenceCenterContext)
  if (!ctx) throw new Error('useEvidenceCenter must be used within EvidenceCenterProvider')
  return ctx
}
