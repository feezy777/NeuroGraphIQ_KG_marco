import type { AttachPreviewResponse } from '../../../api/endpoints'
import { clampConfidence, computeConfidenceImpact } from './confidenceImpact'
import type { Direction } from './types'
import { DIRECTION_LABEL } from './types'

/** 晋升影响右栏:模块经 Context 推送给 RightPanel 渲染(与 S3 reviewDecision 同模式) */
export interface PromotionImpactProps {
  /** 人工审核方向(公式/方向标签用) */
  direction: Direction
  /** KG 当前置信度(preview 不可用时的兜底;preview 可用时以 preview.current_confidence 为准) */
  currentConfidence: number | null
  /** 人工 reviewer 置信度(钳制 [0,1] 后入公式) */
  reviewerConfidence: number
  /** 服务端 attach-preview 结果,可用时优先 */
  preview?: AttachPreviewResponse | null
  previewBusy?: boolean
  /** 晋升后 Evidence 新增数(单次晋升恒为 1) */
  evidenceNewCount: number
  /** 晋升后 Passages 新增数(所选已核验片段数) */
  passagesNewCount: number
  /** 晋升后证据状态 */
  statusLabel?: string
  /** 是否可晋升(有草稿且有已核验片段);false 时「确认晋升」禁用 */
  canPromote?: boolean
  /** 退回人工审核:清除审核状态,跳转人工审核模块 */
  onReturnToReview?: () => void
  /** 确认晋升:唯一 attach 入口 */
  onPromote?: () => void
}

export type PromotionImpactState = PromotionImpactProps

function fmt(n: number | null): string {
  return n == null ? '—' : n.toFixed(2)
}

/** 证据晋升右栏:KG 当前 / 晋升后 / Evidence 新增 / Passages 新增 / 状态 + sticky [退回人工审核] [确认晋升] */
export function PromotionImpact({
  direction,
  currentConfidence,
  reviewerConfidence,
  preview = null,
  previewBusy = false,
  evidenceNewCount,
  passagesNewCount,
  statusLabel = 'human_verified',
  canPromote = false,
  onReturnToReview,
  onPromote,
}: PromotionImpactProps) {
  // reviewer 钳制 [0,1] 后再入公式(与后端 confidence_rules 一致)
  const reviewer = clampConfidence(reviewerConfidence)
  // 置信度影响:preview 可用时以服务端 attach-preview 结果为准,否则本地按方向公式计算
  const impact = preview
    ? {
        current: preview.current_confidence,
        reviewer: preview.reviewer_confidence,
        cap: preview.cap,
        final: preview.final_confidence,
      }
    : computeConfidenceImpact(direction, currentConfidence, reviewer)

  return (
    <div className="ew-right-inner evidence-promotion-impact" data-testid="evidence-promotion-impact">
      <h4>晋升影响</h4>

      <div className="ew-promo-field">
        <span className="ew-promo-key">人工方向</span>
        <span className="ew-promo-val">{DIRECTION_LABEL[direction]}</span>
      </div>
      <div className="ew-promo-field">
        <span className="ew-promo-key">KG 当前置信度</span>
        <span className="ew-promo-val" data-testid="pi-current">{fmt(impact.current)}</span>
      </div>
      <div className="ew-promo-field">
        <span className="ew-promo-key">晋升后置信度</span>
        <span className="ew-promo-val ew-promo-final" data-testid="pi-final">{fmt(impact.final)}</span>
        {impact.cap != null && <span className="ew-meta">上限 {fmt(impact.cap)}</span>}
      </div>
      <div className="ew-promo-field">
        <span className="ew-promo-key">Evidence 新增</span>
        <span className="ew-promo-val" data-testid="pi-evidence-new">+{evidenceNewCount}</span>
      </div>
      <div className="ew-promo-field">
        <span className="ew-promo-key">Passages 新增</span>
        <span className="ew-promo-val" data-testid="pi-passages-new">+{passagesNewCount}</span>
      </div>
      <div className="ew-promo-field">
        <span className="ew-promo-key">晋升后状态</span>
        <span className="ew-promo-val ew-ok" data-testid="pi-status">{statusLabel}</span>
      </div>

      {previewBusy && <div className="ew-busy">正在计算置信度预览…</div>}
      {!canPromote && <p className="ew-meta">该对象缺少可晋升的审核草稿或已核验片段，确认已禁用。</p>}

      <div className="ew-sticky-actions">
        <button type="button" className="btn btn-sm" data-testid="pi-return-btn" onClick={onReturnToReview}>
          退回人工审核
        </button>
        <button type="button" className="btn btn-sm btn-primary" data-testid="pi-promote-btn" disabled={!canPromote} onClick={onPromote}>
          确认晋升
        </button>
      </div>
    </div>
  )
}
