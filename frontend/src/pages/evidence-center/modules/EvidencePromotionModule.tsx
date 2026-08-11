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
import { ClaimPanel } from '../components/ClaimPanel'
import { EmptyState } from '../components/EmptyState'
import { CoveragePanel } from '../components/CoveragePanel'
import { EvidenceDetailDrawer } from '../components/EvidenceDetailDrawer'
import { PromotionDialog } from '../components/PromotionDialog'
import type { PromotionImpactState } from '../components/PromotionImpact'
import { clearReviewStatus, listReviewApproved } from '../components/ReviewStatusStore'
import { aggregateTmpDirection, computeTmpCoverage } from '../components/claimCoverage'
import type { Direction, EvidenceLevel, WorkbenchPassage } from '../components/types'
import { DIRECTION_LABEL, LEVEL_LABEL } from '../components/types'

const DRAFT_PREFIX = 'evidence-center.review-draft.'

/** T8 人工审核模块写回的完整草稿(含人工决策值) */
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

/** Phase 2:后端 EvidenceReviewItem 映射为晋升模块展示所需字段 */
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
  try {
    return new Date(v).toLocaleString('zh-CN', { hour12: false })
  } catch {
    return v
  }
}

/** 证据晋升模块:唯一 attach 入口。待晋升(review_approved)/已晋升/已失效(按 invalidated_at 分组) */
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
  const [attachBusy, setAttachBusy] = useState(false)
  const [detailEvidence, setDetailEvidence] = useState<PaperEvidenceItem | null>(null)
  const [rollbackBusy, setRollbackBusy] = useState(false)
  const [message, setMessage] = useState<string | null>(null)
  const abortRef = useRef<AbortController | null>(null)

  const targetType = state.targetType
  const targetId = state.targetId

  // ─── Phase 2:待晋升列表 = 后端 listEvidenceReviews + sessionStorage 兜底 ───
  const refreshPending = useCallback(async () => {
    try {
      const r = await listEvidenceReviews({ review_status: 'approved', promotion_status: 'awaiting_promotion', page_size: 100 })
      setPendingItems(r.items.map(mapReviewToPending))
    } catch {
      // 后端不可用时降级为 sessionStorage
      setPendingItems(listReviewApproved()
        .filter(rec => rec.status === 'review_approved')
        .map(rec => ({
          reviewId: rec.targetId,
          targetType: rec.targetType ?? '',
          targetId: rec.targetId,
          direction: rec.meta.direction,
          evidenceLevel: rec.meta.evidenceLevel,
          confidence: parseFloat(rec.meta.confidence) || 0,
          note: rec.meta.note,
          approvedAt: rec.meta.at,
        })),
      )
    }
  }, [])

  useEffect(() => { void refreshPending() }, [refreshPending])

  // ─── 选中项:优先跟随当前对象,其次列表首个(按 targetId 匹配)——reviewId 是后端主键 ───
  useEffect(() => {
    if (pendingItems.length === 0) {
      setSelectedPendingId(null)
      return
    }
    setSelectedPendingId(prev => {
      if (prev && pendingItems.some(r => r.reviewId === prev)) return prev
      const matchByTarget = pendingItems.find(r => r.targetId === targetId)
      if (matchByTarget) return matchByTarget.reviewId
      return pendingItems[0].reviewId
    })
  }, [pendingItems, targetId])

  const selectedPending = pendingItems.find(r => r.reviewId === selectedPendingId) ?? null

  /** 选中项的 target_type:记录自带 → 队列匹配 → 当前对象兜底 */
  const selectedTargetType = useMemo(() => {
    if (!selectedPending) return null
    if (selectedPending.targetType) return selectedPending.targetType
    const entry = queue.find(q => q.target_id === selectedPending.targetId)
    if (entry) return entry.target_type
    if (selectedPending.targetId === targetId) return targetType
    return null
  }, [selectedPending, queue, targetType, targetId])

  const selectedQueueEntry = queue.find(q => selectedPending && q.target_id === selectedPending.targetId)

  // ─── 选中项草稿恢复(有 reviewerDirection 且含已核验片段;draft key 仍用 targetId) ───
  useEffect(() => {
    setDraft(null)
    setPreview(null)
    setDetailEvidence(null)
    if (!selectedPending) return
    const draftTargetId = selectedPending.targetId
    const raw = sessionStorage.getItem(`${DRAFT_PREFIX}${draftTargetId}`)
    if (!raw) return
    try {
      const d = JSON.parse(raw) as Partial<ReviewDraft>
      const hasDirection = Boolean(d.reviewerDirection)
      const hasVerifiedPassages = Array.isArray(d.passages) && d.passages.some(p => p.source_verified)
      if (hasDirection && hasVerifiedPassages) {
        setDraft(d as ReviewDraft)
      }
    } catch {
      // 草稿损坏时忽略,保持空态
    }
  }, [selectedPending])

  // ─── 选中项 Claim 数据 ───
  useEffect(() => {
    if (!selectedTargetType || !selectedPending?.targetId) {
      setDto(null)
      return
    }
    let cancelled = false
    setDto(null)
    getEvidenceTarget(selectedTargetType, selectedPending.targetId)
      .then(d => { if (!cancelled) setDto(d) })
      .catch(() => { if (!cancelled) setDto(null) })
    return () => { cancelled = true }
  }, [selectedTargetType, selectedPending?.targetId])

  // ─── 已晋升/已失效列表(当前对象,listPaperEvidence) ───
  const loadList = useCallback(async () => {
    if (!targetType || !targetId) {
      setItems([])
      return
    }
    try {
      const r = await listPaperEvidence({ target_type: targetType, target_id: targetId, limit: 50 })
      setItems(r.items)
    } catch {
      setItems([])
    }
  }, [targetType, targetId])

  useEffect(() => {
    void loadList()
  }, [loadList])

  const selectedPassages = useMemo(
    () => (draft?.passages ?? []).filter(p => p.source_verified),
    [draft],
  )

  const claimComponents = useMemo(() => dto?.claim_components ?? [], [dto])
  const coverage = useMemo(() => computeTmpCoverage(claimComponents, selectedPassages), [claimComponents, selectedPassages])
  const coverageDirection = useMemo(() => aggregateTmpDirection(coverage, selectedPassages), [coverage, selectedPassages])

  const currentConfidence = dto?.current_confidence ?? selectedQueueEntry?.confidence ?? null

  // ─── 预计后置信度预览(草稿就绪后自动计算) ───
  const runPreview = useCallback(async () => {
    if (!selectedTargetType || !selectedPending?.targetId || !draft?.pmid) return
    if (selectedPassages.length === 0) {
      setPreview(null)
      return
    }
    setPreviewBusy(true)
    abortRef.current?.abort()
    abortRef.current = new AbortController()
    try {
      const r = await attachPaperEvidencePreview({
        target_type: selectedTargetType,
        target_id: selectedPending.targetId,
        pmid: draft.pmid,
        direction: draft.reviewerDirection ?? 'supports',
        reviewer_confidence: parseFloat(draft.reviewerConfidence ?? '0.8') || 0,
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
        setMessage(`置信度预览失败：${err instanceof Error ? err.message : String(err)}`)
      }
      setPreview(null)
    } finally {
      setPreviewBusy(false)
    }
  }, [selectedTargetType, selectedPending?.targetId, draft, selectedPassages])

  useEffect(() => { void runPreview() }, [runPreview])

  // ─── Phase 2:晋升 → promoteReview(后端 Review) → 清状态 + 刷新 + 更新 queue ───
  const handlePromote = useCallback(async () => {
    if (!selectedPending) return
    const { reviewId, targetId: pendingTargetId } = selectedPending
    setAttachBusy(true)
    setMessage(null)
    try {
      const resp = await promoteReview(reviewId)
      sessionStorage.removeItem(`${DRAFT_PREFIX}${pendingTargetId}`)
      clearReviewStatus(pendingTargetId)
      setDraft(null)
      setPreview(null)
      setConfirmOpen(false)
      // 晋升成功 → 推进 StepPills → 确认晋升
      setProgress({ promoted: true })
      setMessage('证据已晋升并应用到知识对象')
      setQueue(queue.map(q =>
        q.target_id === pendingTargetId ? { ...q, status: 'completed' } : q,
      ))
      // 标记后端 task item 完成(镜像旧 Modal 条件调用),失败静默,不阻断晋升主流程
      if (state.taskId) {
        const entry = queue.find(q => q.target_id === pendingTargetId)
        if (entry?.taskItemId) {
          try {
            await completePaperEvidenceTaskItem(state.taskId, entry.taskItemId, resp.evidence_id ?? '')
          } catch {
            // 标记失败不影响已入库证据
          }
        }
      }
      await Promise.all([loadList(), refreshPending()])
    } catch (err) {
      setMessage(`晋升失败：${err instanceof Error ? err.message : String(err)}`)
    } finally {
      setAttachBusy(false)
    }
  }, [selectedPending, queue, setQueue, loadList, refreshPending, state.taskId, setProgress])

  // ─── Phase 2:退回人工审核 → returnReview(后端) + 清 status + 清 draft → 跳转 review ───
  const handleReturnToReview = useCallback(async () => {
    const rec = selectedPending
    if (!rec) return
    setAttachBusy(true)
    setMessage(null)
    try {
      await returnReview(rec.reviewId, '退回人工审核')
      clearReviewStatus(rec.targetId)
      sessionStorage.removeItem(`${DRAFT_PREFIX}${rec.targetId}`)
      setDraft(null)
      setPreview(null)
      setConfirmOpen(false)
      await refreshPending()
      if (rec.targetType) {
        openTarget(rec.targetType, rec.targetId, 'review')
      } else {
        const entry = queue.find(q => q.target_id === rec.targetId)
        if (entry) openTarget(entry.target_type, entry.target_id, 'review')
      }
    } catch (err) {
      setMessage(`退回失败：${err instanceof Error ? err.message : String(err)}`)
    } finally {
      setAttachBusy(false)
    }
  }, [selectedPending, refreshPending, openTarget, queue])

  // ─── 回滚:抽屉内 ConfirmDialog 输入原因 → rollback → 刷新列表 ───
  const handleRollback = useCallback(async (reason: string) => {
    const ev = detailEvidence
    if (!ev) return
    setRollbackBusy(true)
    setMessage(null)
    try {
      await rollbackPaperEvidence(ev.evidence_id, reason)
      setDetailEvidence(null)
      setMessage('证据已回滚')
      await loadList()
    } catch (err) {
      setMessage(`回滚失败：${err instanceof Error ? err.message : String(err)}`)
    } finally {
      setRollbackBusy(false)
    }
  }, [detailEvidence, loadList])

  // ─── 右栏接入:把晋升影响状态推送给 Context,RightPanel 渲染 PromotionImpact ───
  const promotionImpact = useMemo<PromotionImpactState>(() => ({
    direction: draft?.reviewerDirection ?? selectedPending?.direction ?? 'supports',
    currentConfidence,
    reviewerConfidence: parseFloat(draft?.reviewerConfidence ?? '') || 0,
    preview,
    previewBusy,
    evidenceNewCount: 1,
    passagesNewCount: selectedPassages.length,
    canPromote: Boolean(draft && selectedPassages.length > 0 && selectedTargetType),
    onReturnToReview: () => void handleReturnToReview(),
    onPromote: () => setConfirmOpen(true),
  }), [draft, selectedPending, currentConfidence, preview, previewBusy, selectedPassages, selectedTargetType, handleReturnToReview])

  useEffect(() => {
    if (!selectedPending || !selectedTargetType || !draft) {
      setPromotionImpact(null)
      return
    }
    setPromotionImpact(promotionImpact)
  }, [selectedPending, selectedTargetType, draft, promotionImpact, setPromotionImpact])

  useEffect(() => () => { setPromotionImpact(null) }, [setPromotionImpact])

  const promoted = useMemo(() => items.filter(i => !i.invalidated_at), [items])
  const invalidated = useMemo(() => items.filter(i => i.invalidated_at), [items])

  const pendingGroup = (
    <section className="evidence-promotion-group" data-testid="promotion-pending-group">
      <div className="evidence-promotion-group-head">
        <span className="evidence-promotion-group-title">待晋升</span>
        <span className="evidence-promotion-group-count">{pendingItems.length}</span>
        <span className="ew-meta">来自人工审核通过（review_approved）</span>
      </div>
      {pendingItems.length === 0 && (
        <EmptyState compact title="暂无待晋升的审核通过证据" />
      )}
      {pendingItems.map(rec => {
        const entry = queue.find(q => q.target_id === rec.targetId)
        const selected = rec.reviewId === selectedPendingId
        return (
          <div
            key={rec.reviewId}
            className={`evidence-promotion-row${selected ? ' evidence-promotion-row-selected' : ''}`}
            data-testid="promotion-pending-row"
            onClick={() => { setMessage(null); setSelectedPendingId(rec.reviewId) }}
          >
            <div className="evidence-promotion-row-main">
              <strong>{entry?.label ?? rec.targetId}</strong>
              <span className="ew-meta">
                {DIRECTION_LABEL[rec.direction]} · {LEVEL_LABEL[rec.evidenceLevel]} · 置信度 {rec.confidence} · {fmtDate(rec.approvedAt)}
              </span>
            </div>
            <span className="ew-warn">{selected ? '查看中' : '待晋升'}</span>
          </div>
        )
      })}
      {selectedPending && draft && (
        <div className="evidence-promotion-card" data-testid="promotion-pending-detail">
          <ClaimPanel
            claimText={dto?.claim_text ?? ''}
            components={claimComponents}
            confidence={dto?.current_confidence ?? null}
            evidenceCount={dto?.existing_evidence ?? 0}
            targetType={selectedTargetType ?? ''}
            granularity={dto?.granularity ?? ''}
          />
          <div className="evidence-promotion-paper">
            <h4>论文</h4>
            <strong>{draft.paperTitle || '—'}</strong>
            <span className="ew-meta">PMID {draft.pmid || '—'}{draft.doi ? ` · DOI ${draft.doi}` : ''}</span>
            {draft.modelAssessment && <p className="ew-meta">模型评估：{draft.modelAssessment}</p>}
          </div>
          {selectedPassages.length > 0 && (
            <CoveragePanel coverage={coverage} direction={coverageDirection} />
          )}
          <div className="evidence-promotion-decision">
            <h4>Reviewer 决策</h4>
            <div className="evidence-promotion-decision-rows">
              <div className="evidence-promotion-decision-row">
                <span>人工方向</span>
                <strong>{DIRECTION_LABEL[draft.reviewerDirection ?? 'supports']}</strong>
                {draft.modelDirection && <em>AI 推荐：{DIRECTION_LABEL[draft.modelDirection]}</em>}
              </div>
              <div className="evidence-promotion-decision-row">
                <span>证据等级</span>
                <strong>{LEVEL_LABEL[draft.reviewerEvidenceLevel ?? 'indirect']}</strong>
              </div>
              <div className="evidence-promotion-decision-row">
                <span>Reviewer 置信度</span>
                <strong>{draft.reviewerConfidence ?? '—'}</strong>
              </div>
              <div className="evidence-promotion-decision-row">
                <span>人工备注</span>
                <span>{draft.note || '—'}</span>
              </div>
              <div className="evidence-promotion-decision-row">
                <span>所选片段</span>
                <span>{selectedPassages.length} 段（均已核验原文）</span>
              </div>
              <div className="evidence-promotion-decision-row" data-testid="promotion-confidence">
                <span>预计后置信度</span>
                <strong>{previewBusy ? '计算中…' : `当前 ${currentConfidence ?? '—'} → 预计晋升后置信度 ${preview?.final_confidence ?? '—'}`}</strong>
              </div>
            </div>
          </div>
          <div className="ew-meta">审核状态：review_approved · {fmtDate(selectedPending.approvedAt)}</div>
        </div>
      )}
      {selectedPending && !draft && (
        <EmptyState compact title="该对象没有可晋升的审核草稿" description="可能已被清理，可在人工审核模块重新处理。" />
      )}
    </section>
  )

  if (!targetType || !targetId) {
    return (
      <div className="evidence-promotion">
        {pendingGroup}
        <EmptyState
          icon={<MousePointerClick size={24} />}
          title="请先从「佐证任务」或「证据候选」进入一个目标对象"
          description="打开任务并选择目标对象后即可晋升审核通过的证据。"
        />
      </div>
    )
  }

  return (
    <div className="evidence-promotion" data-testid="evidence-promotion">
      {message && <div className="ontology-page-message">{message}</div>}

      {pendingGroup}

      <section className="evidence-promotion-group" data-testid="promotion-promoted-group">
        <div className="evidence-promotion-group-head">
          <span className="evidence-promotion-group-title">已晋升</span>
          <span className="evidence-promotion-group-count">{promoted.length}</span>
        </div>
        {promoted.length === 0 && (
          <EmptyState compact title="暂无已晋升的论文证据" />
        )}
        {promoted.map(ev => (
          <div
            key={ev.evidence_id}
            className="evidence-promotion-row"
            data-testid="promotion-evidence-row"
            onClick={() => setDetailEvidence(ev)}
          >
            <div className="evidence-promotion-row-main">
              <strong>{ev.title ?? ev.evidence_text}</strong>
              <span className="ew-meta">
                {DIRECTION_LABEL[ev.direction as keyof typeof DIRECTION_LABEL] ?? ev.direction ?? '—'} · PMID {ev.pmid ?? '—'} · {fmtDate(ev.created_at)}
              </span>
            </div>
            <span className="ew-ok">已晋升</span>
          </div>
        ))}
      </section>

      <section className="evidence-promotion-group" data-testid="promotion-invalidated-group">
        <div className="evidence-promotion-group-head">
          <span className="evidence-promotion-group-title">已失效</span>
          <span className="evidence-promotion-group-count">{invalidated.length}</span>
        </div>
        {invalidated.length === 0 && (
          <EmptyState compact title="暂无已失效的论文证据" />
        )}
        {invalidated.map(ev => (
          <div
            key={ev.evidence_id}
            className="evidence-promotion-row evidence-promotion-row-invalidated"
            data-testid="promotion-invalidated-row"
            onClick={() => setDetailEvidence(ev)}
          >
            <div className="evidence-promotion-row-main">
              <strong>{ev.title ?? ev.evidence_text}</strong>
              <span className="ew-meta">
                {ev.invalidation_reason ?? '—'} · {fmtDate(ev.invalidated_at)}
              </span>
            </div>
            <span className="ew-bad">已失效</span>
          </div>
        ))}
      </section>

      {draft && (
        <PromotionDialog
          open={confirmOpen}
          targetLabel={selectedQueueEntry?.label ?? selectedPending?.targetId ?? ''}
          claimText={dto?.claim_text ?? ''}
          paper={{ title: draft.paperTitle, pmid: draft.pmid, doi: draft.doi ?? null }}
          passages={selectedPassages}
          components={claimComponents}
          direction={draft.reviewerDirection ?? 'supports'}
          preview={preview}
          busy={attachBusy}
          onConfirm={() => void handlePromote()}
          onClose={() => setConfirmOpen(false)}
        />
      )}

      <EvidenceDetailDrawer
        open={detailEvidence !== null}
        evidence={detailEvidence}
        onClose={() => setDetailEvidence(null)}
        onRollback={reason => void handleRollback(reason)}
      />
      {rollbackBusy && <div className="ew-busy">回滚中…</div>}
    </div>
  )
}
