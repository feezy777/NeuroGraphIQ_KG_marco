import { useCallback, useEffect, useMemo, useState } from 'react'
import { PageHeader } from '../../components/PageHeader'
import { useI18n } from '../../i18n-context'
import { readHashQueryParams, buildHashUrl } from '../../utils/pipelineNavigation'
import { useGlobalGranularity } from '../../hooks/useGlobalGranularity'
import { ValidationCenterTabBar } from './ValidationCenterTabBar'
import { ValidationCenterOverview } from './ValidationCenterOverview'
import { MirrorKgPanel } from '../data-center/MirrorKgPanel'
import { MacroClinicalDataPanel } from '../data-center/MacroClinicalDataPanel'
import { FinalKgDataPanel } from '../data-center/FinalKgDataPanel'
import { ValidationRulePanel } from './panels/ValidationRulePanel'
import { ValidationReviewPanel } from './panels/ValidationReviewPanel'
import { ValidationPromotionPanel } from './panels/ValidationPromotionPanel'
import type {
  ValidationCenterNavState,
  ValidationCenterTabId,
  MirrorKgSubTab,
  MacroClinicalSubTab,
  FinalKgSubTab,
} from './validationCenterTypes'
import { VALIDATION_CENTER_TABS, DEFAULT_NAV } from './validationCenterTypes'

function parseNavFromUrl(): ValidationCenterNavState {
  const q = readHashQueryParams()
  const tab = VALIDATION_CENTER_TABS.includes(q.tab as ValidationCenterTabId)
    ? (q.tab as ValidationCenterTabId) : DEFAULT_NAV.tab
  return {
    tab,
    mirrorTab: (['connections', 'functions', 'circuits', 'triples', 'evidence'].includes(q.mirrorTab)
      ? q.mirrorTab : DEFAULT_NAV.mirrorTab) as MirrorKgSubTab,
    macroTab: (['circuit_steps', 'projection_functions', 'memberships', 'circuit_functions', 'cross_validation', 'dual_model'].includes(q.macroTab)
      ? q.macroTab : DEFAULT_NAV.macroTab) as MacroClinicalSubTab,
    finalTab: (['circuit', 'circuit_step', 'projection', 'projection_function', 'membership', 'region_function', 'circuit_function', 'triple', 'evidence'].includes(q.finalTab)
      ? q.finalTab : DEFAULT_NAV.finalTab) as FinalKgSubTab,
    batchId: q.batch_id ?? '',
    resourceId: q.resource_id ?? '',
    sourceAtlas: q.source_atlas ?? '',
    granularityLevel: '',
  }
}

function navToQuery(nav: ValidationCenterNavState): Record<string, string | undefined> {
  return {
    tab: nav.tab === 'overview' ? undefined : nav.tab,
    mirrorTab: nav.tab === 'mirror' ? nav.mirrorTab : undefined,
    macroTab: nav.tab === 'macro' ? nav.macroTab : undefined,
    finalTab: nav.tab === 'final' ? nav.finalTab : undefined,
    batch_id: nav.batchId || undefined,
    resource_id: nav.resourceId || undefined,
    source_atlas: nav.sourceAtlas || undefined,
    granularity_level: readHashQueryParams().granularity_level || undefined,
  }
}

export function ValidationCenterPage() {
  const { t } = useI18n()
  const [nav, setNav] = useState<ValidationCenterNavState>(() => parseNavFromUrl())
  const { granularity } = useGlobalGranularity()

  useEffect(() => {
    const handler = () => setNav(parseNavFromUrl())
    window.addEventListener('hashchange', handler)
    return () => window.removeEventListener('hashchange', handler)
  }, [])

  const updateNav = useCallback((patch: Partial<ValidationCenterNavState>) => {
    setNav(prev => {
      const next = { ...prev, ...patch }
      window.location.hash = buildHashUrl('/validation-center', navToQuery(next))
      return next
    })
  }, [])

  const setTab = useCallback((tab: ValidationCenterTabId) => updateNav({ tab }), [updateNav])

  const workspace = useMemo(() => {
    switch (nav.tab) {
      case 'overview':
        return <ValidationCenterOverview onNavigate={setTab} />
      case 'rule-validation':
        return <ValidationRulePanel granularityLevel={granularity} />
      case 'human-review':
        return <ValidationReviewPanel granularityLevel={granularity} />
      case 'promotion':
        return <ValidationPromotionPanel granularityLevel={granularity} />
      case 'mirror':
        return (
          <MirrorKgPanel
            mirrorTab={nav.mirrorTab}
            onMirrorTabChange={(mirrorTab: MirrorKgSubTab) => updateNav({ tab: 'mirror', mirrorTab })}
            batchId={nav.batchId}
            resourceId={nav.resourceId}
            sourceAtlas={nav.sourceAtlas}
            granularityLevel={granularity}
            onFilterChange={patch => updateNav({
              batchId: patch.batchId ?? nav.batchId,
              resourceId: patch.resourceId ?? nav.resourceId,
              sourceAtlas: patch.sourceAtlas ?? nav.sourceAtlas,
            })}
          />
        )
      case 'macro':
        return (
          <MacroClinicalDataPanel
            macroTab={nav.macroTab}
            onMacroTabChange={(macroTab: MacroClinicalSubTab) => updateNav({ tab: 'macro', macroTab })}
            batchId={nav.batchId}
            resourceId={nav.resourceId}
            sourceAtlas={nav.sourceAtlas}
            granularityLevel={granularity}
            onFilterChange={patch => updateNav({
              batchId: patch.batchId ?? nav.batchId,
              resourceId: patch.resourceId ?? nav.resourceId,
              sourceAtlas: patch.sourceAtlas ?? nav.sourceAtlas,
            })}
          />
        )
      case 'final':
        return (
          <FinalKgDataPanel
            finalTab={nav.finalTab}
            granularityLevel={granularity}
            onFinalTabChange={(finalTab: FinalKgSubTab) => updateNav({ tab: 'final', finalTab })}
          />
        )
      default:
        return <ValidationCenterOverview onNavigate={setTab} />
    }
  }, [nav, granularity, setTab, updateNav])

  return (
    <div className="data-center-page">
      <div className="data-center-header-static">
        <PageHeader title={t('validationCenter.title')} description={t('validationCenter.subtitle')} readonly />
        <ValidationCenterTabBar activeTab={nav.tab} onTabChange={setTab} />
      </div>
      <div className="data-center-workspace">{workspace}</div>
    </div>
  )
}
