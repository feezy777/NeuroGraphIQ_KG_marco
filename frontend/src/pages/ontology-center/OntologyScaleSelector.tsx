import {
  BIOLOGICAL_LAYER_SCALES,
  BRAIN_REGION_SCALES,
  type OntologyScaleKey,
  type OntologyScaleOption,
} from './ontologyScale'

type OntologyScaleSelectorProps = {
  /** 当前尺度；由 OntologyBrowser 持有并同步 URL hash（oc_scale） */
  value: OntologyScaleKey
  onChange: (scale: OntologyScaleKey) => void
  /** compact = 顶栏横向单行（右上角粒度透镜）；缺省 = 左侧纵向列表 */
  variant?: 'vertical' | 'compact'
}

type ScaleOptionProps = {
  option: OntologyScaleOption
  isActive: boolean
  onSelect: (scale: OntologyScaleKey) => void
}

function ScaleOption({ option, isActive, onSelect }: ScaleOptionProps) {
  return (
    <button
      type="button"
      role="radio"
      aria-checked={isActive}
      title={option.hint}
      className={`oc-scale-option ${isActive ? 'oc-scale-option-active' : ''}`}
      onClick={() => onSelect(option.key)}
    >
      <span className="oc-scale-dot" aria-hidden="true" />
      {option.label}
    </button>
  )
}

/**
 * Ontology Scale Selector：受控两组 radio
 * （Brain Region: Macro/Clinical/Meso/Subregion/Fine +
 *   Biological Layer: Cyto/Molecular）。
 * 单 selection 语义 → 外层一个 radiogroup，组名仅作视觉分区。
 */
export function OntologyScaleSelector({ value, onChange, variant = 'vertical' }: OntologyScaleSelectorProps) {
  return (
    <div
      className={`oc-scale-selector ${variant === 'compact' ? 'oc-scale-selector--compact' : ''}`}
      role="radiogroup"
      aria-label="Ontology scale"
    >
      <span className="oc-scale-selector-label">Scale</span>
      <div className="oc-scale-group">
        <span className="oc-scale-group-label">Brain Region</span>
        {BRAIN_REGION_SCALES.map(option => (
          <ScaleOption
            key={option.key}
            option={option}
            isActive={value === option.key}
            onSelect={onChange}
          />
        ))}
      </div>
      <div className="oc-scale-group">
        <span className="oc-scale-group-label">Biological Layer</span>
        {BIOLOGICAL_LAYER_SCALES.map(option => (
          <ScaleOption
            key={option.key}
            option={option}
            isActive={value === option.key}
            onSelect={onChange}
          />
        ))}
      </div>
    </div>
  )
}
