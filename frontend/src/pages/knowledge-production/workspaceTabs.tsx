/**
 * BrainRegion Workspace tab bodies (Phase 1B/1C).
 *
 * Only Overview shows real Gate7B data. Every other tab is an explicit,
 * data-free placeholder describing what will live there — no counts, no rows,
 * no fake statuses. See docs/KNOWLEDGE_PRODUCTION_ARCHITECTURE.md §8 and the
 * visual contract in §12.
 */
import type { ReactNode } from 'react'
import { DataTable, type Column } from '../../components/DataTable'
import {
  DISCOVERY_STATUS_LABELS,
  DISCOVERY_STATUS_TONES,
  type BrainRegionSeedDetail,
  type DiscoveryRun,
  type DiscoveryRunOutcome,
} from './types'

function Field({ label, value }: { label: string; value: string | number | null }) {
  return (
    <div className="kp-field">
      <span className="kp-field-label">{label}</span>
      <span className="kp-field-value">{value === null || value === '' ? '—' : value}</span>
    </div>
  )
}

function FieldSection({
  title,
  fields,
}: {
  title: string
  fields: { label: string; value: string | number | null }[]
}) {
  const shown = fields.filter(f => f.value !== null && f.value !== '')
  // a section with nothing authoritative to show is omitted rather than padded
  if (shown.length === 0) return null
  return (
    <section className="kp-section">
      <h3 className="kp-section-title">{title}</h3>
      <div className="kp-field-grid">
        {shown.map(f => (
          <Field key={f.label} label={f.label} value={f.value} />
        ))}
      </div>
    </section>
  )
}

export function OverviewTab({ detail }: { detail: BrainRegionSeedDetail }) {
  return (
    <div className="kp-overview" data-testid="kp-overview">
      <FieldSection
        title="Identity"
        fields={[
          { label: 'entity_id', value: detail.entity_id },
          { label: 'English name', value: detail.name_en },
          { label: '中文名', value: detail.name_zh },
          { label: 'abbreviation', value: detail.abbreviation },
        ]}
      />
      <FieldSection
        title="Anatomy"
        fields={[
          { label: 'granularity', value: detail.granularity_level },
          { label: 'region category', value: detail.region_category },
          { label: 'hemisphere', value: detail.hemisphere },
          { label: 'species (NCBI taxon)', value: detail.species_taxon_id },
        ]}
      />
      <FieldSection
        title="Hierarchy"
        fields={[
          // only identifiers the API actually exposes — no invented labels
          { label: 'parent region', value: detail.parent_region_pk },
          { label: 'hierarchy depth', value: detail.hierarchy_depth },
        ]}
      />
      <FieldSection
        title="Source / Mapping"
        fields={[
          { label: 'source Atlas', value: detail.atlas_names.join(', ') || null },
          { label: 'external region mapping', value: detail.external_region_ids.join(', ') || null },
          { label: 'mapping type', value: detail.mapping_types.join(', ') || null },
          {
            label: 'mapping review status',
            value: detail.mapping_review_statuses.join(', ') || null,
          },
        ]}
      />
      <FieldSection
        title="Governance"
        fields={[
          { label: 'record_status', value: detail.record_status },
          { label: 'review_status', value: detail.review_status },
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
      <button type="button" className="btn btn-sm" disabled title="Phase 2B/3 开放" data-testid={testId}>
        {buttonLabel}
      </button>
      <p className="kp-card-hint">
        Discovery Run persistence is available. Execution will be enabled in a later phase.
      </p>
    </div>
  )
}

/** Display-only labels for the frozen outcome vocabulary. Never persisted. */
const OUTCOME_LABELS: Record<DiscoveryRunOutcome, string> = {
  CANDIDATES_FOUND: 'Candidates found',
  NO_CANDIDATES_FOUND: 'No candidates found',
  NO_EVIDENCE_FOUND: 'No evidence found',
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
  return (
    <span className={`badge ${DISCOVERY_STATUS_TONES[status]}`}>
      {DISCOVERY_STATUS_LABELS[status]}
    </span>
  )
}

/** Read-only run history. No candidate counts, no evidence counts. */
function RunHistory({ runs }: { runs: DiscoveryRun[] }) {
  const columns: Column<DiscoveryRun>[] = [
    {
      key: 'discovery_type',
      header: 'Type',
      render: r => (r.discovery_type === 'LLM_DISCOVERY' ? 'LLM Discovery' : 'Literature Discovery'),
    },
    { key: 'status', header: 'Status', render: r => <StatusBadge status={r.status} /> },
    {
      key: 'outcome',
      header: 'Outcome',
      // status != outcome: a finished run reports its scientific result here,
      // independently of how the execution went.
      render: r => (r.outcome ? OUTCOME_LABELS[r.outcome] : '—'),
    },
    {
      key: 'provider',
      header: 'Provider / Model',
      // Literature runs carry no provider/model — they show —.
      render: r => [r.provider, r.model_name].filter(Boolean).join(' · ') || '—',
    },
    { key: 'created_at', header: 'Created', render: r => formatTimestamp(r.created_at) },
    { key: 'started_at', header: 'Started', render: r => formatTimestamp(r.started_at) },
    { key: 'finished_at', header: 'Finished', render: r => formatTimestamp(r.finished_at) },
  ]

  return (
    <section className="kp-section kp-run-history" data-testid="kp-run-history">
      <h3 className="kp-section-title">Run History</h3>
      <DataTable columns={columns} rows={runs} getKey={r => r.run_id} />
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
  return (
    <div data-testid="kp-discovery-tab">
      {error && (
        <div className="state-box state-err" data-testid="kp-discovery-error">
          <p>{error}</p>
        </div>
      )}
      {!error && runs === null && (
        <div className="state-box" data-testid="kp-discovery-loading">
          <p>载入中…</p>
        </div>
      )}
      {!error && runs !== null && runs.length === 0 && (
        <TabPlaceholder
          icon="◎"
          title="No Discovery Runs yet"
          description="This BrainRegion has not entered a discovery run. Both routes below write into the same run record, so the first run of either type will appear here."
          blockTitle="Recorded per run"
        >
          <FutureList
            items={['Type and status', 'Outcome', 'Provider / model', 'Created / started / finished']}
          />
        </TabPlaceholder>
      )}
      {!error && runs !== null && runs.length > 0 && <RunHistory runs={runs} />}

      <div className="kp-card-grid kp-op-grid">
        <DiscoveryCard
          glyph="✦"
          title="LLM Discovery"
          description="Generate high-recall circuit / connection / function candidates from the current BrainRegion using an LLM."
          produces={['Circuits', 'Connections', 'Functions']}
          buttonLabel="Start LLM Discovery"
          testId="kp-llm-discovery"
        />
        <DiscoveryCard
          glyph="▤"
          title="Literature Discovery"
          description="Search literature and extract evidence-backed candidate knowledge."
          produces={['Publications', 'Evidence passages']}
          buttonLabel="Start Literature Discovery"
          testId="kp-literature-discovery"
        />
      </div>
    </div>
  )
}

export function CandidatesTab() {
  return (
    <div data-testid="kp-candidates-tab">
      <TabPlaceholder
        icon="◇"
        title="Candidate Knowledge"
        description="Discovery writes candidates here, unreviewed and unmerged. Candidate subtypes stay inside this tab rather than becoming top-level tabs of their own."
        blockTitle="Candidate subtypes"
      >
        <FutureList items={['Circuits', 'Connections', 'Functions', 'Related Regions']} />
      </TabPlaceholder>
    </div>
  )
}

export function EvidenceTab() {
  return (
    <div data-testid="kp-evidence-tab">
      <TabPlaceholder
        icon="≡"
        title="Evidence"
        description="Knowledge here must remain traceable to source text. Every assertion keeps a resolvable path back to the passage it came from."
        blockTitle="Traceability chain"
      >
        <pre className="kp-chain">{`Publication
   ↓
Evidence Passage
   ↓
Knowledge Assertion
   ↓
Canonical Knowledge`}</pre>
      </TabPlaceholder>
    </div>
  )
}

const CANONICALIZATION_DECISIONS = ['MERGE', 'CREATE', 'REJECT', 'DEFER']

export function CanonicalizationTab() {
  return (
    <div data-testid="kp-canonicalization-tab">
      <TabPlaceholder
        icon="⇄"
        title="Canonicalization"
        description="Every candidate resolves to exactly one decision before it can be validated. The decision set is fixed; no candidate may stay undecided."
        blockTitle="Decisions"
      >
        <div className="kp-chip-list">
          {CANONICALIZATION_DECISIONS.map(d => (
            <span className="kp-chip kp-chip--accent" key={d}>
              {d}
            </span>
          ))}
        </div>
      </TabPlaceholder>
    </div>
  )
}

const VALIDATION_CATEGORIES = [
  'Rule Validation',
  'Evidence Validation',
  'Topology Validation',
  'Human Review',
]

export function ValidationTab() {
  return (
    <div data-testid="kp-validation-tab">
      <TabPlaceholder
        icon="✓"
        title="Validation"
        description="Each category below is an independent gate. A candidate must clear all of them before promotion is even offered."
        blockTitle="Validation categories"
      >
        <FutureList items={VALIDATION_CATEGORIES} />
      </TabPlaceholder>
    </div>
  )
}

const HISTORY_SOURCES = [
  'Discovery Runs',
  'Candidate decisions',
  'Evidence binding',
  'Canonicalization decisions',
  'Validation',
  'Promotion',
  'failures / retries',
]

export function HistoryTab() {
  return (
    <div data-testid="kp-history-tab">
      <TabPlaceholder
        icon="↻"
        title="History"
        description="No production history exists yet — nothing has run for this BrainRegion. This tab will become the append-only audit trail of everything that did."
        blockTitle="Recorded events"
      >
        <FutureList items={HISTORY_SOURCES} />
      </TabPlaceholder>
    </div>
  )
}
