import { useCallback, useEffect, useRef, useState } from 'react'

export interface ConfidenceFilter {
  min: number | null
  max: number | null
  includeNull: boolean
}

const PRESETS = [
  { label: '全部', min: null, max: null },
  { label: '≤ 0.20', min: null, max: 0.20 },
  { label: '0.20 – 0.50', min: 0.20, max: 0.50 },
  { label: '0.50 – 0.80', min: 0.50, max: 0.80 },
  { label: '≥ 0.80', min: 0.80, max: null },
]

function formatFilterLabel(f: ConfidenceFilter): string {
  if (f.min == null && f.max == null) return '全部'
  if (f.min == null && f.max != null) return `≤ ${f.max.toFixed(2)}`
  if (f.min != null && f.max == null) return `≥ ${f.min.toFixed(2)}`
  return `${f.min!.toFixed(2)} – ${f.max!.toFixed(2)}`
}

export function isFilterActive(f: ConfidenceFilter): boolean {
  return f.min != null || f.max != null || f.includeNull
}

interface Props {
  filter: ConfidenceFilter
  onChange: (f: ConfidenceFilter) => void
}

export function ConfidenceFilterPopover({ filter, onChange }: Props) {
  const [open, setOpen] = useState(false)
  const [draft, setDraft] = useState<ConfidenceFilter>(filter)
  const [sliderMin, setSliderMin] = useState(filter.min ?? 0)
  const [sliderMax, setSliderMax] = useState(filter.max ?? 1)
  const ref = useRef<HTMLDivElement>(null)

  // Sync draft from current filter when popover opens
  useEffect(() => {
    if (open) {
      setDraft(filter)
      setSliderMin(filter.min ?? 0)
      setSliderMax(filter.max ?? 1)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  // Close on outside click
  useEffect(() => {
    if (!open) return
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [open])

  const applyPreset = useCallback((p: typeof PRESETS[number]) => {
    const next = { min: p.min, max: p.max, includeNull: draft.includeNull }
    setDraft(next)
    setSliderMin(p.min ?? 0)
    setSliderMax(p.max ?? 1)
  }, [draft.includeNull])

  const apply = useCallback(() => {
    onChange(draft)
    setOpen(false)
  }, [draft, onChange])

  const reset = useCallback(() => {
    const empty = { min: null, max: null, includeNull: false }
    setDraft(empty)
    setSliderMin(0)
    setSliderMax(1)
    onChange(empty)
    setOpen(false)
  }, [onChange])

  const clear = useCallback((e: React.MouseEvent) => {
    e.stopPropagation()
    reset()
  }, [reset])

  const active = isFilterActive(filter)

  return (
    <div className="cfp-root" ref={ref}>
      <button
        type="button"
        className={`btn btn-sm cfp-trigger${active ? ' cfp-active' : ''}`}
        onClick={() => setOpen(v => !v)}
      >
        置信度：{formatFilterLabel(filter)}
        {active ? (
          <span className="cfp-clear" onClick={clear}>×</span>
        ) : (
          <span className="cfp-arrow"> ▾</span>
        )}
      </button>

      {open && (
        <div className="cfp-popover">
          <div className="cfp-presets">
            {PRESETS.map(p => (
              <button
                key={p.label}
                type="button"
                className={`cfp-preset-btn${
                  draft.min === p.min && draft.max === p.max ? ' cfp-preset-active' : ''
                }`}
                onClick={() => applyPreset(p)}
              >
                {p.label}
              </button>
            ))}
          </div>

          <div className="cfp-section-label">自定义范围</div>
          <div className="cfp-slider-track">
            {/* Visual track — the ONLY visible track, drawn by divs */}
            <div className="cfp-track-bg" />
            <div
              className="cfp-track-active"
              style={{
                left: `${sliderMin * 100}%`,
                width: `${(sliderMax - sliderMin) * 100}%`,
              }}
            />
            {/* Two transparent range inputs — only thumbs are visible */}
            <input
              type="range"
              className="cfp-range cfp-range-lo"
              min={0}
              max={1}
              step={0.01}
              value={sliderMin}
              onChange={e => {
                const v = parseFloat(e.target.value)
                if (v <= sliderMax) { setSliderMin(v); setDraft(prev => ({ ...prev, min: v })) }
              }}
            />
            <input
              type="range"
              className="cfp-range cfp-range-hi"
              min={0}
              max={1}
              step={0.01}
              value={sliderMax}
              onChange={e => {
                const v = parseFloat(e.target.value)
                if (v >= sliderMin) { setSliderMax(v); setDraft(prev => ({ ...prev, max: v })) }
              }}
            />
          </div>
          <div className="cfp-range-labels">
            <span className="cfp-range-val">{sliderMin.toFixed(2)}</span>
            <span className="cfp-range-val">{sliderMax.toFixed(2)}</span>
          </div>

          <label className="cfp-check">
            <input
              type="checkbox"
              checked={draft.includeNull}
              onChange={e => setDraft(prev => ({ ...prev, includeNull: e.target.checked }))}
            />
            包含未设置置信度的数据
          </label>

          <div className="cfp-actions">
            <button type="button" className="btn btn-sm" onClick={reset}>
              重置
            </button>
            <button type="button" className="btn btn-sm btn-primary" onClick={apply}>
              应用筛选
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
