import type { ReactNode } from 'react'

interface Props {
  /** 空态图标(通常为 lucide 图标元素);缺省不渲染图标区域 */
  icon?: ReactNode
  title: string
  description?: string
  actionLabel?: string
  onAction?: () => void
}

/** 统一空态:图标 + 标题 + 说明 + 可选操作按钮(证据中心各模块共用) */
export function EmptyState({ icon, title, description, actionLabel, onAction }: Props) {
  return (
    <div className="evidence-empty" data-testid="evidence-empty">
      {icon != null && <div className="evidence-empty-icon">{icon}</div>}
      <div className="evidence-empty-title">{title}</div>
      {description && <div className="evidence-empty-desc">{description}</div>}
      {actionLabel && onAction && (
        <button type="button" className="btn btn-sm" onClick={onAction}>
          {actionLabel}
        </button>
      )}
    </div>
  )
}
