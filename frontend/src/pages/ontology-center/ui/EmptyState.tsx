/** 空状态：标题 + 原因（不显示无解释的「暂无数据」） */
export function EmptyState({
  title = 'No canonical relation available',
  reason,
}: {
  title?: string
  reason?: string
}) {
  return (
    <div className="oc-empty-state">
      <span className="oc-empty-state-title">{title}</span>
      {reason && <span className="oc-empty-state-reason">{reason}</span>}
    </div>
  )
}
