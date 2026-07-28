import { useI18n } from '../../i18n-context'
import type { ValidationCenterTabId } from './validationCenterTypes'

const TAB_KEYS: Record<ValidationCenterTabId, string> = {
  overview: 'validationCenter.overview',
  rule_check: 'validationCenter.ruleCheck',
  dual_review: 'validationCenter.dualReview',
  review: 'validationCenter.review',
  promotion: 'validationCenter.promotion',
}

interface Props {
  activeTab: ValidationCenterTabId
  onTabChange: (tab: ValidationCenterTabId) => void
}

export function ValidationCenterTabBar({ activeTab, onTabChange }: Props) {
  const { t } = useI18n()
  return (
    <div className="data-center-tabbar">
      {(Object.keys(TAB_KEYS) as ValidationCenterTabId[]).map(tab => (
        <button
          key={tab}
          type="button"
          className={`data-center-tab${activeTab === tab ? ' data-center-tab-active' : ''}`}
          onClick={() => onTabChange(tab)}
        >
          {t(TAB_KEYS[tab])}
        </button>
      ))}
    </div>
  )
}
