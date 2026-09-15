/**
 * BrainRegion Workspace tab bodies (Phase 1B/1C).
 *
 * Only Overview shows real Gate7B data. Every other tab is an explicit,
 * data-free placeholder describing what will live there — no counts, no rows,
 * no fake statuses. See docs/KNOWLEDGE_PRODUCTION_ARCHITECTURE.md §8 and the
 * visual contract in §12.
 */
import { useEffect, useState, type ReactNode } from 'react'
import { useI18n } from '../../i18n-context'
import { DataTable, type Column } from '../../components/DataTable'
import { fetchLiteratureRuns } from './kpApi'
import { LiteratureInspector } from './LiteratureInspector'
import {
  DISCOVERY_STATUS_LABEL_KEYS,
  DISCOVERY_STATUS_TONES,
  isLiteratureDiscoveryType,
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

function DiscoveryCard({
  glyph,
  title,
  description,
  produces,
  buttonLabel,
  testId,
}: {
  glyph: string
  title: string
  description: string
  produces: string[]
  buttonLabel: string
  testId: string
}) {
  const { t } = useI18n()
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
        disabled
        title={t('knowledgeProduction.discovery.executionTooltip')}
        data-testid={testId}
      >
        {buttonLabel}
      </button>
      <p className="kp-card-hint">{t('knowledgeProduction.discovery.executionHint')}</p>
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
 * Literature runs are SELECTABLE: they reached publications that can be
 * inspected. An LLM_DISCOVERY run is not, and the click is gated here on the
 * raw discovery_type rather than allowed through to a request the backend
 * deliberately answers with 404 — a user should not learn a boundary by
 * watching it fail. The gate uses the shared predicate, not an inline
 * `!== 'LLM_DISCOVERY'` comparison, so a future non-literature route cannot
 * silently become clickable.
 */
function RunHistory({
  runs,
  selectedRunId,
  onSelectLiteratureRun,
}: {
  runs: DiscoveryRun[]
  selectedRunId: string | null
  onSelectLiteratureRun: (run: DiscoveryRun) => void
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
        onRowClick={r => {
          // Non-literature rows are inert: the handler is the gate.
          if (isLiteratureDiscoveryType(r.discovery_type)) onSelectLiteratureRun(r)
        }}
        getRowClassName={r =>
          isLiteratureDiscoveryType(r.discovery_type)
            ? r.run_id === selectedRunId
              ? 'kp-run-selectable kp-run-selected'
              : 'kp-run-selectable'
            : undefined
        }
      />
    </section>
  )
}

export function DiscoveryTab({
  runs,
  error,
}: {
  /** null while the first request is in flight; [] once known to be empty. */
  runs: DiscoveryRun[] | null
  error?: string | null
}) {
  const { t } = useI18n()
  const [literatureRuns, setLiteratureRuns] = useState<LiteratureRun[] | null>(null)
  const [literatureError, setLiteratureError] = useState<string | null>(null)
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null)

  // The run rows already carry their seed, so this tab can load the literature
  // metadata it needs without the page passing an entity_id down.
  const entityId = runs && runs.length > 0 ? runs[0].seed_entity_id : null

  useEffect(() => {
    if (!entityId) return
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

  return (
    <div data-testid="kp-discovery-tab">
      {error && (
        <div className="state-box state-err" data-testid="kp-discovery-error">
          <p>{error}</p>
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
        <RunHistory
          runs={runs}
          selectedRunId={selectedRunId}
          onSelectLiteratureRun={selectRun}
        />
      )}

      {/* Rendered only once the seed is known to HAVE runs: when it has none at
          all, the intentional empty state above already says so, and a second
          empty panel underneath would only repeat it. */}
      {!error && runs !== null && runs.length > 0 && (
        <LiteratureInspector
          literatureRuns={literatureRuns}
          error={literatureError}
          selectedRunId={selectedRunId}
        />
      )}

      <div className="kp-card-grid kp-op-grid">
        <DiscoveryCard
          glyph="✦"
          title={t('knowledgeProduction.discovery.llmTitle')}
          description={t('knowledgeProduction.discovery.llmDescription')}
          produces={t('knowledgeProduction.discovery.llmProduces').split(',').map(s => s.trim())}
          buttonLabel={t('knowledgeProduction.discovery.llmButton')}
          testId="kp-llm-discovery"
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
