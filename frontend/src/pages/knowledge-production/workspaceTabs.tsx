/**
 * BrainRegion Workspace tab bodies (Phase 1B/1C, extended by later phases).
 *
 * Overview, Discovery and Candidates-by-run hold real Gate7B data: Overview the
 * region's own fields, Discovery the persisted run history plus — once a run is
 * selected — its publications (literature route) or its proposed candidates
 * (LLM route). The remaining tabs are explicit, data-free placeholders
 * describing what will live there — no counts, no rows, no fake statuses. See
 * docs/KNOWLEDGE_PRODUCTION_ARCHITECTURE.md §8 and the visual contract in §12.
 */
import { useEffect, useState, type ReactNode } from 'react'
import { useI18n } from '../../i18n-context'
import { ApiError } from '../../api/client'
import { formatApiErrorMessage } from '../../utils/apiErrorMessage'
import { DataTable, type Column } from '../../components/DataTable'
import { executeLlmDiscovery, fetchLiteratureRuns } from './kpApi'
import { LiteratureInspector } from './LiteratureInspector'
import { LlmCandidateList } from './LlmCandidateList'
import {
  DISCOVERY_STATUS_LABEL_KEYS,
  DISCOVERY_STATUS_TONES,
  isLiteratureDiscoveryType,
  isLlmDiscoveryType,
  type BrainRegionSeedDetail,
  type DiscoveryRun,
  type DiscoveryRunOutcome,
  type LiteratureRun,
} from './types'

/** `key` is stable (never translated) so React keys survive a language switch. */
interface FieldDef {
  key: string
  label: string
  value: string | number | null
}

function Field({ label, value }: { label: string; value: string | number | null }) {
  return (
    <div className="kp-field">
      <span className="kp-field-label">{label}</span>
      <span className="kp-field-value">{value === null || value === '' ? '—' : value}</span>
    </div>
  )
}

function FieldSection({ title, fields }: { title: string; fields: FieldDef[] }) {
  const shown = fields.filter(f => f.value !== null && f.value !== '')
  // a section with nothing authoritative to show is omitted rather than padded
  if (shown.length === 0) return null
  return (
    <section className="kp-section">
      <h3 className="kp-section-title">{title}</h3>
      <div className="kp-field-grid">
        {shown.map(f => (
          <Field key={f.key} label={f.label} value={f.value} />
        ))}
      </div>
    </section>
  )
}

export function OverviewTab({ detail }: { detail: BrainRegionSeedDetail }) {
  const { t } = useI18n()
  const f = (name: string) => t(`knowledgeProduction.field.${name}`)
  return (
    <div className="kp-overview" data-testid="kp-overview">
      <FieldSection
        title={t('knowledgeProduction.section.identity')}
        fields={[
          // Labels are localized; the VALUES stay raw Gate7B identifiers.
          { key: 'entity_id', label: 'entity_id', value: detail.entity_id },
          { key: 'name_en', label: f('nameEn'), value: detail.name_en },
          { key: 'name_zh', label: f('nameZh'), value: detail.name_zh },
          { key: 'abbreviation', label: f('abbreviation'), value: detail.abbreviation },
        ]}
      />
      <FieldSection
        title={t('knowledgeProduction.section.anatomy')}
        fields={[
          { key: 'granularity', label: f('granularity'), value: detail.granularity_level },
          { key: 'region_category', label: f('regionCategory'), value: detail.region_category },
          { key: 'hemisphere', label: f('hemisphere'), value: detail.hemisphere },
          { key: 'species', label: f('species'), value: detail.species_taxon_id },
        ]}
      />
      <FieldSection
        title={t('knowledgeProduction.section.hierarchy')}
        fields={[
          // only identifiers the API actually exposes — no invented labels
          { key: 'parent_region', label: f('parentRegion'), value: detail.parent_region_pk },
          { key: 'hierarchy_depth', label: f('hierarchyDepth'), value: detail.hierarchy_depth },
        ]}
      />
      <FieldSection
        title={t('knowledgeProduction.section.sourceMapping')}
        fields={[
          { key: 'atlas', label: f('sourceAtlas'), value: detail.atlas_names.join(', ') || null },
          {
            key: 'external_region',
            label: f('externalRegion'),
            value: detail.external_region_ids.join(', ') || null,
          },
          {
            key: 'mapping_type',
            label: f('mappingType'),
            value: detail.mapping_types.join(', ') || null,
          },
          {
            key: 'mapping_review',
            label: f('mappingReview'),
            value: detail.mapping_review_statuses.join(', ') || null,
          },
        ]}
      />
      <FieldSection
        title={t('knowledgeProduction.section.governance')}
        fields={[
          // DB field names stay literal: they are the column names themselves.
          { key: 'record_status', label: 'record_status', value: detail.record_status },
          { key: 'review_status', label: 'review_status', value: detail.review_status },
        ]}
      />
    </div>
  )
}

/**
 * Shared shape for a tab that has no Phase 1 data: what the tab is for, why it
 * is empty right now, and what will eventually appear in it. Deliberately
 * explanatory — never a bare "not implemented".
 */
function TabPlaceholder({
  icon,
  title,
  description,
  blockTitle,
  children,
}: {
  icon: string
  title: string
  description: string
  blockTitle: string
  children: ReactNode
}) {
  return (
    <div className="kp-empty">
      <span className="kp-empty-icon" aria-hidden="true">
        {icon}
      </span>
      <h3 className="kp-empty-title">{title}</h3>
      <p className="kp-empty-text">{description}</p>
      <div className="kp-empty-block">
        <p className="kp-empty-block-title">{blockTitle}</p>
        {children}
      </div>
    </div>
  )
}

/** Future contents rendered as a bullet list. */
function FutureList({ items }: { items: string[] }) {
  return (
    <ul className="kp-list">
      {items.map(item => (
        <li key={item}>{item}</li>
      ))}
    </ul>
  )
}

/**
 * A failed launch attempt, kept as the backend stated it.
 *
 * `code` is the machine-readable reason (the backend's frozen vocabulary) and
 * `message` its own bounded prose — never a raw response body. `runId` is
 * present when the failure happened AFTER a run was created, which is the
 * difference between "nothing happened" and "a run failed and is inspectable".
 */
interface LaunchFailure {
  code: string | null
  message: string
  runId: string | null
}

/**
 * i18n key for the headline of a launch failure.
 *
 * The headline states WHICH failure it is; the backend's message below it says
 * what happened. The cases are deliberately not merged into one "failed"
 * message: "this BrainRegion does not exist", "a run is already active" and
 * "the model run failed" call for three different user actions.
 */
const LAUNCH_FAILURE_HEADLINES: Record<string, string> = {
  NOT_FOUND: 'knowledgeProduction.execution.error.brainRegionNotFound',
  ACTIVE_RUN_EXISTS: 'knowledgeProduction.execution.error.activeRun',
}

function launchFailureHeadlineKey(code: string | null): string {
  if (code && LAUNCH_FAILURE_HEADLINES[code]) return LAUNCH_FAILURE_HEADLINES[code]
  // The model-run failures all share one headline; their distinct codes and the
  // backend's message are still shown, so nothing is lost by grouping them.
  if (code && code.startsWith('LLM_')) return 'knowledgeProduction.execution.error.modelRunFailed'
  return 'knowledgeProduction.execution.error.generic'
}

/** Read a launch failure out of whatever the API client threw. */
function readLaunchFailure(e: unknown): LaunchFailure {
  const detail = e instanceof ApiError
    ? (e.meta?.responseBody as { detail?: { code?: string; run_id?: string } } | undefined)?.detail
    : undefined
  return {
    code: detail?.code ?? null,
    runId: detail?.run_id ?? null,
    // Extracts the structured `detail.message` rather than stringifying the
    // body, so the user reads prose instead of JSON.
    message: formatApiErrorMessage(e),
  }
}

/**
 * One discovery operation.
 *
 * A route is LIVE only when it is given an `action`. Without one the button is
 * disabled and explains why — an enabled button that does nothing would be a
 * worse lie than a disabled one, and a disabled button with no explanation is
 * just broken. Nothing here decides WHICH routes are live: the caller passes an
 * action or it does not, so literature stays a placeholder until it has a real
 * execution path.
 */
function DiscoveryCard({
  glyph,
  title,
  description,
  produces,
  buttonLabel,
  testId,
  action,
  busy = false,
  busyLabel,
  liveHint,
}: {
  glyph: string
  title: string
  description: string
  produces: string[]
  buttonLabel: string
  testId: string
  /** Present when this route can actually be started. */
  action?: () => void
  busy?: boolean
  busyLabel?: string
  /** Shown instead of the placeholder hint once the route is live. */
  liveHint?: string
}) {
  const { t } = useI18n()
  const live = Boolean(action)
  return (
    <div className="kp-card kp-op-card">
      <h3 className="kp-card-title">
        <span className="kp-card-glyph" aria-hidden="true">
          {glyph}
        </span>
        {title}
      </h3>
      <p className="kp-card-text">{description}</p>
      <div className="kp-op-meta">
        {produces.map(p => (
          <span className="kp-chip" key={p}>
            {p}
          </span>
        ))}
      </div>
      <button
        type="button"
        className="btn btn-sm"
        // Disabled while an attempt is in flight as well as when there is no
        // execution path: a second click would be a second run.
        disabled={!live || busy}
        title={live ? undefined : t('knowledgeProduction.discovery.executionTooltip')}
        onClick={action}
        data-testid={testId}
      >
        {busy && busyLabel ? busyLabel : buttonLabel}
      </button>
      {live ? (
        liveHint && <p className="kp-card-hint">{liveHint}</p>
      ) : (
        <p className="kp-card-hint">{t('knowledgeProduction.discovery.executionHint')}</p>
      )}
    </div>
  )
}

/**
 * Display-only i18n keys for the frozen outcome vocabulary. Never persisted,
 * and never compared: logic always compares the raw enum value.
 */
const OUTCOME_LABEL_KEYS: Record<DiscoveryRunOutcome, string> = {
  CANDIDATES_FOUND: 'knowledgeProduction.outcome.CANDIDATES_FOUND',
  NO_CANDIDATES_FOUND: 'knowledgeProduction.outcome.NO_CANDIDATES_FOUND',
  NO_EVIDENCE_FOUND: 'knowledgeProduction.outcome.NO_EVIDENCE_FOUND',
}

/** `YYYY-MM-DD HH:mm` in local time, or `—` when the run has no such stamp. */
function formatTimestamp(value: string | null): string {
  if (!value) return '—'
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return '—'
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}

function StatusBadge({ status }: { status: DiscoveryRun['status'] }) {
  const { t } = useI18n()
  // The badge tone keys off the RAW enum; only the caption is translated.
  return (
    <span className={`badge ${DISCOVERY_STATUS_TONES[status]}`}>
      {t(DISCOVERY_STATUS_LABEL_KEYS[status])}
    </span>
  )
}

/**
 * Read-only run history. No candidate counts, no evidence counts.
 *
 * Every row is SELECTABLE, because the tab now has a panel for each route:
 * literature runs open the publication inspector, LLM runs open the candidate
 * list (Phase P0-4A). Which panel answers a click is decided by the ROUTE of the
 * run that was selected, at the hand-off in DiscoveryTab — not by which rows are
 * clickable. Stating it there means the gate is one explicit type test on one
 * value, and it cannot be weakened by a second list disagreeing about what it
 * contains.
 *
 * A run on some future route is selectable and simply opens no panel: a click
 * that does nothing is honest, whereas a click that fires a request the backend
 * will refuse teaches the boundary by failure.
 */
function RunHistory({
  runs,
  selectedRunId,
  onSelectRun,
}: {
  runs: DiscoveryRun[]
  selectedRunId: string | null
  onSelectRun: (run: DiscoveryRun) => void
}) {
  const { t } = useI18n()
  const columns: Column<DiscoveryRun>[] = [
    {
      key: 'discovery_type',
      header: t('knowledgeProduction.discovery.colType'),
      // The comparison uses the raw API enum; only the caption is localized.
      render: r =>
        isLiteratureDiscoveryType(r.discovery_type)
          ? t('knowledgeProduction.discovery.literatureTitle')
          : t('knowledgeProduction.discovery.llmTitle'),
    },
    {
      key: 'status',
      header: t('knowledgeProduction.discovery.colStatus'),
      render: r => <StatusBadge status={r.status} />,
    },
    {
      key: 'outcome',
      header: t('knowledgeProduction.discovery.colOutcome'),
      // status != outcome: a finished run reports its scientific result here,
      // independently of how the execution went.
      render: r => (r.outcome ? t(OUTCOME_LABEL_KEYS[r.outcome]) : '—'),
    },
    {
      key: 'provider',
      header: t('knowledgeProduction.discovery.colProvider'),
      // Literature runs carry no provider/model — they show —. A model name is
      // a technical identifier and is never translated.
      render: r => [r.provider, r.model_name].filter(Boolean).join(' · ') || '—',
    },
    {
      key: 'created_at',
      header: t('knowledgeProduction.discovery.colCreated'),
      render: r => formatTimestamp(r.created_at),
    },
    {
      key: 'started_at',
      header: t('knowledgeProduction.discovery.colStarted'),
      render: r => formatTimestamp(r.started_at),
    },
    {
      key: 'finished_at',
      header: t('knowledgeProduction.discovery.colFinished'),
      render: r => formatTimestamp(r.finished_at),
    },
  ]

  return (
    <section className="kp-section kp-run-history" data-testid="kp-run-history">
      <h3 className="kp-section-title">{t('knowledgeProduction.discovery.historyTitle')}</h3>
      <DataTable
        columns={columns}
        rows={runs}
        getKey={r => r.run_id}
        onRowClick={onSelectRun}
        getRowClassName={r =>
          r.run_id === selectedRunId ? 'kp-run-selectable kp-run-selected' : 'kp-run-selectable'
        }
      />
    </section>
  )
}

export function DiscoveryTab({
  entityId,
  runs,
  error,
  onRunsChanged,
}: {
  /** The Workspace's BrainRegion. The route is the selection authority (§4). */
  entityId: string
  /** null while the first request is in flight; [] once known to be empty. */
  runs: DiscoveryRun[] | null
  error?: string | null
  /** Called after a run was STARTED, so the page refetches the real history. */
  onRunsChanged: () => void
}) {
  const { t } = useI18n()
  const [literatureRuns, setLiteratureRuns] = useState<LiteratureRun[] | null>(null)
  const [literatureError, setLiteratureError] = useState<string | null>(null)
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null)
  // Execution is synchronous, so this covers the whole attempt: POST in flight,
  // then the history refetch. One flag, because two would allow a state where
  // the button is live again while the run it started is not yet in the list.
  const [launching, setLaunching] = useState(false)
  const [launchError, setLaunchError] = useState<LaunchFailure | null>(null)

  useEffect(() => {
    let cancelled = false
    setLiteratureRuns(null)
    setLiteratureError(null)
    setSelectedRunId(null)
    fetchLiteratureRuns(entityId)
      .then(res => {
        if (!cancelled) setLiteratureRuns(res.items)
      })
      .catch((e: unknown) => {
        // Kept null, not []: an unreadable list is unknown, not empty.
        if (!cancelled) setLiteratureError(e instanceof Error ? e.message : String(e))
      })
    return () => {
      cancelled = true
    }
  }, [entityId])

  const selectRun = (run: DiscoveryRun) => {
    setSelectedRunId(prev => (prev === run.run_id ? null : run.run_id))
  }

  /**
   * Start ONE LLM Discovery for this Workspace's BrainRegion.
   *
   * The chain is the frozen backend one and this layer adds nothing to it: the
   * request starts a run, the provider answers, the run is persisted and its
   * candidates are stored. The frontend neither calls a model nor writes a run.
   *
   * On success the history is REFETCHED — the new run is taken from the backend
   * list, never spliced in from the response — and then handed to the candidate
   * panel, which loads its candidates from the read API. On failure NOTHING is
   * refetched and nothing is selected: a failed attempt added no run, and showing
   * an empty candidate list for it would report "found nothing" about a run that
   * never happened.
   */
  const launchLlmDiscovery = async () => {
    // The double-submit guard is the BUTTON's `disabled` state (set from
    // `launching` below), not a re-entry check here: React flushes discrete
    // clicks synchronously, so a second click is dispatched only after the
    // button has already gone disabled. Do not "simplify" that attribute away —
    // it is the only thing preventing two runs from one double-click.
    setLaunching(true)
    setLaunchError(null)
    try {
      const result = await executeLlmDiscovery(entityId)
      onRunsChanged()
      setSelectedRunId(result.run.run_id)
    } catch (e: unknown) {
      setLaunchError(readLaunchFailure(e))
    } finally {
      setLaunching(false)
    }
  }

  // One selection, two panels.
  //
  // The literature panel is handed the id ONLY when the selected run is on the
  // literature route, because it looks the run up in a SECOND list
  // (`/literature-runs`) that could disagree with the run history. Without this
  // gate a literature list containing an LLM run's id would be enough to make
  // the panel render — and query — a run it has no contract for.
  //
  // The candidate panel needs no such gate: it is handed the same rows the
  // history renders, so its own membership check IS the route check. It still
  // receives the raw id, so a run on another route simply opens nothing.
  const selectedRun = runs?.find(r => r.run_id === selectedRunId) ?? null
  const literatureRunId =
    selectedRun && isLiteratureDiscoveryType(selectedRun.discovery_type)
      ? selectedRun.run_id
      : null

  // null while the run history is unknown; derived from the SAME rows the history
  // renders, so the two can never disagree about which runs exist.
  const llmRuns =
    runs === null ? null : runs.filter(r => isLlmDiscoveryType(r.discovery_type))

  return (
    <div data-testid="kp-discovery-tab">
      {error && (
        <div className="state-box state-err" data-testid="kp-discovery-error">
          <p>{error}</p>
        </div>
      )}

      {/* A FAILED LAUNCH, reported as a failure. It is never rendered as an
          empty result: no run was produced, so "no candidates" would be a
          statement about something that does not exist. */}
      {launchError && (
        <div className="state-box state-err" data-testid="kp-llm-execute-error">
          <p data-testid="kp-llm-execute-error-headline">
            {t(launchFailureHeadlineKey(launchError.code))}
          </p>
          <p>{launchError.message}</p>
          {launchError.code && (
            <p className="kp-muted" data-testid="kp-llm-execute-error-code">
              {launchError.code}
            </p>
          )}
          {/* A run was created before it failed, so it is inspectable. */}
          {launchError.runId && (
            <p className="kp-muted" data-testid="kp-llm-execute-error-run">
              {t('knowledgeProduction.execution.runId')}: {launchError.runId}
            </p>
          )}
        </div>
      )}
      {!error && runs === null && (
        <div className="state-box" data-testid="kp-discovery-loading">
          <p>{t('knowledgeProduction.loading')}</p>
        </div>
      )}
      {!error && runs !== null && runs.length === 0 && (
        <TabPlaceholder
          icon="◎"
          title={t('knowledgeProduction.discovery.emptyTitle')}
          description={t('knowledgeProduction.discovery.emptyText')}
          blockTitle={t('knowledgeProduction.discovery.emptyBlockTitle')}
        >
          <FutureList
            items={t('knowledgeProduction.discovery.emptyItems').split(',').map(s => s.trim())}
          />
        </TabPlaceholder>
      )}
      {!error && runs !== null && runs.length > 0 && (
        <RunHistory runs={runs} selectedRunId={selectedRunId} onSelectRun={selectRun} />
      )}

      {/* Rendered only once the seed is known to HAVE runs: when it has none at
          all, the intentional empty state above already says so, and a second
          empty panel underneath would only repeat it. */}
      {!error && runs !== null && runs.length > 0 && (
        <LiteratureInspector
          literatureRuns={literatureRuns}
          error={literatureError}
          selectedRunId={literatureRunId}
        />
      )}

      {/* Phase P0-4A — the candidates an LLM Discovery run proposed. Read-only:
          no review action of any kind lives here. The panel resolves the id
          against `llmRuns` itself, which is why no gate is applied here. */}
      {!error && runs !== null && runs.length > 0 && (
        <LlmCandidateList llmRuns={llmRuns} selectedRunId={selectedRunId} />
      )}

      <div className="kp-card-grid kp-op-grid">
        {/* The ONLY live route (P0-4B). Literature gets no action, so its button
            stays disabled with its explanation — this phase wires one execution
            channel, not two. */}
        <DiscoveryCard
          glyph="✦"
          title={t('knowledgeProduction.discovery.llmTitle')}
          description={t('knowledgeProduction.discovery.llmDescription')}
          produces={t('knowledgeProduction.discovery.llmProduces').split(',').map(s => s.trim())}
          buttonLabel={t('knowledgeProduction.discovery.llmButton')}
          testId="kp-llm-discovery"
          action={launchLlmDiscovery}
          busy={launching}
          busyLabel={t('knowledgeProduction.execution.llmButtonBusy')}
          liveHint={t('knowledgeProduction.execution.llmHint')}
        />
        <DiscoveryCard
          glyph="▤"
          title={t('knowledgeProduction.discovery.literatureTitle')}
          description={t('knowledgeProduction.discovery.literatureDescription')}
          produces={t('knowledgeProduction.discovery.literatureProduces')
            .split(',')
            .map(s => s.trim())}
          buttonLabel={t('knowledgeProduction.discovery.literatureButton')}
          testId="kp-literature-discovery"
        />
      </div>
    </div>
  )
}

export function CandidatesTab() {
  const { t } = useI18n()
  return (
    <div data-testid="kp-candidates-tab">
      <TabPlaceholder
        icon="◇"
        title={t('knowledgeProduction.candidates.title')}
        description={t('knowledgeProduction.candidates.text')}
        blockTitle={t('knowledgeProduction.candidates.blockTitle')}
      >
        <FutureList
          items={[
            t('knowledgeProduction.candidates.circuits'),
            t('knowledgeProduction.candidates.connections'),
            t('knowledgeProduction.candidates.functions'),
            t('knowledgeProduction.candidates.relatedRegions'),
          ]}
        />
      </TabPlaceholder>
    </div>
  )
}

export function EvidenceTab() {
  const { t } = useI18n()
  // The traceability chain is a diagram of the four evidence levels; each node
  // is localized, the arrows are structural.
  const chain = [
    t('knowledgeProduction.evidence.publication'),
    t('knowledgeProduction.evidence.passage'),
    t('knowledgeProduction.evidence.assertion'),
    t('knowledgeProduction.evidence.canonical'),
  ].join('\n   ↓\n')
  return (
    <div data-testid="kp-evidence-tab">
      <TabPlaceholder
        icon="≡"
        title={t('knowledgeProduction.evidence.title')}
        description={t('knowledgeProduction.evidence.text')}
        blockTitle={t('knowledgeProduction.evidence.blockTitle')}
      >
        <pre className="kp-chain">{chain}</pre>
      </TabPlaceholder>
    </div>
  )
}

const CANONICALIZATION_DECISION_KEYS = ['merge', 'create', 'reject', 'defer'] as const

export function CanonicalizationTab() {
  const { t } = useI18n()
  return (
    <div data-testid="kp-canonicalization-tab">
      <TabPlaceholder
        icon="⇄"
        title={t('knowledgeProduction.canonicalization.title')}
        description={t('knowledgeProduction.canonicalization.text')}
        blockTitle={t('knowledgeProduction.canonicalization.blockTitle')}
      >
        <div className="kp-chip-list">
          {CANONICALIZATION_DECISION_KEYS.map(d => (
            <span className="kp-chip kp-chip--accent" key={d}>
              {t(`knowledgeProduction.canonicalization.${d}`)}
            </span>
          ))}
        </div>
      </TabPlaceholder>
    </div>
  )
}

const VALIDATION_CATEGORY_KEYS = ['rule', 'evidence', 'topology', 'humanReview'] as const

export function ValidationTab() {
  const { t } = useI18n()
  return (
    <div data-testid="kp-validation-tab">
      <TabPlaceholder
        icon="✓"
        title={t('knowledgeProduction.validation.title')}
        description={t('knowledgeProduction.validation.text')}
        blockTitle={t('knowledgeProduction.validation.blockTitle')}
      >
        <FutureList
          items={VALIDATION_CATEGORY_KEYS.map(k => t(`knowledgeProduction.validation.${k}`))}
        />
      </TabPlaceholder>
    </div>
  )
}

export function HistoryTab() {
  const { t } = useI18n()
  return (
    <div data-testid="kp-history-tab">
      <TabPlaceholder
        icon="↻"
        title={t('knowledgeProduction.history.title')}
        description={t('knowledgeProduction.history.text')}
        blockTitle={t('knowledgeProduction.history.blockTitle')}
      >
        <FutureList items={t('knowledgeProduction.history.items').split(',').map(s => s.trim())} />
      </TabPlaceholder>
    </div>
  )
}
