import { useI18n } from '../../../i18n-context'

interface Props { granularityLevel?: string }

export function ValidationRulePanel({ granularityLevel }: Props) {
  const { t } = useI18n()
  return (
    <div className="vw-panel">
      <h3>{t('validationCenter.ruleCheck') || 'Rule Check'}</h3>
      <p>Circuit rule validation panel.</p>
    </div>
  )
}
