import { useI18n } from '../../i18n-context'
import type { ValidationCenterTabId } from './validationCenterTypes'

const TAB_KEYS: Record<ValidationCenterTabId, string> = {
  overview: 'validationCenter.overview',
  'rule-validation': 'validationCenter.ruleValidation',
  'human-review': 'validationCenter.humanReview',
  promotion: 'validationCenter.promotion',
  mirror: 'validationCenter.mirror',
  macro: 'validationCenter.macro',
  final: 'validationCenter.final',
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
