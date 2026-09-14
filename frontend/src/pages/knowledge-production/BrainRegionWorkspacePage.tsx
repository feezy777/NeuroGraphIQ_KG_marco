/**
 * BrainRegion Workspace (Phase 1B).
 *
 * One canonical Gate7B BrainRegion is the operational root of knowledge
 * production. Entering this route already means the BrainRegion is selected,
 * so selection is NOT a workflow step here.
 *
 * Phase 1B: only Overview holds real data. No Discovery Run table exists, so
 * no workflow step is active and no production count is fabricated.
 * (See docs/KNOWLEDGE_PRODUCTION_ARCHITECTURE.md §8.)
 */
import { useEffect, useState } from 'react'
import { WorkflowSteps } from './WorkflowSteps'
import { fetchBrainRegionSeed, fetchDiscoveryRuns } from './kpApi'
import { KP_INDEX_PATH, navigate } from './routes'
import {
  DISCOVERY_STATUS_LABELS,
  WORKSPACE_TABS,
  WORKSPACE_WORKFLOW_STEPS,
  type BrainRegionSeedDetail,
  type DiscoveryRun,
  type WorkspaceTabId,
} from './types'
import {
  CandidatesTab,
  CanonicalizationTab,
  DiscoveryTab,
  EvidenceTab,
  HistoryTab,
  OverviewTab,
  ValidationTab,
} from './workspaceTabs'

/** NCBI Taxonomy: 9606 is Homo sapiens. Unknown taxons render raw. */
function formatSpecies(taxon: string | null): string | null {
  if (!taxon) return null
  return taxon === '9606' ? 'Human (NCBI:9606)' : `NCBI:${taxon}`
}

/**
 * Phase 1B placeholder — replaced by Discovery Run / Candidate APIs in later
 * phases. `—` is used deliberately instead of `0`, because no production-layer
 * table exists yet and a zero would read as an authoritative count.
 */
const NO_DATA = '—'

/**
 * Discovery cell value, derived ONLY from persisted runs.
 *
 *   unknown (loading / request failed) -> —          (we do not know)
 *   loaded, no runs                    -> Not initialized
 *   loaded, runs exist                 -> latest run's status
 *
 * `—` is deliberate while the request is in flight: claiming
 * "Not initialized" before the answer arrives would be a fabricated fact.
 */
function discoveryValue(runs: DiscoveryRun[] | null, error: string | null): string {
  if (error || runs === null) return NO_DATA
  if (runs.length === 0) return 'Not initialized'
  return DISCOVERY_STATUS_LABELS[runs[0].status]
}

function WorkspaceSummary({ discovery }: { discovery: string }) {
  const cells = [
    { key: 'discovery', label: 'Discovery', value: discovery },
    { key: 'candidates', label: 'Candidates', value: NO_DATA },
    { key: 'evidence', label: 'Evidence', value: NO_DATA },
    { key: 'review', label: 'Review', value: NO_DATA },
  ]
  return (
    <section className="kp-summary-row" data-testid="kp-workspace-summary">
      {cells.map(c => (
        <div className="kp-summary-card" key={c.key} data-testid={`kp-ws-summary-${c.key}`}>
          <span className="kp-summary-label">{c.label}</span>
          {/* No count exists yet for any of these: a status word or an em dash,
              never a number that would read as an authoritative count. */}
          <span className="kp-summary-value kp-summary-value--muted">{c.value}</span>
        </div>
      ))}
    </section>
  )
}

export function BrainRegionWorkspacePage({ entityId }: { entityId: string }) {
  const [detail, setDetail] = useState<BrainRegionSeedDetail | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [tab, setTab] = useState<WorkspaceTabId>('overview')
  // Discovery Runs: null = not yet known, [] = known to be empty.
  const [runs, setRuns] = useState<DiscoveryRun[] | null>(null)
  const [runsError, setRunsError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    setDetail(null)
    fetchBrainRegionSeed(entityId)
      .then(d => {
        if (!cancelled) setDetail(d)
      })
      .catch((e: unknown) => {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e))
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [entityId])

  // Read-only run history for this BrainRegion (newest first).
  useEffect(() => {
    let cancelled = false
    setRuns(null)
    setRunsError(null)
    fetchDiscoveryRuns(entityId)
      .then(res => {
        if (!cancelled) setRuns(res.items)
      })
      .catch((e: unknown) => {
        // Keep `runs` null: an unreadable history is unknown, not empty.
        if (!cancelled) setRunsError(e instanceof Error ? e.message : String(e))
      })
    return () => {
      cancelled = true
    }
  }, [entityId])

  const chips = detail
    ? [
        detail.granularity_level,
        detail.hemisphere,
        formatSpecies(detail.species_taxon_id),
        detail.atlas_names.join(', ') || null,
      ].filter((c): c is string => Boolean(c))
    : []

  return (
    <div className="page kp-page" data-testid="brain-region-workspace">
      <button
        type="button"
        className="kp-back"
        data-testid="kp-back-to-index"
        onClick={() => navigate(KP_INDEX_PATH)}
      >
        ← Back to Brain Regions
      </button>

      <header className="kp-ws-header">
        {loading && <p className="kp-muted">载入中…</p>}
        {error && (
          <div className="state-box state-err" data-testid="kp-workspace-error">
            <p>{error}</p>
          </div>
        )}
        {detail && (
          <>
            {/* Hierarchy: English name is the primary identity, the Chinese
                name is its gloss, entity_id is the stable machine key. */}
            <h1 className="kp-ws-name" data-testid="kp-ws-name">
              {detail.name_en ?? detail.entity_id}
            </h1>
            {detail.name_zh && <p className="kp-ws-name-zh">{detail.name_zh}</p>}
            <p className="kp-ws-id" data-testid="kp-ws-entity-id">
              {detail.entity_id}
            </p>
            <div className="kp-badge-row" data-testid="kp-ws-chips">
              {chips.map(c => (
                <span
                  className={`kp-chip${c === detail.granularity_level ? ' kp-chip--accent' : ''}`}
                  key={c}
                >
                  {c}
                </span>
              ))}
            </div>
          </>
        )}
      </header>

      <WorkspaceSummary discovery={discoveryValue(runs, runsError)} />

      <div className="kp-workflow">
        {/* Phase 1B: no Discovery Run exists, so no step is active or completed. */}
        <WorkflowSteps steps={WORKSPACE_WORKFLOW_STEPS} currentStepId={null} />
      </div>

      <div className="tabs kp-tabs" role="tablist" data-testid="kp-tabs">
        {WORKSPACE_TABS.map(t => (
          <button
            key={t.id}
            type="button"
            role="tab"
            aria-selected={tab === t.id}
            className={`tab-btn${tab === t.id ? ' active' : ''}`}
            data-testid={`kp-tab-${t.id}`}
            onClick={() => setTab(t.id)}
          >
            {t.label}
          </button>
        ))}
      </div>

      <section className="kp-tab-panel" role="tabpanel" data-testid={`kp-panel-${tab}`}>
        {tab === 'overview' &&
          (detail ? (
            <OverviewTab detail={detail} />
          ) : (
            <div className="state-box" data-testid="kp-overview-pending">
              <p>{loading ? '载入中…' : '未找到该脑区。'}</p>
            </div>
          ))}
        {tab === 'discovery' && <DiscoveryTab runs={runs} error={runsError} />}
        {tab === 'candidates' && <CandidatesTab />}
        {tab === 'evidence' && <EvidenceTab />}
        {tab === 'canonicalization' && <CanonicalizationTab />}
        {tab === 'validation' && <ValidationTab />}
        {tab === 'history' && <HistoryTab />}
      </section>
    </div>
  )
}
