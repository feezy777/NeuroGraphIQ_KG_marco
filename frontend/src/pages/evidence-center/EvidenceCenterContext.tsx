import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import type { PromotionImpactState } from './components/PromotionImpact'
import type { ReviewDecisionState } from './components/ReviewerDecisionPanel'
import type { TaskSummaryActions, TaskSummaryData } from './components/TaskSummary'
import type { CandidatePassageItem } from './components/PassageSummary'
import type { ClaimComponent, QueueEntry } from './components/types'
import { buildEmbeddedUrl, buildEvidenceUrl, parseEvidenceUrl, type EvidenceCenterState } from './evidenceCenterUrl'

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

export type TaskFilterGroup = 'all' | 'connection' | 'circuit' | 'function'

interface EvidenceCenterContextValue {
  state: EvidenceCenterState
  queue: QueueEntry[]
  setQueue: (q: QueueEntry[]) => void
  /** 佐证任务页:当前选中的任务卡(仅内存联动,不写 URL;点「继续验证」才跳转) */
  selectedTaskId: string | null
  setSelectedTaskId: (id: string | null) => void
  /** 佐证任务页:类型筛选组(左栏与中栏共用) */
  taskFilterGroup: TaskFilterGroup
  setTaskFilterGroup: (g: TaskFilterGroup) => void
  /** 当前对象的处理进度(StepPills 由 module + progress 推导) */
  progress: ObjectProgress
  /** 推进当前对象进度(仅置位,永不回退;切换对象时由 openTask/openTarget 重置) */
  setProgress: (patch: Partial<ObjectProgress>) => void
  gotoModule: (m: ModuleKey) => void
  openTask: (taskId: string) => void
  closeTask: () => void
  /** 原子导航:一次设置 taskId+taskItemId+target(+module),一次写 URL(无任务时进入 candidates 工作区) */
  openTaskTarget: (taskId: string | null, targetType: string, targetId: string, taskItemId?: string | null, module?: ModuleKey) => void
  /** 关闭对象:清 task_item_id+target,保留当前 task */
  closeTarget: () => void
  /** S6:旧 deep link 唯一匹配后以 replace 语义补齐 task_item_id(不产生浏览器历史,三.8/9) */
  backfillTaskItem: (taskItemId: string) => void
  openTarget: (targetType: string, targetId: string, module?: ModuleKey) => void
  selectPaper: (paperId: string | null) => void
  /** 候选模块推送的当前对象验证事实(仅 candidates 模块使用,页面左栏渲染 ClaimSummaryPanel) */
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
  /** 候选模块推送的提取片段摘要(仅 candidates 模块使用,RightPanel 渲染 PassageSummary) */
  candidatePassages: CandidatePassageItem[]
  setCandidatePassages: (p: CandidatePassageItem[]) => void
  /** 右栏 PassageSummary 点击"查看详情" → 打开中间区域论文证据视图 */
  viewCandidatePaper: (paperId: string) => void
  setViewCandidatePaper: (fn: (paperId: string) => void) => void
  /** 右栏 PassageSummary 多选 state */
  candidateSelectedHashes: Set<string>
  setCandidateSelectedHashes: (s: Set<string>) => void
  toggleCandidatePassage: (hash: string, checked: boolean) => void
  selectAllCandidatePassages: (checked: boolean) => void
  setSelectAllCandidatePassages: (fn: (checked: boolean) => void) => void
  enterReviewFromPassages: () => void
  setEnterReviewFromPassages: (fn: () => void) => void
}

const EvidenceCenterContext = createContext<EvidenceCenterContextValue | null>(null)

function parseEmbeddedUrl(): EvidenceCenterState {
  return parseEvidenceUrl(window.location.hash)
}

export function EvidenceCenterProvider({ children, embedded }: { children: ReactNode; embedded?: boolean }) {
  const [state, setState] = useState<EvidenceCenterState>(() =>
    embedded
      ? parseEmbeddedUrl()
      : parseEvidenceUrl(window.location.hash),
  )
  const [queue, setQueue] = useState<QueueEntry[]>([])
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null)
  const [taskFilterGroup, setTaskFilterGroup] = useState<TaskFilterGroup>('all')
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
  const [candidatePassages, setCandidatePassages] = useState<CandidatePassageItem[]>([])
  const [viewCandidatePaper, setViewCandidatePaper] = useState<((paperId: string) => void)>(() => () => {})
  const [candidateSelectedHashes, setCandidateSelectedHashes] = useState<Set<string>>(new Set())
  const [selectAllCandidatePassages, setSelectAllCandidatePassages] = useState<((checked: boolean) => void)>(() => () => {})
  const [enterReviewFromPassages, setEnterReviewFromPassages] = useState<(() => void)>(() => () => {})
  const toggleCandidatePassage = useCallback((hash: string, checked: boolean) => {
    setCandidateSelectedHashes(prev => { const n = new Set(prev); if (checked) n.add(hash); else n.delete(hash); return n })
  }, [])

  // 初始归一化:embedded 下 URL 缺 tab 时以 replace 补齐(不产生历史记录)
  useEffect(() => {
    if (!embedded) return
    const raw = window.location.hash.replace(/^#/, '')
    const [path, query = ''] = raw.split('?')
    if (path !== '/validation-center' || new URLSearchParams(query).has('tab')) return
    window.history.replaceState(
      null,
      '',
      buildEmbeddedUrl({ module: 'tasks', taskId: null, taskItemId: null, targetType: null, targetId: null, paperId: null }, window.location.hash),
    )
  }, [embedded])

  useEffect(() => {
    const handler = () => setState(
      embedded ? parseEmbeddedUrl() : parseEvidenceUrl(window.location.hash),
    )
    window.addEventListener('hashchange', handler)
    return () => window.removeEventListener('hashchange', handler)
  }, [embedded])

  // 统一状态写回:embedded 写 #/validation-center?tab=paper_evidence(保留无关参数),
  // standalone 写 #/evidence-center;完全相同的 URL 不重复写入(防重复历史记录/循环);
  // replace 语义用于初始化/归一化,不污染历史
  const apply = useCallback((patch: Partial<EvidenceCenterState>, opts?: { replace?: boolean }) => {
    setState(prev => {
      const next = { ...prev, ...patch }
      const target = embedded
        ? buildEmbeddedUrl(next, window.location.hash)
        : buildEvidenceUrl(next)
      if (window.location.hash !== target) {
        if (opts?.replace) {
          window.history.replaceState(null, '', target)
        } else {
          window.location.hash = target
        }
      }
      return next
    })
  }, [embedded])

  // 导航回调必须 useCallback 稳定引用:消费方(如晋升模块)把 openTarget 放入 useCallback/memo 依赖,
  // 内联箭头会随 context value 每次重建 → 下游 memo 每渲染重建 → effect 推送 context → 无限循环
  // 切到 tasks 时清空选择(与 closeTask 语义一致):tasks 深链跳转 effect 依赖 target 残留会弹回佐证页,
  // 导航回任务列表必须不留 target,否则用户永远回不到列表
  const gotoModule = useCallback(
    (m: ModuleKey) =>
      m === 'tasks'
        ? apply({ module: m, taskId: null, taskItemId: null, targetType: null, targetId: null, paperId: null })
        : apply({ module: m }),
    [apply],
  )
  // 对象级进度:仅置位推进(模块各自 setProgress),切换对象时重置为全 false
  const setProgress = useCallback((patch: Partial<ObjectProgress>) => {
    setProgressState(prev => ({ ...prev, ...patch }))
  }, [])
  // 打开任务 → 进入佐证任务详情视图(保持 tasks 模块;必须清除上一任务的 target/task_item,否则详情/审核会打开错误对象)
  const openTask = useCallback(
    (taskId: string) => {
      apply({ taskId, taskItemId: null, targetType: null, targetId: null, module: 'tasks' })
      setProgressState(INITIAL_OBJECT_PROGRESS)
    },
    [apply],
  )
  // 关闭任务 → 回到佐证任务列表视图(全部清除,三.6)
  const closeTask = useCallback(
    () => {
      apply({ taskId: null, taskItemId: null, targetType: null, targetId: null, paperId: null })
      setProgressState(INITIAL_OBJECT_PROGRESS)
    },
    [apply],
  )
  // 原子导航:任务+任务项+对象一次设置、一次 URL 写入;无任务时进入 candidates 工作区(standalone 不写 task_item_id)
  const openTaskTarget = useCallback(
    (taskId: string | null, targetType: string, targetId: string, taskItemId: string | null = null, module: ModuleKey | undefined = undefined) => {
      apply({
        taskId,
        taskItemId: taskId ? taskItemId : null,
        targetType,
        targetId,
        module: module ?? (taskId ? 'tasks' : 'candidates'),
      })
      setProgressState(INITIAL_OBJECT_PROGRESS)
    },
    [apply],
  )
  // 关闭对象:清 task_item_id+target,保留当前 task(三.5)
  const closeTarget = useCallback(
    () => {
      apply({ taskItemId: null, targetType: null, targetId: null })
    },
    [apply],
  )
  const openTarget = useCallback(
    (targetType: string, targetId: string, module: ModuleKey = 'candidates') => {
      // 新对象身份未知 → 清除上一对象的 task_item_id(任务模式下由审核模块重新解析)
      apply({ taskItemId: null, targetType, targetId, module })
      setProgressState(INITIAL_OBJECT_PROGRESS)
    },
    [apply],
  )
  const selectPaper = useCallback((paperId: string | null) => apply({ paperId }), [apply])
  // S6:task_item_id 补齐使用 replace 语义,不污染浏览器历史
  const backfillTaskItem = useCallback((taskItemId: string) => {
    apply({ taskItemId }, { replace: true })
  }, [apply])

  const value = useMemo<EvidenceCenterContextValue>(() => ({
    state,
    queue,
    setQueue,
    selectedTaskId,
    setSelectedTaskId,
    taskFilterGroup,
    setTaskFilterGroup,
    progress,
    setProgress,
    gotoModule,
    openTask,
    openTarget,
    closeTask,
    openTaskTarget,
    closeTarget,
    backfillTaskItem,
    selectPaper,
    candidateClaim,
    setCandidateClaim,
    reviewDecision,
    setReviewDecision,
    promotionImpact,
    setPromotionImpact,
    taskSummary,
    setTaskSummary,
    candidatePassages,
    setCandidatePassages,
    viewCandidatePaper,
    setViewCandidatePaper,
    candidateSelectedHashes,
    setCandidateSelectedHashes,
    toggleCandidatePassage,
    selectAllCandidatePassages,
    setSelectAllCandidatePassages,
    enterReviewFromPassages,
    setEnterReviewFromPassages,
    taskSummaryActions,
    setTaskSummaryActions,
  }), [state, queue, selectedTaskId, setSelectedTaskId, taskFilterGroup, setTaskFilterGroup, progress, setProgress, gotoModule, openTask, openTarget, closeTask, openTaskTarget, closeTarget, backfillTaskItem, selectPaper, candidateClaim, reviewDecision, promotionImpact, taskSummary, candidatePassages, viewCandidatePaper, candidateSelectedHashes, taskSummaryActions])

  return <EvidenceCenterContext.Provider value={value}>{children}</EvidenceCenterContext.Provider>
}

export function useEvidenceCenter(): EvidenceCenterContextValue {
  const ctx = useContext(EvidenceCenterContext)
  if (!ctx) throw new Error('useEvidenceCenter must be used within EvidenceCenterProvider')
  return ctx
}
