import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  attachPaperEvidence,
  attachPaperEvidencePreview,
  getEvidenceTarget,
  listPaperEvidence,
  rollbackPaperEvidence,
  type AttachPreviewResponse,
  type EvidenceTargetDto,
  type PaperEvidenceItem,
} from '../../../api/endpoints'
import { useEvidenceCenter } from '../EvidenceCenterContext'
import { ClaimPanel } from '../components/ClaimPanel'
import { EvidenceDetailDrawer } from '../components/EvidenceDetailDrawer'
import { PromotionDialog } from '../components/PromotionDialog'
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

function fmtDate(v: string | null | undefined): string {
  if (!v) return '—'
  try {
    return new Date(v).toLocaleString('zh-CN', { hour12: false })
  } catch {
    return v
  }
}

/** 证据晋升模块:唯一 attach 入口。待晋升(审核草稿)/已晋升/已失效(按 invalidated_at 分组) */
export function EvidencePromotionModule() {
  const { state, queue, setQueue } = useEvidenceCenter()
  const [dto, setDto] = useState<EvidenceTargetDto | null>(null)
  const [draft, setDraft] = useState<ReviewDraft | null>(null)
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

  // ─── 待晋升草稿恢复(有 reviewerDirection 且含已核验片段) ───
  useEffect(() => {
    setDraft(null)
    setPreview(null)
    setDetailEvidence(null)
    setMessage(null)
    if (!targetId) return
    const raw = sessionStorage.getItem(`${DRAFT_PREFIX}${targetId}`)
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
  }, [targetId])

  // ─── Claim 数据 + 已晋升/已失效列表 ───
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
    if (!targetType || !targetId) {
      setDto(null)
      setItems([])
      return
    }
    let cancelled = false
    setDto(null)
    getEvidenceTarget(targetType, targetId)
      .then(d => { if (!cancelled) setDto(d) })
      .catch(() => { if (!cancelled) setDto(null) })
    void loadList()
    return () => { cancelled = true }
  }, [targetType, targetId, loadList])

  const selectedPassages = useMemo(
    () => (draft?.passages ?? []).filter(p => p.source_verified),
    [draft],
  )

  // ─── 预计后置信度预览(草稿就绪后自动计算) ───
  const runPreview = useCallback(async () => {
    if (!targetType || !targetId || !draft?.pmid) return
    if (selectedPassages.length === 0) {
      setPreview(null)
      return
    }
    setPreviewBusy(true)
    abortRef.current?.abort()
    abortRef.current = new AbortController()
    try {
      const r = await attachPaperEvidencePreview({
        target_type: targetType,
        target_id: targetId,
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
  }, [targetType, targetId, draft, selectedPassages])

  useEffect(() => { void runPreview() }, [runPreview])

  // ─── 晋升:PromotionDialog 确认 → attach → 清 draft + 刷新列表 + 更新 queue ───
  const handlePromote = useCallback(async () => {
    if (!targetType || !targetId || !draft) return
    setAttachBusy(true)
    setMessage(null)
    try {
      await attachPaperEvidence({
        target_type: targetType,
        target_id: targetId,
        pmid: draft.pmid,
        direction: draft.reviewerDirection ?? 'supports',
        evidence_level: draft.reviewerEvidenceLevel ?? 'indirect',
        model_direction: draft.modelDirection ?? null,
        model_assessment: draft.modelAssessment ?? null,
        reviewer_note: draft.note ?? null,
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
      })
      sessionStorage.removeItem(`${DRAFT_PREFIX}${targetId}`)
      setDraft(null)
      setPreview(null)
      setConfirmOpen(false)
      setMessage('证据已晋升并应用到知识对象')
      setQueue(queue.map(q =>
        q.target_type === targetType && q.target_id === targetId ? { ...q, status: 'completed' } : q,
      ))
      await loadList()
    } catch (err) {
      setMessage(`晋升失败：${err instanceof Error ? err.message : String(err)}`)
    } finally {
      setAttachBusy(false)
    }
  }, [targetType, targetId, draft, selectedPassages, queue, setQueue, loadList])

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

  const queueEntry = queue.find(q => q.target_type === targetType && q.target_id === targetId)
  const currentConfidence = dto?.current_confidence ?? queueEntry?.confidence ?? null

  const promoted = useMemo(() => items.filter(i => !i.invalidated_at), [items])
  const invalidated = useMemo(() => items.filter(i => i.invalidated_at), [items])

  if (!targetType || !targetId) {
    return (
      <div className="evidence-promotion">
        <div className="evidence-promotion-empty">
          请先从「佐证任务」或「证据候选」进入一个目标对象。
        </div>
      </div>
    )
  }

  return (
    <div className="evidence-promotion" data-testid="evidence-promotion">
      {message && <div className="ontology-page-message">{message}</div>}

      {draft && selectedPassages.length > 0 && (
        <section className="evidence-promotion-group" data-testid="promotion-pending-group">
          <div className="evidence-promotion-group-head">
            <span className="evidence-promotion-group-title">待晋升</span>
            <span className="evidence-promotion-group-count">1</span>
            <span className="ew-meta">来自人工审核草稿（已确认方向）</span>
          </div>
          <div className="evidence-promotion-card">
            <ClaimPanel
              claimText={dto?.claim_text ?? ''}
              components={dto?.claim_components ?? []}
              confidence={dto?.current_confidence ?? null}
              evidenceCount={dto?.existing_evidence ?? 0}
              targetType={targetType}
              granularity={dto?.granularity ?? ''}
            />
            <div className="evidence-promotion-paper">
              <h4>论文</h4>
              <strong>{draft.paperTitle || '—'}</strong>
              <span className="ew-meta">PMID {draft.pmid || '—'}{draft.doi ? ` · DOI ${draft.doi}` : ''}</span>
              {draft.modelAssessment && <p className="ew-meta">模型评估：{draft.modelAssessment}</p>}
            </div>
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
            <div className="evidence-promotion-actions">
              <button
                type="button"
                className="btn btn-sm btn-primary"
                data-testid="promotion-open-dialog"
                onClick={() => setConfirmOpen(true)}
              >
                确认晋升
              </button>
            </div>
          </div>
        </section>
      )}

      <section className="evidence-promotion-group" data-testid="promotion-promoted-group">
        <div className="evidence-promotion-group-head">
          <span className="evidence-promotion-group-title">已晋升</span>
          <span className="evidence-promotion-group-count">{promoted.length}</span>
        </div>
        {promoted.length === 0 && (
          <div className="evidence-promotion-empty">暂无已晋升的论文证据</div>
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
          <div className="evidence-promotion-empty">暂无已失效的论文证据</div>
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
          targetLabel={queueEntry?.label ?? targetId}
          claimText={dto?.claim_text ?? ''}
          paper={{ title: draft.paperTitle, pmid: draft.pmid, doi: draft.doi ?? null }}
          passages={selectedPassages}
          components={dto?.claim_components ?? []}
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
