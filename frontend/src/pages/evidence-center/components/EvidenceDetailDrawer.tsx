import { useState } from 'react'
import type { PaperEvidenceItem } from '../../../api/endpoints'
import { ConfirmDialog } from '../../../components/ConfirmDialog'
import { COMPONENT_LABEL, DIRECTION_LABEL, LEVEL_LABEL } from './types'

interface Props {
  open: boolean
  evidence: PaperEvidenceItem | null
  onClose: () => void
  onRollback: (reason: string) => void
}

const VERIFICATION_LABEL: Record<string, string> = {
  verified: '已验证',
  invalidated: '已失效',
  pending: '待处理',
  under_review: '复核中',
}

function fmtConfidence(v: number | null | undefined): string {
  return v == null ? '—' : v.toFixed(2)
}

function fmtDate(v: string | null | undefined): string {
  if (!v) return '—'
  try {
    return new Date(v).toLocaleString('zh-CN', { hour12: false })
  } catch {
    return v
  }
}

/** 论文证据详情抽屉:claim snapshot / 论文 / coverage / reviewer 决策 / passages;有效证据可回滚 */
export function EvidenceDetailDrawer({ open, evidence, onClose, onRollback }: Props) {
  const [reason, setReason] = useState('')
  const [confirmOpen, setConfirmOpen] = useState(false)
  if (!open || !evidence) return null

  const invalidated = Boolean(evidence.invalidated_at)
  const coverage = evidence.coverage_summary_snapshot
  const claimComponents = evidence.claim_components_snapshot ?? []
  const passages = evidence.passages ?? []

  return (
    <div className="evidence-drawer-overlay" onClick={onClose}>
      <aside
        className="evidence-drawer"
        role="dialog"
        aria-label="证据详情"
        data-testid="evidence-detail-drawer"
        onClick={e => e.stopPropagation()}
      >
        <header className="evidence-drawer-head">
          <h4 className="evidence-drawer-title">证据详情</h4>
          <button type="button" className="evidence-drawer-close" aria-label="关闭" onClick={onClose}>×</button>
        </header>
        <div className="evidence-drawer-body evidence-detail-body">
          <section className="evidence-detail-section">
            <h5 className="evidence-detail-section-title">Claim 快照</h5>
            <p className="evidence-detail-claim">{evidence.claim_text_snapshot ?? evidence.evidence_text ?? '—'}</p>
            {claimComponents.length > 0 && (
              <div className="evidence-detail-chips">
                {claimComponents.map(c => (
                  <span key={c.component_type} className="evidence-detail-chip">
                    <b>{COMPONENT_LABEL[c.component_type] ?? c.component_type}</b>
                    <span>{c.statement}</span>
                  </span>
                ))}
              </div>
            )}
          </section>

          <section className="evidence-detail-section">
            <h5 className="evidence-detail-section-title">论文信息</h5>
            <div className="evidence-detail-meta">
              <div className="evidence-detail-meta-row"><span>标题</span><strong>{evidence.title ?? '—'}</strong></div>
              <div className="evidence-detail-meta-row"><span>期刊</span><span>{evidence.journal ?? '—'}{evidence.year ? ` (${evidence.year})` : ''}</span></div>
              <div className="evidence-detail-meta-row"><span>PMID / DOI</span><span>{evidence.pmid ?? '—'} / {evidence.doi ?? '—'}</span></div>
              <div className="evidence-detail-meta-row"><span>晋升时间</span><span>{fmtDate(evidence.created_at)}</span></div>
              <div className="evidence-detail-meta-row">
                <span>验证状态</span>
                <span className={invalidated ? 'ew-bad' : 'ew-ok'}>
                  {VERIFICATION_LABEL[evidence.verification_status ?? ''] ?? evidence.verification_status ?? '—'}
                  {invalidated ? `（${fmtDate(evidence.invalidated_at)}）` : ''}
                </span>
              </div>
              {evidence.invalidation_reason && (
                <div className="evidence-detail-meta-row"><span>失效原因</span><span>{evidence.invalidation_reason}</span></div>
              )}
            </div>
          </section>

          {coverage && (
            <section className="evidence-detail-section">
              <h5 className="evidence-detail-section-title">覆盖摘要</h5>
              <div className="evidence-detail-meta">
                <div className="evidence-detail-meta-row"><span>覆盖度</span><span>{Math.round(coverage.coverage_ratio * 100)}%</span></div>
                <div className="evidence-detail-meta-row"><span>总方向</span><span>{DIRECTION_LABEL[coverage.overall_direction as keyof typeof DIRECTION_LABEL] ?? coverage.overall_direction}</span></div>
                <div className="evidence-detail-meta-row"><span>支持组件</span><span>{coverage.supported_components.map(c => COMPONENT_LABEL[c] ?? c).join('、') || '—'}</span></div>
                <div className="evidence-detail-meta-row"><span>未覆盖组件</span><span>{coverage.uncovered_components.map(c => COMPONENT_LABEL[c] ?? c).join('、') || '—'}</span></div>
                <div className="evidence-detail-meta-row"><span>结论</span><span>{coverage.full_claim_supported ? '完整支持 Claim' : coverage.has_conflict ? '存在冲突' : '部分支持'}</span></div>
              </div>
            </section>
          )}

          <section className="evidence-detail-section">
            <h5 className="evidence-detail-section-title">Reviewer 决策</h5>
            <div className="evidence-detail-meta">
              <div className="evidence-detail-meta-row"><span>人工方向</span><span>{DIRECTION_LABEL[evidence.direction as keyof typeof DIRECTION_LABEL] ?? evidence.direction ?? '—'}</span></div>
              <div className="evidence-detail-meta-row"><span>证据等级</span><span>{LEVEL_LABEL[evidence.evidence_level as keyof typeof LEVEL_LABEL] ?? evidence.evidence_level ?? '—'}</span></div>
              <div className="evidence-detail-meta-row"><span>模型方向</span><span>{DIRECTION_LABEL[evidence.model_direction as keyof typeof DIRECTION_LABEL] ?? evidence.model_direction ?? '—'}</span></div>
              <div className="evidence-detail-meta-row"><span>人工备注</span><span>{evidence.reviewer_note ?? '—'}</span></div>
              <div className="evidence-detail-meta-row">
                <span>置信度调整</span>
                <span>{evidence.confidence_adjustment_status ?? '—'}{evidence.suggested_confidence != null ? `（建议 ${fmtConfidence(evidence.suggested_confidence)}）` : ''}</span>
              </div>
            </div>
          </section>

          <section className="evidence-detail-section">
            <h5 className="evidence-detail-section-title">证明片段（{passages.length}）</h5>
            {passages.length === 0 && <p className="ew-meta">无片段详情</p>}
            {passages.map(p => (
              <div key={p.id} className="evidence-detail-passage">
                <div className="evidence-detail-passage-meta">
                  <span className={`ew-${p.direction === 'contradicts' ? 'bad' : 'ok'}`}>{DIRECTION_LABEL[p.direction as keyof typeof DIRECTION_LABEL] ?? p.direction}</span>
                  <span className="ew-meta">{p.source_scope}{p.section_title ? ` · ${p.section_title}` : ''}{p.source_locator ? ` · ${p.source_locator}` : ''}</span>
                  {!p.source_verified && <span className="ew-bad">未核验</span>}
                </div>
                <p className="ew-passage-en">{p.passage}</p>
                {p.translation_zh && <p className="ew-passage-zh">{p.translation_zh}</p>}
                {p.reason && <p className="ew-meta">理由：{p.reason}</p>}
              </div>
            ))}
          </section>

          <div className="evidence-detail-actions">
            {!invalidated && (
              <button type="button" className="btn btn-sm btn-danger" onClick={() => setConfirmOpen(true)}>回滚</button>
            )}
          </div>
        </div>
        <ConfirmDialog
          open={confirmOpen}
          title="回滚论文证据"
          message="回滚后该证据将从知识对象移除，置信度将恢复。请填写回滚原因："
          confirmLabel="确认回滚"
          danger
          onConfirm={() => {
            const trimmed = reason.trim()
            if (!trimmed) return
            setConfirmOpen(false)
            setReason('')
            onRollback(trimmed)
          }}
          onCancel={() => setConfirmOpen(false)}
        >
          <textarea
            className="filter-input"
            value={reason}
            onChange={e => setReason(e.target.value)}
            placeholder="回滚原因（必填）"
            rows={3}
          />
        </ConfirmDialog>
      </aside>
    </div>
  )
}
