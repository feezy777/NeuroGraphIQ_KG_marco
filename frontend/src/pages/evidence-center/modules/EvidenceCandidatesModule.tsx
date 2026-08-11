import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
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
import { CandidatePaperCard, type CandidatePaperData } from '../components/PaperCard'
import { CandidateSummaryData } from '../components/CandidateSummary'
import { ClaimView } from '../components/ClaimView'
import { PaperDetailDrawer } from '../components/PaperDetailDrawer'
import { PaperEvidenceView } from '../components/PaperEvidenceView'
import { loadReviewStatus } from '../components/ReviewStatusStore'
import type { QueueEntry, QueueStatus, WorkbenchPassage } from '../components/types'

const DRAFT_PREFIX = 'evidence-center.review-draft.'

type EvidenceMode = 'auto' | 'function' | 'existence'

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
  const { state, queue, setQueue, openTarget, setCandidateSummary, setProgress } = useEvidenceCenter()
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
  useEffect(() => {
    if (!current) return
    const hasExtracted = (current.candidate_papers ?? []).some(c => (c.passages?.length ?? 0) > 0)
    if (hasExtracted || sessionStorage.getItem(`${DRAFT_PREFIX}${current.target_id}`)) {
      setProgress({ extracted: true })
    }
    if (loadReviewStatus(current.target_id)) {
      setProgress({ reviewed: true })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [current?.target_id])

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

  // 切换目标时重置选择状态
  useEffect(() => {
    setEvidenceViewPaperId(null)
    setDetailPaperId(null)
    setSelectedHashes(new Set())
    setExcludedPaperIds(new Set())
    setSearchExpanded(false)
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
  const querySummary = manualQuery.trim() || queryTerms.join(' · ') || '系统推荐检索式'

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
    void runSearch('')
  }, [runSearch])

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

  // ─── 右栏候选摘要(Context → RightPanel) ───
  const summary = useMemo<CandidateSummaryData | null>(() => {
    if (!current) return null
    const all = [...candidates, ...manualResults]
    const passages = all.flatMap(c => candidatePassagesToWorkbench(c.passages ?? [], c.paper_id))
    const verified = passages.filter(p => p.source_verified)
    const coverage = computeTmpCoverage(claimComponents, verified)
    return {
      claimText: dto?.claim_text ?? current.label ?? '',
      foundPapers: all.length + (manualResult?.papers.length ?? 0),
      extractedPapers: all.length,
      verifiedPassages: verified.length,
      selectedPassages: selectedHashes.size,
      coverageRatio: coverage.coverage_ratio,
      direction: aggregateTmpDirection(coverage, verified),
      modelAssessment: all[0]?.model_assessment ?? null,
    }
  }, [current, dto, candidates, manualResults, manualResult, claimComponents, selectedHashes])

  useEffect(() => { setCandidateSummary(summary) }, [summary, setCandidateSummary])
  useEffect(() => () => { setCandidateSummary(null) }, [setCandidateSummary])

  const totalPapers = candidates.length + manualResults.length + visibleSearchPapers.length

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
          <div className="evidence-candidates-empty">
            请先在「佐证任务」中打开一个任务，或从上方任务列表进入。
          </div>
        )}
        {!loading && !error && current && (
          <>
            <ClaimView
              claimText={dto?.claim_text ?? ''}
              components={claimComponents}
              targetType={current.target_type}
            />

            {message && <div className="ontology-page-message">{message}</div>}

            {evidencePaper ? (
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
            ) : (
              <>
                {manualTarget && (
                  hasSearchResults && !searchExpanded ? (
                    // 有检索结果 → 默认折叠为一条:Query 摘要 + [重新搜索](直接执行) + [展开检索]
                    <div className="evidence-search evidence-search-collapsed" data-testid="evidence-search-collapsed">
                      <span className="evidence-search-collapsed-label">已检索</span>
                      <span
                        className="evidence-search-collapsed-query"
                        data-testid="evidence-search-collapsed-query"
                        title={querySummary}
                      >
                        {querySummary}
                      </span>
                      <button type="button" className="btn btn-sm" disabled={manualBusy} onClick={() => void handleManualSearch()}>
                        {manualBusy ? '检索中…' : '重新搜索'}
                      </button>
                      <button type="button" className="btn btn-sm" onClick={() => setSearchExpanded(true)}>
                        展开检索
                      </button>
                    </div>
                  ) : (
                    <div className="evidence-search" data-testid="evidence-search">
                      <div className="evidence-search-layer">
                        <h4 className="evidence-search-title">查找相关论文</h4>
                        <div className="evidence-search-row">
                          <input
                            className="filter-input evidence-search-query"
                            data-testid="evidence-search-query"
                            value={manualQuery}
                            onChange={e => setManualQuery(e.target.value)}
                            placeholder="检索式 / 关键词（留空使用系统推荐检索式）"
                          />
                          <button type="button" className="btn btn-sm" disabled={manualBusy} onClick={() => void handleManualSearch()}>
                            {manualBusy ? '检索中…' : '重新搜索'}
                          </button>
                          <button type="button" className="btn btn-sm" disabled={manualBusy} onClick={() => void handleRestoreRecommended()}>
                            恢复系统推荐
                          </button>
                        </div>
                        {queryTerms.length > 0 && (
                          <div className="evidence-search-terms">
                            {queryTerms.map(t => (
                              <span key={t} className="evidence-query-term" data-testid="evidence-query-term">{t}</span>
                            ))}
                          </div>
                        )}
                      </div>
                      <div className="evidence-search-layer">
                        <h4 className="evidence-search-title">检索过滤</h4>
                        <div className="evidence-search-row">
                          <label className="evidence-search-filter">
                            <input type="checkbox" checked={oaOnly} onChange={e => setOaOnly(e.target.checked)} />
                            仅 OA
                          </label>
                          <label className="evidence-search-filter">
                            佐证模式
                            <select
                              className="filter-select"
                              value={modeOverride}
                              onChange={e => setModeOverride(e.target.value as EvidenceMode)}
                            >
                              <option value="auto">自动</option>
                              <option value="existence">存在性</option>
                              <option value="function">功能性</option>
                            </select>
                          </label>
                          <input
                            className="filter-input evidence-search-year"
                            value={yearFilter}
                            onChange={e => setYearFilter(e.target.value)}
                            placeholder="年份（如 2020）"
                          />
                          <button type="button" className="btn btn-xs" onClick={() => setExcludedPaperIds(new Set())}>
                            恢复排除
                          </button>
                        </div>
                      </div>
                      <div className="evidence-search-layer">
                        <h4 className="evidence-search-title">批量操作</h4>
                        <div className="evidence-search-row">
                          <button
                            type="button"
                            className="btn btn-sm"
                            disabled={visibleSearchPapers.length === 0}
                            onClick={() => setManualSelected(new Set(visibleSearchPapers.map(p => p.pmid)))}
                          >
                            全选
                          </button>
                          <button
                            type="button"
                            className="btn btn-sm btn-primary"
                            disabled={manualBusy || manualSelected.size === 0}
                            onClick={() => void handleManualExtract()}
                          >
                            提取所选论文（{manualSelected.size}）
                          </button>
                          {hasSearchResults && (
                            <button type="button" className="btn btn-xs" onClick={() => setSearchExpanded(false)}>
                              收起检索
                            </button>
                          )}
                        </div>
                      </div>
                    </div>
                  )
                )}

                <div className="evidence-candidates-papers">
                  <div className="evidence-candidates-papers-head">
                    <h4>候选论文（{totalPapers}）</h4>
                    <span className="evidence-module-hint">
                      勾选已核验片段后可从右栏「进入人工审核」；排除的论文可用「恢复排除」找回。
                    </span>
                  </div>
                  {totalPapers === 0 && (
                    <div className="evidence-candidates-empty">
                      {manualTarget
                        ? '没有找到候选论文，可先在上方检索相关论文或切换其他对象。'
                        : '当前对象暂无候选证据，可尝试重新提取或切换其他对象。'}
                    </div>
                  )}
                  {visibleSearchPapers.map(p => (
                    <CandidatePaperCard
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
                    <CandidatePaperCard
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
                      <CandidatePaperCard
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
                </div>
              </>
            )}

            {detailPaperId && <PaperDetailDrawer paperId={detailPaperId} onClose={() => setDetailPaperId(null)} />}
          </>
        )}
      </div>
    </div>
  )
}
