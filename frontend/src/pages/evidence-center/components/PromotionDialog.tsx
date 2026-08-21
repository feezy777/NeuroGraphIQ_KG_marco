import type { AttachPreviewResponse } from '../../../api/endpoints'
import type { ClaimComponent, Direction, WorkbenchPassage } from './types'
import { COMPONENT_LABEL, DIRECTION_LABEL } from './types'

interface PaperMeta {
  title?: string | null
  pmid?: string | null
  doi?: string | null
}

interface Props {
  open: boolean
  targetLabel: string
  claimText: string
  paper: PaperMeta
  passages: WorkbenchPassage[]
  components: ClaimComponent[]
  direction: Direction
  preview: AttachPreviewResponse | null
  busy: boolean
  onConfirm: () => void
  onClose: () => void
}

export function PromotionDialog({ open, targetLabel, claimText, paper, passages, components, direction, preview, busy, onConfirm, onClose }: Props) {
  if (!open) return null
  return (
    <div className="ontology-modal-overlay" onClick={onClose}>
      <div className="ontology-modal" onClick={e => e.stopPropagation()} data-testid="ew-attach-dialog">
        <div className="ontology-modal-header">
          <span className="ontology-card-title">确认论文证据</span>
          <button type="button" className="btn btn-xs" onClick={onClose}>关闭</button>
        </div>
        <div className="ontology-modal-body">
          <div className="ontology-detail-row"><span>当前对象</span><strong>{targetLabel}</strong></div>
          <div className="ontology-detail-row"><span>Claim</span><span>{claimText}</span></div>
          <div className="ontology-detail-row"><span>论文</span><strong>{paper.title ?? '—'}</strong></div>
          <div className="ontology-detail-row"><span>PMID / DOI</span><span>{paper.pmid ?? '—'} / {paper.doi ?? '—'}</span></div>
          <div className="ontology-detail-row"><span>所选 Passage</span><span>{passages.length} 段</span></div>
          <div className="ontology-detail-row"><span>Reviewer 方向</span><span>{DIRECTION_LABEL[direction]}</span></div>
          <div className="ontology-detail-row"><span>置信度</span><span>{preview?.current_confidence ?? '—'} → {preview?.final_confidence ?? '—'}（上限 {preview?.cap ?? '—'}）</span></div>
          <div className="ontology-detail-row"><span>验证状态</span><span>{passages.every(p => p.source_verified) ? '所有片段均已核验原文' : '存在未核验片段'}</span></div>
          <details open>
            <summary>每段证明的 Component</summary>
            {passages.map((p, i) => (
              <p key={p.hash} className="ew-meta">
                {i + 1}. {p.direction === 'contradicts' ? '反驳' : '佐证'}：
                {(p.supported_components || []).map(c => COMPONENT_LABEL[c] ?? c).join('、') || '—'} — {p.passage.slice(0, 120)}{p.passage.length > 120 ? '…' : ''}
              </p>
            ))}
          </details>
          {preview && !preview.allow && (
            <div className="ew-bad" style={{ margin: '8px 0', padding: 8, background: '#fff3cd', borderRadius: 4 }}>
              <strong>⚠ 拦截原因：</strong>
              {preview.block_reasons.map((r, i) => <div key={i}>• {r}</div>)}
              <p className="ew-meta" style={{ marginTop: 4 }}>若确认原文无误，可继续强制入库（证据仍会记录，但需人工复核原文匹配）。</p>
            </div>
          )}
          {preview?.allow && (
            <p className="ew-meta">确认后将创建正式论文证据，并更新当前知识对象置信度。所有操作可在证据记录中追溯并可回滚。</p>
          )}
          <div className="ontology-modal-actions">
            <button type="button" data-testid="ew-confirm-attach" className="btn btn-sm btn-primary"
              disabled={busy} onClick={onConfirm}>
              {preview?.allow ? '确认入库' : '强制入库（跳过验证）'}
            </button>
            <button type="button" className="btn btn-sm" onClick={onClose}>取消</button>
          </div>
        </div>
      </div>
    </div>
  )
}
