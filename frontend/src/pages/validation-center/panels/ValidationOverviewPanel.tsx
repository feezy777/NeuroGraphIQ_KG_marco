import { useI18n } from '../../../i18n-context'

interface Props { granularityLevel?: string }

export function ValidationOverviewPanel({ granularityLevel }: Props) {
  const { t } = useI18n()
  return (
    <div className="vw-panel">
      <h3>{t('validationCenter.overview') || 'Overview'}</h3>
      <p>Circuit Validation Center overview content.</p>
    </div>
  )
}
