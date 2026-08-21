import { useEffect, useState } from 'react'
import { getOntologyRole } from '../../../api/endpoints'
import { FunctionsGovernance } from './FunctionsGovernance'
import { GovernanceOverview, type GovernanceSubTab } from './GovernanceOverview'
import { RegionsGovernance } from './RegionsGovernance'
import { RelationsGovernance } from './RelationsGovernance'

/**
 * 本体治理工作台（由旧 OntologyCenterPage 迁移而来）：
 * 功能术语治理、未锚定处理、脑区对齐审核、词汇注册表、审计日志。
 */
export function OntologyGovernance({ granularity }: { granularity: string }) {
  const [tab, setTab] = useState<GovernanceSubTab>('functions')
  const [role, setRole] = useState<'viewer' | 'reviewer' | 'ontology_admin'>('viewer')

  useEffect(() => {
    getOntologyRole().then(r => setRole(r.role)).catch(() => setRole('viewer'))
  }, [])

  return (
    <div className="ontology-page">
      <div className="ontology-page-tabs">
        {(
          [
            ['functions', '功能'],
            ['regions', '实体'],
            ['relations', '关系'],
          ] as Array<[GovernanceSubTab, string]>
        ).map(([key, label]) => (
          <button
            key={key}
            type="button"
            className={`ontology-page-tab ${tab === key ? 'ontology-page-tab-active' : ''}`}
            onClick={() => setTab(key)}
          >
            {label}
          </button>
        ))}
        <span className="ontology-page-granularity">当前颗粒度：{granularity}</span>
      </div>
      <GovernanceOverview granularity={granularity} onNavigate={setTab} />
      <div className="ontology-page-tab-body">
        {tab === 'functions' && <FunctionsGovernance granularity={granularity} role={role} />}
        {tab === 'regions' && <RegionsGovernance granularity={granularity} role={role} />}
        {tab === 'relations' && <RelationsGovernance granularity={granularity} role={role} />}
      </div>
    </div>
  )
}
