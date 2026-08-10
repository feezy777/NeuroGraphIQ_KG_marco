import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import type { CandidateSummaryData } from './components/CandidateSummary'
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
}

const EvidenceCenterContext = createContext<EvidenceCenterContextValue | null>(null)

export function EvidenceCenterProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<EvidenceCenterState>(() => parseEvidenceUrl(window.location.hash))
  const [queue, setQueue] = useState<QueueEntry[]>([])
  const [candidateSummary, setCandidateSummary] = useState<CandidateSummaryData | null>(null)

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

  const value = useMemo<EvidenceCenterContextValue>(() => ({
    state,
    queue,
    setQueue,
    gotoModule: m => apply({ module: m }),
    openTask: taskId => apply({ taskId, module: 'candidates' }),
    openTarget: (targetType, targetId, module = 'candidates') => apply({ targetType, targetId, module }),
    selectPaper: paperId => apply({ paperId }),
    candidateSummary,
    setCandidateSummary,
  }), [state, queue, apply, candidateSummary])

  return <EvidenceCenterContext.Provider value={value}>{children}</EvidenceCenterContext.Provider>
}

export function useEvidenceCenter(): EvidenceCenterContextValue {
  const ctx = useContext(EvidenceCenterContext)
  if (!ctx) throw new Error('useEvidenceCenter must be used within EvidenceCenterProvider')
  return ctx
}
