import { useCallback, useEffect, useMemo, useState } from 'react'
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
import { candidatePassagesToWorkbench } from '../components/candidatePassages'
import { ClaimPanel } from '../components/ClaimPanel'
import { DIRECTION_LABEL, type Direction, type QueueEntry, type QueueStatus, type WorkbenchPassage } from '../components/types'

const ITEM_STATUS_LABEL: Record<string, string> = {
  pending: '待处理',
  searching: '检索中',
  extracting: '提取中',
  awaiting_review: '待人工审核',
  completed: '已审核',
  skipped: '已跳过',
  failed: '失败',
}

const PREPROCESS_HINTS: Record<string, string> = {
  no_evidence_found: '系统未找到有效论文证据',
  no_available_papers: '未找到可用论文',
  parse_error: '预处理解析失败',
}

const DRAFT_PREFIX = 'evidence-center.review-draft.'

/** 候选论文(任务 item 的 candidate_papers 与手动提取的 ExtractedPaperCandidate 的公共子集) */
interface CandidatePaper {
  paper_id: string
  pmid: string
  doi?: string | null
  title: string
  journal: string
  year: string
  is_oa: boolean
  fulltext_fetched?: boolean | null
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
    modelDirection: (it.model_direction as Direction | null) ?? null,
  }
}

function directionTone(direction: string | null): string {
  switch (direction) {
    case 'supports': return 'ok'
    case 'partial': return 'warn'
    case 'contradicts':
    case 'mixed': return 'bad'
    default: return 'muted'
  }
}

interface CandidatePaperCardProps {
  cand: CandidatePaper
  expanded: boolean
  selectedHashes: Set<string>
  reExtracting: boolean
  onToggleExpand: () => void
  onTogglePassage: (hash: string, checked: boolean) => void
  onReview: () => void
  onExclude: () => void
  onReExtract: () => void
}

function CandidatePaperCard({
  cand, expanded, selectedHashes, reExtracting,
  onToggleExpand, onTogglePassage, onReview, onExclude, onReExtract,
}: CandidatePaperCardProps) {
  const passages = useMemo(
    () => candidatePassagesToWorkbench(cand.passages ?? [], cand.paper_id),
    [cand.passages, cand.paper_id],
  )
  const selectedCount = passages.filter(p => selectedHashes.has(p.hash)).length
  const verifiedCount = passages.filter(p => p.source_verified).length
  const coverage = (cand.coverage_summary ?? null) as {
    coverage_ratio?: number
    supported_components?: string[]
    required_components?: string[]
  } | null
  const dirLabel = cand.model_direction
    ? (DIRECTION_LABEL[cand.model_direction as Direction] ?? cand.model_direction)
    : null

  return (
    <div className="evidence-candidate-paper" data-testid="evidence-candidate-paper">
      <div className="evidence-candidate-paper-head">
        <div className="evidence-candidate-paper-title">
          <strong>{cand.title}</strong>
          <span className="ew-meta">{cand.journal} · {cand.year} · PMID {cand.pmid}</span>
        </div>
        <div className="evidence-candidate-paper-badges">
          {dirLabel && (
            <span className={`evidence-candidate-badge evidence-candidate-badge-${directionTone(cand.model_direction)}`}>
              模型判断 {dirLabel}
            </span>
          )}
          {coverage?.coverage_ratio != null && (
            <span className="evidence-candidate-badge" title={coverage.supported_components?.join('、')}>
              覆盖度 {Math.round(coverage.coverage_ratio * 100)}%
            </span>
          )}
          <span className="evidence-candidate-badge">片段 {passages.length}</span>
          <span className="evidence-candidate-badge evidence-candidate-badge-ok">已核验 {verifiedCount}</span>
          {cand.fulltext_fetched === false && (
            <span className="evidence-candidate-badge evidence-candidate-badge-warn" title="未获取到 OA 全文,仅基于摘要提取">仅摘要</span>
          )}
        </div>
      </div>

      {expanded && (
        <div className="evidence-candidate-passages" data-testid="cand-passages">
          {passages.length === 0 && <div className="evidence-candidates-empty">该论文暂无候选片段</div>}
          {passages.map(p => (
            <div key={p.hash} className={`evidence-candidate-passage${p.source_verified ? '' : ' evidence-candidate-passage-invalid'}`} data-testid="cand-passage">
              <div className="evidence-candidate-passage-meta">
                <label>
                  <input
                    type="checkbox"
                    data-testid="cand-passage-checkbox"
                    checked={selectedHashes.has(p.hash)}
                    onChange={e => onTogglePassage(p.hash, e.target.checked)}
                  />
                  选择片段
                </label>
                <span className="ew-passage-direction">{p.direction}</span>
                <span className="ew-meta">{p.source_scope}{p.section_title ? ` · ${p.section_title}` : ''}</span>
                {p.source_verified
                  ? <span className="ew-ok">已核验</span>
                  : <span className="ew-bad">未核验</span>}
              </div>
              <p className="ew-passage-en">{p.passage}</p>
            </div>
          ))}
        </div>
      )}

      <div className="evidence-candidate-paper-actions">
        <button type="button" className="btn btn-xs" onClick={onToggleExpand}>
          {expanded ? '收起候选证据' : '查看候选证据'}
        </button>
        <button
          type="button"
          className="btn btn-xs btn-primary"
          data-testid="review-submit"
          disabled={selectedCount === 0}
          title={selectedCount === 0 ? '请先勾选已核验的候选片段' : '将所选片段作为人工审核草稿提交'}
          onClick={onReview}
        >
          加入人工审核{selectedCount > 0 ? `（${selectedCount}）` : ''}
        </button>
        <button type="button" className="btn btn-xs" onClick={onExclude}>排除</button>
        <button type="button" className="btn btn-xs" disabled={reExtracting} onClick={onReExtract}>
          {reExtracting ? '重新提取中…' : '重新提取'}
        </button>
      </div>
    </div>
  )
}

export function EvidenceCandidatesModule() {
  const { state, queue, setQueue, openTarget } = useEvidenceCenter()
  const [items, setItems] = useState<PaperEvidenceTaskItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [dto, setDto] = useState<EvidenceTargetDto | null>(null)
  const [excludedPaperIds, setExcludedPaperIds] = useState<Set<string>>(new Set())
  const [expandedPaperId, setExpandedPaperId] = useState<string | null>(null)
  const [selectedHashes, setSelectedHashes] = useState<Set<string>>(new Set())
  const [reExtractBusy, setReExtractBusy] = useState<string | null>(null)
  const [manualQuery, setManualQuery] = useState('')
  const [manualResult, setManualResult] = useState<PaperSearchResponse | null>(null)
  const [manualBusy, setManualBusy] = useState(false)
  const [manualSelected, setManualSelected] = useState<Set<string>>(new Set())
  const [manualResults, setManualResults] = useState<CandidatePaper[]>([])

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

  // 自动将第一个 item 选中到 URL(便于直接进入人工审核时带上 target)
  useEffect(() => {
    if (items.length > 0 && current && (!state.targetType || !state.targetId)) {
      openTarget(current.target_type, current.target_id, 'candidates')
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [current?.target_id, items.length])

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

  // 切换目标时重置选择状态
  useEffect(() => {
    setExpandedPaperId(null)
    setSelectedHashes(new Set())
    setExcludedPaperIds(new Set())
    setMessage(null)
  }, [current?.target_id])

  const mode = current?.target_type === 'connection' || current?.target_type === 'projection' ? 'existence' : 'function'

  const candidates: CandidatePaper[] = useMemo(() => {
    const papers = current?.candidate_papers ?? []
    return papers
      .map(p => ({ ...p, passages: p.passages ?? [] }))
      .filter(c => !excludedPaperIds.has(c.paper_id || c.pmid))
  }, [current, excludedPaperIds])

  const handleTogglePassage = useCallback((hash: string, checked: boolean) => {
    setSelectedHashes(prev => {
      const next = new Set(prev)
      if (checked) next.add(hash)
      else next.delete(hash)
      return next
    })
  }, [])

  const handleReview = useCallback((cand: CandidatePaper) => {
    if (!current) return
    const passages = candidatePassagesToWorkbench(cand.passages ?? [], cand.paper_id)
      .filter(p => selectedHashes.has(p.hash))
    if (passages.length === 0) return
    const draft: ReviewDraft = {
      passages,
      modelDirection: cand.model_direction,
      modelAssessment: cand.model_assessment,
      paperTitle: cand.title,
      pmid: cand.pmid,
    }
    sessionStorage.setItem(`${DRAFT_PREFIX}${current.target_id}`, JSON.stringify(draft))
    openTarget(current.target_type, current.target_id, 'review')
  }, [current, selectedHashes, openTarget])

  const handleReExtract = useCallback(async (cand: CandidatePaper) => {
    if (!current) return
    setReExtractBusy(cand.paper_id || cand.pmid)
    setMessage(null)
    try {
      const resp = await extractSelectedPaperEvidence({
        target_type: current.target_type,
        target_id: current.target_id,
        papers: [{ pmid: cand.pmid, doi: cand.doi ?? null, title: cand.title }],
        mode,
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
  }, [current, mode])

  // ─── 手动检索/提取(任务 items 为空时的兜底入口) ───
  const manualTarget = current && items.length === 0
    ? { target_type: current.target_type, target_id: current.target_id }
    : null

  const handleManualSearch = useCallback(async () => {
    if (!manualTarget) return
    setManualBusy(true)
    setMessage(null)
    try {
      const resp = await searchPaperEvidence({
        target_type: manualTarget.target_type,
        target_id: manualTarget.target_id,
        limit: 10,
        mode,
        query_override: manualQuery.trim() || undefined,
      })
      setManualResult(resp)
      setManualSelected(new Set())
    } catch (err) {
      setMessage(`检索失败：${err instanceof Error ? err.message : String(err)}`)
    } finally {
      setManualBusy(false)
    }
  }, [manualTarget, mode, manualQuery])

  const handleManualExtract = useCallback(async () => {
    if (!manualTarget) return
    const papers = (manualResult?.papers ?? []).filter(p => manualSelected.has(p.pmid) && Boolean(p.pmid || p.doi))
    if (papers.length === 0) return
    setManualBusy(true)
    setMessage(null)
    try {
      const resp = await extractSelectedPaperEvidence({
        target_type: manualTarget.target_type,
        target_id: manualTarget.target_id,
        papers: papers.map(p => ({ pmid: p.pmid, doi: p.doi, title: p.title })),
        mode,
      })
      setManualResults(resp.results)
      setMessage(`已提取 ${resp.results.length} 篇论文，请勾选片段后加入人工审核`)
    } catch (err) {
      setMessage(`批量提取失败：${err instanceof Error ? err.message : String(err)}`)
    } finally {
      setManualBusy(false)
    }
  }, [manualTarget, manualSelected, manualResult, mode])

  const claimComponents = dto?.claim_components ?? []

  return (
    <div className="evidence-candidates">
      <div className="evidence-candidates-queue" data-testid="candidates-queue">
        <div className="evidence-candidates-queue-head">
          <h4>候选队列</h4>
          <span className="evidence-candidates-queue-count">{queue.length}</span>
        </div>
        {queue.map(e => (
          <div
            key={e.target_id}
            className={`evidence-candidates-queue-item${current?.target_id === e.target_id ? ' evidence-candidates-queue-item-active' : ''}`}
            data-testid="candidates-queue-item"
            onClick={() => openTarget(e.target_type, e.target_id, 'candidates')}
          >
            <div className="evidence-candidates-queue-label">{e.label}</div>
            <div className="evidence-candidates-queue-meta">{e.target_type}</div>
            <span className="evidence-candidates-queue-status">{ITEM_STATUS_LABEL[e.status] ?? e.status}</span>
            {e.preprocessOutcome && PREPROCESS_HINTS[e.preprocessOutcome] && (
              <div className="ew-meta">{PREPROCESS_HINTS[e.preprocessOutcome]}</div>
            )}
          </div>
        ))}
        {queue.length === 0 && !loading && <div className="evidence-candidates-empty">队列为空</div>}
      </div>

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
            <ClaimPanel
              claimText={dto?.claim_text ?? ''}
              components={claimComponents}
              confidence={current.current_confidence}
              evidenceCount={candidates.length}
              targetType={current.target_type}
              granularity={dto?.granularity ?? ''}
            />

            {message && <div className="ontology-page-message">{message}</div>}

            {items.length > 0 && (
              <div className="evidence-candidates-papers">
                <div className="evidence-candidates-papers-head">
                  <h4>候选论文（{candidates.length}）</h4>
                  <span className="evidence-module-hint">
                    以下为 DeepSeek 从检索到的论文中提取的候选佐证原文。勾选片段后「加入人工审核」进入人工确认；重新提取会再次调用模型提取该论文。
                  </span>
                </div>
                {candidates.length === 0 && (
                  <div className="evidence-candidates-empty">
                    当前对象暂无候选证据，可尝试重新提取或切换其他对象。
                  </div>
                )}
                {candidates.map(cand => (
                  <CandidatePaperCard
                    key={cand.paper_id || cand.pmid}
                    cand={cand}
                    expanded={expandedPaperId === (cand.paper_id || cand.pmid)}
                    selectedHashes={selectedHashes}
                    reExtracting={reExtractBusy === (cand.paper_id || cand.pmid)}
                    onToggleExpand={() => setExpandedPaperId(prev => (prev === (cand.paper_id || cand.pmid) ? null : (cand.paper_id || cand.pmid)))}
                    onTogglePassage={handleTogglePassage}
                    onReview={() => handleReview(cand)}
                    onExclude={() => setExcludedPaperIds(prev => new Set(prev).add(cand.paper_id || cand.pmid))}
                    onReExtract={() => void handleReExtract(cand)}
                  />
                ))}
              </div>
            )}

            {manualTarget && (
              <div className="evidence-candidates-manual" data-testid="candidates-manual">
                <h4>手动检索与提取</h4>
                <p className="evidence-module-hint">
                  当前任务没有候选论文。可手动检索 Europe PMC 并逐篇提取候选证据；结果仅为候选，仍需人工审核后才能入库。
                </p>
                <div className="ontology-form-row">
                  <input
                    className="filter-input"
                    value={manualQuery}
                    onChange={e => setManualQuery(e.target.value)}
                    placeholder="检索式 / 关键词（留空使用系统推荐检索式）"
                  />
                  <button type="button" className="btn btn-sm" disabled={manualBusy} onClick={() => void handleManualSearch()}>
                    {manualBusy ? '检索中…' : '检索'}
                  </button>
                </div>
                {manualResult && manualResult.papers.length === 0 && (
                  <div className="evidence-candidates-empty">没有找到符合检索式的论文，请修改检索词后重试。</div>
                )}
                {manualResult && manualResult.papers.length > 0 && (
                  <div className="evidence-candidates-manual-papers">
                    {manualResult.papers.map(p => (
                      <label key={p.pmid} className="evidence-candidates-manual-paper">
                        <input
                          type="checkbox"
                          checked={manualSelected.has(p.pmid)}
                          onChange={e => {
                            setManualSelected(prev => {
                              const next = new Set(prev)
                              if (e.target.checked) next.add(p.pmid)
                              else next.delete(p.pmid)
                              return next
                            })
                          }}
                        />
                        <span>
                          <strong>{p.title}</strong>
                          <span className="ew-meta"> · {p.journal} · {p.year} · PMID {p.pmid}</span>
                        </span>
                      </label>
                    ))}
                    <button
                      type="button"
                      className="btn btn-sm btn-primary"
                      disabled={manualBusy || manualSelected.size === 0}
                      onClick={() => void handleManualExtract()}
                    >
                      提取所选论文（{manualSelected.size}）
                    </button>
                  </div>
                )}
                {manualResults.map(cand => (
                  <CandidatePaperCard
                    key={cand.paper_id || cand.pmid}
                    cand={cand}
                    expanded={expandedPaperId === (cand.paper_id || cand.pmid)}
                    selectedHashes={selectedHashes}
                    reExtracting={reExtractBusy === (cand.paper_id || cand.pmid)}
                    onToggleExpand={() => setExpandedPaperId(prev => (prev === (cand.paper_id || cand.pmid) ? null : (cand.paper_id || cand.pmid)))}
                    onTogglePassage={handleTogglePassage}
                    onReview={() => handleReview(cand)}
                    onExclude={() => setExcludedPaperIds(prev => new Set(prev).add(cand.paper_id || cand.pmid))}
                    onReExtract={() => void handleReExtract(cand)}
                  />
                ))}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}
