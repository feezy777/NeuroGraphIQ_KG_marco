/**
 * Knowledge Production Workspace — Phase 1 foundation.
 *
 * Phase 1 scope: read-only BrainRegion seed selection from the Gate7B authority
 * database plus visible-but-disabled Discovery placeholders. No discovery,
 * candidate persistence, canonicalization, validation or promotion is
 * implemented, and none is faked here.
 *
 * A discovery status is intentionally NOT modelled: there is no Discovery Run
 * table yet, so the page shows a frontend-only "未初始化" label that is never
 * persisted and never presented as scientific state.
 */
import { useEffect, useState } from 'react'
import { BrainRegionSeedList } from './BrainRegionSeedList'
import { WorkflowSteps } from './WorkflowSteps'
import { fetchBrainRegionSeed } from './kpApi'
import type { BrainRegionSeed, BrainRegionSeedDetail, WorkflowStepDef } from './types'
import './knowledge-production.css'

const WORKFLOW_STEPS: WorkflowStepDef[] = [
  { id: 'select-region', label: '选择脑区' },
  { id: 'discover', label: '发现' },
  { id: 'canonicalize', label: '归一化' },
  { id: 'validate', label: '验证' },
  { id: 'promote', label: '晋升' },
]

const WORKSPACE_TABS = [
  { id: 'overview', label: 'Overview' },
  { id: 'circuits', label: 'Circuits' },
  { id: 'connections', label: 'Connections' },
  { id: 'functions', label: 'Functions' },
  { id: 'evidence', label: 'Evidence' },
  { id: 'canonicalization', label: 'Canonicalization' },
  { id: 'validation', label: 'Validation' },
] as const

type TabId = (typeof WORKSPACE_TABS)[number]['id']

function Field({ label, value }: { label: string; value: string | number | null }) {
  return (
    <div className="kp-field">
      <span className="kp-field-label">{label}</span>
      <span className="kp-field-value">{value === null || value === '' ? '—' : value}</span>
    </div>
  )
}

function OverviewTab({ seed }: { seed: BrainRegionSeed | null }) {
  const [detail, setDetail] = useState<BrainRegionSeedDetail | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!seed) {
      setDetail(null)
      return
    }
    let cancelled = false
    setError(null)
    fetchBrainRegionSeed(seed.entity_id)
      .then(d => {
        if (!cancelled) setDetail(d)
      })
      .catch((e: unknown) => {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e))
      })
    return () => {
      cancelled = true
    }
  }, [seed])

  if (!seed) {
    return (
      <div className="state-box" data-testid="kp-no-selection">
        <p>请从左侧选择一个脑区作为发现种子。</p>
      </div>
    )
  }

  if (error) {
    return (
      <div className="state-box state-err" data-testid="kp-overview-error">
        <p>{error}</p>
      </div>
    )
  }

  const view = detail ?? seed
  return (
    <div className="kp-overview" data-testid="kp-overview">
      <Field label="entity_id" value={view.entity_id} />
      <Field label="名称 (EN)" value={view.name_en} />
      <Field label="名称 (ZH)" value={view.name_zh} />
      <Field label="粒度" value={view.granularity_level} />
      <Field label="区域类别" value={view.region_category} />
      <Field label="半球" value={view.hemisphere} />
      <Field label="物种 (NCBI taxon)" value={view.species_taxon_id} />
      <Field label="记录状态" value={view.record_status} />
      <Field label="审核状态" value={view.review_status} />
      <Field label="来源 Atlas" value={view.atlas_names.join(', ') || null} />
      {detail && <Field label="层级深度" value={detail.hierarchy_depth} />}
      {detail && (
        <Field label="外部区域映射" value={detail.external_region_ids.join(', ') || null} />
      )}
      {detail && <Field label="映射类型" value={detail.mapping_types.join(', ') || null} />}
    </div>
  )
}

export function KnowledgeProductionPage() {
  const [seed, setSeed] = useState<BrainRegionSeed | null>(null)
  const [tab, setTab] = useState<TabId>('overview')

  // Phase 1: nothing is ever "running". Selecting a seed COMPLETES step 1 and
  // explicitly does NOT activate step 2 (Discover), because Discovery is not
  // implemented — showing Discover as active would imply it is executing.
  const currentStepId = seed ? null : 'select-region'
  const completedThroughId = seed ? 'select-region' : null
  // Frontend-only placeholder. Never persisted, never returned by the API.
  const discoveryPlaceholder = seed ? '未初始化' : '—'

  return (
    <div className="page kp-page" data-testid="knowledge-production-page">
      <header className="kp-header">
        <div>
          <h1 className="kp-title">知识生产</h1>
          <p className="kp-subtitle">
            脑区知识生产工作台 · Phase 1（只读基础） · 权威库 neurographiq_human_brain_v1
          </p>
        </div>
        <WorkflowSteps
          steps={WORKFLOW_STEPS}
          currentStepId={currentStepId}
          completedThroughId={completedThroughId}
        />
      </header>

      <div className="kp-discovery-actions">
        <button
          type="button"
          className="btn btn-sm"
          disabled
          title="后续阶段开放"
          data-testid="kp-llm-discovery"
        >
          LLM Discovery
        </button>
        <button
          type="button"
          className="btn btn-sm"
          disabled
          title="后续阶段开放"
          data-testid="kp-literature-discovery"
        >
          Literature Discovery
        </button>
        <span className="kp-discovery-state" data-testid="kp-discovery-state">
          发现状态：{discoveryPlaceholder}
        </span>
      </div>

      <div className="kp-body">
        <BrainRegionSeedList selectedId={seed?.entity_id ?? null} onSelect={setSeed} />

        <section className="kp-workspace" data-testid="kp-workspace">
          <div className="kp-tabs" role="tablist" data-testid="kp-tabs">
            {WORKSPACE_TABS.map(t => (
              <button
                key={t.id}
                type="button"
                role="tab"
                aria-selected={tab === t.id}
                className={`kp-tab${tab === t.id ? ' active' : ''}`}
                data-testid={`kp-tab-${t.id}`}
                onClick={() => setTab(t.id)}
              >
                {t.label}
              </button>
            ))}
          </div>

          <div className="kp-tab-panel" role="tabpanel" data-testid={`kp-panel-${tab}`}>
            {tab === 'overview' ? (
              <OverviewTab seed={seed} />
            ) : (
              <div className="state-box" data-testid={`kp-empty-${tab}`}>
                <p>Phase 1 未实现发现功能。</p>
              </div>
            )}
          </div>
        </section>
      </div>
    </div>
  )
}
