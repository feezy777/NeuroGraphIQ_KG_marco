import { useCallback, useEffect, useState } from 'react'
import { PageHeader } from '../../components/PageHeader'
import { useGlobalGranularity } from '../../hooks/useGlobalGranularity'
import { OntologyBrowser } from './browser/OntologyBrowser'
import { OntologyGovernance } from './governance/OntologyGovernance'
import { OntologyQueryPage } from './query/OntologyQueryPage'

export type OntologyCenterTab = 'browser' | 'query' | 'governance'

const TABS: Array<{ key: OntologyCenterTab; label: string }> = [
  { key: 'browser', label: '本体浏览' },
  { key: 'query', label: '自然语言查询' },
  { key: 'governance', label: '本体治理' },
]

const VALID_TABS: readonly string[] = TABS.map(t => t.key)
const DEFAULT_TAB: OntologyCenterTab = 'browser'

function getTabFromHash(): OntologyCenterTab {
  const hash = window.location.hash.slice(1)
  const query = hash.split('?')[1] ?? ''
  const tab = new URLSearchParams(query).get('tab')
  return VALID_TABS.includes(tab ?? '') ? (tab as OntologyCenterTab) : DEFAULT_TAB
}

export function OntologyCenterPage() {
  const { granularity } = useGlobalGranularity()
  const [tab, setTab] = useState<OntologyCenterTab>(getTabFromHash)

  // 与 hash query 双向同步（沿用 data-center 的 #/path?tab= 惯例）
  const selectTab = useCallback((next: OntologyCenterTab) => {
    setTab(next)
    window.location.hash = `#/ontology-center?tab=${next}`
  }, [])

  useEffect(() => {
    const onHashChange = () => setTab(getTabFromHash())
    window.addEventListener('hashchange', onHashChange)
    return () => window.removeEventListener('hashchange', onHashChange)
  }, [])

  return (
    <div className="data-center-page">
      <div className="data-center-header-static">
        <PageHeader
          title="本体中心"
          description="Canonical Ontology Center · 脑区 / 连接 / 回路 / 功能本体的浏览与治理"
          readonly
        />
      </div>
      <div className="ontology-page">
        <div className="ontology-page-tabs">
          {TABS.map(({ key, label }) => (
            <button
              key={key}
              type="button"
              className={`ontology-page-tab ${tab === key ? 'ontology-page-tab-active' : ''}`}
              onClick={() => selectTab(key)}
            >
              {label}
            </button>
          ))}
        </div>
        <div
          className={`ontology-page-tab-body ${
            tab === 'browser' ? 'ontology-page-tab-body--browser' : ''
          } ${tab === 'query' ? 'ontology-page-tab-body--query' : ''}`}
        >
          {tab === 'browser' && <OntologyBrowser />}
          {tab === 'query' && <OntologyQueryPage />}
          {tab === 'governance' && <OntologyGovernance granularity={granularity} />}
        </div>
      </div>
    </div>
  )
}
