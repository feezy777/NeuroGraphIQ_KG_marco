interface Props {
  score: number
  showLabel?: boolean
}

function scoreColor(s: number): string {
  if (s >= 80) return '#52c41a'
  if (s >= 60) return '#faad14'
  if (s >= 40) return '#ff7a45'
  return '#ff4d4f'
}

function scoreBgc(s: number): string {
  if (s >= 80) return '#f6ffed'
  if (s >= 60) return '#fffbe6'
  if (s >= 40) return '#fff2e8'
  return '#fff2f0'
}

export function QualityScoreBadge({ score, showLabel = false }: Props) {
  const sc = Math.round(score)
  const color = scoreColor(sc)
  const bgc = scoreBgc(sc)
  return (
    <span
      title={`数据质量分: ${sc}/100`}
      style={{
        display: 'inline-flex', alignItems: 'center', gap: 4,
        padding: '1px 8px', borderRadius: 10, fontSize: 11, fontWeight: 600,
        background: bgc, color, border: `1px solid ${color}44`,
      }}
    >
      {showLabel && <span style={{ opacity: 0.7 }}>质量</span>}
      {sc}
    </span>
  )
}
