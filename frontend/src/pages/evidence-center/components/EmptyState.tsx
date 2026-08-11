import type { ReactNode } from 'react'

interface Props {
  /** 空态图标(通常为 lucide 图标元素);缺省不渲染图标区域 */
  icon?: ReactNode
  title: string
  description?: string
  actionLabel?: string
  onAction?: () => void
  /** 紧凑变体(窄栏队列 / 分组内联):轻量虚线卡 */
  compact?: boolean
  /** 根节点 data-testid(缺省 evidence-empty) */
  testId?: string
  /** 操作按钮 data-testid */
  actionTestId?: string
}

/** 统一空态:图标 + 标题 + 说明 + 可选操作按钮(证据中心各模块共用) */
export function EmptyState({ icon, title, description, actionLabel, onAction, compact, testId, actionTestId }: Props) {
  return (
    <div className={`evidence-empty${compact ? ' evidence-empty-compact' : ''}`} data-testid={testId ?? 'evidence-empty'}>
      {icon != null && <div className="evidence-empty-icon">{icon}</div>}
      <div className="evidence-empty-title">{title}</div>
      {description && <div className="evidence-empty-desc">{description}</div>}
      {actionLabel && onAction && (
        <button type="button" className="btn btn-sm" data-testid={actionTestId} onClick={onAction}>
          {actionLabel}
        </button>
      )}
    </div>
  )
}
