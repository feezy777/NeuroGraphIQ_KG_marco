import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { MousePointerClick } from 'lucide-react'
import {
  attachPaperEvidencePreview,
  completePaperEvidenceTaskItem,
  getEvidenceTarget,
  listEvidenceReviews,
  listPaperEvidence,
  promoteReview,
  returnReview,
  rollbackPaperEvidence,
  type AttachPreviewResponse,
  type EvidenceReviewItem,
  type EvidenceTargetDto,
  type PaperEvidenceItem,
} from '../../../api/endpoints'
import { useEvidenceCenter } from '../EvidenceCenterContext'
import { EmptyState } from '../components/EmptyState'
import { CoveragePanel } from '../components/CoveragePanel'
import { EvidenceDetailDrawer } from '../components/EvidenceDetailDrawer'
import { PromotionDialog } from '../components/PromotionDialog'
import type { PromotionImpactState } from '../components/PromotionImpact'
import { clearReviewStatus, listReviewApproved } from '../components/ReviewStatusStore'
import { aggregateTmpDirection, computeTmpCoverage } from '../components/claimCoverage'
import type { Direction, EvidenceLevel, WorkbenchPassage } from '../components/types'
import { DIRECTION_LABEL, LEVEL_LABEL } from '../components/types'
import { MacroPromotionGate } from '../../validation-center/macro-governance/MacroGovernanceIntegration'
import { useMacroViewForEvidence } from '../../validation-center/macro-governance/useMacroCandidates'

const DRAFT_PREFIX = 'evidence-center.review-draft.'

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

interface PendingItem {
  reviewId: string
  targetType: string
  targetId: string
  direction: Direction
  evidenceLevel: EvidenceLevel
  confidence: number
  note: string
  approvedAt: string
}

function mapReviewToPending(r: EvidenceReviewItem): PendingItem {
  return {
    reviewId: r.id,
    targetType: r.target_type,
    targetId: r.target_id,
    direction: (r.reviewer_direction as Direction) ?? 'supports',
    evidenceLevel: (r.reviewer_evidence_level as EvidenceLevel) ?? 'indirect',
    confidence: r.reviewer_confidence ?? 0,
    note: r.reviewer_note ?? '',
    approvedAt: r.approved_at ?? r.reviewed_at ?? '',
  }
}

function fmtDate(v: string | null | undefined): string {
  if (!v) return '—'
  try { return new Date(v).toLocaleString('zh-CN', { hour12: false }) }
  catch { return v }
}

function fmtConf(v: number | null | undefined): string {
  return v == null ? '—' : v.toFixed(2)
}

export function EvidencePromotionModule() {
  const { state, queue, setQueue, openTarget, setPromotionImpact, setProgress } = useEvidenceCenter()
  const [dto, setDto] = useState<EvidenceTargetDto | null>(null)
  const [draft, setDraft] = useState<ReviewDraft | null>(null)
  const [pendingItems, setPendingItems] = useState<PendingItem[]>([])
  const [selectedPendingId, setSelectedPendingId] = useState<string | null>(null)
  const [items, setItems] = useState<PaperEvidenceItem[]>([])
  const [preview, setPreview] = useState<AttachPreviewResponse | null>(null)
  const [previewBusy, setPreviewBusy] = useState(false)
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [promoteBusy, setPromoteBusy] = useState(false)
  const [detailEvidence, setDetailEvidence] = useState<PaperEvidenceItem | null>(null)
  const [rollbackBusy, setRollbackBusy] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const [autoAdvance, setAutoAdvance] = useState(true)
  const [promotedResult, setPromotedResult] = useState<{ before: number | null; after: number | null } | null>(null)
  const abortRef = useRef<AbortController | null>(null)

  const targetType = state.targetType
  const targetId = state.targetId

  // ─── 待晋升列表 ───
  const refreshPending = useCallback(async () => {
    try {
      const r = await listEvidenceReviews({ review_status: 'approved', promotion_status: 'awaiting_promotion', page_size: 100 })
      setPendingItems(r.items.map(mapReviewToPending))
    } catch {
      setPendingItems(listReviewApproved()
        .filter(rec => rec.status === 'review_approved')
        .map(rec => ({
          reviewId: rec.targetId, targetType: rec.targetType ?? '', targetId: rec.targetId,
          direction: rec.meta.direction, evidenceLevel: rec.meta.evidenceLevel,
          confidence: parseFloat(rec.meta.confidence) || 0, note: rec.meta.note, approvedAt: rec.meta.at,
        })),
      )
    }
  }, [])

  useEffect(() => { void refreshPending() }, [refreshPending])

  // ─── 选中项 ───
  useEffect(() => {
    if (pendingItems.length === 0) { setSelectedPendingId(null); return }
    setSelectedPendingId(prev => {
      if (prev && pendingItems.some(r => r.reviewId === prev)) return prev
      const m = pendingItems.find(r => r.targetId === targetId)
      return m ? m.reviewId : pendingItems[0].reviewId
    })
  }, [pendingItems, targetId])

  const selectedPending = pendingItems.find(r => r.reviewId === selectedPendingId) ?? null
  const selectedTargetType = useMemo(() => {
    if (!selectedPending) return null
    if (selectedPending.targetType) return selectedPending.targetType
    const entry = queue.find(q => q.target_id === selectedPending.targetId)
    return entry ? entry.target_type : (selectedPending.targetId === targetId ? targetType : null)
  }, [selectedPending, queue, targetType, targetId])
  const selectedQueueEntry = queue.find(q => selectedPending && q.target_id === selectedPending.targetId)

  // ─── 草稿恢复 ───
  useEffect(() => {
    setDraft(null); setPreview(null); setDetailEvidence(null); setPromotedResult(null)
    if (!selectedPending) return
    const raw = sessionStorage.getItem(`${DRAFT_PREFIX}${selectedPending.targetId}`)
    if (!raw) return
    try {
      const d = JSON.parse(raw) as Partial<ReviewDraft>
      if (d.reviewerDirection && Array.isArray(d.passages) && d.passages.some(p => p.source_verified))
        setDraft(d as ReviewDraft)
    } catch { /* ignore */ }
  }, [selectedPending])

  // ─── Claim ───
  useEffect(() => {
    if (!selectedTargetType || !selectedPending?.targetId) { setDto(null); return }
    let cancelled = false
    setDto(null)
    getEvidenceTarget(selectedTargetType, selectedPending.targetId)
      .then(d => { if (!cancelled) setDto(d) })
      .catch(() => { if (!cancelled) setDto(null) })
    return () => { cancelled = true }
  }, [selectedTargetType, selectedPending?.targetId])

  // ─── 已晋升列表 ───
  const loadList = useCallback(async () => {
    if (!targetType || !targetId) { setItems([]); return }
    try { const r = await listPaperEvidence({ target_type: targetType, target_id: targetId, limit: 50 }); setItems(r.items) }
    catch { setItems([]) }
  }, [targetType, targetId])

  useEffect(() => { void loadList() }, [loadList])

  const selectedPassages = useMemo(() => (draft?.passages ?? []).filter(p => p.source_verified), [draft])
  const claimComponents = useMemo(() => dto?.claim_components ?? [], [dto])

  // Macro 治理晋升门禁:Rule PASS + Human Approved + Evidence 存在(macro 匹配时才生效)
  const macroView = useMacroViewForEvidence(
    selectedPending?.targetId ?? null,
    dto?.source_region,
    dto?.target_region,
    dto?.source_region_canonical_id,
    dto?.target_region_canonical_id,
  )
  const macroGateOk = useMemo(() => {
    if (!macroView) return true
    return Boolean(
      macroView.ruleResult?.passed
      && (macroView.status === 'promotion_ready' || macroView.status === 'promoted')
      && selectedPassages.length > 0,
    )
  }, [macroView, selectedPassages.length])
  const coverage = useMemo(() => computeTmpCoverage(claimComponents, selectedPassages), [claimComponents, selectedPassages])
  const coverageDirection = useMemo(() => aggregateTmpDirection(coverage, selectedPassages), [coverage, selectedPassages])
  const currentConfidence = dto?.current_confidence ?? selectedQueueEntry?.confidence ?? null

  // ─── 置信度预览 ───
  const runPreview = useCallback(async () => {
    if (!selectedTargetType || !selectedPending?.targetId || !draft?.pmid || selectedPassages.length === 0) {
      setPreview(null); return
    }
    setPreviewBusy(true)
    abortRef.current?.abort()
    abortRef.current = new AbortController()
    try {
      const r = await attachPaperEvidencePreview({
        target_type: selectedTargetType, target_id: selectedPending.targetId, pmid: draft.pmid,
        direction: draft.reviewerDirection ?? 'supports',
        reviewer_confidence: parseFloat(draft.reviewerConfidence ?? '0.8') || 0,
        passages: selectedPassages.map(p => ({
          source_scope: p.source_scope, paragraph_index: p.paragraph_index,
          passage: p.passage, direction: p.direction, reason: p.reason,
          confidence: p.confidence, source_locator: p.source_locator,
          source_verified: true, supported_components: p.supported_components,
        })),
      }, abortRef.current.signal)
      setPreview(r)
    } catch (err) {
      if ((err as Error)?.name !== 'AbortError')
        setMessage(`置信度预览失败：${err instanceof Error ? err.message : String(err)}`)
      setPreview(null)
    } finally { setPreviewBusy(false) }
  }, [selectedTargetType, selectedPending?.targetId, draft, selectedPassages])

  useEffect(() => { void runPreview() }, [runPreview])

  // ─── 确认入库 ───
  const handlePromote = useCallback(async () => {
    if (!selectedPending) return
    const { reviewId, targetId: pendingTargetId } = selectedPending
    const before = currentConfidence
    setPromoteBusy(true); setMessage(null)
    try {
      const resp = await promoteReview(reviewId)
      const after = preview?.final_confidence ?? null
      sessionStorage.removeItem(`${DRAFT_PREFIX}${pendingTargetId}`)
      clearReviewStatus(pendingTargetId)
      setDraft(null); setPreview(null); setConfirmOpen(false)
      setPromotedResult({ before, after })
      setProgress({ promoted: true })
      setQueue(queue.map(q => q.target_id === pendingTargetId ? { ...q, status: 'completed' } : q))
      if (state.taskId) {
        const entry = queue.find(q => q.target_id === pendingTargetId)
        if (entry?.taskItemId) {
          completePaperEvidenceTaskItem(state.taskId, entry.taskItemId, resp.evidence_id ?? '').catch(() => {})
        }
      }
      await Promise.all([loadList(), refreshPending()])
      // 自动下一条
      if (autoAdvance) {
        setTimeout(() => {
          setPendingItems(prev => {
            const idx = prev.findIndex(r => r.reviewId === reviewId)
            if (idx >= 0 && idx + 1 < prev.length) {
              setSelectedPendingId(prev[idx + 1].reviewId)
            }
            return prev
          })
        }, 1500)
      }
    } catch (err) {
      setMessage(`入库失败：${err instanceof Error ? err.message : String(err)}`)
      setConfirmOpen(false)
    } finally { setPromoteBusy(false) }
  }, [selectedPending, currentConfidence, queue, setQueue, loadList, refreshPending, state.taskId, setProgress, autoAdvance])

  // ─── 退回审核 ───
  const handleReturnToReview = useCallback(async () => {
    const rec = selectedPending
    if (!rec) return
    setPromoteBusy(true); setMessage(null)
    try {
      await returnReview(rec.reviewId, '退回人工审核')
      clearReviewStatus(rec.targetId)
      sessionStorage.removeItem(`${DRAFT_PREFIX}${rec.targetId}`)
      setDraft(null); setPreview(null); setConfirmOpen(false)
      await refreshPending()
      if (rec.targetType) openTarget(rec.targetType, rec.targetId, 'review')
      else {
        const entry = queue.find(q => q.target_id === rec.targetId)
        if (entry) openTarget(entry.target_type, entry.target_id, 'review')
      }
    } catch (err) {
      setMessage(`退回失败：${err instanceof Error ? err.message : String(err)}`)
    } finally { setPromoteBusy(false) }
  }, [selectedPending, refreshPending, openTarget, queue])

  // ─── 回滚 ───
  const handleRollback = useCallback(async (reason: string) => {
    const ev = detailEvidence
    if (!ev) return
    setRollbackBusy(true); setMessage(null)
    try { await rollbackPaperEvidence(ev.evidence_id, reason); setDetailEvidence(null); setMessage('证据已回滚'); await loadList() }
    catch (err) { setMessage(`回滚失败：${err instanceof Error ? err.message : String(err)}`) }
    finally { setRollbackBusy(false) }
  }, [detailEvidence, loadList])

  // ─── 右栏推送 ───
  const promotionImpact = useMemo<PromotionImpactState>(() => ({
    direction: draft?.reviewerDirection ?? selectedPending?.direction ?? 'supports',
    currentConfidence, reviewerConfidence: parseFloat(draft?.reviewerConfidence ?? '') || 0,
    preview, previewBusy, evidenceNewCount: 1, passagesNewCount: selectedPassages.length,
    canPromote: Boolean(draft && selectedPassages.length > 0 && selectedTargetType),
    onReturnToReview: () => void handleReturnToReview(),
    onPromote: () => setConfirmOpen(true),
  }), [draft, selectedPending, currentConfidence, preview, previewBusy, selectedPassages, selectedTargetType, handleReturnToReview])

  useEffect(() => {
    if (!selectedPending || !selectedTargetType || !draft) { setPromotionImpact(null); return }
    setPromotionImpact(promotionImpact)
  }, [selectedPending, selectedTargetType, draft, promotionImpact, setPromotionImpact])
  useEffect(() => () => { setPromotionImpact(null) }, [setPromotionImpact])

  const promoted = useMemo(() => items.filter(i => !i.invalidated_at), [items])
  const invalidated = useMemo(() => items.filter(i => i.invalidated_at), [items])

  // ─── 下一项 ───
  const nextPending = useMemo(() => {
    if (!selectedPendingId || pendingItems.length < 2) return null
    const idx = pendingItems.findIndex(r => r.reviewId === selectedPendingId)
    return idx >= 0 && idx + 1 < pendingItems.length ? pendingItems[idx + 1] : null
  }, [pendingItems, selectedPendingId])

  const handleNext = useCallback(() => {
    if (nextPending) setSelectedPendingId(nextPending.reviewId)
  }, [nextPending])

  if (!targetType || !targetId) {
    return (
      <div className="evidence-review">
        <div className="evidence-review-main">
          <div className="evidence-review-toolbar"><h3>证据晋升</h3></div>
          <EmptyState icon={<MousePointerClick size={24} />} title="请先从「佐证任务」进入一个目标对象" />
        </div>
      </div>
    )
  }

  return (
    <div className="evidence-review" data-testid="evidence-promotion">
      <div className="evidence-review-main">
        <div className="evidence-review-toolbar">
          <div className="evidence-review-toolbar-title">
            <h3>证据晋升</h3>
            <p className="evidence-module-hint">审核通过的证据将正式入库并更新知识对象置信度</p>
          </div>
          <div className="evidence-review-toolbar-actions">
            <label className="evidence-promotion-auto">
              <input type="checkbox" checked={autoAdvance} onChange={e => setAutoAdvance(e.target.checked)} />自动下一条
            </label>
          </div>
        </div>

        {message && <div className="ontology-page-message">{message}</div>}

        {/* Macro 治理晋升门禁:Rule PASS + Human Approved + Evidence 存在(仅 macro 候选匹配时显示) */}
        <MacroPromotionGate
          targetId={selectedPending?.targetId ?? ''}
          sourceName={dto?.source_region}
          targetName={dto?.target_region}
          sourceCanonicalId={dto?.source_region_canonical_id}
          targetCanonicalId={dto?.target_region_canonical_id}
          evidenceCount={selectedPassages.length}
        />

        {/* 待晋升列表(晋升前可手动切换选中项;第3-5步重构后恢复,防多待晋升无法切换) */}
        {pendingItems.length > 1 && (
          <div className="evidence-promotion-pending-list" data-testid="promotion-pending-list">
            {pendingItems.map(p => (
              <div
                key={p.reviewId}
                role="button"
                tabIndex={0}
                className={`evidence-promotion-pending-row${p.reviewId === selectedPendingId ? ' evidence-promotion-pending-row-active' : ''}`}
                data-testid="promotion-pending-row"
                onClick={() => setSelectedPendingId(p.reviewId)}
                onKeyDown={e => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault()
                    setSelectedPendingId(p.reviewId)
                  }
                }}
              >
                <span className="evidence-promotion-pending-name">{queue.find(q => q.target_id === p.targetId)?.label ?? p.targetId}</span>
                <span className="ew-meta">{DIRECTION_LABEL[p.direction]} · {LEVEL_LABEL[p.evidenceLevel]} · 置信度 {fmtConf(p.confidence)}</span>
              </div>
            ))}
          </div>
        )}

        {promotedResult && selectedPending && (
          <div className="evidence-promotion-result" data-testid="promotion-result">
            <span className="ew-ok">✅ 已入库</span>
            <span>置信度 {fmtConf(promotedResult.before)} → {fmtConf(promotedResult.after)}</span>
            {nextPending && (
              <button type="button" className="btn btn-sm btn-primary" onClick={handleNext}>
                下一项：{queue.find(q => q.target_id === nextPending.targetId)?.label ?? nextPending.targetId}
              </button>
            )}
            <button type="button" className="btn btn-sm" onClick={() => setPromotedResult(null)}>关闭</button>
          </div>
        )}

        {selectedPending && draft ? (
          <>
            <div className="evidence-review-paper">
              <span className="ew-meta">{draft.paperTitle || '—'} · PMID {draft.pmid || '—'}{draft.doi ? ` · DOI ${draft.doi}` : ''}</span>
            </div>

            {selectedPassages.length > 0 && (
              <CoveragePanel coverage={coverage} direction={coverageDirection} />
            )}

            <div className="evidence-promotion-decision">
              <h4>审核决策</h4>
              <div className="evidence-promotion-decision-rows">
                <div className="evidence-promotion-decision-row">
                  <span>人工方向</span><strong>{DIRECTION_LABEL[draft.reviewerDirection ?? 'supports']}</strong>
                  {draft.modelDirection && <em>（AI：{DIRECTION_LABEL[draft.modelDirection]}）</em>}
                </div>
                <div className="evidence-promotion-decision-row">
                  <span>证据等级</span><strong>{LEVEL_LABEL[draft.reviewerEvidenceLevel ?? 'indirect']}</strong>
                </div>
                <div className="evidence-promotion-decision-row">
                  <span>Reviewer 置信度</span><strong>{draft.reviewerConfidence ?? '—'}</strong>
                </div>
                <div className="evidence-promotion-decision-row">
                  <span>核验片段</span><span>{selectedPassages.length} 段</span>
                </div>
              </div>
            </div>

            <div className="evidence-promotion-preview" data-testid="promotion-confidence-preview">
              <h4>置信度变化预览</h4>
              {previewBusy ? (
                <span className="ew-meta">计算中…</span>
              ) : preview ? (
                <div className="evidence-promotion-confidence-grid">
                  <div className="evidence-promotion-confidence-cell">
                    <span className="evidence-promotion-confidence-label">当前</span>
                    <strong>{fmtConf(currentConfidence)}</strong>
                  </div>
                  <span className="evidence-promotion-confidence-arrow">→</span>
                  <div className="evidence-promotion-confidence-cell">
                    <span className="evidence-promotion-confidence-label">审核人建议</span>
                    <strong>{fmtConf(parseFloat(draft.reviewerConfidence ?? '0') || 0)}</strong>
                  </div>
                  <span className="evidence-promotion-confidence-arrow">→</span>
                  <div className="evidence-promotion-confidence-cell evidence-promotion-confidence-final">
                    <span className="evidence-promotion-confidence-label">入库后预计</span>
                    <strong>{fmtConf(preview.final_confidence)}</strong>
                    {preview.cap != null && <span className="ew-meta">上限 {fmtConf(preview.cap)}</span>}
                  </div>
                </div>
              ) : (
                <span className="ew-meta">无预览数据</span>
              )}
              {preview?.block_reasons?.length ? (
                <div className="ew-bad">⚠ {preview.block_reasons.join('；')}</div>
              ) : null}
            </div>

            <div className="evidence-promotion-actions">
              <button type="button" className="btn btn-sm" disabled={promoteBusy} onClick={() => handleReturnToReview()}>
                退回审核
              </button>
              <button
                type="button" className="btn btn-sm btn-primary" data-testid="promotion-confirm-btn"
                disabled={promoteBusy || !draft || selectedPassages.length === 0 || !macroGateOk}
                onClick={() => setConfirmOpen(true)}
              >
                {promoteBusy ? '处理中…' : '确认入库'}
              </button>
              {!macroGateOk && (
                <span className="ew-bad" data-testid="promotion-macro-gate-blocked">
                  Macro 晋升条件未满足(Rule PASS + Human Approved + Evidence 存在),先处理后再入库
                </span>
              )}
            </div>

            <div className="ew-meta" style={{ marginTop: 8 }}>审核状态：review_approved · {fmtDate(selectedPending.approvedAt)}</div>

            {/* 已晋升记录 */}
            {items.length > 0 && (
              <section className="evidence-promotion-group" style={{ marginTop: 16 }}>
                <div className="evidence-promotion-group-head">
                  <span className="evidence-promotion-group-title">已晋升证据</span>
                  <span className="evidence-promotion-group-count">{promoted.length}</span>
                </div>
                {promoted.slice(0, 5).map(ev => (
                  <div
                    key={ev.evidence_id}
                    className="evidence-promotion-row"
                    data-testid="promotion-evidence-row"
                    onClick={() => setDetailEvidence(ev)}
                  >
                    <div className="evidence-promotion-row-main">
                      <strong>{ev.title || '—'}</strong>
                      <span className="ew-meta">{DIRECTION_LABEL[ev.direction as keyof typeof DIRECTION_LABEL] ?? ev.direction} · PMID {ev.pmid} · {ev.created_at ? fmtDate(ev.created_at) : '—'}</span>
                    </div>
                    {ev.confidence_adjustment_status && (
                      <span className="ew-ok">{ev.confidence_adjustment_status}</span>
                    )}
                  </div>
                ))}
                {invalidated.length > 0 && (
                  <>
                    <div className="evidence-promotion-group-head" style={{ marginTop: 8 }}>
                      <span className="evidence-promotion-group-title">已失效</span>
                      <span className="evidence-promotion-group-count">{invalidated.length}</span>
                    </div>
                    {invalidated.slice(0, 3).map(ev => (
                      <div
                        key={ev.evidence_id}
                        className="evidence-promotion-row"
                        data-testid="promotion-invalidated-row"
                        onClick={() => setDetailEvidence(ev)}
                      >
                        <div className="evidence-promotion-row-main">
                          <strong>{ev.title || '—'}</strong>
                          <span className="ew-meta">回滚理由：{ev.invalidation_reason || '—'}</span>
                        </div>
                      </div>
                    ))}
                  </>
                )}
              </section>
            )}
          </>
        ) : selectedPending ? (
          <EmptyState compact title="该对象没有可晋升的审核草稿" description="可能已被清理，可在人工审核模块重新处理。" />
        ) : pendingItems.length === 0 ? (
          <EmptyState compact title="暂无待晋升的审核通过证据" description="从人工审核批准证据后将在此处执行晋升。" />
        ) : (
          <EmptyState compact title="请从左侧队列中选择一个待晋升对象" />
        )}
      </div>

      <EvidenceDetailDrawer
        open={detailEvidence !== null}
        evidence={detailEvidence}
        onClose={() => setDetailEvidence(null)}
        onRollback={(reason) => void handleRollback(reason)}
      />

      <PromotionDialog
        open={confirmOpen}
        targetLabel={selectedQueueEntry?.label ?? selectedPending?.targetId ?? ''}
        claimText={dto?.claim_text ?? ''}
        paper={{ title: draft?.paperTitle ?? '', pmid: draft?.pmid ?? '', doi: draft?.doi ?? null }}
        passages={selectedPassages}
        components={claimComponents}
        direction={draft?.reviewerDirection ?? 'supports'}
        preview={preview}
        busy={promoteBusy}
        onConfirm={() => void handlePromote()}
        onClose={() => setConfirmOpen(false)}
      />
    </div>
  )
}
