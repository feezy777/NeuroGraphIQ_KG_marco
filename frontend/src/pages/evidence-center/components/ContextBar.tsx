import type { ClaimComponent } from './types'

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
  /** 完整事实句(页面从 candidateClaim/queue 合成,如「需要验证:R1 到 R2 存在投射连接」) */
  claimSentence?: string | null
  onBackToDataCenter: () => void
  onRefresh: () => void
}

function formatConfidence(v: number | null): string {
  return v == null ? '—' : `${Math.round(v * 100)}%`
}

/**
 * 从候选事实(claimText + 组件)合成一句完整事实句;无候选事实时回退到队列对象 label。
 * 优先组件拼装(source 到 target + relation + direction),组件不齐时回退完整 claimText。
 */
export function composeClaimSentence(
  claimText: string,
  components: ClaimComponent[],
  fallbackLabel: string | null,
): string | null {
  const byType = new Map(components.map(c => [c.component_type, c.statement]))
  const source = byType.get('source_region')
  const target = byType.get('target_region')
  const relation = byType.get('relation')
  const direction = byType.get('direction')
  if (source && target && relation) {
    const dir = direction ? `(方向性:${direction})` : ''
    return `需要验证:${source} 到 ${target} ${relation}${dir}`
  }
  if (claimText) return `需要验证:${claimText}`
  if (fallbackLabel) return `需要验证:${fallbackLabel}`
  return null
}

/**
 * 顶部信息条:状态 Badge + 完整事实句 + 对象元信息(类型/粒度/置信度/证据数/任务进度),随 Context 数据实时推导。
 * 左侧 [Badge + 事实句],右侧 [刷新][返回数据中心]。
 */
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
  claimSentence = null,
  onBackToDataCenter,
  onRefresh,
}: ContextBarProps) {
  const hasQueue = queueTotal > 0
  const progress = hasQueue ? `${Math.max(queueIndex, 0) + 1}/${queueTotal}` : null
  const badge = taskStatus ?? '等待处理对象'
  return (
    <div className="evidence-context-bar" data-testid="evidence-context-bar">
      <span className="evidence-context-badge">{badge}</span>
      <div className="evidence-context-fact">
        <span className="evidence-context-label">{targetLabel ?? '未选择对象'}</span>
        {claimSentence && <span className="evidence-context-sentence">{claimSentence}</span>}
        <div className="evidence-context-meta">
          {targetType && <span className="evidence-context-chip">{targetType}</span>}
          {granularity && <span className="evidence-context-chip">粒度 {granularity}</span>}
          {confidence != null && (
            <span className="evidence-context-chip">置信度 {formatConfidence(confidence)}</span>
          )}
          {evidenceCount != null && <span className="evidence-context-chip">{evidenceCount} 条证据</span>}
          {taskName && <span className="evidence-context-chip">{taskName}</span>}
          {progress && <span className="evidence-context-chip">进度 {progress}</span>}
        </div>
      </div>
      <div className="evidence-context-actions">
        <button type="button" className="btn btn-sm" onClick={onRefresh}>刷新</button>
        <button type="button" className="btn btn-sm btn-primary" onClick={onBackToDataCenter}>返回数据中心</button>
      </div>
    </div>
  )
}
