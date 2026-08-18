import React from 'react'
import { ArrowLeft, Lock } from 'lucide-react'
import { useI18n } from '../i18n-context'

interface PageHeaderProps {
  title: string
  description?: string
  actions?: React.ReactNode
  readonly?: boolean
  /** 显示返回箭头并回到上一页面(如验证中心顶部) */
  onBack?: () => void
}

export function PageHeader({ title, description, actions, readonly: ro = true, onBack }: PageHeaderProps) {
  const { t } = useI18n()

  return (
    <div className="page-header">
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, minWidth: 0 }}>
        {onBack && (
          <button
            type="button"
            className="btn btn-sm page-header-back"
            data-testid="page-header-back"
            aria-label="返回上一页"
            onClick={onBack}
          >
            <ArrowLeft size={14} />
          </button>
        )}
        <div style={{ minWidth: 0 }}>
          <h1 className="page-title">{title}</h1>
          {description && <p className="page-desc">{description}</p>}
        </div>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        {ro && (
          <span className="readonly-notice">
            <Lock size={10} />
            {t('common.readonly')}
          </span>
        )}
        {actions}
      </div>
    </div>
  )
}
