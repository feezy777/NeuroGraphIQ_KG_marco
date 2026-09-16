/**
 * BrainRegion Workspace (Phase 1B).
 *
 * One canonical Gate7B BrainRegion is the operational root of knowledge
 * production. Entering this route already means the BrainRegion is selected,
 * so selection is NOT a workflow step here.
 *
 * Overview holds the region's own fields; Discovery holds the run history and,
 * once a run is selected, its result summary; Candidates holds the region's
 * candidate pool and links out to one candidate's own page. No workflow step is
 * active and no count is fabricated: an unread value shows `—`.
 * (See docs/KNOWLEDGE_PRODUCTION_ARCHITECTURE.md §8.)
 */
import { useEffect, useState } from 'react'
import { useI18n } from '../../i18n-context'
import { WorkflowSteps } from './WorkflowSteps'
import { isCandidateStorageUnavailable } from './candidateTypes'
import {
  fetchBrainRegionLlmCandidates,
  fetchBrainRegionSeed,
  fetchDiscoveryRuns,
} from './kpApi'
import { KP_INDEX_PATH, kpCandidatePath, navigate } from './routes'
import {
  DISCOVERY_STATUS_LABEL_KEYS,
  brainRegionNames,
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

/**
 * NCBI Taxonomy: 9606 is Homo sapiens. Unknown taxons render raw.
 *
 * The taxon ID is a scientific identifier and never translated; only the
 * common-name word is localized.
 */
function formatSpecies(
  taxon: string | null,
  t: (key: string) => string,
): string | null {
  if (!taxon) return null
  return taxon === '9606'
    ? `${t('knowledgeProduction.species.human')} (NCBI:9606)`
    : `NCBI:${taxon}`
}

/**
 * The value shown when something is UNKNOWN — a request in flight, or one that
 * failed. Deliberately not `0`: a zero is a measurement, and showing one for a
 * value nobody read would state as fact something we do not know.
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
 *
 * The decision uses the RAW enum (`runs[0].status`); only the rendered text is
 * translated.
 */
function discoveryValue(
  runs: DiscoveryRun[] | null,
  error: string | null,
  t: (key: string) => string,
): string {
  if (error || runs === null) return NO_DATA
  if (runs.length === 0) return t('knowledgeProduction.status.notInitialized')
  return t(DISCOVERY_STATUS_LABEL_KEYS[runs[0].status])
}

function WorkspaceSummary({
  discovery,
  candidates,
  candidatesNote,
}: {
  discovery: string
  /**
   * The BrainRegion's candidate pool size, or `null` while it is unknown.
   *
   * `—` and `0` are different answers and both are honest: `—` means the pool
   * could not be read, `0` means it was read and is empty. Showing `—` next to a
   * pool that actually holds candidates is the one thing this card must not do —
   * it reads as "nothing was found".
   */
  candidates: number | null
  /**
   * Why the pool is unknown, when the reason is known and worth saying.
   *
   * An unknown value is not always an unexplained one: on a database without
   * candidate storage the `—` has a definite cause, and stating it turns a
   * silence into an answer. Still `—` for the value itself — the count was not
   * measured, so no number may appear.
   */
  candidatesNote?: string
}) {
  const { t } = useI18n()
  const cells = [
    { key: 'discovery', labelKey: 'knowledgeProduction.summary.discovery', value: discovery },
    {
      key: 'candidates',
      labelKey: 'knowledgeProduction.summary.candidates',
      value: candidates === null ? NO_DATA : String(candidates),
      note: candidatesNote,
    },
    // Evidence and review have no read API wired yet, so they remain unknown —
    // NOT zero, which would claim this region has none.
    { key: 'evidence', labelKey: 'knowledgeProduction.summary.evidence', value: NO_DATA },
    { key: 'review', labelKey: 'knowledgeProduction.summary.review', value: NO_DATA },
  ]
  return (
    <section className="kp-summary-row" data-testid="kp-workspace-summary">
      {cells.map(c => (
        <div className="kp-summary-card" key={c.key} data-testid={`kp-ws-summary-${c.key}`}>
          <span className="kp-summary-label">{t(c.labelKey)}</span>
          {/* A MEASURED count (the candidate pool) or an em dash where nothing
              is known — never a zero standing in for "we did not look". */}
          <span className="kp-summary-value kp-summary-value--muted">{c.value}</span>
          {c.note && (
            <span className="kp-summary-note" data-testid={`kp-ws-summary-${c.key}-note`}>
              {c.note}
            </span>
          )}
        </div>
      ))}
    </section>
  )
}

export function BrainRegionWorkspacePage({ entityId }: { entityId: string }) {
  const { language, t } = useI18n()
  const [detail, setDetail] = useState<BrainRegionSeedDetail | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [tab, setTab] = useState<WorkspaceTabId>('overview')
  // Discovery Runs: null = not yet known, [] = known to be empty.
  const [runs, setRuns] = useState<DiscoveryRun[] | null>(null)
  const [runsError, setRunsError] = useState<string | null>(null)
  // Bumped when a run has been started, so the history is refetched from the
  // backend (P0-4B). A counter rather than a copy of the new run: the history
  // stays the BACKEND's list, and nothing here splices a locally built row in.
  const [runsRefreshToken, setRunsRefreshToken] = useState(0)
  // null = the pool could not be read; a number is a MEASURED count.
  const [candidateTotal, setCandidateTotal] = useState<number | null>(null)
  // This database has no candidate storage: the `—` above has a stated cause.
  const [candidateStorageNotEnabled, setCandidateStorageNotEnabled] = useState(false)

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

  // The candidate pool size, from the SAME region-scoped endpoint the Candidate
  // Knowledge tab reads. Only the number is taken: the pool itself stays that
  // tab's business. A failed read stays `null` (unknown), never 0.
  useEffect(() => {
    let cancelled = false
    setCandidateTotal(null)
    setCandidateStorageNotEnabled(false)
    fetchBrainRegionLlmCandidates(entityId)
      .then(res => {
        if (!cancelled) setCandidateTotal(res.total)
      })
      .catch((e: unknown) => {
        // Unknown, not empty: the summary keeps showing —. Only the readiness
        // code additionally explains WHY, because that cause is knowable and
        // fixed; any other failure keeps the dash unexplained rather than
        // guessing at a reason.
        if (cancelled) return
        setCandidateTotal(null)
        setCandidateStorageNotEnabled(isCandidateStorageUnavailable(e))
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
  }, [entityId, runsRefreshToken])

  // Metadata chips: raw identifiers (granularity enum, hemisphere, NCBI taxon,
  // canonical atlas names) stay language-neutral; only "Human" is localized.
  const chips = detail
    ? [
        detail.granularity_level,
        detail.hemisphere,
        formatSpecies(detail.species_taxon_id, t),
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
        ← {t('knowledgeProduction.back')}
      </button>

      <header className="kp-ws-header">
        {loading && <p className="kp-muted">{t('knowledgeProduction.loading')}</p>}
        {error && (
          <div className="state-box state-err" data-testid="kp-workspace-error">
            <p>{error}</p>
          </div>
        )}
        {detail && (
          <>
            {/* Hierarchy is locale-aware (§10): the active language leads as
                the H1, the other name stays as its secondary gloss. entity_id
                remains the stable machine key in its own mono line. */}
            <h1 className="kp-ws-name" data-testid="kp-ws-name">
              {brainRegionNames(detail, language).primary}
            </h1>
            {brainRegionNames(detail, language).secondary && (
              <p className="kp-ws-name-zh">{brainRegionNames(detail, language).secondary}</p>
            )}
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

      <WorkspaceSummary
        discovery={discoveryValue(runs, runsError, t)}
        candidates={candidateTotal}
        candidatesNote={
          candidateStorageNotEnabled
            ? t('knowledgeProduction.candidateStorage.notEnabled')
            : undefined
        }
      />

      <div className="kp-workflow">
        {/* Phase 1B: no Discovery Run exists, so no step is active or completed. */}
        <WorkflowSteps steps={WORKSPACE_WORKFLOW_STEPS} currentStepId={null} />
      </div>

      <div className="tabs kp-tabs" role="tablist" data-testid="kp-tabs">
        {WORKSPACE_TABS.map(tabDef => (
          <button
            key={tabDef.id}
            type="button"
            role="tab"
            aria-selected={tab === tabDef.id}
            className={`tab-btn${tab === tabDef.id ? ' active' : ''}`}
            data-testid={`kp-tab-${tabDef.id}`}
            onClick={() => setTab(tabDef.id)}
          >
            {t(tabDef.labelKey)}
          </button>
        ))}
      </div>

      <section className="kp-tab-panel" role="tabpanel" data-testid={`kp-panel-${tab}`}>
        {tab === 'overview' &&
          (detail ? (
            <OverviewTab detail={detail} />
          ) : (
            <div className="state-box" data-testid="kp-overview-pending">
              <p>
                {loading
                  ? t('knowledgeProduction.loading')
                  : t('knowledgeProduction.notFound')}
              </p>
            </div>
          ))}
        {tab === 'discovery' && (
          <DiscoveryTab
            entityId={entityId}
            runs={runs}
            error={runsError}
            onRunsChanged={() => setRunsRefreshToken(v => v + 1)}
            onOpenCandidates={() => setTab('candidates')}
          />
        )}
        {tab === 'candidates' && (
          <CandidatesTab
            entityId={entityId}
            // A circuit opens its OWN page — the pool never expands a detail
            // underneath itself, and the detail page re-reads everything from
            // the URL so a refresh recovers the same view.
            onOpenCircuit={candidateId => navigate(kpCandidatePath(entityId, candidateId))}
          />
        )}
        {tab === 'evidence' && <EvidenceTab />}
        {tab === 'canonicalization' && <CanonicalizationTab />}
        {tab === 'validation' && <ValidationTab />}
        {tab === 'history' && <HistoryTab />}
      </section>
    </div>
  )
}
