import { PageHeader } from '../../components/PageHeader'
import { useI18n } from '../../i18n-context'
import { useGlobalGranularity } from '../../hooks/useGlobalGranularity'
import { ValidationWorkbench } from './ValidationWorkbench'

export function ValidationCenterPage() {
  const { t } = useI18n()
  const { granularity } = useGlobalGranularity()
  return (
    <div className="data-center-page">
      <div className="data-center-header-static">
        <PageHeader
          title={t('validationCenter.title')}
          description={t('validationCenter.subtitle')}
          readonly
          onBack={() => window.history.back()}
        />
      </div>
      <div className="data-center-workspace">
        <ValidationWorkbench granularityLevel={granularity} />
      </div>
    </div>
  )
}
