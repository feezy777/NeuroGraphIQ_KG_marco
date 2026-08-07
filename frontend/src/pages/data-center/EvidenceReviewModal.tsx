import { useCallback, useEffect, useMemo, useRef, useState, type PointerEvent as ReactPointerEvent } from 'react'
import {
  attachPaperEvidence,
  attachPaperEvidencePreview,
  extractPaperPassage,
  getEvidenceQueue,
  listPaperEvidence,
  searchPaperEvidence,
  translateEvidenceText,
  type AttachPreviewResponse,
  type EvidencePassageInput,
  type PaperSearchResponse,
} from '../../api/endpoints'

type Direction = 'supports' | 'partial' | 'contradicts' | 'not_found'
type QueueStatus = 'pending' | 'processing' | 'completed' | 'skipped' | 'failed'

interface QueueItem {
  target_type: string
  target_id: string
  label: string
  confidence: number | null
}

interface QueueEntry extends QueueItem {
  status: QueueStatus
  evidenceCount: number
}

const STORAGE_KEY = 'neurographiq.evidenceWorkbench.queue.v1'
const STEPS = ['确认对象', '检索论文', '提取原文', '人工审核', '确认入库']
const STEPS_HINT = [
  '确认当前对象信息与关键词，点击「重新检索」进入下一步',
  '选择一篇真实论文；OA/摘要标签辅助判断，可筛选或排除',
  'AI 提取原文片段；仅通过原文校验的片段可被选择',
  '确认方向、人工推荐置信度与备注，查看置信度预览',
  '核对入库影响后确认；成功后自动进入下一条',
]
const DIRECTION_LABEL: Record<Direction, string> = {
  supports: '支持',
  partial: '部分支持',
  contradicts: '矛盾',
  not_found: '未找到',
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

export function EvidenceReviewModal({ open, onClose, initialItems }: {
  open: boolean
  onClose: () => void
  initialItems?: QueueItem[]
}) {
  const [queue, setQueue] = useState<QueueEntry[]>([])
  const [idx, setIdx] = useState(0)
  const [step, setStep] = useState(0)
  const [query, setQuery] = useState('')
  const [chips, setChips] = useState<string[]>([])
  const [result, setResult] = useState<PaperSearchResponse | null>(null)
  const [selectedPmid, setSelectedPmid] = useState('')
  const [passages, setPassages] = useState<Array<{
    hash: string
    source_scope: 'abstract' | 'fulltext'
    section_title: string | null
    paragraph_index: number | null
    passage: string
    direction: Direction
    reason: string
    confidence: number
    source_locator: string | null
    source_verified: boolean
  }>>([])
  const [selectedHashes, setSelectedHashes] = useState<Set<string>>(new Set())
  const [translations, setTranslations] = useState<Record<string, string>>({})
  const [direction, setDirection] = useState<Direction>('supports')
  const [confidence, setConfidence] = useState('0.8')
  const [note, setNote] = useState('')
  const [preview, setPreview] = useState<AttachPreviewResponse | null>(null)
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [busy, setBusy] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [minimized, setMinimized] = useState(false)
  const [heightPct, setHeightPct] = useState(74)
  const [onlyPending, setOnlyPending] = useState(false)
  const [excludedPmids, setExcludedPmids] = useState<Set<string>>(new Set())
  const [oaOnly, setOaOnly] = useState(false)
  const [yearFilter, setYearFilter] = useState('')
  const [usedPmids, setUsedPmids] = useState<Set<string>>(new Set())
  const [evidenceText, setEvidenceText] = useState('')
  const bodyRef = useRef<HTMLDivElement | null>(null)

  const current = queue[idx]

  const persist = useCallback((q: QueueEntry[], i: number) => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify({ queue: q, idx: i, savedAt: new Date().toISOString() }))
    } catch {
      // 本地存储不可用时静默降级
    }
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
        evidenceText: r.items[0]?.evidence_text ?? '',
      }
    } catch {
      return { count: 0, pmids: new Set<string>(), evidenceText: '' }
    }
  }, [])

  const searchForCurrent = useCallback(async (item: QueueEntry, q: string, itemIdx: number) => {
    if (!item) return false
    setBusy('search')
    setMessage(null)
    try {
      const resp = await searchPaperEvidence({
        target_type: item.target_type,
        target_id: item.target_id,
        limit: 10,
        query_override: q.trim() || undefined,
      })
      setResult(resp)
      setQuery(q || resp.target_info.query)
      setChips((resp.target_info.query || '').split(' AND ').filter(Boolean))
      setSelectedPmid('')
      setPassages([])
      setStep(1)
      return true
    } catch (err) {
      setMessage(`检索失败：${err instanceof Error ? err.message : String(err)}`)
      mark(itemIdx, 'failed')
      return false
    } finally {
      setBusy(null)
    }
  }, [mark])

  const startCurrent = useCallback(async (i: number, item: QueueEntry | undefined, q: string) => {
    if (!item) return false
    if (item.status === 'pending' || item.status === 'failed') {
      mark(i, 'processing')
    }
    return searchForCurrent(item, q, i)
  }, [mark, searchForCurrent])

  const initQueue = useCallback(async (items: QueueItem[]) => {
    const metas = await Promise.all(items.map(loadEvidenceMeta))
    const enriched = items.map((it, i) => ({ ...it, status: 'pending' as const, evidenceCount: metas[i].count }))
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
    setUsedPmids(metas[0]?.pmids ?? new Set<string>())
    setEvidenceText(metas[0]?.evidenceText ?? '')
    persist(enriched, 0)
    if (enriched[0]) void startCurrent(0, enriched[0], '')
  }, [loadEvidenceMeta, persist, startCurrent])

  useEffect(() => {
    if (!open) return
    if (initialItems && initialItems.length > 0) {
      void initQueue(initialItems)
      return
    }
    const saved = loadSaved()
    if (saved) {
      setQueue(saved.queue)
      setIdx(saved.idx)
      setStep(0)
      const restored = saved.queue[saved.idx]
      if (restored) {
        void startCurrent(saved.idx, restored, '').then(ok => {
          if (ok) setMessage('已恢复上次处理进度')
        })
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, startCurrent])

  const loadScopeQueue = useCallback(async (targetType: string, scope: string) => {
    setBusy('loading')
    try {
      const r = await getEvidenceQueue({ target_type: targetType, scope, limit: 50 })
      await initQueue(r.items)
      setMessage(`已加载 ${r.items.length} 条待处理`)
    } catch (err) {
      setMessage(`加载失败：${err instanceof Error ? err.message : String(err)}`)
    } finally {
      setBusy(null)
    }
  }, [initQueue])

  const goto = useCallback(async (i: number) => {
    if (i < 0 || i >= queue.length) return
    const target = queue[i]
    setIdx(i)
    setStep(0)
    setResult(null)
    setPassages([])
    setSelectedHashes(new Set())
    setTranslations({})
    setPreview(null)
    setConfirmOpen(false)
    setMessage(null)
    const meta = await loadEvidenceMeta(target)
    setUsedPmids(meta.pmids)
    setEvidenceText(meta.evidenceText)
    setQueue(q => q.map((e, j) => j === i ? { ...e, evidenceCount: meta.count } : e))
    if (target.status === 'pending' || target.status === 'failed') {
      void startCurrent(i, target, '')
    }
  }, [queue, loadEvidenceMeta, startCurrent])

  const selectedPaper = result?.papers.find(p => p.pmid === selectedPmid)

  const extract = useCallback(async () => {
    if (!current || !selectedPaper) return
    setBusy('extract')
    setMessage(null)
    try {
      const r = await extractPaperPassage({
        target_type: current.target_type,
        target_id: current.target_id,
        pmid: selectedPaper.pmid,
        title: selectedPaper.title,
        abstract: selectedPaper.abstract,
      })
      const mapped = r.passages.map((p, i) => ({
        ...p,
        source_scope: p.source_scope,
        direction: p.direction,
        hash: `${selectedPaper.pmid}-${i}-${p.passage}`,
      }))
      setPassages(mapped)
      setSelectedHashes(new Set(mapped.filter(p => p.source_verified).map(p => p.hash)))
      setDirection(r.overall_direction)
      setStep(2)
      setMessage(`${mapped.filter(p => p.source_verified).length}/${mapped.length} 个片段通过原文校验`)
    } catch (err) {
      setMessage(`提取失败：${err instanceof Error ? err.message : String(err)}`)
      mark(idx, 'failed')
    } finally {
      setBusy(null)
    }
  }, [current, selectedPaper, idx, mark])

  const translatePassage = useCallback(async (hash: string, text: string) => {
    setBusy('translate')
    try {
      const r = await translateEvidenceText({ text })
      setTranslations(t => ({ ...t, [hash]: r.translated }))
    } catch (err) {
      setMessage(`翻译失败：${err instanceof Error ? err.message : String(err)}`)
    } finally {
      setBusy(null)
    }
  }, [])

  const translateAll = useCallback(async () => {
    setBusy('translate')
    try {
      const texts = passages.filter(p => selectedHashes.has(p.hash) && p.source_verified)
      for (const p of texts) {
        const r = await translateEvidenceText({ text: p.passage })
        setTranslations(t => ({ ...t, [p.hash]: r.translated }))
      }
    } catch (err) {
      setMessage(`翻译失败：${err instanceof Error ? err.message : String(err)}`)
    } finally {
      setBusy(null)
    }
  }, [passages, selectedHashes])

  const selectedPassages = useMemo(
    () => passages.filter(p => selectedHashes.has(p.hash) && p.source_verified),
    [passages, selectedHashes],
  )

  const runPreview = useCallback(async () => {
    if (!current || !selectedPmid) return
    if (selectedPassages.length === 0) {
      setPreview(null)
      return
    }
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
        })),
      })
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
      }))
      const resp = await attachPaperEvidence({
        target_type: current.target_type,
        target_id: current.target_id,
        pmid: selectedPmid,
        direction,
        reviewer_confidence: parseFloat(confidence) || 0,
        passages: body,
      })
      const meta = await loadEvidenceMeta(current)
      setQueue(q => q.map((e, j) => j === idx ? { ...e, status: 'completed' as const, evidenceCount: meta.count } : e))
      setEvidenceText(meta.evidenceText)
      setConfirmOpen(false)
      const next = queue.findIndex((e, j) => j > idx && e.status === 'pending')
      if (next >= 0) await goto(next)
      setMessage(`入库成功（${resp.passage_count} 段，置信度 ${resp.confidence ?? '不变'}），自动进入下一条`)
    } catch (err) {
      setMessage(`入库失败：${err instanceof Error ? err.message : String(err)}（草稿已保留）`)
    } finally {
      setBusy(null)
    }
  }, [current, selectedPmid, selectedPassages, direction, confidence, queue, idx, loadEvidenceMeta, goto])

  const saveDraft = useCallback(() => {
    persist(queue, idx)
    setMessage('草稿已保存到本地，关闭后可恢复')
  }, [persist, queue, idx])

  const handleClose = useCallback(() => {
    persist(queue, idx)
    onClose()
  }, [persist, queue, idx, onClose])

  const skip = useCallback(() => {
    if (!current) return
    mark(idx, 'skipped')
    const n = queue.findIndex((e, j) => j > idx && e.status === 'pending')
    if (n >= 0) void goto(n)
  }, [current, idx, mark, queue, goto])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement | null
      if (el && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.tagName === 'SELECT' || el.isContentEditable)) return
      if (!open || minimized) return
      if (e.altKey && e.key === 'ArrowRight') {
        e.preventDefault()
        const n = queue.findIndex((x, j) => j > idx && x.status === 'pending')
        if (n >= 0) void goto(n)
      } else if (e.altKey && e.key === 'ArrowLeft') {
        e.preventDefault()
        if (idx > 0) void goto(idx - 1)
      } else if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
        if (direction !== 'not_found' && selectedHashes.size > 0 && busy === null) setConfirmOpen(true)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, minimized, queue, idx, goto, direction, selectedHashes.size, busy])

  const startResize = useCallback((e: ReactPointerEvent<HTMLDivElement>) => {
    e.preventDefault()
    const onMove = (ev: PointerEvent) => {
      const next = Math.min(92, Math.max(45, Math.round(((window.innerHeight - ev.clientY) / window.innerHeight) * 100)))
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
  const cap = direction === 'supports' ? 0.85 : direction === 'partial' ? 0.75 : null

  return (
    <div className="evidence-workbench" style={{ height: `${heightPct}vh` }} data-testid="ew-workbench">
      <div className="ew-resize" onPointerDown={startResize} title="拖动调整高度" />
      <div className="ew-header">
        <div>
          <strong>{current?.label ?? '论文佐证工作台'}</strong>
          <span className="ew-meta">{current?.target_type} · 置信度 {current?.confidence ?? '—'} · 已有证据 {current?.evidenceCount ?? 0}</span>
        </div>
        <span className="ew-progress">{Math.min(idx + 1, queue.length)}/{queue.length} · {current?.status ?? '—'}</span>
        <span className="ew-step-label" data-testid="ew-step-label">步骤 {step + 1}/5：{STEPS[step]}</span>
        <div className="ew-actions">
          <button type="button" className="btn btn-xs" onClick={() => setMinimized(m => !m)}>{minimized ? '展开' : '最小化'}</button>
          <button type="button" className="btn btn-xs" onClick={handleClose}>关闭</button>
        </div>
      </div>
      {!minimized && (
        <div className="ew-body" ref={bodyRef}>
          <div className="ew-left">
            <div className="ew-left-tools">
              <label><input type="checkbox" checked={onlyPending} onChange={e => setOnlyPending(e.target.checked)} /> 只看未处理</label>
              <button type="button" className="btn btn-xs" onClick={() => loadScopeQueue('connection', 'low_confidence')}>加载低置信队列</button>
            </div>
            {visibleQueue.map(e => {
              const realIdx = queue.indexOf(e)
              return (
                <div key={e.target_id} className={`ew-queue-item ${realIdx === idx ? 'ew-queue-active' : ''} ew-status-${e.status}`} data-testid="ew-queue-item" onClick={() => goto(realIdx)}>
                  <div className="ew-queue-name">{e.label}</div>
                  <div className="ew-queue-meta">{e.target_type} · {e.confidence ?? '—'} · 证据 {e.evidenceCount}</div>
                  <div className="ew-queue-status">{e.status}</div>
                  {e.status === 'failed' && <button type="button" className="btn btn-xs" onClick={ev => { ev.stopPropagation(); void goto(realIdx) }}>重试</button>}
                  {e.status === 'completed' && <button type="button" className="btn btn-xs" onClick={ev => { ev.stopPropagation(); void goto(realIdx) }}>重新打开</button>}
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
            {busy && <div className="ew-busy">处理中：{busy}</div>}
            {allDone && <div className="ew-done-banner">当前队列已处理完成</div>}

            <div className="ew-section ew-object-info">
              <h4>确认对象</h4>
              <div className="ew-meta">
                {current?.target_type} · 功能术语 {result?.target_info.function_term ?? '—'} · 颗粒度 {String(result?.target_info.info.granularity_level ?? '—')} · 来源图谱 {String(result?.target_info.info.source_atlas ?? '—')} · 置信度 {current?.confidence ?? '—'} · 已有论文证据 {current?.evidenceCount ?? 0}
              </div>
              {evidenceText && (
                <details>
                  <summary>当前 evidence_text</summary>
                  <p className="ew-meta">{evidenceText}</p>
                </details>
              )}
            </div>

            <div className="ew-section">
              <h4>检索关键词</h4>
              <div className="ontology-form-row">
                <input className="filter-input" value={query} onChange={e => setQuery(e.target.value)} placeholder="Europe PMC 检索式（可编辑）" />
                <button type="button" className="btn btn-sm" disabled={!current || busy !== null} onClick={() => searchForCurrent(current!, query, idx)}>重新检索</button>
                <button type="button" className="btn btn-xs" onClick={() => setChips([])}>清空</button>
              </div>
              <div className="ew-chips">
                {chips.map((c, i) => (
                  <span key={i} className="ew-chip">{c}<button type="button" className="btn-text" onClick={() => setChips(chips.filter((_, j) => j !== i))}>×</button></span>
                ))}
              </div>
            </div>

            <div className="ew-section">
              <h4>候选论文（{visiblePapers.length}/{result?.papers.length ?? 0}）</h4>
              <div className="ontology-form-row">
                <label className="ew-meta"><input type="checkbox" checked={oaOnly} onChange={e => setOaOnly(e.target.checked)} /> OA Only</label>
                <select className="filter-select" value={yearFilter} onChange={e => setYearFilter(e.target.value)}>
                  <option value="">全部年份</option>
                  {years.map(y => <option key={y} value={y}>{y}</option>)}
                </select>
                <button type="button" className="btn btn-xs" onClick={() => setExcludedPmids(new Set())}>恢复排除</button>
              </div>
              {result && result.papers.length === 0 && (
                <div className="ontology-empty">没有可用论文，请调整关键词后重新检索</div>
              )}
              {result && result.papers.length > 0 && visiblePapers.length === 0 && (
                <div className="ontology-empty">当前筛选/排除后无论文，请调整筛选条件</div>
              )}
              {visiblePapers.map(p => (
                <div key={p.pmid} className={`ew-paper ${selectedPmid === p.pmid ? 'ew-paper-active' : ''}`} data-testid="ew-paper" onClick={() => { setSelectedPmid(p.pmid); setPassages([]); setStep(2) }}>
                  <strong>{p.title}</strong>
                  <div>{p.authors}（{p.year}）· {p.journal}</div>
                  <div className="ontology-form-row">
                    {p.pmid && <a href={`https://pubmed.ncbi.nlm.nih.gov/${p.pmid}/`} target="_blank" rel="noreferrer" onClick={e => e.stopPropagation()}>PubMed {p.pmid}</a>}
                    {p.doi && <a href={`https://doi.org/${p.doi}`} target="_blank" rel="noreferrer" onClick={e => e.stopPropagation()}>DOI</a>}
                    {p.is_open_access && <span className="ew-oa">OA</span>}
                    {p.abstract ? <span className="ew-meta">摘要可用</span> : <span className="ew-meta">无摘要</span>}
                    {usedPmids.has(p.pmid) && <span className="ew-used">已用于当前对象</span>}
                    <button type="button" className="btn btn-xs" onClick={e => { e.stopPropagation(); setExcludedPmids(prev => new Set(prev).add(p.pmid)) }}>排除候选</button>
                  </div>
                </div>
              ))}
            </div>

            {selectedPaper && (
              <div className="ew-section">
                <h4>原文片段（{passages.length}）</h4>
                <div className="ontology-form-row">
                  <button type="button" className="btn btn-sm" disabled={busy !== null} onClick={extract}>AI 提取原文</button>
                  <button type="button" className="btn btn-sm" disabled={busy !== null || selectedHashes.size === 0} onClick={translateAll}>翻译全部已选</button>
                </div>
                {passages.length === 0 && <div className="ontology-empty">点击「AI 提取原文」从摘要/OA 全文中提取佐证片段</div>}
                {passages.map(p => {
                  const selected = selectedHashes.has(p.hash)
                  return (
                    <div key={p.hash} className={`ew-passage ${!p.source_verified ? 'ew-passage-invalid' : ''}`} data-testid="ew-passage">
                      <label>
                        <input type="checkbox" checked={selected} disabled={!p.source_verified}
                          onChange={e => setSelectedHashes(prev => { const n = new Set(prev); if (e.target.checked) n.add(p.hash); else n.delete(p.hash); return n })} />
                        选择片段
                      </label>
                      <span className="ew-meta">{p.source_scope}{p.section_title ? ` · ${p.section_title}` : ''}{p.paragraph_index != null ? ` · ¶${p.paragraph_index}` : ''} · {DIRECTION_LABEL[p.direction]} · {p.confidence}</span>
                      {p.source_verified ? <span className="ew-ok">已验证</span> : <span className="ew-bad">未通过原文校验，禁止选择</span>}
                      <p className="ew-passage-en">{p.passage}</p>
                      {p.reason && <p className="ew-meta">模型理由：{p.reason}</p>}
                      {p.source_locator && <p className="ew-meta">定位：{p.source_locator}</p>}
                      {p.source_verified && (
                        <div className="ontology-form-row">
                          <textarea className="filter-input ew-trans" value={translations[p.hash] ?? ''} onChange={e => setTranslations(t => ({ ...t, [p.hash]: e.target.value }))} placeholder="中文翻译（可编辑）" />
                          <button type="button" className="btn btn-xs" onClick={() => translatePassage(p.hash, p.passage)}>翻译</button>
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>
            )}
          </div>
          <div className="ew-right">
            <h4>人工审核</h4>
            <div className="ew-field">
              <label>论文整体方向</label>
              {(['supports', 'partial', 'contradicts', 'not_found'] as const).map(d => (
                <label key={d} className="ew-radio"><input type="radio" name="dir" checked={direction === d} onChange={() => setDirection(d)} /> {DIRECTION_LABEL[d]}</label>
              ))}
            </div>
            <div className="ew-field">
              <label>人工推荐置信度</label>
              <input className="filter-input" value={confidence} onChange={e => setConfidence(e.target.value)} />
            </div>
            <div className="ew-field">
              <label>人工备注</label>
              <textarea className="filter-input" value={note} onChange={e => setNote(e.target.value)} placeholder="可选" />
            </div>
            <div className="ew-field">
              <label>已选片段</label>
              <span className="ew-meta">{selectedHashes.size} 段（仅统计通过校验的片段）</span>
            </div>
            {preview && (
              <div className="ew-preview">
                <h4>置信度预览</h4>
                <div className="ew-preview-flow">{preview.current_confidence ?? '—'} → {preview.final_confidence ?? '—'}（上限 {preview.cap ?? '—'}）</div>
                <p className="ew-meta">
                  {direction === 'supports' && '公式：min(0.85, max(当前, 人工推荐))'}
                  {direction === 'partial' && '公式：min(0.75, max(当前, 人工推荐))'}
                  {direction === 'contradicts' && '矛盾：不自动修改置信度，生成待确认调整'}
                  {direction === 'not_found' && '未找到：禁止作为论文证据入库'}
                </p>
                <div className="ew-meta">已选片段 {preview.selected_passage_count} · 重复 {preview.duplicate_passage_count}</div>
                {preview.block_reasons.map((r, i) => <div key={i} className="ew-bad">{r}</div>)}
                <details><summary>证据文本预览</summary><p className="ew-meta">{preview.evidence_text_preview}</p></details>
              </div>
            )}
          </div>
        </div>
      )}
      <div className="ew-bottom">
        <button type="button" className="btn btn-sm" disabled={idx === 0} onClick={() => goto(idx - 1)}>上一条</button>
        <button type="button" className="btn btn-sm" disabled={!current} onClick={skip}>跳过</button>
        <button type="button" className="btn btn-sm" disabled={!current} onClick={saveDraft}>保存草稿</button>
        <button type="button" className="btn btn-sm" disabled={idx + 1 >= queue.length} onClick={() => goto(idx + 1)}>下一条</button>
        <span className="ew-meta">快捷键：Alt+←/→ 切换 · Ctrl+Enter 入库</span>
        <button type="button" data-testid="ew-attach" className="btn btn-primary btn-sm" disabled={!current || direction === 'not_found' || selectedHashes.size === 0 || busy !== null} onClick={() => setConfirmOpen(true)}>确认入库</button>
      </div>
      {confirmOpen && (
        <div className="ontology-modal-overlay" onClick={() => setConfirmOpen(false)}>
          <div className="ontology-modal" onClick={e => e.stopPropagation()}>
            <div className="ontology-modal-header"><span className="ontology-card-title">确认入库</span><button type="button" className="btn btn-xs" onClick={() => setConfirmOpen(false)}>关闭</button></div>
            <div className="ontology-modal-body">
              <div className="ontology-detail-row"><span>将更新的对象</span><strong>{current?.label}（{current?.target_type}）</strong></div>
              <div className="ontology-detail-row"><span>论文</span><strong>{selectedPaper?.title}</strong></div>
              <div className="ontology-detail-row"><span>PMID/DOI</span><span>{selectedPaper?.pmid} / {selectedPaper?.doi ?? '—'}</span></div>
              <div className="ontology-detail-row"><span>已选片段</span><span>{selectedHashes.size} 段</span></div>
              <div className="ontology-detail-row"><span>方向</span><span>{DIRECTION_LABEL[direction]}</span></div>
              <div className="ontology-detail-row"><span>置信度</span><span>{preview?.current_confidence ?? '—'} → {preview?.final_confidence ?? '—'}（上限 {preview?.cap ?? '—'}）</span></div>
              {preview && preview.duplicate_passage_count > 0 && <div className="ew-bad">检测到 {preview.duplicate_passage_count} 段重复片段</div>}
              {preview && !preview.allow && preview.block_reasons.map((r, i) => <div key={i} className="ew-bad">{r}</div>)}
              <details open>
                <summary>即将写入的原文片段</summary>
                {selectedPassages.map((p, i) => (
                  <p key={p.hash} className="ew-meta">{i + 1}. {p.passage.slice(0, 220)}{p.passage.length > 220 ? '…' : ''}</p>
                ))}
              </details>
              <div className="ontology-modal-actions">
                <button type="button" data-testid="ew-confirm-attach" className="btn btn-sm" disabled={!preview?.allow || busy !== null} onClick={attach}>确认</button>
                <button type="button" className="btn btn-sm" onClick={() => setConfirmOpen(false)}>取消</button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
