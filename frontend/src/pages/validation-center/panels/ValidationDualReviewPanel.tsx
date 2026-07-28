import { useI18n } from '../../../i18n-context'

interface Props { granularityLevel?: string }

export function ValidationDualReviewPanel({ granularityLevel }: Props) {
  const { t } = useI18n()
  return (
    <div className="vw-panel">
      <h3>{t('validationCenter.dualReview') || 'Dual Model Review'}</h3>
      <p>Dual model blind review panel.</p>
    </div>
  )
}
