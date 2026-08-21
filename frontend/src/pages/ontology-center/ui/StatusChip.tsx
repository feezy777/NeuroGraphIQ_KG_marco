/** 状态 → 语义色调（active 绿 / proposed 黄 / deprecated 灰） */
const STATUS_TONES: Record<string, string> = {
  active: 'green',
  proposed: 'yellow',
  pending: 'yellow',
  draft: 'yellow',
  deprecated: 'gray',
  retired: 'gray',
}

export function StatusChip({ status }: { status?: string | null }) {
  if (!status) return null
  const tone = STATUS_TONES[status] ?? 'neutral'
  return <span className={`oc-status-chip oc-status-chip-${tone}`}>{status}</span>
}
