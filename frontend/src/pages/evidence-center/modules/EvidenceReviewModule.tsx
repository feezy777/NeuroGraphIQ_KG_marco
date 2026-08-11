import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { MousePointerClick } from 'lucide-react'
import {
  attachPaperEvidencePreview,
  buildReview,
  getEvidenceTarget,
  saveTaskItemDraft,
  translateEvidenceText,
  validatePassageSelection,
  type AttachPreviewResponse,
  type EvidenceTargetDto,
} from '../../../api/endpoints'
import { useEvidenceCenter } from '../EvidenceCenterContext'
import { ClaimPanel } from '../components/ClaimPanel'
import { EmptyState } from '../components/EmptyState'
import { CoveragePanel } from '../components/CoveragePanel'
import { PassageEvidenceCard } from '../components/PassageEvidenceCard'
import { loadReviewStatus, saveReviewStatus, type ReviewStatusMeta, type ReviewStatusRecord } from '../components/ReviewStatusStore'
import type { ReviewDecisionState } from '../components/ReviewerDecisionPanel'
import { aggregateTmpDirection, computeTmpCoverage } from '../components/claimCoverage'
import type { Direction, EvidenceLevel, WorkbenchPassage } from '../components/types'

const DRAFT_PREFIX = 'evidence-center.review-draft.'

/** T7 候选模块写入、本模块恢复/回写的审核草稿 */
interface ReviewDraft {
  passages: WorkbenchPassage[]
  modelDirection: Direction | null
  modelAssessment: string | null
  paperTitle: string
  pmid: string
  doi?: string | null
  translations?: Record<string, string>
  reviewerDirection?: Direction
  reviewerEvidenceLevel?: EvidenceLevel
  reviewerConfidence?: string
  note?: string
}

export function EvidenceReviewModule() {
  const { state, queue, openTarget, setReviewDecision, setProgress } = useEvidenceCenter()
  const [dto, setDto] = useState<EvidenceTargetDto | null>(null)
  const [passages, setPassages] = useState<WorkbenchPassage[]>([])
  const [selectedHashes, setSelectedHashes] = useState<Set<string>>(new Set())
  const [translations, setTranslations] = useState<Record<string, string>>({})
  const [direction, setDirection] = useState<Direction>('supports')
  const [modelDirection, setModelDirection] = useState<Direction | null>(null)
  const [modelAssessment, setModelAssessment] = useState<string | null>(null)
  const [paperTitle, setPaperTitle] = useState('')
  const [pmid, setPmid] = useState('')
  const [doi, setDoi] = useState<string | null>(null)
  const [evidenceLevel, setEvidenceLevel] = useState<EvidenceLevel>('indirect')
  const [confidence, setConfidence] = useState('0.8')
  const [note, setNote] = useState('')
  const [preview, setPreview] = useState<AttachPreviewResponse | null>(null)
  const [previewBusy, setPreviewBusy] = useState(false)
  const [showContextHash, setShowContextHash] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [saveState, setSaveState] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle')
  const [reviewStatus, setReviewStatus] = useState<ReviewStatusRecord | null>(null)
  const [reviewBusy, setReviewBusy] = useState(false)
  const abortRef = useRef<AbortController | null>(null)

  const targetType = state.targetType
  const targetId = state.targetId

  // ─── 目标切换:恢复 sessionStorage 审核草稿 + 审核状态(刷新不丢) ───
  useEffect(() => {
    setDto(null)
    setPassages([])
    setSelectedHashes(new Set())
    setTranslations({})
    setDirection('supports')
    setEvidenceLevel('indirect')
    setConfidence('0.8')
    setNote('')
    setModelDirection(null)
    setModelAssessment(null)
    setPaperTitle('')
    setPmid('')
    setDoi(null)
    setPreview(null)
    setPreviewBusy(false)
    setShowContextHash(null)
    setMessage(null)
    setSaveState('idle')
    setReviewStatus(null)
    if (!targetId) return
    setReviewStatus(loadReviewStatus(targetId))
    const raw = sessionStorage.getItem(`${DRAFT_PREFIX}${targetId}`)
    if (!raw) return
    try {
      const d = JSON.parse(raw) as Partial<ReviewDraft>
      if (Array.isArray(d.passages)) {
        setPassages(d.passages)
        setSelectedHashes(new Set(d.passages.filter(p => p.source_verified).map(p => p.hash)))
      }
      if (d.modelDirection) setModelDirection(d.modelDirection as Direction)
      if (d.modelAssessment != null) setModelAssessment(d.modelAssessment)
      if (d.paperTitle != null) setPaperTitle(d.paperTitle)
      if (d.pmid != null) setPmid(d.pmid)
      if (d.doi != null) setDoi(d.doi)
      if (d.translations) setTranslations(d.translations)
      if (d.reviewerDirection) setDirection(d.reviewerDirection as Direction)
      if (d.reviewerEvidenceLevel) setEvidenceLevel(d.reviewerEvidenceLevel as EvidenceLevel)
      if (d.reviewerConfidence != null) setConfidence(d.reviewerConfidence)
      if (d.note != null) setNote(d.note)
    } catch {
      // 草稿损坏时忽略,保持空态
    }
  }, [targetId])

  // Claim DTO(ClaimPanel 数据源)
  useEffect(() => {
    if (!targetType || !targetId) return
    let cancelled = false
    getEvidenceTarget(targetType, targetId)
      .then(d => { if (!cancelled) setDto(d) })
      .catch(() => { if (!cancelled) setDto(null) })
    return () => { cancelled = true }
  }, [targetType, targetId])

  const updatePassage = useCallback((hash: string, patch: Partial<WorkbenchPassage>) => {
    setPassages(ps => ps.map(p => (p.hash === hash ? { ...p, ...patch } : p)))
  }, [])

  const selectedPassages = useMemo(
    () => passages.filter(p => selectedHashes.has(p.hash)),
    [passages, selectedHashes],
  )

  // 必须 memo 稳定引用:dto 未加载时为 [] 的新引用会让下游 useMemo 每渲染重建,导致 reviewDecision 推送 effect 无限循环
  const claimComponents = useMemo(() => dto?.claim_components ?? [], [dto])
  const tmpCoverage = useMemo(() => computeTmpCoverage(claimComponents, selectedPassages), [claimComponents, selectedPassages])
  const tmpDirection = useMemo(() => aggregateTmpDirection(tmpCoverage, selectedPassages), [tmpCoverage, selectedPassages])

  // ─── 置信度预览(350ms debounce,body 同旧逻辑) ───
  const runPreview = useCallback(async () => {
    if (!targetType || !targetId || !pmid) return
    if (selectedPassages.length === 0) {
      setPreview(null)
      return
    }
    abortRef.current?.abort()
    abortRef.current = new AbortController()
    setPreviewBusy(true)
    try {
      const r = await attachPaperEvidencePreview({
        target_type: targetType,
        target_id: targetId,
        pmid,
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
      // 被新一轮预览 abort 的旧请求不算失败
      if ((err as Error)?.name !== 'AbortError') {
        setMessage(`预览失败：${err instanceof Error ? err.message : String(err)}`)
      }
    } finally {
      setPreviewBusy(false)
    }
  }, [targetType, targetId, pmid, direction, confidence, selectedPassages])

  useEffect(() => {
    const t = setTimeout(() => void runPreview(), 350)
    return () => clearTimeout(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [direction, confidence, selectedHashes, passages, pmid, targetType, targetId])

  // ─── 草稿 debounce(500ms)写回 sessionStorage(永不丢) ───
  const buildDraft = useCallback((): ReviewDraft => ({
    passages,
    modelDirection,
    modelAssessment,
    paperTitle,
    pmid,
    doi,
    translations,
    reviewerDirection: direction,
    reviewerEvidenceLevel: evidenceLevel,
    reviewerConfidence: confidence,
    note,
  }), [passages, modelDirection, modelAssessment, paperTitle, pmid, doi, translations, direction, evidenceLevel, confidence, note])

  /** 同步落盘当前草稿(debounce 定时器与退出路径共用,保证草稿不丢失) */
  const persistDraft = useCallback(() => {
    if (!targetId || passages.length === 0) return
    sessionStorage.setItem(`${DRAFT_PREFIX}${targetId}`, JSON.stringify(buildDraft()))
  }, [targetId, passages.length, buildDraft])

  useEffect(() => {
    if (!targetId || passages.length === 0) return
    const t = setTimeout(() => persistDraft(), 500)
    return () => clearTimeout(t)
  }, [targetId, passages.length, persistDraft])

  // 模块卸载/切换时同步落盘最后一次编辑(绕过 debounce 清理窗口)
  const persistDraftRef = useRef(persistDraft)
  useEffect(() => {
    persistDraftRef.current = persistDraft
  })
  useEffect(() => {
    return () => { persistDraftRef.current() }
  }, [])

  // ─── 片段操作 ───
  const translatePassage = useCallback(async (hash: string, text: string) => {
    try {
      const r = await translateEvidenceText({ text })
      setTranslations(t => ({ ...t, [hash]: r.translated }))
    } catch (err) {
      setMessage(`翻译失败：${err instanceof Error ? err.message : String(err)}`)
    }
  }, [])

  const copyPassage = useCallback((text: string) => {
    void navigator.clipboard?.writeText(text).catch(() => undefined)
  }, [])

  const handleReselect = useCallback(async (paperPassageId: string, text: string): Promise<boolean> => {
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

  // ─── 顶部操作 ───
  const handleBack = useCallback(() => {
    persistDraft()
    if (targetType && targetId) openTarget(targetType, targetId, 'candidates')
  }, [targetType, targetId, openTarget, persistDraft])

  const taskItem = queue.find(q => q.target_type === targetType && q.target_id === targetId)

  const handleSaveDraft = useCallback(async () => {
    if (!targetId) return
    const draft = buildDraft()
    sessionStorage.setItem(`${DRAFT_PREFIX}${targetId}`, JSON.stringify(draft))
    if (taskItem?.taskItemId) {
      setSaveState('saving')
      try {
        await saveTaskItemDraft(taskItem.taskItemId, draft as unknown as Record<string, unknown>, 0)
        setSaveState('saved')
      } catch (err) {
        setSaveState('error')
        setMessage(`保存到任务失败：${err instanceof Error ? err.message : String(err)}`)
      }
    } else {
      setMessage('草稿已保存在本地（未关联任务项）')
    }
  }, [targetId, buildDraft, taskItem?.taskItemId])

  // ─── 审核:sessionStorage(兼容) + 后端 Review(权威) ───
  const commitReviewStatus = useCallback(async (status: 'review_approved' | 'rejected', at: string) => {
    if (!targetId || !targetType) return
    persistDraft()
    const meta: ReviewStatusMeta = { direction, evidenceLevel, confidence, note, at }
    // 保留 sessionStorage 兼容写入(现有晋升模块兼容读取 + 跨标签瞬时提示)
    saveReviewStatus(targetId, status, meta, state.targetType ?? undefined)
    setReviewStatus({ targetId, status, meta })
    // 同时写后端 Review(权威持久化)
    const paperId: string | null = passages[0]?.paper_id ?? null
    const claimVersion: string = dto?.claim_version ?? 'v1'
    const claimText: string = dto?.claim_text ?? ''
    const taskItem = queue.find(q => q.target_type === targetType && q.target_id === targetId)
    const taskId: string | null = state.taskId ?? null
    const taskItemId: string | null = taskItem?.taskItemId ?? null
    await buildReview({
      target_type: targetType!,
      target_id: targetId!,
      paper_id: paperId,
      task_id: taskId,
      task_item_id: taskItemId,
      reviewer_id: null,
      claim_version: claimVersion,
      claim_text_snapshot: claimText,
      claim_components_snapshot: (dto?.claim_components ?? []) as Record<string, unknown>[],
      model_direction: modelDirection as string | null,
      model_assessment: modelAssessment as string | null,
      reviewer_direction: direction,
      reviewer_evidence_level: evidenceLevel,
      reviewer_confidence: parseFloat(confidence) || 0,
      reviewer_note: (note || null) as string | null,
      coverage_summary_snapshot: tmpCoverage as unknown as Record<string, unknown>,
      coverage_formula_version: 'v2',
      draft_revision: 0,
      passages: selectedPassages.map(p => ({
        paper_passage_id: p.paper_passage_id,
        passage_text: p.passage,
        source_scope: p.source_scope,
        section_title: p.section_title,
        paragraph_index: p.paragraph_index,
        paragraph_id: p.paragraph_id,
        translation_zh: p.translation_zh,
        direction: p.direction,
        evidence_level: p.evidence_level,
        reason: p.reason,
        confidence: p.confidence,
        semantic_confidence: p.semantic_confidence,
        source_locator: p.source_locator,
        source_verified: p.source_verified,
        source_verification_method: p.source_verification_method,
        supported_components: p.supported_components,
        passage_hash: p.hash,
        rank: 0,
        is_selected: true,
      })),
    })
    // 审核通过/驳回 → 推进 StepPills → 人工审核
    setProgress({ reviewed: true })
  }, [targetId, targetType, persistDraft, direction, evidenceLevel, confidence, note, state.targetType, state.taskId, passages, modelDirection, modelAssessment, dto, tmpCoverage, selectedPassages, queue, setProgress])

  const handleApprove = useCallback(async () => {
    setReviewBusy(true)
    setMessage(null)
    try {
      await commitReviewStatus('review_approved', new Date().toISOString())
      setMessage('已审核通过，进入「证据晋升」模块待晋升')
    } catch (err) {
      setMessage(`审核失败：${err instanceof Error ? err.message : String(err)}`)
    } finally {
      setReviewBusy(false)
    }
  }, [commitReviewStatus])

  const handleReject = useCallback(async () => {
    setReviewBusy(true)
    setMessage(null)
    try {
      await commitReviewStatus('rejected', new Date().toISOString())
      setMessage('已驳回该证据，不会进入晋升')
    } catch (err) {
      setMessage(`驳回失败：${err instanceof Error ? err.message : String(err)}`)
    } finally {
      setReviewBusy(false)
    }
  }, [commitReviewStatus])

  // ─── 右栏接入:把人工审核决策状态推送给 Context,RightPanel 渲染 ReviewerDecisionPanel ───
  const reviewDecision = useMemo<ReviewDecisionState>(() => ({
    direction,
    modelDirection,
    evidenceLevel,
    confidence,
    note,
    selectedCount: selectedHashes.size,
    preview,
    previewBusy,
    coverage: selectedPassages.length > 0 ? tmpCoverage : null,
    currentConfidence: dto?.current_confidence ?? null,
    reviewStatus,
    reviewBusy,
    onDirectionChange: setDirection,
    onEvidenceLevelChange: setEvidenceLevel,
    onConfidenceChange: setConfidence,
    onNoteChange: setNote,
    onApprove: handleApprove,
    onReject: handleReject,
  }), [direction, modelDirection, evidenceLevel, confidence, note, selectedHashes, preview, previewBusy,
    selectedPassages, tmpCoverage, dto, reviewStatus, reviewBusy, handleApprove, handleReject])

  useEffect(() => {
    if (!targetType || !targetId) {
      setReviewDecision(null)
      return
    }
    setReviewDecision(reviewDecision)
  }, [targetType, targetId, reviewDecision, setReviewDecision])

  useEffect(() => () => { setReviewDecision(null) }, [setReviewDecision])

  const reviewToolbarTitle = (
    <div className="evidence-review-toolbar-title">
      <h3>人工审核</h3>
      <p className="evidence-module-hint">
        勾选已核验片段，设置人工方向/证据等级/置信度后完成审核；审核通过 ≠ 晋升入库，将进入「证据晋升」待晋升队列。
      </p>
    </div>
  )

  if (!targetType || !targetId) {
    return (
      <div className="evidence-review">
        <div className="evidence-review-main">
          <div className="evidence-review-toolbar">{reviewToolbarTitle}</div>
          <EmptyState
            icon={<MousePointerClick size={24} />}
            title="请先从「佐证任务」或「证据候选」进入一个目标对象"
            description="打开任务并选择目标对象后即可开始人工审核。"
          />
        </div>
      </div>
    )
  }

  return (
    <div className="evidence-review" data-testid="evidence-review">
      <div className="evidence-review-main">
        <div className="evidence-review-toolbar">
          {reviewToolbarTitle}
          <div className="evidence-review-toolbar-actions">
            <button type="button" className="btn btn-sm" onClick={handleBack}>返回证据候选</button>
            <button type="button" className="btn btn-sm" onClick={() => void handleSaveDraft()}>保存草稿</button>
            {saveState === 'saving' && <span className="ew-meta">保存中…</span>}
            {saveState === 'saved' && <span className="ew-ok">已保存</span>}
            {saveState === 'error' && <span className="ew-bad">保存失败</span>}
          </div>
        </div>

        <ClaimPanel
          claimText={dto?.claim_text ?? ''}
          components={claimComponents}
          confidence={dto?.current_confidence ?? null}
          evidenceCount={dto?.existing_evidence ?? 0}
          targetType={targetType}
          granularity={dto?.granularity ?? ''}
        />

        <div className="evidence-review-paper" data-testid="evidence-review-paper">
          <h4>当前论文</h4>
          <strong>{paperTitle || '—'}</strong>
          <span className="ew-meta">PMID {pmid || '—'} · DOI {doi || '—'}</span>
          {modelAssessment && <p className="ew-meta">模型评估：{modelAssessment}</p>}
        </div>

        {message && <div className="ontology-page-message">{message}</div>}

        <div className="evidence-review-passages">
          <div className="evidence-review-passages-head" data-testid="evidence-review-passages-head">
            <h4>已选佐证原文</h4>
            <span className="evidence-review-passages-count" data-testid="evidence-review-passages-count">{passages.length}</span>
          </div>
          {passages.length === 0 && (
            <EmptyState compact title="暂无审核草稿" description="请先在「证据候选」中勾选片段并「加入人工审核」。" />
          )}
          {passages.map(p => (
            <PassageEvidenceCard
              key={p.hash}
              passage={p}
              components={claimComponents}
              selected={selectedHashes.has(p.hash)}
              translation={translations[p.hash] ?? ''}
              onToggleSelect={checked => {
                setSelectedHashes(prev => {
                  const n = new Set(prev)
                  if (checked) n.add(p.hash)
                  else n.delete(p.hash)
                  return n
                })
              }}
              onLevelChange={level => updatePassage(p.hash, { evidence_level: level })}
              onComponentToggle={(comp, checked) => {
                const next = checked
                  ? [...new Set([...(p.supported_components || []), comp])]
                  : (p.supported_components || []).filter(c => c !== comp)
                updatePassage(p.hash, { supported_components: next })
              }}
              onTranslationChange={value => setTranslations(t => ({ ...t, [p.hash]: value }))}
              onTranslate={() => void translatePassage(p.hash, p.passage)}
              onCopy={() => copyPassage(p.passage)}
              onShowContext={() => setShowContextHash(prev => (prev === p.hash ? null : p.hash))}
              showContext={showContextHash === p.hash}
              onReselect={handleReselect}
            />
          ))}
        </div>

        {selectedPassages.length > 0 && (
          <CoveragePanel coverage={tmpCoverage} direction={tmpDirection} />
        )}
      </div>
    </div>
  )
}
