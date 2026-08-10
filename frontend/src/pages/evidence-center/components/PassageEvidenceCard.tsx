import { useState } from 'react'
import type { ClaimComponent, EvidenceLevel, WorkbenchPassage } from './types'
import { COMPONENT_LABEL, DIMENSION_HINT, DIMENSION_LABEL, LEVEL_HINT, LEVEL_LABEL } from './types'

interface Props {
  passage: WorkbenchPassage
  components: ClaimComponent[]
  selected: boolean
  translation: string
  onToggleSelect: (checked: boolean) => void
  onLevelChange: (level: EvidenceLevel) => void
  onComponentToggle: (component: string, checked: boolean) => void
  onTranslationChange: (value: string) => void
  onTranslate: () => void
  onCopy: () => void
  onShowContext: () => void
  showContext: boolean
  onReselect?: (paperPassageId: string, text: string) => Promise<boolean>
}

function VerificationBadge({ passage }: { passage: WorkbenchPassage }) {
  if (!passage.source_verified) {
    return <span className="ew-bad">未通过原文校验，请人工核对或重新截取</span>
  }
  const method =
    passage.source_verification_method === 'exact'
      ? 'Exact'
      : passage.source_verification_method === 'normalized_whitespace'
        ? 'Whitespace normalized'
        : passage.source_verification_method === 'normalized_unicode'
          ? 'Unicode normalized'
          : passage.source_verification_method ?? 'Exact'
  if (passage.source_verification_method === 'similarity' || passage.source_verification_method === 'similarity_located') {
    return <span className="ew-warn" title="近似匹配：与原文存在轻微改写，请人工核对后确认">近似匹配（{method}）· 请核对原文</span>
  }
  return <span className="ew-ok">已核验原文 · {method}</span>
}

export function PassageEvidenceCard({
  passage,
  components,
  selected,
  translation,
  onToggleSelect,
  onLevelChange,
  onComponentToggle,
  onTranslationChange,
  onTranslate,
  onCopy,
  onShowContext,
  showContext,
  onReselect,
}: Props) {
  const allowed = components.map(c => c.component_type)
  const isContradict = passage.direction === 'contradicts'
  const [reselectOpen, setReselectOpen] = useState(false)
  const [reselectText, setReselectText] = useState('')
  return (
    <div className={`ew-passage ${!passage.source_verified ? 'ew-passage-invalid' : ''}`} data-testid="ew-passage">
      <div className="ew-passage-top">
        <label>
          <input type="checkbox" checked={selected} disabled={!passage.source_verified}
            onChange={e => onToggleSelect(e.target.checked)} />
          选择片段
        </label>
        <span className="ew-level-badge">{LEVEL_LABEL[passage.evidence_level]}</span>
        {passage.evidence_dimension && passage.evidence_dimension !== 'mixed' && (
          <span className="ew-dimension-badge" title={DIMENSION_HINT[passage.evidence_dimension]}>
            {DIMENSION_LABEL[passage.evidence_dimension]}
          </span>
        )}
        <span className="ew-passage-direction">{passage.direction}</span>
        <span className="ew-meta">{passage.source_scope}{passage.section_title ? ` · ${passage.section_title}` : ''}{passage.paragraph_index != null ? ` · ¶${passage.paragraph_index}` : ''}</span>
        <VerificationBadge passage={passage} />
      </div>
      <p className="ew-passage-en">{passage.passage}</p>
      {showContext && (
        <details open className="ew-passage-context">
          <summary>展开上下文</summary>
          <p className="ew-meta">focus paragraph: {passage.paragraph_id ?? '—'} · locator: {passage.source_locator ?? '—'}</p>
        </details>
      )}
      {passage.source_verified && (
        <>
          <div className="ontology-form-row">
            <textarea className="filter-input ew-trans" value={translation}
              onChange={e => onTranslationChange(e.target.value)} placeholder="中文翻译（可编辑）" />
            <button type="button" className="btn btn-xs" onClick={onTranslate}>翻译</button>
            <button type="button" className="btn btn-xs" onClick={onCopy}>复制原文</button>
            <button type="button" className="btn btn-xs" onClick={onShowContext}>{showContext ? '收起上下文' : '展开上下文'}</button>
            {passage.paper_passage_id && onReselect && (
              <>
                <button type="button" className="btn btn-xs" onClick={() => setReselectOpen(o => !o)}>重新截取</button>
                {reselectOpen && (
                  <div className="ew-reselect">
                    <textarea className="filter-input ew-trans" value={reselectText} onChange={e => setReselectText(e.target.value)} placeholder="输入更短的真实原文范围（后端校验）" />
                    <button type="button" className="btn btn-xs" disabled={!reselectText.trim()}
                      onClick={async () => {
                        const ok = await onReselect(passage.paper_passage_id!, reselectText.trim())
                        if (ok) { setReselectOpen(false); setReselectText('') }
                      }}>校验并替换</button>
                  </div>
                )}
              </>
            )}
          </div>
          <div className="ew-field">
            <label>证据等级</label>
            <select className="filter-select" value={passage.evidence_level} title={LEVEL_HINT[passage.evidence_level]}
              onChange={e => onLevelChange(e.target.value as EvidenceLevel)}>
              {(['direct', 'indirect', 'interpretive', 'background'] as const).map(l => (
                <option key={l} value={l}>{LEVEL_LABEL[l]} — {LEVEL_HINT[l]}</option>
              ))}
            </select>
          </div>
          <div className="ew-field">
            <label>{isContradict ? '本段反驳' : '本段佐证'}</label>
            <div className="ew-component-grid">
              {allowed.map(comp => {
                const checked = passage.supported_components.includes(comp)
                return (
                  <label key={comp} className={`ew-comp-check${checked ? ' on' : ''}`}>
                    <input type="checkbox" checked={checked}
                      onChange={e => onComponentToggle(comp, e.target.checked)} />
                    {checked ? '✓' : '○'} {COMPONENT_LABEL[comp] ?? comp}
                  </label>
                )
              })}
            </div>
          </div>
        </>
      )}
      {passage.reason && <p className="ew-meta">模型理由：{passage.reason}</p>}
      {passage.semantic_confidence != null && <p className="ew-meta">DeepSeek semantic confidence：{passage.semantic_confidence}（仅供参考）</p>}
    </div>
  )
}
