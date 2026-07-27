import React from 'react'

export interface ValidationAction {
  key: string
  label: string
  variant: 'primary' | 'danger' | 'default'
  icon: React.ReactNode
  disabled?: boolean
  disabledReason?: string
  onClick: (ids: string[]) => void | Promise<void>
}

interface Props {
  selectedCount: number
  selectedIds: string[]
  actions: ValidationAction[]
  onClearSelection: () => void
}

export function ValidationActionBar({ selectedCount, selectedIds, actions, onClearSelection }: Props) {
  if (selectedCount === 0) return null

  return (
    <div className="validation-action-bar">
      <span className="validation-action-bar-count">
        已选 <strong>{selectedCount}</strong> 项
      </span>
      <button type="button" className="btn btn-ghost btn-sm" onClick={onClearSelection}>
        ✕ 清空
      </button>
      <div className="validation-action-bar-sep" />
      {actions.map(action => (
        <button
          key={action.key}
          type="button"
          className={`btn btn-sm btn-${action.variant}`}
          disabled={action.disabled}
          title={action.disabledReason}
          onClick={() => action.onClick(selectedIds)}
        >
          {action.icon}
          {action.label}
        </button>
      ))}
    </div>
  )
}
