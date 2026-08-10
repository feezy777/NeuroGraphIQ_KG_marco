import { useCallback, useEffect, useMemo, useRef, useState, type PointerEvent as ReactPointerEvent } from 'react'
import {
  attachPaperEvidence,
  attachPaperEvidencePreview,
  completePaperEvidenceTaskItem,
  extractPaperPassage,
  extractSelectedPaperEvidence,
  getEvidenceQueue,
  getEvidenceTarget,
  listPaperEvidence,
  listPaperEvidenceTaskItems,
  saveTaskItemDraft,
  searchPaperEvidence,
  translateEvidenceText,
  validatePassageSelection,
  writeEvidenceAudit,
  type AttachPreviewResponse,
  type EvidencePassageInput,
  type EvidenceTargetDto,
  type PaperEvidenceItem,
  type PaperSearchResponse,
} from '../../api/endpoints'
import { ConfirmDialog } from '../../components/ConfirmDialog'
import { AttachDialog } from '../evidence-center/components/AttachDialog'
import { candidatePassagesToWorkbench } from '../evidence-center/components/candidatePassages'
import { ClaimPanel } from '../evidence-center/components/ClaimPanel'
import { CoveragePanel } from '../evidence-center/components/CoveragePanel'
import { PassageEvidenceCard } from '../evidence-center/components/PassageEvidenceCard'
import { ReviewerPanel } from '../evidence-center/components/ReviewerPanel'
import { aggregateTmpDirection, computeTmpCoverage } from '../evidence-center/components/claimCoverage'
import {
  DIRECTION_LABEL,
  type ClaimComponent,
  type Direction,
  type EvidenceLevel,
  type QueueEntry,
  type QueueStatus,
  type WorkbenchDraft,
  type WorkbenchPassage,
} from '../evidence-center/components/types'

interface QueueItem {
  target_type: string
  target_id: string
  label: string
  confidence: number | null
}

const STORAGE_KEY = 'neurographiq.evidenceWorkbench.queue.v1'
const STEPS = ['确认对象', '查找论文', '找到原文', '人工审核', '确认入库']
const STEPS_HINT = [
  '确认当前需要被论文证明的知识事实',
  '从 Europe PMC 找到可能相关的真实论文',
  'DeepSeek 从摘要/全文定位真实佐证片段',
  '确认这些原文究竟证明了什么',
  '预览证据和置信度变化后正式保存',
]

const DEFAULT_DRAFT: WorkbenchDraft = {
  query: '',
  selectedPmid: '',
  passages: [],
  translations: {},
  reviewerDirection: 'supports',
  reviewerEvidenceLevel: 'indirect',
  reviewerConfidence: '0.8',
  note: '',
  step: 0,
}

function loadSaved(): { queue: QueueEntry[]; idx: number } | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw) as { queue?: QueueEntry[]; idx?: number }
    if (!Array.isArray(parsed.queue) || parsed.queue.length === 0) return null
    return { queue: parsed.queue, idx: Math.min(parsed.idx ?? 0, parsed.queue.length - 1) }
  } catch {
    return null
  }
}

export function EvidenceReviewModal({ open, onClose, initialItems, initialTaskId }: {
  open: boolean
  onClose: () => void
  initialItems?: QueueItem[]
  initialTaskId?: string
}) {
  const [queue, setQueue] = useState<QueueEntry[]>([])
  const [idx, setIdx] = useState(0)
  const [step, setStep] = useState(0)
  const [busy, setBusy] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [minimized, setMinimized] = useState(false)
  const [heightPct, setHeightPct] = useState(72)
  const [onlyPending, setOnlyPending] = useState(false)
  const [autoNext, setAutoNext] = useState(true)

  const [dto, setDto] = useState<EvidenceTargetDto | null>(null)
  const [result, setResult] = useState<PaperSearchResponse | null>(null)
  const [selectedPaperIds, setSelectedPaperIds] = useState<Set<string>>(new Set())
  const [paperExtractResults, setPaperExtractResults] = useState<Record<string, {
    busy?: boolean
    error?: string
    model_direction?: string | null
    fulltext_fetched?: boolean | null
    passages?: WorkbenchPassage[]
  }>>({})
  const [query, setQuery] = useState('')
  const [chips, setChips] = useState<string[]>([])
  const [excludedPmids, setExcludedPmids] = useState<Set<string>>(new Set())
  const [oaOnly, setOaOnly] = useState(false)
  const [yearFilter, setYearFilter] = useState('')
  const [claimMode, setClaimMode] = useState<'function' | 'existence'>('function')
  const claimModeTouchedRef = useRef(false)
  const [selectedPmid, setSelectedPmid] = useState('')
  const [passages, setPassages] = useState<WorkbenchPassage[]>([])
  const [selectedHashes, setSelectedHashes] = useState<Set<string>>(new Set())
  const [translations, setTranslations] = useState<Record<string, string>>({})
  const [direction, setDirection] = useState<Direction>('supports')
  const [modelDirection, setModelDirection] = useState<Direction | null>(null)
  const [modelAssessment, setModelAssessment] = useState<string | null>(null)
  const [evidenceLevel, setEvidenceLevel] = useState<EvidenceLevel>('indirect')
  const [confidence, setConfidence] = useState('0.8')
  const [note, setNote] = useState('')
  const [preview, setPreview] = useState<AttachPreviewResponse | null>(null)
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [dirty, setDirty] = useState(false)
  const [closeConfirm, setCloseConfirm] = useState(false)
  const [showContextHash, setShowContextHash] = useState<string | null>(null)
  const [saveState, setSaveState] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle')
  const [serverDraftConfirm, setServerDraftConfirm] = useState(false)
  const [existingEvidence, setExistingEvidence] = useState<PaperEvidenceItem[]>([])

  const taskIdRef = useRef<string | null>(null)
  const abortRef = useRef<AbortController | null>(null)
  const targetRef = useRef<string | null>(null)
  const autosaveRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const revisionRef = useRef(0)
  const draftRef = useRef<WorkbenchDraft>({ ...DEFAULT_DRAFT })
  const queueRef = useRef<QueueEntry[]>([])
  queueRef.current = queue

  const current = queue[idx]
  const selectedPaper = result?.papers.find(p => p.pmid === selectedPmid)
  const claimComponents: ClaimComponent[] = dto?.claim_components ?? []
  const claimText = dto?.claim_text ?? ''

  const audit = useCallback((actionType: string, afterData: Record<string, unknown>, entityId?: string) => {
    const eid = entityId ?? current?.target_id
    if (!eid) return
    void writeEvidenceAudit({
      action_type: actionType,
      entity_type: 'evidence',
      entity_id: eid,
      after_data: afterData,
      reason: 'workbench interaction',
    }).catch(() => { /* best-effort */ })
  }, [current])

  const persist = useCallback((q: QueueEntry[], i: number) => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify({ queue: q, idx: i, savedAt: new Date().toISOString() }))
    } catch { /* ignore */ }
  }, [])

  const mark = useCallback((i: number, status: QueueStatus) => {
    setQueue(q => {
      const next = q.map((e, j) => (j === i ? { ...e, status } : e))
      persist(next, i)
      return next
    })
  }, [persist])

  const loadEvidenceMeta = useCallback(async (item: QueueItem) => {
    try {
      const r = await listPaperEvidence({ target_type: item.target_type, target_id: item.target_id, limit: 100 })
      return {
        count: r.items.length,
        pmids: new Set(r.items.map(it => it.pmid).filter((p): p is string => Boolean(p))),
      }
    } catch {
      return { count: 0, pmids: new Set<string>() }
    }
  }, [])

  const loadDto = useCallback(async (item: QueueItem) => {
    try {
      const d = await getEvidenceTarget(item.target_type, item.target_id)
      setDto(d)
      return d
    } catch {
      setDto(null)
      return null
    }
  }, [])

  const syncDraft = useCallback(() => {
    draftRef.current = {
      query,
      selectedPmid,
      passages,
      translations,
      reviewerDirection: direction,
      reviewerEvidenceLevel: evidenceLevel,
      reviewerConfidence: confidence,
      note,
      step,
    }
  }, [query, selectedPmid, passages, translations, direction, evidenceLevel, confidence, note, step])

  const applyDraft = useCallback((d: WorkbenchDraft | undefined) => {
    const draft = d ?? DEFAULT_DRAFT
    setQuery(draft.query)
    setSelectedPmid(draft.selectedPmid)
    setPassages(draft.passages)
    setDirection(draft.reviewerDirection)
    setEvidenceLevel(draft.reviewerEvidenceLevel)
    setConfidence(draft.reviewerConfidence)
    setNote(draft.note)
    setStep(draft.step)
    setSelectedHashes(new Set(draft.passages.filter(p => p.source_verified).map(p => p.hash)))
    setTranslations(draft.translations ?? {})
    setPreview(null)
    setConfirmOpen(false)
    setDirty(false)
    setSaveState('idle')
    revisionRef.current = 0
    draftRef.current = { ...draft }
  }, [])

  const saveCurrentDraft = useCallback((i: number) => {
    syncDraft()
    const d = { ...draftRef.current }
    setQueue(q => q.map((e, j) => (j === i ? { ...e, draft: d } : e)))
    setDirty(false)
  }, [syncDraft])

  const startSearch = useCallback(async (item: QueueEntry, q: string, itemIdx: number) => {
    if (!item) return false
    abortRef.current?.abort()
    abortRef.current = new AbortController()
    targetRef.current = item.target_id
    setBusy('search')
    setMessage(null)
    try {
      const effectiveMode = claimModeTouchedRef.current
        ? claimMode
        : (item.target_type === 'connection' || item.target_type === 'projection' ? 'existence' : 'function')
      const resp = await searchPaperEvidence({
        target_type: item.target_type,
        target_id: item.target_id,
        limit: 10,
        mode: effectiveMode,
        query_override: q.trim() || undefined,
      }, abortRef.current.signal)
      if (targetRef.current !== item.target_id) return false
      setResult(resp)
      setQuery(q || resp.target_info.query)
      setChips((resp.target_info.query || '').split(' AND ').filter(Boolean))
      setSelectedPmid('')
      setPassages([])
      setSelectedHashes(new Set())
      setStep(1)
      return true
    } catch (err) {
      if (targetRef.current !== item.target_id) return false
      setMessage(`检索失败：${err instanceof Error ? err.message : String(err)}`)
      mark(itemIdx, 'failed')
      return false
    } finally {
      setBusy(null)
    }
  }, [mark, claimMode])

  const goto = useCallback(async (i: number) => {
    if (i < 0 || i >= queueRef.current.length) return
    saveCurrentDraft(idx)
    const target = queueRef.current[i]
    abortRef.current?.abort()
    targetRef.current = target.target_id
    setIdx(i)
    setStep(0)
    setResult(null)
    setPassages([])
    setSelectedHashes(new Set())
    setTranslations({})
    setPreview(null)
    setConfirmOpen(false)
    setMessage(null)
    setShowContextHash(null)
    const meta = await loadEvidenceMeta(target)
    await loadDto(target)
    setQueue(q => q.map((e, j) => j === i ? { ...e, evidenceCount: meta.count } : e))
    if (target.draft) {
      applyDraft(target.draft)
    } else if (target.draftPassages && target.draftPassages.length > 0) {
      setPassages(target.draftPassages)
      setSelectedHashes(new Set(target.draftPassages.map(p => p.hash)))
      setSelectedPmid(target.draftPmid ?? '')
      setDirection(target.draftDirection ?? 'supports')
      setStep(2)
      setMessage('已加载批量提取草稿，请人工审核后入库')
    } else if (target.status === 'pending' || target.status === 'failed') {
      mark(i, 'searching')
      void startSearch(target, '', i)
    }
  }, [idx, saveCurrentDraft, loadEvidenceMeta, loadDto, applyDraft, mark, startSearch])

  const initQueue = useCallback(async (items: Array<QueueItem & { taskItemId?: string; draftPmid?: string; draftPassages?: WorkbenchPassage[]; draftDirection?: Direction; draft?: WorkbenchDraft; preprocessOutcome?: string | null; modelDirection?: Direction | null }>) => {
    const metas = await Promise.all(items.map(loadEvidenceMeta))
    const enriched: QueueEntry[] = items.map((it, i) => ({
      ...it,
      status: 'pending' as const,
      evidenceCount: metas[i].count,
      taskItemId: it.taskItemId,
      draftPmid: it.draftPmid,
      draftPassages: it.draftPassages,
      draftDirection: it.draftDirection,
      draft: it.draft,
      preprocessOutcome: it.preprocessOutcome,
      modelDirection: it.modelDirection,
    }))
    setQueue(enriched)
    setIdx(0)
    setStep(0)
    setResult(null)
    setPassages([])
    setSelectedHashes(new Set())
    setTranslations({})
    setPreview(null)
    setMessage(null)
    setExcludedPmids(new Set())
    setOaOnly(false)
    setYearFilter('')
    persist(enriched, 0)
    if (enriched[0]) {
      await loadDto(enriched[0])
      if (enriched[0].draft) {
        applyDraft(enriched[0].draft)
      } else if (enriched[0].draftPassages && enriched[0].draftPassages.length > 0) {
        setPassages(enriched[0].draftPassages)
        setSelectedHashes(new Set(enriched[0].draftPassages.map(p => p.hash)))
        setSelectedPmid(enriched[0].draftPmid ?? '')
        setDirection(enriched[0].draftDirection ?? 'supports')
        setStep(2)
      } else {
        void startSearch(enriched[0], '', 0)
      }
    }
  }, [loadEvidenceMeta, loadDto, startSearch, persist])

  const loadTaskQueue = useCallback(async (taskId: string) => {
    setBusy('loading')
    setMessage(null)
    try {
      taskIdRef.current = taskId
      const r = await listPaperEvidenceTaskItems(taskId, { limit: 200 })
      const items: Array<QueueItem & { taskItemId: string; draftPmid?: string; draftPassages?: WorkbenchPassage[]; draftDirection?: Direction; draft?: WorkbenchDraft; preprocessOutcome?: string | null; modelDirection?: Direction | null }> = []
      for (const it of r.items) {
        const draftPassages: WorkbenchPassage[] = (it.candidate_papers ?? []).flatMap(
          (cand): WorkbenchPassage[] => candidatePassagesToWorkbench(cand.passages ?? [], cand.paper_id),
        )
        items.push({
          target_type: it.target_type,
          target_id: it.target_id,
          label: it.label || it.target_id,
          confidence: it.current_confidence,
          taskItemId: it.id,
          preprocessOutcome: it.preprocess_outcome,
          modelDirection: it.model_direction as Direction | null,
          draftPmid: it.pmid ?? undefined,
          draftPassages,
          draftDirection: it.direction as Direction | undefined,
          draft: (it.review_draft as unknown as WorkbenchDraft | undefined),
        })
      }
      await initQueue(items)
      setMessage(`已恢复批量任务，共 ${items.length} 条待审核草稿`)
    } catch (err) {
      setMessage(`加载批量任务失败：${err instanceof Error ? err.message : String(err)}`)
    } finally {
      setBusy(null)
    }
  }, [initQueue])

  useEffect(() => {
    if (!open) return
    if (initialTaskId) {
      void loadTaskQueue(initialTaskId)
      return
    }
    if (initialItems && initialItems.length > 0) {
      void initQueue(initialItems)
      return
    }
    const saved = loadSaved()
    if (saved) {
      setQueue(saved.queue)
      setIdx(saved.idx)
      setMessage('已恢复上次处理进度')
      const restored = saved.queue[saved.idx]
      if (restored) {
        void loadDto(restored)
        if (restored.draft) applyDraft(restored.draft)
        else if (restored.draftPassages?.length) {
          setPassages(restored.draftPassages)
          setSelectedHashes(new Set(restored.draftPassages.map(p => p.hash)))
          setSelectedPmid(restored.draftPmid ?? '')
          setStep(2)
          setMessage('已恢复上次处理进度')
        } else if (restored.status === 'pending' || restored.status === 'failed') {
          void startSearch(restored, '', saved.idx).then(ok => {
            if (ok) setMessage('已恢复上次处理进度')
          })
        }
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  const extractOneForPaper = useCallback(async (paper: NonNullable<PaperSearchResponse['papers'][number]>) => {
    if (!current) return null
    abortRef.current?.abort()
    abortRef.current = new AbortController()
    targetRef.current = current.target_id
    setBusy('extract')
    try {
      const r = await extractPaperPassage({
        target_type: current.target_type,
        target_id: current.target_id,
        pmid: paper.pmid,
        doi: paper.doi,
        pmcid: paper.pmcid,
        title: paper.title,
        abstract: paper.abstract,
      }, abortRef.current.signal)
      if (targetRef.current !== current.target_id) return null
      const mapped: WorkbenchPassage[] = r.passages.map((p, i) => ({
        hash: `${paper.pmid}-${i}-${p.passage}`,
        paper_id: null,
        paper_passage_id: null,
        source_scope: p.source_scope,
        section_title: p.section_title,
        paragraph_index: p.paragraph_index,
        paragraph_id: p.paragraph_id,
        passage: p.passage,
        translation_zh: null,
        direction: p.direction,
        evidence_level: p.evidence_level ?? 'indirect',
        reason: p.reason,
        confidence: p.confidence,
        semantic_confidence: p.semantic_confidence,
        source_locator: p.source_locator,
        source_verified: p.source_verified,
        source_verification_method: p.source_verification_method,
        supported_components: p.supported_components ?? [],
      }))
      return { passages: mapped, model_direction: r.overall_direction, model_assessment: r.assessment }
    } catch (err) {
      if (targetRef.current !== current.target_id) return null
      throw err
    } finally {
      setBusy(null)
    }
  }, [current])

  const extract = useCallback(async () => {
    if (!current || !selectedPaper) return
    setMessage(null)
    setStep(2)
    try {
      const result = await extractOneForPaper(selectedPaper)
      if (!result) return
      setPassages(result.passages)
      setSelectedHashes(new Set(result.passages.filter(p => p.source_verified).map(p => p.hash)))
      setModelDirection(result.model_direction)
      setModelAssessment(result.model_assessment)
      setDirection(result.model_direction ?? 'supports')
      setStep(3)
      const verified = result.passages.filter(p => p.source_verified).length
      setMessage(`找到 ${result.passages.length} 个候选证据片段：${verified} 个已通过原文核验，${result.passages.length - verified} 个未通过核验`)
    } catch (err) {
      const raw = err instanceof Error ? err.message : String(err)
      const paperTitle = selectedPaper?.title ?? '当前论文'
      if (raw.includes('parse_error')) {
        setMessage(`「${paperTitle}」提取解析失败（DeepSeek 返回内容无法解析），请重试或换一篇论文`)
      } else if (raw.includes('network_error')) {
        setMessage(`「${paperTitle}」网络/服务错误，请稍后重试`)
      } else {
        setMessage(`提取失败：${raw}`)
      }
      mark(idx, 'failed')
    }
  }, [current, selectedPaper, idx, mark, extractOneForPaper])

  const extractSelected = useCallback(async () => {
    if (!current || selectedPaperIds.size === 0) return
    const papers = (result?.papers ?? []).filter(p => selectedPaperIds.has(p.pmid))
    const extractable = papers.filter(p => p.pmid || p.doi)
    if (extractable.length === 0) {
      setMessage('所选论文均缺少 PMID/DOI，无法提取')
      return
    }
    setPaperExtractResults({})
    setMessage(null)
    setBusy('extract')
    try {
      const resp = await extractSelectedPaperEvidence({
        target_type: current.target_type,
        target_id: current.target_id,
        papers: extractable.map(p => ({ pmid: p.pmid, doi: p.doi, pmcid: p.pmcid, title: p.title })),
        mode: claimMode,
      })
      const next: Record<string, {
        busy?: boolean
        error?: string
        model_direction?: string | null
        fulltext_fetched?: boolean | null
        passages?: WorkbenchPassage[]
      }> = {}
      let okCount = 0
      for (const cand of resp.results) {
        const pmid = cand.pmid
        if (cand.error_code === 'SEMANTIC_SKIPPED') {
          next[pmid] = {
            busy: false,
            error: `相关性评分过低已跳过（${cand.semantic_relevance ?? '—'}）：${cand.error_message ?? ''}`,
          }
          continue
        }
        if (cand.error_code) {
          next[pmid] = { busy: false, error: `提取失败（${cand.error_code}）：${cand.error_message ?? ''}` }
          continue
        }
        const passages = candidatePassagesToWorkbench(cand.passages ?? [], cand.paper_id)
        if (passages.some(p => p.source_verified)) okCount += 1
        next[pmid] = {
          busy: false,
          model_direction: cand.model_direction,
          fulltext_fetched: cand.fulltext_fetched ?? null,
          passages,
        }
      }
      setPaperExtractResults(next)
      setMessage(
        `已提取 ${extractable.length} 篇论文，${okCount} 篇找到有效片段；点击论文下方「载入片段」进入审核`,
      )
    } catch (err) {
      setMessage(`批量提取失败：${err instanceof Error ? err.message : String(err)}`)
    } finally {
      setBusy(null)
    }
  }, [current, selectedPaperIds, result, claimMode])

  const loadPaperResult = useCallback((paper: NonNullable<PaperSearchResponse['papers'][number]>, passages: WorkbenchPassage[]) => {
    setPassages(passages)
    setSelectedHashes(new Set(passages.filter(p => p.source_verified).map(p => p.hash)))
    const res = paperExtractResults[paper.pmid]
    setModelDirection((res?.model_direction as Direction) ?? null)
    setDirection((res?.model_direction as Direction) ?? 'supports')
    setSelectedPmid(paper.pmid)
    setStep(3)
    setDirty(true)
    const verified = passages.filter(p => p.source_verified).length
    setMessage(`已载入「${paper.title}」的 ${passages.length} 个候选片段（${verified} 个已核验），请人工审核`)
  }, [paperExtractResults])

  const translatePassage = useCallback(async (hash: string, text: string) => {
    abortRef.current?.abort()
    abortRef.current = new AbortController()
    setBusy('translate')
    try {
      const r = await translateEvidenceText({ text }, abortRef.current.signal)
      setTranslations(t => ({ ...t, [hash]: r.translated }))
      setDirty(true)
    } catch (err) {
      setMessage(`翻译失败：${err instanceof Error ? err.message : String(err)}`)
    } finally {
      setBusy(null)
    }
  }, [])

  const selectedPassages = useMemo(
    () => passages.filter(p => selectedHashes.has(p.hash) && p.source_verified),
    [passages, selectedHashes],
  )

  const tmpCoverage = useMemo(
    () => computeTmpCoverage(claimComponents, selectedPassages),
    [claimComponents, selectedPassages],
  )
  const tmpDirection = useMemo(
    () => aggregateTmpDirection(tmpCoverage, selectedPassages),
    [tmpCoverage, selectedPassages],
  )

  const busyText = useMemo(() => {
    const paperTitle = selectedPaper?.title ?? (current?.draftPmid ? '批量草稿论文' : '')
    switch (busy) {
      case 'search': return '正在检索 Europe PMC…'
      case 'extract': return paperTitle
        ? `DeepSeek 正在提取「${paperTitle}」的原文片段（最多 3 次尝试）…`
        : 'DeepSeek 正在提取原文片段…'
      case 'translate': return '正在翻译…'
      case 'preview': return '正在计算置信度预览…'
      case 'attach': return '正在入库并更新置信度…'
      case 'loading': return '正在加载队列…'
      default: return busy ? `处理中：${busy}` : ''
    }
  }, [busy, selectedPaper, current])

  const updatePassage = useCallback((hash: string, patch: Partial<WorkbenchPassage>) => {
    setPassages(ps => ps.map(p => (p.hash === hash ? { ...p, ...patch } : p)))
    setDirty(true)
  }, [])

  const reselect = useCallback(async (paperPassageId: string, text: string) => {
    try {
      const r = await validatePassageSelection({ paper_passage_id: paperPassageId, selected_text: text })
      if (!r.source_verified) {
        setMessage('重新截取未通过原文校验，禁止使用')
        return false
      }
      const hash = passages.find(p => p.paper_passage_id === paperPassageId)?.hash
      if (hash) {
        updatePassage(hash, {
          passage: r.normalized_selection ?? text,
          source_verified: true,
          source_verification_method: r.verification_method,
        })
      }
      setMessage('重新截取已通过原文校验')
      return true
    } catch (err) {
      setMessage(`重新截取失败：${err instanceof Error ? err.message : String(err)}`)
      return false
    }
  }, [passages, updatePassage])

  const runPreview = useCallback(async () => {
    if (!current || !selectedPmid) return
    if (selectedPassages.length === 0) {
      setPreview(null)
      return
    }
    abortRef.current?.abort()
    abortRef.current = new AbortController()
    setBusy('preview')
    try {
      const r = await attachPaperEvidencePreview({
        target_type: current.target_type,
        target_id: current.target_id,
        pmid: selectedPmid,
        direction,
        reviewer_confidence: parseFloat(confidence) || 0,
        passages: selectedPassages.map(p => ({
          source_scope: p.source_scope,
          paragraph_index: p.paragraph_index,
          passage: p.passage,
          direction: p.direction,
          reason: p.reason,
          confidence: p.confidence,
          source_locator: p.source_locator,
          source_verified: true,
          supported_components: p.supported_components,
        })),
      }, abortRef.current.signal)
      setPreview(r)
    } catch (err) {
      setMessage(`预览失败：${err instanceof Error ? err.message : String(err)}`)
    } finally {
      setBusy(null)
    }
  }, [current, selectedPmid, selectedPassages, direction, confidence])

  useEffect(() => {
    const t = setTimeout(() => void runPreview(), 350)
    return () => clearTimeout(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [direction, confidence, selectedHashes, passages, selectedPmid])

  // backend autosave for batch-task items (debounced)
  useEffect(() => {
    if (!taskIdRef.current || !current?.taskItemId) return
    if (autosaveRef.current) clearTimeout(autosaveRef.current)
    autosaveRef.current = setTimeout(() => {
      syncDraft()
      setSaveState('saving')
      const rev = revisionRef.current + 1
      void saveTaskItemDraft(current.taskItemId!, draftRef.current as unknown as Record<string, unknown>, rev)
        .then(r => { revisionRef.current = r.server_revision; setSaveState('saved') })
        .catch(() => setSaveState('error'))
    }, 500)
    return () => { if (autosaveRef.current) clearTimeout(autosaveRef.current) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query, selectedPmid, passages, direction, evidenceLevel, confidence, note, step, current?.taskItemId])

  const attach = useCallback(async () => {
    if (!current || !selectedPmid || selectedPassages.length === 0) return
    setBusy('attach')
    setMessage(null)
    try {
      const body: EvidencePassageInput[] = selectedPassages.map(p => ({
        source_scope: p.source_scope,
        section_title: p.section_title,
        paragraph_index: p.paragraph_index,
        passage: p.passage,
        direction: p.direction,
        reason: p.reason,
        confidence: p.confidence,
        source_locator: p.source_locator,
        source_verified: true,
        supported_components: p.supported_components,
      }))
      const resp = await attachPaperEvidence({
        target_type: current.target_type,
        target_id: current.target_id,
        pmid: selectedPmid,
        direction,
        evidence_level: evidenceLevel,
        model_direction: modelDirection,
        model_assessment: modelAssessment,
        reviewer_note: note || null,
        reviewer_confidence: parseFloat(confidence) || 0,
        passages: body,
      })
      const meta = await loadEvidenceMeta(current)
      setQueue(q => q.map((e, j) => j === idx ? { ...e, status: 'completed' as const, evidenceCount: meta.count } : e))
      void listPaperEvidence({ target_type: current.target_type, target_id: current.target_id, limit: 20 })
        .then(r => setExistingEvidence(r.items))
        .catch(() => undefined)
      setConfirmOpen(false)
      setDirty(false)
      if (taskIdRef.current && current.taskItemId) {
        try {
          await completePaperEvidenceTaskItem(taskIdRef.current, current.taskItemId, resp.evidence_id)
        } catch { /* keep going */ }
      }
      const next = autoNext ? queue.findIndex((e, j) => j > idx && e.status === 'pending') : -1
      if (next >= 0) await goto(next)
      setMessage(
        `已添加 1 篇论文证据，保存 ${resp.passage_count} 个原文片段，` +
        `Confidence ${preview?.current_confidence ?? current?.confidence ?? '—'} → ${resp.confidence ?? '不变'}`,
      )
    } catch (err) {
      setMessage(`入库失败：${err instanceof Error ? err.message : String(err)}（草稿已保留）`)
    } finally {
      setBusy(null)
    }
  }, [current, selectedPmid, selectedPassages, direction, evidenceLevel, modelDirection, modelAssessment, note, confidence, preview, queue, idx, autoNext, loadEvidenceMeta, goto])

  const saveDraft = useCallback(() => {
    saveCurrentDraft(idx)
    persist(queueRef.current, idx)
    if (taskIdRef.current && current?.taskItemId) {
      if (autosaveRef.current) clearTimeout(autosaveRef.current)
      setSaveState('saving')
      const rev = revisionRef.current + 1
      void saveTaskItemDraft(current.taskItemId, draftRef.current as unknown as Record<string, unknown>, rev)
        .then(r => { revisionRef.current = r.server_revision; setSaveState('saved'); setMessage('草稿已保存到服务器') })
        .catch(() => { setSaveState('error'); setMessage('草稿保存到服务器失败') })
    } else {
      setMessage('草稿已保存到本地，关闭后可恢复')
    }
  }, [saveCurrentDraft, idx, persist, current])

  const handleClose = useCallback(() => {
    if (saveState === 'error') {
      setServerDraftConfirm(true)
      return
    }
    if (dirty) {
      setCloseConfirm(true)
      return
    }
    saveCurrentDraft(idx)
    persist(queueRef.current, idx)
    onClose()
  }, [dirty, saveState, saveCurrentDraft, idx, persist, onClose])

  const retrySaveAndClose = useCallback(() => {
    if (autosaveRef.current) clearTimeout(autosaveRef.current)
    syncDraft()
    setSaveState('saving')
    const rev = revisionRef.current + 1
    void saveTaskItemDraft(current?.taskItemId ?? '', draftRef.current as unknown as Record<string, unknown>, rev)
      .then(r => {
        revisionRef.current = r.server_revision
        setSaveState('saved')
        setServerDraftConfirm(false)
        saveCurrentDraft(idx)
        persist(queueRef.current, idx)
        onClose()
      })
      .catch(() => setSaveState('error'))
  }, [current, syncDraft, saveCurrentDraft, idx, persist, onClose])

  const skip = useCallback(() => {
    saveCurrentDraft(idx)
    mark(idx, 'skipped')
    const n = queue.findIndex((e, j) => j > idx && e.status === 'pending')
    if (n >= 0) void goto(n)
  }, [idx, saveCurrentDraft, mark, queue, goto])

  useEffect(() => {
    if (!current) {
      setExistingEvidence([])
      return
    }
    void listPaperEvidence({ target_type: current.target_type, target_id: current.target_id, limit: 20 })
      .then(r => setExistingEvidence(r.items))
      .catch(() => setExistingEvidence([]))
  }, [current])

  // connection/projection objects verify OBJECT EXISTENCE by default (retrieval
  // without function terms); user can override and the choice sticks.
  useEffect(() => {
    if (claimModeTouchedRef.current) return
    const t = current?.target_type
    setClaimMode(t === 'connection' || t === 'projection' ? 'existence' : 'function')
  }, [current])

  useEffect(() => {
    return () => { abortRef.current?.abort() }
  }, [])

  const startResize = useCallback((e: ReactPointerEvent<HTMLDivElement>) => {
    e.preventDefault()
    const onMove = (ev: PointerEvent) => {
      const next = Math.min(92, Math.max(48, Math.round(((window.innerHeight - ev.clientY) / window.innerHeight) * 100)))
      setHeightPct(next)
    }
    const onUp = () => {
      window.removeEventListener('pointermove', onMove)
      window.removeEventListener('pointerup', onUp)
    }
    window.addEventListener('pointermove', onMove)
    window.addEventListener('pointerup', onUp)
  }, [])

  if (!open) return null

  const visibleQueue = onlyPending ? queue.filter(e => e.status === 'pending') : queue
  const years = Array.from(new Set((result?.papers ?? []).map(p => p.year).filter(Boolean))).sort().reverse()
  const visiblePapers = (result?.papers ?? [])
    .filter(p => !excludedPmids.has(p.pmid))
    .filter(p => !oaOnly || p.is_open_access)
    .filter(p => !yearFilter || p.year === yearFilter)
  const allDone = queue.length > 0 && queue.every(e => e.status === 'completed' || e.status === 'skipped')
  const hasSimilarityPassage = selectedPassages.some(
    p => p.source_verification_method === 'similarity' || p.source_verification_method === 'similarity_located',
  )
  const attachDisabled =
    !current ||
    direction === 'not_found' ||
    selectedHashes.size === 0 ||
    busy !== null ||
    (hasSimilarityPassage && !note.trim())
  const attachDisabledReason = !current
    ? '当前没有对象'
    : direction === 'not_found'
      ? '未找到不能作为正式论文佐证入库'
      : selectedHashes.size === 0
        ? '至少选择一个已通过原文校验的证据片段'
        : hasSimilarityPassage && !note.trim()
          ? '存在近似匹配片段，请在备注中确认已核对原文'
          : busy !== null
            ? '正在处理中'
            : ''

  return (
    <div className="evidence-workbench" style={{ height: `${heightPct}vh` }} data-testid="ew-workbench">
      <div className="ew-resize" onPointerDown={startResize} title="拖动调整高度" />
      <div className="ew-header">
        <div>
          <strong>{current?.label ?? '论文佐证工作台'}</strong>
          <span className="ew-meta">{current?.target_type} · {dto?.granularity ?? '—'} · 置信度 {current?.confidence ?? '—'} · 已有证据 {current?.evidenceCount ?? 0}</span>
        </div>
        <span className="ew-progress">{Math.min(idx + 1, queue.length)}/{queue.length} · {current?.status ?? '—'}</span>
        <span className="ew-step-label" data-testid="ew-step-label">步骤 {step + 1}/5：{STEPS[step]}</span>
        <div className="ew-actions">
          <label className="ew-meta"><input type="checkbox" checked={autoNext} onChange={e => setAutoNext(e.target.checked)} /> 自动下一条</label>
          <button type="button" className="btn btn-xs" onClick={() => setMinimized(m => !m)}>{minimized ? '展开' : '最小化'}</button>
          <button type="button" className="btn btn-xs" onClick={handleClose}>关闭</button>
        </div>
      </div>
      {!minimized && (
        <div className="ew-body">
          <div className="ew-left">
            <div className="ew-left-tools">
              <label><input type="checkbox" checked={onlyPending} onChange={e => setOnlyPending(e.target.checked)} /> 只看未处理</label>
              <button type="button" className="btn btn-xs" onClick={() => { void loadTaskQueue('') }} disabled>批量任务（阶段4）</button>
            </div>
            {visibleQueue.map(e => {
              const realIdx = queue.indexOf(e)
              return (
                <div key={e.target_id} className={`ew-queue-item ${realIdx === idx ? 'ew-queue-active' : ''} ew-status-${e.status}`} data-testid="ew-queue-item" onClick={() => goto(realIdx)}>
                  <div className="ew-queue-name">{e.label}</div>
                  <div className="ew-queue-meta">{e.target_type} · {e.confidence ?? '—'} · 证据 {e.evidenceCount}</div>
                  <div className="ew-queue-status">{e.status}</div>
                  {e.preprocessOutcome === 'no_evidence_found' && <div className="ew-meta">系统未找到有效论文证据</div>}
                  {(e.modelDirection === 'mixed' || e.modelDirection === 'contradicts') && <div className="ew-bad">存在矛盾证据</div>}
                  {e.status === 'failed' && <button type="button" className="btn btn-xs" onClick={ev => { ev.stopPropagation(); void goto(realIdx) }}>重试</button>}
                  {e.status === 'completed' && <button type="button" className="btn btn-xs" onClick={ev => { ev.stopPropagation(); void goto(realIdx) }}>查看</button>}
                </div>
              )
            })}
            {visibleQueue.length === 0 && <div className="ontology-empty">队列为空</div>}
          </div>
          <div className="ew-center">
            <div className="ew-stepper" data-testid="ew-stepper">
              {STEPS.map((s, i) => (
                <div key={s} className={`ew-step ${i === step ? 'ew-step-active' : ''} ${i < step ? 'ew-step-done' : ''}`}>{s}</div>
              ))}
            </div>
            <div className="ew-hint">{STEPS_HINT[step]}</div>
            {message && <div className="ontology-page-message">{message}</div>}
            <div className="ew-progress-track">
              <div className="ew-progress-fill" style={{ width: `${Math.round(((step + 1) / 5) * 100)}%` }} />
              {busy && <div className="ew-progress-anim" />}
            </div>
            <div className="ew-progress-text">{busyText || `步骤 ${step + 1}/5：${STEPS[step]}`}</div>
            {busy && <div className="ew-busy">{busyText}</div>}
            {allDone && <div className="ew-done-banner">当前队列已处理完成</div>}

            <ClaimPanel
              claimText={claimText}
              components={claimComponents}
              confidence={current?.confidence ?? null}
              evidenceCount={current?.evidenceCount ?? 0}
              targetType={current?.target_type ?? ''}
              granularity={dto?.granularity ?? ''}
            />

            {existingEvidence.length > 0 && (
              <div className="ew-section" data-testid="ew-existing-evidence">
                <h4>已有论文证据（{existingEvidence.length}）</h4>
                {existingEvidence.map(e => (
                  <div key={e.evidence_id} className="ew-meta">
                    <span className={`ew-${e.direction === 'contradicts' || e.direction === 'mixed' ? 'bad' : 'ok'}`}>{e.direction}</span>
                    {' '}{e.title ?? '—'}（PMID {e.pmid ?? '—'}）· 调整状态 {e.confidence_adjustment_status ?? '—'}
                    {e.invalidated_at && <span className="ew-bad"> · 已回滚</span>}
                  </div>
                ))}
              </div>
            )}

            <div className="ew-section">
              <h4>论文搜索 Query（可修改，同时检索摘要与 OA 全文，仅影响检索，不影响正式 Claim）</h4>
              <div className="ontology-form-row">
                <input className="filter-input" value={query} onChange={e => { setQuery(e.target.value); setDirty(true) }} placeholder="Europe PMC 检索式（可编辑）" />
                <button type="button" className="btn btn-sm" disabled={!current || busy !== null} onClick={() => { audit('EVIDENCE_QUERY_EDIT', { query }); void startSearch(current!, query, idx) }}>重新搜索</button>
                <button type="button" className="btn btn-xs" onClick={() => { setQuery(result?.target_info.query ?? ''); setChips((result?.target_info.query ?? '').split(' AND ').filter(Boolean)) }}>恢复系统推荐检索式</button>
              </div>
              <div className="ew-chips">
                {chips.map((c, i) => (
                  <span key={i} className="ew-chip">{c}<button type="button" className="btn-text" onClick={() => setChips(chips.filter((_, j) => j !== i))}>×</button></span>
                ))}
              </div>
              <div className="ontology-form-row">
                <label className="ew-meta"><input type="checkbox" checked={oaOnly} onChange={e => setOaOnly(e.target.checked)} /> OA Only</label>
                <select className="filter-select" data-testid="ew-mode-select" value={claimMode} title="存在性佐证：检索只用源/靶脑区，判断论文是否证明对象存在"
                  onChange={e => { claimModeTouchedRef.current = true; setClaimMode(e.target.value as 'function' | 'existence'); setDirty(true); audit('EVIDENCE_MODE_EDIT', { mode: e.target.value }) }}>
                  <option value="function">功能佐证</option>
                  <option value="existence">存在性佐证</option>
                </select>
                <select className="filter-select" value={yearFilter} onChange={e => setYearFilter(e.target.value)}>
                  <option value="">全部年份</option>
                  {years.map(y => <option key={y} value={y}>{y}</option>)}
                </select>
                <button type="button" className="btn btn-xs" onClick={() => setExcludedPmids(new Set())}>恢复排除</button>
              </div>
              <div className="ontology-form-row">
                <button type="button" className="btn btn-xs" disabled={visiblePapers.length === 0} onClick={() => setSelectedPaperIds(new Set(visiblePapers.map(p => p.pmid).filter(Boolean)))}>全选</button>
                <button type="button" data-testid="ew-extract-selected" className="btn btn-sm" disabled={selectedPaperIds.size === 0 || busy !== null} onClick={extractSelected}>提取所选论文（{selectedPaperIds.size}）</button>
                <span className="ew-meta">多选后逐篇提取，每篇结果展示在对应论文下方</span>
              </div>
              {result && result.papers.length === 0 && (
                <div className="ontology-empty">没有找到符合当前检索式的论文，请修改检索词、放宽搜索或恢复系统推荐检索式后重新搜索。</div>
              )}
              {result && result.papers.length > 0 && visiblePapers.length === 0 && (
                <div className="ontology-empty">当前筛选/排除后无论文，请调整筛选条件</div>
              )}
              {visiblePapers.map(p => {
                const paperResult = paperExtractResults[p.pmid]
                return (
                <div key={p.pmid} className={`ew-paper ${selectedPmid === p.pmid ? 'ew-paper-active' : ''}`} data-testid="ew-paper"
                  onClick={() => { setSelectedPmid(p.pmid); setPassages([]); setStep(2); setDirty(true); audit('EVIDENCE_PAPER_SELECT', { pmid: p.pmid, title: p.title }) }}>
                  <strong>{p.title}</strong>
                  <div className="ew-meta">{p.authors}（{p.year}）· {p.journal}</div>
                  <div className="ew-meta">
                    {p.paper_match_score != null && <span className="ew-match">匹配度 {p.paper_match_score}</span>}
                    {p.match_reason && <span> · {p.match_reason}</span>}
                  </div>
                  <div className="ontology-form-row">
                    <label onClick={e => e.stopPropagation()}>
                      <input type="checkbox" disabled={!p.pmid} checked={selectedPaperIds.has(p.pmid)}
                        onChange={e => setSelectedPaperIds(prev => { const n = new Set(prev); if (e.target.checked) n.add(p.pmid); else n.delete(p.pmid); return n })} />
                      加入提取
                    </label>
                    {p.pmid && <a href={`https://pubmed.ncbi.nlm.nih.gov/${p.pmid}/`} target="_blank" rel="noreferrer" onClick={e => e.stopPropagation()}>PubMed {p.pmid}</a>}
                    {p.doi && <a href={`https://doi.org/${p.doi}`} target="_blank" rel="noreferrer" onClick={e => e.stopPropagation()}>DOI</a>}
                    {p.abstract ? <span className="ew-meta">摘要可用</span> : <span className="ew-meta">无摘要</span>}
                    {p.fulltext_available ? <span className="ew-oa">OA 全文可用</span> : <span className="ew-meta">无 OA 全文</span>}
                    <button type="button" className="btn btn-xs" onClick={e => { e.stopPropagation(); setExcludedPmids(prev => new Set(prev).add(p.pmid)) }}>排除此候选</button>
                  </div>
                  {paperResult && (
                    <div className="ew-paper-result" data-testid="ew-paper-result">
                      {paperResult.busy && <span className="ew-meta">正在提取…</span>}
                      {paperResult.error && <span className="ew-bad">提取失败：{paperResult.error}</span>}
                      {!paperResult.busy && !paperResult.error && paperResult.passages && (
                        <>
                          <span className="ew-meta">
                            模型判断：{paperResult.model_direction ?? '—'} · 候选片段 {paperResult.passages.length} ·
                            已核验 {paperResult.passages.filter(x => x.source_verified).length}
                            {paperResult.fulltext_fetched === false && <span className="ew-warn"> · 仅摘要（无 OA 全文）</span>}
                          </span>
                          <div className="ontology-form-row">
                            <button type="button" className="btn btn-xs" disabled={!paperResult.passages.some(x => x.source_verified)}
                              onClick={e => { e.stopPropagation(); loadPaperResult(p, paperResult.passages!) }}>载入片段</button>
                          </div>
                        </>
                      )}
                    </div>
                  )}
                </div>
                )
              })}
            </div>

            {(selectedPaper || (current?.draftPassages?.length ?? 0) > 0 || passages.length > 0) && (
              <div className="ew-section">
                <h4>原文片段（{passages.length}）</h4>
                {selectedPaper && (
                  <div className="ew-current-paper">
                    <strong>当前论文：</strong>{selectedPaper.title}
                    <span className="ew-meta"> · PMID {selectedPaper.pmid}{selectedPaper.doi ? ` · DOI ${selectedPaper.doi}` : ''}</span>
                  </div>
                )}
                <div className="ontology-form-row">
                  <button type="button" className="btn btn-sm" disabled={!selectedPaper || (!selectedPaper.pmid && !selectedPaper.doi) || busy !== null} onClick={extract}>AI 提取原文</button>
                  {selectedPaper && !selectedPaper.pmid && !selectedPaper.doi && (
                    <span className="ew-bad">该论文缺少 PMID/DOI，无法提取</span>
                  )}
                  <button type="button" className="btn btn-sm" disabled={busy !== null || selectedHashes.size === 0} onClick={() => { void (async () => {
                    setBusy('translate')
                    try {
                      for (const p of selectedPassages) {
                        const r = await translateEvidenceText({ text: p.passage })
                        setTranslations(t => ({ ...t, [p.hash]: r.translated }))
                      }
                    } finally { setBusy(null) }
                  })() }}>翻译全部已选</button>
                </div>
                {passages.length === 0 && <div className="ontology-empty">点击「AI 提取原文」从摘要/OA 全文中提取佐证片段</div>}
                {passages.map(p => (
                  <PassageEvidenceCard
                    key={p.hash}
                    passage={p}
                    components={claimComponents}
                    selected={selectedHashes.has(p.hash)}
                    translation={translations[p.hash] ?? ''}
                    onToggleSelect={checked => {
                      setSelectedHashes(prev => { const n = new Set(prev); if (checked) n.add(p.hash); else n.delete(p.hash); return n })
                      setDirty(true)
                      audit('EVIDENCE_PASSAGE_SELECT', { passage: p.passage.slice(0, 120), selected: checked })
                    }}
                    onLevelChange={level => { updatePassage(p.hash, { evidence_level: level }); audit('EVIDENCE_LEVEL_EDIT', { level }) }}
                    onComponentToggle={(comp, checked) => {
                      const next = checked
                        ? [...new Set([...(p.supported_components || []), comp])]
                        : (p.supported_components || []).filter(c => c !== comp)
                      updatePassage(p.hash, { supported_components: next })
                      audit('EVIDENCE_COMPONENT_EDIT', { component: comp, checked })
                    }}
                    onTranslationChange={value => { setTranslations(t => ({ ...t, [p.hash]: value })); setDirty(true) }}
                    onTranslate={() => translatePassage(p.hash, p.passage)}
                    onCopy={() => { void navigator.clipboard?.writeText(p.passage).catch(() => undefined) }}
                    onShowContext={() => setShowContextHash(prev => (prev === p.hash ? null : p.hash))}
                    showContext={showContextHash === p.hash}
                    onReselect={reselect}
                  />
                ))}
              </div>
            )}

            {selectedPassages.length > 0 && (
              <CoveragePanel coverage={tmpCoverage} direction={tmpDirection} />
            )}
          </div>
          <div className="ew-right">
            <ReviewerPanel
              direction={direction}
              modelDirection={modelDirection}
              onDirectionChange={d => { setDirection(d); setDirty(true); audit('EVIDENCE_DIRECTION_EDIT', { direction: d }) }}
              evidenceLevel={evidenceLevel}
              onEvidenceLevelChange={l => { setEvidenceLevel(l); setDirty(true) }}
              confidence={confidence}
              onConfidenceChange={v => { setConfidence(v); setDirty(true) }}
              note={note}
              onNoteChange={v => { setNote(v); setDirty(true) }}
              selectedCount={selectedHashes.size}
              preview={preview}
              previewBusy={busy === 'preview'}
            />
          </div>
        </div>
      )}
      <div className="ew-bottom">
        <button type="button" className="btn btn-sm" disabled={idx === 0} onClick={() => goto(idx - 1)}>上一条</button>
        <button type="button" className="btn btn-sm" disabled={!current} onClick={skip}>跳过</button>
        <button type="button" className="btn btn-sm" disabled={!current} onClick={saveDraft}>保存草稿</button>
        <button type="button" className="btn btn-sm" disabled={idx + 1 >= queue.length} onClick={() => goto(idx + 1)}>下一条</button>
        {saveState === 'saving' && <span className="ew-meta">保存中…</span>}
        {saveState === 'saved' && <span className="ew-ok">已保存</span>}
        {saveState === 'error' && (
          <>
            <span className="ew-bad">保存失败</span>
            <button type="button" className="btn btn-xs" onClick={() => saveDraft()}>重试保存</button>
          </>
        )}
        <span className="ew-meta" title={attachDisabledReason}>{attachDisabled ? `ⓘ ${attachDisabledReason}` : '确认论文证据'}</span>
        <button type="button" data-testid="ew-attach" className="btn btn-primary btn-sm" disabled={attachDisabled} onClick={() => setConfirmOpen(true)}>确认论文证据</button>
      </div>
      <AttachDialog
        open={confirmOpen}
        targetLabel={current?.label ?? ''}
        claimText={claimText}
        paper={{ title: selectedPaper?.title, pmid: selectedPaper?.pmid, doi: selectedPaper?.doi }}
        passages={selectedPassages}
        components={claimComponents}
        direction={direction}
        preview={preview}
        busy={busy === 'attach'}
        onConfirm={attach}
        onClose={() => setConfirmOpen(false)}
      />
      <ConfirmDialog
        open={closeConfirm}
        title="未保存的审核内容"
        message="当前对象存在未保存审核内容，是否保存草稿后关闭？"
        onConfirm={() => {
          saveCurrentDraft(idx)
          persist(queueRef.current, idx)
          setCloseConfirm(false)
          onClose()
        }}
        onCancel={() => setCloseConfirm(false)}
        confirmLabel="保存并关闭"
      />
      <ConfirmDialog
        open={serverDraftConfirm}
        title="最新审核草稿尚未保存到服务器"
        message="草稿保存失败，关闭将丢失最新修改。"
        onConfirm={retrySaveAndClose}
        onCancel={() => {
          setServerDraftConfirm(false)
          saveCurrentDraft(idx)
          persist(queueRef.current, idx)
          onClose()
        }}
        confirmLabel="重试保存并关闭"
      />
    </div>
  )
}
