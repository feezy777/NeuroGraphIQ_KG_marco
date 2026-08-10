import type { AttachPreviewResponse } from '../../../api/endpoints'
import { ConfidencePreview } from './ConfidencePreview'
import type { Direction, EvidenceLevel } from './types'
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
}

const DIRECTIONS: readonly Direction[] = ['supports', 'partial', 'contradicts', 'mixed', 'not_found']

/** 人工审核决策区(从旧 ReviewerPanel 拆出):AI 推荐灰字 + 人工方向独立高亮 + ConfidencePreview */
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
}: ReviewerDecisionPanelProps) {
  return (
    <div className="ew-right-inner" data-testid="ew-reviewer-panel">
      <h4>人工审核</h4>
      <div className="ew-field">
        <label className="ew-dir-label">
          人工方向
          {modelDirection && (
            <span className="ew-ai-recommend" data-testid="ew-ai-recommend">
              AI 推荐：{DIRECTION_LABEL[modelDirection]}
            </span>
          )}
        </label>
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
        <label>整篇证据等级</label>
        <select className="filter-select" value={evidenceLevel} title={LEVEL_HINT[evidenceLevel]}
          onChange={e => onEvidenceLevelChange(e.target.value as EvidenceLevel)}>
          {(['direct', 'indirect', 'interpretive', 'background'] as const).map(l => (
            <option key={l} value={l}>{LEVEL_LABEL[l]}</option>
          ))}
        </select>
      </div>
      <div className="ew-field">
        <label>Reviewer Confidence（0–0.85）</label>
        <input type="range" min={0} max={0.85} step={0.01} value={Math.min(0.85, parseFloat(confidence) || 0)}
          onChange={e => onConfidenceChange(e.target.value)} />
        <input className="filter-input" value={confidence} onChange={e => onConfidenceChange(e.target.value)} />
        <span className="ew-meta">DeepSeek semantic confidence 仅供参考，不是图谱 confidence。</span>
      </div>
      <div className="ew-field">
        <label>人工备注</label>
        <textarea className="filter-input" value={note} onChange={e => onNoteChange(e.target.value)} placeholder="为什么接受/调整方向/修改组件等（可选）" />
      </div>
      <div className="ew-field"><label>已选片段</label><span className="ew-meta">{selectedCount} 段（仅统计通过原文校验的片段）</span></div>
      {previewBusy && <div className="ew-busy">正在计算置信度预览…</div>}
      {direction === 'not_found' && <div className="ew-bad">不能作为正式论文佐证入库</div>}
      {(direction === 'contradicts' || direction === 'mixed') && (
        <div className="ew-bad">不会自动修改当前置信度，将进入验证中心待复核</div>
      )}
      {direction !== 'not_found' && direction !== 'contradicts' && direction !== 'mixed' && (
        <ConfidencePreview preview={preview} />
      )}
    </div>
  )
}
