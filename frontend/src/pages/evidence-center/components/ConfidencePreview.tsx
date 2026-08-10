import type { AttachPreviewResponse } from '../../../api/endpoints'

interface Props {
  preview: AttachPreviewResponse | null
}

/** 置信度预览:current → final + 公式 + cap + block_reasons(从旧 ReviewerPanel 的 ConfidenceRuleText 迁移) */
export function ConfidencePreview({ preview }: Props) {
  if (!preview) return null
  return (
    <div className="ew-preview" data-testid="ew-confidence-preview">
      <h4>置信度预览</h4>
      <div className="ew-preview-flow">
        {preview.current_confidence ?? '—'} → {preview.final_confidence ?? '—'}（上限 {preview.cap ?? '—'}）
      </div>
      <div className="ew-meta">公式：min({preview.cap ?? '—'}, max(当前, 人工推荐))</div>
      <div className="ew-meta">已选片段 {preview.selected_passage_count} · 重复 {preview.duplicate_passage_count}</div>
      {preview.block_reasons.map((r, i) => (
        <div key={i} className="ew-bad">{r}</div>
      ))}
    </div>
  )
}
