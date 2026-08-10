import type { AttachPreviewResponse } from '../../../api/endpoints'
import { clampConfidence, computeConfidenceImpact } from './confidenceImpact'
import type { ReviewStatusRecord } from './ReviewStatusStore'
import type { CoverageSummary, Direction, EvidenceLevel } from './types'
import { DIRECTION_LABEL, LEVEL_HINT, LEVEL_LABEL } from './types'

export interface ReviewerDecisionPanelProps {
  direction: Direction
  modelDirection: Direction | null
  onDirectionChange: (d: Direction) => void
  evidenceLevel: EvidenceLevel
  onEvidenceLevelChange: (l: EvidenceLevel) => void
  confidence: string
  onConfidenceChange: (v: string) => void
  note: string
  onNoteChange: (v: string) => void
  selectedCount: number
  preview: AttachPreviewResponse | null
  previewBusy: boolean
  /** V2-S3 新增(可选,保持兼容):AI 初判区 Coverage(已核验片段支撑组件数/必需组件数) */
  coverage?: CoverageSummary | null
  /** 当前图谱 confidence(置信度影响 Current;preview 可用时以 preview 为准) */
  currentConfidence?: number | null
  /** 当前审核状态(已审核通过/已驳回,面板反馈) */
  reviewStatus?: ReviewStatusRecord | null
  onApprove?: () => void
  onReject?: () => void
}

/** 人工审核决策状态:模块经 Context 推送给右栏,由 RightPanel 渲染本面板 */
export type ReviewDecisionState = ReviewerDecisionPanelProps

const DIRECTIONS: readonly Direction[] = ['supports', 'partial', 'contradicts', 'mixed', 'not_found']

function fmt(n: number | null): string {
  return n == null ? '—' : n.toFixed(2)
}

/** 人工审核决策面板:AI 初判(灰字) + 分隔线「人工最终判断」+ 置信度影响 + sticky [驳回证据][审核通过]。只完成审核,不调 attach。 */
export function ReviewerDecisionPanel({
  direction,
  modelDirection,
  onDirectionChange,
  evidenceLevel,
  onEvidenceLevelChange,
  confidence,
  onConfidenceChange,
  note,
  onNoteChange,
  selectedCount,
  preview,
  previewBusy,
  coverage = null,
  currentConfidence = null,
  reviewStatus = null,
  onApprove,
  onReject,
}: ReviewerDecisionPanelProps) {
  // reviewer 钳制 [0,1] 后再入公式(与后端 confidence_rules 一致)
  const reviewer = clampConfidence(parseFloat(confidence) || 0)
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
    <div className="ew-right-inner" data-testid="ew-reviewer-panel">
      <h4>人工审核</h4>

      <div className="ew-ai-section" data-testid="ew-ai-section">
        <div className="ew-ai-line">
          <span className="ew-ai-label">AI 初判</span>
          <span className="ew-ai-recommend" data-testid="ew-ai-direction">
            {modelDirection ? DIRECTION_LABEL[modelDirection] : '—'}
          </span>
        </div>
        {coverage && coverage.required_components.length > 0 && (
          <div className="ew-ai-line">
            <span className="ew-ai-label">Coverage</span>
            <span className="ew-ai-recommend" data-testid="ew-ai-coverage">
              {coverage.supported_components.length}/{coverage.required_components.length}
            </span>
          </div>
        )}
      </div>

      <div className="ew-divider">人工最终判断</div>

      <div className="ew-field">
        <label className="ew-dir-label">人工方向</label>
        <div className="ew-dir-radios">
          {DIRECTIONS.map(d => (
            <label key={d} className={`ew-dir-chip${direction === d ? ' ew-dir-chip-active' : ''}`}>
              <input type="radio" name="dir" value={d} checked={direction === d} onChange={() => onDirectionChange(d)} />
              {DIRECTION_LABEL[d]}
            </label>
          ))}
        </div>
      </div>

      <div className="ew-field">
        <label>证据等级</label>
        <select className="filter-select" value={evidenceLevel} title={LEVEL_HINT[evidenceLevel]}
          onChange={e => onEvidenceLevelChange(e.target.value as EvidenceLevel)}>
          {(['direct', 'indirect', 'interpretive', 'background'] as const).map(l => (
            <option key={l} value={l}>{LEVEL_LABEL[l]}</option>
          ))}
        </select>
      </div>

      <div className="ew-field">
        <label>Reviewer Confidence（0–0.85）</label>
        <input type="range" min={0} max={0.85} step={0.01} value={Math.min(0.85, reviewer)}
          onChange={e => onConfidenceChange(e.target.value)} />
        <input className="filter-input" value={confidence} onChange={e => onConfidenceChange(e.target.value)} />
        <span className="ew-meta">DeepSeek semantic confidence 仅供参考，不是图谱 confidence。</span>
      </div>

      <div className="ew-field">
        <label>Reviewer Note</label>
        <textarea className="filter-input" value={note} onChange={e => onNoteChange(e.target.value)} placeholder="为什么接受/调整方向/修改组件等（可选）" />
      </div>

      <div className="ew-field">
        <label>已选片段</label>
        <span className="ew-meta">{selectedCount} 段（仅统计通过原文校验的片段）</span>
      </div>

      {previewBusy && <div className="ew-busy">正在计算置信度预览…</div>}
      {direction === 'not_found' && <div className="ew-bad">不能作为正式论文佐证入库</div>}
      {(direction === 'contradicts' || direction === 'mixed') && (
        <div className="ew-bad">不会自动修改当前置信度，将进入验证中心待复核</div>
      )}

      <div className="ew-field">
        <label>置信度影响</label>
        <div className="ew-impact-grid">
          <div className="ew-impact-cell">
            <span className="ew-impact-key">Current</span>
            <span className="ew-impact-val" data-testid="ew-impact-current">{fmt(impact.current)}</span>
          </div>
          <div className="ew-impact-cell">
            <span className="ew-impact-key">Reviewer</span>
            <span className="ew-impact-val" data-testid="ew-impact-reviewer">{fmt(impact.reviewer)}</span>
          </div>
          <div className="ew-impact-cell">
            <span className="ew-impact-key">Rule</span>
            <span className="ew-impact-val" data-testid="ew-impact-rule">
              {impact.cap != null ? `≤${fmt(impact.cap)}` : '—'}
            </span>
          </div>
          <div className="ew-impact-cell">
            <span className="ew-impact-key">Final</span>
            <span className="ew-impact-val ew-impact-final" data-testid="ew-impact-final">{fmt(impact.final)}</span>
          </div>
        </div>
      </div>

      {reviewStatus && (
        <div className={reviewStatus.status === 'review_approved' ? 'ew-ok' : 'ew-bad'} data-testid="ew-review-status">
          {reviewStatus.status === 'review_approved' ? '已审核通过' : '已驳回'} · {DIRECTION_LABEL[reviewStatus.meta.direction]} · 置信度 {reviewStatus.meta.confidence}
        </div>
      )}

      <div className="ew-sticky-actions">
        <button type="button" className="btn btn-sm" onClick={onReject} data-testid="ew-reject-btn">驳回证据</button>
        <button
          type="button"
          className="btn btn-sm btn-primary"
          disabled={selectedCount === 0}
          title={selectedCount === 0 ? '请先勾选已核验的候选片段' : '审核通过'}
          onClick={onApprove}
          data-testid="ew-approve-btn"
        >
          审核通过
        </button>
      </div>
    </div>
  )
}
