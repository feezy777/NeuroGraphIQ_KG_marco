/** 紧凑指标卡（Query Summary 的 Entity / Intent / Results / Confidence 复用） */
export function QueryMetricCard({
  label,
  value,
  sub,
  icon,
  tone = 'blue',
  mono = false,
  onClick,
}: {
  label: string
  value: string
  sub?: string
  icon?: React.ReactNode
  tone?: 'blue' | 'green' | 'orange' | 'gray'
  /** value 用等宽字体（如 code） */
  mono?: boolean
  onClick?: () => void
}) {
  const clickable = Boolean(onClick)
  return (
    <div
      className={`oqd-metric oqd-metric-${tone}${clickable ? ' oqd-metric-clickable' : ''}`}
      role={clickable ? 'button' : undefined}
      tabIndex={clickable ? 0 : undefined}
      onClick={onClick}
      onKeyDown={onClick ? e => e.key === 'Enter' && onClick() : undefined}
      title={clickable ? '点击查看本体详情' : undefined}
    >
      <span className="oqd-metric-label">{label}</span>
      <span className="oqd-metric-value-row">
        {icon && <span className="oqd-metric-icon">{icon}</span>}
        <span className={`oqd-metric-value${mono ? ' oqd-mono' : ''}`} title={value}>
          {value}
        </span>
      </span>
      {sub && <span className="oqd-metric-sub">{sub}</span>}
    </div>
  )
}
