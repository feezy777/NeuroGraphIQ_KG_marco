import { useState } from 'react'
import { useI18n } from '../../i18n-context'
import { ValidationStatsBar } from './components/ValidationStatsBar'
import { CreateRunModal } from './components/CreateRunModal'
import { ValidationOverviewPanel } from './panels/ValidationOverviewPanel'
import { ValidationRulePanel } from './panels/ValidationRulePanel'
import { ValidationDualReviewPanel } from './panels/ValidationDualReviewPanel'
import { ValidationHumanReviewPanel } from './panels/ValidationHumanReviewPanel'
import type { CircuitValidationRun, ValidationCenterTabId } from './validationCenterTypes'

const TABS: { key: ValidationCenterTabId; label: string }[] = [
  { key: 'overview', label: '总览' },
  { key: 'rule_check', label: '规则校验' },
  { key: 'dual_review', label: '双模型盲审' },
  { key: 'review', label: '人工审核' },
]

interface Props { granularityLevel?: string }
export function ValidationWorkbench({ granularityLevel }: Props) {
  const { t } = useI18n()
  const [activeTab, setActiveTab] = useState<ValidationCenterTabId>('overview')
  const [createModalOpen, setCreateModalOpen] = useState(false)
  const [latestRun, setLatestRun] = useState<CircuitValidationRun | null>(null)

  const handleCreated = (run: CircuitValidationRun) => {
    setLatestRun(run)
    setCreateModalOpen(false)
    setActiveTab('overview')
  }

  const renderPanel = () => {
    switch (activeTab) {
      case 'overview': return <ValidationOverviewPanel granularityLevel={granularityLevel} />
      case 'rule_check': return <ValidationRulePanel granularityLevel={granularityLevel} />
      case 'dual_review': return <ValidationDualReviewPanel granularityLevel={granularityLevel} />
      case 'review': return <ValidationHumanReviewPanel granularityLevel={granularityLevel} />
      default: return <ValidationOverviewPanel granularityLevel={granularityLevel} />
    }
  }

  return (
    <div className="vw-root">
      <ValidationStatsBar granularityLevel={granularityLevel} />
      <div className="vr-header">
        <div className="vr-tabs">
          {TABS.map(table => (
            <button key={table.key} type="button"
              className={`vr-tab${activeTab === table.key ? ' active' : ''}`}
              onClick={() => setActiveTab(table.key)}>{table.label}</button>
          ))}
        </div>
        <div className="vr-header-right">
          <button className="btn btn-sm btn-primary" onClick={() => setCreateModalOpen(true)}>+ 新建验证任务</button>
        </div>
      </div>
      <div style={{ flex: 1, overflow: 'auto' }}>{renderPanel()}</div>
      <CreateRunModal
        open={createModalOpen}
        granularityLevel={granularityLevel}
        onClose={() => setCreateModalOpen(false)}
        onCreated={handleCreated}
      />
      {latestRun && (
        <div style={{ position: 'fixed', bottom: 16, right: 16, background: 'var(--white)', padding: '8px 16px', borderRadius: 'var(--radius-md)', boxShadow: 'var(--shadow-lg)', fontSize: 13, zIndex: 1000, border: '1px solid var(--primary)' }}>
          已创建任务: <code>{latestRun.id.slice(0, 8)}</code> ({latestRun.status})
        </div>
      )}
    </div>
  )
}
