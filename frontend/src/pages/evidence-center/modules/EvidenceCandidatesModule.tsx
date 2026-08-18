import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { MousePointerClick } from 'lucide-react'
import {
  cancelPaperEvidenceExtractionRun,
  createPaperEvidenceExtractionRun,
  extractSelectedPaperEvidence,
  getEvidenceTarget,
  getPaperEvidenceExtractionRun,
  listPaperEvidenceTaskItems,
  retryFailedPaperEvidenceExtractionRun,
  searchPaperEvidence,
  type EvidenceTargetDto,
  type PaperEvidenceExtractionRun,
  type PaperEvidenceTaskItem,
  type PaperSearchResponse,
} from '../../../api/endpoints'
import { ApiError } from '../../../api/client'
import { useEvidenceCenter } from '../EvidenceCenterContext'
import { INITIAL_QUEUE_KEY } from '../evidenceCenterUrl'
import { candidatePassagesToWorkbench } from '../components/candidatePassages'
import { aggregateTmpDirection, computeTmpCoverage } from '../components/claimCoverage'
import { EmptyState } from '../components/EmptyState'
import { PaperBatchActions } from '../components/PaperBatchActions'
import { PaperCandidateCard, type CandidatePaperData } from '../components/PaperCandidateCard'
import { PaperCandidateList } from '../components/PaperCandidateList'
import { PaperExtractionProgress } from '../components/PaperExtractionProgress'
import { PaperSearchFilters, type EvidenceMode } from '../components/PaperSearchFilters'
import { PaperSearchPanel } from '../components/PaperSearchPanel'
import { PaperStatusSummary, type CandidateStats } from '../components/PaperStatusSummary'
import { PaperDetailDrawer } from '../components/PaperDetailDrawer'
import { PaperEvidenceView } from '../components/PaperEvidenceView'
import { loadReviewStatus } from '../components/ReviewStatusStore'
import type { CandidatePassageItem } from '../components/PassageSummary'
import type { QueueEntry, QueueStatus, WorkbenchPassage } from '../components/types'

const DRAFT_PREFIX = 'evidence-center.review-draft.'
const EXTRACTION_RUN_KEY_PREFIX = 'evidence-center.extraction-run.'
const EXTRACTION_TERMINAL = new Set(['completed', 'partially_failed', 'failed', 'cancelled'])

/** 候选论文(任务 item 的 candidate_papers 与手动提取的 ExtractedPaperCandidate 的公共子集) */
interface CandidatePaper {
  paper_id: string
  pmid: string
  doi?: string | null
  pmcid?: string | null
  title: string
  journal: string
  year: string
  is_oa: boolean
  fulltext_fetched?: boolean | null
  paper_match_score?: number | null
  match_reason?: string | null
  model_direction: string | null
  model_assessment: string | null
  coverage_summary: Record<string, unknown> | null
  passages: Array<Record<string, unknown>>
  error_code?: string | null
  error_message?: string | null
}

interface ReviewDraft {
  passages: WorkbenchPassage[]
  modelDirection: string | null
  modelAssessment: string | null
  paperTitle: string
  pmid: string
}

type PaperIdentity = {
  paper_id?: string | null
  pmid?: string | null
  pmcid?: string | null
  doi?: string | null
  title?: string | null
}

/** 跨 PubMed / PMC / DOI 生成稳定键，避免 DOI-only 论文共用空 PMID。 */
function paperIdentityKey(paper: PaperIdentity): string {
  const pmid = paper.pmid?.trim()
  if (pmid) return `pmid:${pmid}`
  const pmcid = paper.pmcid?.trim().toLowerCase()
  if (pmcid) return `pmcid:${pmcid}`
  const doi = paper.doi?.trim().toLowerCase()
  if (doi) return `doi:${doi}`
  const paperId = paper.paper_id?.trim()
  if (paperId) return `paper:${paperId}`
  return `title:${paper.title?.trim().toLowerCase() ?? ''}`
}

function hasPaperIdentifier(paper: PaperIdentity): boolean {
  return Boolean(paper.pmid?.trim() || paper.pmcid?.trim() || paper.doi?.trim())
}

function resultJsonToCandidate(result: Record<string, unknown>): CandidatePaper {
  return {
    paper_id: String(result.paper_id ?? ''),
    pmid: String(result.pmid ?? ''),
    doi: (result.doi as string | null | undefined) ?? null,
    pmcid: (result.pmcid as string | null | undefined) ?? null,
    title: String(result.title ?? ''),
    journal: String(result.journal ?? ''),
    year: String(result.year ?? ''),
    is_oa: Boolean(result.is_oa),
    fulltext_fetched: result.fulltext_fetched as boolean | null | undefined,
    paper_match_score: result.paper_match_score as number | null | undefined,
    match_reason: result.match_reason as string | null | undefined,
    model_direction: (result.model_direction as string | null | undefined) ?? null,
    model_assessment: (result.model_assessment as string | null | undefined) ?? null,
    coverage_summary: (result.coverage_summary as Record<string, unknown> | null | undefined) ?? null,
    passages: Array.isArray(result.passages) ? (result.passages as Array<Record<string, unknown>>) : [],
    error_code: (result.error_code as string | null | undefined) ?? null,
    error_message: (result.error_message as string | null | undefined) ?? null,
  }
}

function mergeExtractionResults(
  prev: CandidatePaper[],
  run: PaperEvidenceExtractionRun,
): CandidatePaper[] {
  const merged = new Map(prev.map(p => [paperIdentityKey(p), p]))
  for (const item of run.items) {
    if (!item.result_json) continue
    if (item.status !== 'completed' && item.status !== 'no_evidence' && item.status !== 'failed') continue
    const cand = resultJsonToCandidate(item.result_json)
    if (item.status === 'failed' && !cand.error_code) {
      cand.error_code = item.error_code ?? 'EXTRACTION_FAILED'
      cand.error_message = item.error_message ?? cand.error_message
    }
    merged.set(paperIdentityKey(cand), cand)
  }
  return [...merged.values()]
}

function itemToQueueEntry(it: PaperEvidenceTaskItem): QueueEntry {
  return {
    target_type: it.target_type,
    target_id: it.target_id,
    label: it.label || it.target_id,
    confidence: it.current_confidence,
    status: ((it.status as QueueStatus) || 'pending') as QueueStatus,
    evidenceCount: it.candidate_papers?.length ?? 0,
    taskItemId: it.id,
    preprocessOutcome: it.preprocess_outcome,
    modelDirection: it.model_direction as QueueEntry['modelDirection'],
  }
}

/** 任务候选 / 手动提取结果 → 分层卡片数据(已提取) */
function extractedToCardData(cand: CandidatePaper): CandidatePaperData {
  return {
    paperId: cand.paper_id,
    pmid: cand.pmid,
    doi: cand.doi ?? null,
    pmcid: cand.pmcid ?? null,
    title: cand.title,
    journal: cand.journal,
    year: cand.year,
    authors: null,
    source: (cand as any).source ?? null,
    abstract: (cand as any).abstract ?? null,
    isOa: cand.is_oa,
    abstractAvailable: true,
    fulltextAvailable: cand.is_oa && cand.fulltext_fetched !== false,
    matchReason: cand.match_reason ?? null,
    matchScore: cand.paper_match_score ?? null,
    extracted: true,
    modelDirection: cand.model_direction,
    modelAssessment: cand.model_assessment,
    coverageSummary: cand.coverage_summary,
    passageCount: cand.passages?.length ?? 0,
    verifiedCount: (cand.passages ?? []).filter(p => Boolean(p.source_verified)).length,
  }
}

/** 手动检索结果 → 分层卡片数据(未提取,仅匹配信息) */
function searchToCardData(p: PaperSearchResponse['papers'][number]): CandidatePaperData {
  return {
    paperId: null,
    pmid: p.pmid,
    doi: p.doi,
    pmcid: p.pmcid ?? null,
    title: p.title,
    journal: p.journal,
    year: p.year,
    authors: p.authors || null,
    source: (p as any).source ?? null,
    abstract: (p as any).abstract ?? null,
    isOa: Boolean(p.is_open_access),
    abstractAvailable: Boolean(p.abstract),
    fulltextAvailable: Boolean(p.fulltext_available),
    matchReason: p.match_reason ?? null,
    matchScore: p.paper_match_score ?? null,
    extracted: false,
    modelDirection: null,
    modelAssessment: null,
    coverageSummary: null,
    passageCount: 0,
    verifiedCount: 0,
  }
}

/** 后端 getEvidenceTarget 的「target not found」精确识别(400 + 结构化 detail.message);其余错误一律按通用失败处理 */
function isTargetNotFoundError(err: unknown): boolean {
  if (!(err instanceof ApiError)) return false
  if (err.status !== 400) return false
  const body = err.meta?.responseBody as { detail?: { message?: string } } | undefined
  if (body?.detail?.message === 'target not found') return true
  return /target not found/.test(err.message)
}

/** 目标数据不存在专用错误面板(不展示内部异常细节) */
function TargetNotFoundPanel({ targetType, name, shortId, hasTask, onBack, onRetry }: {
  targetType: string
  name: string | null
  shortId: string
  hasTask: boolean
  onBack: () => void
  onRetry: () => void
}) {
  return (
    <div className="evidence-target-not-found" data-testid="evidence-target-not-found">
      <h4>目标数据不存在或尚未同步</h4>
      <p className="evidence-module-hint">
        该任务引用的对象已不存在,或尚未同步到当前镜像数据,因此暂时无法打开证据佐证工作区。
      </p>
      <p className="ew-meta">对象类型:{targetType}</p>
      {name && <p className="ew-meta">对象名称:{name}</p>}
      <p className="ew-meta">对象 ID:{shortId}</p>
      <div style={{ display: 'flex', gap: 8 }}>
        <button type="button" className="btn btn-sm" data-testid="evidence-target-not-found-back" onClick={onBack}>
          {hasTask ? '返回任务' : '返回任务列表'}
        </button>
        <button type="button" className="btn btn-sm" data-testid="evidence-target-not-found-retry" onClick={onRetry}>
          重新加载
        </button>
      </div>
    </div>
  )
}

export function EvidenceCandidatesModule() {
  const { state, queue, setQueue, openTarget, closeTarget, closeTask, setCandidateClaim, setProgress, setCandidatePassages, setViewCandidatePaper, setSelectAllCandidatePassages, setEnterReviewFromPassages, setCandidateSelectedHashes } = useEvidenceCenter()
  const [items, setItems] = useState<PaperEvidenceTaskItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [dto, setDto] = useState<EvidenceTargetDto | null>(null)
  const [dtoStatus, setDtoStatus] = useState<'idle' | 'loading' | 'success' | 'not_found' | 'error'>('idle')
  const [dtoReload, setDtoReload] = useState(0)
  const [excludedPaperIds, setExcludedPaperIds] = useState<Set<string>>(new Set())
  const [selectedHashes, setSelectedHashes] = useState<Set<string>>(new Set())
  const [reExtractBusy, setReExtractBusy] = useState<string | null>(null)
  const [manualQuery, setManualQuery] = useState('')
  const [manualResult, setManualResult] = useState<PaperSearchResponse | null>(null)
  const [manualBusy, setManualBusy] = useState(false)
  const [manualSelected, setManualSelected] = useState<Set<string>>(new Set())
  const [manualResults, setManualResults] = useState<CandidatePaper[]>([])
  const [extractionRun, setExtractionRun] = useState<PaperEvidenceExtractionRun | null>(null)
  const [pollEpoch, setPollEpoch] = useState(0)
  const [evidenceViewPaperId, setEvidenceViewPaperId] = useState<string | null>(null)
  const [detailPaperId, setDetailPaperId] = useState<string | null>(null)
  // 检索区展开态:有检索结果时默认折叠为一条(Query 摘要 + 重新搜索 + 展开)
  const [searchExpanded, setSearchExpanded] = useState(false)
  // 搜索过滤(第二层)
  const [oaOnly, setOaOnly] = useState(false)
  const [modeOverride, setModeOverride] = useState<EvidenceMode>('auto')
  const [yearFilter, setYearFilter] = useState('')
  // Query Chips 用户清除项(× 清空;恢复系统推荐时重置)
  const [clearedTerms, setClearedTerms] = useState<Set<string>>(new Set())

  const loadItems = useCallback(async () => {
    if (!state.taskId) {
      setItems([])
      setQueue([])
      setLoading(false)
      return
    }
    setLoading(true)
    setError(null)
    try {
      const r = await listPaperEvidenceTaskItems(state.taskId, { limit: 100 })
      setItems(r.items)
      setQueue(r.items.map(itemToQueueEntry))
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
      setItems([])
      setQueue([])
    } finally {
      setLoading(false)
    }
  }, [state.taskId, setQueue])

  useEffect(() => { void loadItems() }, [loadItems])

  // 注册右栏 PassageSummary "查看详情" 回调 → 打开中间区域论文证据视图
  useEffect(() => {
    setViewCandidatePaper(() => (paperId: string) => { setEvidenceViewPaperId(paperId) })
    return () => { setViewCandidatePaper(() => () => {}) }
  }, [setViewCandidatePaper])

  const current = useMemo(() => {
    if (items.length > 0) {
      if (state.targetType && state.targetId) {
        const found = items.find(it => it.target_type === state.targetType && it.target_id === state.targetId)
        if (found) return found
      }
      return items[0]
    }
    if (state.targetType && state.targetId) {
      return {
        target_type: state.targetType,
        target_id: state.targetId,
        status: 'pending',
        label: state.targetId,
        candidate_papers: [],
      } as unknown as PaperEvidenceTaskItem
    }
    return null
  }, [items, state.targetType, state.targetId])

  // 自动将当前项同步到 URL(便于直接进入人工审核时带上 target):
  // - URL 无 target 时选中首个 item;
  // - URL 残留上一任务的陈旧 target(与 items 不匹配,current 已回退到 items[0])时,以当前项回写纠错
  useEffect(() => {
    if (items.length > 0 && current) {
      const needsSync = current.target_id !== state.targetId || current.target_type !== state.targetType
      if (needsSync) openTarget(current.target_type, current.target_id, 'candidates')
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [current?.target_id, current?.target_type, items.length, state.targetId, state.targetType])

  // StepPills 进度:从现有数据推导对象实际进度(任务候选已含片段 / 本地已有审核草稿 → 找到原文;
  // 已有审核状态 → 人工审核)。声明在 URL 同步 effect 之后,确保 openTarget 重置进度后本推导最终生效。
  // deps 含 candidate_papers:直达 URL 进入(刷新/深链)时 effect 先对 fallback current(空候选)跑一次,
  // items 加载后 candidate_papers 变化触发重跑,正确推导 extracted(setProgress 为稳定引用,不会重复执行)。
  useEffect(() => {
    if (!current) return
    const hasExtracted = (current.candidate_papers ?? []).some(c => (c.passages?.length ?? 0) > 0)
    if (hasExtracted || sessionStorage.getItem(`${DRAFT_PREFIX}${current.target_id}`)) {
      setProgress({ extracted: true })
    }
    if (loadReviewStatus(current.target_id)) {
      setProgress({ reviewed: true })
    }
  }, [current?.target_id, current?.candidate_papers, setProgress])

  useEffect(() => {
    const t = current?.target_type
    const id = current?.target_id
    if (!t || !id) {
      setDto(null)
      setDtoStatus('idle')
      return
    }
    let cancelled = false
    setDto(null)
    setDtoStatus('loading')
    getEvidenceTarget(t, id)
      .then(d => {
        if (cancelled) return
        setDto(d)
        setDtoStatus('success')
      })
      .catch((err: unknown) => {
        if (cancelled) return
        setDto(null)
        setDtoStatus(isTargetNotFoundError(err) ? 'not_found' : 'error')
      })
    return () => { cancelled = true }
  }, [current?.target_type, current?.target_id, dtoReload])

  // 左栏 ClaimSummaryPanel 数据源:DTO 加载后推送当前对象验证事实到 Context(页面左栏渲染);卸载/切对象清空
  useEffect(() => {
    if (!dto) {
      setCandidateClaim(null)
      return
    }
    setCandidateClaim({
      claimText: dto.claim_text ?? '',
      components: dto.claim_components ?? [],
      granularity: dto.granularity ?? null,
      targetType: dto.target_type,
    })
  }, [dto, setCandidateClaim])

  useEffect(() => () => { setCandidateClaim(null) }, [setCandidateClaim])

  // granularity 兑现:DTO 加载后填充队列条目,页面 ContextBar 读取(仅实际变更时 setQueue,避免重渲染循环)
  useEffect(() => {
    if (!dto?.granularity) return
    const next = queue.map(e =>
      e.target_type === dto.target_type && e.target_id === dto.target_id && e.granularity !== dto.granularity
        ? { ...e, granularity: dto.granularity }
        : e,
    )
    if (next.some((e, i) => e !== queue[i])) setQueue(next)
  }, [dto, queue, setQueue])

  // 切换目标时重置选择状态与手动检索状态(防止 A 的检索结果 / query 摘要 / 已提取结果泄漏到 B)
  useEffect(() => {
    setEvidenceViewPaperId(null)
    setDetailPaperId(null)
    setSelectedHashes(new Set())
    setExcludedPaperIds(new Set())
    setManualQuery('')
    setManualResult(null)
    setManualSelected(new Set())
    setManualResults([])
    setSearchExpanded(false)
    setClearedTerms(new Set())
    setMessage(null)
    setCandidatePassages([])
  }, [current?.target_id])

  // 数据中心跳转兼容:无任务时从 sessionStorage initial-queue 一次性恢复队列
  useEffect(() => {
    if (state.taskId) return
    try {
      const raw = sessionStorage.getItem(INITIAL_QUEUE_KEY)
      if (!raw) return
      const parsed = JSON.parse(raw) as {
        items?: Array<{ target_type?: string; target_id?: string; label?: string; confidence?: number | null }>
      } | null
      const items = parsed?.items
      if (!Array.isArray(items) || items.length === 0) return
      sessionStorage.removeItem(INITIAL_QUEUE_KEY)
      const restored: QueueEntry[] = items
        .filter(it => it && typeof it.target_type === 'string' && typeof it.target_id === 'string')
        .map(it => ({
          target_type: it.target_type as string,
          target_id: it.target_id as string,
          label: it.label || (it.target_id as string),
          confidence: typeof it.confidence === 'number' ? it.confidence : null,
          status: 'pending' as const,
          evidenceCount: 0,
        }))
      if (restored.length === 0) return
      setQueue(restored)
      setMessage(`已从数据中心恢复 ${restored.length} 个待处理对象，可手动检索或直接加入人工审核`)
    } catch {
      // 交接数据损坏时忽略,保持空态
    }
  }, [state.taskId, setQueue])

  const derivedMode: 'function' | 'existence' =
    current?.target_type === 'connection' || current?.target_type === 'projection' ? 'existence' : 'function'
  const effectiveMode: 'function' | 'existence' = modeOverride === 'auto' ? derivedMode : modeOverride

  const candidates: CandidatePaper[] = useMemo(() => {
    const papers = current?.candidate_papers ?? []
    return papers
      .map(p => ({ ...p, passages: p.passages ?? [] }))
      .filter(c => !excludedPaperIds.has(c.paper_id || c.pmid))
  }, [current, excludedPaperIds])

  // useMemo:保证引用稳定(否则作为 summary 计算依赖会触发无限重渲染循环)
  const claimComponents = useMemo(() => dto?.claim_components ?? [], [dto])

  // ─── 搜索区(当前对象存在即可手动重新搜索;有候选论文时默认折叠为一条,可展开重新搜索) ───
  const manualTarget = useMemo(() =>
    current
      ? { target_type: current.target_type, target_id: current.target_id }
      : null,
  [current?.target_type, current?.target_id])

  const queryTerms = useMemo(() => {
    if (!dto) return []
    return [dto.source_region, dto.target_region, dto.relation, dto.function_context, dto.circuit_context]
      .filter((t): t is string => Boolean(t))
      .filter((t, i, arr) => arr.indexOf(t) === i)
  }, [dto])

  /** 可见推荐词(用户 × 清除后不再展示) */
  const visibleQueryTerms = useMemo(
    () => queryTerms.filter(t => !clearedTerms.has(t)),
    [queryTerms, clearedTerms],
  )

  const visibleSearchPapers = useMemo(() => {
    const papers = manualResult?.papers ?? []
    const extractedKeys = new Set(
      [...candidates, ...manualResults]
        .filter(p => !p.error_code)
        .map(paperIdentityKey),
    )
    return papers.filter(p =>
      !excludedPaperIds.has(paperIdentityKey(p))
      && !extractedKeys.has(paperIdentityKey(p))
      && (!oaOnly || p.is_open_access)
      && (!yearFilter || Number(p.year) >= Number(yearFilter)),
    )
  }, [manualResult, candidates, manualResults, oaOnly, yearFilter, excludedPaperIds])

  const selectedSearchPapers = useMemo(
    () => visibleSearchPapers.filter(p =>
      hasPaperIdentifier(p) && manualSelected.has(paperIdentityKey(p)),
    ),
    [visibleSearchPapers, manualSelected],
  )
  const selectedPaperCount = selectedSearchPapers.length

  /** 是否有检索结果:有结果或已有候选论文 → 检索区默认折叠为一条(可展开重新搜索);否则展开完整检索区 */
  const hasSearchResults = (manualResult?.papers.length ?? 0) > 0 || candidates.length > 0

  /** 折叠条 Query 摘要(截断显示):手动检索式 → 推荐词 → 占位 */
  const querySummary = manualQuery.trim() || visibleQueryTerms.join(' · ') || '系统推荐检索式'

  /** 是否使用自定义检索式(manualQuery 非空 或 已清除推荐词 → 自定义;否则系统推荐) */
  const queryMode: 'system' | 'custom' =
    manualQuery.trim().length > 0 || clearedTerms.size > 0 ? 'custom' : 'system'

  const runSearch = useCallback(async (query: string) => {
    if (!manualTarget) return
    setManualBusy(true)
    setMessage(null)
    try {
      const resp = await searchPaperEvidence({
        target_type: manualTarget.target_type,
        target_id: manualTarget.target_id,
        limit: 20,
        mode: effectiveMode,
        query_override: query.trim() || undefined,
      })
      setManualResult(resp)
      setManualSelected(new Set())
      // 检索完成自动收起检索区,候选论文列表占据主视区;同时推进 StepPills → 查找论文
      setSearchExpanded(false)
      setProgress({ searched: true })
    } catch (err) {
      setMessage(`检索失败：${err instanceof Error ? err.message : String(err)}`)
    } finally {
      setManualBusy(false)
    }
  }, [manualTarget, effectiveMode, setProgress])

  // 进入候选页自动检索:DTO 加载后当前对象尚无候选论文时,用系统推荐词触发一次 search
  // (数据中心入口 / 任务卡进入 / 回退重评进入统一行为:先开始查找论文;已有候选则不重复自动搜,可手动重新搜索)
  const [autoSearchDone, setAutoSearchDone] = useState(false)
  useEffect(() => {
    if (!dto || !current || autoSearchDone) return
    if ((current.candidate_papers ?? []).length > 0) return
    setAutoSearchDone(true)
    void runSearch('')
  }, [dto, current, autoSearchDone, runSearch])
  // 切对象时重置 auto-search 标记,下一对象重新触发
  useEffect(() => { setAutoSearchDone(false) }, [current?.target_id])
  // auto-search 触发后推进进度到 "查找论文"
  useEffect(() => {
    if (manualResult || manualBusy) setProgress({ searched: true })
  }, [manualResult, manualBusy, setProgress])

  const handleManualSearch = useCallback(() => { void runSearch(manualQuery) }, [runSearch, manualQuery])

  const handleRestoreRecommended = useCallback(() => {
    setManualQuery('')
    setClearedTerms(new Set())
    void runSearch('')
  }, [runSearch])

  /** Query Chip ×:从推荐词中移除该关键词(仅展示层,不影响后端推荐检索式) */
  const handleClearTerm = useCallback((term: string) => {
    setClearedTerms(prev => new Set(prev).add(term))
  }, [])

  const handleManualExtract = useCallback(async () => {
    if (!manualTarget) return
    const papers = selectedSearchPapers
    if (papers.length === 0) return
    setManualBusy(true)
    setMessage(null)
    try {
      const started = await createPaperEvidenceExtractionRun({
        target_type: manualTarget.target_type,
        target_id: manualTarget.target_id,
        papers: papers.map(p => ({
          pmid: p.pmid,
          pmcid: p.pmcid,
          doi: p.doi,
          title: p.title,
          abstract: p.abstract,
        })),
        mode: effectiveMode,
        concurrency: 4,
      })
      const runKey = `${EXTRACTION_RUN_KEY_PREFIX}${manualTarget.target_id}`
      sessionStorage.setItem(runKey, started.run_id)
      const submittedKeys = new Set(papers.map(paperIdentityKey))
      setManualSelected(prev => {
        const next = new Set(prev)
        for (const key of submittedKeys) next.delete(key)
        return next
      })
      const detail = await getPaperEvidenceExtractionRun(started.run_id)
      setExtractionRun(detail)
      setManualResults(prev => mergeExtractionResults(prev, detail))
      if (EXTRACTION_TERMINAL.has(detail.status)) {
        setManualBusy(false)
        const hits = detail.items.filter(i => i.status === 'completed' && i.result_json).length
        if (hits > 0) setProgress({ extracted: true })
        setMessage(
          `提取完成：命中 ${detail.evidence_hit_items} · 无证据 ${detail.no_evidence_items}`
          + `${detail.failed_items > 0 ? ` · 失败 ${detail.failed_items}` : ''}`
          + '。请勾选片段后加入人工审核',
        )
      } else {
        setMessage(`已启动并行提取 ${started.total_items} 篇（并发 ${started.requested_concurrency}）`)
        // Force poll effect to pick up the newly stored run id.
        setPollEpoch(n => n + 1)
      }
    } catch (err) {
      setMessage(`批量提取失败：${err instanceof Error ? err.message : String(err)}`)
      setManualBusy(false)
    }
  }, [manualTarget, selectedSearchPapers, effectiveMode, setProgress])

  // Poll active extraction run; restore from sessionStorage on target change.
  useEffect(() => {
    const targetId = manualTarget?.target_id ?? current?.target_id
    if (!targetId) {
      setExtractionRun(null)
      return
    }
    const stored = sessionStorage.getItem(`${EXTRACTION_RUN_KEY_PREFIX}${targetId}`)
    if (!stored) return

    let cancelled = false
    const controller = new AbortController()

    async function poll(runId: string) {
      try {
        const detail = await getPaperEvidenceExtractionRun(runId, controller.signal)
        if (cancelled) return
        setExtractionRun(detail)
        setManualResults(prev => mergeExtractionResults(prev, detail))
        const hits = detail.items.filter(i => i.status === 'completed' && i.result_json).length
        if (hits > 0) setProgress({ extracted: true })
        if (EXTRACTION_TERMINAL.has(detail.status)) {
          setManualBusy(false)
          setMessage(
            `提取完成：命中 ${detail.evidence_hit_items} · 无证据 ${detail.no_evidence_items}`
            + `${detail.failed_items > 0 ? ` · 失败 ${detail.failed_items}` : ''}`
            + '。请勾选片段后加入人工审核',
          )
          return
        }
        setManualBusy(true)
        window.setTimeout(() => {
          if (!cancelled) void poll(runId)
        }, 1000)
      } catch (err) {
        if (cancelled || controller.signal.aborted) return
        setManualBusy(false)
        setMessage(`提取进度同步失败：${err instanceof Error ? err.message : String(err)}`)
      }
    }

    void poll(stored)
    return () => {
      cancelled = true
      controller.abort()
    }
  }, [manualTarget?.target_id, current?.target_id, pollEpoch, setProgress])

  const handleCancelExtraction = useCallback(async () => {
    if (!extractionRun) return
    try {
      const detail = await cancelPaperEvidenceExtractionRun(extractionRun.id)
      setExtractionRun(detail)
      setManualResults(prev => mergeExtractionResults(prev, detail))
      setManualBusy(false)
      setMessage('已请求取消：未开始的论文已停止，已完成结果保留')
    } catch (err) {
      setMessage(`取消失败：${err instanceof Error ? err.message : String(err)}`)
    }
  }, [extractionRun])

  const handleRetryFailedExtraction = useCallback(async () => {
    if (!extractionRun) return
    setManualBusy(true)
    setMessage(null)
    try {
      const result = await retryFailedPaperEvidenceExtractionRun(extractionRun.id)
      if (result.retried <= 0) {
        setManualBusy(false)
        setMessage('没有可重试的失败论文')
        return
      }
      sessionStorage.setItem(
        `${EXTRACTION_RUN_KEY_PREFIX}${extractionRun.target_id}`,
        extractionRun.id,
      )
      setPollEpoch(n => n + 1)
      const detail = await getPaperEvidenceExtractionRun(extractionRun.id)
      setExtractionRun(detail)
      setMessage(`已重新排队失败论文 ${result.retried} 篇`)
    } catch (err) {
      setManualBusy(false)
      setMessage(`重试失败：${err instanceof Error ? err.message : String(err)}`)
    }
  }, [extractionRun])

  /** ☐全选:勾选全部可见搜索结果 / 取消清空其勾选 */
  const handleToggleAll = useCallback((checked: boolean) => {
    setManualSelected(prev => {
      const next = new Set(prev)
      for (const p of visibleSearchPapers) {
        if (!hasPaperIdentifier(p)) continue
        const key = paperIdentityKey(p)
        if (checked) next.add(key)
        else next.delete(key)
      }
      return next
    })
  }, [visibleSearchPapers])

  const handleTogglePassage = useCallback((hash: string, checked: boolean) => {
    // 选中片段(写审核草稿)→ 推进 StepPills → 找到原文
    if (checked) setProgress({ extracted: true })
    setSelectedHashes(prev => {
      const next = new Set(prev)
      if (checked) next.add(hash)
      else next.delete(hash)
      return next
    })
  }, [setProgress])

  const handleReExtract = useCallback(async (cand: CandidatePaper) => {
    if (!current) return
    setReExtractBusy(cand.paper_id || cand.pmid)
    setMessage(null)
    try {
      const resp = await extractSelectedPaperEvidence({
        target_type: current.target_type,
        target_id: current.target_id,
        papers: [{ pmid: cand.pmid, doi: cand.doi ?? null, title: cand.title }],
        mode: effectiveMode,
      })
      const fresh = resp.results[0]
      if (fresh) {
        setItems(prev => prev.map(it => {
          if (it.target_id !== current.target_id) return it
          const cands = it.candidate_papers ?? []
          const idx = cands.findIndex(c =>
            (cand.paper_id && c.paper_id === cand.paper_id) || (cand.pmid && c.pmid === cand.pmid),
          )
          if (idx < 0) return it
          const next = cands.slice()
          next[idx] = { ...fresh, passages: fresh.passages ?? [] }
          return { ...it, candidate_papers: next }
        }))
        // 手动提取结果同样就地更新
        setManualResults(prev => {
          const idx = prev.findIndex(c =>
            (cand.paper_id && c.paper_id === cand.paper_id) || (cand.pmid && c.pmid === cand.pmid),
          )
          if (idx < 0) return prev
          const next = prev.slice()
          next[idx] = fresh as CandidatePaper
          return next
        })
        setMessage(`「${fresh.title}」已重新提取，获得 ${fresh.passages?.length ?? 0} 个候选片段`)
      }
    } catch (err) {
      setMessage(`重新提取失败：${err instanceof Error ? err.message : String(err)}`)
    } finally {
      setReExtractBusy(null)
    }
  }, [current, effectiveMode])

  // ─── 论文↔证据视图:勾选已核验片段时自动写审核草稿(进入人工审核即恢复) ───
  const evidencePaper = useMemo(() => {
    if (!evidenceViewPaperId) return null
    return [...candidates, ...manualResults].find(c => (c.paper_id || c.pmid) === evidenceViewPaperId) ?? null
  }, [evidenceViewPaperId, candidates, manualResults])

  const evidencePassages = useMemo(
    () => candidatePassagesToWorkbench(evidencePaper?.passages ?? [], evidencePaper?.paper_id ?? null),
    [evidencePaper],
  )

  // 记录本 effect 最近一次写入的 key,用于区分「用户清空选择」与「尚未选择」:
  // 只有先前为本目标写入过草稿、现在选择全部清空时才删除,避免误删用户已存在的审核草稿
  const draftWrittenRef = useRef<{ key: string } | null>(null)

  // auto-draft 跨论文累计:遍历全部已提取论文,收集 selectedHashes 对应的片段(不限于当前查看的论文),
  // 支持「多论文多片段混合审核」;右栏 selectedPassages 计数与草稿内容保持一致
  useEffect(() => {
    if (!current) return
    const key = `${DRAFT_PREFIX}${current.target_id}`
    const allPapers = [...candidates, ...manualResults]
    const selected: WorkbenchPassage[] = []
    const seen = new Set<string>()
    let metaPaper: CandidatePaper | null = null
    for (const c of allPapers) {
      for (const p of candidatePassagesToWorkbench(c.passages ?? [], c.paper_id)) {
        if (!selectedHashes.has(p.hash) || seen.has(p.hash)) continue
        seen.add(p.hash)
        selected.push(p)
        if (!metaPaper) metaPaper = c
      }
    }
    if (selected.length === 0) {
      if (draftWrittenRef.current?.key === key) {
        sessionStorage.removeItem(key)
        draftWrittenRef.current = null
      }
      return
    }
    // 元数据取第一篇贡献片段的论文(多论文时片段自身携带 paper_id/paper_passage_id 溯源)
    const draft: ReviewDraft = {
      passages: selected,
      modelDirection: metaPaper?.model_direction ?? null,
      modelAssessment: metaPaper?.model_assessment ?? null,
      paperTitle: metaPaper?.title ?? '',
      pmid: metaPaper?.pmid ?? '',
    }
    sessionStorage.setItem(key, JSON.stringify(draft))
    draftWrittenRef.current = { key }
  }, [current, candidates, manualResults, selectedHashes])

  // ─── 聚合已提取论文的全部已核验片段推送至右栏 PassageSummary ───
  useEffect(() => {
    if (!current) {
      setCandidatePassages([])
      return
    }
    const allPapers = [...candidates, ...manualResults]
    const items: CandidatePassageItem[] = []
    const seen = new Set<string>()
    for (const paper of allPapers) {
      for (const p of paper.passages ?? []) {
        const hash = typeof p.passage_hash === 'string' ? p.passage_hash : JSON.stringify(p.passage ?? '').slice(0, 32)
        if (!hash || seen.has(hash)) continue
        seen.add(hash)
        items.push({
          hash,
          passage: typeof p.passage === 'string' ? p.passage : (typeof p.passage_text === 'string' ? p.passage_text : ''),
          direction: typeof p.direction === 'string' ? p.direction : 'not_found',
          evidenceLevel: typeof p.evidence_level === 'string' ? p.evidence_level : 'indirect',
          paperTitle: paper.title,
          pmid: paper.pmid,
          paperId: paper.paper_id ?? null,
          confidence: typeof p.confidence === 'number' ? p.confidence : null,
          sourceVerified: Boolean(p.source_verified),
        })
      }
    }
    setCandidatePassages(items)
  }, [current, candidates, manualResults, setCandidatePassages])

  // ─── 中栏状态条数据(候选/已提取/已核验/覆盖/模型判断) ───
  const stats = useMemo<CandidateStats | null>(() => {
    if (!current) return null
    const all = [...candidates, ...manualResults.filter(p => !p.error_code)]
    const passages = all.flatMap(c => candidatePassagesToWorkbench(c.passages ?? [], c.paper_id))
    const verified = passages.filter(p => p.source_verified)
    const coverage = computeTmpCoverage(claimComponents, verified)
    const foundKeys = new Set([
      ...candidates.map(paperIdentityKey),
      ...manualResults.map(paperIdentityKey),
      ...(manualResult?.papers ?? []).map(paperIdentityKey),
    ])
    return {
      foundPapers: foundKeys.size,
      extractedPapers: all.length,
      verifiedPassages: verified.length,
      selectedPassages: selectedHashes.size,
      coverageRatio: coverage.coverage_ratio,
      coverageSupported: coverage.supported_components.length,
      coverageRequired: coverage.required_components.length,
      direction: aggregateTmpDirection(coverage, verified),
      modelAssessment: all[0]?.model_assessment ?? null,
    }
  }, [current, candidates, manualResults, manualResult, claimComponents, selectedHashes])

  const successfulManualResults = manualResults.filter(p => !p.error_code)
  const totalPapers = new Set([
    ...candidates.map(paperIdentityKey),
    ...successfulManualResults.map(paperIdentityKey),
    ...visibleSearchPapers.map(paperIdentityKey),
  ]).size

  const handleEnterReview = useCallback(() => {
    if (!state.targetType || !state.targetId) return
    // 进入审核前仅写入用户已勾选的已核验片段，再导航到 review 模块。
    const allPapers = [...candidates, ...manualResults]
    const selected = allPapers
      .flatMap(c => candidatePassagesToWorkbench(c.passages ?? [], c.paper_id))
      .filter(p => p.source_verified && selectedHashes.has(p.hash))
    if (selected.length > 0) {
      const draft: ReviewDraft = {
        passages: selected,
        modelDirection: allPapers[0]?.model_direction ?? null,
        modelAssessment: allPapers[0]?.model_assessment ?? null,
        paperTitle: allPapers[0]?.title ?? '',
        pmid: allPapers[0]?.pmid ?? '',
      }
      sessionStorage.setItem(`${DRAFT_PREFIX}${state.targetId}`, JSON.stringify(draft))
    }
    openTarget(state.targetType, state.targetId, 'review')
  }, [state.targetType, state.targetId, openTarget, candidates, manualResults, selectedHashes])

  // 向右栏 PassageSummary 注册多选回调
  useEffect(() => {
    setSelectAllCandidatePassages(() => (checked: boolean) => {
      const allPapers = [...candidates, ...manualResults]
      const allPassages = allPapers.flatMap(c => candidatePassagesToWorkbench(c.passages ?? [], c.paper_id))
      const verifiedHashes = allPassages.filter(p => p.source_verified).map(p => p.hash)
      if (checked) {
        setSelectedHashes(prev => { const n = new Set(prev); verifiedHashes.forEach(h => n.add(h)); return n })
        setCandidateSelectedHashes(new Set(verifiedHashes))
      } else {
        setSelectedHashes(prev => { const n = new Set(prev); verifiedHashes.forEach(h => n.delete(h)); return n })
        setCandidateSelectedHashes(new Set())
      }
    })
    setEnterReviewFromPassages(() => () => handleEnterReview())
    return () => { setSelectAllCandidatePassages(() => () => {}); setEnterReviewFromPassages(() => () => {}) }
  }, [setSelectAllCandidatePassages, setEnterReviewFromPassages, candidates, manualResults, handleEnterReview, setSelectedHashes])

  // 同步 selectedHashes → 右栏 candidateSelectedHashes
  useEffect(() => {
    setCandidateSelectedHashes(new Set(selectedHashes))
  }, [selectedHashes, setCandidateSelectedHashes])

  return (
    <div className="evidence-candidates">
      <div className="evidence-candidates-main">
        {loading && <div className="evidence-task-loading">加载中…</div>}
        {!loading && error && (
          <div className="evidence-task-error">
            <p>候选加载失败：{error}</p>
            <button type="button" className="btn btn-sm" onClick={() => void loadItems()}>重试</button>
          </div>
        )}
        {!loading && !error && !current && (
          <EmptyState
            icon={<MousePointerClick size={24} />}
            title="请先在「佐证任务」中打开一个任务"
            description="或从上方任务列表进入一个目标对象。"
          />
        )}
        {!loading && !error && current && (
          <>
            {dtoStatus === 'loading' && <div className="evidence-task-loading">对象数据加载中…</div>}
            {dtoStatus === 'not_found' && (
              <TargetNotFoundPanel
                targetType={current.target_type}
                name={current.display_name ?? current.label ?? null}
                shortId={current.target_id.slice(0, 8)}
                hasTask={Boolean(state.taskId)}
                onBack={() => {
                  if (state.taskId) closeTarget()
                  else closeTask()
                }}
                onRetry={() => setDtoReload(c => c + 1)}
              />
            )}
            {dtoStatus === 'error' && (
              <div className="evidence-task-error" data-testid="evidence-target-error">
                <p>对象数据加载失败,请重试。</p>
                <button type="button" className="btn btn-sm" onClick={() => setDtoReload(c => c + 1)}>重新加载</button>
              </div>
            )}
            {dtoStatus === 'success' && (
            <>
            {message && <div className="ontology-page-message">{message}</div>}

            {evidencePaper ? (
              <>
                {/* 证据视图态:状态条保留在上方,[进入人工审核] 随勾选实时可用 */}
                <PaperStatusSummary stats={stats} onEnterReview={handleEnterReview} />
                <PaperEvidenceView
                  paper={{
                    paperId: evidencePaper.paper_id,
                    pmid: evidencePaper.pmid,
                    doi: evidencePaper.doi ?? null,
                    title: evidencePaper.title,
                    journal: evidencePaper.journal,
                    year: evidencePaper.year,
                  }}
                  components={claimComponents}
                  passages={evidencePassages}
                  selectedHashes={selectedHashes}
                  onTogglePassage={handleTogglePassage}
                  onBack={() => setEvidenceViewPaperId(null)}
                />
              </>
            ) : (
              <>
                {manualTarget && (
                  <PaperSearchPanel
                    collapsed={hasSearchResults && !searchExpanded}
                    busy={manualBusy}
                    query={manualQuery}
                    onQueryChange={setManualQuery}
                    onSearch={handleManualSearch}
                    onRestoreRecommended={handleRestoreRecommended}
                    queryTerms={visibleQueryTerms}
                    onClearTerm={handleClearTerm}
                    querySummary={querySummary}
                    queryMode={queryMode}
                    onExpand={() => setSearchExpanded(true)}
                    selectedCount={selectedPaperCount}
                    onExtractSelected={() => void handleManualExtract()}
                    onSelectAll={handleToggleAll}
                    totalResults={visibleSearchPapers.length}
                    filters={
                      <PaperSearchFilters
                        oaOnly={oaOnly}
                        onOaOnlyChange={setOaOnly}
                        mode={modeOverride}
                        onModeChange={setModeOverride}
                        year={yearFilter}
                        onYearChange={setYearFilter}
                        onRestoreDefaults={() => {
                          setOaOnly(false)
                          setModeOverride('auto')
                          setYearFilter('')
                        }}
                        excludedCount={excludedPaperIds.size}
                        onRestoreExcluded={() => setExcludedPaperIds(new Set())}
                      />
                    }
                    batchActions={
                      <PaperBatchActions
                        allSelected={selectedPaperCount > 0 && selectedPaperCount === visibleSearchPapers.filter(hasPaperIdentifier).length}
                        onToggleAll={handleToggleAll}
                        selectedCount={selectedPaperCount}
                        busy={manualBusy}
                        onExtractSelected={() => void handleManualExtract()}
                        canSelect={visibleSearchPapers.length > 0}
                        canCollapse={hasSearchResults}
                        onCollapse={() => setSearchExpanded(false)}
                      />
                    }
                  />
                )}

                {/* 中栏状态条:检索区下方、候选论文列表上方;Claim 事实在页面左栏 */}
                <PaperStatusSummary stats={stats} onEnterReview={handleEnterReview} />

                {extractionRun && (
                  <PaperExtractionProgress
                    run={extractionRun}
                    busy={manualBusy}
                    onCancel={() => void handleCancelExtraction()}
                    onRetryFailed={() => void handleRetryFailedExtraction()}
                  />
                )}

                <PaperCandidateList
                  total={totalPapers}
                  searchable={Boolean(manualTarget)}
                  onAdjustSearch={() => setSearchExpanded(true)}
                >
                  {visibleSearchPapers.map(p => (
                    <PaperCandidateCard
                      key={`s-${paperIdentityKey(p)}`}
                      paper={searchToCardData(p)}
                      selected={manualSelected.has(paperIdentityKey(p))}
                      reExtracting={false}
                      onToggleSelected={checked => {
                        setManualSelected(prev => {
                          const next = new Set(prev)
                          const key = paperIdentityKey(p)
                          if (checked && hasPaperIdentifier(p)) next.add(key)
                          else next.delete(key)
                          return next
                        })
                      }}
                      onOpenDetail={() => undefined}
                      onExclude={() => setExcludedPaperIds(prev => new Set(prev).add(paperIdentityKey(p)))}
                      onReExtract={() => undefined}
                      onViewEvidence={() => undefined}
                    />
                  ))}
                  {candidates.map(cand => (
                    <PaperCandidateCard
                      key={cand.paper_id || cand.pmid}
                      paper={extractedToCardData(cand)}
                      selected={false}
                      reExtracting={reExtractBusy === (cand.paper_id || cand.pmid)}
                      onToggleSelected={() => undefined}
                      onOpenDetail={() => setDetailPaperId(cand.paper_id)}
                      onExclude={() => setExcludedPaperIds(prev => new Set(prev).add(cand.paper_id || cand.pmid))}
                      onReExtract={() => void handleReExtract(cand)}
                      onViewEvidence={() => setEvidenceViewPaperId(cand.paper_id || cand.pmid)}
                    />
                  ))}
                  {successfulManualResults
                    .filter(c => !excludedPaperIds.has(c.paper_id || c.pmid))
                    .map(cand => (
                      <PaperCandidateCard
                        key={`m-${cand.paper_id || cand.pmid}`}
                        paper={extractedToCardData(cand)}
                        selected={false}
                        reExtracting={reExtractBusy === (cand.paper_id || cand.pmid)}
                        onToggleSelected={() => undefined}
                        onOpenDetail={() => setDetailPaperId(cand.paper_id)}
                        onExclude={() => setExcludedPaperIds(prev => new Set(prev).add(cand.paper_id || cand.pmid))}
                        onReExtract={() => void handleReExtract(cand)}
                        onViewEvidence={() => setEvidenceViewPaperId(cand.paper_id || cand.pmid)}
                      />
                    ))}
                </PaperCandidateList>
              </>
            )}

            {detailPaperId && <PaperDetailDrawer paperId={detailPaperId} onClose={() => setDetailPaperId(null)} />}
            </>
            )}
          </>
        )}
      </div>
    </div>
  )
}
