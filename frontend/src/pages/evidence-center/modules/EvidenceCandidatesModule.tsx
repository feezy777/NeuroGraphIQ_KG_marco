import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { MousePointerClick } from 'lucide-react'
import {
  extractSelectedPaperEvidence,
  getEvidenceTarget,
  listPaperEvidenceTaskItems,
  searchPaperEvidence,
  type EvidenceTargetDto,
  type PaperEvidenceTaskItem,
  type PaperSearchResponse,
} from '../../../api/endpoints'
import { useEvidenceCenter } from '../EvidenceCenterContext'
import { INITIAL_QUEUE_KEY } from '../evidenceCenterUrl'
import { candidatePassagesToWorkbench } from '../components/candidatePassages'
import { aggregateTmpDirection, computeTmpCoverage } from '../components/claimCoverage'
import { EmptyState } from '../components/EmptyState'
import { PaperBatchActions } from '../components/PaperBatchActions'
import { PaperCandidateCard, type CandidatePaperData } from '../components/PaperCandidateCard'
import { PaperCandidateList } from '../components/PaperCandidateList'
import { PaperSearchFilters, type EvidenceMode } from '../components/PaperSearchFilters'
import { PaperSearchPanel } from '../components/PaperSearchPanel'
import { PaperStatusSummary, type CandidateStats } from '../components/PaperStatusSummary'
import { PaperDetailDrawer } from '../components/PaperDetailDrawer'
import { PaperEvidenceView } from '../components/PaperEvidenceView'
import { loadReviewStatus } from '../components/ReviewStatusStore'
import type { QueueEntry, QueueStatus, WorkbenchPassage } from '../components/types'

const DRAFT_PREFIX = 'evidence-center.review-draft.'

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
}

interface ReviewDraft {
  passages: WorkbenchPassage[]
  modelDirection: string | null
  modelAssessment: string | null
  paperTitle: string
  pmid: string
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

export function EvidenceCandidatesModule() {
  const { state, queue, setQueue, openTarget, setCandidateClaim, setProgress } = useEvidenceCenter()
  const [items, setItems] = useState<PaperEvidenceTaskItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [dto, setDto] = useState<EvidenceTargetDto | null>(null)
  const [excludedPaperIds, setExcludedPaperIds] = useState<Set<string>>(new Set())
  const [selectedHashes, setSelectedHashes] = useState<Set<string>>(new Set())
  const [reExtractBusy, setReExtractBusy] = useState<string | null>(null)
  const [manualQuery, setManualQuery] = useState('')
  const [manualResult, setManualResult] = useState<PaperSearchResponse | null>(null)
  const [manualBusy, setManualBusy] = useState(false)
  const [manualSelected, setManualSelected] = useState<Set<string>>(new Set())
  const [manualResults, setManualResults] = useState<CandidatePaper[]>([])
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
      return
    }
    let cancelled = false
    setDto(null)
    getEvidenceTarget(t, id)
      .then(d => { if (!cancelled) setDto(d) })
      .catch(() => { if (!cancelled) setDto(null) })
    return () => { cancelled = true }
  }, [current?.target_type, current?.target_id])

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

  // ─── 搜索区(仅任务为空时的手动兜底入口;三层:查找论文/过滤/批量) ───
  const manualTarget = current && items.length === 0
    ? { target_type: current.target_type, target_id: current.target_id }
    : null

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
    return papers.filter(p =>
      !excludedPaperIds.has(p.pmid)
      && (!oaOnly || p.is_open_access)
      && (!yearFilter || Number(p.year) >= Number(yearFilter)),
    )
  }, [manualResult, oaOnly, yearFilter, excludedPaperIds])

  /** 是否有检索结果:有结果 → 检索区默认折叠为一条;无结果 → 展开完整检索区 */
  const hasSearchResults = (manualResult?.papers.length ?? 0) > 0

  /** 折叠条 Query 摘要(截断显示):手动检索式 → 推荐词 → 占位 */
  const querySummary = manualQuery.trim() || visibleQueryTerms.join(' · ') || '系统推荐检索式'

  const runSearch = useCallback(async (query: string) => {
    if (!manualTarget) return
    setManualBusy(true)
    setMessage(null)
    try {
      const resp = await searchPaperEvidence({
        target_type: manualTarget.target_type,
        target_id: manualTarget.target_id,
        limit: 10,
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
    const papers = visibleSearchPapers.filter(p => manualSelected.has(p.pmid) && Boolean(p.pmid || p.doi))
    if (papers.length === 0) return
    setManualBusy(true)
    setMessage(null)
    try {
      const resp = await extractSelectedPaperEvidence({
        target_type: manualTarget.target_type,
        target_id: manualTarget.target_id,
        papers: papers.map(p => ({ pmid: p.pmid, doi: p.doi, title: p.title })),
        mode: effectiveMode,
      })
      setManualResults(resp.results)
      // 已有提取片段 → 推进 StepPills → 找到原文
      setProgress({ extracted: true })
      setMessage(`已提取 ${resp.results.length} 篇论文，请勾选片段后加入人工审核`)
    } catch (err) {
      setMessage(`批量提取失败：${err instanceof Error ? err.message : String(err)}`)
    } finally {
      setManualBusy(false)
    }
  }, [manualTarget, manualSelected, visibleSearchPapers, effectiveMode, setProgress])

  /** ☐全选:勾选全部可见搜索结果 / 取消清空其勾选 */
  const handleToggleAll = useCallback((checked: boolean) => {
    setManualSelected(prev => {
      const next = new Set(prev)
      for (const p of visibleSearchPapers) {
        if (checked) next.add(p.pmid)
        else next.delete(p.pmid)
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

  // ─── 中栏状态条数据(候选/已提取/已核验/覆盖/模型判断) ───
  const stats = useMemo<CandidateStats | null>(() => {
    if (!current) return null
    const all = [...candidates, ...manualResults]
    const passages = all.flatMap(c => candidatePassagesToWorkbench(c.passages ?? [], c.paper_id))
    const verified = passages.filter(p => p.source_verified)
    const coverage = computeTmpCoverage(claimComponents, verified)
    return {
      foundPapers: all.length + (manualResult?.papers.length ?? 0),
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

  const totalPapers = candidates.length + manualResults.length + visibleSearchPapers.length

  const handleEnterReview = useCallback(() => {
    if (state.targetType && state.targetId) openTarget(state.targetType, state.targetId, 'review')
  }, [state.targetType, state.targetId, openTarget])

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
                    onExpand={() => setSearchExpanded(true)}
                    selectedCount={manualSelected.size}
                    onExtractSelected={() => void handleManualExtract()}
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
                        allSelected={visibleSearchPapers.length > 0 && visibleSearchPapers.every(p => manualSelected.has(p.pmid))}
                        onToggleAll={handleToggleAll}
                        selectedCount={manualSelected.size}
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

                <PaperCandidateList
                  total={totalPapers}
                  searchable={Boolean(manualTarget)}
                  excludedCount={excludedPaperIds.size}
                  onRestoreExcluded={() => setExcludedPaperIds(new Set())}
                  onAdjustSearch={() => setSearchExpanded(true)}
                >
                  {visibleSearchPapers.map(p => (
                    <PaperCandidateCard
                      key={`s-${p.pmid}`}
                      paper={searchToCardData(p)}
                      selected={manualSelected.has(p.pmid)}
                      reExtracting={false}
                      onToggleSelected={checked => {
                        setManualSelected(prev => {
                          const next = new Set(prev)
                          if (checked) next.add(p.pmid)
                          else next.delete(p.pmid)
                          return next
                        })
                      }}
                      onOpenDetail={() => undefined}
                      onExclude={() => setExcludedPaperIds(prev => new Set(prev).add(p.pmid))}
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
                  {manualResults
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
      </div>
    </div>
  )
}
