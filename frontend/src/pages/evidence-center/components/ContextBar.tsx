interface ContextBarProps {
  /** 当前队列对象名称;null 表示未选择 */
  targetLabel: string | null
  targetType: string | null
  granularity: string | null
  confidence: number | null
  evidenceCount: number | null
  taskName: string | null
  /** 当前对象在队列中的下标(0 起);无匹配时为 -1 */
  queueIndex: number
  queueTotal: number
  taskStatus: string | null
  onBackToDataCenter: () => void
  onRefresh: () => void
}

function formatConfidence(v: number | null): string {
  return v == null ? '—' : `${Math.round(v * 100)}%`
}

/** 顶部信息条:当前对象 / 任务 / 队列进度,随 Context 数据实时推导 */
export function ContextBar({
  targetLabel,
  targetType,
  granularity,
  confidence,
  evidenceCount,
  taskName,
  queueIndex,
  queueTotal,
  taskStatus,
  onBackToDataCenter,
  onRefresh,
}: ContextBarProps) {
  const hasQueue = queueTotal > 0
  const progress = hasQueue ? `${Math.max(queueIndex, 0) + 1}/${queueTotal}` : null
  return (
    <div className="evidence-context-bar" data-testid="evidence-context-bar">
      <div className="evidence-context-object">
        <span className="evidence-context-label">{targetLabel ?? '未选择对象'}</span>
        {targetType && <span className="evidence-context-chip">{targetType}</span>}
        {granularity && <span className="evidence-context-chip">粒度 {granularity}</span>}
        {confidence != null && (
          <span className="evidence-context-chip">置信度 {formatConfidence(confidence)}</span>
        )}
        {evidenceCount != null && <span className="evidence-context-chip">{evidenceCount} 条证据</span>}
      </div>
      <div className="evidence-context-progress">
        {hasQueue ? (
          <span className="evidence-context-task">
            {taskName ?? '当前任务'} · 进度 {progress}
          </span>
        ) : (
          <span className="evidence-context-task">等待处理对象</span>
        )}
        {taskStatus && <span className="evidence-context-chip">{taskStatus}</span>}
      </div>
      <div className="evidence-context-actions">
        <button type="button" className="btn btn-sm" onClick={onRefresh}>刷新</button>
        <button type="button" className="btn btn-sm btn-primary" onClick={onBackToDataCenter}>返回数据中心</button>
      </div>
    </div>
  )
}
