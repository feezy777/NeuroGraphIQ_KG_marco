import type { ClaimComponent, EvidenceLevel, WorkbenchPassage } from './types'
import { COMPONENT_LABEL, LEVEL_HINT, LEVEL_LABEL } from './types'

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
}

function VerificationBadge({ passage }: { passage: WorkbenchPassage }) {
  if (!passage.source_verified) {
    return <span className="ew-bad">无法在论文原文定位</span>
  }
  const method =
    passage.source_verification_method === 'exact'
      ? 'Exact'
      : passage.source_verification_method === 'normalized_whitespace'
        ? 'Whitespace normalized'
        : passage.source_verification_method === 'normalized_unicode'
          ? 'Unicode normalized'
          : passage.source_verification_method ?? 'Exact'
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
}: Props) {
  const allowed = components.map(c => c.component_type)
  const isContradict = passage.direction === 'contradicts'
  return (
    <div className={`ew-passage ${!passage.source_verified ? 'ew-passage-invalid' : ''}`} data-testid="ew-passage">
      <div className="ew-passage-top">
        <label>
          <input type="checkbox" checked={selected} disabled={!passage.source_verified}
            onChange={e => onToggleSelect(e.target.checked)} />
          选择片段
        </label>
        <span className="ew-level-badge">{LEVEL_LABEL[passage.evidence_level]}</span>
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
