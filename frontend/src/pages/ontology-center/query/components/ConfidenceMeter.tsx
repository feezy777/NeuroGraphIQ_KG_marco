/** 紧凑置信度指示器：细条 + 百分比（置信度 null 时不渲染） */
export function ConfidenceMeter({ value }: { value: number | null }) {
  if (value == null) return null
  const pct = Math.round(value * 100)
  const tone = pct >= 80 ? 'high' : pct >= 60 ? 'mid' : 'low'
  return (
    <span className={`oq-confidence oq-confidence-${tone}`} title={`置信度 ${pct}%`}>
      <span className="oq-confidence-bar">
        <span className="oq-confidence-fill" style={{ width: `${pct}%` }} />
      </span>
      <span className="oq-confidence-value">{pct}%</span>
    </span>
  )
}
