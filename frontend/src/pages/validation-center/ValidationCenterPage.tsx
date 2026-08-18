import { ArrowLeft } from 'lucide-react'
import { PageHeader } from '../../components/PageHeader'
import { useI18n } from '../../i18n-context'
import { useGlobalGranularity } from '../../hooks/useGlobalGranularity'
import { ValidationWorkbench } from './ValidationWorkbench'

export function ValidationCenterPage() {
  const { t } = useI18n()
  const { granularity } = useGlobalGranularity()
  return (
    <div className="data-center-page validation-center-page">
      {/* 左上顶格返回箭头:绝对定位抵消 .main 顶部 padding,贴页面内容区顶角 */}
      <button
        type="button"
        className="btn btn-sm page-header-back vc-top-back"
        data-testid="vc-top-back"
        aria-label="返回上一页"
        onClick={() => window.history.back()}
      >
        <ArrowLeft size={14} />
      </button>
      <div className="data-center-header-static">
        <PageHeader title={t('validationCenter.title')} description={t('validationCenter.subtitle')} readonly />
      </div>
      <div className="data-center-workspace">
        <ValidationWorkbench granularityLevel={granularity} />
      </div>
    </div>
  )
}
