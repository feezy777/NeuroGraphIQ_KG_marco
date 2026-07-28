import { useI18n } from '../../../i18n-context'

interface Props { granularityLevel?: string }

export function ValidationHumanReviewPanel({ granularityLevel }: Props) {
  const { t } = useI18n()
  return (
    <div className="vw-panel">
      <h3>{t('validationCenter.humanReview') || 'Human Review'}</h3>
      <p>Human review panel for circuit validation.</p>
    </div>
  )
}
